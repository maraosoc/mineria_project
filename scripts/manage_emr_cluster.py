#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manage_emr_cluster.py
---------------------
Script helper para gestionar el cluster EMR
Permite crear, listar, terminar y monitorear clusters

Uso:
  python manage_emr_cluster.py list
  python manage_emr_cluster.py status --cluster-id j-XXXXXXXXX
  python manage_emr_cluster.py terminate --cluster-id j-XXXXXXXXX
  python manage_emr_cluster.py logs --cluster-id j-XXXXXXXXX --step-id s-XXXXXXXXX
"""

import argparse
import boto3
import json
from datetime import datetime
from typing import List, Dict

def list_clusters(emr_client, active_only=True):
    """Lista todos los clusters EMR"""
    print(f"\n{'='*80}")
    print(f"{'CLUSTERS EMR':^80}")
    print(f"{'='*80}\n")
    
    if active_only:
        response = emr_client.list_clusters(
            ClusterStates=['STARTING', 'BOOTSTRAPPING', 'RUNNING', 'WAITING']
        )
    else:
        response = emr_client.list_clusters()
    
    clusters = response.get('Clusters', [])
    
    if not clusters:
        print("No hay clusters activos.\n")
        return
    
    # Header
    print(f"{'ID':<16} {'Nombre':<30} {'Estado':<15} {'Creado':<20}")
    print(f"{'-'*16} {'-'*30} {'-'*15} {'-'*20}")
    
    # Clusters
    for cluster in clusters:
        cluster_id = cluster['Id']
        name = cluster['Name'][:28]
        status = cluster['Status']['State']
        created = cluster['Status']['Timeline']['CreationDateTime']
        created_str = created.strftime("%Y-%m-%d %H:%M:%S")
        
        # Color por estado
        if status == 'WAITING':
            status_display = f"✓ {status}"
        elif status in ['STARTING', 'BOOTSTRAPPING', 'RUNNING']:
            status_display = f"⏳ {status}"
        else:
            status_display = f"  {status}"
        
        print(f"{cluster_id:<16} {name:<30} {status_display:<15} {created_str:<20}")
    
    print(f"\nTotal: {len(clusters)} cluster(s)\n")

def get_cluster_details(emr_client, cluster_id):
    """Muestra detalles completos de un cluster"""
    print(f"\n{'='*80}")
    print(f"{'DETALLES DEL CLUSTER':^80}")
    print(f"{'='*80}\n")
    
    try:
        response = emr_client.describe_cluster(ClusterId=cluster_id)
        cluster = response['Cluster']
        
        print(f"ID:               {cluster['Id']}")
        print(f"Nombre:           {cluster['Name']}")
        print(f"Estado:           {cluster['Status']['State']}")
        print(f"Release:          {cluster['ReleaseLabel']}")
        print(f"Aplicaciones:     {', '.join([app['Name'] for app in cluster['Applications']])}")
        
        if 'MasterPublicDnsName' in cluster:
            print(f"Master DNS:       {cluster['MasterPublicDnsName']}")
        
        # Timeline
        timeline = cluster['Status']['Timeline']
        print(f"\nTimeline:")
        print(f"  Creado:         {timeline['CreationDateTime']}")
        if 'ReadyDateTime' in timeline:
            print(f"  Listo:          {timeline['ReadyDateTime']}")
        if 'EndDateTime' in timeline:
            print(f"  Terminado:      {timeline['EndDateTime']}")
        
        # Instancias
        print(f"\nInstancias:")
        instance_groups = emr_client.list_instance_groups(ClusterId=cluster_id)
        for group in instance_groups['InstanceGroups']:
            print(f"  {group['InstanceGroupType']:10} {group['InstanceType']:15} x{group['RequestedInstanceCount']}")
        
        # Configuración S3
        if 'LogUri' in cluster:
            print(f"\nLogs S3:          {cluster['LogUri']}")
        
        # Steps recientes
        print(f"\nSteps recientes:")
        steps_response = emr_client.list_steps(ClusterId=cluster_id)
        steps = steps_response.get('Steps', [])[:5]
        
        if steps:
            print(f"  {'ID':<18} {'Nombre':<35} {'Estado':<12}")
            print(f"  {'-'*18} {'-'*35} {'-'*12}")
            for step in steps:
                step_id = step['Id']
                name = step['Name'][:33]
                status = step['Status']['State']
                
                if status == 'COMPLETED':
                    status_display = f"✓ {status}"
                elif status in ['PENDING', 'RUNNING']:
                    status_display = f"⏳ {status}"
                elif status == 'FAILED':
                    status_display = f"✗ {status}"
                else:
                    status_display = f"  {status}"
                
                print(f"  {step_id:<18} {name:<35} {status_display:<12}")
        else:
            print("  No hay steps")
        
        print()
    
    except Exception as e:
        print(f"❌ Error: {e}\n")

def terminate_cluster(emr_client, cluster_id, force=False):
    """Termina un cluster EMR"""
    if not force:
        confirm = input(f"¿Terminar cluster {cluster_id}? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Operación cancelada.")
            return
    
    try:
        emr_client.terminate_job_flows(JobFlowIds=[cluster_id])
        print(f"✓ Cluster {cluster_id} terminando...")
    except Exception as e:
        print(f"❌ Error: {e}")

def get_step_logs(emr_client, cluster_id, step_id):
    """Muestra información de logs de un step"""
    print(f"\n{'='*80}")
    print(f"{'LOGS DEL STEP':^80}")
    print(f"{'='*80}\n")
    
    try:
        # Obtener detalles del step
        response = emr_client.describe_step(ClusterId=cluster_id, StepId=step_id)
        step = response['Step']
        
        print(f"Step ID:    {step['Id']}")
        print(f"Nombre:     {step['Name']}")
        print(f"Estado:     {step['Status']['State']}")
        
        # Obtener logs URI
        cluster_response = emr_client.describe_cluster(ClusterId=cluster_id)
        log_uri = cluster_response['Cluster'].get('LogUri', '')
        
        if log_uri:
            step_log_path = f"{log_uri}{cluster_id}/steps/{step_id}/"
            print(f"\nLogs en S3:")
            print(f"  {step_log_path}")
            print(f"\nDescargar logs:")
            print(f"  aws s3 cp {step_log_path} ./logs/ --recursive")
            print(f"\nVer stderr:")
            print(f"  aws s3 cp {step_log_path}stderr.gz - | gunzip | tail -100")
            print(f"\nVer stdout:")
            print(f"  aws s3 cp {step_log_path}stdout.gz - | gunzip | tail -100")
        else:
            print("\n⚠️  No hay logs URI configurado")
        
        print()
    
    except Exception as e:
        print(f"❌ Error: {e}\n")

def list_steps(emr_client, cluster_id):
    """Lista todos los steps de un cluster"""
    print(f"\n{'='*80}")
    print(f"{'STEPS DEL CLUSTER':^80}")
    print(f"{'='*80}\n")
    
    try:
        response = emr_client.list_steps(ClusterId=cluster_id)
        steps = response.get('Steps', [])
        
        if not steps:
            print("No hay steps en este cluster.\n")
            return
        
        print(f"{'ID':<18} {'Nombre':<40} {'Estado':<15} {'Creado':<20}")
        print(f"{'-'*18} {'-'*40} {'-'*15} {'-'*20}")
        
        for step in steps:
            step_id = step['Id']
            name = step['Name'][:38]
            status = step['Status']['State']
            created = step['Status']['Timeline']['CreationDateTime']
            created_str = created.strftime("%Y-%m-%d %H:%M:%S")
            
            if status == 'COMPLETED':
                status_display = f"✓ {status}"
            elif status in ['PENDING', 'RUNNING']:
                status_display = f"⏳ {status}"
            elif status == 'FAILED':
                status_display = f"✗ {status}"
            else:
                status_display = f"  {status}"
            
            print(f"{step_id:<18} {name:<40} {status_display:<15} {created_str:<20}")
        
        print(f"\nTotal: {len(steps)} step(s)\n")
    
    except Exception as e:
        print(f"❌ Error: {e}\n")

def main():
    parser = argparse.ArgumentParser(
        description="Gestión de clusters EMR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Listar clusters activos
  python manage_emr_cluster.py list
  
  # Ver detalles de un cluster
  python manage_emr_cluster.py status --cluster-id j-XXXXXXXXX
  
  # Listar steps
  python manage_emr_cluster.py steps --cluster-id j-XXXXXXXXX
  
  # Ver logs de un step
  python manage_emr_cluster.py logs --cluster-id j-XXXXXXXXX --step-id s-XXXXXXXXX
  
  # Terminar cluster
  python manage_emr_cluster.py terminate --cluster-id j-XXXXXXXXX
        """
    )
    
    parser.add_argument("action", 
                       choices=["list", "status", "steps", "logs", "terminate"],
                       help="Acción a realizar")
    parser.add_argument("--cluster-id",
                       help="ID del cluster EMR")
    parser.add_argument("--step-id",
                       help="ID del step (para ver logs)")
    parser.add_argument("--all", action="store_true",
                       help="Incluir clusters terminados (para list)")
    parser.add_argument("--force", action="store_true",
                       help="No pedir confirmación (para terminate)")
    parser.add_argument("--region", default="us-east-1",
                       help="AWS region (default: us-east-1)")
    
    args = parser.parse_args()
    
    # Cliente EMR
    emr_client = boto3.client('emr', region_name=args.region)
    
    # Ejecutar acción
    try:
        if args.action == "list":
            list_clusters(emr_client, active_only=not args.all)
        
        elif args.action == "status":
            if not args.cluster_id:
                print("❌ Error: --cluster-id es requerido para status")
                return 1
            get_cluster_details(emr_client, args.cluster_id)
        
        elif args.action == "steps":
            if not args.cluster_id:
                print("❌ Error: --cluster-id es requerido para steps")
                return 1
            list_steps(emr_client, args.cluster_id)
        
        elif args.action == "logs":
            if not args.cluster_id or not args.step_id:
                print("❌ Error: --cluster-id y --step-id son requeridos para logs")
                return 1
            get_step_logs(emr_client, args.cluster_id, args.step_id)
        
        elif args.action == "terminate":
            if not args.cluster_id:
                print("❌ Error: --cluster-id es requerido para terminate")
                return 1
            terminate_cluster(emr_client, args.cluster_id, force=args.force)
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        return 1

if __name__ == "__main__":
    exit(main())
