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
│   ├── EMR_TRAINING.md
│   ├── QUICK_REFERENCE.md
│   ├── TRAINING_IMPROVEMENTS.md
│   └── RESULTADOS_ENTRENAMIENTO.md  # ⭐ Reporte completo
├── infrastructure/                  # Infraestructura como código
│   ├── backend.tf
│   ├── main.tf
│   ├── s3.tf
│   ├── variables.tf
│   ├── terraform.tfvars
│   └── modules/
│       ├── ec2/                     # Módulo EC2
│       └── emr/                     # Módulo EMR
├── scripts/                         # Scripts de procesamiento
│   ├── 01_procesar_sentinel_clip.py # Procesamiento Sentinel-2 ✅
│   ├── 02_generar_mascaras.py       # Máscaras de calidad ✅
│   ├── 03_tabular_features.py       # Features tabulares ✅
│   ├── 04_rasterizar_labels.py      # Rasterización de labels ✅
│   ├── 05_unir_features_labels.py   # Unión de datos ✅
│   ├── 06_entrenar_rapido.py        # Entrenamiento rápido ✅
│   ├── 07_evaluar_modelos.py        # Evaluación de modelos
│   ├── process_all_zones_parallel.py # Orquestador paralelo ✅
│   ├── submit_emr_steps.py          # Submitter de EMR
│   ├── bootstrap/                   # Scripts de bootstrap EMR
│   └── orchestration/               # Scripts de orquestación
│       ├── run_ec2_pipeline.py
│       └── run_emr_pipeline.py
├── requirements.txt                 # Dependencias Python
└── README.md                        # Este archivo
```

---

## 🔧 Configuración

### Variables de Terraform (`terraform.tfvars`)

```hcl
# General
project_name = "mineria"
environment  = "dev"
aws_region   = "us-east-1"

# EC2
ec2_instance_type = "c5.4xlarge"  # 16 vCPUs, 32GB RAM
ec2_volume_size   = 100           # GB

# S3
s3_bucket_name = "mineria-project"

# Networking
allowed_ssh_cidr = ["0.0.0.0/0"]  # ⚠️ Cambiar en producción
```

### Zonas Procesadas

Las 15 zonas procesadas actualmente:

1. 14_ElDanubio_Granada_Meta
2. 21_LaPalmera_Granada_Cundinamarca
3. 28_Montebello_Barrancabermeja_Santander
4. 29_Cuiva_SantaRosadeOsos_Antioquia
5. 32_LosNaranjos_Venecia_Antioquia
6. 35_Bellavista_Albán_Cundinamarca
7. 41_Cárpatos_LaUnión_Antioquia
8. 42_VillaLuzA_Unguía_Chocó
9. 44_SantaRosa_SanLuisdeGaceno_Boyacá
10. 54_LaAlameda_Prado_Tolima
11. 55_ElEdén_SantaRosadeOsos_Antioquia
12. 59_SanGabriel_Belmira_Antioquia
13. 69_Guabineros_Zarzal_ValledelCauca
14. 72_ElPorro_PuebloNuevo_Córdoba
15. 79_SanJerónimo_Pore_Casanare

---

## 🐛 Problemas Conocidos y Soluciones

### 1. CRS Corrupto en Archivos SAFE

**Problema:** 30-50% de archivos Sentinel-2 tienen CRS incorrecto en metadatos.

**Solución Implementada:**
- Detección automática de tile code (e.g., `T18N`) mediante regex
- Corrección de CRS basada en el tile code
- Logging de archivos corruptos a S3

### 2. AWS CLI Roto en Ubuntu 22.04

**Problema:** `KeyError: 'opsworkscm'` en comandos `aws s3`.

**Solución:**
- Usar `boto3` directamente en Python en lugar de AWS CLI
- Scripts incluyen workaround automático

### 3. Shapefiles en CTM_12 (EPSG:3116)

**Problema:** Shapefiles de zonas están en proyección diferente a Sentinel-2.

**Solución:**
- Reproyección automática en script 01
- Validación de bounds geográficos para Colombia

---

## 📊 Resultados del Script 01

### Resumen de Ejecución

```
Duración total: 18.0 minutos
Zonas procesadas: 15/15 (100%)
Workers paralelos: 8
Instancia: c5.4xlarge (16 vCPUs, 32GB RAM)

Resultados por zona:
  ✅ 14_ElDanubio_Granada_Meta: 18.0 min
  ✅ 21_LaPalmera_Granada_Cundinamarca: 3.1 min
  ✅ 28_Montebello_Barrancabermeja_Santander: 2.9 min
  ✅ 29_Cuiva_SantaRosadeOsos_Antioquia: 15.8 min
  ✅ 32_LosNaranjos_Venecia_Antioquia: 14.5 min
  ✅ 35_Bellavista_Albán_Cundinamarca: 3.1 min
  ✅ 41_Cárpatos_LaUnión_Antioquia: 4.8 min
  ✅ 42_VillaLuzA_Unguía_Chocó: 0.5 min
  ✅ 44_SantaRosa_SanLuisdeGaceno_Boyacá: 14.7 min
  ✅ 54_LaAlameda_Prado_Tolima: 11.3 min
  ✅ 55_ElEdén_SantaRosadeOsos_Antioquia: 10.2 min
  ✅ 59_SanGabriel_Belmira_Antioquia: 4.1 min
  ✅ 69_Guabineros_Zarzal_ValledelCauca: 2.0 min
  ✅ 72_ElPorro_PuebloNuevo_Córdoba: 7.3 min
  ✅ 79_SanJerónimo_Pore_Casanare: 10.5 min
```

### Logs de Corrupción

16 archivos JSON generados con detalles de archivos corruptos:
- Ubicación: `s3://mineria-project/logs/01_procesar_sentinel/`
- Formato: `corrupt_files_<ZONE>_<TIMESTAMP>.json`
- Incluye: safe_file, expected_crs, actual_crs, tile_code, error_message

---

## 💰 Costos Estimados

### Script 01 (Procesamiento Sentinel-2)

- **Instancia:** c5.4xlarge @ $0.68/hora
- **Duración:** 18 minutos = 0.3 horas
- **Costo EC2:** ~$0.20
- **Costo S3:** Negligible (< $0.01)
- **Total:** ~$0.21 por ejecución completa

### Scripts 06-07 (EMR Spark)

- **Master:** m5.xlarge @ $0.192/hora
- **Core (2x):** m5.xlarge @ $0.192/hora cada uno
- **Duración estimada:** 1-2 horas
- **Costo estimado:** ~$1.15 - $2.30

---

## 📝 Próximos Pasos

1. **Script 02:** Generación de máscaras de calidad
2. **Script 03:** Extracción de features tabulares
3. **Script 04:** Rasterización de labels
4. **Script 05:** Unión de features con labels
5. **Scripts 06-07:** Entrenamiento y evaluación en EMR
6. **Optimización:** Fine-tuning de modelos
7. **Deployment:** Pipeline automatizado

---

## 📄 Licencia

Ver archivo [LICENSE](LICENSE) para más detalles.

---

## 👥 Contribución

Este es un proyecto académico. Para consultas o contribuciones, contactar al equipo del proyecto.

---

**Última actualización:** 12 de Noviembre, 2025  
**Estado:** Script 01 completado exitosamente ✅
