#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_procesar_sentinel.py
-----------------------
Procesa archivos SAFE de Sentinel-2 en AWS EMR.
Lee desde S3, procesa bandas e índices, guarda en S3.

Uso (EMR):
  spark-submit \
    --deploy-mode cluster \
    --executor-memory 16g \
    s3://bucket/scripts/01_procesar_sentinel.py \
    --input s3://bucket/raw_sentinel/*.SAFE \
    --output s3://bucket/01_processed/ \
    --bands B01,B02,B03,B04,B05,B06,B07,B08,B8A,B11,B12 \
    --resolution 20 \
    --indices NDVI,NDWI
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Dict
import tempfile

import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.errors import RasterioIOError
import boto3
from botocore.exceptions import ClientError


def parse_args():
    p = argparse.ArgumentParser(description="Procesa Sentinel-2 SAFE files en AWS")
    p.add_argument("--input", required=True, help="S3 path pattern de SAFE files")
    p.add_argument("--output", required=True, help="S3 output directory")
    p.add_argument("--bands", default="B01,B02,B03,B04,B05,B06,B07,B08,B8A,B11,B12", 
                   help="Bandas a procesar (separadas por coma)")
    p.add_argument("--resolution", type=int, default=20, help="Resolución objetivo (m)")
    p.add_argument("--indices", default="NDVI,NDWI", help="Índices a calcular")
    p.add_argument("--target_crs", default="EPSG:4326", help="CRS objetivo")
    p.add_argument("--temp_dir", default="/tmp/sentinel_processing", help="Directorio temporal")
    return p.parse_args()


class S3Handler:
    """Maneja operaciones con S3"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.s3_resource = boto3.resource('s3')
    
    def parse_s3_path(self, s3_path: str):
        """Extrae bucket y key de s3://bucket/key"""
        parts = s3_path.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""
        return bucket, key
    
    def list_safe_files(self, s3_pattern: str) -> List[str]:
        """Lista archivos SAFE en S3"""
        bucket, prefix = self.parse_s3_path(s3_pattern.replace("*.SAFE", ""))
        
        response = self.s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        safe_dirs = set()
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                if '.SAFE/' in key:
                    safe_dir = key.split('.SAFE/')[0] + '.SAFE'
                    safe_dirs.add(f"s3://{bucket}/{safe_dir}")
        
        return sorted(safe_dirs)
    
    def download_file(self, s3_path: str, local_path: str):
        """Descarga archivo de S3"""
        bucket, key = self.parse_s3_path(s3_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.s3_client.download_file(bucket, key, local_path)
    
    def upload_file(self, local_path: str, s3_path: str):
        """Sube archivo a S3"""
        bucket, key = self.parse_s3_path(s3_path)
        self.s3_client.upload_file(local_path, bucket, key)
        print(f"  ✓ Subido: {s3_path}")


def find_band_file(safe_dir: str, band: str, resolution: int) -> str:
    """Encuentra archivo de banda en estructura SAFE"""
    granule_dir = Path(safe_dir) / "GRANULE"
    
    if not granule_dir.exists():
        raise FileNotFoundError(f"No se encontró directorio GRANULE en {safe_dir}")
    
    tile_dirs = list(granule_dir.glob("L2A_*"))
    if not tile_dirs:
        raise FileNotFoundError(f"No se encontraron tiles L2A en {granule_dir}")
    
    img_dir = tile_dirs[0] / "IMG_DATA" / f"R{resolution}m"
    
    band_files = list(img_dir.glob(f"*_{band}_{resolution}m.jp2"))
    if not band_files:
        raise FileNotFoundError(f"No se encontró banda {band} a {resolution}m en {img_dir}")
    
    return str(band_files[0])


def calculate_ndvi(b08: np.ndarray, b04: np.ndarray) -> np.ndarray:
    """Calcula NDVI = (NIR - Red) / (NIR + Red)"""
    with np.errstate(divide='ignore', invalid='ignore'):
        ndvi = (b08 - b04) / (b08 + b04)
        ndvi[np.isnan(ndvi)] = 0
        ndvi[np.isinf(ndvi)] = 0
    return ndvi


def calculate_ndwi(b03: np.ndarray, b08: np.ndarray) -> np.ndarray:
    """Calcula NDWI = (Green - NIR) / (Green + NIR)"""
    with np.errstate(divide='ignore', invalid='ignore'):
        ndwi = (b03 - b08) / (b03 + b08)
        ndwi[np.isnan(ndwi)] = 0
        ndwi[np.isinf(ndwi)] = 0
    return ndwi


def process_safe_file(safe_s3_path: str, bands: List[str], resolution: int, 
                     indices: List[str], target_crs: str, temp_dir: str,
                     s3_handler: S3Handler) -> str:
    """Procesa un archivo SAFE completo"""
    
    safe_name = os.path.basename(safe_s3_path)
    print(f"\n{'='*70}")
    print(f"Procesando: {safe_name}")
    print(f"{'='*70}")
    
    # Crear directorio temporal
    local_safe_dir = os.path.join(temp_dir, safe_name)
    os.makedirs(local_safe_dir, exist_ok=True)
    
    # Descargar solo las bandas necesarias
    bucket, prefix = s3_handler.parse_s3_path(safe_s3_path)
    
    print(f"  Descargando bandas desde S3...")
    band_files = {}
    for band in bands:
        try:
            # Construir path esperado de la banda
            s3_band_pattern = f"{prefix}/GRANULE/*/IMG_DATA/R{resolution}m/*_{band}_{resolution}m.jp2"
            
            # Listar archivos que coincidan
            response = s3_handler.s3_client.list_objects_v2(
                Bucket=bucket,
                Prefix=f"{prefix}/GRANULE/"
            )
            
            band_key = None
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    if f"_{band}_{resolution}m.jp2" in key and f"/R{resolution}m/" in key:
                        band_key = key
                        break
            
            if band_key:
                local_band_path = os.path.join(local_safe_dir, os.path.basename(band_key))
                s3_handler.download_file(f"s3://{bucket}/{band_key}", local_band_path)
                band_files[band] = local_band_path
                print(f"    ✓ {band}")
            else:
                print(f"    ⚠ {band} no encontrada")
        
        except Exception as e:
            print(f"    ✗ Error descargando {band}: {e}")
    
    if not band_files:
        raise ValueError(f"No se pudieron descargar bandas de {safe_name}")
    
    # Leer banda de referencia para metadata
    ref_band = band_files[bands[0]]
    with rasterio.open(ref_band) as src:
        ref_meta = src.meta.copy()
        ref_transform = src.transform
        ref_crs = src.crs
        ref_bounds = src.bounds
    
    # Transformación a CRS objetivo si es necesario
    if str(ref_crs) != target_crs:
        dst_crs = target_crs
        dst_transform, dst_width, dst_height = calculate_default_transform(
            ref_crs, dst_crs, ref_meta['width'], ref_meta['height'],
            *ref_bounds
        )
    else:
        dst_crs = ref_crs
        dst_transform = ref_transform
        dst_width = ref_meta['width']
        dst_height = ref_meta['height']
    
    # Procesar bandas e índices
    print(f"\n  Procesando bandas e índices...")
    
    output_bands = {}
    
    # Leer y reproyectar bandas
    for band, band_file in band_files.items():
        with rasterio.open(band_file) as src:
            if str(src.crs) != target_crs:
                band_data = np.empty((dst_height, dst_width), dtype=np.float32)
                reproject(
                    source=rasterio.band(src, 1),
                    destination=band_data,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear
                )
            else:
                band_data = src.read(1).astype(np.float32)
            
            # Normalizar a [0, 1]
            band_data = band_data / 10000.0
            band_data = np.clip(band_data, 0, 1)
            
            output_bands[band] = band_data
            print(f"    ✓ {band}")
    
    # Calcular índices
    if "NDVI" in indices and "B08" in output_bands and "B04" in output_bands:
        ndvi = calculate_ndvi(output_bands["B08"], output_bands["B04"])
        output_bands["NDVI"] = ndvi
        print(f"    ✓ NDVI")
    
    if "NDWI" in indices and "B03" in output_bands and "B08" in output_bands:
        ndwi = calculate_ndwi(output_bands["B03"], output_bands["B08"])
        output_bands["NDWI"] = ndwi
        print(f"    ✓ NDWI")
    
    # Guardar como GeoTIFF multiband
    output_filename = safe_name.replace(".SAFE", "_procesado.tif")
    local_output_path = os.path.join(temp_dir, output_filename)
    
    n_bands = len(output_bands)
    band_names = list(output_bands.keys())
    
    output_meta = {
        'driver': 'GTiff',
        'dtype': 'float32',
        'nodata': 0,
        'width': dst_width,
        'height': dst_height,
        'count': n_bands,
        'crs': dst_crs,
        'transform': dst_transform,
        'compress': 'lzw',
        'tiled': True,
        'blockxsize': 256,
        'blockysize': 256
    }
    
    print(f"\n  Guardando: {output_filename}")
    with rasterio.open(local_output_path, 'w', **output_meta) as dst:
        for i, band_name in enumerate(band_names, 1):
            dst.write(output_bands[band_name], i)
            dst.set_band_description(i, band_name)
    
    print(f"    ✓ Archivo local: {local_output_path}")
    
    # Limpiar archivos temporales de bandas
    for band_file in band_files.values():
        try:
            os.remove(band_file)
        except:
            pass
    
    return local_output_path, band_names


def main():
    args = parse_args()
    
    print(f"\n{'='*70}")
    print("PROCESAMIENTO SENTINEL-2 EN AWS EMR")
    print(f"{'='*70}")
    print(f"  Input:  {args.input}")
    print(f"  Output: {args.output}")
    print(f"  Bands:  {args.bands}")
    print(f"  Resolution: {args.resolution}m")
    print(f"  Indices: {args.indices}")
    
    bands = [b.strip() for b in args.bands.split(',')]
    indices = [i.strip() for i in args.indices.split(',')]
    
    # Inicializar S3
    s3_handler = S3Handler()
    
    # Listar archivos SAFE
    print(f"\n  Listando archivos SAFE en S3...")
    safe_files = s3_handler.list_safe_files(args.input)
    print(f"  ✓ Encontrados: {len(safe_files)} archivos SAFE")
    
    if not safe_files:
        print("  ⚠ No se encontraron archivos SAFE")
        return
    
    # Crear directorio temporal
    os.makedirs(args.temp_dir, exist_ok=True)
    
    # Procesar cada SAFE file
    processed_count = 0
    failed_count = 0
    
    for safe_path in safe_files:
        try:
            local_output, band_names = process_safe_file(
                safe_path, bands, args.resolution, indices,
                args.target_crs, args.temp_dir, s3_handler
            )
            
            # Subir a S3
            output_filename = os.path.basename(local_output)
            s3_output_path = f"{args.output.rstrip('/')}/{output_filename}"
            
            print(f"\n  Subiendo a S3: {s3_output_path}")
            s3_handler.upload_file(local_output, s3_output_path)
            
            # Limpiar archivo local
            os.remove(local_output)
            
            processed_count += 1
            
        except Exception as e:
            print(f"\n  ✗ Error procesando {os.path.basename(safe_path)}: {e}")
            failed_count += 1
    
    print(f"\n{'='*70}")
    print("RESUMEN")
    print(f"{'='*70}")
    print(f"  ✓ Procesados exitosamente: {processed_count}")
    print(f"  ✗ Fallidos: {failed_count}")
    print(f"  Output S3: {args.output}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
