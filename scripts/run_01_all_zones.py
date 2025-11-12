#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_01_all_zones.py
-------------------
Ejecuta el script 01_procesar_sentinel.py para todas las zonas encontradas en S3.
"""

import argparse
import subprocess
import sys
from typing import List
import boto3
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Procesa todas las zonas de Sentinel-2")
    p.add_argument("--input_base", default="s3://mineria-project/raw/raw_copernicus/",
                   help="Path base S3 donde están las carpetas de zonas")
    p.add_argument("--output", default="s3://mineria-project/staging/01_rasters_procesados/",
                   help="Path base S3 para salida")
    p.add_argument("--resolution", type=int, default=20, help="Resolución objetivo (m)")
    p.add_argument("--bands", default="B02,B03,B04,B05,B06,B07,B8A,B11,B12",
                   help="Bandas a procesar (solo 20m)")
    p.add_argument("--indices", default="NDVI,NDWI", help="Índices a calcular")
    p.add_argument("--temp_dir", default="C:/temp/sentinel_processing",
                   help="Directorio temporal")
    p.add_argument("--zones", nargs="+", help="Procesar solo estas zonas específicas")
    p.add_argument("--skip_zones", nargs="+", default=[],
                   help="Saltar estas zonas")
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
    
    # Listar "carpetas" (prefijos comunes)
    paginator = s3_client.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(
        Bucket=bucket,
        Prefix=prefix,
        Delimiter='/'
    )
    
    zones = []
    for page in page_iterator:
        if 'CommonPrefixes' in page:
            for prefix_obj in page['CommonPrefixes']:
                zone_prefix = prefix_obj['Prefix']
                # Extraer nombre de zona (último componente antes de /)
                zone_name = zone_prefix.rstrip('/').split('/')[-1]
                zones.append(zone_name)
    
    return sorted(zones)


def run_processing(zone: str, args) -> bool:
    """Ejecuta el procesamiento para una zona específica"""
    input_path = f"{args.input_base.rstrip('/')}/{zone}/"
    
    cmd = [
        sys.executable,  # Python executable actual
        "scripts/01_procesar_sentinel.py",
        "--input", input_path,
        "--output", args.output,
        "--zone_name", zone,
        "--resolution", str(args.resolution),
        "--bands", args.bands,
        "--indices", args.indices,
        "--temp_dir", args.temp_dir
    ]
    
    print(f"\n{'='*70}")
    print(f"EJECUTANDO: {zone}")
    print(f"{'='*70}")
    print(f"Comando: {' '.join(cmd)}\n")
    
    if args.dry_run:
        return True
    
    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Error procesando {zone}: {e}")
        return False


def main():
    args = parse_args()
    
    print(f"\n{'='*70}")
    print("PROCESAMIENTO BATCH - TODAS LAS ZONAS")
    print(f"{'='*70}")
    print(f"Input base: {args.input_base}")
    print(f"Output: {args.output}")
    print(f"Resolution: {args.resolution}m")
    print(f"Bands: {args.bands}")
    print(f"Indices: {args.indices}")
    
    # Listar zonas disponibles
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
        print("\n[DRY RUN] No se procesará ninguna zona")
        return
    
    # Confirmar antes de continuar
    print(f"\n{'='*70}")
    response = input("¿Continuar con el procesamiento? (y/N): ")
    if response.lower() != 'y':
        print("Procesamiento cancelado")
        return
    
    # Procesar cada zona
    print(f"\n{'='*70}")
    print("INICIANDO PROCESAMIENTO")
    print(f"{'='*70}")
    
    results = {
        'success': [],
        'failed': []
    }
    
    for i, zone in enumerate(zones_to_process, 1):
        print(f"\n[{i}/{len(zones_to_process)}] Procesando: {zone}")
        
        success = run_processing(zone, args)
        
        if success:
            results['success'].append(zone)
            print(f"✓ {zone} completado")
        else:
            results['failed'].append(zone)
            print(f"✗ {zone} falló")
    
    # Resumen final
    print(f"\n{'='*70}")
    print("RESUMEN FINAL")
    print(f"{'='*70}")
    print(f"Total zonas: {len(zones_to_process)}")
    print(f"✓ Exitosas: {len(results['success'])}")
    print(f"✗ Fallidas: {len(results['failed'])}")
    
    if results['failed']:
        print("\nZonas fallidas:")
        for zone in results['failed']:
            print(f"  - {zone}")
    
    print(f"\nOutput: {args.output}")
    print(f"{'='*70}\n")
    
    # Exit code
    sys.exit(0 if not results['failed'] else 1)


if __name__ == "__main__":
    main()
