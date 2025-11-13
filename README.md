# 🌳 Proyecto Minería de Datos - Detección de Deforestación con ML

Pipeline completo de procesamiento de imágenes Sentinel-2 y clasificación de cobertura forestal usando Machine Learning.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![Scikit-learn](https://img.shields.io/badge/Scikit--learn-1.3-orange.svg)](https://scikit-learn.org)
[![AWS](https://img.shields.io/badge/AWS-S3-yellow.svg)](https://aws.amazon.com/s3)
[![Status](https://img.shields.io/badge/Status-Production-green.svg)]()

---

## 🎯 Resultados Principales

### ✅ Modelo Entrenado Exitosamente

**Random Forest Classifier** - Detección de Deforestación

| Métrica | Valor | Descripción |
|---------|-------|-------------|
| **Accuracy** | **90.35%** | Tasa de acierto general |
| **Precision** | 72.89% | De cada 100 predicciones de "bosque", 73 son correctas |
| **Recall** | **91.58%** | Detecta 9 de cada 10 áreas boscosas |
| **F1-Score** | 81.17% | Balance entre precision y recall |
| **ROC AUC** | **96.16%** | Excelente capacidad de discriminación |
| **PR AUC** | **85.42%** | Muy bueno para clases desbalanceadas |

📊 **[Ver Reporte Completo](docs/RESULTADOS_ENTRENAMIENTO.md)**

### 📁 Dataset

- **Total**: 8,008 muestras de 5 zonas
- **Distribución**: 77.3% no-bosque, 22.7% bosque
- **Split**: 70% train / 15% val / 15% test
- **Features**: 15 características (bandas espectrales + índices de vegetación)

### 🔝 Features Más Importantes

1. **B03_med** (Verde) - 18.90%
2. **NDVI_range** (Variabilidad) - 11.67%
3. **B11_med** (SWIR) - 9.99%

---

## �️ Arquitectura del Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     PIPELINE MINERÍA                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  📦 Procesamiento de Datos (Scripts 01-05)                      │
│  ├─ 01_procesar_sentinel_clip.py → Procesar y recortar SAFE    │
│  ├─ 02_generar_mascaras.py       → Máscaras de calidad         │
│  ├─ 03_tabular_features.py       → Features tabulares          │
│  ├─ 04_rasterizar_labels.py      → Rasterizar labels           │
│  └─ 05_unir_features_labels.py   → Dataset de entrenamiento    │
│                                                                  │
│  🤖 Machine Learning (Script 06)                                │
│  └─ 06_entrenar_rapido.py        → Random Forest Training      │
│                                                                  │
│  💾 S3 Bucket (Almacenamiento)                                  │
│  └─ s3://mineria-project/                                       │
│     ├─ raw/                      → Datos originales             │
│     ├─ staging/                  → Datos procesados             │
│     ├─ data/all/                 → Dataset de entrenamiento     │
│     ├─ models/                   → Modelos entrenados          │
│     └─ results/                  → Métricas y reportes          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Estado Actual del Proyecto

### ✅ Pipeline Completo Ejecutado

**Script 01 - Procesamiento Sentinel-2:**
- ✅ Procesamiento de imágenes SAFE con bandas de 20m (B02-B07, B8A, B11, B12)
- ✅ Recorte automático con shapefiles por zona
- ✅ Corrección automática de CRS corrupto
- ✅ **5 zonas procesadas exitosamente**

**Scripts 02-05 - Preparación de Datos:**
- ✅ Generación de máscaras de calidad
- ✅ Extracción de features tabulares (bandas + NDVI)
- ✅ Rasterización de labels
- ✅ Unión de features con labels
- ✅ **Dataset final: 8,008 muestras**

**Script 06 - Entrenamiento:**
- ✅ Random Forest con grid search
- ✅ Validación con split 70/15/15
- ✅ Selección de mejor modelo basado en PR AUC
- ✅ **Modelo en producción con 90.35% accuracy**

**Resultados Guardados en S3:**
- ✅ `s3://mineria-project/models/random_forest_model.pkl` (1.9 MB)
- ✅ `s3://mineria-project/results/training_summary.json`
- ✅ `s3://mineria-project/results/feature_importance.csv`
- ✅ `s3://mineria-project/results/RESULTADOS_ENTRENAMIENTO.md`

---

## 🚀 Uso

### 1. Clonar el Repositorio

```bash
git clone https://github.com/maraosoc/mineria_project.git
cd mineria_project
```

### 2. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 3. Ejecutar Pipeline Completo

#### Opción A: Usando el Modelo Pre-entrenado

```bash
# Descargar el modelo desde S3
aws s3 cp s3://mineria-project/models/random_forest_model.pkl ./models/

# Aplicar predicciones a nuevas zonas (Script 07)
python scripts/07_evaluar_modelos.py \
  --model_path ./models/random_forest_model.pkl \
  --input_data s3://mineria-project/data/new_zone/features.parquet \
  --output s3://mineria-project/results/new_zone/
```

#### Opción B: Entrenar un Nuevo Modelo

```bash
# 1. Procesar imágenes Sentinel-2
python scripts/01_procesar_sentinel_clip.py \
  --input s3://mineria-project/raw/raw_copernicus/<ZONE>/ \
  --output s3://mineria-project/staging/01_rasters_procesados_clipped/ \
  --zone_name "<ZONE_NAME>" \
  --shape_path "s3://mineria-project/raw/shapes/<ZONE>/Perímetro" \
  --clip

# 2. Generar máscaras de calidad
python scripts/02_generar_mascaras.py \
  --input s3://mineria-project/staging/01_rasters_procesados_clipped/<ZONE>/ \
  --output s3://mineria-project/staging/02_mascaras/<ZONE>/

# 3. Extraer features tabulares
python scripts/03_tabular_features.py \
  --rasters s3://mineria-project/staging/01_rasters_procesados_clipped/<ZONE>/ \
  --output s3://mineria-project/staging/03_features/<ZONE>/

# 4. Rasterizar labels
python scripts/04_rasterizar_labels.py \
  --shapes s3://mineria-project/raw/shapes/<ZONE>/labels/ \
  --reference s3://mineria-project/staging/01_rasters_procesados_clipped/<ZONE>/ \
  --output s3://mineria-project/staging/04_labels/<ZONE>/

# 5. Unir features con labels
python scripts/05_unir_features_labels.py \
  --features s3://mineria-project/staging/03_features/<ZONE>/ \
  --labels s3://mineria-project/staging/04_labels/<ZONE>/ \
  --output s3://mineria-project/data/<ZONE>/training_data.parquet

# 6. Entrenar modelo
python scripts/06_entrenar_rapido.py \
  --input s3://mineria-project/data/<ZONE>/training_data.parquet \
  --output ./models/new_model/
```

### 4. Verificar Resultados

```bash
# Ver métricas del modelo
cat models/training_summary.json

# Ver features más importantes
cat models/feature_importance.csv

# Listar archivos en S3
aws s3 ls s3://mineria-project/results/ --recursive
aws s3 ls s3://mineria-project/models/ --recursive
```

### 5. Descargar Resultados

```bash
# Descargar todos los resultados
aws s3 sync s3://mineria-project/results/ ./local_results/
aws s3 sync s3://mineria-project/models/ ./local_models/

# Ver reporte completo
cat local_results/RESULTADOS_ENTRENAMIENTO.md
```

---

## 📁 Estructura del Proyecto

```
mineria_project/
├── config/                          # Configuraciones
│   ├── aws_config.yaml
│   └── pipeline_config.yaml
├── docs/                            # Documentación
│   ├── AWS_SETUP.md
│   └── RESULTADOS_ENTRENAMIENTO.md  # ⭐ Reporte completo
├── infrastructure/                  # Infraestructura como código (Terraform)
│   ├── backend.tf
│   ├── main.tf
│   ├── s3.tf
│   └── variables.tf
├── scripts/                         # Pipeline de procesamiento
│   ├── 01_procesar_sentinel.py      # Procesamiento Sentinel-2 ✅
│   ├── 02_generar_mascaras.py       # Máscaras de calidad ✅
│   ├── 03_tabular_features.py       # Extracción features ✅
│   ├── 04_rasterizar_labels.py      # Rasterización labels ✅
│   ├── 05_unir_features_labels.py   # Dataset final ✅
│   ├── 06_entrenar_rapido.py        # Entrenamiento Random Forest ✅
│   └── 07_evaluar_modelos.py        # Evaluación y predicción
├── requirements.txt                 # Dependencias Python
└── README.md                        # Este archivo
```

---

## 🔧 Configuración

### Requisitos del Sistema

```bash
# Python 3.11+
python --version

# Instalar dependencias
pip install -r requirements.txt

# Principales dependencias:
# - scikit-learn >= 1.3.0
# - pandas >= 2.0.0
# - numpy >= 1.24.0
# - rasterio >= 1.3.0
# - geopandas >= 0.13.0
```

### Configuración de AWS

```bash
# Configurar credenciales AWS
aws configure

# Verificar acceso al bucket S3
aws s3 ls s3://mineria-project/
```

### Variables de Terraform (Opcional)

Si deseas desplegar la infraestructura en AWS:

```hcl
# terraform.tfvars
project_name = "mineria"
environment  = "dev"
aws_region   = "us-east-1"
s3_bucket_name = "mineria-project"
```

---

## � Dataset

### Características

- **Total de muestras:** 8,008 píxeles etiquetados
- **Features:** 15 características espectrales y texturales
  - Bandas Sentinel-2: B02, B03, B04, B08, B11, B12 (mediana y desviación estándar)
  - NDVI: mínimo, máximo y rango
- **Classes:** Binario (bosque / no bosque)
  - No bosque: 6,188 muestras (77.3%)
  - Bosque: 1,820 muestras (22.7%)
- **División:** Train 70% / Val 15% / Test 15% (estratificado)
- **Zonas:** 5 regiones de Colombia con diferentes ecosistemas

### Features Más Importantes

| Feature | Importancia | Descripción |
|---------|-------------|-------------|
| B03_med | 18.90% | Banda verde (vegetación) |
| NDVI_range | 11.67% | Rango de NDVI (variabilidad) |
| B11_med | 9.99% | Infrarrojo de onda corta |
| B08_med | 9.81% | Infrarrojo cercano |
| NDVI_max | 8.16% | NDVI máximo |

---

## 🎯 Reproducibilidad

### Ejecutar el Pipeline Completo

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/mineria_project.git
cd mineria_project

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar AWS
aws configure
# Ingresar: Access Key, Secret Key, Region (us-east-1)

# 4. Ejecutar pipeline completo
python scripts/01_procesar_sentinel.py
python scripts/02_generar_mascaras.py
python scripts/03_tabular_features.py
python scripts/04_rasterizar_labels.py
python scripts/05_unir_features_labels.py
python scripts/06_entrenar_rapido.py

# 5. Verificar resultados en S3
aws s3 ls s3://mineria-project/models/
aws s3 ls s3://mineria-project/results/
```

### Tiempo de Ejecución Estimado

| Script | Duración | Hardware Recomendado |
|--------|----------|---------------------|
| Script 01 | ~30 min | 8+ cores, 16GB RAM |
| Script 02 | ~10 min | 4+ cores, 8GB RAM |
| Script 03 | ~15 min | 4+ cores, 8GB RAM |
| Script 04 | ~5 min | 4+ cores, 8GB RAM |
| Script 05 | ~2 min | 2+ cores, 4GB RAM |
| Script 06 | ~1 min | 4+ cores, 8GB RAM |
| **Total** | **~1 hora** | |

---

## 📖 Documentación Adicional

- **[docs/RESULTADOS_ENTRENAMIENTO.md](docs/RESULTADOS_ENTRENAMIENTO.md)**: Reporte completo con análisis de features, matriz de confusión y recomendaciones
- **[docs/AWS_SETUP.md](docs/AWS_SETUP.md)**: Guía detallada para configurar infraestructura AWS

---

## 🤝 Contribución

Este es un proyecto de investigación académica. Si tienes sugerencias o encuentras problemas:

1. Abre un **Issue** describiendo el problema
2. Si tienes una solución, crea un **Pull Request**
3. Para consultas académicas, contacta al equipo del proyecto

---

## 📄 Licencia

Ver archivo [LICENSE](LICENSE) para más detalles.

---

## � Contacto

Para consultas sobre el proyecto, metodología o colaboraciones, contactar al equipo de investigación.

---

**Última actualización:** Diciembre 2024  
**Estado:** ✅ Pipeline completo - Modelo en producción

