#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_all_zones_pipeline.py
------------------------------
Pipeline automatizado para procesar todas las zonas disponibles.

Ejecuta los scripts 03-05 para todas las zonas y genera:
1. Datos por zona en s3://mineria-project/data/fincas/ZONA/
2. Dataset consolidado en s3://mineria-project/data/all/
3. Informe de balance en s3://mineria-project/logs/

Autor: Proyecto Manu - Minería de Datos
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import subprocess
import boto3
import polars as pl
import numpy as np


class S3Handler:
    """Maneja operaciones con S3"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
    
    def list_zones(self, bucket: str, prefix: str) -> List[str]:
        """Lista todas las zonas (directorios) en un prefijo S3"""
        response = self.s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            Delimiter='/'
        )
        
        zones = []
        if 'CommonPrefixes' in response:
            for obj in response['CommonPrefixes']:
                zone_name = obj['Prefix'].replace(prefix, '').strip('/')
                zones.append(zone_name)
        
        return sorted(zones)
    
    def zone_has_rasters(self, bucket: str, zone: str) -> bool:
        """Verifica si una zona tiene rasters procesados"""
        prefix = f"staging/01_rasters_procesados_clipped/{zone}/"
        response = self.s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            MaxKeys=1
        )
        return 'Contents' in response
    
    def zone_has_shapes(self, bucket: str, zone: str) -> bool:
        """Verifica si una zona tiene shapefiles de bosque y perímetro"""
        bosque_prefix = f"raw/shapes/{zone}/Bosque.shp"
        perimetro_prefix = f"raw/shapes/{zone}/Perímetro.shp"
        
        try:
            self.s3_client.head_object(Bucket=bucket, Key=bosque_prefix)
            self.s3_client.head_object(Bucket=bucket, Key=perimetro_prefix)
            return True
        except:
            return False


def run_script_03(zone: str, bucket: str) -> Dict:
    """Ejecuta script 03 (tabular features) para una zona"""
    print(f"\n{'='*70}")
    print(f"[ZONA {zone}] PASO 1/3: Tabulando features...")
    print(f"{'='*70}")
    
    input_rasters = f"s3://{bucket}/staging/01_rasters_procesados_clipped/{zone}/"
    output_composite = f"s3://{bucket}/data/fincas/{zone}/composite_annual.parquet"
    output_observations = f"s3://{bucket}/data/fincas/{zone}/observations_all.parquet"
    
    cmd = [
        "python", "scripts/03_tabular_features.py",
        "--rasters", input_rasters,
        "--output", output_composite,
        "--save_observations",
        "--observations", output_observations
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        print(result.stdout)
        return {"status": "success", "zone": zone, "step": "03_features"}
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Error en script 03 para {zone}:")
        print(e.stderr)
        return {"status": "error", "zone": zone, "step": "03_features", "error": str(e)}


def run_script_04(zone: str, bucket: str, erosion_pixels: int = 1) -> Dict:
    """Ejecuta script 04 (rasterizar labels) para una zona"""
    print(f"\n{'='*70}")
    print(f"[ZONA {zone}] PASO 2/3: Rasterizando labels...")
    print(f"{'='*70}")
    
    # Buscar raster de referencia
    s3 = boto3.client('s3')
    prefix = f"staging/01_rasters_procesados_clipped/{zone}/"
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    
    raster_ref = None
    if 'Contents' in response:
        for obj in response['Contents']:
            if obj['Key'].endswith('.tif'):
                raster_ref = f"s3://{bucket}/{obj['Key']}"
                break
    
    if not raster_ref:
        return {"status": "error", "zone": zone, "step": "04_labels", "error": "No raster reference found"}
    
    bosque_shp = f"s3://{bucket}/raw/shapes/{zone}/Bosque.shp"
    perimetro_shp = f"s3://{bucket}/raw/shapes/{zone}/Perímetro.shp"
    output_labels = f"s3://{bucket}/data/fincas/{zone}/forest_labels.tif"
    
    cmd = [
        "python", "scripts/04_rasterizar_labels.py",
        "--ref", raster_ref,
        "--bosque_shp", bosque_shp,
        "--perimetro_shp", perimetro_shp,
        "--output", output_labels,
        "--erosion_pixels", str(erosion_pixels)
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        print(result.stdout)
        return {"status": "success", "zone": zone, "step": "04_labels"}
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Error en script 04 para {zone}:")
        print(e.stderr)
        return {"status": "error", "zone": zone, "step": "04_labels", "error": str(e)}


def run_script_05(zone: str, bucket: str) -> Dict:
    """Ejecuta script 05 (unir features + labels) para una zona"""
    print(f"\n{'='*70}")
    print(f"[ZONA {zone}] PASO 3/3: Uniendo features + labels...")
    print(f"{'='*70}")
    
    features_parquet = f"s3://{bucket}/data/fincas/{zone}/composite_annual.parquet"
    labels_tif = f"s3://{bucket}/data/fincas/{zone}/forest_labels.tif"
    output_training = f"s3://{bucket}/data/fincas/{zone}/training_data.parquet"
    
    cmd = [
        "python", "scripts/05_unir_features_labels.py",
        "--features", features_parquet,
        "--labels", labels_tif,
        "--output", output_training
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        print(result.stdout)
        return {"status": "success", "zone": zone, "step": "05_union"}
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Error en script 05 para {zone}:")
        print(e.stderr)
        return {"status": "error", "zone": zone, "step": "05_union", "error": str(e)}


def process_zone(zone: str, bucket: str, erosion_pixels: int) -> Dict:
    """Procesa una zona completa (scripts 03, 04, 05)"""
    print(f"\n{'#'*70}")
    print(f"# PROCESANDO ZONA: {zone}")
    print(f"{'#'*70}")
    
    start_time = datetime.now()
    results = []
    
    # Paso 1: Script 03 (features)
    result_03 = run_script_03(zone, bucket)
    results.append(result_03)
    if result_03["status"] != "success":
        return {
            "zone": zone,
            "status": "error",
            "failed_step": "03_features",
            "duration": (datetime.now() - start_time).total_seconds(),
            "results": results
        }
    
    # Paso 2: Script 04 (labels)
    result_04 = run_script_04(zone, bucket, erosion_pixels)
    results.append(result_04)
    if result_04["status"] != "success":
        return {
            "zone": zone,
            "status": "error",
            "failed_step": "04_labels",
            "duration": (datetime.now() - start_time).total_seconds(),
            "results": results
        }
    
    # Paso 3: Script 05 (union)
    result_05 = run_script_05(zone, bucket)
    results.append(result_05)
    if result_05["status"] != "success":
        return {
            "zone": zone,
            "status": "error",
            "failed_step": "05_union",
            "duration": (datetime.now() - start_time).total_seconds(),
            "results": results
        }
    
    duration = (datetime.now() - start_time).total_seconds()
    
    print(f"\n[OK] Zona {zone} procesada exitosamente en {duration:.1f}s")
    
    return {
        "zone": zone,
        "status": "success",
        "duration": duration,
        "results": results
    }


def consolidate_datasets(bucket: str, zones: List[str]) -> Dict:
    """Consolida todos los parquets de zonas en un solo dataset"""
    print(f"\n{'='*70}")
    print(f"CONSOLIDANDO DATASETS DE TODAS LAS ZONAS")
    print(f"{'='*70}")
    
    all_dfs = []
    zone_stats = []
    
    for zone in zones:
        parquet_path = f"s3://{bucket}/data/fincas/{zone}/training_data.parquet"
        
        try:
            print(f"\n  Cargando {zone}...")
            df = pl.read_parquet(parquet_path)
            
            # Agregar columna de zona
            df = df.with_columns(pl.lit(zone).alias("zone"))
            
            # Estadísticas por zona
            n_total = len(df)
            n_bosque = df.filter(pl.col("label") == 1).shape[0]
            n_no_bosque = df.filter(pl.col("label") == 0).shape[0]
            
            zone_stats.append({
                "zone": zone,
                "total_samples": n_total,
                "bosque": n_bosque,
                "no_bosque": n_no_bosque,
                "ratio": n_no_bosque / n_bosque if n_bosque > 0 else 0,
                "pct_bosque": n_bosque / n_total * 100 if n_total > 0 else 0
            })
            
            all_dfs.append(df)
            print(f"    [OK] {n_total:,} samples ({n_bosque:,} bosque, {n_no_bosque:,} no-bosque)")
        
        except Exception as e:
            print(f"    [WARN] Error cargando {zone}: {e}")
            continue
    
    if not all_dfs:
        raise ValueError("No se pudieron cargar datasets de ninguna zona")
    
    # Concatenar todos los DataFrames
    print(f"\n  Concatenando {len(all_dfs)} datasets...")
    df_consolidated = pl.concat(all_dfs, how="vertical_relaxed")
    
    # Guardar consolidado
    output_path = f"s3://{bucket}/data/all/training_data_all_zones.parquet"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        local_file = os.path.join(tmpdir, "training_data_all_zones.parquet")
        df_consolidated.write_parquet(local_file)
        
        # Subir a S3
        s3 = boto3.client('s3')
        s3.upload_file(local_file, bucket, "data/all/training_data_all_zones.parquet")
    
    print(f"\n  [OK] Dataset consolidado guardado: {output_path}")
    
    # Estadísticas globales
    total_samples = len(df_consolidated)
    total_bosque = df_consolidated.filter(pl.col("label") == 1).shape[0]
    total_no_bosque = df_consolidated.filter(pl.col("label") == 0).shape[0]
    
    print(f"\nESTADISTICAS GLOBALES:")
    print(f"  Total samples: {total_samples:,}")
    print(f"  Bosque (1): {total_bosque:,} ({total_bosque/total_samples*100:.1f}%)")
    print(f"  No-Bosque (0): {total_no_bosque:,} ({total_no_bosque/total_samples*100:.1f}%)")
    print(f"  Ratio: {total_no_bosque/total_bosque:.2f}:1")
    print(f"  Zonas: {len(zones)}")
    
    return {
        "output_path": output_path,
        "total_samples": total_samples,
        "total_bosque": total_bosque,
        "total_no_bosque": total_no_bosque,
        "zones": len(zones),
        "zone_stats": zone_stats
    }


def generate_report(bucket: str, processing_results: List[Dict], consolidation_stats: Dict):
    """Genera informe JSON con estadísticas del procesamiento"""
    print(f"\n{'='*70}")
    print(f"GENERANDO INFORME DE PROCESAMIENTO")
    print(f"{'='*70}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Construir informe
    report = {
        "timestamp": timestamp,
        "execution_date": datetime.now().isoformat(),
        "summary": {
            "total_zones_processed": len(processing_results),
            "successful_zones": sum(1 for r in processing_results if r["status"] == "success"),
            "failed_zones": sum(1 for r in processing_results if r["status"] == "error"),
            "total_duration_seconds": sum(r.get("duration", 0) for r in processing_results)
        },
        "consolidation": consolidation_stats,
        "zone_details": processing_results
    }
    
    # Guardar JSON
    with tempfile.TemporaryDirectory() as tmpdir:
        # JSON report
        json_file = os.path.join(tmpdir, f"pipeline_report_{timestamp}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        
        # Subir a S3
        s3 = boto3.client('s3')
        s3.upload_file(json_file, bucket, f"logs/pipeline_report_{timestamp}.json")
        
        print(f"\n  [OK] Informe JSON: s3://{bucket}/logs/pipeline_report_{timestamp}.json")
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline automatizado para procesar todas las zonas (scripts 03-05)"
    )
    
    parser.add_argument("--bucket", default="mineria-project",
                       help="Bucket S3 (default: mineria-project)")
    parser.add_argument("--zones", nargs="*", default=None,
                       help="Zonas específicas a procesar (default: todas)")
    parser.add_argument("--erosion_pixels", type=int, default=1,
                       help="Píxeles de erosión para labels (default: 1)")
    parser.add_argument("--skip_consolidation", action="store_true",
                       help="Saltar consolidación de datasets")
    parser.add_argument("--dry-run", action="store_true",
                       help="Mostrar zonas a procesar sin ejecutar")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("PIPELINE AUTOMATIZADO - SCRIPTS 03, 04, 05")
    print("="*70)
    print(f"\nConfiguracion:")
    print(f"   Bucket: {args.bucket}")
    print(f"   Erosion: {args.erosion_pixels} pixeles")
    
    # Descubrir zonas disponibles
    s3_handler = S3Handler()
    
    if args.zones:
        zones = args.zones
        print(f"\nZonas especificadas manualmente: {len(zones)}")
    else:
        print(f"\nDescubriendo zonas disponibles...")
        all_zones = s3_handler.list_zones(args.bucket, "staging/01_rasters_procesados_clipped/")
        
        # Filtrar zonas que tienen rasters y shapes
        zones = []
        for zone in all_zones:
            has_rasters = s3_handler.zone_has_rasters(args.bucket, zone)
            has_shapes = s3_handler.zone_has_shapes(args.bucket, zone)
            
            if has_rasters and has_shapes:
                zones.append(zone)
                print(f"   [OK] {zone}")
            else:
                print(f"   [WARN] {zone} (falta rasters o shapes)")
    
    if not zones:
        print(f"\n[ERROR] No se encontraron zonas para procesar")
        sys.exit(1)
    
    print(f"\nTotal de zonas a procesar: {len(zones)}")
    
    if args.dry_run:
        print(f"\nDRY-RUN: No se ejecutaran los scripts")
        sys.exit(0)
    
    # Procesar zonas
    start_time = datetime.now()
    
    print(f"\nProcesamiento secuencial...")
    results = []
    for zone in zones:
        result = process_zone(zone, args.bucket, args.erosion_pixels)
        results.append(result)
    
    total_duration = (datetime.now() - start_time).total_seconds()
    
    # Resumen de resultados
    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "error"]
    
    print(f"\n{'='*70}")
    print(f"RESUMEN DE PROCESAMIENTO POR ZONA")
    print(f"{'='*70}")
    print(f"\n[OK] Exitosas: {len(successful)}/{len(zones)}")
    print(f"[ERROR] Fallidas: {len(failed)}/{len(zones)}")
    print(f"Duracion total: {total_duration:.1f}s")
    
    if failed:
        print(f"\nZonas con errores:")
        for r in failed:
            print(f"   - {r['zone']}: {r.get('failed_step', 'unknown')}")
    
    # Consolidar datasets
    consolidation_stats = None
    if not args.skip_consolidation and successful:
        try:
            successful_zones = [r["zone"] for r in successful]
            consolidation_stats = consolidate_datasets(args.bucket, successful_zones)
        except Exception as e:
            print(f"\n[ERROR] Error en consolidacion: {e}")
    
    # Generar informe
    if consolidation_stats:
        try:
            report = generate_report(args.bucket, results, consolidation_stats)
            print(f"\n[OK] Informe generado exitosamente")
        except Exception as e:
            print(f"\n[WARN] Error generando informe: {e}")
    
    # Mensaje final
    print(f"\n{'='*70}")
    print(f"PIPELINE COMPLETADO")
    print(f"{'='*70}")
    
    if consolidation_stats:
        print(f"\nOutputs generados:")
        print(f"   - Datos por zona: s3://{args.bucket}/data/fincas/")
        print(f"   - Dataset consolidado: {consolidation_stats['output_path']}")
        print(f"   - Informes: s3://{args.bucket}/logs/")
    
    print()


if __name__ == "__main__":
    main()
