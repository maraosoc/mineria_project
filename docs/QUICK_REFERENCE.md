# Quick Reference - Comandos EMR Training

## 🚀 Inicio Rápido

### 1. Crear Cluster EMR
```bash
cd infrastructure
terraform init
terraform apply
```

### 2. Obtener Cluster ID
```bash
CLUSTER_ID=$(terraform output -raw emr_cluster_id)
echo $CLUSTER_ID
```

### 3. Entrenar Modelo
```bash
python scripts/submit_training_emr.py \
  --cluster-id $CLUSTER_ID \
  --evaluate \
  --wait
```

---

## 📋 Comandos Frecuentes

### Gestión de Clusters

```bash
# Listar clusters activos
python scripts/manage_emr_cluster.py list

# Ver estado
python scripts/manage_emr_cluster.py status --cluster-id j-XXX

# Ver steps
python scripts/manage_emr_cluster.py steps --cluster-id j-XXX

# Terminar cluster
python scripts/manage_emr_cluster.py terminate --cluster-id j-XXX
```

### Entrenamiento

```bash
# Básico
python scripts/submit_training_emr.py --cluster-id j-XXX

# Con evaluación
python scripts/submit_training_emr.py --cluster-id j-XXX --evaluate

# Esperar completación
python scripts/submit_training_emr.py --cluster-id j-XXX --wait

# Custom input
python scripts/submit_training_emr.py \
  --cluster-id j-XXX \
  --input-data s3://mineria-project/data/custom/data.parquet

# Configuración avanzada
python scripts/submit_training_emr.py \
  --cluster-id j-XXX \
  --test-frac 0.2 \
  --metric areaUnderROC \
  --seed 123 \
  --evaluate \
  --wait
```

### Monitoreo

```bash
# AWS CLI
aws emr list-clusters --active
aws emr describe-cluster --cluster-id j-XXX
aws emr list-steps --cluster-id j-XXX
aws emr describe-step --cluster-id j-XXX --step-id s-XXX

# Logs
python scripts/manage_emr_cluster.py logs --cluster-id j-XXX --step-id s-XXX

# Descargar logs
aws s3 cp s3://mineria-project/logs/emr/j-XXX/steps/s-XXX/ ./logs/ --recursive
```

### Resultados

```bash
# Listar modelos
aws s3 ls s3://mineria-project/models/

# Descargar métricas
aws s3 cp s3://mineria-project/models/model_20251112_163000/metrics/summary.json ./

# Listar evaluaciones
aws s3 ls s3://mineria-project/results/

# Descargar reporte
aws s3 cp s3://mineria-project/results/eval_20251112_163500/EVALUATION_REPORT.md ./
```

---

## 🔧 Terraform

```bash
# Plan
terraform plan

# Apply
terraform apply

# Destroy solo EMR
terraform destroy -target=aws_emr_cluster.ml_cluster

# Destroy todo
terraform destroy

# Ver outputs
terraform output
terraform output emr_cluster_id
terraform output emr_cluster_master_public_dns
```

---

## 📊 Análisis de Resultados

### Leer métricas desde Python

```python
import json
import boto3

s3 = boto3.client('s3')

# Descargar summary
response = s3.get_object(
    Bucket='mineria-project',
    Key='models/model_20251112_163000/metrics/summary.json'
)
metrics = json.loads(response['Body'].read())

# Ver winner
print(f"Mejor modelo: {metrics['winner']['name']}")
print(f"Accuracy: {metrics['winner']['test_metrics_retrained']['accuracy']:.4f}")
print(f"F1-Score: {metrics['winner']['test_metrics_retrained']['f1']:.4f}")
print(f"AUC-ROC: {metrics['winner']['test_metrics_retrained']['areaUnderROC']:.4f}")

# Top 10 features
for feat in metrics['feature_importances'][:10]:
    print(f"{feat['feature']}: {feat['importance']:.4f}")
```

### Comparar modelos

```python
import pandas as pd
import boto3

s3 = boto3.client('s3')

# Listar todos los modelos
response = s3.list_objects_v2(
    Bucket='mineria-project',
    Prefix='models/',
    Delimiter='/'
)

models = []
for prefix in response.get('CommonPrefixes', []):
    model_path = prefix['Prefix']
    
    # Leer métricas
    try:
        obj = s3.get_object(
            Bucket='mineria-project',
            Key=f'{model_path}metrics/summary.json'
        )
        metrics = json.loads(obj['Body'].read())
        
        models.append({
            'path': model_path,
            'winner': metrics['winner']['name'],
            'accuracy': metrics['winner']['test_metrics_retrained']['accuracy'],
            'f1': metrics['winner']['test_metrics_retrained']['f1'],
            'auc_roc': metrics['winner']['test_metrics_retrained']['areaUnderROC'],
            'train_samples': metrics['train_samples'],
            'test_samples': metrics['test_samples']
        })
    except:
        pass

# Crear DataFrame
df = pd.DataFrame(models)
df = df.sort_values('auc_roc', ascending=False)
print(df)
```

---

## 🐛 Troubleshooting Rápido

### Cluster no arranca
```bash
# Ver logs de bootstrap
aws s3 ls s3://mineria-project/logs/emr/j-XXX/node/

# Ver estado detallado
aws emr describe-cluster --cluster-id j-XXX
```

### Step falla
```bash
# Ver stderr
aws s3 cp s3://mineria-project/logs/emr/j-XXX/steps/s-XXX/stderr.gz - | gunzip | tail -100

# Ver stdout
aws s3 cp s3://mineria-project/logs/emr/j-XXX/steps/s-XXX/stdout.gz - | gunzip | tail -100

# Ver controller log
aws s3 cp s3://mineria-project/logs/emr/j-XXX/steps/s-XXX/controller.gz - | gunzip
```

### Out of Memory
```bash
# Aumentar recursos en submit_training_emr.py:
--conf spark.executor.memory=12g
--conf spark.driver.memory=6g
--conf spark.executor.instances=6
```

### Cluster muy lento
```bash
# Escalar temporalmente (añadir task nodes)
aws emr modify-instance-groups \
  --cluster-id j-XXX \
  --instance-groups InstanceGroupId=ig-XXX,InstanceCount=4
```

---

## 💡 Tips

### 1. Guardar Cluster ID
```bash
# En bash
echo "export CLUSTER_ID=j-XXX" >> ~/.bashrc
source ~/.bashrc

# Uso
python scripts/submit_training_emr.py --cluster-id $CLUSTER_ID
```

### 2. Alias útiles
```bash
# Añadir a ~/.bashrc
alias emr-list='python scripts/manage_emr_cluster.py list'
alias emr-status='python scripts/manage_emr_cluster.py status --cluster-id'
alias emr-train='python scripts/submit_training_emr.py --cluster-id $CLUSTER_ID'
```

### 3. Monitoreo continuo
```bash
# Watch cluster status
watch -n 30 'aws emr describe-cluster --cluster-id j-XXX --query "Cluster.Status.State"'

# Watch steps
watch -n 30 'aws emr list-steps --cluster-id j-XXX --query "Steps[0].Status.State"'
```

### 4. Spark UI
```bash
# Obtener Master DNS
MASTER_DNS=$(aws emr describe-cluster --cluster-id j-XXX \
  --query 'Cluster.MasterPublicDnsName' --output text)

# Túnel SSH (si configuraste key)
ssh -i your-key.pem -N -L 8088:localhost:8088 hadoop@$MASTER_DNS

# Abrir en navegador
open http://localhost:8088
```

---

## 📝 Checklist Pre-Entrenamiento

- [ ] Cluster EMR activo (`WAITING` o `RUNNING`)
- [ ] Dataset disponible en S3
- [ ] Scripts subidos a S3
- [ ] Configuración revisada
- [ ] Budget alerts activas
- [ ] Backup de configuración

---

## 📞 Soporte

**Documentación Completa:**
- `docs/EMR_TRAINING.md` - Guía detallada
- `docs/DATA_PREP.md` - Preparación de datos
- `docs/TRAINING_IMPROVEMENTS.md` - Cambios y mejoras

**AWS CLI Help:**
```bash
aws emr help
aws emr create-cluster help
aws emr add-job-flow-steps help
```

**Logs del Pipeline:**
```
s3://mineria-project/logs/emr/
s3://mineria-project/logs/pipeline_report_*.json
```
