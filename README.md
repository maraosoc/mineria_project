# 🌳 Minería de Datos - Pipeline de Clasificación Bosque/No-Bosque

Pipeline completo de procesamiento de imágenes Sentinel-2 y clasificación de cobertura forestal usando AWS EMR, S3 y Spark MLlib.

---

## 📋 Tabla de Contenidos

- [Arquitectura](#arquitectura)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Pipeline de Datos](#pipeline-de-datos)
- [Configuración AWS](#configuración-aws)
- [Ejecución](#ejecución)
- [Monitoreo](#monitoreo)
- [Desarrollo Local](#desarrollo-local)

---

## 🏗️ Arquitectura

```
┌─────────────────┐
│  Sentinel-2     │
│  Raw Data (S3)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│            AWS EMR Cluster (Spark 3.x)                  │
│                                                          │
│  Step 1: Procesar Sentinel                              │
│  ├─ Leer SAFE files (rasterio)                         │
│  ├─ Calcular índices (NDVI, NDWI)                      │
│  └─ Guardar → s3://bucket/01_processed/                │
│                                                          │
│  Step 2: Generar Máscaras                               │
│  ├─ SCL classification                                  │
│  ├─ Clear sky mask                                      │
│  └─ Guardar → s3://bucket/02_masks/                    │
│                                                          │
│  Step 3: Tabulación con Polars                          │
│  ├─ Extraer valores por píxel                          │
│  ├─ Calcular estadísticas temporales                    │
│  └─ Guardar → s3://bucket/03_features/                 │
│                                                          │
│  Step 4: Rasterizar Labels                              │
│  ├─ Vectores bosque → raster                           │
│  ├─ Aplicar erosión de bordes                          │
│  └─ Guardar → s3://bucket/04_labels/                   │
│                                                          │
│  Step 5: Unir Features + Labels                         │
│  ├─ Join espacial                                       │
│  └─ Guardar → s3://bucket/05_training_data/            │
│                                                          │
│  Step 6: Entrenar Modelos (Spark MLlib)                 │
│  ├─ Random Forest                                       │
│  ├─ Gradient Boosted Trees                             │
│  ├─ Optimización hiperparámetros                       │
│  └─ Guardar → s3://bucket/06_models/                   │
│                                                          │
│  Step 7: Evaluación                                      │
│  └─ Guardar métricas → s3://bucket/07_evaluation/      │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Predicciones   │
│  (S3 + Athena)  │
└─────────────────┘
```

---

## 📁 Estructura del Proyecto

```
mineria_project/
├── README.md
├── requirements.txt
├── setup.py
│
├── config/
│   ├── aws_config.yaml          # Configuración AWS (región, bucket, etc)
│   ├── emr_config.json          # Configuración cluster EMR
│   └── pipeline_config.yaml     # Parámetros del pipeline
│
├── scripts/
│   ├── 01_procesar_sentinel.py           # Procesar SAFE files
│   ├── 02_generar_mascaras.py            # Generar máscaras clear sky
│   ├── 03_tabular_features.py            # Extraer features por píxel
│   ├── 04_rasterizar_labels.py           # Vectores → raster labels
│   ├── 05_unir_features_labels.py        # Join features + labels
│   ├── 06_entrenar_modelos_spark.py      # Entrenar RF + GBT (Spark)
│   ├── 07_evaluar_modelos.py             # Generar métricas
│   ├── 08_predecir.py                    # Predicciones nuevas áreas
│   ├── submit_emr_steps.py               # Enviar steps a EMR
│   └── utils/
│       ├── __init__.py
│       ├── s3_utils.py                   # Funciones S3
│       ├── raster_utils.py               # Funciones rasterio
│       └── spark_utils.py                # Funciones Spark
│
├── terraform/
│   ├── main.tf                  # Infraestructura AWS
│   ├── emr.tf                   # Cluster EMR
│   ├── s3.tf                    # Buckets S3
│   ├── iam.tf                   # Roles y policies
│   └── variables.tf             # Variables Terraform
│
├── .github/
│   └── workflows/
│       └── deploy.yml           # CI/CD con GitHub Actions
│
├── docs/
│   ├── AWS_SETUP.md             # Guía configuración AWS
│   ├── EMR_GUIDE.md             # Guía uso EMR
│   ├── PIPELINE.md              # Documentación pipeline
│   └── TROUBLESHOOTING.md       # Resolución de problemas
│
└── tests/
    ├── test_procesar_sentinel.py
    ├── test_tabular_features.py
    └── test_entrenar_modelos.py
```

---

## 🔄 Pipeline de Datos

### Step 1: Procesar Sentinel-2
```bash
spark-submit \
  --deploy-mode cluster \
  s3://bucket/scripts/01_procesar_sentinel.py \
  --input s3://bucket/raw_sentinel/*.SAFE \
  --output s3://bucket/01_processed/ \
  --bands B01,B02,B03,B04,B05,B06,B07,B08,B8A,B11,B12 \
  --resolution 20
```

### Step 2: Generar Máscaras
```bash
spark-submit \
  s3://bucket/scripts/02_generar_mascaras.py \
  --input s3://bucket/01_processed/*.tif \
  --output s3://bucket/02_masks/ \
  --clear_classes 4,5,6
```

### Step 3: Tabular Features
```bash
spark-submit \
  --executor-memory 16g \
  s3://bucket/scripts/03_tabular_features.py \
  --rasters s3://bucket/01_processed/*.tif \
  --masks s3://bucket/02_masks/*.tif \
  --output s3://bucket/03_features/composite.parquet \
  --stats median,p10,p90
```

### Step 4-6: Training Pipeline
```bash
# Rasterizar labels
spark-submit s3://bucket/scripts/04_rasterizar_labels.py \
  --bosque_shp s3://bucket/shapes/bosque.shp \
  --output s3://bucket/04_labels/forest_labels.tif

# Unir features + labels
spark-submit s3://bucket/scripts/05_unir_features_labels.py \
  --features s3://bucket/03_features/composite.parquet \
  --labels s3://bucket/04_labels/forest_labels.tif \
  --output s3://bucket/05_training_data/training.parquet

# Entrenar modelos
spark-submit \
  --executor-memory 32g \
  --executor-cores 8 \
  s3://bucket/scripts/06_entrenar_modelos_spark.py \
  --input s3://bucket/05_training_data/training.parquet \
  --out_model s3://bucket/06_models/best_model \
  --out_metrics s3://bucket/07_evaluation/
```

---

## ⚙️ Configuración AWS

### 1. Requisitos Previos

- AWS CLI configurado
- Terraform instalado
- Cuenta AWS con permisos EMR, S3, IAM

### 2. Desplegar Infraestructura

```bash
cd terraform/
terraform init
terraform plan
terraform apply
```

Esto crea:
- ✅ Bucket S3 (`s3://mineria-data-bucket`)
- ✅ Cluster EMR (Spark 3.5, 1 master + N workers)
- ✅ Roles IAM (EMR_EC2_DefaultRole, EMR_DefaultRole)
- ✅ Security Groups

### 3. Subir Scripts a S3

```bash
aws s3 sync scripts/ s3://mineria-data-bucket/scripts/
aws s3 sync config/ s3://mineria-data-bucket/config/
```

### 4. Subir Datos Raw

```bash
aws s3 sync safe/ s3://mineria-data-bucket/raw_sentinel/
aws s3 sync shapes/ s3://mineria-data-bucket/shapes/
```

---

## 🚀 Ejecución

### Opción 1: Ejecución Manual (AWS Console)

1. Ir a **EMR Console**
2. Seleccionar cluster
3. **Add Step** → Custom JAR (spark-submit)
4. Configurar argumentos del script

### Opción 2: Ejecución Programática (Python)

```python
# scripts/submit_emr_steps.py
python scripts/submit_emr_steps.py \
  --cluster-id j-XXXXXXXXXXXXX \
  --step procesar_sentinel \
  --config config/pipeline_config.yaml
```

### Opción 3: Pipeline Completo (Airflow/Step Functions)

```bash
# Ejecutar todos los pasos en secuencia
python scripts/submit_emr_steps.py \
  --cluster-id j-XXXXXXXXXXXXX \
  --pipeline full \
  --wait
```

---

## 📊 Monitoreo

### CloudWatch Logs

```bash
# Ver logs de step
aws emr describe-step \
  --cluster-id j-XXXXXXXXXXXXX \
  --step-id s-XXXXXXXXXXXXX

# Descargar logs
aws s3 sync s3://aws-logs-bucket/emr/j-XXX/steps/ ./logs/
```

### Spark UI

```bash
# Túnel SSH
aws emr socks --cluster-id j-XXXXXXXXXXXXX --key-pair-file key.pem

# Acceder: http://master-public-dns:8088
```

### Métricas S3

```bash
# Ver tamaño de outputs
aws s3 ls s3://mineria-data-bucket/ --recursive --human-readable --summarize
```

---

## 💻 Desarrollo Local

### Setup Entorno

```bash
# Crear virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### Ejecutar Scripts Localmente (Sin Spark)

```bash
# Usar versión sklearn en lugar de Spark
python scripts/sklearn_train_bosque_nobosque.py \
  --input data/training_data.parquet \
  --out_model_dir models/ \
  --out_metrics_dir evaluation/
```

### Testing

```bash
pytest tests/
```

---

## 📈 Resultados Esperados

### Métricas del Modelo

| Métrica | Objetivo | Actual |
|---------|----------|--------|
| Accuracy | > 85% | 90.32% ✅ |
| ROC-AUC | > 90% | 92.41% ✅ |
| F1-Score | > 85% | 89.33% ✅ |

### Costos Estimados AWS

| Recurso | Costo/hora | Costo/día (24h) |
|---------|------------|-----------------|
| EMR (m5.xlarge × 3) | $0.30 | $7.20 |
| S3 Storage (100GB) | - | $0.23 |
| Data Transfer | - | ~$0.50 |
| **Total** | - | **~$8/día** |

💡 **Tip**: Usar Spot Instances para reducir costos 60-70%

---

## 🔧 Configuración Avanzada

### Optimizar Cluster EMR

```json
// config/emr_config.json
{
  "InstanceGroups": [
    {
      "InstanceRole": "MASTER",
      "InstanceType": "m5.xlarge",
      "InstanceCount": 1
    },
    {
      "InstanceRole": "CORE",
      "InstanceType": "m5.2xlarge",
      "InstanceCount": 5,
      "BidPrice": "0.10"  // Spot instance
    }
  ],
  "Applications": [
    {"Name": "Spark"},
    {"Name": "Hadoop"},
    {"Name": "Hive"}
  ]
}
```

### Particionamiento S3

```
s3://mineria-data-bucket/
├── 03_features/
│   ├── year=2019/
│   ├── year=2020/
│   ├── year=2021/
│   └── year=2022/
└── 05_training_data/
    ├── finca=finca1/
    ├── finca=finca2/
    └── finca=finca3/
```

---

## 🐛 Troubleshooting

Ver [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

**Problemas comunes:**
- Cluster EMR no inicia → Revisar límites de servicio
- Out of Memory → Aumentar `executor-memory`
- S3 access denied → Verificar IAM roles

---

## 📚 Referencias

- [AWS EMR Documentation](https://docs.aws.amazon.com/emr/)
- [Spark MLlib Guide](https://spark.apache.org/docs/latest/ml-guide.html)
- [Rasterio Documentation](https://rasterio.readthedocs.io/)
- [Polars Guide](https://pola-rs.github.io/polars-book/)

---

## 👥 Autores

**Manu** - Minería de Datos  
**Última actualización**: Noviembre 2025

---

## 📄 Licencia

MIT License - Ver [LICENSE](LICENSE) para más detalles
