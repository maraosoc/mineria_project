#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_procesar_sentinel_clip.py
----------------------------
Procesa archivos SAFE de Sentinel-2 con recorte por shapefile.
Lee desde S3, procesa bandas e índices, recorta a zona de interés, guarda en S3.
"""

import argparse
import os
import sys
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import tempfile

import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.mask import mask
from rasterio.errors import RasterioIOError
import geopandas as gpd
from shapely.geometry import mapping
import boto3
from botocore.exceptions import ClientError


def parse_args():
    p = argparse.ArgumentParser(description="Procesa Sentinel-2 SAFE files con recorte")
    p.add_argument("--input", required=True, help="S3 path a carpeta de zona")
    p.add_argument("--output", required=True, help="S3 output directory")
    p.add_argument("--zone_name", required=True, help="Nombre de la zona")
    p.add_argument("--shape_path", help="S3 path al shapefile de perimetro")
    p.add_argument("--bands", default="B02,B03,B04,B05,B06,B07,B8A,B11,B12", 
                   help="Bandas a procesar (solo 20m)")
    p.add_argument("--resolution", type=int, default=20, help="Resolucion objetivo (m)")
    p.add_argument("--indices", default="NDVI,NDWI", help="Indices a calcular")
    p.add_argument("--target_crs", default="EPSG:4326", help="CRS objetivo para reproyeccion")
    p.add_argument("--temp_dir", default="C:/temp/sentinel_processing", help="Directorio temporal")
    p.add_argument("--clip", action="store_true", help="Recortar con shapefile de perimetro")
    p.add_argument("--log_bucket", default="s3://mineria-project/logs/01_procesar_sentinel/", 
                   help="S3 path para guardar logs de archivos corruptos")
    return p.parse_args()


class CorruptFileLogger:
    """Registra archivos SAFE con problemas de CRS o bounds"""
    
    def __init__(self, zone_name: str, s3_handler):
        self.zone_name = zone_name
        self.s3_handler = s3_handler
        self.corrupt_files = []
        self.timestamp = datetime.utcnow().isoformat()
    
    def add_corrupt_file(self, safe_name: str, issue_type: str, details: dict):
        """Registra un archivo corrupto con sus detalles"""
        entry = {
            "timestamp": self.timestamp,
            "zone_name": self.zone_name,
            "safe_file": safe_name,
            "issue_type": issue_type,  # "crs_mismatch", "bounds_invalid", "no_overlap"
            "details": details
        }
        self.corrupt_files.append(entry)
        
        print(f"  [WARN] Archivo registrado como corrupto: {safe_name}")
        print(f"    Problema: {issue_type}")
        print(f"    Detalles: {json.dumps(details, indent=2)}")
    
    def save_logs(self, log_s3_path: str):
        """Guarda los logs en S3"""
        if not self.corrupt_files:
            print("\n  No se encontraron archivos corruptos")
            return
        
        # Crear nombre de archivo de log con timestamp
        log_filename = f"corrupt_files_{self.zone_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Crear log con resumen
        log_data = {
            "zone_name": self.zone_name,
            "timestamp": self.timestamp,
            "total_corrupt_files": len(self.corrupt_files),
            "corrupt_files": self.corrupt_files,
            "summary": {
                "crs_mismatch": sum(1 for f in self.corrupt_files if f["issue_type"] == "crs_mismatch"),
                "bounds_invalid": sum(1 for f in self.corrupt_files if f["issue_type"] == "bounds_invalid"),
                "no_overlap": sum(1 for f in self.corrupt_files if f["issue_type"] == "no_overlap")
            }
        }
        
        # Guardar en archivo temporal
        temp_log_path = os.path.join(tempfile.gettempdir(), log_filename)
        with open(temp_log_path, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        # Subir a S3
        log_s3_full_path = f"{log_s3_path.rstrip('/')}/{log_filename}"
        print(f"\n  Subiendo log de archivos corruptos a S3: {log_s3_full_path}")
        self.s3_handler.upload_file(temp_log_path, log_s3_full_path)
        
        # Limpiar archivo temporal
        os.remove(temp_log_path)
        
        print(f"  [OK] Log guardado exitosamente")
        print(f"  Total archivos corruptos: {len(self.corrupt_files)}")


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
    
    def list_safe_files(self, s3_zone_path: str) -> List[str]:
        """Lista archivos SAFE en una carpeta de zona especifica en S3"""
        bucket, prefix = self.parse_s3_path(s3_zone_path)
        
        if not prefix.endswith('/'):
            prefix += '/'
        
        print(f"  Buscando en: s3://{bucket}/{prefix}")
        
        paginator = self.s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)
        
        safe_dirs = set()
        for page in page_iterator:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    if '.SAFE/' in key:
                        safe_path = key.split('.SAFE/')[0] + '.SAFE'
                        safe_name = safe_path.replace(prefix, '')
                        if safe_name:
                            safe_dirs.add(f"s3://{bucket}/{safe_path}")
        
        return sorted(list(safe_dirs))
    
    def download_file(self, s3_path: str, local_path: str):
        """Descarga archivo de S3"""
        bucket, key = self.parse_s3_path(s3_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.s3_client.download_file(bucket, key, local_path)
    
    def upload_file(self, local_path: str, s3_path: str):
        """Sube archivo a S3"""
        bucket, key = self.parse_s3_path(s3_path)
        self.s3_client.upload_file(local_path, bucket, key)
        print(f"  [OK] Subido: {s3_path}")
    
    def download_shapefile(self, shape_s3_base: str, local_dir: str) -> str:
        """
        Descarga todos los componentes de un shapefile desde S3.
        Retorna la ruta local al archivo .shp principal.
        """
        bucket, prefix = self.parse_s3_path(shape_s3_base)
        
        if prefix.endswith('.shp') or prefix.endswith('.shx'):
            prefix = prefix.rsplit('.', 1)[0]
        
        extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.shp.xml']
        
        os.makedirs(local_dir, exist_ok=True)
        shp_file = None
        
        for ext in extensions:
            s3_key = f"{prefix}{ext}"
            local_file = os.path.join(local_dir, os.path.basename(s3_key))
            
            try:
                self.s3_client.download_file(bucket, s3_key, local_file)
                if ext == '.shp':
                    shp_file = local_file
                print(f"    [OK] Descargado: {os.path.basename(local_file)}")
            except ClientError as e:
                if e.response['Error']['Code'] != '404':
                    print(f"    [WARN] Error descargando {ext}: {e}")
        
        if not shp_file or not os.path.exists(shp_file):
            raise FileNotFoundError(f"No se pudo descargar shapefile desde {shape_s3_base}")
        
        return shp_file


def load_clip_geometry(shapefile_path: str) -> gpd.GeoDataFrame:
    """
    Carga shapefile y retorna GeoDataFrame.
    NO reproyecta aqui - se reproyectara dinamicamente al CRS de cada raster.
    """
    print(f"  Cargando shapefile: {shapefile_path}")
    gdf = gpd.read_file(shapefile_path)
    
    print(f"    CRS original: {gdf.crs}")
    print(f"    Geometrias: {len(gdf)}")
    
    # Unir todas las geometrias en una sola si hay multiples
    if len(gdf) > 1:
        from shapely.ops import unary_union
        geometry = unary_union(gdf.geometry)
        gdf = gpd.GeoDataFrame([{'geometry': geometry}], crs=gdf.crs)
    
    bounds = gdf.total_bounds
    print(f"    Bounds: minx={bounds[0]:.6f}, miny={bounds[1]:.6f}, maxx={bounds[2]:.6f}, maxy={bounds[3]:.6f}")
    
    return gdf


def calculate_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Calcula NDVI = (NIR - Red) / (NIR + Red)"""
    with np.errstate(divide='ignore', invalid='ignore'):
        ndvi = (nir - red) / (nir + red)
        ndvi = np.nan_to_num(ndvi, nan=0.0, posinf=0.0, neginf=0.0)
    return ndvi


def calculate_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Calcula NDWI = (Green - NIR) / (Green + NIR)"""
    with np.errstate(divide='ignore', invalid='ignore'):
        ndwi = (green - nir) / (green + nir)
        ndwi = np.nan_to_num(ndwi, nan=0.0, posinf=0.0, neginf=0.0)
    return ndwi


def validate_bounds_geographic(bounds_4326, expected_lat_range=(-5, 15), expected_lon_range=(-80, -66)):
    """
    Valida que los bounds en EPSG:4326 estén dentro del rango esperado para Colombia.
    Colombia: aproximadamente lat 12°S a 12°N (-5 a 15), lon 82°W a 66°W (-82 a -66)
    """
    left, bottom, right, top = bounds_4326.left, bounds_4326.bottom, bounds_4326.right, bounds_4326.top
    
    # Verificar si está dentro de los rangos de Colombia (con margen)
    lat_valid = expected_lat_range[0] <= bottom and top <= expected_lat_range[1]
    lon_valid = expected_lon_range[0] <= left and right <= expected_lon_range[1]
    
    return lat_valid and lon_valid, {
        "bounds": {
            "left": left,
            "bottom": bottom,
            "right": right,
            "top": top
        },
        "lat_valid": lat_valid,
        "lon_valid": lon_valid,
        "expected_lat_range": expected_lat_range,
        "expected_lon_range": expected_lon_range
    }


def process_safe_file(safe_s3_path: str, bands: List[str], resolution: int, 
                     indices: List[str], target_crs: str, temp_dir: str,
                     s3_handler, clip_gdf: Optional[gpd.GeoDataFrame]=None,
                     logger: Optional['CorruptFileLogger']=None) -> Tuple[Optional[str], List[str], bool]:
    """
    Procesa un archivo SAFE completo con recorte opcional.
    Retorna: (local_output_path, band_names, is_corrupt)
    """
    
    safe_name = os.path.basename(safe_s3_path)
    print(f"\n{'='*70}")
    print(f"Procesando: {safe_name}")
    print(f"{'='*70}")
    
    # Crear directorio temporal
    local_safe_dir = os.path.join(temp_dir, safe_name)
    os.makedirs(local_safe_dir, exist_ok=True)
    
    # Descargar solo las bandas necesarias
    bucket, prefix = s3_handler.parse_s3_path(safe_s3_path)
    
    print(f"  Descargando bandas desde S3 (resolucion {resolution}m)...")
    band_files = {}
    for band in bands:
        try:
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
                print(f"    [OK] {band}")
            else:
                print(f"    [WARN] {band} no encontrada a {resolution}m")
        
        except Exception as e:
            print(f"    [ERROR] Error descargando {band}: {e}")
    
    if not band_files:
        raise ValueError(f"No se pudieron descargar bandas de {safe_name}")
    
    # Leer banda de referencia para metadata
    ref_band = band_files[bands[0]]
    with rasterio.open(ref_band) as src:
        ref_meta = src.meta.copy()
        ref_transform = src.transform
        ref_crs = src.crs
        ref_bounds = src.bounds
    
    print(f"    CRS original del raster (posiblemente incorrecto): {ref_crs}")
    print(f"    Bounds originales: {ref_bounds}")
    
    # Variable para rastrear si el archivo es corrupto
    is_corrupt = False
    corruption_details = {}
    
    # CORRECCION: Extraer el tile code del nombre SAFE y forzar el CRS correcto
    # Formato: S2X_MSIL2A_YYYYMMDDTHHMMSS_NXXXX_RXXX_TXXXXX_...
    # El tile code está después de la tercera R (ej: T18NWL, T18NTP)
    tile_match = re.search(r'_T(\d{2})[A-Z]{3}_', safe_name)
    if tile_match:
        utm_zone = int(tile_match.group(1))
        # Colombia está en el hemisferio norte, usar EPSG:326XX
        correct_crs_code = f"EPSG:326{utm_zone:02d}"
        print(f"    Tile detectado: Zone {utm_zone}N -> CRS correcto debe ser: {correct_crs_code}")
        
        # Si el CRS leído es diferente al correcto, necesitamos usar el correcto
        if str(ref_crs) != correct_crs_code:
            print(f"    [WARN] CRS del archivo ({ref_crs}) NO coincide con tile code")
            print(f"    Usando CRS correcto basado en tile code: {correct_crs_code}")
            # Registrar problema de CRS
            is_corrupt = True
            corruption_details["crs_mismatch"] = {
                "file_crs": str(ref_crs),
                "expected_crs": correct_crs_code,
                "tile_code": f"T{utm_zone:02d}"
            }
            # Usar el CRS correcto para la reproyección
            ref_crs_for_reproj = correct_crs_code
        else:
            ref_crs_for_reproj = ref_crs
    else:
        print(f"    [WARN] No se pudo extraer tile code de {safe_name}, usando CRS del archivo")
        ref_crs_for_reproj = ref_crs
    
    # Siempre reproyectar a target_crs para normalizar
    if target_crs and str(ref_crs_for_reproj) != target_crs:
        print(f"    Reproyectando raster de {ref_crs_for_reproj} a {target_crs}")
        dst_crs = target_crs
        dst_transform, dst_width, dst_height = calculate_default_transform(
            ref_crs_for_reproj, dst_crs, ref_meta['width'], ref_meta['height'],
            *ref_bounds
        )
        print(f"    Nuevas dimensiones: {dst_width}x{dst_height}")
        
        # Calcular bounds en EPSG:4326 para validación
        from rasterio.transform import array_bounds
        bounds_4326 = rasterio.coords.BoundingBox(*array_bounds(dst_height, dst_width, dst_transform))
        
        # Validar que los bounds estén en Colombia
        bounds_valid, validation_info = validate_bounds_geographic(bounds_4326)
        if not bounds_valid:
            print(f"    [WARN] Bounds fuera del rango esperado para Colombia")
            is_corrupt = True
            corruption_details["bounds_invalid"] = validation_info
    else:
        # Mantener CRS original si no se especifica target_crs
        dst_crs = ref_crs_for_reproj
        dst_transform = ref_transform
        dst_width = ref_meta['width']
        dst_height = ref_meta['height']
        bounds_4326 = None
    
    # Procesar bandas e indices
    print(f"\n  Procesando bandas e indices...")
    
    output_bands = {}
    
    # Leer y reproyectar bandas
    for band, band_file in band_files.items():
        with rasterio.open(band_file) as src:
            if target_crs and str(ref_crs_for_reproj) != str(dst_crs):
                # Reproyectar banda usando el CRS corregido
                band_data = np.empty((dst_height, dst_width), dtype=np.float32)
                reproject(
                    source=rasterio.band(src, 1),
                    destination=band_data,
                    src_transform=src.transform,
                    src_crs=ref_crs_for_reproj,  # Usar CRS corregido, no src.crs
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear
                )
            else:
                # Leer sin reproyectar
                band_data = src.read(1).astype(np.float32)
            
            # Normalizar a [0, 1]
            band_data = band_data / 10000.0
            band_data = np.clip(band_data, 0, 1)
            
            output_bands[band] = band_data
            print(f"    [OK] {band}")
    
    # Calcular indices
    if "NDVI" in indices and "B8A" in output_bands and "B04" in output_bands:
        ndvi = calculate_ndvi(output_bands["B8A"], output_bands["B04"])
        output_bands["NDVI"] = ndvi
        print(f"    [OK] NDVI")
    
    if "NDWI" in indices and "B03" in output_bands and "B8A" in output_bands:
        ndwi = calculate_ndwi(output_bands["B03"], output_bands["B8A"])
        output_bands["NDWI"] = ndwi
        print(f"    [OK] NDWI")
    
    # Aplicar recorte si se proporciono geometria
    if clip_gdf is not None:
        print(f"\n  Aplicando recorte con shapefile...")
        
        # Crear un GeoTIFF temporal con todas las bandas
        temp_full_path = os.path.join(temp_dir, "temp_full.tif")
        
        n_bands = len(output_bands)
        band_names = list(output_bands.keys())
        
        temp_meta = {
            'driver': 'GTiff',
            'dtype': 'float32',
            'nodata': 0,
            'width': dst_width,
            'height': dst_height,
            'count': n_bands,
            'crs': dst_crs,
            'transform': dst_transform,
        }
        
        # Escribir bandas temporales
        with rasterio.open(temp_full_path, 'w', **temp_meta) as dst:
            for i, band_name in enumerate(band_names, 1):
                dst.write(output_bands[band_name], i)
        
        # Reproyectar geometria al CRS del raster y aplicar recorte
        try:
            with rasterio.open(temp_full_path) as src:
                # Debug: mostrar CRS y bounds del raster
                print(f"    Raster CRS: {src.crs}")
                print(f"    Raster bounds: {src.bounds}")
                
                # Reproyectar GeoDataFrame al CRS del raster
                if clip_gdf.crs != src.crs:
                    print(f"    Reproyectando geometria de {clip_gdf.crs} a {src.crs}")
                    gdf_reproj = clip_gdf.to_crs(src.crs)
                    print(f"    Geometry bounds reproyectada: {gdf_reproj.total_bounds}")
                else:
                    gdf_reproj = clip_gdf
                    print(f"    Geometry bounds (sin reproyeccion): {gdf_reproj.total_bounds}")
                
                # Convertir geometrias a formato GeoJSON
                geometries = [mapping(geom) for geom in gdf_reproj.geometry]
                
                # Aplicar recorte
                clipped_data, clipped_transform = mask(src, geometries, crop=True, filled=False)
                
                # Actualizar dimensiones
                clipped_height, clipped_width = clipped_data.shape[1], clipped_data.shape[2]
                dst_height, dst_width = clipped_height, clipped_width
                dst_transform = clipped_transform
                
                # Actualizar bandas con datos recortados
                for i, band_name in enumerate(band_names):
                    output_bands[band_name] = clipped_data[i]
                
                original_pixels = temp_meta['height'] * temp_meta['width']
                clipped_pixels = dst_height * dst_width
                reduction = (1 - clipped_pixels / original_pixels) * 100
                
                print(f"    Dimensiones originales: {temp_meta['height']}x{temp_meta['width']}")
                print(f"    Dimensiones recortadas: {dst_height}x{dst_width}")
                print(f"    Reduccion: {reduction:.1f}%")
                print(f"    [OK] Recorte aplicado exitosamente")
                
        except ValueError as e:
            error_msg = str(e)
            print(f"    [WARN] No se pudo recortar: {error_msg}")
            print(f"    Continuando sin recorte")
            
            # Registrar problema de overlap si es el error específico
            if "do not overlap" in error_msg.lower():
                is_corrupt = True
                corruption_details["no_overlap"] = {
                    "error": error_msg,
                    "raster_crs": str(src.crs) if 'src' in locals() else "unknown",
                    "raster_bounds": list(src.bounds) if 'src' in locals() else None,
                    "geometry_bounds": list(gdf_reproj.total_bounds) if 'gdf_reproj' in locals() else None
                }
        except Exception as e:
            print(f"    [ERROR] Error en recorte: {e}")
            print(f"    Continuando sin recorte")
            is_corrupt = True
            corruption_details["clip_error"] = {
                "error": str(e),
                "error_type": type(e).__name__
            }
        finally:
            # Eliminar archivo temporal
            if os.path.exists(temp_full_path):
                os.remove(temp_full_path)
    
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
    
    file_size_mb = os.path.getsize(local_output_path) / (1024 * 1024)
    print(f"    [OK] Archivo local: {local_output_path}")
    print(f"    Tamano: {file_size_mb:.2f} MB")
    
    # Registrar en logger si el archivo es corrupto
    if is_corrupt and logger:
        issue_type = "multiple_issues"
        if "crs_mismatch" in corruption_details and len(corruption_details) == 1:
            issue_type = "crs_mismatch"
        elif "bounds_invalid" in corruption_details and len(corruption_details) == 1:
            issue_type = "bounds_invalid"
        elif "no_overlap" in corruption_details:
            issue_type = "no_overlap"
        
        logger.add_corrupt_file(safe_name, issue_type, corruption_details)
    
    # Limpiar archivos temporales de bandas
    for band_file in band_files.values():
        try:
            os.remove(band_file)
        except:
            pass
    
    return local_output_path, band_names, is_corrupt


def main():
    args = parse_args()
    
    print(f"\n{'='*70}")
    print("PROCESAMIENTO SENTINEL-2 - SCRIPT 01 CON RECORTE")
    print(f"{'='*70}")
    print(f"  Zona:   {args.zone_name}")
    print(f"  Input:  {args.input}")
    print(f"  Output: {args.output}")
    print(f"  Bands:  {args.bands}")
    print(f"  Resolution: {args.resolution}m")
    print(f"  Indices: {args.indices}")
    print(f"  Clip:   {'Si (con shapefile)' if args.clip else 'No'}")
    
    bands = [b.strip() for b in args.bands.split(',')]
    indices = [i.strip() for i in args.indices.split(',')]
    
    # Inicializar S3
    s3_handler = S3Handler()
    
    # Inicializar logger de archivos corruptos
    logger = CorruptFileLogger(args.zone_name, s3_handler)
    
    # Cargar geometria de recorte si se especifico
    clip_gdf = None
    if args.clip:
        print(f"\n{'='*70}")
        print("CARGANDO SHAPEFILE DE RECORTE")
        print(f"{'='*70}")
        
        # Si no se especifico shape_path, construirlo automaticamente
        if not args.shape_path:
            bucket, _ = s3_handler.parse_s3_path(args.input)
            args.shape_path = f"s3://{bucket}/raw/shapes/{args.zone_name}/Perimetro"
            print(f"  Path automatico: {args.shape_path}.shp")
        
        try:
            # Descargar shapefile
            shape_local_dir = os.path.join(args.temp_dir, "shapes", args.zone_name)
            shape_local_path = s3_handler.download_shapefile(args.shape_path, shape_local_dir)
            
            # Cargar geometria
            clip_gdf = load_clip_geometry(shape_local_path)
            print(f"  [OK] Shapefile cargado exitosamente")
            
        except Exception as e:
            print(f"  [ERROR] Error cargando shapefile: {e}")
            print(f"  [WARN] Continuando SIN recorte")
            import traceback
            traceback.print_exc()
            clip_gdf = None
    
    # Listar archivos SAFE
    print(f"\n{'='*70}")
    print("LISTANDO ARCHIVOS SENTINEL-2")
    print(f"{'='*70}")
    safe_files = s3_handler.list_safe_files(args.input)
    print(f"  [OK] Encontrados: {len(safe_files)} archivos SAFE")
    
    if not safe_files:
        print("  [WARN] No se encontraron archivos SAFE")
        return
    
    for safe_path in safe_files:
        print(f"    - {os.path.basename(safe_path)}")
    
    # Crear directorio temporal
    os.makedirs(args.temp_dir, exist_ok=True)
    
    # Preparar directorio de salida
    zone_output = f"{args.output.rstrip('/')}/{args.zone_name}"
    print(f"\n  Output final: {zone_output}")
    
    # Procesar cada SAFE file
    print(f"\n{'='*70}")
    print("PROCESANDO ARCHIVOS")
    print(f"{'='*70}")
    processed_count = 0
    failed_count = 0
    corrupt_count = 0
    total_size_mb = 0
    
    for safe_path in safe_files:
        try:
            local_output, band_names, is_corrupt = process_safe_file(
                safe_path, bands, args.resolution, indices,
                args.target_crs, args.temp_dir, s3_handler,
                clip_gdf=clip_gdf, logger=logger
            )
            
            # Si el archivo es corrupto, NO subirlo a S3
            if is_corrupt:
                print(f"\n  [WARN] Archivo corrupto detectado, NO se sube a S3")
                print(f"  Se guardará información en logs para análisis posterior")
                
                # Limpiar archivo local
                if os.path.exists(local_output):
                    os.remove(local_output)
                
                corrupt_count += 1
            else:
                # Subir a S3 solo si NO es corrupto
                output_filename = os.path.basename(local_output)
                s3_output_path = f"{zone_output}/{output_filename}"
                
                print(f"\n  Subiendo a S3: {s3_output_path}")
                s3_handler.upload_file(local_output, s3_output_path)
                
                # Acumular tamaño
                file_size_mb = os.path.getsize(local_output) / (1024 * 1024)
                total_size_mb += file_size_mb
                
                # Limpiar archivo local
                os.remove(local_output)
                
                processed_count += 1
            
        except Exception as e:
            print(f"\n  [ERROR] Error procesando {os.path.basename(safe_path)}: {e}")
            import traceback
            traceback.print_exc()
            failed_count += 1
    
    # Guardar logs de archivos corruptos en S3
    if corrupt_count > 0:
        print(f"\n{'='*70}")
        print("GUARDANDO LOGS DE ARCHIVOS CORRUPTOS")
        print(f"{'='*70}")
        logger.save_logs(args.log_bucket)
    
    print(f"\n{'='*70}")
    print("RESUMEN")
    print(f"{'='*70}")
    print(f"  Zona: {args.zone_name}")
    print(f"  [OK] Procesados exitosamente: {processed_count}")
    print(f"  [WARN] Archivos corruptos (no subidos): {corrupt_count}")
    print(f"  [ERROR] Fallidos: {failed_count}")
    print(f"  Tamano total generado: {total_size_mb:.2f} MB")
    print(f"  Output S3: {zone_output}")
    if corrupt_count > 0:
        print(f"  Logs corruptos S3: {args.log_bucket}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
