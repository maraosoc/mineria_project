#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_emr_pipeline.py
===================
Orquestador para ejecutar los scripts 06-07 en EMR con Spark.
Permite ejecutar scripts de forma individual o secuencial en un cluster EMR.

Uso:
    # Ejecutar un script individual en cluster existente
    python run_emr_pipeline.py --script 06_entrenar_modelos_spark --cluster-id j-XXXXX
    
    # Crear cluster y ejecutar
    python run_emr_pipeline.py --script 06_entrenar_modelos_spark --create-cluster
    
    # Ejecutar secuencia completa
    python run_emr_pipeline.py --mode sequential --create-cluster --auto-terminate
    
    # Dry run
    python run_emr_pipeline.py --script 06_entrenar_modelos_spark --dry-run

Autor: Minería Project
"""

import argparse
import logging
import os
import sys
import time
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError


class EMRPipelineOrchestrator:
    """Orquesta la ejecución de scripts 06-07 en EMR"""
    
    def __init__(self, config_path: str, aws_config_path: str, execution_config_path: str):
        """
        Inicializa el orquestador EMR
        
        Args:
            config_path: Ruta a pipeline_config.yaml
            aws_config_path: Ruta a aws_config.yaml
            execution_config_path: Ruta a execution_config.yaml
        """
        self.config = self._load_config(config_path)
        self.aws_config = self._load_config(aws_config_path)
        self.exec_config = self._load_config(execution_config_path)
        
        # Inicializar clientes AWS
        region = self.aws_config['aws']['region']
        self.emr_client = boto3.client('emr', region_name=region)
        self.s3_client = boto3.client('s3', region_name=region)
        
        # Setup logging
        self._setup_logging()
        
        # Scripts disponibles para EMR
        self.emr_scripts = {
            "06_entrenar_modelos_spark": {
                "name": "06_entrenar_modelos_spark.py",
                "description": "Entrenar modelos con Spark MLlib",
                "output_path": "06_models/",
                "spark_config": {
                    "executor-memory": "16g",
                    "executor-cores": "4",
                    "driver-memory": "8g"
                }
            },
            "07_evaluar_modelos": {
                "name": "07_evaluar_modelos.py",
                "description": "Evaluar modelos entrenados",
                "output_path": "07_evaluation/",
                "spark_config": {
                    "executor-memory": "8g",
                    "executor-cores": "2",
                    "driver-memory": "4g"
                }
            }
        }
        
        self.cluster_id = None
    
    def _load_config(self, config_path: str) -> Dict:
        """Carga archivo de configuración YAML"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _setup_logging(self):
        """Configura el sistema de logging"""
        log_config = self.exec_config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO'))
        log_format = log_config.get('format', '[%(asctime)s] [%(levelname)s] - %(message)s')
        
        # Crear directorio de logs
        log_dir = Path('./logs')
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Nombre del archivo de log
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f'emr_pipeline_{timestamp}.log'
        
        # Configurar logging
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging configurado. Log file: {log_file}")
    
    def create_cluster(self) -> Optional[str]:
        """
        Crea un nuevo cluster EMR
        
        Returns:
            Cluster ID si se crea exitosamente, None en caso contrario
        """
        self.logger.info("🚀 Creando cluster EMR...")
        
        cluster_config = self.exec_config['emr']['cluster_config']
        bucket = self.aws_config['s3']['bucket_name']
        
        # Configuración del cluster
        cluster_params = {
            'Name': cluster_config['name'],
            'ReleaseLabel': cluster_config['release_label'],
            'LogUri': cluster_config['log_uri'],
            'Applications': [{'Name': 'Spark'}, {'Name': 'Hadoop'}],
            'Instances': {
                'MasterInstanceType': cluster_config['master_instance']['type'],
                'SlaveInstanceType': cluster_config['core_instances']['type'],
                'InstanceCount': cluster_config['core_instances']['count'] + 1,  # +1 para master
                'KeepJobFlowAliveWhenNoSteps': not cluster_config.get('auto_terminate', True),
                'Ec2KeyName': self.aws_config.get('ec2', {}).get('key_name', ''),
            },
            'VisibleToAllUsers': True,
            'JobFlowRole': 'EMR_EC2_DefaultRole',
            'ServiceRole': 'EMR_DefaultRole',
        }
        
        # Agregar bootstrap actions si existen
        bootstrap_path = f"s3://{bucket}/scripts/bootstrap/install_packages.sh"
        if self._s3_object_exists(bucket, "scripts/bootstrap/install_packages.sh"):
            cluster_params['BootstrapActions'] = [
                {
                    'Name': 'Install Python Packages',
                    'ScriptBootstrapAction': {
                        'Path': bootstrap_path
                    }
                }
            ]
        
        # Configuración Spark
        spark_config = self.exec_config['emr']['spark_config']
        cluster_params['Configurations'] = [
            {
                'Classification': 'spark-defaults',
                'Properties': {
                    'spark.executor.memory': spark_config.get('executor_memory', '8g'),
                    'spark.executor.cores': str(spark_config.get('executor_cores', 4)),
                    'spark.driver.memory': spark_config.get('driver_memory', '4g'),
                    'spark.dynamicAllocation.enabled': 'true',
                    'spark.shuffle.service.enabled': 'true'
                }
            }
        ]
        
        try:
            response = self.emr_client.run_job_flow(**cluster_params)
            cluster_id = response['JobFlowId']
            
            self.logger.info(f"✓ Cluster creado: {cluster_id}")
            self.logger.info("Esperando a que el cluster esté listo...")
            
            # Esperar a que el cluster esté en estado WAITING
            waiter = self.emr_client.get_waiter('cluster_running')
            waiter.wait(
                ClusterId=cluster_id,
                WaiterConfig={'Delay': 30, 'MaxAttempts': 40}
            )
            
            self.logger.info(f"✓ Cluster {cluster_id} está listo")
            return cluster_id
            
        except Exception as e:
            self.logger.error(f"✗ Error creando cluster: {e}")
            return None
    
    def _s3_object_exists(self, bucket: str, key: str) -> bool:
        """Verifica si un objeto existe en S3"""
        try:
            self.s3_client.head_object(Bucket=bucket, Key=key)
            return True
        except:
            return False
    
    def build_spark_submit_step(self, script_key: str) -> Dict:
        """
        Construye la configuración de un step de Spark para EMR
        
        Args:
            script_key: Clave del script (e.g., '06_entrenar_modelos_spark')
        
        Returns:
            Dict con configuración del step
        """
        script_info = self.emr_scripts[script_key]
        bucket = self.aws_config['s3']['bucket_name']
        script_path = f"s3://{bucket}/scripts/{script_info['name']}"
        
        # Configuración Spark específica del script
        spark_config = script_info.get('spark_config', {})
        
        # Args del script según el tipo
        params = self.exec_config.get('script_params', {}).get(script_key, {})
        
        if script_key == "06_entrenar_modelos_spark":
            script_args = [
                '--inputs', f"s3://{bucket}/{self.aws_config['s3']['paths']['training_data']}",
                '--out_model_dir', f"s3://{bucket}/{self.aws_config['s3']['paths']['models']}",
                '--out_metrics_dir', f"s3://{bucket}/{self.aws_config['s3']['paths']['evaluation']}",
                '--label_col', 'label',
                '--test_frac', str(params.get('test_fraction', 0.20)),
                '--seed', str(params.get('seed', 42))
            ]
        
        elif script_key == "07_evaluar_modelos":
            script_args = [
                '--model_dir', f"s3://{bucket}/{self.aws_config['s3']['paths']['models']}",
                '--test_data', f"s3://{bucket}/{self.aws_config['s3']['paths']['training_data']}",
                '--output', f"s3://{bucket}/{self.aws_config['s3']['paths']['evaluation']}"
            ]
        else:
            script_args = []
        
        # Construir el step
        step = {
            'Name': script_key,
            'ActionOnFailure': 'CONTINUE',
            'HadoopJarStep': {
                'Jar': 'command-runner.jar',
                'Args': [
                    'spark-submit',
                    '--deploy-mode', 'cluster',
                    '--executor-memory', spark_config.get('executor-memory', '8g'),
                    '--executor-cores', str(spark_config.get('executor-cores', 4)),
                    '--driver-memory', spark_config.get('driver-memory', '4g'),
                    script_path
                ] + script_args
            }
        }
        
        return step
    
    def submit_step(self, cluster_id: str, script_key: str, dry_run: bool = False) -> Optional[str]:
        """
        Envía un step al cluster EMR
        
        Args:
            cluster_id: ID del cluster
            script_key: Clave del script a ejecutar
            dry_run: Si es True, solo simula el envío
        
        Returns:
            Step ID si se envía exitosamente, None en caso contrario
        """
        script_info = self.emr_scripts[script_key]
        self.logger.info("=" * 80)
        self.logger.info(f"Preparando step: {script_key}")
        self.logger.info(f"Descripción: {script_info['description']}")
        self.logger.info("=" * 80)
        
        step_config = self.build_spark_submit_step(script_key)
        
        # Log del comando
        spark_args = step_config['HadoopJarStep']['Args']
        self.logger.info(f"Comando Spark: {' '.join(spark_args)}")
        
        if dry_run:
            self.logger.info("[DRY RUN] No se enviará el step")
            return "dry-run-step-id"
        
        try:
            response = self.emr_client.add_job_flow_steps(
                JobFlowId=cluster_id,
                Steps=[step_config]
            )
            
            step_id = response['StepIds'][0]
            self.logger.info(f"✓ Step enviado: {step_id}")
            return step_id
            
        except Exception as e:
            self.logger.error(f"✗ Error enviando step: {e}")
            return None
    
    def wait_for_step(self, cluster_id: str, step_id: str) -> Tuple[bool, str]:
        """
        Espera a que un step complete su ejecución
        
        Args:
            cluster_id: ID del cluster
            step_id: ID del step
        
        Returns:
            Tuple (success: bool, message: str)
        """
        self.logger.info(f"Esperando a que complete step {step_id}...")
        
        start_time = time.time()
        timeout = 7200  # 2 horas max
        check_interval = 30  # segundos
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                return False, f"Timeout después de {timeout}s"
            
            try:
                response = self.emr_client.describe_step(
                    ClusterId=cluster_id,
                    StepId=step_id
                )
                
                step = response['Step']
                state = step['Status']['State']
                
                if state == 'COMPLETED':
                    self.logger.info(f"✓ Step completado en {elapsed:.1f}s")
                    return True, f"Completado en {elapsed:.1f}s"
                
                elif state in ['FAILED', 'CANCELLED', 'INTERRUPTED']:
                    reason = step['Status'].get('StateChangeReason', {}).get('Message', 'Unknown')
                    self.logger.error(f"✗ Step falló: {state} - {reason}")
                    return False, f"{state}: {reason}"
                
                elif state in ['PENDING', 'RUNNING']:
                    self.logger.info(f"Step en estado {state} (elapsed: {elapsed:.0f}s)...")
                    time.sleep(check_interval)
                
                else:
                    self.logger.warning(f"Estado desconocido: {state}")
                    time.sleep(check_interval)
                    
            except Exception as e:
                self.logger.error(f"Error consultando estado: {e}")
                time.sleep(check_interval)
    
    def run_script(self, cluster_id: str, script_key: str, 
                   wait: bool = True, dry_run: bool = False) -> Tuple[bool, str]:
        """
        Ejecuta un script en EMR
        
        Args:
            cluster_id: ID del cluster
            script_key: Clave del script a ejecutar
            wait: Si es True, espera a que el step complete
            dry_run: Si es True, solo simula la ejecución
        
        Returns:
            Tuple (success: bool, message: str)
        """
        if script_key not in self.emr_scripts:
            return False, f"Script desconocido: {script_key}"
        
        # Enviar step
        step_id = self.submit_step(cluster_id, script_key, dry_run)
        
        if not step_id:
            return False, "Error enviando step"
        
        if dry_run or not wait:
            return True, f"Step enviado: {step_id}"
        
        # Esperar a que complete
        return self.wait_for_step(cluster_id, step_id)
    
    def run_sequential(self, cluster_id: str) -> Dict[str, Tuple[bool, str]]:
        """
        Ejecuta scripts 06-07 secuencialmente
        
        Args:
            cluster_id: ID del cluster
        
        Returns:
            Dict con resultados de cada script
        """
        results = {}
        scripts_to_run = self.exec_config['execution']['emr_scripts']
        
        self.logger.info("🚀 Iniciando pipeline EMR secuencial")
        self.logger.info(f"Cluster: {cluster_id}")
        self.logger.info(f"Scripts a ejecutar: {', '.join(scripts_to_run)}")
        
        for script_key in scripts_to_run:
            success, message = self.run_script(cluster_id, script_key, wait=True)
            results[script_key] = (success, message)
            
            if not success:
                self.logger.error(f"Pipeline detenido debido a error en {script_key}")
                if not self.exec_config['control'].get('continue_on_error', False):
                    break
        
        # Resumen
        self.logger.info("\n" + "=" * 80)
        self.logger.info("RESUMEN DE EJECUCIÓN EMR")
        self.logger.info("=" * 80)
        
        for script_key, (success, message) in results.items():
            status = "✓ ÉXITO" if success else "✗ FALLO"
            self.logger.info(f"{status:10} | {script_key:35} | {message}")
        
        return results
    
    def terminate_cluster(self, cluster_id: str):
        """Termina el cluster EMR"""
        self.logger.info(f"Terminando cluster {cluster_id}...")
        
        try:
            self.emr_client.terminate_job_flows(JobFlowIds=[cluster_id])
            self.logger.info(f"✓ Cluster {cluster_id} en proceso de terminación")
        except Exception as e:
            self.logger.error(f"✗ Error terminando cluster: {e}")
    
    def upload_logs_to_s3(self):
        """Sube logs de ejecución a S3"""
        if not self.exec_config['logging'].get('upload_to_s3', False):
            return
        
        log_dir = Path('./logs')
        bucket = self.aws_config['s3']['bucket_name']
        s3_prefix = self.exec_config['logging'].get('s3_log_prefix', 'logs/pipeline_runs/')
        
        self.logger.info("Subiendo logs a S3...")
        
        for log_file in log_dir.glob('emr_pipeline_*.log'):
            s3_key = f"{s3_prefix}{log_file.name}"
            try:
                self.s3_client.upload_file(str(log_file), bucket, s3_key)
                self.logger.info(f"✓ Log subido: s3://{bucket}/{s3_key}")
            except Exception as e:
                self.logger.error(f"Error subiendo log {log_file}: {e}")


def parse_args():
    """Parse argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Orquestador de pipeline EMR para scripts 06-07",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--mode',
        choices=['individual', 'sequential'],
        default='individual',
        help='Modo de ejecución'
    )
    
    parser.add_argument(
        '--script',
        choices=['06_entrenar_modelos_spark', '07_evaluar_modelos'],
        help='Script individual a ejecutar (requerido si mode=individual)'
    )
    
    parser.add_argument(
        '--cluster-id',
        help='ID de cluster EMR existente'
    )
    
    parser.add_argument(
        '--create-cluster',
        action='store_true',
        help='Crear un nuevo cluster EMR'
    )
    
    parser.add_argument(
        '--auto-terminate',
        action='store_true',
        help='Terminar el cluster después de ejecutar (solo si se crea nuevo)'
    )
    
    parser.add_argument(
        '--no-wait',
        action='store_true',
        help='No esperar a que los steps completen'
    )
    
    parser.add_argument(
        '--config',
        default='config/pipeline_config.yaml',
        help='Ruta al archivo de configuración del pipeline'
    )
    
    parser.add_argument(
        '--aws-config',
        default='config/aws_config.yaml',
        help='Ruta al archivo de configuración AWS'
    )
    
    parser.add_argument(
        '--execution-config',
        default='config/execution_config.yaml',
        help='Ruta al archivo de configuración de ejecución'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simular ejecución sin ejecutar comandos'
    )
    
    return parser.parse_args()


def main():
    """Función principal"""
    args = parse_args()
    
    # Validar argumentos
    if args.mode == 'individual' and not args.script:
        print("ERROR: --script es requerido cuando mode=individual")
        sys.exit(1)
    
    if not args.create_cluster and not args.cluster_id:
        print("ERROR: Se requiere --cluster-id o --create-cluster")
        sys.exit(1)
    
    try:
        # Inicializar orquestador
        orchestrator = EMRPipelineOrchestrator(
            config_path=args.config,
            aws_config_path=args.aws_config,
            execution_config_path=args.execution_config
        )
        
        # Obtener o crear cluster
        if args.create_cluster:
            cluster_id = orchestrator.create_cluster()
            if not cluster_id:
                print("✗ Error creando cluster")
                sys.exit(1)
            created_cluster = True
        else:
            cluster_id = args.cluster_id
            created_cluster = False
        
        orchestrator.cluster_id = cluster_id
        
        # Ejecutar según modo
        if args.mode == 'individual':
            success, message = orchestrator.run_script(
                cluster_id, 
                args.script, 
                wait=not args.no_wait,
                dry_run=args.dry_run
            )
            
            if success:
                print(f"\n✓ Script {args.script} completado exitosamente")
                exit_code = 0
            else:
                print(f"\n✗ Script {args.script} falló: {message}")
                exit_code = 1
        
        else:  # sequential
            results = orchestrator.run_sequential(cluster_id)
            
            # Determinar código de salida
            all_success = all(success for success, _ in results.values())
            exit_code = 0 if all_success else 1
        
        # Terminar cluster si se creó y se solicitó auto-terminate
        if created_cluster and args.auto_terminate:
            orchestrator.terminate_cluster(cluster_id)
        
        # Subir logs a S3
        orchestrator.upload_logs_to_s3()
        
        sys.exit(exit_code)
    
    except Exception as e:
        print(f"\n✗ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
