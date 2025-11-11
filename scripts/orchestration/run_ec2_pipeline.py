#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_ec2_pipeline.py
===================
Orquestador para ejecutar los scripts 01-05 en EC2 de forma individual o secuencial.
Permite ejecutar un script a la vez para validar resultados antes de continuar.

Uso:
    # Ejecutar un script individual
    python run_ec2_pipeline.py --script 01_procesar_sentinel
    
    # Ejecutar secuencia completa
    python run_ec2_pipeline.py --mode sequential
    
    # Ejecutar hasta cierto paso
    python run_ec2_pipeline.py --mode sequential --stop-after 03_tabular_features
    
    # Dry run (simular sin ejecutar)
    python run_ec2_pipeline.py --script 01_procesar_sentinel --dry-run

Autor: Minería Project
"""

import argparse
import logging
import os
import sys
import time
import yaml
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError


class EC2PipelineOrchestrator:
    """Orquesta la ejecución de scripts 01-05 en EC2"""
    
    def __init__(self, config_path: str, aws_config_path: str, execution_config_path: str):
        """
        Inicializa el orquestador
        
        Args:
            config_path: Ruta a pipeline_config.yaml
            aws_config_path: Ruta a aws_config.yaml
            execution_config_path: Ruta a execution_config.yaml
        """
        self.config = self._load_config(config_path)
        self.aws_config = self._load_config(aws_config_path)
        self.exec_config = self._load_config(execution_config_path)
        
        # Inicializar clientes AWS
        self.s3_client = boto3.client('s3', region_name=self.aws_config['aws']['region'])
        
        # Setup logging
        self._setup_logging()
        
        # Directorio base del proyecto
        self.project_root = Path(__file__).parent.parent.parent
        self.scripts_dir = self.project_root / "scripts"
        
        # Crear directorios de trabajo
        self._setup_directories()
        
        # Scripts disponibles para EC2
        self.ec2_scripts = {
            "01_procesar_sentinel": {
                "name": "01_procesar_sentinel.py",
                "description": "Procesar archivos Sentinel-2",
                "output_path": "01_processed/"
            },
            "02_generar_mascaras": {
                "name": "02_generar_mascaras.py",
                "description": "Generar máscaras de calidad",
                "output_path": "02_masks/"
            },
            "03_tabular_features": {
                "name": "03_tabular_features.py",
                "description": "Tabular features con Polars",
                "output_path": "03_features/"
            },
            "04_rasterizar_labels": {
                "name": "04_rasterizar_labels.py",
                "description": "Rasterizar labels desde vectores",
                "output_path": "04_labels/"
            },
            "05_unir_features_labels": {
                "name": "05_unir_features_labels.py",
                "description": "Unir features con labels",
                "output_path": "05_training_data/"
            }
        }
    
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
        log_dir = Path(self.exec_config['ec2'].get('log_dir', './logs'))
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Nombre del archivo de log
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f'ec2_pipeline_{timestamp}.log'
        
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
    
    def _setup_directories(self):
        """Crea directorios de trabajo necesarios"""
        work_dir = Path(self.exec_config['ec2'].get('work_dir', './work'))
        work_dir.mkdir(parents=True, exist_ok=True)
        
        log_dir = Path(self.exec_config['ec2'].get('log_dir', './logs'))
        log_dir.mkdir(parents=True, exist_ok=True)
    
    def check_s3_output(self, s3_path: str) -> bool:
        """
        Verifica si existen outputs en S3
        
        Args:
            s3_path: Path relativo en S3 (e.g., '01_processed/')
        
        Returns:
            True si existen archivos, False en caso contrario
        """
        bucket = self.aws_config['s3']['bucket_name']
        full_path = f"s3://{bucket}/{s3_path}"
        
        self.logger.info(f"Verificando outputs en: {full_path}")
        
        try:
            # Listar objetos en el path
            response = self.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=s3_path,
                MaxKeys=10
            )
            
            has_contents = 'Contents' in response and len(response['Contents']) > 0
            
            if has_contents:
                count = response.get('KeyCount', 0)
                self.logger.info(f"✓ Encontrados {count} archivos en {s3_path}")
                return True
            else:
                self.logger.warning(f"✗ No se encontraron archivos en {s3_path}")
                return False
                
        except ClientError as e:
            self.logger.error(f"Error verificando S3: {e}")
            return False
    
    def build_script_command(self, script_key: str) -> List[str]:
        """
        Construye el comando para ejecutar un script
        
        Args:
            script_key: Clave del script (e.g., '01_procesar_sentinel')
        
        Returns:
            Lista con el comando y argumentos
        """
        script_info = self.ec2_scripts[script_key]
        script_path = self.scripts_dir / script_info['name']
        
        # Python executable (usar venv si existe)
        venv_path = Path(self.exec_config['ec2'].get('venv_path', ''))
        if venv_path.exists():
            python_exe = str(venv_path / 'bin' / 'python')
        else:
            python_exe = 'python3'
        
        # Comando base
        cmd = [python_exe, str(script_path)]
        
        # Agregar parámetros específicos del script
        params = self.exec_config.get('script_params', {}).get(script_key, {})
        bucket = self.aws_config['s3']['bucket_name']
        
        # Construir argumentos según el script
        if script_key == "01_procesar_sentinel":
            cmd.extend([
                '--input', f"s3://{bucket}/{self.aws_config['s3']['paths']['raw_sentinel']}",
                '--output', f"s3://{bucket}/{self.aws_config['s3']['paths']['processed']}",
                '--bands', params.get('bands', 'B01,B02,B03,B04,B08,B11,B12'),
                '--resolution', str(params.get('resolution', 20)),
                '--indices', params.get('indices', 'NDVI,NDWI')
            ])
        
        elif script_key == "02_generar_mascaras":
            cmd.extend([
                '--input', f"s3://{bucket}/{self.aws_config['s3']['paths']['processed']}",
                '--output', f"s3://{bucket}/{self.aws_config['s3']['paths']['masks']}",
                '--cloud-threshold', str(params.get('cloud_threshold', 50))
            ])
        
        elif script_key == "03_tabular_features":
            cmd.extend([
                '--input', f"s3://{bucket}/{self.aws_config['s3']['paths']['processed']}",
                '--masks', f"s3://{bucket}/{self.aws_config['s3']['paths']['masks']}",
                '--output', f"s3://{bucket}/{self.aws_config['s3']['paths']['features']}",
                '--aggregations', params.get('aggregations', 'mean,std,min,max')
            ])
        
        elif script_key == "04_rasterizar_labels":
            cmd.extend([
                '--input', f"s3://{bucket}/{self.aws_config['s3']['paths']['shapes']}",
                '--output', f"s3://{bucket}/{self.aws_config['s3']['paths']['labels']}",
                '--pixel-size', str(params.get('pixel_size', 20)),
                '--buffer', str(params.get('buffer_distance', -60))
            ])
        
        elif script_key == "05_unir_features_labels":
            cmd.extend([
                '--features', f"s3://{bucket}/{self.aws_config['s3']['paths']['features']}",
                '--labels', f"s3://{bucket}/{self.aws_config['s3']['paths']['labels']}",
                '--output', f"s3://{bucket}/{self.aws_config['s3']['paths']['training_data']}"
            ])
        
        return cmd
    
    def run_script(self, script_key: str, dry_run: bool = False) -> Tuple[bool, str]:
        """
        Ejecuta un script individual
        
        Args:
            script_key: Clave del script a ejecutar
            dry_run: Si es True, solo simula la ejecución
        
        Returns:
            Tuple (success: bool, message: str)
        """
        if script_key not in self.ec2_scripts:
            return False, f"Script desconocido: {script_key}"
        
        script_info = self.ec2_scripts[script_key]
        self.logger.info("=" * 80)
        self.logger.info(f"Ejecutando: {script_key}")
        self.logger.info(f"Descripción: {script_info['description']}")
        self.logger.info("=" * 80)
        
        # Construir comando
        cmd = self.build_script_command(script_key)
        self.logger.info(f"Comando: {' '.join(cmd)}")
        
        if dry_run:
            self.logger.info("[DRY RUN] No se ejecutará el comando")
            return True, "Dry run completado"
        
        # Ejecutar
        start_time = time.time()
        timeout = self.exec_config['monitoring']['timeouts'].get(script_key, 3600)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            
            elapsed = time.time() - start_time
            
            # Log output
            if result.stdout:
                self.logger.info(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                self.logger.warning(f"STDERR:\n{result.stderr}")
            
            if result.returncode == 0:
                self.logger.info(f"✓ Script completado exitosamente en {elapsed:.1f}s")
                
                # Validar outputs en S3 si está configurado
                if self.exec_config['validation']['check_outputs']:
                    time.sleep(self.exec_config['validation']['wait_before_check'])
                    output_path = script_info['output_path']
                    
                    if self.check_s3_output(output_path):
                        return True, f"Completado con éxito en {elapsed:.1f}s"
                    else:
                        return False, "Script ejecutado pero no se encontraron outputs en S3"
                
                return True, f"Completado con éxito en {elapsed:.1f}s"
            else:
                self.logger.error(f"✗ Script falló con código {result.returncode}")
                return False, f"Error code {result.returncode}: {result.stderr[:500]}"
        
        except subprocess.TimeoutExpired:
            self.logger.error(f"✗ Timeout después de {timeout}s")
            return False, f"Timeout después de {timeout}s"
        
        except Exception as e:
            self.logger.error(f"✗ Error inesperado: {e}")
            return False, str(e)
    
    def run_sequential(self, stop_after: Optional[str] = None) -> Dict[str, Tuple[bool, str]]:
        """
        Ejecuta scripts secuencialmente
        
        Args:
            stop_after: Script donde detener la ejecución (opcional)
        
        Returns:
            Dict con resultados de cada script
        """
        results = {}
        scripts_to_run = self.exec_config['execution']['ec2_scripts']
        
        self.logger.info("🚀 Iniciando pipeline EC2 secuencial")
        self.logger.info(f"Scripts a ejecutar: {', '.join(scripts_to_run)}")
        
        for script_key in scripts_to_run:
            success, message = self.run_script(script_key)
            results[script_key] = (success, message)
            
            if not success:
                self.logger.error(f"Pipeline detenido debido a error en {script_key}")
                if not self.exec_config['control'].get('continue_on_error', False):
                    break
            
            # Detener si se alcanzó el límite especificado
            if stop_after and script_key == stop_after:
                self.logger.info(f"Deteniendo después de {stop_after} según configuración")
                break
        
        # Resumen
        self.logger.info("\n" + "=" * 80)
        self.logger.info("RESUMEN DE EJECUCIÓN")
        self.logger.info("=" * 80)
        
        for script_key, (success, message) in results.items():
            status = "✓ ÉXITO" if success else "✗ FALLO"
            self.logger.info(f"{status:10} | {script_key:30} | {message}")
        
        return results
    
    def upload_logs_to_s3(self):
        """Sube logs de ejecución a S3"""
        if not self.exec_config['logging'].get('upload_to_s3', False):
            return
        
        log_dir = Path(self.exec_config['ec2'].get('log_dir', './logs'))
        bucket = self.aws_config['s3']['bucket_name']
        s3_prefix = self.exec_config['logging'].get('s3_log_prefix', 'logs/pipeline_runs/')
        
        self.logger.info("Subiendo logs a S3...")
        
        for log_file in log_dir.glob('*.log'):
            s3_key = f"{s3_prefix}{log_file.name}"
            try:
                self.s3_client.upload_file(str(log_file), bucket, s3_key)
                self.logger.info(f"✓ Log subido: s3://{bucket}/{s3_key}")
            except Exception as e:
                self.logger.error(f"Error subiendo log {log_file}: {e}")


def parse_args():
    """Parse argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(
        description="Orquestador de pipeline EC2 para scripts 01-05",
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
        choices=[
            '01_procesar_sentinel',
            '02_generar_mascaras',
            '03_tabular_features',
            '04_rasterizar_labels',
            '05_unir_features_labels'
        ],
        help='Script individual a ejecutar (requerido si mode=individual)'
    )
    
    parser.add_argument(
        '--stop-after',
        choices=[
            '01_procesar_sentinel',
            '02_generar_mascaras',
            '03_tabular_features',
            '04_rasterizar_labels',
            '05_unir_features_labels'
        ],
        help='Detener después de este script (solo para mode=sequential)'
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
    
    try:
        # Inicializar orquestador
        orchestrator = EC2PipelineOrchestrator(
            config_path=args.config,
            aws_config_path=args.aws_config,
            execution_config_path=args.execution_config
        )
        
        # Ejecutar según modo
        if args.mode == 'individual':
            success, message = orchestrator.run_script(args.script, dry_run=args.dry_run)
            
            if success:
                print(f"\n✓ Script {args.script} completado exitosamente")
                exit_code = 0
            else:
                print(f"\n✗ Script {args.script} falló: {message}")
                exit_code = 1
        
        else:  # sequential
            results = orchestrator.run_sequential(stop_after=args.stop_after)
            
            # Determinar código de salida
            all_success = all(success for success, _ in results.values())
            exit_code = 0 if all_success else 1
        
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
