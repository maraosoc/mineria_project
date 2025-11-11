#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05_unir_features_labels.py
--------------------------
Une features anuales (composite) con etiquetas del raster de bosque
para generar tabla de entrenamiento.

Pipeline integrado con AWS S3:
- Lee composite anual desde S3 (03_features/composite_annual.parquet)
- Lee raster de etiquetas desde S3 (04_labels/forest_labels.tif)
- Extrae etiqueta para cada píxel usando coordenadas (x, y)
- Filtra píxeles con label != -1 (excluye "ignorar")
- Guarda tabla de entrenamiento en S3 (05_training_data/)

Output:
- training_data.parquet: Features + label (x, y, B01_med, ..., NDVI_med, ..., label)

Uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/05_unir_features_labels.py \\
    --features s3://bucket/03_features/composite_annual.parquet \\
    --labels s3://bucket/04_labels/forest_labels.tif \\
    --output s3://bucket/05_training_data/training_data.parquet

Autor: Proyecto Manu - Minería de Datos
Versión: 2.0 - AWS EMR
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Tuple
import numpy as np
import polars as pl
import rasterio
import boto3


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
        print(f"  Descargando: s3://{bucket}/{key}")
        self.s3_client.download_file(bucket, key, local_path)
    
    def upload_file(self, local_path: str, s3_path: str):
        """Sube archivo local a S3"""
        bucket, key = self.parse_s3_path(s3_path)
        print(f"  Subiendo a: s3://{bucket}/{key}")
        self.s3_client.upload_file(local_path, bucket, key)


def extract_label_from_raster(
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    label_raster_path: str
) -> np.ndarray:
    """
    Extrae valores del raster de etiquetas para cada coordenada (x, y).
    
    Args:
        x_coords: Array de longitudes
        y_coords: Array de latitudes
        label_raster_path: Path al raster de etiquetas
    
    Returns:
        Array de labels (int16)
    """
    with rasterio.open(label_raster_path) as src:
        # Convertir coordenadas geográficas a índices de píxel
        rows, cols = rasterio.transform.rowcol(src.transform, x_coords, y_coords)
        
        # Leer raster completo
        labels_array = src.read(1)
        
        # Asegurar que los índices estén dentro de límites
        rows = np.clip(rows, 0, src.height - 1)
        cols = np.clip(cols, 0, src.width - 1)
        
        # Extraer valores
        labels = labels_array[rows, cols]
        
        return labels


def main():
    parser = argparse.ArgumentParser(
        description="Une features anuales con etiquetas para generar tabla de entrenamiento (AWS S3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/05_unir_features_labels.py \\
    --features s3://bucket/03_features/composite_annual.parquet \\
    --labels s3://bucket/04_labels/forest_labels.tif \\
    --output s3://bucket/05_training_data/training_data.parquet
    
Ejemplo local (para testing):
  python 05_unir_features_labels.py \\
    --features s3://mineria-data-dev/03_features/composite_annual.parquet \\
    --labels s3://mineria-data-dev/04_labels/forest_labels.tif \\
    --output s3://mineria-data-dev/05_training_data/training_data.parquet
        """
    )
    
    parser.add_argument("--features", required=True,
                       help="Parquet S3 con features anuales (composite_annual.parquet)")
    parser.add_argument("--labels", required=True,
                       help="Raster S3 de etiquetas (forest_labels.tif)")
    parser.add_argument("--output", required=True,
                       help="Path S3 de salida (training_data.parquet)")
    parser.add_argument("--format", choices=["parquet", "csv"], default="parquet",
                       help="Formato de salida (default: parquet)")
    parser.add_argument("--exclude_ignore", action="store_true", default=True,
                       help="Excluir píxeles con label=-1 (ignorar). Default: True")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("UNIÓN DE FEATURES + LABELS → TABLA DE ENTRENAMIENTO")
    print("="*70)
    
    # Validar paths S3
    if not all(p.startswith('s3://') for p in [args.features, args.labels, args.output]):
        print(f"\n❌ Error: Todos los paths deben ser S3 (s3://...)")
        sys.exit(1)
    
    print(f"\n📂 Archivos de entrada:")
    print(f"   Features: {args.features}")
    print(f"   Labels: {args.labels}")
    print(f"   Output: {args.output}")
    print(f"   Formato: {args.format}")
    print(f"   Excluir ignorar: {args.exclude_ignore}")
    
    # Inicializar S3 handler
    s3_handler = S3Handler()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # --- 1) Descargar features desde S3
        print(f"\n📊 Descargando features anuales...")
        local_features = os.path.join(tmpdir, "composite_annual.parquet")
        s3_handler.download_file(args.features, local_features)
        
        # Cargar con Polars
        df_features = pl.read_parquet(local_features)
        n_features = len(df_features)
        n_cols_features = len(df_features.columns)
        
        print(f"   ✓ {n_features:,} píxeles cargados")
        print(f"   ✓ {n_cols_features} columnas (features)")
        
        feature_cols = [col for col in df_features.columns if col not in ['x', 'y']]
        print(f"   ✓ Features disponibles: {', '.join(feature_cols[:5])}... ({len(feature_cols)} total)")
        
        # --- 2) Descargar raster de etiquetas desde S3
        print(f"\n🏷️  Descargando raster de etiquetas...")
        local_labels = os.path.join(tmpdir, "forest_labels.tif")
        s3_handler.download_file(args.labels, local_labels)
        
        # --- 3) Extraer etiquetas para cada píxel
        print(f"\n🔍 Extrayendo etiquetas del raster...")
        x_coords = df_features['x'].to_numpy()
        y_coords = df_features['y'].to_numpy()
        
        labels = extract_label_from_raster(x_coords, y_coords, local_labels)
        
        print(f"   ✓ {len(labels):,} etiquetas extraídas")
        
        # Estadísticas de etiquetas
        n_bosque = np.sum(labels == 1)
        n_no_bosque = np.sum(labels == 0)
        n_ignorar = np.sum(labels == -1)
        
        print(f"\n   Distribución de etiquetas:")
        print(f"      Bosque (1):      {n_bosque:,} ({n_bosque/len(labels)*100:.1f}%)")
        print(f"      No-Bosque (0):   {n_no_bosque:,} ({n_no_bosque/len(labels)*100:.1f}%)")
        print(f"      Ignorar (-1):    {n_ignorar:,} ({n_ignorar/len(labels)*100:.1f}%)")
        
        # --- 4) Agregar etiquetas al DataFrame
        print(f"\n🔗 Uniendo features + labels...")
        df_features = df_features.with_columns(
            pl.Series("label", labels, dtype=pl.Int16)
        )
        
        # --- 5) Filtrar píxeles "ignorar" si se especifica
        if args.exclude_ignore:
            print(f"\n🔍 Filtrando píxeles con label=-1 (ignorar)...")
            df_training = df_features.filter(pl.col("label") != -1)
            n_removed = len(df_features) - len(df_training)
            print(f"   ✓ {n_removed:,} píxeles removidos")
            print(f"   ✓ {len(df_training):,} píxeles válidos restantes")
        else:
            df_training = df_features
            print(f"\n○ Conservando todos los píxeles (incluye label=-1)")
        
        # Estadísticas finales
        n_final_bosque = df_training.filter(pl.col("label") == 1).shape[0]
        n_final_no_bosque = df_training.filter(pl.col("label") == 0).shape[0]
        
        print(f"\n📊 Datos de entrenamiento finales:")
        print(f"   Total samples: {len(df_training):,}")
        print(f"   Bosque (1):    {n_final_bosque:,} ({n_final_bosque/len(df_training)*100:.1f}%)")
        print(f"   No-Bosque (0): {n_final_no_bosque:,} ({n_final_no_bosque/len(df_training)*100:.1f}%)")
        
        if n_final_bosque > 0 and n_final_no_bosque > 0:
            ratio = n_final_no_bosque / n_final_bosque
            print(f"   Ratio: {ratio:.2f}:1")
            
            if ratio > 10 or ratio < 0.1:
                print(f"   ⚠️  Desbalance significativo - considerar:")
                print(f"      - class_weight='balanced' en modelo")
                print(f"      - Ajustar erosion_pixels en 04_rasterizar_labels.py")
        
        print(f"\n   Features: {len(feature_cols)}")
        print(f"   Columnas totales: {len(df_training.columns)}")
        
        # --- 6) Guardar tabla de entrenamiento
        print(f"\n💾 Guardando tabla de entrenamiento...")
        
        if args.format == "parquet":
            local_output = os.path.join(tmpdir, "training_data.parquet")
            df_training.write_parquet(local_output)
        else:
            local_output = os.path.join(tmpdir, "training_data.csv")
            df_training.write_csv(local_output)
        
        size_mb = Path(local_output).stat().st_size / (1024**2)
        print(f"   ✓ Formato: {args.format.upper()}")
        print(f"   ✓ Tamaño: {size_mb:.2f} MB")
        
        # Subir a S3
        s3_handler.upload_file(local_output, args.output)
        print(f"   ✓ Archivo guardado: {args.output}")
    
    # Resumen final
    print(f"\n" + "="*70)
    print("✅ TABLA DE ENTRENAMIENTO GENERADA")
    print("="*70)
    
    print(f"\n📊 Resumen:")
    print(f"   Píxeles totales: {n_features:,}")
    print(f"   Píxeles válidos: {len(df_training):,}")
    print(f"   Bosque: {n_final_bosque:,}")
    print(f"   No-Bosque: {n_final_no_bosque:,}")
    print(f"   Features: {len(feature_cols)}")
    
    print(f"\n📂 Output:")
    print(f"   {args.output}")
    
    print(f"\n📋 Siguiente paso:")
    print(f"   Entrenar modelo Random Forest + GBT → 06_entrenar_modelos_spark.py")
    
    print(f"\n💡 Ejemplo de uso del archivo generado:")
    print(f"""
# En PySpark:
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()
df = spark.read.parquet("{args.output}")
df.show(5)

# En Python local:
import polars as pl
df = pl.read_parquet("{args.output}")
print(df.head())
    """)
    print()


if __name__ == "__main__":
    main()
