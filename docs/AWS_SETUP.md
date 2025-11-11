# Guía de Configuración AWS

Guía paso a paso para configurar la infraestructura AWS necesaria para el proyecto.

---

## 📋 Requisitos Previos

### 1. Cuenta AWS
- Cuenta AWS activa
- Permisos de administrador o permisos para:
  - EMR
  - S3
  - IAM
  - EC2
  - VPC

### 2. Herramientas Locales
```bash
# AWS CLI
aws --version  # >= 2.13.0

# Terraform
terraform --version  # >= 1.0.0

# Python
python --version  # >= 3.9
```

---

## 🚀 Setup Paso a Paso

### Paso 1: Configurar AWS CLI

```bash
# Configurar credenciales
aws configure

# Verificar acceso
aws sts get-caller-identity
```

**Salida esperada**:
```json
{
    "UserId": "AIDACKCEVSQ6C2EXAMPLE",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/tu-usuario"
}
```

---

### Paso 2: Crear Key Pair para EMR

```bash
# Crear key pair
aws ec2 create-key-pair \
  --key-name mineria-emr-key \
  --query 'KeyMaterial' \
  --output text > mineria-emr-key.pem

# Cambiar permisos (Linux/Mac)
chmod 400 mineria-emr-key.pem
```

**⚠️ Guardar este archivo en lugar seguro** - Se necesita para SSH al cluster.

---

### Paso 3: Crear Roles IAM para EMR

```bash
# Crear EMR Service Role
aws emr create-default-roles

# Verificar roles creados
aws iam list-roles | grep EMR
```

**Roles creados**:
- `EMR_DefaultRole` - Rol del servicio EMR
- `EMR_EC2_DefaultRole` - Rol de instancias EC2

---

### Paso 4: Desplegar Infraestructura con Terraform

```bash
cd terraform/

# Inicializar Terraform
terraform init

# Ver plan de ejecución
terraform plan

# Aplicar cambios
terraform apply
```

**Recursos creados**:
- ✅ S3 bucket: `mineria-data-dev`
- ✅ S3 bucket logs: `mineria-logs-dev`
- ✅ EMR Cluster (opcional)
- ✅ Security Groups
- ✅ IAM Policies

**Salida**:
```
Apply complete! Resources: 8 added, 0 changed, 0 destroyed.

Outputs:

bucket_name = "mineria-data-dev"
emr_cluster_id = "j-XXXXXXXXXXXXX"
```

---

### Paso 5: Subir Scripts y Configuración a S3

```bash
# Volver al directorio raíz del proyecto
cd ..

# Subir scripts
aws s3 sync scripts/ s3://mineria-data-dev/scripts/ \
  --exclude "*.pyc" \
  --exclude "__pycache__/*"

# Subir configuración
aws s3 sync config/ s3://mineria-data-dev/config/

# Verificar
aws s3 ls s3://mineria-data-dev/scripts/ --recursive
```

---

### Paso 6: Subir Datos Raw

```bash
# Subir archivos SAFE de Sentinel-2
aws s3 sync /path/to/safe/files/ s3://mineria-data-dev/raw_sentinel/ \
  --exclude "*" \
  --include "*.SAFE/*"

# Subir shapefiles
aws s3 sync shapes/ s3://mineria-data-dev/shapes/

# Verificar tamaño total
aws s3 ls s3://mineria-data-dev/ --recursive --human-readable --summarize
```

---

### Paso 7: Crear Cluster EMR (Opcional)

Si no lo creaste con Terraform, puedes crear un cluster manualmente:

```bash
python scripts/submit_emr_steps.py \
  --create-cluster \
  --config config/aws_config.yaml
```

O desde AWS CLI:

```bash
aws emr create-cluster \
  --name "Mineria-Spark-Cluster" \
  --release-label emr-7.0.0 \
  --applications Name=Spark Name=Hadoop \
  --ec2-attributes KeyName=mineria-emr-key \
  --instance-type m5.xlarge \
  --instance-count 3 \
  --use-default-roles \
  --log-uri s3://mineria-logs-dev/emr/
```

---

## 🔍 Verificación

### Verificar Bucket S3

```bash
aws s3 ls s3://mineria-data-dev/

# Salida esperada:
#                           PRE config/
#                           PRE raw_sentinel/
#                           PRE scripts/
#                           PRE shapes/
```

### Verificar Cluster EMR

```bash
# Listar clusters
aws emr list-clusters --active

# Describir cluster específico
aws emr describe-cluster --cluster-id j-XXXXXXXXXXXXX
```

### Test de Conectividad S3

```python
import boto3

s3 = boto3.client('s3')
response = s3.list_objects_v2(Bucket='mineria-data-dev', Prefix='scripts/', MaxKeys=10)

for obj in response.get('Contents', []):
    print(f"  {obj['Key']}")
```

---

## 💰 Estimación de Costos

### S3 Storage
- **100 GB**: ~$2.30/mes
- **1 TB**: ~$23/mes

### EMR Cluster (por hora)
| Configuración | Costo/hora | Costo/día (8h) | Costo/mes (30 días, 8h/día) |
|---------------|------------|----------------|------------------------------|
| **Dev** (1 master + 2 core m5.xlarge) | $0.30 | $2.40 | $72 |
| **Prod** (1 master + 5 core m5.2xlarge) | $0.80 | $6.40 | $192 |
| **Prod Spot** (60% descuento) | $0.32 | $2.56 | $76.80 |

### Data Transfer
- **S3 → EMR**: Gratis (misma región)
- **EMR → Internet**: $0.09/GB

**💡 Recomendaciones para reducir costos**:
1. ✅ Usar **Spot Instances** (60-70% más barato)
2. ✅ Configurar **Auto-termination** (1-2 horas de idle)
3. ✅ Habilitar **S3 Lifecycle Policies** (mover datos antiguos a Glacier)
4. ✅ Usar **EMR Serverless** para cargas esporádicas

---

## 🔒 Seguridad

### 1. Encriptación

S3 buckets ya tienen encriptación habilitada (AES-256):
```bash
aws s3api get-bucket-encryption --bucket mineria-data-dev
```

### 2. Acceso IAM

Verificar políticas:
```bash
aws iam get-role-policy \
  --role-name EMR_EC2_DefaultRole \
  --policy-name EMR_EC2_DefaultRole_Policy
```

### 3. Security Groups

Revisar reglas del cluster:
```bash
aws emr describe-cluster --cluster-id j-XXXXXXXXXXXXX \
  --query 'Cluster.Ec2InstanceAttributes.EmrManagedMasterSecurityGroup'
```

**Recomendaciones**:
- ✅ Restringir acceso SSH solo a tu IP
- ✅ No abrir puertos innecesarios
- ✅ Usar VPC privada para EMR

---

## 🐛 Troubleshooting

### Error: "Access Denied" al acceder S3

```bash
# Verificar permisos del rol
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::ACCOUNT_ID:role/EMR_EC2_DefaultRole \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::mineria-data-dev/*
```

### Error: EMR cluster no inicia

```bash
# Ver logs del cluster
aws emr describe-cluster --cluster-id j-XXXXXXXXXXXXX \
  --query 'Cluster.Status.StateChangeReason'

# Descargar logs
aws s3 sync s3://mineria-logs-dev/emr/j-XXXXXXXXXXXXX/ ./emr_logs/
```

### Error: "Insufficient capacity"

Cambiar tipo de instancia o región:
```yaml
# config/aws_config.yaml
emr:
  master_instance:
    type: m5.large  # En lugar de m5.xlarge
```

---

## 📚 Referencias

- [AWS EMR Documentation](https://docs.aws.amazon.com/emr/)
- [S3 Pricing](https://aws.amazon.com/s3/pricing/)
- [EMR Pricing](https://aws.amazon.com/emr/pricing/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

---

## ✅ Checklist de Setup

- [ ] AWS CLI configurado
- [ ] Key pair creado (`mineria-emr-key.pem`)
- [ ] Roles IAM creados (EMR_DefaultRole, EMR_EC2_DefaultRole)
- [ ] Terraform aplicado exitosamente
- [ ] Buckets S3 creados y verificados
- [ ] Scripts subidos a S3
- [ ] Datos raw subidos a S3
- [ ] Cluster EMR creado (opcional)
- [ ] Test de conectividad S3 exitoso
- [ ] Bootstrap script funcional

---

**Siguiente paso**: [Ejecutar Pipeline](../README.md#ejecución)
