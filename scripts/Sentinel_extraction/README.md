# 🧭 Guía de ejecución — `s2_safe_expanded_s3_pipeline.py`

## 🛰️ Descripción general

Este script automatiza el proceso de:

1. Leer los **polígonos (shapefiles)** de tus fincas almacenados en S3 (`raw/shapes`).
2. Buscar productos **Sentinel-2 L2A** con menos del 10 % de nubes en **Sentinel Hub**.
3. Descargar las carpetas `.SAFE` completas desde el bucket público `eodata` del **Copernicus Data Space Ecosystem (CDSE)**.
4. Subir esas carpetas **sin comprimir** a tu bucket S3 (`raw/raw_copernicus/<finca>/<fecha>/<producto>.SAFE`).

---

## 📦 1. Requisitos previos

Antes de ejecutar el script, asegúrate de tener:

### 🧰 a) Software instalado

- **Python 3.10 o superior**
- **pip** actualizado (`python -m pip install --upgrade pip`)
- Las siguientes librerías instaladas:

```bash
pip install geopandas boto3 sentinelhub tqdm
```

> 💡 *Si usas un entorno virtual (recomendado), crea uno antes:*
> ```bash
> python -m venv .venv
> source .venv/bin/activate  # Linux/Mac
> .venv\Scripts\activate     # Windows
> ```

---

## 🔐 2. Configuración de credenciales

El script necesita **dos grupos de credenciales**:  
1️⃣ para **Sentinel Hub y CDSE (Copernicus)**  
2️⃣ para tu **AWS (S3 de destino)**

Guárdalas de forma segura como variables de entorno o en un archivo privado.

---

### 🧩 A. Credenciales Sentinel Hub / Copernicus Data Space

#### 1. **CLIENT_ID y CLIENT_SECRET**
Son tus credenciales de **Sentinel Hub / CDSE API**.

**Dónde obtenerlas:**
- Inicia sesión en [https://dataspace.copernicus.eu](https://dataspace.copernicus.eu)
- Ve a:  
  **Dashboard → User settings → Applications → New Application**
- Crea una aplicación y copia:
  - `Client ID`
  - `Client Secret`

**Cómo guardarlas (seguro):**

Linux / Mac:
```bash
export SH_CLIENT_ID="tu_client_id"
export SH_CLIENT_SECRET="tu_client_secret"
```

Windows PowerShell:
```bash
setx SH_CLIENT_ID "tu_client_id"
setx SH_CLIENT_SECRET "tu_client_secret"
```

---

#### 2. **EODATA_ACCESS_KEY y EODATA_SECRET_KEY**
Estas son tus credenciales de acceso **S3** para el bucket `eodata` de Copernicus.

**Dónde obtenerlas:**
1. Inicia sesión en [https://dataspace.copernicus.eu](https://dataspace.copernicus.eu)
2. En tu panel de usuario, entra a:  
   **“S3 Access” → “Generate access credentials”**
3. Copia los valores:
   - **Access Key**
   - **Secret Key**

**Cómo guardarlas:**

Linux / Mac:
```bash
export CDSE_EODATA_ACCESS_KEY="tu_access_key"
export CDSE_EODATA_SECRET_KEY="tu_secret_key"
```

Windows PowerShell:
```bash
setx CDSE_EODATA_ACCESS_KEY "tu_access_key"
setx CDSE_EODATA_SECRET_KEY "tu_secret_key"
```

---

### 🧩 B. Credenciales de tu bucket AWS S3 (destino)

**Dónde obtenerlas:**
- Inicia sesión en la **AWS Console** →  
  **IAM → Users → <tu usuario> → Security Credentials → Create access key**

**Cómo guardarlas:**

Linux / Mac:
```bash
export AWS_ACCESS_KEY_ID="tu_aws_key"
export AWS_SECRET_ACCESS_KEY="tu_aws_secret"
export AWS_DEFAULT_REGION="us-east-1"
```

Windows PowerShell:
```bash
setx AWS_ACCESS_KEY_ID "tu_aws_key"
setx AWS_SECRET_ACCESS_KEY "tu_aws_secret"
setx AWS_DEFAULT_REGION "us-east-1"
```

> 🔒 **Recomendación:** nunca incluyas tus claves directamente en el código.  
> Guárdalas en variables de entorno o en un archivo `.env` que esté **excluido** de tu repositorio (`.gitignore`).

---

### ✅ Alternativa con archivo `.env`

```bash
SH_CLIENT_ID=tu_client_id
SH_CLIENT_SECRET=tu_client_secret
CDSE_EODATA_ACCESS_KEY=tu_access_key
CDSE_EODATA_SECRET_KEY=tu_secret_key
AWS_ACCESS_KEY_ID=tu_aws_key
AWS_SECRET_ACCESS_KEY=tu_aws_secret
AWS_DEFAULT_REGION=us-east-1
```

Y luego en el script (opcionalmente):
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 📁 3. Estructura esperada en tu bucket S3

```
mineria-project/
└── raw/
    ├── shapes/
    │   ├── 21_LaPalmera_Granada_Cundinamarca/
    │   │   ├── Perímetro.shp
    │   │   ├── Perímetro.dbf
    │   │   ├── Perímetro.shx
    │   │   └── Perímetro.prj
    │   ├── 14_ElDanubio_Granada_Meta/
    │   │   ├── Perímetro.shp
    │   │   ├── ...
    │   └── ...
    └── raw_copernicus/
        (vacío al inicio)
```

Cada carpeta dentro de `raw/shapes/` representa una finca.

---

## ⚙️ 4. Ejecución del script

Ejecuta desde el directorio donde está guardado el archivo:

```bash
python s2_safe_expanded_s3_pipeline.py
```

Para registrar logs:
```bash
python s2_safe_expanded_s3_pipeline.py | tee logs/s2_pipeline_$(date +%F).log
```

---

## 🧩 5. Qué hace el script paso a paso

1. Carga las credenciales.
2. Lista las fincas en `raw/shapes`.
3. Para cada finca:
   - Descarga el shapefile temporalmente.
   - Busca escenas Sentinel-2 L2A (<10 % nubes).
   - Descarga cada carpeta `.SAFE` completa desde `eodata`.
   - La sube a tu bucket S3 (`raw/raw_copernicus/<finca>/<fecha>/<producto>.SAFE/`).
4. Limpia los archivos temporales.
5. Muestra progreso con `tqdm`.

---

## 🧠 6. Personalización de parámetros

| Parámetro | Descripción | Ejemplo |
|------------|-------------|----------|
| `START_DATE` | Fecha inicial de búsqueda | `"2020-01-01"` |
| `END_DATE` | Fecha final de búsqueda | `"2025-12-31"` |
| `MAX_CONCURRENT_DOWNLOADS` | Nº máximo de descargas simultáneas | `2` |
| `S3_INPUT_PREFIX` | Carpeta de entrada (shapes) | `"raw/shapes"` |
| `S3_OUTPUT_PREFIX` | Carpeta de salida (SAFE) | `"raw/raw_copernicus"` |

---

## 📋 7. Recomendaciones prácticas

- ✅ Procesa finca por finca si el ancho de banda es limitado.
  ```python
  for farm in farms[3:4]:
  ```

- 🕒 Cada descarga puede tardar entre 5 y 30 min (~1–6 GB).

- 💾 Asegúrate de tener al menos **10 GB libres** en disco temporal.

- ☁️ Nunca subas este script con claves visibles.

---

## 🧹 8. Verificación de resultados

```
raw/raw_copernicus/
└── 21_LaPalmera_Granada_Cundinamarca/
    ├── 2023-05-19/
    │   └── S2A_MSIL2A_20230519T152731_N0509_R068_T18NUM_20230519T175514.SAFE/
    │       ├── GRANULE/
    │       ├── AUX_DATA/
    │       ├── HTML/
    │       └── manifest.safe
```

---

## 🔍 9. Solución de problemas comunes

| Problema | Causa | Solución |
|-----------|--------|-----------|
| `Faltan las variables de entorno CDSE_EODATA_ACCESS_KEY / CDSE_EODATA_SECRET_KEY` | No configuraste las claves del CDSE | Usa `export` o `.env` correctamente |
| `botocore.exceptions.NoCredentialsError` | AWS sin credenciales válidas | Configura `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY` |
| `No se encontró producto similar en eodata` | El producto ya no existe o el ID cambió | Intenta con otra fecha o ajusta la búsqueda |
| `MemoryError` o disco lleno | Descarga temporal muy grande | Reduce `MAX_CONCURRENT_DOWNLOADS` o cambia ruta de `tempfile` |

---

## ✅ 10. Ejemplo de ejecución completa

```bash
$ python s2_safe_expanded_s3_pipeline.py
🌎 3 fincas encontradas: ['21_LaPalmera_Granada_Cundinamarca', '14_ElDanubio_Granada_Meta', '05_SanMiguel']
🏡 Procesando finca: 21_LaPalmera_Granada_Cundinamarca
🌍 21_LaPalmera_Granada_Cundinamarca: reproyectando a EPSG:4326
🛰️ Se encontraron 5 escenas con links y metadatos disponibles.
📦 21_LaPalmera_Granada_Cundinamarca: 100%|█████████████████| 5/5
🎯 Proceso completo — Productos SAFE expandidos cargados a S3 ✅
```
