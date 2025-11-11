# 📖 Guía de Ejecución del Pipeline Minería

Esta guía explica cómo ejecutar el pipeline de procesamiento de forma **incremental**, permitiendo ejecutar un script a la vez, verificar resultados y refinar antes de continuar.

---

## 🏗️ Arquitectura de Ejecución

```
┌─────────────────────────────────────────────────────────┐
│                    PIPELINE COMPLETO                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  EC2 Instance (Scripts 01-05)                           │
│  ├── 01_procesar_sentinel.py                            │
│  ├── 02_generar_mascaras.py                             │
│  ├── 03_tabular_features.py                             │
│  ├── 04_rasterizar_labels.py                            │
│  └── 05_unir_features_labels.py                         │
│                                                          │
│  EMR Cluster (Scripts 06-07)                            │
│  ├── 06_entrenar_modelos_spark.py                       │
│  └── 07_evaluar_modelos.py                              │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Setup Inicial

### 1. Configurar Infraestructura con Terraform

```bash
cd infrastructure/

# Copiar y editar configuración
cp terraform.tfvars.example terraform.tfvars
# IMPORTANTE: Editar terraform.tfvars con tus valores

# Inicializar Terraform
terraform init

# Ver plan de ejecución
terraform plan

# Crear infraestructura
terraform apply

# Guardar outputs
terraform output > ../outputs.txt
```

**Outputs importantes:**
- `ec2_public_ip`: IP pública de la instancia EC2
- `ec2_ssh_command`: Comando para conectarte por SSH
- `bucket_name`: Nombre del bucket S3

### 2. Subir Scripts y Configuración a S3

```bash
# Desde el directorio raíz del proyecto
aws s3 sync scripts/ s3://mineria-data-dev/scripts/
aws s3 sync config/ s3://mineria-data-dev/config/

# Verificar
aws s3 ls s3://mineria-data-dev/scripts/ --recursive
```

### 3. Subir Datos Raw de Sentinel

```bash
# Subir tus archivos SAFE de Sentinel-2
aws s3 sync /path/to/sentinel/data/ s3://mineria-data-dev/raw_sentinel/

# Subir shapefiles de labels
aws s3 sync /path/to/shapefiles/ s3://mineria-data-dev/shapes/
```

### 4. Conectar a la Instancia EC2

```bash
# Opción 1: SSH
ssh -i mineria-key.pem ubuntu@<EC2_PUBLIC_IP>

# Opción 2: AWS Systems Manager (SSM)
aws ssm start-session --target <EC2_INSTANCE_ID>
```

---

## 📝 Ejecución Incremental en EC2 (Scripts 01-05)

### Flujo Recomendado

1. **Ejecutar un script**
2. **Verificar outputs en S3**
3. **Revisar logs**
4. **Si hay errores, corregir y reintentar**
5. **Continuar con el siguiente script**

### Script 01: Procesar Sentinel

```bash
# En la instancia EC2
cd /home/ubuntu/mineria_scripts

# Ejecutar script 01
python orchestration/run_ec2_pipeline.py --script 01_procesar_sentinel

# O usando el wrapper
./run_pipeline.sh --script 01_procesar_sentinel
```

**Verificar resultados:**
```bash
# Listar outputs en S3
aws s3 ls s3://mineria-data-dev/01_processed/ --recursive

# Ver logs
tail -f /home/ubuntu/mineria_logs/ec2_pipeline_*.log

# Verificar tamaño de datos procesados
aws s3 ls s3://mineria-data-dev/01_processed/ --recursive --human-readable --summarize
```

**¿Qué esperar?**
- Archivos procesados en `s3://bucket/01_processed/`
- Bandas espectrales en formato optimizado
- Índices calculados (NDVI, NDWI, etc.)

### Script 02: Generar Máscaras

```bash
# Ejecutar script 02
python orchestration/run_ec2_pipeline.py --script 02_generar_mascaras

# Verificar
aws s3 ls s3://mineria-data-dev/02_masks/ --recursive
```

**¿Qué esperar?**
- Máscaras de nubes y sombras
- Máscaras de cielo claro
- Archivos en formato raster

### Script 03: Tabular Features

```bash
# Ejecutar script 03
python orchestration/run_ec2_pipeline.py --script 03_tabular_features

# Verificar
aws s3 ls s3://mineria-data-dev/03_features/ --recursive

# Descargar un archivo de muestra para inspeccionar
aws s3 cp s3://mineria-data-dev/03_features/sample.parquet /tmp/
```

**¿Qué esperar?**
- Features tabulares en formato Parquet
- Estadísticas temporales (media, std, min, max, percentiles)
- Datos organizados por píxel

### Script 04: Rasterizar Labels

```bash
# Ejecutar script 04
python orchestration/run_ec2_pipeline.py --script 04_rasterizar_labels

# Verificar
aws s3 ls s3://mineria-data-dev/04_labels/ --recursive
```

**¿Qué esperar?**
- Labels en formato raster
- Alineados con la grilla de los features
- Valores binarios (0/1 para bosque/no-bosque)

### Script 05: Unir Features + Labels

```bash
# Ejecutar script 05
python orchestration/run_ec2_pipeline.py --script 05_unir_features_labels

# Verificar
aws s3 ls s3://mineria-data-dev/05_training_data/ --recursive

# Ver estructura del dataset
aws s3 cp s3://mineria-data-dev/05_training_data/training.parquet /tmp/
```

**¿Qué esperar?**
- Dataset unificado con features y labels
- Formato Parquet optimizado para Spark
- Balance de clases reportado en logs

### Ejecutar Pipeline Completo EC2

Si todos los scripts individuales funcionan correctamente:

```bash
# Ejecutar secuencia completa
python orchestration/run_ec2_pipeline.py --mode sequential

# O hasta cierto punto
python orchestration/run_ec2_pipeline.py --mode sequential --stop-after 03_tabular_features
```

---

## ⚡ Ejecución en EMR (Scripts 06-07)

### Opción 1: Crear Cluster y Ejecutar Script Individual

```bash
# Desde tu máquina local (no EC2)
cd scripts/orchestration/

# Ejecutar script 06
python run_emr_pipeline.py \
    --script 06_entrenar_modelos_spark \
    --create-cluster \
    --auto-terminate

# El cluster se creará, ejecutará el script y se terminará automáticamente
```

**Monitoreo:**
```bash
# Ver estado del cluster
aws emr list-clusters --active

# Ver logs del step
aws emr describe-step --cluster-id j-XXXXXXXXXXXXX --step-id s-YYYYYYYYYYYYY

# Ver logs completos en S3
aws s3 ls s3://mineria-data-dev/logs/emr/ --recursive
```

### Opción 2: Crear Cluster Persistente

```bash
# Crear cluster sin ejecutar nada
python run_emr_pipeline.py \
    --create-cluster \
    --script 06_entrenar_modelos_spark \
    --no-wait

# Esto te dará el cluster ID
# Guárdalo para uso posterior
export CLUSTER_ID="j-XXXXXXXXXXXXX"
```

**Ejecutar scripts en cluster existente:**

```bash
# Script 06: Entrenar modelos
python run_emr_pipeline.py \
    --cluster-id $CLUSTER_ID \
    --script 06_entrenar_modelos_spark

# Esperar y verificar resultados
aws s3 ls s3://mineria-data-dev/06_models/ --recursive

# Script 07: Evaluar modelos
python run_emr_pipeline.py \
    --cluster-id $CLUSTER_ID \
    --script 07_evaluar_modelos

# Ver resultados
aws s3 ls s3://mineria-data-dev/07_evaluation/ --recursive
aws s3 cp s3://mineria-data-dev/07_evaluation/metrics.json /tmp/
```

**Terminar cluster manualmente:**
```bash
aws emr terminate-clusters --cluster-ids $CLUSTER_ID
```

### Opción 3: Pipeline Completo EMR

```bash
# Crear cluster y ejecutar scripts 06-07 secuencialmente
python run_emr_pipeline.py \
    --mode sequential \
    --create-cluster \
    --auto-terminate
```

---

## 🔍 Debugging y Troubleshooting

### Ver Logs en Tiempo Real (EC2)

```bash
# En la instancia EC2
tail -f /home/ubuntu/mineria_logs/ec2_pipeline_*.log

# Logs del sistema
tail -f /var/log/user-data.log
```

### Ver Logs de EMR

```bash
# Listar logs en S3
aws s3 ls s3://mineria-data-dev/logs/emr/ --recursive

# Descargar logs de un step específico
aws s3 cp s3://mineria-data-dev/logs/emr/<cluster-id>/steps/<step-id>/ /tmp/emr-logs/ --recursive

# Ver stderr
cat /tmp/emr-logs/stderr.gz | gunzip
```

### Dry Run (Simular sin Ejecutar)

```bash
# EC2
python orchestration/run_ec2_pipeline.py --script 01_procesar_sentinel --dry-run

# EMR
python run_emr_pipeline.py --script 06_entrenar_modelos_spark --dry-run
```

### Verificar Estado de Recursos

```bash
# Ver instancia EC2
aws ec2 describe-instances --instance-ids <INSTANCE_ID>

# Ver clusters EMR
aws emr list-clusters --active

# Ver contenido de S3
aws s3 ls s3://mineria-data-dev/ --recursive --human-readable --summarize
```

---

## ⚙️ Configuración Avanzada

### Modificar Parámetros de Ejecución

Editar `config/execution_config.yaml`:

```yaml
# Ejemplo: Cambiar timeout de un script
monitoring:
  timeouts:
    "01_procesar_sentinel": 7200  # 2 horas

# Ejemplo: Modificar parámetros de un script
script_params:
  "01_procesar_sentinel":
    bands: "B02,B03,B04,B08"  # Solo estas bandas
    resolution: 10            # Mayor resolución
```

### Ejecutar con Subset de Datos (Testing)

```yaml
# En execution_config.yaml
development:
  use_sample_data: true
  sample_size: 100  # Solo 100 imágenes
```

### Continuar Pipeline desde un Punto Específico

```bash
# Si el script 02 falló, puedes continuar desde ahí
python orchestration/run_ec2_pipeline.py --mode sequential --start-from 02_generar_mascaras
```

---

## 📊 Monitoreo de Costos

### Ver Costos Actuales

```bash
# Instalar AWS Cost Explorer CLI
pip install awscli-cost-explorer

# Ver costos del mes actual
aws ce get-cost-and-usage \
    --time-period Start=2025-11-01,End=2025-11-30 \
    --granularity MONTHLY \
    --metrics BlendedCost
```

### Apagar Recursos para Ahorrar

```bash
# Detener instancia EC2 (preserva datos)
aws ec2 stop-instances --instance-ids <INSTANCE_ID>

# Terminar cluster EMR
aws emr terminate-clusters --cluster-ids <CLUSTER_ID>

# Los datos en S3 se mantienen
```

---

## 🎯 Checklist de Ejecución Completa

- [ ] **Setup inicial**
  - [ ] Infraestructura creada con Terraform
  - [ ] Scripts subidos a S3
  - [ ] Datos raw subidos a S3
  - [ ] Conexión SSH a EC2 funcionando

- [ ] **Pipeline EC2 (01-05)**
  - [ ] Script 01 ejecutado y verificado
  - [ ] Script 02 ejecutado y verificado
  - [ ] Script 03 ejecutado y verificado
  - [ ] Script 04 ejecutado y verificado
  - [ ] Script 05 ejecutado y verificado
  - [ ] Dataset de training disponible en S3

- [ ] **Pipeline EMR (06-07)**
  - [ ] Cluster EMR creado
  - [ ] Script 06 ejecutado (modelos entrenados)
  - [ ] Modelos guardados en S3
  - [ ] Script 07 ejecutado (evaluación)
  - [ ] Métricas disponibles en S3

- [ ] **Limpieza**
  - [ ] Logs descargados
  - [ ] Resultados verificados
  - [ ] Instancia EC2 detenida/terminada
  - [ ] Cluster EMR terminado

---

## 📞 Soporte

Para problemas o preguntas:

1. **Revisar logs**: Siempre empezar por los logs
2. **Verificar S3**: Asegurar que los datos estén donde se esperan
3. **Dry run**: Probar con dry-run antes de ejecutar
4. **Documentación**: Consultar README.md y docs/

---

## 🔗 Enlaces Útiles

- [AWS EMR Documentation](https://docs.aws.amazon.com/emr/)
- [Spark MLlib Guide](https://spark.apache.org/docs/latest/ml-guide.html)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Rasterio Documentation](https://rasterio.readthedocs.io/)
