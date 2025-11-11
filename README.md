# 🌳 Proyecto Minería de Datos - Pipeline de Clasificación Forestal

Pipeline completo de procesamiento de imágenes Sentinel-2 y clasificación de cobertura forestal usando **AWS EC2** y **EMR Spark**.

---

## 🎯 Arquitectura Reorganizada

```
┌─────────────────────────────────────────────────────────────────┐
│                     PIPELINE MINERÍA                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  📦 EC2 Instance (Procesamiento de Datos)                       │
│  ├─ 01_procesar_sentinel.py     → Procesar SAFE files          │
│  ├─ 02_generar_mascaras.py      → Máscaras de calidad          │
│  ├─ 03_tabular_features.py      → Features tabulares           │
│  ├─ 04_rasterizar_labels.py     → Rasterizar labels            │
│  └─ 05_unir_features_labels.py  → Dataset de entrenamiento     │
│                                                                  │
│  ⚡ EMR Cluster (Machine Learning con Spark)                    │
│  ├─ 06_entrenar_modelos_spark.py → Random Forest + GBT         │
│  └─ 07_evaluar_modelos.py        → Métricas y evaluación       │
│                                                                  │
│  💾 S3 Bucket (Almacenamiento)                                  │
│  └─ Datos raw, procesados, modelos y resultados                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerrequisitos

- AWS CLI configurado
- Terraform >= 1.0
- Python 3.10+
- SSH key pair en AWS

### 2. Setup Rápido

```bash
# Clonar repositorio
git clone <repo-url>
cd mineria_project

# Ejecutar script de setup
chmod +x setup.sh
./setup.sh

# El script te guiará a través de:
# - Configuración de Terraform
# - Creación de infraestructura
# - Subida de scripts a S3
```

### 3. Ejecutar Pipeline

**En EC2 (Scripts 01-05):**
```bash
# Conectar a EC2
ssh -i key.pem ubuntu@<EC2_IP>

# Ejecutar script individual
cd /home/ubuntu/mineria_scripts
python orchestration/run_ec2_pipeline.py --script 01_procesar_sentinel

# O ejecutar pipeline completo
python orchestration/run_ec2_pipeline.py --mode sequential
```

**En EMR (Scripts 06-07):**
```bash
# Desde tu máquina local
cd scripts/orchestration/

# Entrenar modelos
python run_emr_pipeline.py \
    --script 06_entrenar_modelos_spark \
    --create-cluster \
    --auto-terminate
```

---

## 📂 Estructura del Proyecto

```
mineria_project/
├── 📄 EXECUTION_GUIDE.md           ⭐ Guía detallada de ejecución
├── 📄 REORGANIZATION_SUMMARY.md    ⭐ Resumen de cambios
├── 📄 README.md                     Este archivo
│
├── config/
│   ├── aws_config.yaml              Configuración AWS
│   ├── pipeline_config.yaml         Parámetros del pipeline
│   └── execution_config.yaml        ⭐ Config de ejecución incremental
│
├── infrastructure/                  ⭐ Terraform modular
│   ├── main.tf                      Configuración principal
│   ├── variables.tf                 Variables
│   ├── s3.tf                        Bucket S3
│   ├── terraform.tfvars.example     Ejemplo de configuración
│   │
│   └── modules/
│       ├── ec2/                     ⭐ Módulo EC2
│       │   ├── main.tf
│       │   └── user_data.sh
│       └── emr/                     ⭐ Módulo EMR
│           └── main.tf
│
├── scripts/
│   ├── 01_procesar_sentinel.py      EC2: Procesar Sentinel
│   ├── 02_generar_mascaras.py       EC2: Máscaras
│   ├── 03_tabular_features.py       EC2: Features
│   ├── 04_rasterizar_labels.py      EC2: Labels
│   ├── 05_unir_features_labels.py   EC2: Join
│   ├── 06_entrenar_modelos_spark.py EMR: Entrenar
│   ├── 07_evaluar_modelos.py        EMR: Evaluar
│   │
│   ├── orchestration/               ⭐ Scripts de orquestación
│   │   ├── run_ec2_pipeline.py      ⭐ Orquestador EC2
│   │   └── run_emr_pipeline.py      ⭐ Orquestador EMR
│   │
│   └── bootstrap/
│       └── install_packages.sh
│
├── docs/
│   └── AWS_SETUP.md
│
└── setup.sh                         ⭐ Script de setup automatizado
```

---

## ✨ Características Principales

### ✅ Ejecución Incremental
- Ejecuta scripts **uno a la vez**
- Verifica resultados antes de continuar
- Perfecto para testing y debugging

### ✅ Validación Automática
- Verifica outputs en S3 después de cada paso
- Logging detallado de todas las operaciones
- Detección temprana de errores

### ✅ Flexible y Escalable
- Configura recursos EC2 y EMR según necesidades
- EMR on-demand (crea cluster solo cuando lo necesites)
- Spot instances para ahorrar costos

### ✅ Infrastructure as Code
- Toda la infraestructura en Terraform
- Módulos reutilizables EC2 y EMR
- Fácil replicación en diferentes entornos

### ✅ Observabilidad
- Logs centralizados en S3
- Monitoreo en tiempo real
- Dry-run mode para testing

---

## 📖 Documentación

| Documento | Descripción |
|-----------|-------------|
| **[EXECUTION_GUIDE.md](EXECUTION_GUIDE.md)** | 📘 Guía completa paso a paso |
| **[REORGANIZATION_SUMMARY.md](REORGANIZATION_SUMMARY.md)** | 📋 Resumen de la reorganización |
| **[docs/AWS_SETUP.md](docs/AWS_SETUP.md)** | ⚙️ Setup de AWS |
| **[MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md)** | 📜 Historia de migración |

---

## 🎯 Flujo de Trabajo Típico

### Desarrollo / Testing

```bash
# 1. Ejecutar script individual en EC2
ssh ubuntu@<EC2_IP>
cd /home/ubuntu/mineria_scripts
python orchestration/run_ec2_pipeline.py --script 01_procesar_sentinel

# 2. Verificar resultados
aws s3 ls s3://bucket/01_processed/ --recursive

# 3. Si hay problemas, revisar logs
tail -f /home/ubuntu/mineria_logs/ec2_pipeline_*.log

# 4. Refinar y repetir

# 5. Continuar con siguiente script cuando esté listo
python orchestration/run_ec2_pipeline.py --script 02_generar_mascaras
```

### Producción

```bash
# Pipeline completo EC2
python orchestration/run_ec2_pipeline.py --mode sequential

# Pipeline EMR
cd scripts/orchestration/
python run_emr_pipeline.py --mode sequential --create-cluster --auto-terminate
```

---

## 💰 Estimación de Costos (AWS us-east-1)

| Recurso | Tipo | Costo/hora | Uso típico | Costo estimado |
|---------|------|------------|------------|----------------|
| EC2 Processing | t3.xlarge | $0.17 | 4-8 horas | $1-2 |
| EMR Master | m5.xlarge | $0.19 | 5-10 horas | $1-2 |
| EMR Workers (2x) | m5.2xlarge | $0.38 c/u | 5-10 horas | $4-8 |
| S3 Storage | - | $0.023/GB/mes | 100 GB | $2.30/mes |
| **Total pipeline completo** | - | - | Una ejecución | **$6-12** |

**Tips para ahorrar:**
- ✅ Detener EC2 cuando no se use
- ✅ EMR on-demand (no permanente)
- ✅ Usar Spot instances para workers (-70%)
- ✅ Lifecycle policies en S3

---

## 🔧 Configuración

### Variables de Terraform

Edita `infrastructure/terraform.tfvars`:

```hcl
# Básico
region        = "us-east-1"
project_name  = "mineria"
environment   = "dev"
key_pair_name = "your-key"

# EC2
ec2_instance_type = "t3.xlarge"

# EMR
create_emr_cluster = false  # Crear on-demand
emr_core_instance_count = 2
```

### Parámetros de Ejecución

Edita `config/execution_config.yaml`:

```yaml
# Parámetros por script
script_params:
  "01_procesar_sentinel":
    bands: "B01,B02,B03,B04,B05,B06,B07,B08,B8A,B11,B12"
    resolution: 20

# Timeouts
monitoring:
  timeouts:
    "01_procesar_sentinel": 7200
    "06_entrenar_modelos_spark": 10800
```

---

## 🐛 Troubleshooting

### EC2 no responde

```bash
# Ver estado
aws ec2 describe-instances --instance-ids <ID>

# Ver logs de inicialización
ssh ubuntu@<IP>
tail -f /var/log/user-data.log
```

### Script falla en EC2

```bash
# Ver logs
tail -f /home/ubuntu/mineria_logs/ec2_pipeline_*.log

# Ejecutar con dry-run
python orchestration/run_ec2_pipeline.py --script 01_procesar_sentinel --dry-run
```

### EMR job falla

```bash
# Ver clusters
aws emr list-clusters --active

# Ver detalles del step
aws emr describe-step --cluster-id j-XXX --step-id s-YYY

# Descargar logs
aws s3 sync s3://bucket/logs/emr/<cluster-id>/ ./logs/
```

---

## 🔗 Recursos Útiles

- [AWS EMR Documentation](https://docs.aws.amazon.com/emr/)
- [Spark MLlib Guide](https://spark.apache.org/docs/latest/ml-guide.html)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Rasterio Documentation](https://rasterio.readthedocs.io/)

---

## 🤝 Contribuir

1. Fork el repositorio
2. Crea una rama (`git checkout -b feature/mejora`)
3. Commit cambios (`git commit -am 'Add mejora'`)
4. Push a la rama (`git push origin feature/mejora`)
5. Abre un Pull Request

---

## 📝 Licencia

Ver archivo [LICENSE](LICENSE)

---

## 👥 Autores

- Minería Team
- Contacto: <your-email>

---

**🚀 ¡Listo para procesar datos forestales a escala!**
