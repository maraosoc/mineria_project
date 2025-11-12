# Entrenamiento de Modelos en AWS EMR

## 📋 Resumen

Este documento describe cómo entrenar y evaluar modelos de Machine Learning usando **AWS EMR (Elastic MapReduce)** con **Apache Spark**. El pipeline está optimizado para procesamiento distribuido de datasets grandes.

---

## 🏗️ Arquitectura EMR

### **Componentes del Cluster**

```
EMR Cluster (mineria-ml-cluster)
│
├── Master Node (m5.xlarge)
│   ├── YARN ResourceManager
│   ├── Spark Driver
│   └── HDFS NameNode
│
└── Core Nodes (2x m5.2xlarge)
    ├── YARN NodeManager
    ├── Spark Executors
    └── HDFS DataNode
```

### **Especificaciones**

| Componente | Tipo | vCPU | RAM | Storage | Función |
|------------|------|------|-----|---------|---------|
| **Master** | m5.xlarge | 4 | 16GB | 64GB EBS | Coordinación, Spark Driver |
| **Core (x2)** | m5.2xlarge | 8 | 32GB | 2x128GB EBS | Procesamiento, HDFS |
| **Total** | - | 20 | 80GB | 320GB | - |

### **Configuración de Spark**

```json
{
  "maximizeResourceAllocation": true,
  "spark.dynamicAllocation.enabled": true,
  "spark.shuffle.service.enabled": true,
  "spark.serializer": "KryoSerializer",
  "spark.sql.adaptive.enabled": true
}
```

---

## 🚀 Deployment del Cluster

### **1. Configurar Variables Terraform**

Editar `infrastructure/terraform.tfvars`:

```hcl
# Configuración EMR
emr_master_instance_type  = "m5.xlarge"
emr_core_instance_type    = "m5.2xlarge"
emr_core_instance_count   = 2
emr_key_name              = "your-ssh-key"  # opcional
```

### **2. Crear Cluster EMR**

```bash
cd infrastructure
terraform init
terraform plan
terraform apply
```

**Tiempo de creación:** ~10-15 minutos

### **3. Obtener Cluster ID**

```bash
# Desde Terraform output
terraform output emr_cluster_id

# O desde AWS CLI
aws emr list-clusters --active --query 'Clusters[0].Id' --output text
```

---

## 📊 Entrenamiento de Modelos

### **Script 06: Entrenamiento**

**Función:** Entrena modelos Random Forest y GBT con optimización de hiperparámetros.

#### **Pipeline de Entrenamiento**

```
1. Carga de datos desde S3
   ↓
2. Split train/val/test (70/15/15)
   ↓
3. Cálculo de pesos para balanceo de clases
   ↓
4. Optimización de hiperparámetros
   ├── Random Forest (Grid Search)
   └── Gradient Boosted Trees (Grid Search)
   ↓
5. Selección del mejor modelo (según validation)
   ↓
6. Re-entrenamiento con TODO el train set
   ↓
7. Evaluación final en test set
   ↓
8. Guardado del modelo en S3
```

#### **Grid de Hiperparámetros**

**Random Forest:**
- `numTrees`: [200, 400, 600]
- `maxDepth`: [10, 14, 18]
- `maxBins`: [64, 128]
- `featureSubsetStrategy`: ["sqrt", "log2"]
- **Total combinaciones:** 24

**Gradient Boosted Trees:**
- `maxDepth`: [6, 8, 10]
- `maxBins`: [64, 128]
- `maxIter`: [100, 200]
- `stepSize`: [0.05, 0.1, 0.2]
- **Total combinaciones:** 36

#### **Uso Manual (spark-submit)**

```bash
spark-submit \
  --deploy-mode cluster \
  --master yarn \
  --conf spark.executor.memory=8g \
  --conf spark.executor.cores=4 \
  --conf spark.executor.instances=4 \
  --conf spark.driver.memory=4g \
  s3://mineria-project/source/scripts/06_entrenar_modelos_spark.py \
  --inputs s3://mineria-project/data/all/training_data_all_zones.parquet \
  --out_model_dir s3://mineria-project/models/model_v1/ \
  --label_col label \
  --test_frac 0.15 \
  --seed 42 \
  --metric areaUnderPR
```

#### **Uso con Script Helper**

```bash
# Entrenamiento básico
python scripts/submit_training_emr.py --cluster-id j-XXXXXXXXX

# Entrenar y esperar
python scripts/submit_training_emr.py --cluster-id j-XXXXXXXXX --wait

# Entrenar y evaluar automáticamente
python scripts/submit_training_emr.py \
  --cluster-id j-XXXXXXXXX \
  --evaluate \
  --wait

# Configuración custom
python scripts/submit_training_emr.py \
  --cluster-id j-XXXXXXXXX \
  --input-data s3://mineria-project/data/custom/filtered_data.parquet \
  --test-frac 0.2 \
  --metric areaUnderROC \
  --evaluate
```

#### **Outputs del Entrenamiento**

```
s3://mineria-project/models/model_YYYYMMDD_HHMMSS/
├── pipeline_best/               # Modelo completo (Pipeline)
│   ├── metadata/
│   ├── stages/
│   │   ├── 0_VectorAssembler/
│   │   └── 1_RandomForestClassifier/  (o GBTClassifier)
│   └── ...
└── metrics/
    ├── summary.json             # Métricas completas
    └── feature_importances.csv  # Importancia de variables
```

**Contenido de `summary.json`:**
```json
{
  "metric_used": "areaUnderPR",
  "train_samples": 5605,
  "val_samples": 1201,
  "test_samples": 1202,
  "n_features": 15,
  "class_weights": {"0.0": 0.65, "1.0": 2.20},
  "models": {
    "RandomForest": {
      "val_metrics": {
        "areaUnderROC": 0.8723,
        "areaUnderPR": 0.7654,
        "accuracy": 0.8234,
        "f1": 0.7890
      },
      "test_metrics": {...},
      "best_params": {
        "numTrees": "400",
        "maxDepth": "14",
        "maxBins": "128"
      }
    },
    "GBT": {...}
  },
  "winner": {
    "name": "RandomForest",
    "val_metrics": {...},
    "test_metrics_retrained": {...}
  },
  "confusion_matrix": {
    "TN": 890,
    "FP": 120,
    "FN": 95,
    "TP": 97
  },
  "feature_importances": [
    {"feature": "B08_med", "importance": 0.1856},
    {"feature": "NDVI_med", "importance": 0.1432},
    ...
  ]
}
```

---

## 📈 Evaluación de Modelos

### **Script 07: Evaluación**

**Función:** Evalúa modelo guardado y genera reportes detallados.

#### **Uso**

```bash
# Evaluación manual
spark-submit \
  --deploy-mode cluster \
  --master yarn \
  s3://mineria-project/source/scripts/07_evaluar_modelos.py \
  --model s3://mineria-project/models/model_20251112_163000/pipeline_best \
  --test_data s3://mineria-project/data/all/training_data_all_zones.parquet \
  --output s3://mineria-project/results/eval_20251112/ \
  --test_fraction 0.15

# O usar el helper con --evaluate
python scripts/submit_training_emr.py --cluster-id j-XXXXXXXXX --evaluate --wait
```

#### **Outputs de Evaluación**

```
s3://mineria-project/results/eval_YYYYMMDD_HHMMSS/
├── metrics.json                 # Métricas JSON
├── feature_importance.json      # Importancia detallada
└── EVALUATION_REPORT.md         # Reporte legible
```

**Métricas Calculadas:**
- AUC-ROC
- AUC-PR
- Accuracy
- F1-Score
- Precision (weighted)
- Recall (weighted)
- Precision por clase (0, 1)
- Recall por clase (0, 1)
- Matriz de confusión (TN, FP, FN, TP)

---

## 🔍 Monitoreo y Debugging

### **Verificar Estado del Cluster**

```bash
# Estado general
aws emr describe-cluster --cluster-id j-XXXXXXXXX

# Listar steps
aws emr list-steps --cluster-id j-XXXXXXXXX

# Ver detalles de un step
aws emr describe-step --cluster-id j-XXXXXXXXX --step-id s-XXXXXXXXX
```

### **Acceder a Logs**

```bash
# Logs del cluster
aws s3 ls s3://mineria-project/logs/emr/j-XXXXXXXXX/

# Descargar logs de un step
aws s3 cp s3://mineria-project/logs/emr/j-XXXXXXXXX/steps/s-XXXXXXXXX/ ./logs/ --recursive

# Ver stderr de un step
aws s3 cp s3://mineria-project/logs/emr/j-XXXXXXXXX/steps/s-XXXXXXXXX/stderr.gz - | gunzip
```

### **UIs de Monitoreo**

**Spark History Server:**
```
http://<master-public-dns>:18080
```

**YARN ResourceManager:**
```
http://<master-public-dns>:8088
```

**Para acceder:**
```bash
# 1. Obtener DNS del master
MASTER_DNS=$(aws emr describe-cluster --cluster-id j-XXXXXXXXX \
  --query 'Cluster.MasterPublicDnsName' --output text)

# 2. Crear túnel SSH (si configuraste SSH key)
ssh -i your-key.pem -N -L 8088:localhost:8088 hadoop@$MASTER_DNS

# 3. Abrir en navegador
open http://localhost:8088
```

---

## 💰 Costos y Optimización

### **Estimación de Costos (us-east-1)**

| Componente | Tipo | Precio/hora | Cantidad | Total/hora |
|------------|------|-------------|----------|------------|
| Master | m5.xlarge | $0.192 | 1 | $0.19 |
| Core | m5.2xlarge | $0.384 | 2 | $0.77 |
| EMR Fee | - | 25% | - | $0.24 |
| **Total** | | | | **$1.20/hora** |

**Costos típicos:**
- Entrenamiento completo: **~30 minutos** = **$0.60**
- Evaluación: **~10 minutos** = **$0.20**
- **Total por experimento:** **~$0.80**

### **Configuración de Auto-terminación**

El cluster se termina automáticamente después de **1 hora de inactividad** para evitar costos innecesarios.

```hcl
# En emr.tf
auto_termination_policy {
  idle_timeout = 3600  # 1 hora
}
```

### **Terminar Cluster Manualmente**

```bash
# Terminar cluster
aws emr terminate-clusters --cluster-ids j-XXXXXXXXX

# O con Terraform
terraform destroy -target=aws_emr_cluster.ml_cluster
```

---

## 🛠️ Troubleshooting

### **Error: Cluster no disponible**
```
Error: Cluster no está disponible (estado: TERMINATED)
```
**Solución:** Verificar que el cluster esté en estado `WAITING` o `RUNNING`:
```bash
aws emr list-clusters --active
```

### **Error: Out of Memory**
```
java.lang.OutOfMemoryError: Java heap space
```
**Solución:** Aumentar memoria de executors:
```bash
--conf spark.executor.memory=12g \
--conf spark.driver.memory=6g
```

### **Error: S3 Access Denied**
```
AccessDeniedException: User not authorized
```
**Solución:** Verificar IAM roles y políticas en `emr.tf` (línea 74-91).

### **Error: Step Failed**
```
Step failed with error: Command failed with exit code 1
```
**Solución:** Revisar logs detallados:
```bash
aws s3 cp s3://mineria-project/logs/emr/j-XXX/steps/s-XXX/stderr.gz - | gunzip | tail -100
```

---

## 📚 Referencias

### **Documentación AWS**
- [AWS EMR Documentation](https://docs.aws.amazon.com/emr/)
- [Spark on EMR](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-spark.html)
- [EMR Best Practices](https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-plan-instances-guidelines.html)

### **Comandos Útiles**

```bash
# Listar clusters activos
aws emr list-clusters --active

# Crear cluster desde CLI (alternativa a Terraform)
aws emr create-cluster \
  --name "mineria-ml-cluster" \
  --release-label emr-6.15.0 \
  --applications Name=Spark Name=Hadoop \
  --ec2-attributes KeyName=your-key,InstanceProfile=EMR_EC2_DefaultRole \
  --instance-groups InstanceGroupType=MASTER,InstanceType=m5.xlarge,InstanceCount=1 \
                    InstanceGroupType=CORE,InstanceType=m5.2xlarge,InstanceCount=2 \
  --service-role EMR_DefaultRole \
  --log-uri s3://mineria-project/logs/emr/

# Ver configuración de Spark
aws emr describe-cluster --cluster-id j-XXX \
  --query 'Cluster.Configurations' --output json

# Escalar cluster (añadir task nodes)
aws emr modify-instance-groups --cluster-id j-XXX \
  --instance-groups InstanceGroupId=ig-XXX,InstanceCount=4
```

---

## ✅ Checklist de Producción

Antes de ejecutar en producción:

- [ ] Cluster EMR creado y en estado `WAITING`
- [ ] Scripts 06 y 07 subidos a S3
- [ ] Bootstrap script funcionando correctamente
- [ ] IAM roles configurados con permisos S3
- [ ] Security groups permiten acceso necesario
- [ ] Dataset consolidado disponible en S3
- [ ] Auto-terminación configurada (evitar costos)
- [ ] Logs habilitados en S3
- [ ] Budget alerts configuradas en AWS

---

**Última actualización:** 2025-11-12  
**Versión:** 1.0  
**Contacto:** Equipo de MLOps - Proyecto Minería
