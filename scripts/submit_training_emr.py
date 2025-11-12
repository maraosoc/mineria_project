#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
submit_training_emr.py
----------------------
Lanza job de entrenamiento de modelos en cluster EMR
Ejecuta script 06 (entrenamiento) y opcionalmente script 07 (evaluación)

Uso:
  python submit_training_emr.py --cluster-id j-XXXXXXXXX
  python submit_training_emr.py --cluster-id j-XXXXXXXXX --evaluate
  python submit_training_emr.py --cluster-id j-XXXXXXXXX --input s3://mineria-project/data/custom/data.parquet
"""

import argparse
import boto3
import json
import time
from datetime import datetime

def get_cluster_status(emr_client, cluster_id):
    """Obtiene el estado actual del cluster"""
    response = emr_client.describe_cluster(ClusterId=cluster_id)
    return response['Cluster']['Status']['State']

def wait_for_step_completion(emr_client, cluster_id, step_id, step_name):
    """Espera a que un step complete"""
    print(f"\n⏳ Esperando completación de '{step_name}'...")
    
    while True:
        response = emr_client.describe_step(ClusterId=cluster_id, StepId=step_id)
        status = response['Step']['Status']['State']
        
        if status == 'COMPLETED':
            print(f"✅ '{step_name}' completado exitosamente")
            return True
        elif status in ['FAILED', 'CANCELLED']:
            failure_reason = response['Step']['Status'].get('FailureDetails', {}).get('Reason', 'Unknown')
            print(f"❌ '{step_name}' falló: {failure_reason}")
            return False
        elif status in ['PENDING', 'RUNNING']:
            print(f"   Estado: {status}...", end='\r')
            time.sleep(30)
        else:
            print(f"⚠️  Estado desconocido: {status}")
            time.sleep(30)

def submit_training_step(emr_client, cluster_id, args):
    """Envía step de entrenamiento al cluster EMR"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_model_dir = f"s3://mineria-project/models/model_{timestamp}/"
    
    spark_args = [
        "spark-submit",
        "--deploy-mode", "cluster",
        "--master", "yarn",
        "--conf", "spark.executor.memory=8g",
        "--conf", "spark.executor.cores=4",
        "--conf", "spark.executor.instances=4",
        "--conf", "spark.driver.memory=4g",
        "--conf", "spark.dynamicAllocation.enabled=true",
        "--conf", "spark.shuffle.service.enabled=true",
        "s3://mineria-project/source/scripts/06_entrenar_modelos_spark.py",
        "--inputs", args.input_data,
        "--out_model_dir", output_model_dir,
        "--label_col", "label",
        "--test_frac", str(args.test_frac),
        "--seed", str(args.seed),
        "--metric", args.metric
    ]
    
    step_config = {
        'Name': f'Training_Model_{timestamp}',
        'ActionOnFailure': 'CONTINUE',
        'HadoopJarStep': {
            'Jar': 'command-runner.jar',
            'Args': spark_args
        }
    }
    
    print(f"\n{'='*70}")
    print("LANZANDO ENTRENAMIENTO EN EMR")
    print(f"{'='*70}")
    print(f"Cluster ID: {cluster_id}")
    print(f"Input: {args.input_data}")
    print(f"Output: {output_model_dir}")
    print(f"Test fraction: {args.test_frac}")
    print(f"Metric: {args.metric}")
    
    response = emr_client.add_job_flow_steps(
        JobFlowId=cluster_id,
        Steps=[step_config]
    )
    
    step_id = response['StepIds'][0]
    print(f"\n✓ Step enviado con ID: {step_id}")
    
    return step_id, output_model_dir

def submit_evaluation_step(emr_client, cluster_id, model_path, test_data_path, args):
    """Envía step de evaluación al cluster EMR"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_results_dir = f"s3://mineria-project/results/eval_{timestamp}/"
    
    spark_args = [
        "spark-submit",
        "--deploy-mode", "cluster",
        "--master", "yarn",
        "--conf", "spark.executor.memory=8g",
        "--conf", "spark.executor.cores=4",
        "--conf", "spark.executor.instances=2",
        "--conf", "spark.driver.memory=4g",
        "s3://mineria-project/source/scripts/07_evaluar_modelos.py",
        "--model", model_path + "pipeline_best",
        "--test_data", test_data_path,
        "--output", output_results_dir,
        "--test_fraction", str(args.test_frac),
        "--seed", str(args.seed)
    ]
    
    step_config = {
        'Name': f'Evaluation_Model_{timestamp}',
        'ActionOnFailure': 'CONTINUE',
        'HadoopJarStep': {
            'Jar': 'command-runner.jar',
            'Args': spark_args
        }
    }
    
    print(f"\n{'='*70}")
    print("LANZANDO EVALUACIÓN EN EMR")
    print(f"{'='*70}")
    print(f"Modelo: {model_path}")
    print(f"Output: {output_results_dir}")
    
    response = emr_client.add_job_flow_steps(
        JobFlowId=cluster_id,
        Steps=[step_config]
    )
    
    step_id = response['StepIds'][0]
    print(f"\n✓ Step enviado con ID: {step_id}")
    
    return step_id, output_results_dir

def main():
    parser = argparse.ArgumentParser(
        description="Lanza job de entrenamiento ML en cluster EMR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Entrenar con datos por defecto
  python submit_training_emr.py --cluster-id j-XXXXXXXXX
  
  # Entrenar y evaluar
  python submit_training_emr.py --cluster-id j-XXXXXXXXX --evaluate
  
  # Entrenar con datos custom
  python submit_training_emr.py --cluster-id j-XXXXXXXXX \\
    --input s3://mineria-project/data/custom/data.parquet
  
  # Configurar hiperparámetros
  python submit_training_emr.py --cluster-id j-XXXXXXXXX \\
    --test-frac 0.2 --metric areaUnderROC
        """
    )
    
    parser.add_argument("--cluster-id", required=True,
                       help="ID del cluster EMR")
    parser.add_argument("--input-data", 
                       default="s3://mineria-project/data/all/training_data_all_zones.parquet",
                       help="Path S3 a datos de entrenamiento")
    parser.add_argument("--test-frac", type=float, default=0.15,
                       help="Fracción para test (default: 0.15)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed (default: 42)")
    parser.add_argument("--metric", default="areaUnderPR",
                       choices=["areaUnderPR", "areaUnderROC"],
                       help="Métrica de optimización (default: areaUnderPR)")
    parser.add_argument("--evaluate", action="store_true",
                       help="Ejecutar evaluación después del entrenamiento")
    parser.add_argument("--wait", action="store_true",
                       help="Esperar a que complete el entrenamiento")
    parser.add_argument("--region", default="us-east-1",
                       help="AWS region (default: us-east-1)")
    
    args = parser.parse_args()
    
    # Cliente EMR
    emr_client = boto3.client('emr', region_name=args.region)
    
    # Verificar estado del cluster
    try:
        cluster_status = get_cluster_status(emr_client, args.cluster_id)
        print(f"\nCluster {args.cluster_id} - Estado: {cluster_status}")
        
        if cluster_status not in ['WAITING', 'RUNNING']:
            print(f"❌ Error: Cluster no está disponible (estado: {cluster_status})")
            return 1
    
    except Exception as e:
        print(f"❌ Error verificando cluster: {e}")
        return 1
    
    # Enviar step de entrenamiento
    try:
        training_step_id, model_path = submit_training_step(emr_client, args.cluster_id, args)
        
        # Esperar si se solicitó
        if args.wait or args.evaluate:
            training_success = wait_for_step_completion(
                emr_client, 
                args.cluster_id, 
                training_step_id,
                "Training"
            )
            
            if not training_success:
                print("\n❌ Entrenamiento falló. No se ejecutará la evaluación.")
                return 1
            
            print(f"\n✅ Modelo guardado en: {model_path}")
            
            # Ejecutar evaluación si se solicitó
            if args.evaluate:
                eval_step_id, results_path = submit_evaluation_step(
                    emr_client,
                    args.cluster_id,
                    model_path,
                    args.input_data,
                    args
                )
                
                eval_success = wait_for_step_completion(
                    emr_client,
                    args.cluster_id,
                    eval_step_id,
                    "Evaluation"
                )
                
                if eval_success:
                    print(f"\n✅ Resultados guardados en: {results_path}")
                    print(f"\nPara ver el reporte:")
                    print(f"  aws s3 cp {results_path}EVALUATION_REPORT.md ./")
                else:
                    return 1
        
        else:
            print(f"\n✓ Steps enviados exitosamente")
            print(f"\nMonitorear progreso:")
            print(f"  aws emr describe-step --cluster-id {args.cluster_id} --step-id {training_step_id}")
            print(f"\nVer logs:")
            print(f"  aws s3 ls s3://mineria-project/logs/emr/{args.cluster_id}/")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    
    print(f"\n{'='*70}")
    print("✅ PROCESO COMPLETADO")
    print(f"{'='*70}\n")
    
    return 0

if __name__ == "__main__":
    exit(main())
