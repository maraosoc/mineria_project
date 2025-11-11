#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04_rasterizar_labels.py
-----------------------
Rasteriza shapefiles de bosque sobre la malla de un raster de referencia
y genera un raster de etiquetas con erosión morfológica opcional.

Pipeline integrado con AWS S3:
- Lee raster de referencia desde S3 (01_processed/)
- Lee shapefiles de bosque y perímetro desde S3 (shapes/)
- Genera raster de etiquetas: 1=bosque, 0=no-bosque, -1=ignorar
- Aplica erosión morfológica al bosque (evitar píxeles de borde)
- Guarda resultado en S3 (04_labels/)

Etiquetas:
- 1 = bosque (positivo) con erosión morfológica
- 0 = no-bosque (negativo) dentro del perímetro
- -1 = ignorar (fuera del perímetro o sin datos)

Uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/04_rasterizar_labels.py \\
    --ref s3://bucket/01_processed/20200112_sentinel20m_procesado.tif \\
    --bosque_shp s3://bucket/shapes/bosque.shp \\
    --perimetro_shp s3://bucket/shapes/study_area.shp \\
    --output s3://bucket/04_labels/forest_labels.tif \\
    --erosion_pixels 2

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
import geopandas as gpd
from shapely.ops import unary_union
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import binary_erosion
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
    
    def download_shapefile(self, s3_shp_path: str, local_dir: str) -> str:
        """
        Descarga shapefile completo (.shp, .shx, .dbf, .prj) desde S3.
        
        Args:
            s3_shp_path: Path S3 al archivo .shp
            local_dir: Directorio local donde descargar
        
        Returns:
            Path local al archivo .shp
        """
        bucket, shp_key = self.parse_s3_path(s3_shp_path)
        base_key = shp_key.rsplit('.', 1)[0]  # Remover .shp
        
        # Extensiones de shapefile
        extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg']
        
        local_shp = None
        for ext in extensions:
            s3_key = base_key + ext
            local_file = os.path.join(local_dir, os.path.basename(s3_key))
            
            try:
                self.s3_client.download_file(bucket, s3_key, local_file)
                if ext == '.shp':
                    local_shp = local_file
            except Exception as e:
                if ext in ['.shp', '.shx', '.dbf']:
                    # Estos son obligatorios
                    raise
                # Otros son opcionales
                pass
        
        return local_shp
    
    def upload_file(self, local_path: str, s3_path: str):
        """Sube archivo local a S3"""
        bucket, key = self.parse_s3_path(s3_path)
        print(f"  Subiendo a: s3://{bucket}/{key}")
        self.s3_client.upload_file(local_path, bucket, key)


def rasterize_geom(geom, out_shape, transform, burn_value=1, dtype="uint8"):
    """Rasteriza una geometría (o colección) a una matriz binaria."""
    if geom is None or geom.is_empty:
        return np.zeros(out_shape, dtype=dtype)
    
    arr = rasterize(
        [(geom, burn_value)],
        out_shape=out_shape,
        transform=transform,
        fill=0,
        dtype=dtype
    )
    return arr


def main():
    parser = argparse.ArgumentParser(
        description="Genera raster de etiquetas (1=bosque, 0=no-bosque, -1=ignorar) con erosión (AWS S3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/04_rasterizar_labels.py \\
    --ref s3://bucket/01_processed/20200112_sentinel20m_procesado.tif \\
    --bosque_shp s3://bucket/shapes/bosque.shp \\
    --perimetro_shp s3://bucket/shapes/study_area.shp \\
    --output s3://bucket/04_labels/forest_labels.tif \\
    --erosion_pixels 2
    
Ejemplo local (para testing):
  python 04_rasterizar_labels.py \\
    --ref s3://mineria-data-dev/01_processed/20200112_sentinel20m_procesado.tif \\
    --bosque_shp s3://mineria-data-dev/shapes/bosque.shp \\
    --output s3://mineria-data-dev/04_labels/forest_labels.tif \\
    --erosion_pixels 2
        """
    )
    
    parser.add_argument("--ref", required=True,
                       help="Raster S3 de referencia (define malla, CRS y transform)")
    parser.add_argument("--bosque_shp", required=True,
                       help="Shapefile S3 de polígonos de bosque")
    parser.add_argument("--perimetro_shp", required=False, default=None,
                       help="Shapefile S3 del perímetro de la finca (opcional)")
    parser.add_argument("--output", required=True,
                       help="Path S3 de salida del raster de etiquetas")
    parser.add_argument("--erosion_pixels", type=int, default=1,
                       help="Píxeles de erosión para el bosque (default=1)")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("GENERACIÓN DE RASTER DE ETIQUETAS")
    print("="*70)
    
    # Validar paths S3
    if not all(p.startswith('s3://') for p in [args.ref, args.bosque_shp, args.output]):
        print(f"\n❌ Error: Paths deben ser S3 (s3://...)")
        sys.exit(1)
    
    if args.perimetro_shp and not args.perimetro_shp.startswith('s3://'):
        print(f"\n❌ Error: Path de perímetro debe ser S3 (s3://...)")
        sys.exit(1)
    
    print(f"\n📂 Archivos de entrada:")
    print(f"   Raster referencia: {args.ref}")
    print(f"   Bosque shapefile: {args.bosque_shp}")
    if args.perimetro_shp:
        print(f"   Perímetro shapefile: {args.perimetro_shp}")
    else:
        print(f"   Perímetro: No especificado (se usará toda la malla)")
    print(f"   Erosión: {args.erosion_pixels} píxeles")
    
    # Inicializar S3 handler
    s3_handler = S3Handler()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # --- 1) Descargar y abrir raster de referencia
        print(f"\n🗺️  Descargando raster de referencia...")
        local_ref = os.path.join(tmpdir, "reference.tif")
        s3_handler.download_file(args.ref, local_ref)
        
        with rasterio.open(local_ref) as ref:
            ref_meta = ref.meta.copy()
            transform = ref.transform
            crs = ref.crs
            height, width = ref.height, ref.width
        
        print(f"   ✓ Dimensiones: {width} × {height} px")
        print(f"   ✓ CRS: {crs}")
        
        out_shape = (height, width)
        
        # --- 2) Descargar y cargar shapefiles
        print(f"\n📍 Descargando shapefiles...")
        
        local_bosque_shp = s3_handler.download_shapefile(args.bosque_shp, tmpdir)
        gdf_bos = gpd.read_file(local_bosque_shp)
        print(f"   ✓ Bosque: {len(gdf_bos)} polígonos (CRS: {gdf_bos.crs})")
        
        if args.perimetro_shp:
            local_per_shp = s3_handler.download_shapefile(args.perimetro_shp, tmpdir)
            gdf_per = gpd.read_file(local_per_shp)
            print(f"   ✓ Perímetro: {len(gdf_per)} polígonos (CRS: {gdf_per.crs})")
        else:
            gdf_per = None
            print(f"   ○ Perímetro: No especificado")
        
        # --- 3) Reproyectar a CRS del raster
        print(f"\n🔄 Reproyectando a CRS del raster...")
        gdf_bos = gdf_bos.to_crs(crs)
        if gdf_per is not None:
            gdf_per = gdf_per.to_crs(crs)
        print(f"   ✓ Reproyección completada")
        
        # --- 4) Unificar geometrías
        print(f"\n🔗 Unificando geometrías...")
        bosque_union = unary_union(gdf_bos.geometry)
        perimetro_union = unary_union(gdf_per.geometry) if gdf_per is not None else None
        print(f"   ✓ Bosque unificado: {bosque_union.geom_type}")
        if perimetro_union:
            print(f"   ✓ Perímetro unificado: {perimetro_union.geom_type}")
        
        # --- 5) Rasterizar bosque = 1
        print(f"\n🎨 Rasterizando bosque...")
        bosque_r = rasterize_geom(bosque_union, out_shape, transform, burn_value=1, dtype="uint8")
        n_bosque_pre = np.sum(bosque_r == 1)
        print(f"   ✓ Píxeles de bosque (pre-erosión): {n_bosque_pre:,} ({n_bosque_pre/(height*width)*100:.2f}%)")
        
        # --- 6) Aplicar erosión morfológica
        erosion_px = max(0, int(args.erosion_pixels))
        if erosion_px > 0:
            print(f"\n⚙️  Aplicando erosión morfológica ({erosion_px} píxeles)...")
            bosque_r = binary_erosion(bosque_r.astype(bool), iterations=erosion_px).astype(np.uint8)
            n_bosque_post = np.sum(bosque_r == 1)
            n_removed = n_bosque_pre - n_bosque_post
            print(f"   ✓ Píxeles de bosque (post-erosión): {n_bosque_post:,} ({n_bosque_post/(height*width)*100:.2f}%)")
            print(f"   ✓ Píxeles removidos: {n_removed:,} ({n_removed/n_bosque_pre*100:.1f}%)")
        else:
            print(f"\n○ Sin erosión (erosion_pixels=0)")
            n_bosque_post = n_bosque_pre
        
        # --- 7) Construir etiqueta final: -1 ignorar, 0 no-bosque, 1 bosque
        print(f"\n🏷️  Construyendo etiquetas finales...")
        label = np.full(out_shape, -1, dtype=np.int16)
        
        if perimetro_union is not None:
            # Rasterizar perímetro (1 dentro de la finca)
            per_r = rasterize_geom(perimetro_union, out_shape, transform, burn_value=1, dtype="uint8")
            n_perimetro = np.sum(per_r == 1)
            print(f"   ✓ Píxeles dentro del perímetro: {n_perimetro:,} ({n_perimetro/(height*width)*100:.2f}%)")
            
            # Por defecto, dentro del perímetro es NO-BOSQUE (0)
            label[per_r == 1] = 0
            # Donde hay bosque (erosionado), poner 1
            label[(per_r == 1) & (bosque_r == 1)] = 1
        else:
            # Sin perímetro: toda la malla es área válida
            label[:, :] = 0
            label[bosque_r == 1] = 1
            print(f"   ○ Sin perímetro: toda la malla es área válida")
        
        # --- 8) Estadísticas finales
        n_bosque = np.sum(label == 1)
        n_no_bosque = np.sum(label == 0)
        n_ignorar = np.sum(label == -1)
        total = height * width
        
        print(f"\n📊 Estadísticas de etiquetas:")
        print(f"   Bosque (1):      {n_bosque:,} píxeles ({n_bosque/total*100:.2f}%)")
        print(f"   No-Bosque (0):   {n_no_bosque:,} píxeles ({n_no_bosque/total*100:.2f}%)")
        print(f"   Ignorar (-1):    {n_ignorar:,} píxeles ({n_ignorar/total*100:.2f}%)")
        print(f"   Total:           {total:,} píxeles")
        
        if n_bosque > 0 and n_no_bosque > 0:
            ratio = n_no_bosque / n_bosque
            print(f"\n   Ratio No-Bosque/Bosque: {ratio:.2f}:1")
            if ratio > 10:
                print(f"   ⚠️  Advertencia: Desbalance significativo (ratio > 10:1)")
            elif ratio > 3:
                print(f"   ⚠️  Desbalance moderado (ratio > 3:1)")
            else:
                print(f"   ✓ Balance razonable de clases")
        
        # --- 9) Guardar raster localmente
        print(f"\n💾 Guardando raster de etiquetas...")
        local_output = os.path.join(tmpdir, "forest_labels.tif")
        
        out_meta = ref_meta.copy()
        out_meta.update(count=1, dtype="int16", nodata=-1)
        
        with rasterio.open(local_output, "w", **out_meta) as dst:
            dst.write(label, 1)
            dst.set_band_description(1, "label (1=bosque, 0=no-bosque, -1=ignorar)")
        
        # --- 10) Subir a S3
        s3_handler.upload_file(local_output, args.output)
        print(f"   ✓ Archivo guardado: {args.output}")
        print(f"   ✓ Formato: GeoTIFF int16, nodata=-1")
    
    # Resumen final
    print(f"\n" + "="*70)
    print("✅ RASTERIZACIÓN COMPLETADA")
    print("="*70)
    
    print(f"\nLeyenda del raster generado:")
    print(f"   1  = Bosque (positivo, erosionado {erosion_px}px)")
    print(f"   0  = No-Bosque (negativo, dentro del área válida)")
    print(f"  -1  = Ignorar (fuera del perímetro o sin datos)")
    
    print(f"\n📋 Siguiente paso:")
    print(f"   Unir features anuales + labels → 05_unir_features_labels.py")
    print()


if __name__ == "__main__":
    main()
