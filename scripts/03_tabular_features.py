#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_tabular_features.py
----------------------
Tabula rasters Sentinel-2 procesados + máscaras clear sky y genera composite temporal
usando Polars para procesamiento eficiente.

Pipeline integrado con AWS S3:
- Lee rasters procesados desde S3 (01_processed/)
- Lee máscaras clear sky desde S3 (02_masks/)
- Extrae valores de píxeles válidos (clear==1, nodata excluido)
- Calcula composiciones temporales (median, p10, p90, range)
- Guarda resultados en S3 (03_features/)

Outputs:
- composite_annual.parquet: Features agregadas temporalmente por píxel (x, y, features)
- observations_all.parquet (opcional): Todas las observaciones (fecha, x, y, features)

Uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/03_tabular_features.py \\
    --rasters s3://bucket/01_processed/ \\
    --masks s3://bucket/02_masks/ \\
    --output s3://bucket/03_features/composite_annual.parquet \\
    --save_observations

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
import polars as pl
import rasterio
import boto3
from botocore.exceptions import ClientError


class S3Handler:
    """Maneja operaciones con S3 (download/upload)"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
    
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
        self.s3_client.download_file(bucket, key, local_path)
    
    def upload_file(self, local_path: str, s3_path: str):
        """Sube archivo local a S3"""
        bucket, key = self.parse_s3_path(s3_path)
        print(f"  Subiendo a: s3://{bucket}/{key}")
        self.s3_client.upload_file(local_path, bucket, key)
    
    def list_files(self, s3_prefix: str, pattern: str = "*.tif") -> List[str]:
        """Lista archivos en S3 que coincidan con pattern"""
        bucket, prefix = self.parse_s3_path(s3_prefix)
        
        # Remover wildcard del prefix si existe
        if prefix.endswith('*'):
            prefix = str(Path(prefix).parent) + '/'
        if not prefix.endswith('/') and prefix:
            prefix += '/'
        
        response = self.s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                # Filtrar por patrón
                if pattern == "*.tif" and key.endswith('.tif'):
                    files.append(f"s3://{bucket}/{key}")
                elif pattern == "*.parquet" and key.endswith('.parquet'):
                    files.append(f"s3://{bucket}/{key}")
                elif pattern in key or pattern == "*":
                    files.append(f"s3://{bucket}/{key}")
        
        return sorted(files)


def extract_date_from_filename(filename: str) -> str:
    """Extrae fecha del nombre del archivo (formato: YYYYMMDD_*.tif)"""
    basename = Path(filename).stem
    date = basename.split('_')[0]
    return date


def discover_image_pairs(
    rasters_s3_dir: str,
    masks_s3_dir: str,
    s3_handler: S3Handler
) -> List[Tuple[str, str, str]]:
    """
    Descubre pares (date, raster_procesado, clear_mask) desde S3.
    
    Returns:
        Lista de tuplas (date, s3_raster_path, s3_mask_path)
    """
    print(f"\n🔍 Buscando pares raster/máscara...")
    print(f"   Rasters: {rasters_s3_dir}")
    print(f"   Máscaras: {masks_s3_dir}")
    
    # Listar rasters
    rasters = s3_handler.list_files(rasters_s3_dir, pattern="*.tif")
    print(f"   ✓ {len(rasters)} rasters encontrados")
    
    # Listar máscaras
    masks = s3_handler.list_files(masks_s3_dir, pattern="*.tif")
    print(f"   ✓ {len(masks)} máscaras encontradas")
    
    # Crear dict de máscaras por fecha
    masks_by_date = {}
    for mask_path in masks:
        date = extract_date_from_filename(mask_path)
        masks_by_date[date] = mask_path
    
    # Emparejar rasters con máscaras
    pairs = []
    for raster_path in rasters:
        date = extract_date_from_filename(raster_path)
        if date in masks_by_date:
            pairs.append((date, raster_path, masks_by_date[date]))
            print(f"   ✓ Par encontrado: {date}")
        else:
            print(f"   ⚠️  Máscara no encontrada para {date}")
    
    return pairs


def raster_to_dataframe(
    raster_path: str,
    mask_path: str,
    date: str,
    s3_handler: S3Handler,
    tmpdir: str
) -> pl.DataFrame:
    """
    Convierte raster multibanda a DataFrame filtrando por máscara clear==1 y excluyendo nodata.
    
    Args:
        raster_path: Path S3 al raster multibanda
        mask_path: Path S3 a la máscara clear sky
        date: Fecha de la imagen (YYYYMMDD)
        s3_handler: Handler para operaciones S3
        tmpdir: Directorio temporal para descargas
    
    Returns:
        DataFrame de Polars con columnas: date, x, y, B01, B02, ..., NDVI, NDWI
    """
    # Descargar archivos desde S3
    local_raster = os.path.join(tmpdir, f"{date}_raster.tif")
    local_mask = os.path.join(tmpdir, f"{date}_mask.tif")
    
    s3_handler.download_file(raster_path, local_raster)
    s3_handler.download_file(mask_path, local_mask)
    
    # Leer raster
    with rasterio.open(local_raster) as src:
        data = src.read()
        transform = src.transform
        nodata = src.nodata
        band_names = [src.descriptions[i] or f"band_{i+1}" for i in range(src.count)]
    
    # Leer máscara
    with rasterio.open(local_mask) as mask_src:
        clear_mask = mask_src.read(1)
    
    # Generar coordenadas
    n_bands, height, width = data.shape
    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    xs, ys = rasterio.transform.xy(transform, rows.flatten(), cols.flatten())
    
    # Filtrar por clear_mask==1 Y excluir píxeles nodata
    valid_mask = clear_mask.flatten() == 1
    if nodata is not None:
        # Excluir píxeles donde la primera banda tiene nodata
        first_band_valid = data[0].flatten() != nodata
        valid_mask = valid_mask & first_band_valid
    
    n_valid = valid_mask.sum()
    print(f"   Píxeles válidos: {n_valid:,}/{valid_mask.size:,} ({n_valid/valid_mask.size*100:.1f}%)")
    
    # Construir DataFrame
    df_data = {
        "date": np.full(n_valid, date),
        "x": np.array(xs)[valid_mask],
        "y": np.array(ys)[valid_mask]
    }
    
    for i, band_name in enumerate(band_names):
        df_data[band_name] = data[i].flatten()[valid_mask].astype(np.float32)
    
    return pl.DataFrame(df_data)


def compute_temporal_composite(observations: pl.DataFrame) -> pl.DataFrame:
    """
    Calcula composición temporal por píxel (median, percentiles).
    
    Args:
        observations: DataFrame con columnas: date, x, y, B01, ..., NDVI, NDWI
    
    Returns:
        DataFrame con composite: x, y, B01_med, ..., NDVI_med, NDVI_p10, NDVI_p90, NDVI_range, n_obs
    """
    print(f"\n📊 Calculando composite temporal...")
    
    feature_cols = [col for col in observations.columns if col not in ("date", "x", "y")]
    
    # Agregar medianas para todas las bandas
    agg_exprs = [pl.col(col).median().alias(f"{col}_med") for col in feature_cols]
    
    # Agregar percentiles y range para NDVI
    if "NDVI" in feature_cols:
        agg_exprs.extend([
            pl.col("NDVI").quantile(0.10).alias("NDVI_p10"),
            pl.col("NDVI").quantile(0.90).alias("NDVI_p90")
        ])
    
    # Agregar count de observaciones
    agg_exprs.append(pl.len().alias("n_obs"))
    
    # Agrupar por píxel
    composite = observations.group_by(["x", "y"]).agg(agg_exprs)
    
    # Calcular NDVI range
    if "NDVI" in feature_cols:
        composite = composite.with_columns(
            (pl.col("NDVI_p90") - pl.col("NDVI_p10")).alias("NDVI_range")
        )
    
    return composite


def main():
    parser = argparse.ArgumentParser(
        description="Tabula rasters Sentinel-2 con máscaras clear sky y genera composite temporal (AWS S3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/03_tabular_features.py \\
    --rasters s3://bucket/01_processed/ \\
    --masks s3://bucket/02_masks/ \\
    --output s3://bucket/03_features/composite_annual.parquet \\
    --save_observations \\
    --observations s3://bucket/03_features/observations_all.parquet
    
Ejemplo local (para testing):
  python 03_tabular_features.py \\
    --rasters s3://mineria-data-dev/01_processed/ \\
    --masks s3://mineria-data-dev/02_masks/ \\
    --output s3://mineria-data-dev/03_features/composite_annual.parquet
        """
    )
    
    parser.add_argument("--rasters", required=True,
                       help="Directorio S3 con rasters procesados (ej: s3://bucket/01_processed/)")
    parser.add_argument("--masks", required=True,
                       help="Directorio S3 con máscaras clear sky (ej: s3://bucket/02_masks/)")
    parser.add_argument("--output", required=True,
                       help="Path S3 para composite anual (ej: s3://bucket/03_features/composite.parquet)")
    parser.add_argument("--save_observations", action="store_true",
                       help="Guardar todas las observaciones (date, x, y, features)")
    parser.add_argument("--observations", default=None,
                       help="Path S3 para observaciones completas (solo con --save_observations)")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("TABULACIÓN Y COMPOSICIÓN TEMPORAL CON POLARS")
    print("="*70)
    
    # Validar paths S3
    if not all(p.startswith('s3://') for p in [args.rasters, args.masks, args.output]):
        print(f"\n❌ Error: Todos los paths deben ser S3 (s3://...)")
        sys.exit(1)
    
    # Si se guarda observations, necesita path
    if args.save_observations and not args.observations:
        # Generar path automático
        output_dir = str(Path(args.output).parent)
        args.observations = f"{output_dir}/observations_all.parquet"
    
    print(f"\n⚙️  Configuración:")
    print(f"   Rasters: {args.rasters}")
    print(f"   Máscaras: {args.masks}")
    print(f"   Output composite: {args.output}")
    if args.save_observations:
        print(f"   Output observations: {args.observations}")
    
    # Inicializar S3 handler
    s3_handler = S3Handler()
    
    # Descubrir pares raster/máscara
    pairs = discover_image_pairs(args.rasters, args.masks, s3_handler)
    
    if not pairs:
        print(f"\n❌ No se encontraron pares raster/máscara")
        sys.exit(1)
    
    print(f"\n✓ {len(pairs)} pares encontrados")
    
    # Procesar cada par y acumular observaciones
    all_observations = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (date, raster_path, mask_path) in enumerate(pairs, 1):
            print(f"\n{'─'*70}")
            print(f"[{i}/{len(pairs)}] Procesando {date}...")
            
            try:
                df = raster_to_dataframe(raster_path, mask_path, date, s3_handler, tmpdir)
                all_observations.append(df)
                print(f"   ✓ Filas: {len(df):,}, Columnas: {len(df.columns)}")
            
            except Exception as e:
                print(f"   ❌ Error: {e}")
                continue
        
        if not all_observations:
            print(f"\n❌ No se pudieron procesar observaciones")
            sys.exit(1)
        
        # Concatenar todas las observaciones
        print(f"\n🔗 Concatenando observaciones...")
        observations = pl.concat(all_observations, how="vertical_relaxed")
        
        n_unique_dates = observations['date'].n_unique()
        n_unique_pixels = observations.select([pl.col('x'), pl.col('y')]).unique().shape[0]
        
        print(f"   ✓ Total observaciones: {len(observations):,}")
        print(f"   ✓ Fechas únicas: {n_unique_dates}")
        print(f"   ✓ Píxeles únicos: {n_unique_pixels:,}")
        
        # Guardar observaciones si se solicitó
        if args.save_observations:
            print(f"\n💾 Guardando observaciones completas...")
            local_obs = os.path.join(tmpdir, "observations_all.parquet")
            observations.write_parquet(local_obs)
            
            # Subir a S3
            s3_handler.upload_file(local_obs, args.observations)
            size_mb = Path(local_obs).stat().st_size / (1024**2)
            print(f"   ✓ Guardado: {args.observations} ({size_mb:.2f} MB)")
        
        # Calcular composite temporal
        composite = compute_temporal_composite(observations)
        
        print(f"   ✓ Composite: {len(composite):,} píxeles, {len(composite.columns)} columnas")
        
        # Estadísticas de observaciones/píxel
        if "n_obs" in composite.columns:
            min_obs = composite['n_obs'].min()
            max_obs = composite['n_obs'].max()
            mean_obs = composite['n_obs'].mean()
            print(f"\n   📊 Observaciones/píxel:")
            print(f"      Min: {min_obs}, Max: {max_obs}, Media: {mean_obs:.1f}")
        
        # Guardar composite
        print(f"\n💾 Guardando composite anual...")
        local_composite = os.path.join(tmpdir, "composite_annual.parquet")
        composite.write_parquet(local_composite)
        
        # Subir a S3
        s3_handler.upload_file(local_composite, args.output)
        size_mb = Path(local_composite).stat().st_size / (1024**2)
        print(f"   ✓ Guardado: {args.output} ({size_mb:.2f} MB)")
    
    # Resumen final
    print(f"\n" + "="*70)
    print("✅ TABULACIÓN COMPLETADA")
    print("="*70)
    
    print(f"\n📊 Resumen:")
    print(f"   Fechas procesadas: {n_unique_dates}")
    print(f"   Píxeles únicos: {n_unique_pixels:,}")
    print(f"   Total observaciones: {len(observations):,}")
    print(f"   Features: {len(composite.columns) - 3}")  # -3 por x, y, n_obs
    
    print(f"\n📂 Outputs:")
    print(f"   Composite: {args.output}")
    if args.save_observations:
        print(f"   Observations: {args.observations}")
    
    print(f"\n📋 Siguiente paso:")
    print(f"   Rasterizar labels de bosque → 04_rasterizar_labels.py")
    print()


if __name__ == "__main__":
    main()
