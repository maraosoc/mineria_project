#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
submit_emr_steps.py
-------------------
Envía steps de Spark a un cluster EMR existente.

Uso:
  # Enviar step individual
  python submit_emr_steps.py \
    --cluster-id j-XXXXXXXXXXXXX \
    --step procesar_sentinel \
    --config config/pipeline_config.yaml

  # Pipeline completo
  python submit_emr_steps.py \
    --cluster-id j-XXXXXXXXXXXXX \
    --pipeline full \
    --wait

  # Crear cluster y ejecutar
  python submit_emr_steps.py \
    --create-cluster \
    --pipeline full \
    --auto-terminate
"""

import argparse
import json
import time
import yaml
from pathlib import Path
from typing import List, Dict, Optional

import boto3
from botocore.exceptions import ClientError


class EMRJobSubmitter:
    """Gestiona envío de jobs a EMR"""
    
    def __init__(self, aws_config_path: str, pipeline_config_path: str):
        with open(aws_config_path, 'r') as f:
            self.aws_config = yaml.safe_load(f)
        
        with open(pipeline_config_path, 'r') as f:
            self.pipeline_config = yaml.safe_load(f)
        
        self.emr_client = boto3.client('emr', region_name=self.aws_config['aws']['region'])
        self.s3_client = boto3.client('s3', region_name=self.aws_config['aws']['region'])
        
        self.bucket = self.aws_config['s3']['bucket_name']
        self.s3_paths = self.aws_config['s3']['paths']
    
    def create_cluster(self, auto_terminate: bool = False) -> str:
        """Crea un nuevo cluster EMR"""
        emr_config = self.aws_config['emr']
        
        print(f"\n{'='*70}")
        print("CREANDO CLUSTER EMR")
        print(f"{'='*70}")
        print(f"  Nombre: {emr_config['cluster_name']}")
        print(f"  Release: {emr_config['release_label']}")
        print(f"  Master: {emr_config['master_instance']['type']}")
        print(f"  Core: {emr_config['core_instances']['count']}x {emr_config['core_instances']['type']}")
        
        instances_config = {
            'InstanceGroups': [
                {
                    'Name': 'Master',
                    'InstanceRole': 'MASTER',
                    'InstanceType': emr_config['master_instance']['type'],
                    'InstanceCount': 1,
                    'Market': emr_config['master_instance']['market'],
                    'EbsConfiguration': {
                        'EbsBlockDeviceConfigs': [{
                            'VolumeSpecification': {
                                'SizeInGB': emr_config['master_instance']['ebs_size'],
                                'VolumeType': 'gp3'
                            },
                            'VolumesPerInstance': 1
                        }]
                    }
                },
                {
                    'Name': 'Core',
                    'InstanceRole': 'CORE',
                    'InstanceType': emr_config['core_instances']['type'],
                    'InstanceCount': emr_config['core_instances']['count'],
                    'Market': emr_config['core_instances']['market'],
                    'BidPrice': emr_config['core_instances'].get('bid_price', ''),
                    'EbsConfiguration': {
                        'EbsBlockDeviceConfigs': [{
                            'VolumeSpecification': {
                                'SizeInGB': emr_config['core_instances']['ebs_size'],
                                'VolumeType': 'gp3'
                            },
                            'VolumesPerInstance': 1
                        }]
                    }
                }
            ],
            'Ec2KeyName': 'your-key-pair',  # ⚠️ Cambiar por tu key pair
            'KeepJobFlowAliveWhenNoSteps': not auto_terminate
        }
        
        applications = [{'Name': app} for app in emr_config['applications']]
        
        configurations = emr_config.get('configurations', [])
        
        bootstrap_actions = []
        if 'bootstrap_actions' in emr_config:
            for ba in emr_config['bootstrap_actions']:
                bootstrap_actions.append({
                    'Name': ba['name'],
                    'ScriptBootstrapAction': {
                        'Path': ba['path']
                    }
                })
        
        response = self.emr_client.run_job_flow(
            Name=emr_config['cluster_name'],
            ReleaseLabel=emr_config['release_label'],
            LogUri=emr_config['log_uri'],
            Applications=applications,
            Instances=instances_config,
            Configurations=configurations,
            BootstrapActions=bootstrap_actions,
            ServiceRole='EMR_DefaultRole',
            JobFlowRole='EMR_EC2_DefaultRole',
            VisibleToAllUsers=True,
            Tags=[
                {'Key': 'Project', 'Value': 'Mineria'},
                {'Key': 'Purpose', 'Value': 'BosqueClassification'}
            ]
        )
        
        cluster_id = response['JobFlowId']
        print(f"\n  ✓ Cluster creado: {cluster_id}")
        print(f"  ⏳ Esperando que el cluster esté listo...")
        
        self.wait_for_cluster_ready(cluster_id)
        
        return cluster_id
    
    def wait_for_cluster_ready(self, cluster_id: str, timeout: int = 1800):
        """Espera a que el cluster esté en estado WAITING"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = self.emr_client.describe_cluster(ClusterId=cluster_id)
            state = response['Cluster']['Status']['State']
            
            print(f"    Estado: {state}", end='\r')
            
            if state == 'WAITING':
                print(f"\n  ✓ Cluster listo!")
                return True
            elif state in ['TERMINATING', 'TERMINATED', 'TERMINATED_WITH_ERRORS']:
                raise Exception(f"Cluster terminó con estado: {state}")
            
            time.sleep(30)
        
        raise TimeoutError(f"Timeout esperando cluster después de {timeout}s")
    
    def get_step_config(self, step_name: str) -> Dict:
        """Genera configuración de step según nombre"""
        
        s3_scripts = f"s3://{self.bucket}/{self.s3_paths['scripts']}"
        
        steps = {
            'procesar_sentinel': {
                'Name': 'Step 1: Procesar Sentinel-2',
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Jar': 'command-runner.jar',
                    'Args': [
                        'spark-submit',
                        '--deploy-mode', 'cluster',
                        '--executor-memory', '16g',
                        '--executor-cores', '4',
                        f'{s3_scripts}01_procesar_sentinel.py',
                        '--input', f"s3://{self.bucket}/{self.s3_paths['raw_sentinel']}*.SAFE",
                        '--output', f"s3://{self.bucket}/{self.s3_paths['processed']}",
                        '--bands', ','.join(self.pipeline_config['sentinel']['bands']),
                        '--resolution', str(self.pipeline_config['sentinel']['resolution']),
                        '--indices', ','.join(self.pipeline_config['sentinel']['indices'])
                    ]
                }
            },
            
            'generar_mascaras': {
                'Name': 'Step 2: Generar Máscaras',
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Jar': 'command-runner.jar',
                    'Args': [
                        'spark-submit',
                        '--deploy-mode', 'cluster',
                        f'{s3_scripts}02_generar_mascaras.py',
                        '--input', f"s3://{self.bucket}/{self.s3_paths['processed']}*.tif",
                        '--output', f"s3://{self.bucket}/{self.s3_paths['masks']}"
                    ]
                }
            },
            
            'tabular_features': {
                'Name': 'Step 3: Tabular Features',
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Jar': 'command-runner.jar',
                    'Args': [
                        'spark-submit',
                        '--deploy-mode', 'cluster',
                        '--executor-memory', '16g',
                        f'{s3_scripts}03_tabular_features.py',
                        '--rasters', f"s3://{self.bucket}/{self.s3_paths['processed']}*.tif",
                        '--masks', f"s3://{self.bucket}/{self.s3_paths['masks']}*.tif",
                        '--output', f"s3://{self.bucket}/{self.s3_paths['features']}composite.parquet"
                    ]
                }
            },
            
            'rasterizar_labels': {
                'Name': 'Step 4: Rasterizar Labels',
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Jar': 'command-runner.jar',
                    'Args': [
                        'spark-submit',
                        f'{s3_scripts}04_rasterizar_labels.py',
                        '--bosque_shp', f"s3://{self.bucket}/{self.s3_paths['shapes']}bosque.shp",
                        '--perimetro_shp', f"s3://{self.bucket}/{self.s3_paths['shapes']}study_area.shp",
                        '--ref_raster', f"s3://{self.bucket}/{self.s3_paths['processed']}*_procesado.tif",
                        '--output', f"s3://{self.bucket}/{self.s3_paths['labels']}forest_labels.tif",
                        '--erosion_pixels', str(self.pipeline_config['labels']['erosion_pixels'])
                    ]
                }
            },
            
            'unir_features_labels': {
                'Name': 'Step 5: Unir Features + Labels',
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Jar': 'command-runner.jar',
                    'Args': [
                        'spark-submit',
                        f'{s3_scripts}05_unir_features_labels.py',
                        '--features', f"s3://{self.bucket}/{self.s3_paths['features']}composite.parquet",
                        '--labels', f"s3://{self.bucket}/{self.s3_paths['labels']}forest_labels.tif",
                        '--output', f"s3://{self.bucket}/{self.s3_paths['training_data']}training.parquet"
                    ]
                }
            },
            
            'entrenar_modelos': {
                'Name': 'Step 6: Entrenar Modelos',
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Jar': 'command-runner.jar',
                    'Args': [
                        'spark-submit',
                        '--deploy-mode', 'cluster',
                        '--executor-memory', '32g',
                        '--executor-cores', '8',
                        f'{s3_scripts}06_entrenar_modelos_spark.py',
                        '--inputs', f"s3://{self.bucket}/{self.s3_paths['training_data']}training.parquet",
                        '--out_model_dir', f"s3://{self.bucket}/{self.s3_paths['models']}best_model",
                        '--out_metrics_dir', f"s3://{self.bucket}/{self.s3_paths['evaluation']}",
                        '--test_frac', str(self.pipeline_config['training']['test_fraction']),
                        '--seed', str(self.pipeline_config['training']['random_seed']),
                        '--metric', self.pipeline_config['training']['optimization']['metric']
                    ]
                }
            },
            
            'evaluar_modelos': {
                'Name': 'Step 7: Evaluar Modelos',
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Jar': 'command-runner.jar',
                    'Args': [
                        'spark-submit',
                        '--deploy-mode', 'cluster',
                        '--executor-memory', '16g',
                        f'{s3_scripts}07_evaluar_modelos.py',
                        '--model', f"s3://{self.bucket}/{self.s3_paths['models']}best_model",
                        '--test_data', f"s3://{self.bucket}/{self.s3_paths['training_data']}training.parquet",
                        '--output', f"s3://{self.bucket}/{self.s3_paths['evaluation']}",
                        '--test_fraction', str(self.pipeline_config['training']['test_fraction']),
                        '--seed', str(self.pipeline_config['training']['random_seed'])
                    ]
                }
            }
        }
        
        return steps.get(step_name)
    
    def submit_step(self, cluster_id: str, step_name: str, wait: bool = False) -> str:
        """Envía un step al cluster"""
        step_config = self.get_step_config(step_name)
        
        if not step_config:
            raise ValueError(f"Step desconocido: {step_name}")
        
        print(f"\n{'='*70}")
        print(f"ENVIANDO STEP: {step_config['Name']}")
        print(f"{'='*70}")
        
        response = self.emr_client.add_job_flow_steps(
            JobFlowId=cluster_id,
            Steps=[step_config]
        )
        
        step_id = response['StepIds'][0]
        print(f"  ✓ Step enviado: {step_id}")
        
        if wait:
            self.wait_for_step_completion(cluster_id, step_id)
        
        return step_id
    
    def wait_for_step_completion(self, cluster_id: str, step_id: str, timeout: int = 7200):
        """Espera a que un step termine"""
        print(f"  ⏳ Esperando completación del step...")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = self.emr_client.describe_step(
                ClusterId=cluster_id,
                StepId=step_id
            )
            
            state = response['Step']['Status']['State']
            print(f"    Estado: {state}", end='\r')
            
            if state == 'COMPLETED':
                print(f"\n  ✓ Step completado exitosamente!")
                return True
            elif state in ['FAILED', 'CANCELLED']:
                failure_details = response['Step']['Status'].get('FailureDetails', {})
                raise Exception(f"Step falló: {state} - {failure_details}")
            
            time.sleep(30)
        
        raise TimeoutError(f"Timeout esperando step después de {timeout}s")
    
    def submit_pipeline(self, cluster_id: str, pipeline_type: str = 'full', wait: bool = False):
        """Envía pipeline completo"""
        pipelines = {
            'full': [
                'procesar_sentinel',
                'generar_mascaras',
                'tabular_features',
                'rasterizar_labels',
                'unir_features_labels',
                'entrenar_modelos',
                'evaluar_modelos'
            ],
            'training_only': [
                'rasterizar_labels',
                'unir_features_labels',
                'entrenar_modelos',
                'evaluar_modelos'
            ],
            'processing_only': [
                'procesar_sentinel',
                'generar_mascaras',
                'tabular_features'
            ]
        }
        
        steps = pipelines.get(pipeline_type)
        if not steps:
            raise ValueError(f"Pipeline desconocido: {pipeline_type}")
        
        print(f"\n{'='*70}")
        print(f"EJECUTANDO PIPELINE: {pipeline_type.upper()}")
        print(f"{'='*70}")
        print(f"  Steps: {len(steps)}")
        for i, step in enumerate(steps, 1):
            print(f"    {i}. {step}")
        
        step_ids = []
        for step_name in steps:
            step_id = self.submit_step(cluster_id, step_name, wait=wait)
            step_ids.append(step_id)
        
        return step_ids


def parse_args():
    p = argparse.ArgumentParser(description="Envía steps a EMR")
    p.add_argument("--cluster-id", help="ID del cluster EMR existente")
    p.add_argument("--create-cluster", action="store_true", help="Crear nuevo cluster")
    p.add_argument("--step", help="Nombre del step individual a ejecutar")
    p.add_argument("--pipeline", choices=['full', 'training_only', 'processing_only'],
                   help="Pipeline completo a ejecutar")
    p.add_argument("--wait", action="store_true", help="Esperar a que los steps terminen")
    p.add_argument("--auto-terminate", action="store_true", help="Terminar cluster al finalizar")
    p.add_argument("--config", default="config/aws_config.yaml", help="Path a config AWS")
    p.add_argument("--pipeline-config", default="config/pipeline_config.yaml", help="Path a config pipeline")
    return p.parse_args()


def main():
    args = parse_args()
    
    submitter = EMRJobSubmitter(args.config, args.pipeline_config)
    
    # Crear cluster si se solicita
    if args.create_cluster:
        cluster_id = submitter.create_cluster(auto_terminate=args.auto_terminate)
    elif args.cluster_id:
        cluster_id = args.cluster_id
    else:
        raise ValueError("Debe especificar --cluster-id o --create-cluster")
    
    # Ejecutar step o pipeline
    if args.step:
        submitter.submit_step(cluster_id, args.step, wait=args.wait)
    elif args.pipeline:
        submitter.submit_pipeline(cluster_id, args.pipeline, wait=args.wait)
    else:
        raise ValueError("Debe especificar --step o --pipeline")
    
    print(f"\n{'='*70}")
    print(f"CLUSTER ID: {cluster_id}")
    print(f"  Monitorear en: https://console.aws.amazon.com/emr/")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
