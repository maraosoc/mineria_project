# 🔧 Comandos Útiles - Referencia Rápida

## 📦 Setup Inicial

### Terraform
```bash
# Configurar
cd infrastructure/
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars

# Inicializar y aplicar
terraform init
terraform plan
terraform apply

# Ver outputs
terraform output
terraform output -json > ../outputs.json
```

### Subir Scripts a S3
```bash
BUCKET="mineria-data-dev"

# Scripts
aws s3 sync scripts/ s3://$BUCKET/scripts/ --exclude "*.pyc"

# Config
aws s3 sync config/ s3://$BUCKET/config/

# Verificar
aws s3 ls s3://$BUCKET/scripts/ --recursive
```

---

## 🖥️ EC2 Commands

### Conectar
```bash
# SSH
ssh -i mineria-key.pem ubuntu@<EC2_IP>

# SSM (no requiere SSH key)
aws ssm start-session --target <INSTANCE_ID>
```

### Ver Estado
```bash
# Instancia
aws ec2 describe-instances --instance-ids <INSTANCE_ID>

# Estado
aws ec2 describe-instance-status --instance-ids <INSTANCE_ID>
```

### Control de Instancia
```bash
# Iniciar
aws ec2 start-instances --instance-ids <INSTANCE_ID>

# Detener
aws ec2 stop-instances --instance-ids <INSTANCE_ID>

# Reiniciar
aws ec2 reboot-instances --instance-ids <INSTANCE_ID>

# Terminar (CUIDADO: Elimina la instancia)
aws ec2 terminate-instances --instance-ids <INSTANCE_ID>
```

### Ver Logs
```bash
# En EC2
tail -f /var/log/user-data.log                    # Inicialización
tail -f /home/ubuntu/mineria_logs/*.log           # Pipeline
journalctl -u mineria-processing -f               # Service

# Ver últimas 100 líneas
tail -100 /home/ubuntu/mineria_logs/ec2_pipeline_*.log
```

---

## 🚀 Ejecutar Pipeline EC2

### Script Individual
```bash
# En EC2
cd /home/ubuntu/mineria_scripts

# Opción 1: Usando wrapper
./run_pipeline.sh --script 01_procesar_sentinel

# Opción 2: Directo
python orchestration/run_ec2_pipeline.py --script 01_procesar_sentinel

# Dry run (simular)
python orchestration/run_ec2_pipeline.py --script 01_procesar_sentinel --dry-run
```

### Pipeline Completo
```bash
# Secuencial completo
python orchestration/run_ec2_pipeline.py --mode sequential

# Hasta cierto punto
python orchestration/run_ec2_pipeline.py --mode sequential --stop-after 03_tabular_features
```

### Verificar Resultados
```bash
# Listar outputs
aws s3 ls s3://$BUCKET/01_processed/ --recursive
aws s3 ls s3://$BUCKET/02_masks/ --recursive
aws s3 ls s3://$BUCKET/03_features/ --recursive

# Tamaño total
aws s3 ls s3://$BUCKET/01_processed/ --recursive --human-readable --summarize

# Descargar muestra
aws s3 cp s3://$BUCKET/03_features/sample.parquet /tmp/
```

---

## ⚡ EMR Commands

### Crear y Ejecutar (Desde tu máquina local)
```bash
cd scripts/orchestration/

# Script individual con cluster nuevo
python run_emr_pipeline.py \
    --script 06_entrenar_modelos_spark \
    --create-cluster \
    --auto-terminate

# Usar cluster existente
python run_emr_pipeline.py \
    --script 06_entrenar_modelos_spark \
    --cluster-id j-XXXXXXXXXXXXX

# Pipeline completo
python run_emr_pipeline.py \
    --mode sequential \
    --create-cluster \
    --auto-terminate
```

### Gestión de Clusters
```bash
# Listar clusters
aws emr list-clusters                              # Todos
aws emr list-clusters --active                     # Activos
aws emr list-clusters --created-after 2025-11-01   # Filtrado

# Detalles de cluster
aws emr describe-cluster --cluster-id j-XXXXXXXXXXXXX

# Terminar cluster
aws emr terminate-clusters --cluster-ids j-XXXXXXXXXXXXX

# Terminar todos los clusters activos (CUIDADO!)
for cluster in $(aws emr list-clusters --active --query 'Clusters[*].Id' --output text); do
    aws emr terminate-clusters --cluster-ids $cluster
done
```

### Monitoreo de Steps
```bash
# Listar steps
aws emr list-steps --cluster-id j-XXXXXXXXXXXXX

# Detalles de step
aws emr describe-step \
    --cluster-id j-XXXXXXXXXXXXX \
    --step-id s-YYYYYYYYYYYYY

# Ver logs de step
aws s3 ls s3://$BUCKET/logs/emr/j-XXXXXXXXXXXXX/steps/ --recursive

# Descargar logs
aws s3 cp s3://$BUCKET/logs/emr/j-XXXXXXXXXXXXX/steps/s-YYYYY/ /tmp/logs/ --recursive
```

---

## 💾 S3 Commands

### Navegación
```bash
BUCKET="mineria-data-dev"

# Listar todo
aws s3 ls s3://$BUCKET/ --recursive

# Por directorio
aws s3 ls s3://$BUCKET/01_processed/
aws s3 ls s3://$BUCKET/06_models/

# Con tamaño
aws s3 ls s3://$BUCKET/01_processed/ --recursive --human-readable --summarize
```

### Subir/Descargar
```bash
# Subir archivo
aws s3 cp local_file.txt s3://$BUCKET/path/

# Subir directorio
aws s3 sync local_dir/ s3://$BUCKET/path/

# Descargar
aws s3 cp s3://$BUCKET/path/file.txt ./
aws s3 sync s3://$BUCKET/path/ ./local_dir/
```

### Eliminar
```bash
# Archivo
aws s3 rm s3://$BUCKET/path/file.txt

# Directorio
aws s3 rm s3://$BUCKET/path/ --recursive

# Limpiar datos de prueba
aws s3 rm s3://$BUCKET/01_processed/ --recursive
aws s3 rm s3://$BUCKET/02_masks/ --recursive
```

### Sincronizar
```bash
# Local → S3
aws s3 sync ./scripts/ s3://$BUCKET/scripts/ --delete

# S3 → Local
aws s3 sync s3://$BUCKET/scripts/ ./scripts_backup/

# Dry run (ver qué se subiría)
aws s3 sync ./scripts/ s3://$BUCKET/scripts/ --dryrun
```

---

## 🔍 Debugging

### Logs Detallados
```bash
# EC2: Pipeline logs
ssh ubuntu@<EC2_IP>
cd /home/ubuntu/mineria_logs
ls -lth                                    # Ordenados por fecha
tail -f ec2_pipeline_$(date +%Y%m%d)*.log

# EC2: System logs
tail -f /var/log/cloud-init-output.log
tail -f /var/log/user-data.log

# EMR: Logs en S3
aws s3 ls s3://$BUCKET/logs/emr/ --recursive
```

### Estado de Recursos
```bash
# EC2
aws ec2 describe-instances \
    --instance-ids <INSTANCE_ID> \
    --query 'Reservations[0].Instances[0].State'

# EMR
aws emr describe-cluster \
    --cluster-id j-XXXXXXXXXXXXX \
    --query 'Cluster.Status.State'

# S3
aws s3api head-object \
    --bucket $BUCKET \
    --key 01_processed/file.tif
```

### Test Conectividad
```bash
# Desde EC2 a S3
aws s3 ls s3://$BUCKET/

# Python dependencies
source /home/ubuntu/mineria_venv/bin/activate
pip list

# GDAL
gdalinfo --version
python -c "import rasterio; print(rasterio.__version__)"
```

---

## 📊 Monitoreo de Costos

### Ver Costos
```bash
# Mes actual
aws ce get-cost-and-usage \
    --time-period Start=$(date -d "$(date +%Y-%m-01)" +%Y-%m-%d),End=$(date +%Y-%m-%d) \
    --granularity MONTHLY \
    --metrics BlendedCost

# Por servicio
aws ce get-cost-and-usage \
    --time-period Start=2025-11-01,End=2025-11-30 \
    --granularity MONTHLY \
    --metrics BlendedCost \
    --group-by Type=DIMENSION,Key=SERVICE
```

### Recursos Activos
```bash
# EC2 instances running
aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=running" \
    --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,State.Name]' \
    --output table

# EMR clusters running
aws emr list-clusters --active

# Volúmenes EBS
aws ec2 describe-volumes \
    --filters "Name=status,Values=available" \
    --query 'Volumes[*].[VolumeId,Size,State]' \
    --output table
```

---

## 🧹 Limpieza

### Detener Todo
```bash
# EC2
aws ec2 stop-instances --instance-ids <INSTANCE_ID>

# EMR
aws emr terminate-clusters --cluster-ids j-XXXXXXXXXXXXX
```

### Limpiar S3 (Mantener estructura)
```bash
# Solo outputs (mantener raw data)
aws s3 rm s3://$BUCKET/01_processed/ --recursive
aws s3 rm s3://$BUCKET/02_masks/ --recursive
aws s3 rm s3://$BUCKET/03_features/ --recursive
aws s3 rm s3://$BUCKET/04_labels/ --recursive
aws s3 rm s3://$BUCKET/05_training_data/ --recursive
aws s3 rm s3://$BUCKET/06_models/ --recursive
aws s3 rm s3://$BUCKET/07_evaluation/ --recursive

# Logs antiguos (más de 30 días)
aws s3 ls s3://$BUCKET/logs/ --recursive | \
    awk '$1 < "'$(date -d '30 days ago' +%Y-%m-%d)'" {print $4}' | \
    xargs -I {} aws s3 rm s3://$BUCKET/{}
```

### Destruir Infraestructura
```bash
cd infrastructure/

# Ver qué se eliminará
terraform plan -destroy

# Eliminar todo
terraform destroy

# Confirmar eliminación manual de S3 si es necesario
aws s3 rb s3://$BUCKET --force
```

---

## 🔐 Configuración AWS CLI

### Profiles
```bash
# Configurar profile
aws configure --profile mineria
# Ingresar: Access Key ID, Secret Access Key, Region

# Usar profile
export AWS_PROFILE=mineria

# O en cada comando
aws s3 ls --profile mineria
```

### Verificar Credenciales
```bash
# Usuario actual
aws sts get-caller-identity

# Región
aws configure get region

# Test acceso S3
aws s3 ls
```

---

## 📋 Scripts de Mantenimiento

### Backup de Configuración
```bash
# Backup de configs
tar -czf mineria-config-backup-$(date +%Y%m%d).tar.gz \
    config/ \
    infrastructure/terraform.tfvars \
    infrastructure/*.tf

# Subir a S3
aws s3 cp mineria-config-backup-*.tar.gz s3://$BUCKET/backups/
```

### Verificación de Health
```bash
# Script rápido de health check
cat > health_check.sh << 'EOF'
#!/bin/bash
echo "=== Health Check ==="
echo "EC2 Instance: $(aws ec2 describe-instances --instance-ids <ID> --query 'Reservations[0].Instances[0].State.Name' --output text)"
echo "EMR Clusters: $(aws emr list-clusters --active --query 'Clusters[*].Id' --output text | wc -w) active"
echo "S3 Bucket: $(aws s3 ls s3://$BUCKET/ 2>&1 | grep -c 'An error' && echo 'Error' || echo 'OK')"
EOF
chmod +x health_check.sh
```

---

## 💡 Tips y Trucos

### Aliases Útiles
```bash
# Agregar a ~/.bashrc o ~/.zshrc
alias ec2-connect='ssh -i mineria-key.pem ubuntu@<EC2_IP>'
alias s3-ls='aws s3 ls s3://mineria-data-dev/'
alias emr-list='aws emr list-clusters --active'
alias tf-apply='cd infrastructure && terraform apply && cd ..'
```

### Variables de Entorno
```bash
# En ~/.bashrc
export MINERIA_BUCKET="mineria-data-dev"
export MINERIA_EC2_ID="i-XXXXXXXXXXXXX"
export MINERIA_REGION="us-east-1"

# Usar
aws s3 ls s3://$MINERIA_BUCKET/
```

### Watch Commands
```bash
# Monitorear estado EC2
watch -n 30 'aws ec2 describe-instances --instance-ids <ID> --query "Reservations[0].Instances[0].State"'

# Monitorear EMR step
watch -n 30 'aws emr describe-step --cluster-id j-XXX --step-id s-YYY --query "Step.Status"'
```

---

**🎯 Guarda este archivo para referencia rápida!**
