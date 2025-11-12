#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_tabular_features.py
----------------------
Tabula rasters Sentinel-2 procesados y genera composite temporal
usando Polars para procesamiento eficiente.

Pipeline integrado con AWS S3:
- Lee rasters procesados desde S3 (01_rasters_procesados_clipped/)
- Extrae valores de píxeles válidos (excluyendo nodata)
- Calcula composiciones temporales (median, p10, p90, range)
- Guarda resultados en S3 (03_features/)

Outputs:
- composite_annual.parquet: Features agregadas temporalmente por píxel (x, y, features)
- observations_all.parquet (opcional): Todas las observaciones (fecha, x, y, features)

Uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/03_tabular_features.py \\
    --rasters s3://bucket/staging/01_rasters_procesados_clipped/ZONA/ \\
    --output s3://bucket/staging/03_features/ZONA/composite_annual.parquet \\
    --save_observations

Autor: Proyecto Manu - Minería de Datos
Versión: 2.1 - Sin máscaras clear sky
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


def discover_rasters(
    rasters_s3_dir: str,
    s3_handler: S3Handler
) -> List[Tuple[str, str]]:
    """
    Descubre rasters procesados desde S3.
    
    Returns:
        Lista de tuplas (date, s3_raster_path)
    """
    print(f"\nBuscando rasters procesados...")
    print(f"   Rasters: {rasters_s3_dir}")
    
    # Listar rasters
    rasters = s3_handler.list_files(rasters_s3_dir, pattern="*.tif")
    print(f"   [OK] {len(rasters)} rasters encontrados")
    
    # Crear lista de pares (date, raster_path)
    pairs = []
    for raster_path in rasters:
        date = extract_date_from_filename(raster_path)
        pairs.append((date, raster_path))
        print(f"   [OK] Raster encontrado: {date}")
    
    return pairs


def raster_to_dataframe(
    raster_path: str,
    date: str,
    s3_handler: S3Handler,
    tmpdir: str
) -> pl.DataFrame:
    """
    Convierte raster multibanda a DataFrame excluyendo píxeles nodata.
    
    Args:
        raster_path: Path S3 al raster multibanda
        date: Fecha de la imagen (YYYYMMDD)
        s3_handler: Handler para operaciones S3
        tmpdir: Directorio temporal para descargas
    
    Returns:
        DataFrame de Polars con columnas: date, x, y, B02, B03, ..., NDVI, NDWI
    """
    # Descargar archivo desde S3
    local_raster = os.path.join(tmpdir, f"{date}_raster.tif")
    s3_handler.download_file(raster_path, local_raster)
    
    # Leer raster
    with rasterio.open(local_raster) as src:
        data = src.read()
        transform = src.transform
        nodata = src.nodata
        band_names = [src.descriptions[i] or f"band_{i+1}" for i in range(src.count)]
    
    # Generar coordenadas
    n_bands, height, width = data.shape
    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    xs, ys = rasterio.transform.xy(transform, rows.flatten(), cols.flatten())
    
    # Filtrar píxeles válidos (excluir nodata)
    valid_mask = np.ones(height * width, dtype=bool)
    if nodata is not None:
        # Excluir píxeles donde la primera banda tiene nodata
        first_band_valid = data[0].flatten() != nodata
        valid_mask = valid_mask & first_band_valid
    
    n_valid = valid_mask.sum()
    print(f"   Pixeles válidos: {n_valid:,}/{valid_mask.size:,} ({n_valid/valid_mask.size*100:.1f}%)")
    
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
    print(f"\n Calculando composite temporal...")
    
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
        description="Tabula rasters Sentinel-2 y genera composite temporal (AWS S3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/03_tabular_features.py \\
    --rasters s3://bucket/staging/01_rasters_procesados_clipped/ZONA/ \\
    --output s3://bucket/staging/03_features/ZONA/composite_annual.parquet \\
    --save_observations \\
    --observations s3://bucket/staging/03_features/ZONA/observations_all.parquet
    
Ejemplo local (para testing):
  python 03_tabular_features.py \\
    --rasters s3://mineria-project/staging/01_rasters_procesados_clipped/29_Cuiva_SantaRosadeOsos_Antioquia/ \\
    --output s3://mineria-project/staging/03_features/29_Cuiva_SantaRosadeOsos_Antioquia/composite_annual.parquet
        """
    )
    
    parser.add_argument("--rasters", required=True,
                       help="Directorio S3 con rasters procesados (ej: s3://bucket/staging/01_rasters_procesados_clipped/ZONA/)")
    parser.add_argument("--output", required=True,
                       help="Path S3 para composite anual (ej: s3://bucket/staging/03_features/ZONA/composite.parquet)")
    parser.add_argument("--save_observations", action="store_true",
                       help="Guardar todas las observaciones (date, x, y, features)")
    parser.add_argument("--observations", default=None,
                       help="Path S3 para observaciones completas (solo con --save_observations)")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("TABULACION Y COMPOSICION TEMPORAL CON POLARS")
    print("="*70)
    
    # Validar paths S3
    if not all(p.startswith('s3://') for p in [args.rasters, args.output]):
        print(f"\nError: Todos los paths deben ser S3 (s3://...)")
        sys.exit(1)
    
    # Si se guarda observations, necesita path
    if args.save_observations and not args.observations:
        # Generar path automático
        output_dir = str(Path(args.output).parent)
        args.observations = f"{output_dir}/observations_all.parquet"
    
    print(f"\nConfiguracion:")
    print(f"   Rasters: {args.rasters}")
    print(f"   Output composite: {args.output}")
    if args.save_observations:
        print(f"   Output observations: {args.observations}")
    
    # Inicializar S3 handler
    s3_handler = S3Handler()
    
    # Descubrir rasters
    pairs = discover_rasters(args.rasters, s3_handler)
    
    if not pairs:
        print(f"\n[ERROR] No se encontraron rasters")
        sys.exit(1)
    
    print(f"\n[OK] {len(pairs)} rasters encontrados")
    
    # Procesar cada raster y acumular observaciones
    all_observations = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, (date, raster_path) in enumerate(pairs, 1):
            print(f"\n{'-'*70}")
            print(f"[{i}/{len(pairs)}] Procesando {date}...")
            
            try:
                df = raster_to_dataframe(raster_path, date, s3_handler, tmpdir)
                all_observations.append(df)
                print(f"   [OK] Filas: {len(df):,}, Columnas: {len(df.columns)}")
            
            except Exception as e:
                print(f"   [ERROR] Error: {e}")
                continue
        
        if not all_observations:
            print(f"\n[ERROR] No se pudieron procesar observaciones")
            sys.exit(1)
        
        # Concatenar todas las observaciones
        print(f"\n Concatenando observaciones...")
        observations = pl.concat(all_observations, how="vertical_relaxed")
        
        n_unique_dates = observations['date'].n_unique()
        n_unique_pixels = observations.select([pl.col('x'), pl.col('y')]).unique().shape[0]
        
        print(f"   [OK] Total observaciones: {len(observations):,}")
        print(f"   [OK] Fechas unicas: {n_unique_dates}")
        print(f"   [OK] Pixeles unicos: {n_unique_pixels:,}")
        
        # Guardar observaciones si se solicitó
        if args.save_observations:
            print(f"\n Guardando observaciones completas...")
            local_obs = os.path.join(tmpdir, "observations_all.parquet")
            observations.write_parquet(local_obs)
            
            # Subir a S3
            s3_handler.upload_file(local_obs, args.observations)
            size_mb = Path(local_obs).stat().st_size / (1024**2)
            print(f"   [OK] Guardado: {args.observations} ({size_mb:.2f} MB)")
        
        # Calcular composite temporal
        composite = compute_temporal_composite(observations)
        
        print(f"   [OK] Composite: {len(composite):,} píxeles, {len(composite.columns)} columnas")
        
        # Estadísticas de observaciones/píxel
        if "n_obs" in composite.columns:
            min_obs = composite['n_obs'].min()
            max_obs = composite['n_obs'].max()
            mean_obs = composite['n_obs'].mean()
            if min_obs is not None and max_obs is not None and mean_obs is not None:
                print(f"\n    Observaciones/píxel:")
                print(f"      Min: {min_obs}, Max: {max_obs}, Media: {mean_obs:.1f}")
        
        # Guardar composite
        print(f"\n Guardando composite anual...")
        local_composite = os.path.join(tmpdir, "composite_annual.parquet")
        composite.write_parquet(local_composite)
        
        # Subir a S3
        s3_handler.upload_file(local_composite, args.output)
        size_mb = Path(local_composite).stat().st_size / (1024**2)
        print(f"   [OK] Guardado: {args.output} ({size_mb:.2f} MB)")
    
    # Resumen final
    print(f"\n" + "="*70)
    print("[OK] TABULACION COMPLETADA")
    print("="*70)
    
    print(f"\n Resumen:")
    print(f"   Fechas procesadas: {n_unique_dates}")
    print(f"   Pixeles unicos: {n_unique_pixels:,}")
    print(f"   Total observaciones: {len(observations):,}")
    print(f"   Features: {len(composite.columns) - 3}")  # -3 por x, y, n_obs
    
    print(f"\n Outputs:")
    print(f"   Composite: {args.output}")
    if args.save_observations:
        print(f"   Observations: {args.observations}")
    
    print(f"\n Siguiente paso:")
    print(f"   Rasterizar labels de bosque -> 04_rasterizar_labels.py")
    print()


if __name__ == "__main__":
    main()
