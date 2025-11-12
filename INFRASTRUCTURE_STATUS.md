# Estado de la Infraestructura - Proyecto Mineria

**Fecha**: 2025-11-12 16:22 UTC  
**Estado**: ✅ **DESPLEGADA EXITOSAMENTE**

---

## 📊 Resumen Ejecutivo

✅ **26 recursos creados** exitosamente  
✅ **Roles IAM creados** con permisos correctos  
✅ **Instancia EC2 ejecutándose** (t3.xlarge)  
✅ **Políticas S3 adjuntas** correctamente  
✅ **Infraestructura EMR preparada** (sin cluster activo)

---

## 🖥️ Instancia EC2 (Scripts 01-05)

### Detalles
- **Instance ID**: `i-08a5477ac5e3f4d33`
- **Public IP**: `3.238.21.249`
- **Estado**: `running` ✅
- **Tipo**: `t3.xlarge` (4 vCPU, 16 GB RAM)
- **Instance Profile**: `mineria-ec2-processing-profile-dev`

### Conexión
```bash
# Via SSH
ssh -i mineria-ec2-key.pem ubuntu@3.238.21.249

# Via SSM (recomendado)
aws ssm start-session --target i-08a5477ac5e3f4d33
```

### Roles y Políticas IAM
**Rol**: `mineria-ec2-processing-role-dev`  
**ARN**: `arn:aws:iam::264483381923:role/mineria-ec2-processing-role-dev`  
**Creado**: 2025-11-12 16:22:41 UTC

**Políticas Adjuntas**:
1. ✅ `mineria-ec2-s3-access-dev` (Custom)
   - Permisos: s3:GetObject, s3:PutObject, s3:DeleteObject, s3:ListBucket
   - Bucket: `mineria-project`
   
2. ✅ `AmazonSSMManagedInstanceCore` (AWS Managed)
   - Permisos: Acceso SSM para administración remota

---

## 📦 Amazon EMR (Scripts 06-07)

### Estado
- **Cluster**: No creado (on-demand)
- **Infraestructura IAM**: ✅ Preparada

### Roles IAM Creados

#### 1. Rol de Servicio EMR
**Rol**: `mineria-emr-service-role-dev`  
**ARN**: `arn:aws:iam::264483381923:role/mineria-emr-service-role-dev`  
**Creado**: 2025-11-12 16:22:41 UTC

**Políticas Adjuntas**:
- ✅ `AmazonElasticMapReduceRole` (AWS Managed)

#### 2. Rol EC2 para Nodos EMR
**Rol**: `mineria-emr-ec2-role-dev`  
**ARN**: `arn:aws:iam::264483381923:role/mineria-emr-ec2-role-dev`  
**Creado**: 2025-11-12 16:22:41 UTC

**Políticas Adjuntas**:
1. ✅ `mineria-emr-s3-access-dev` (Custom)
   - Permisos S3 para leer/escribir datos
   
2. ✅ `AmazonElasticMapReduceforEC2Role` (AWS Managed)
   - Permisos estándar para nodos EMR

#### 3. Instance Profile
**Profile**: `mineria-emr-ec2-profile-dev`  
**ARN**: `arn:aws:iam::264483381923:instance-profile/mineria-emr-ec2-profile-dev`

---

## 🪣 Buckets S3

### 1. Bucket Principal
- **Nombre**: `mineria-project`
- **Estado**: Existente (referenciado)
- **Contenido**: 15 zonas de datos Sentinel-2 (~115.9 GB)

### 2. Bucket de Datos (Dev)
- **Nombre**: `mineria-data-dev`
- **Versioning**: ✅ Enabled
- **Encriptación**: ✅ AES256
- **Public Access**: ❌ Bloqueado

**Lifecycle Rules**:
- Logs: Expiración a 90 días
- Raw Sentinel: Transición a STANDARD_IA (30d) → GLACIER (90d)

### 3. Bucket de Logs
- **Nombre**: `mineria-logs-dev`
- **Uso**: Logs de EMR
- **Public Access**: ❌ Bloqueado
- **Política**: Acceso para servicio EMR

---

## 🔐 Security Groups

### 1. EC2 Processing
- **Nombre**: `mineria-ec2-processing-dev`
- **ID**: `sg-092920970e63e0450`
- **Ingress**: 
  - SSH (22/tcp) desde 0.0.0.0/0
- **Egress**: Todo el tráfico permitido

### 2. EMR Master
- **Nombre**: `mineria-emr-master-dev`
- **ID**: `sg-041f35344a9bf68e1`
- **Ingress**:
  - SSH (22/tcp) desde 0.0.0.0/0
  - Spark UI (8088/tcp) desde 0.0.0.0/0
  - Comunicación desde EMR slaves

### 3. EMR Slave
- **Nombre**: `mineria-emr-slave-dev`
- **ID**: `sg-0be6722a801405242`
- **Ingress**:
  - Comunicación desde EMR master

---

## 📋 Recursos Creados (Terraform State)

### Data Sources (6)
- ✅ `data.aws_s3_bucket.project_bucket`
- ✅ `data.aws_subnets.default`
- ✅ `data.aws_vpc.default`
- ✅ `module.ec2_processing.data.aws_ami.ubuntu`
- ✅ `module.ec2_processing.data.template_file.user_data`

### S3 Resources (7)
- ✅ `aws_s3_bucket.data_bucket`
- ✅ `aws_s3_bucket.logs_bucket`
- ✅ `aws_s3_bucket_lifecycle_configuration.data_bucket_lifecycle`
- ✅ `aws_s3_bucket_policy.logs_bucket_policy`
- ✅ `aws_s3_bucket_public_access_block.data_bucket_public_access`
- ✅ `aws_s3_bucket_public_access_block.logs_bucket_public_access`
- ✅ `aws_s3_bucket_server_side_encryption_configuration.data_bucket_encryption`
- ✅ `aws_s3_bucket_versioning.data_bucket_versioning`

### EC2 Module (8)
- ✅ `module.ec2_processing.aws_iam_instance_profile.ec2_processing`
- ✅ `module.ec2_processing.aws_iam_policy.ec2_s3_access`
- ✅ `module.ec2_processing.aws_iam_role.ec2_processing`
- ✅ `module.ec2_processing.aws_iam_role_policy_attachment.ec2_s3_attach`
- ✅ `module.ec2_processing.aws_iam_role_policy_attachment.ec2_ssm_attach`
- ✅ `module.ec2_processing.aws_instance.processing`
- ✅ `module.ec2_processing.aws_security_group.ec2_processing`

### EMR Module (10)
- ✅ `module.emr_cluster.aws_iam_instance_profile.emr_ec2_profile`
- ✅ `module.emr_cluster.aws_iam_policy.emr_s3_access`
- ✅ `module.emr_cluster.aws_iam_role.emr_ec2_role`
- ✅ `module.emr_cluster.aws_iam_role.emr_service_role`
- ✅ `module.emr_cluster.aws_iam_role_policy_attachment.emr_ec2_policy`
- ✅ `module.emr_cluster.aws_iam_role_policy_attachment.emr_s3_attach`
- ✅ `module.emr_cluster.aws_iam_role_policy_attachment.emr_service_policy`
- ✅ `module.emr_cluster.aws_security_group.emr_master`
- ✅ `module.emr_cluster.aws_security_group.emr_slave`
- ✅ `module.emr_cluster.aws_security_group_rule.emr_master_to_slave`
- ✅ `module.emr_cluster.aws_security_group_rule.emr_slave_to_master`

**Total**: 31 recursos en Terraform State

---

## 🎯 Próximos Pasos

### 1. Subir Scripts y Configuración a S3
```bash
cd c:\Users\Raspu\GitHub\mineria_project
aws s3 sync scripts/ s3://mineria-project/scripts/ --exclude "*.pyc" --exclude "__pycache__/*"
aws s3 sync config/ s3://mineria-project/config/
```

### 2. Verificar User Data Script en EC2
El script `user_data.sh` se ejecuta automáticamente al inicio:
- Instala Python 3.10
- Instala GDAL y dependencias geoespaciales
- Crea entorno virtual
- Descarga scripts desde S3
- Configura estructura de directorios

**Verificar logs**:
```bash
ssh -i mineria-ec2-key.pem ubuntu@3.238.21.249
tail -f /var/log/user-data.log
```

### 3. Ejecutar Procesamiento de Zonas

**Opción A - Todas las zonas**:
```bash
ssh -i mineria-ec2-key.pem ubuntu@3.238.21.249
cd /home/ubuntu/mineria_scripts
source venv/bin/activate
python run_01_all_zones.py
```

**Opción B - Zona individual**:
```bash
python scripts/01_procesar_sentinel.py \
  --input s3://mineria-project/raw/raw_copernicus/14_ElDanubio_Granada_Meta/ \
  --output s3://mineria-project/staging/01_rasters_procesados/ \
  --zone_name 14_ElDanubio_Granada_Meta
```

### 4. Monitorear Ejecución
- **Logs EC2**: `/var/log/user-data.log`
- **CloudWatch**: Métricas de CPU/Memoria
- **S3**: Verificar outputs en `s3://mineria-project/staging/01_rasters_procesados/`

---

## 💰 Costos Estimados

### EC2 t3.xlarge (en ejecución)
- **Costo/hora**: ~$0.166
- **Costo/día**: ~$4.00
- **Recomendación**: Detener cuando no esté procesando

### S3 Storage
- **Datos existentes**: 115.9 GB (~$2.66/mes)
- **Outputs esperados**: ~150 GB adicionales (~$3.45/mes)

### EMR (cuando se cree)
- **Master (m5.xlarge)**: ~$0.192/hora
- **Workers (2x m5.2xlarge)**: ~$0.768/hora
- **Total cluster**: ~$0.96/hora
- **Recomendación**: Crear on-demand, terminar después de uso

---

## 🔧 Comandos Útiles

### Ver outputs de Terraform
```bash
cd infrastructure
terraform output
```

### Ver estado de EC2
```bash
aws ec2 describe-instances --instance-ids i-08a5477ac5e3f4d33
```

### Detener EC2 (cuando no se use)
```bash
aws ec2 stop-instances --instance-ids i-08a5477ac5e3f4d33
```

### Iniciar EC2
```bash
aws ec2 start-instances --instance-ids i-08a5477ac5e3f4d33
```

### Ver logs de user-data
```bash
ssh -i mineria-ec2-key.pem ubuntu@3.238.21.249
sudo cat /var/log/cloud-init-output.log
```

---

## ✅ Checklist de Validación

- [x] Terraform apply exitoso
- [x] Roles IAM creados con permisos correctos
- [x] Políticas S3 adjuntas correctamente
- [x] EC2 en estado `running`
- [x] Instance Profile asignado a EC2
- [x] Security Groups configurados
- [x] Buckets S3 creados
- [ ] Scripts subidos a S3
- [ ] User data script completado (verificar logs)
- [ ] Primera ejecución de script 01 exitosa

---

## 📞 Troubleshooting

### Si EC2 no responde
```bash
# Ver logs en consola AWS
aws ec2 get-console-output --instance-id i-08a5477ac5e3f4d33

# Reiniciar instancia
aws ec2 reboot-instances --instance-ids i-08a5477ac5e3f4d33
```

### Si hay errores de permisos S3
```bash
# Verificar políticas adjuntas
aws iam list-attached-role-policies --role-name mineria-ec2-processing-role-dev

# Ver contenido de política
aws iam get-policy-version \
  --policy-arn arn:aws:iam::264483381923:policy/mineria-ec2-s3-access-dev \
  --version-id v1
```

### Si EMR falla al crear
```bash
# Verificar roles
aws iam get-role --role-name mineria-emr-service-role-dev
aws iam get-role --role-name mineria-emr-ec2-role-dev
```

---

## 📚 Documentación Relacionada

- `docs/AWS_SETUP.md` - Configuración inicial AWS
- `docs/IAM_PERMISSIONS_REQUIRED.md` - Permisos IAM requeridos
- `MIGRATION_SUMMARY.md` - Resumen de migración del proyecto
- `RESUMEN_EJECUTIVO.md` - Visión general del proyecto

---

**Última actualización**: 2025-11-12 16:30 UTC  
**Mantenido por**: Equipo Proyecto Mineria
