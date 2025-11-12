# 🌳 Proyecto Minería de Datos - Pipeline de Clasificación Forestal

Pipeline completo de procesamiento de imágenes Sentinel-2 y clasificación de cobertura forestal usando **AWS EC2** y **EMR Spark**.

---

## 🎯 Arquitectura del Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     PIPELINE MINERÍA                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  📦 EC2 Instance (Procesamiento de Datos)                       │
│  ├─ 01_procesar_sentinel_clip.py → Procesar y recortar SAFE    │
│  ├─ 02_generar_mascaras.py       → Máscaras de calidad         │
│  ├─ 03_tabular_features.py       → Features tabulares          │
│  ├─ 04_rasterizar_labels.py      → Rasterizar labels           │
│  └─ 05_unir_features_labels.py   → Dataset de entrenamiento    │
│                                                                  │
│  ⚡ EMR Cluster (Machine Learning con Spark)                    │
│  ├─ 06_entrenar_modelos_spark.py → Random Forest + GBT         │
│  └─ 07_evaluar_modelos.py        → Métricas y evaluación       │
│                                                                  │
│  💾 S3 Bucket (Almacenamiento)                                  │
│  └─ s3://mineria-project/                                       │
│     ├─ raw/raw_copernicus/       → Datos Sentinel-2 originales │
│     ├─ raw/shapes/                → Shapefiles de zonas        │
│     ├─ staging/                  → Datos procesados             │
│     ├─ logs/                     → Logs de corrupción           │
│     └─ source/scripts/           → Scripts para EC2/EMR         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Estado Actual del Proyecto

### ✅ Completado

**Script 01 - Procesamiento Sentinel-2:**
- ✅ Procesamiento de imágenes SAFE con bandas de 20m (B02-B07, B8A, B11, B12)
- ✅ Recorte automático con shapefiles por zona
- ✅ Corrección automática de CRS corrupto (detección por tile code)
- ✅ Sistema de logging de archivos corruptos (JSON a S3)
- ✅ Procesamiento paralelo de 15 zonas (8 workers)
- ✅ **Resultado:** 15 zonas procesadas exitosamente en 18 minutos

**Infraestructura:**
- ✅ Terraform modular (EC2 + EMR)
- ✅ Roles IAM configurados
- ✅ S3 buckets con lifecycle policies
- ✅ Security groups
- ✅ User data scripts para EC2

### 🔄 Pendiente

**Scripts 02-05:**
- ⏳ Generación de máscaras
- ⏳ Extracción de features tabulares
- ⏳ Rasterización de labels
- ⏳ Unión de features con labels

**Scripts 06-07:**
- ⏳ Entrenamiento de modelos con Spark
- ⏳ Evaluación de modelos

---

## 🚀 Uso

### 1. Desplegar Infraestructura

```bash
cd infrastructure

# Inicializar Terraform
terraform init

# Revisar y aplicar plan
terraform plan -out=tfplan
terraform apply tfplan
```

La infraestructura incluye:
- **EC2 c5.4xlarge** (16 vCPUs, 32GB RAM) para scripts 01-05
- **Security Groups** configurados
- **IAM Roles** con acceso a S3 y SSM
- **S3 Buckets** con políticas de lifecycle

### 2. Conectarse a EC2

```bash
# Obtener Instance ID de los outputs de Terraform
aws ssm start-session --target <INSTANCE_ID>

# Cambiar a usuario ubuntu
sudo su - ubuntu
```

### 3. Ejecutar Script 01 (Procesamiento Sentinel-2)

**Procesamiento paralelo de todas las zonas:**

```bash
cd /home/ubuntu/mineria_project/scripts

# Descargar scripts desde S3 si no están presentes
python3 << 'EOF'
import boto3, os
s3 = boto3.client('s3')
scripts = ['01_procesar_sentinel_clip.py', 'process_all_zones_parallel.py']
for script in scripts:
    s3.download_file('mineria-project', f'source/scripts/{script}', script)
    os.chmod(script, 0o755)
EOF

# Ejecutar procesamiento paralelo
nohup python3 process_all_zones_parallel.py --workers 8 > ../logs/processing_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Monitorear en tiempo real
tail -f ../logs/processing_*.log
```

**Procesamiento de una zona individual:**

```bash
python3 01_procesar_sentinel_clip.py \
  --input s3://mineria-project/raw/raw_copernicus/42_VillaLuzA_Unguía_Chocó/ \
  --output s3://mineria-project/staging/01_rasters_procesados_clipped/ \
  --zone_name "42_VillaLuzA_Unguía_Chocó" \
  --shape_path "s3://mineria-project/raw/shapes/42_VillaLuzA_Unguía_Chocó/Perímetro" \
  --clip
```

### 4. Verificar Resultados

```bash
# Contar archivos procesados
aws s3 ls s3://mineria-project/staging/01_rasters_procesados_clipped/ --recursive | wc -l

# Ver logs de corrupción
aws s3 ls s3://mineria-project/logs/01_procesar_sentinel/

# Descargar un log específico
aws s3 cp s3://mineria-project/logs/01_procesar_sentinel/corrupt_files_<ZONE>.json .
```

### 5. Destruir Infraestructura

```bash
cd infrastructure
terraform destroy -auto-approve
```

---

## 📁 Estructura del Proyecto

```
mineria_project/
├── config/                          # Configuraciones
│   ├── aws_config.yaml
│   └── pipeline_config.yaml
├── docs/                            # Documentación
│   └── AWS_SETUP.md
├── infrastructure/                  # Infraestructura como código
│   ├── backend.tf                   # Backend de Terraform
│   ├── main.tf                      # Configuración principal
│   ├── s3.tf                        # Buckets S3
│   ├── variables.tf                 # Variables
│   ├── terraform.tfvars             # Valores de variables
│   └── modules/                     # Módulos Terraform
│       ├── ec2/                     # Módulo EC2
│       └── emr/                     # Módulo EMR
├── scripts/                         # Scripts de procesamiento
│   ├── 01_procesar_sentinel_clip.py # Procesamiento Sentinel-2 ✅
│   ├── 02_generar_mascaras.py       # Máscaras de calidad
│   ├── 03_tabular_features.py       # Features tabulares
│   ├── 04_rasterizar_labels.py      # Rasterización de labels
│   ├── 05_unir_features_labels.py   # Unión de datos
│   ├── 06_entrenar_modelos_spark.py # Entrenamiento con Spark
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
