#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_01_all_zones_parallel.py
-----------------------------
Ejecuta el script 01_procesar_sentinel.py para todas las zonas en PARALELO.
Usa multiprocessing para procesar múltiples zonas simultáneamente.
"""

import argparse
import subprocess
import sys
from typing import List, Dict
import boto3
from pathlib import Path
from multiprocessing import Pool, cpu_count
from datetime import datetime
import time


def parse_args():
    p = argparse.ArgumentParser(description="Procesa todas las zonas de Sentinel-2 en paralelo")
    p.add_argument("--input_base", default="s3://mineria-project/raw/raw_copernicus/",
                   help="Path base S3 donde están las carpetas de zonas")
    p.add_argument("--output", default="s3://mineria-project/staging/01_rasters_procesados/",
                   help="Path base S3 para salida")
    p.add_argument("--resolution", type=int, default=20, help="Resolución objetivo (m)")
    p.add_argument("--bands", default="B02,B03,B04,B05,B06,B07,B8A,B11,B12",
                   help="Bandas a procesar (solo 20m)")
    p.add_argument("--indices", default="NDVI,NDWI", help="Índices a calcular")
    p.add_argument("--temp_dir", default="/tmp/sentinel_processing",
                   help="Directorio temporal")
    p.add_argument("--zones", nargs="+", help="Procesar solo estas zonas específicas")
    p.add_argument("--skip_zones", nargs="+", default=[],
                   help="Saltar estas zonas")
    p.add_argument("--workers", type=int, default=3,
                   help="Número de procesos paralelos (default: 3 para t3.xlarge)")
    p.add_argument("--dry_run", action="store_true",
                   help="Mostrar zonas sin procesar")
    return p.parse_args()


def list_zones(s3_base_path: str) -> List[str]:
    """Lista todas las carpetas de zonas en S3"""
    s3_client = boto3.client('s3')
    
    # Parsear path S3
    parts = s3_base_path.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    
    if not prefix.endswith('/'):
        prefix += '/'
    
    print(f"Listando zonas en: s3://{bucket}/{prefix}")
    
    # Listar prefijos (carpetas)
    paginator = s3_client.get_paginator('list_objects_v2')
    zones = set()
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter='/'):
        if 'CommonPrefixes' in page:
            for obj in page['CommonPrefixes']:
                zone_path = obj['Prefix']
                # Extraer nombre de zona
                zone_name = zone_path.replace(prefix, '').rstrip('/')
                if zone_name:
                    zones.add(zone_name)
    
    return sorted(list(zones))


def run_processing_worker(task_data: Dict) -> Dict:
    """
    Worker function para procesamiento paralelo.
    Retorna dict con resultado del procesamiento.
    """
    zone = task_data['zone']
    args = task_data['args']
    zone_num = task_data['zone_num']
    total_zones = task_data['total_zones']
    
    start_time = time.time()
    
    print(f"\n[Worker {zone_num}/{total_zones}] INICIANDO: {zone}")
    
    input_path = f"{args.input_base.rstrip('/')}/{zone}/"
    output_path = args.output
    
    cmd = [
        sys.executable,
        "01_procesar_sentinel.py",
        "--input", input_path,
        "--output", output_path,
        "--resolution", str(args.resolution),
        "--bands", args.bands,
        "--indices", args.indices,
        "--temp_dir", args.temp_dir,
        "--zone_name", zone
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200  # 2 horas timeout por zona
        )
        
        elapsed = time.time() - start_time
        elapsed_min = elapsed / 60
        
        if result.returncode == 0:
            print(f"✓ [{zone_num}/{total_zones}] {zone} completado en {elapsed_min:.1f} min")
            return {
                'zone': zone,
                'success': True,
                'elapsed': elapsed,
                'stdout': result.stdout[-500:] if result.stdout else '',
                'stderr': result.stderr[-500:] if result.stderr else ''
            }
        else:
            print(f"✗ [{zone_num}/{total_zones}] {zone} FALLÓ después de {elapsed_min:.1f} min")
            print(f"   Error: {result.stderr[-200:]}")
            return {
                'zone': zone,
                'success': False,
                'elapsed': elapsed,
                'stdout': result.stdout[-500:] if result.stdout else '',
                'stderr': result.stderr[-500:] if result.stderr else ''
            }
    
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        elapsed_min = elapsed / 60
        print(f"⏱ [{zone_num}/{total_zones}] {zone} TIMEOUT después de {elapsed_min:.1f} min")
        return {
            'zone': zone,
            'success': False,
            'elapsed': elapsed,
            'stdout': '',
            'stderr': 'TIMEOUT: Proceso excedió 2 horas'
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"✗ [{zone_num}/{total_zones}] {zone} ERROR: {str(e)}")
        return {
            'zone': zone,
            'success': False,
            'elapsed': elapsed,
            'stdout': '',
            'stderr': str(e)
        }


def main():
    args = parse_args()
    
    print(f"{'='*70}")
    print("PROCESAMIENTO BATCH PARALELO - TODAS LAS ZONAS")
    print(f"{'='*70}")
    print(f"Input base: {args.input_base}")
    print(f"Output: {args.output}")
    print(f"Resolution: {args.resolution}m")
    print(f"Bands: {args.bands}")
    print(f"Indices: {args.indices}")
    print(f"Workers: {args.workers} procesos paralelos")
    print(f"CPUs disponibles: {cpu_count()}")
    
    print(f"\n{'='*70}")
    print("LISTANDO ZONAS")
    print(f"{'='*70}")
    
    all_zones = list_zones(args.input_base)
    print(f"\nZonas encontradas: {len(all_zones)}")
    
    # Filtrar zonas
    if args.zones:
        zones_to_process = [z for z in all_zones if z in args.zones]
        print(f"Filtrado a zonas específicas: {len(zones_to_process)}")
    else:
        zones_to_process = all_zones
    
    # Eliminar zonas a saltar
    zones_to_process = [z for z in zones_to_process if z not in args.skip_zones]
    
    if args.skip_zones:
        print(f"Saltando {len(args.skip_zones)} zonas")
    
    print(f"\nZonas a procesar: {len(zones_to_process)}")
    for i, zone in enumerate(zones_to_process, 1):
        print(f"  {i:2d}. {zone}")
    
    if args.dry_run:
        print(f"\n[DRY RUN] No se procesará ninguna zona")
        print(f"Tiempo estimado con {args.workers} workers: {len(zones_to_process) * 15 / args.workers:.0f} minutos")
        return
    
    # Confirmar antes de continuar
    print(f"\n{'='*70}")
    est_time = len(zones_to_process) * 15 / args.workers  # ~15 min por zona
    print(f"Tiempo estimado: ~{est_time:.0f} minutos ({est_time/60:.1f} horas)")
    print(f"Procesando {args.workers} zonas simultáneamente")
    response = input("¿Continuar con el procesamiento? (y/N): ")
    if response.lower() != 'y':
        print("Procesamiento cancelado")
        return
    
    # Preparar tareas
    print(f"\n{'='*70}")
    print("INICIANDO PROCESAMIENTO PARALELO")
    print(f"{'='*70}")
    
    start_time = datetime.now()
    
    tasks = [
        {
            'zone': zone,
            'args': args,
            'zone_num': i,
            'total_zones': len(zones_to_process)
        }
        for i, zone in enumerate(zones_to_process, 1)
    ]
    
    # Ejecutar en paralelo
    with Pool(processes=args.workers) as pool:
        results_list = pool.map(run_processing_worker, tasks)
    
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    
    # Analizar resultados
    success_results = [r for r in results_list if r['success']]
    failed_results = [r for r in results_list if not r['success']]
    
    # Resumen final
    print(f"\n{'='*70}")
    print("RESUMEN FINAL")
    print(f"{'='*70}")
    print(f"Inicio: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Fin: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tiempo total: {elapsed/60:.1f} minutos ({elapsed/3600:.2f} horas)")
    print(f"\nTotal zonas: {len(zones_to_process)}")
    print(f"✓ Exitosas: {len(success_results)}")
    print(f"✗ Fallidas: {len(failed_results)}")
    
    if success_results:
        avg_time = sum(r['elapsed'] for r in success_results) / len(success_results)
        print(f"\nTiempo promedio por zona: {avg_time/60:.1f} minutos")
        print("\nZonas exitosas:")
        for r in success_results:
            print(f"  ✓ {r['zone']} ({r['elapsed']/60:.1f} min)")
    
    if failed_results:
        print("\nZonas fallidas:")
        for r in failed_results:
            print(f"  ✗ {r['zone']} ({r['elapsed']/60:.1f} min)")
            if r['stderr']:
                print(f"     Error: {r['stderr'][:100]}")
    
    print(f"\nOutput: {args.output}")
    print(f"{'='*70}\n")
    
    # Exit code
    sys.exit(0 if not failed_results else 1)


if __name__ == "__main__":
    main()
