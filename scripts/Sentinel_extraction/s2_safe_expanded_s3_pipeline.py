#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sentinel-2 SAFE Downloader (Expanded, CDSE S3)
----------------------------------------------------
✅ Lee shapefiles (Perímetro.shp) desde S3 (tu bucket)
✅ Busca productos Sentinel-2 L2A (<10% nubes) vía Sentinel Hub
✅ Descarga carpetas .SAFE completas desde CDSE S3 (sin compresión)
✅ Usa Sentinel Hub para el catálogo, y S3 (eodata) para datos brutos
✅ Sube estructura expandida a tu S3 en: raw/raw_copernicus/<finca>/<fecha>/<producto>.SAFE/
"""

import os
import asyncio
import geopandas as gpd
import boto3
import tempfile
import shutil
from datetime import datetime
from tqdm import tqdm

from sentinelhub import (
    SHConfig,
    DataCollection,
    SentinelHubCatalog,
    CRS,
    Geometry,
)

# ==============================
# ⚙️ CONFIGURACIÓN DEL USUARIO
# ==============================
# Tu bucket (AWS) donde están los shapes y donde quieres guardar las SAFE
BUCKET = "mineria-project"
S3_INPUT_PREFIX = "raw/shapes"
S3_OUTPUT_PREFIX = "raw/raw_copernicus"

START_DATE = "2017-03-28"
END_DATE = "2025-11-09"
MAX_CONCURRENT_DOWNLOADS = 2

# Credenciales Sentinel Hub (para catálogo / process, etc.)
CLIENT_ID = os.environ.get("SENTINEL_HUB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SENTINEL_HUB_CLIENT_SECRET")

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

# ==============================
# 🌐 CONFIG S3 EODATA (CDSE)
# ==============================
# Endpoint y bucket donde están los productos Sentinel-2 en CDSE
EODATA_ENDPOINT = "https://eodata.dataspace.copernicus.eu"
EODATA_BUCKET = "eodata"

# Credenciales S3 de CDSE (genera en la página "S3 Access" y guárdalas como variables de entorno)
EODATA_ACCESS_KEY = os.environ.get("CDSE_EODATA_ACCESS_KEY")
EODATA_SECRET_KEY = os.environ.get("CDSE_EODATA_SECRET_KEY")

if not EODATA_ACCESS_KEY or not EODATA_SECRET_KEY:
    raise RuntimeError(
        "Faltan las variables de entorno CDSE_EODATA_ACCESS_KEY / CDSE_EODATA_SECRET_KEY "
        "con las credenciales S3 de Copernicus Data Space."
    )

# ==============================
# 🧠 CONFIG SENTINEL HUB
# ==============================
config = SHConfig()
config.sh_client_id = CLIENT_ID
config.sh_client_secret = CLIENT_SECRET
config.sh_base_url = "https://sh.dataspace.copernicus.eu"
config.sh_token_url = TOKEN_URL


# ==============================
# 🔍 FUNCIÓN PARA BUSCAR ESCENAS
# ==============================
def search_scenes(geom):
    """Consulta catálogo Sentinel Hub para obtener escenas de Sentinel-2 L2A."""
    catalog = SentinelHubCatalog(config=config)
    search_iterator = catalog.search(
        DataCollection.SENTINEL2_L2A,
        bbox=geom.bbox,
        time=(START_DATE, END_DATE),
        filter="eo:cloud_cover < 10",
        fields={
            "include": ["id", "properties.datetime", "assets", "links"],
            "exclude": []
        },
    )
    scenes = list(search_iterator)
    print(f"🛰️ Se encontraron {len(scenes)} escenas con links y metadatos disponibles.")
    return scenes


# ==============================
# 🧱 UTILIDAD: PREFIJO S3 EN EODATA
# ==============================
def build_eodata_prefix(scene):
    """
    Construye el prefijo S3 en eodata para un producto S2 L2A a partir del STAC item de Sentinel Hub.

    Estructura en CDSE S3:
    s3://eodata/Sentinel-2/MSI/L2A/YYYY/MM/DD/<product_id>.SAFE/
    """
    product_id = scene["id"]
    if not product_id.endswith(".SAFE"):
        product_id = product_id + ".SAFE"

    dt_str = scene["properties"]["datetime"]
    # Normalmente es algo como "2023-02-19T15:17:01Z"
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    year = dt.year
    month = f"{dt.month:02d}"
    day = f"{dt.day:02d}"

    prefix = f"Sentinel-2/MSI/L2A/{year:04d}/{month}/{day}/{product_id}/"
    return product_id, prefix


# ==============================
# 📥 DESCARGAR SAFE DESDE EODATA S3
# ==============================
def download_safe_from_eodata(eodata_bucket, safe_name, s3_prefix, local_root):
    """
    Descarga recursivamente todos los objetos bajo s3_prefix desde eodata
    y los coloca en local_root/<safe_name>/...
    Si no se encuentra coincidencia exacta, busca por startswith dentro del mismo día.
    """
    print(f"⬇️ Buscando objetos en eodata con prefijo '{s3_prefix}'...")
    objects = list(eodata_bucket.objects.filter(Prefix=s3_prefix))

    # Si no encontró objetos exactos, intenta buscar versiones parecidas
    if not objects:
        # Buscar por el mismo día (recorta la ruta hasta YYYY/MM/DD)
        parent_prefix = "/".join(s3_prefix.rstrip("/").split("/")[:-1]) + "/"
        print(f"🔎 No se encontró coincidencia exacta. Buscando alternativas en: {parent_prefix}")

        # Buscar todos los productos del mismo día
        all_objs = list(eodata_bucket.objects.filter(Prefix=parent_prefix))
        candidates = sorted(
            set("/".join(obj.key.split("/")[:8]) for obj in all_objs if obj.key.endswith(".SAFE/"))
        )

        if not candidates:
            raise FileNotFoundError(f"No se encontraron objetos similares en {parent_prefix}")

        print("🔁 Coincidencias encontradas:")
        for c in candidates:
            print("  -", c)

        # Usa la primera coincidencia que empiece con el mismo ID base
        base_id = safe_name.split("_20")[0]  # corta antes del timestamp de reprocesamiento
        match = next((c for c in candidates if base_id in c), None)

        if not match:
            raise FileNotFoundError(f"No se encontró producto similar a {safe_name} en {parent_prefix}")

        print(f"✅ Usando coincidencia más cercana: {match}")
        s3_prefix = match

        # Volver a listar objetos bajo el nuevo prefijo
        objects = list(eodata_bucket.objects.filter(Prefix=s3_prefix))

    safe_folder = os.path.join(local_root, safe_name)
    os.makedirs(safe_folder, exist_ok=True)

    for obj in objects:
        key = obj.key
        if key.endswith("/"):
            continue
        rel_path = os.path.relpath(key, s3_prefix)
        local_path = os.path.join(safe_folder, rel_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        eodata_bucket.download_file(key, local_path)

    print(f"✅ Descargada carpeta SAFE desde eodata: {safe_name}")
    return safe_folder

# ==============================
# ⚡ DESCARGA + UPLOAD SAFE
# ==============================
async def download_and_upload_safe(scene, tmpdir, sem, s3_client_aws, farm_prefix, eodata_bucket):
    async with sem:
        product_id = scene["id"]
        iso_date = scene["properties"]["datetime"][:10]  # YYYY-MM-DD para la ruta en tu bucket
        safe_name, eodata_prefix = build_eodata_prefix(scene)

        print(f"\n📦 Procesando producto {product_id} ({iso_date})")
        # Descarga SAFE desde eodata (bloqueante, pero encapsulado aquí)
        try:
            safe_folder = download_safe_from_eodata(
                eodata_bucket=eodata_bucket,
                safe_name=safe_name,
                s3_prefix=eodata_prefix,
                local_root=tmpdir,
            )
        except FileNotFoundError as e:
            print(f"⚠️ {e}")
            return
        except Exception as e:
            print(f"❌ Error descargando desde eodata para {product_id}: {e}")
            return

        # Subir a tu S3 (mineria-project) preservando estructura
        product_name = os.path.basename(safe_folder.rstrip("/"))
        s3_prefix_out = f"{S3_OUTPUT_PREFIX}/{farm_prefix}/{iso_date}/{product_name}/"
        print(f"☁️ Subiendo {product_name} a s3://{BUCKET}/{s3_prefix_out}")

        for root, _, files in os.walk(safe_folder):
            for file in files:
                local_path = os.path.join(root, file)
                rel_path = os.path.relpath(local_path, safe_folder)
                s3_key = s3_prefix_out + rel_path.replace("\\", "/")
                s3_client_aws.upload_file(local_path, BUCKET, s3_key)

        print(f"✅ Subido completo: {product_name}")

        # Limpieza local (el tmpdir se borra entero después)
        shutil.rmtree(safe_folder, ignore_errors=True)


# ==============================
# 🧭 PROCESAR CADA FINCA
# ==============================
async def process_farm(s3_client_aws, farm_prefix, eodata_bucket):
    print(f"\n🏡 Procesando finca: {farm_prefix}")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Descargar shapefile desde tu S3
        local_shp = os.path.join(tmpdir, "Perímetro.shp")
        base_key = f"{S3_INPUT_PREFIX}/{farm_prefix}/Perímetro"

        for ext in ["shp", "shx", "dbf", "prj"]:
            key = f"{base_key}.{ext}"
            local_path = os.path.join(tmpdir, f"Perímetro.{ext}")
            s3_client_aws.download_file(BUCKET, key, local_path)

        # Leer shapefile y reproyectar
        gdf = gpd.read_file(local_shp)
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        else:
            gdf = gdf.to_crs("EPSG:4326")

        print(f"🌍 {farm_prefix}: reproyectando a EPSG:4326")

        geom = Geometry(geometry=gdf.geometry.iloc[0].__geo_interface__, crs=CRS.WGS84)
        scenes = search_scenes(geom)
        print(f"✅ {len(scenes)} productos encontrados para {farm_prefix}")

        sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

        tasks = [
            download_and_upload_safe(scene, tmpdir, sem, s3_client_aws, farm_prefix, eodata_bucket)
            for scene in scenes
        ]
        for t in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"📦 {farm_prefix}"):
            await t


# ==============================
# 🚀 MAIN
# ==============================
async def main():
    # Cliente S3 para tu bucket (mineria-project en AWS u otro proveedor compatible)
    s3_client_aws = boto3.client("s3")

    # Recurso S3 para eodata (CDSE)
    eodata_session = boto3.session.Session()
    eodata_s3 = eodata_session.resource(
        "s3",
        endpoint_url=EODATA_ENDPOINT,
        aws_access_key_id=EODATA_ACCESS_KEY,
        aws_secret_access_key=EODATA_SECRET_KEY,
        region_name="default",
    )
    eodata_bucket = eodata_s3.Bucket(EODATA_BUCKET)

    # Listar fincas
    response = s3_client_aws.list_objects_v2(
        Bucket=BUCKET,
        Prefix=S3_INPUT_PREFIX + "/",
        Delimiter="/"
    )
    farms = [prefix["Prefix"].split("/")[-2] for prefix in response.get("CommonPrefixes", [])]
    print(f"🌎 {len(farms)} fincas encontradas: {farms}")

    # Por ahora solo primeras 2 fincas, como tenías
    for farm in farms[:]:
        await process_farm(s3_client_aws, farm, eodata_bucket)

    print("\n🎯 Proceso completo — Productos SAFE expandidos cargados a S3 ✅")


if __name__ == "__main__":
    asyncio.run(main())