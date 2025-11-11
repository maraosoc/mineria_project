#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_generar_mascaras.py
----------------------
Genera máscaras clear sky a partir de rasters Sentinel-2 procesados usando SCL
(Scene Classification Layer) y heurísticas basadas en NDVI y NIR.

Pipeline integrado con AWS S3:
- Lee rasters procesados desde S3 (01_processed/)
- Genera máscaras clear sky (1=clear, 0=cloud/shadow/nodata)
- Guarda máscaras en S3 (02_masks/)

Máscaras basadas en:
- SCL: excluir nubes {8,9,10}, sombras {3}, nieve {11}
- Heurística nubes: NDVI bajo + NIR alto
- Heurística sombras: NDVI bajo + NIR bajo
- Dilatación morfológica de nubes (buffer de seguridad)

Uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/02_generar_mascaras.py \\
    --input s3://bucket/01_processed/*.tif \\
    --output s3://bucket/02_masks/ \\
    --dilate_pixels 1

Autor: Proyecto Manu - Minería de Datos
Versión: 2.0 - AWS EMR
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from scipy.ndimage import binary_dilation
import boto3
from botocore.exceptions import ClientError


class S3Handler:
    """Maneja operaciones con S3 (download/upload)"""
    
    def __init__(self, bucket_name: str = None):
        self.s3_client = boto3.client('s3')
        self.bucket_name = bucket_name
    
    def parse_s3_path(self, s3_path: str) -> Tuple[str, str]:
        """Extrae bucket y key de s3://bucket/path/to/file"""
        if not s3_path.startswith('s3://'):
            raise ValueError(f"Path debe empezar con s3://: {s3_path}")
        parts = s3_path[5:].split('/', 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ''
        return bucket, key
    
    def download_file(self, s3_path: str, local_path: str):
        """Descarga archivo desde S3 a path local"""
        bucket, key = self.parse_s3_path(s3_path)
        print(f"  Descargando: s3://{bucket}/{key}")
        self.s3_client.download_file(bucket, key, local_path)
    
    def upload_file(self, local_path: str, s3_path: str):
        """Sube archivo local a S3"""
        bucket, key = self.parse_s3_path(s3_path)
        print(f"  Subiendo: s3://{bucket}/{key}")
        self.s3_client.upload_file(local_path, bucket, key)
    
    def list_files(self, s3_prefix: str, pattern: str = "*.tif") -> List[str]:
        """Lista archivos en S3 que coincidan con pattern"""
        bucket, prefix = self.parse_s3_path(s3_prefix)
        
        # Remover wildcard del prefix si existe
        if prefix.endswith('*'):
            prefix = str(Path(prefix).parent)
        if prefix.endswith('*.tif'):
            prefix = str(Path(prefix).parent)
        
        response = self.s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                # Filtrar por patrón si se especifica
                if pattern == "*.tif" and key.endswith('.tif'):
                    files.append(f"s3://{bucket}/{key}")
                elif pattern in key or pattern == "*":
                    files.append(f"s3://{bucket}/{key}")
        
        return sorted(files)


def build_clear_mask(
    scl: np.ndarray, 
    ndvi: np.ndarray, 
    nir: np.ndarray,
    t_ndvi_cloud: float = 0.10,
    t_ndvi_shadow: float = 0.05,
    dilate_cloud_px: int = 1,
    exclude_water: bool = False
) -> np.ndarray:
    """
    Construye máscara CLEAR combinando SCL y heurísticas NDVI/NIR.
    
    Args:
        scl: Array SCL (Scene Classification Layer) uint8
        ndvi: Array NDVI normalizado float32 [-1, 1]
        nir: Array NIR (B8A) normalizado float32 [0, 1]
        t_ndvi_cloud: Umbral NDVI para detección de nubes (default: 0.10)
        t_ndvi_shadow: Umbral NDVI para detección de sombras (default: 0.05)
        dilate_cloud_px: Píxeles de dilatación para nubes (default: 1)
        exclude_water: Si True, excluye píxeles de agua (SCL==6)
    
    Returns:
        Array uint8 (1=clear, 0=bad/masked)
    """
    # Inicializar máscara como "clear" (1)
    mask = np.ones(scl.shape, dtype=np.uint8)
    
    # 1) Máscara SCL: nubes {8,9,10}, sombras {3}, nieve {11}
    scl_bad = np.isin(scl, [3, 8, 9, 10, 11])
    mask[scl_bad] = 0
    
    # 2) Opcional: excluir agua (SCL==6)
    if exclude_water:
        mask[scl == 6] = 0
    
    # 3) Heurística nubes: NDVI bajo + NIR alto
    if np.any(mask == 1):
        p80_nir = np.percentile(nir[mask == 1], 80)
        cloud_heuristic = (ndvi < t_ndvi_cloud) & (nir > p80_nir)
        mask[cloud_heuristic] = 0
    
    # 4) Heurística sombras: NDVI bajo + NIR bajo
    if np.any(mask == 1):
        p20_nir = np.percentile(nir[mask == 1], 20)
        shadow_heuristic = (ndvi < t_ndvi_shadow) & (nir < p20_nir)
        mask[shadow_heuristic] = 0
    
    # 5) Dilatación de nubes
    if dilate_cloud_px > 0:
        cloud_mask = (mask == 0)
        dilated = binary_dilation(cloud_mask, iterations=dilate_cloud_px)
        mask[dilated] = 0
    
    return mask


def extract_date_from_filename(filename: str) -> str:
    """Extrae fecha del nombre del archivo (formato: YYYYMMDD_*.tif)"""
    basename = Path(filename).stem
    # Asumimos formato: YYYYMMDD_sentinel20m_procesado
    date = basename.split('_')[0]
    return date


def generate_clear_mask(
    raster_path: str,
    output_path: str,
    dilate_pixels: int = 1,
    exclude_water: bool = False,
    t_ndvi_cloud: float = 0.10,
    t_ndvi_shadow: float = 0.05
) -> Tuple[int, int]:
    """
    Genera máscara clear sky a partir de un raster Sentinel-2 procesado.
    
    Args:
        raster_path: Path al raster multibanda con bandas procesadas
        output_path: Path donde guardar la máscara
        dilate_pixels: Píxeles de dilatación para nubes
        exclude_water: Si True, excluye píxeles de agua
        t_ndvi_cloud: Umbral NDVI para nubes
        t_ndvi_shadow: Umbral NDVI para sombras
    
    Returns:
        Tuple (n_clear, n_total): Número de píxeles clear y total
    """
    with rasterio.open(raster_path) as src:
        # Leer metadatos
        meta = src.meta.copy()
        band_descriptions = [src.descriptions[i] for i in range(src.count)]
        
        # Buscar índices de bandas necesarias
        try:
            idx_scl = band_descriptions.index('SCL')
            idx_ndvi = band_descriptions.index('NDVI')
            idx_nir = band_descriptions.index('B8A')
        except ValueError as e:
            print(f"  ❌ Error: Banda no encontrada en raster: {e}")
            print(f"     Bandas disponibles: {band_descriptions}")
            raise
        
        # Leer bandas (índices 1-based para rasterio)
        scl = src.read(idx_scl + 1).astype(np.uint8)
        ndvi = src.read(idx_ndvi + 1).astype(np.float32)
        nir = src.read(idx_nir + 1).astype(np.float32)
    
    # Generar máscara clear
    mask = build_clear_mask(
        scl, ndvi, nir,
        t_ndvi_cloud=t_ndvi_cloud,
        t_ndvi_shadow=t_ndvi_shadow,
        dilate_cloud_px=dilate_pixels,
        exclude_water=exclude_water
    )
    
    # Calcular estadísticas
    n_clear = np.sum(mask == 1)
    n_total = mask.size
    
    # Guardar máscara
    meta.update(count=1, dtype='uint8', nodata=0)
    with rasterio.open(output_path, 'w', **meta) as dst:
        dst.write(mask, 1)
        dst.set_band_description(1, 'clear_mask (1=clear, 0=cloud/shadow)')
    
    return n_clear, n_total


def process_raster_with_s3(
    s3_input: str,
    s3_output_dir: str,
    s3_handler: S3Handler,
    dilate_pixels: int = 1,
    exclude_water: bool = False,
    t_ndvi_cloud: float = 0.10,
    t_ndvi_shadow: float = 0.05
) -> dict:
    """
    Procesa un raster desde S3, genera máscara, y sube a S3.
    
    Returns:
        Dict con estadísticas del procesamiento
    """
    date = extract_date_from_filename(s3_input)
    
    print(f"\n[{date}] Procesando...")
    print(f"  Input: {s3_input}")
    
    # Crear temp dir para procesamiento local
    with tempfile.TemporaryDirectory() as tmpdir:
        # Descargar raster desde S3
        local_input = os.path.join(tmpdir, f"{date}_input.tif")
        s3_handler.download_file(s3_input, local_input)
        
        # Generar máscara localmente
        local_output = os.path.join(tmpdir, f"{date}_clear_mask.tif")
        n_clear, n_total = generate_clear_mask(
            local_input,
            local_output,
            dilate_pixels=dilate_pixels,
            exclude_water=exclude_water,
            t_ndvi_cloud=t_ndvi_cloud,
            t_ndvi_shadow=t_ndvi_shadow
        )
        
        # Subir máscara a S3
        s3_output = f"{s3_output_dir}/{date}_clear_mask.tif"
        s3_handler.upload_file(local_output, s3_output)
        
        pct_clear = n_clear / n_total * 100
        print(f"  ✓ Clear pixels: {n_clear:,}/{n_total:,} ({pct_clear:.1f}%)")
        print(f"  ✓ Output: {s3_output}")
    
    return {
        'date': date,
        'n_clear': n_clear,
        'n_total': n_total,
        'pct_clear': pct_clear,
        's3_output': s3_output
    }


def main():
    parser = argparse.ArgumentParser(
        description="Genera máscaras clear sky desde rasters Sentinel-2 procesados (AWS S3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/02_generar_mascaras.py \\
    --input s3://bucket/01_processed/*.tif \\
    --output s3://bucket/02_masks/ \\
    --dilate_pixels 1
    
Ejemplo local (para testing):
  python 02_generar_mascaras.py \\
    --input s3://mineria-data-dev/01_processed/*.tif \\
    --output s3://mineria-data-dev/02_masks/ \\
    --dilate_pixels 1
        """
    )
    
    parser.add_argument("--input", required=True,
                       help="Path S3 a rasters procesados (ej: s3://bucket/01_processed/*.tif)")
    parser.add_argument("--output", required=True,
                       help="Directorio S3 donde guardar máscaras (ej: s3://bucket/02_masks/)")
    parser.add_argument("--dilate_pixels", type=int, default=1,
                       help="Píxeles de dilatación para nubes (default: 1)")
    parser.add_argument("--exclude_water", action="store_true",
                       help="Excluir píxeles de agua (SCL==6)")
    parser.add_argument("--t_ndvi_cloud", type=float, default=0.10,
                       help="Umbral NDVI para detección de nubes (default: 0.10)")
    parser.add_argument("--t_ndvi_shadow", type=float, default=0.05,
                       help="Umbral NDVI para detección de sombras (default: 0.05)")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("GENERACIÓN DE MÁSCARAS CLEAR SKY")
    print("="*70)
    
    # Validar paths S3
    if not args.input.startswith('s3://'):
        print(f"\n❌ Error: --input debe ser un path S3 (s3://...)")
        sys.exit(1)
    
    if not args.output.startswith('s3://'):
        print(f"\n❌ Error: --output debe ser un path S3 (s3://...)")
        sys.exit(1)
    
    # Asegurar que output termine con /
    if not args.output.endswith('/'):
        args.output += '/'
    
    print(f"\n⚙️  Configuración:")
    print(f"   Input: {args.input}")
    print(f"   Output: {args.output}")
    print(f"   Dilatación nubes: {args.dilate_pixels} px")
    print(f"   Excluir agua: {args.exclude_water}")
    print(f"   Umbral NDVI nubes: {args.t_ndvi_cloud}")
    print(f"   Umbral NDVI sombras: {args.t_ndvi_shadow}")
    
    # Inicializar S3 handler
    s3_handler = S3Handler()
    
    # Listar archivos en S3
    print(f"\n🔍 Buscando rasters procesados...")
    input_files = s3_handler.list_files(args.input, pattern="*.tif")
    
    if not input_files:
        print(f"  ❌ No se encontraron archivos .tif en {args.input}")
        sys.exit(1)
    
    print(f"  ✓ {len(input_files)} archivos encontrados")
    
    # Procesar cada raster
    results = []
    for i, s3_input in enumerate(input_files, 1):
        print(f"\n{'─'*70}")
        print(f"Procesando {i}/{len(input_files)}")
        
        try:
            result = process_raster_with_s3(
                s3_input,
                args.output,
                s3_handler,
                dilate_pixels=args.dilate_pixels,
                exclude_water=args.exclude_water,
                t_ndvi_cloud=args.t_ndvi_cloud,
                t_ndvi_shadow=args.t_ndvi_shadow
            )
            results.append(result)
        
        except Exception as e:
            print(f"  ❌ Error procesando {s3_input}: {e}")
            continue
    
    # Resumen final
    print(f"\n" + "="*70)
    print("✅ PROCESAMIENTO COMPLETADO")
    print("="*70)
    
    if results:
        print(f"\n📊 Resumen de máscaras generadas:")
        print(f"   Total procesados: {len(results)}")
        
        # Calcular estadísticas agregadas
        total_clear = sum(r['n_clear'] for r in results)
        total_pixels = sum(r['n_total'] for r in results)
        avg_clear = total_clear / total_pixels * 100 if total_pixels > 0 else 0
        
        print(f"\n   Estadísticas globales:")
        print(f"      Clear pixels: {total_clear:,}/{total_pixels:,} ({avg_clear:.1f}%)")
        print(f"      Avg per image: {avg_clear:.1f}%")
        
        # Mostrar resumen por fecha
        print(f"\n   Detalle por fecha:")
        for r in results:
            print(f"      {r['date']}: {r['pct_clear']:.1f}% clear")
        
        print(f"\n📂 Máscaras guardadas en: {args.output}")
    else:
        print(f"\n⚠️  No se generaron máscaras")
    
    print()


if __name__ == "__main__":
    main()
