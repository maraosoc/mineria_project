# DATA_PREP - Preparación de Datos para Detección de Deforestación

## 📋 Resumen Ejecutivo

Este documento describe el proceso completo de preparación de datos para el proyecto de detección de deforestación mediante imágenes Sentinel-2 y machine learning. El pipeline procesa 6 zonas geográficas en Colombia, generando un dataset consolidado de 8,008 muestras con 15 features espectrales.

**Dataset final:** `s3://mineria-project/data/all/training_data_all_zones.parquet`

---

## 🔄 Pipeline de Procesamiento

### **Paso 1: Descarga y Procesamiento de Imágenes Sentinel-2**

**Script:** `01_procesar_sentinel_clip.py`

**Entrada:**
- Imágenes Sentinel-2 L2A desde `s3://mineria-project/raw/raw_copernicus/ZONA/`
- Shapefiles de perímetro desde `s3://mineria-project/raw/shapes/ZONA/Perímetro.shp`

**Procesamiento:**
1. Descarga de imágenes .SAFE desde S3
2. Extracción de bandas espectrales (B02-B08, B8A, B11, B12)
3. Remuestreo a resolución común (10m)
4. Reproyección a EPSG:4326 (WGS84)
5. Recorte (clipping) al perímetro de la zona
6. Cálculo de máscara de calidad (Scene Classification Layer)

**Salida:**
- Rasters procesados en `s3://mineria-project/staging/01_rasters_procesados_clipped/ZONA/`
- Formato: GeoTIFF multiband con 10 bandas espectrales

---

### **Paso 2: Tabulación de Features Espectrales**

**Script:** `03_tabular_features.py`

**Entrada:**
- Rasters procesados del Paso 1

**Procesamiento:**
1. **Descubrimiento de rasters:** Lista todos los GeoTIFF disponibles por zona
2. **Extracción pixel-a-pixel:**
   - Lee cada raster banda por banda
   - Extrae coordenadas (x, y) y fecha de captura
   - Filtra píxeles con nodata (-9999)
   - Almacena valores espectrales: B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12
3. **Composición temporal:**
   - Agrupa píxeles por coordenadas (x, y)
   - Calcula estadísticos por banda:
     - **Mediana** (`B02_med`, `B03_med`, ..., `B12_med`)
     - **Percentil 25** (`B02_p25`, `B03_p25`, ..., `B12_p25`)
     - **Percentil 75** (`B02_p75`, `B03_p75`, ..., `B12_p75`)
   - Cuenta observaciones por píxel (`n_obs`)
4. **Generación de tabla:**
   - Formato Parquet con librería Polars
   - **15 features finales** (medianas de 10 bandas + estadísticos adicionales)

**Salida:**
- `composite_annual.parquet`: Tabla con features por píxel
- `observations_all.parquet`: Observaciones crudas antes de agregación

**Estructura del composite:**
```
Columnas: x, y, fecha, B02_med, B03_med, B04_med, B05_med, B06_med, 
          B07_med, B08_med, B8A_med, B11_med, B12_med, B02_p25, 
          B03_p25, B04_p25, n_obs (total: 17 columnas)
```

---

### **Paso 3: Rasterización de Etiquetas (Labels)**

**Script:** `04_rasterizar_labels.py`

**Entrada:**
- Raster de referencia (para dimensiones y georreferenciación)
- `Bosque.shp`: Polígonos de áreas con cobertura forestal
- `Perímetro.shp`: Límite del área de estudio

**Procesamiento:**
1. **Reproyección:** Transforma shapefiles al CRS del raster (EPSG:4326)
2. **Unificación de geometrías:** Fusiona múltiples polígonos en geometría única
3. **Rasterización de bosque:**
   - Quema geometría de bosque en raster con valor 1
   - Resto de píxeles = 0
4. **Erosión morfológica:**
   - Aplica erosión de N píxeles (por defecto 1) en bordes de bosque
   - **Objetivo:** Eliminar píxeles de borde con mezcla espectral (efecto edge)
   - **Resultado:** Reduce píxeles de bosque pero aumenta pureza de clases
5. **Construcción de máscara final:**
   - **1** = Bosque (positivo, después de erosión)
   - **0** = No-Bosque (dentro del perímetro, sin bosque)
   - **-1** = Ignorar (fuera del perímetro o sin datos)

**Salida:**
- `forest_labels.tif`: Raster de etiquetas (int16, nodata=-1)

**Efecto de la erosión:**
```
Pre-erosión:  1,114 píxeles de bosque
Post-erosión: 1,104 píxeles de bosque
Removidos:    10 píxeles (bordes contaminados)
```

---

### **Paso 4: Unión de Features + Labels**

**Script:** `05_unir_features_labels.py`

**Entrada:**
- `composite_annual.parquet`: Features espectrales
- `forest_labels.tif`: Etiquetas rasterizadas

**Procesamiento:**
1. **Carga de features:** Lee tabla Parquet con coordenadas (x, y)
2. **Extracción de labels:**
   - Para cada coordenada (x, y) en el composite
   - Muestrea el valor del raster de labels en esa posición
   - Asigna label (1, 0, o -1) a cada píxel
3. **Filtrado:**
   - Elimina píxeles con `label = -1` (fuera del perímetro)
   - Mantiene solo muestras válidas (bosque o no-bosque)
4. **Generación de tabla de entrenamiento:**
   - Combina features (15 bandas) + label (1 columna)
   - Formato: Parquet con 18 columnas totales

**Salida:**
- `training_data.parquet`: Tabla final por zona

**Estructura de training_data:**
```
Columnas:
  - x, y: Coordenadas geográficas
  - fecha: Fecha de captura
  - B02_med, B03_med, B04_med, B05_med, B06_med, B07_med, B08_med, 
    B8A_med, B11_med, B12_med: Medianas espectrales (10 features)
  - B02_p25, B03_p25, B04_p25: Percentiles 25 (3 features)
  - B02_p75, B03_p75: Percentiles 75 (2 features)
  - label: Etiqueta binaria (0 o 1)
  - n_obs: Número de observaciones

Total: 18 columnas (15 features + 3 metadata)
```

---

### **Paso 5: Consolidación Multi-Zona**

**Script:** `process_all_zones_pipeline.py`

**Procesamiento:**
1. **Descubrimiento automático de zonas** desde S3
2. **Validación:** Verifica que cada zona tenga rasters y shapefiles
3. **Ejecución secuencial:** Ejecuta pasos 2-4 para cada zona
4. **Consolidación:**
   - Lee todos los `training_data.parquet` individuales
   - Añade columna `zone` identificadora
   - Concatena en un solo DataFrame
5. **Generación de reporte:**
   - Estadísticas por zona (balance de clases, ratio, muestras)
   - Estadísticas globales del dataset consolidado
   - Reporte en formato JSON y texto

**Salida:**
- `training_data_all_zones.parquet`: Dataset consolidado
- `pipeline_report_YYYYMMDD_HHMMSS.json`: Reporte de ejecución

---

## 📊 Estadísticas del Dataset Final

### **Resumen General**

| Métrica | Valor |
|---------|-------|
| **Archivo** | `s3://mineria-project/data/all/training_data_all_zones.parquet` |
| **Total de muestras** | 8,008 píxeles |
| **Clase Bosque (1)** | 1,820 píxeles (22.7%) |
| **Clase No-Bosque (0)** | 6,188 píxeles (77.3%) |
| **Ratio global** | 3.40:1 |
| **Features** | 15 bandas espectrales |
| **Zonas procesadas** | 5 de 6 |
| **Duración total** | 64.7 segundos |
| **Fecha de generación** | 2025-11-12 16:36:53 |

---

### **Estadísticas por Zona**

#### **🟢 Zona 1: 14_ElDanubio_Granada_Meta**
- **Ubicación:** Granada, Meta
- **Muestras:** 432 (5.4% del dataset)
- **Bosque:** 20 píxeles (4.6%)
- **No-Bosque:** 412 píxeles (95.4%)
- **Ratio:** 20.60:1 ⚠️
- **Duración:** 10.4s
- **Observación:** Muy desbalanceado, poca cobertura forestal

#### **🟢 Zona 2: 29_Cuiva_SantaRosadeOsos_Antioquia** ⭐
- **Ubicación:** Santa Rosa de Osos, Antioquia
- **Muestras:** 4,306 (53.8% del dataset) - **Zona principal**
- **Bosque:** 1,104 píxeles (25.6%)
- **No-Bosque:** 3,202 píxeles (74.4%)
- **Ratio:** 2.90:1 ✅
- **Duración:** 10.5s
- **Observación:** Mejor balance, mayor contribución al dataset

#### **🟢 Zona 3: 32_LosNaranjos_Venecia_Antioquia** ⭐⭐
- **Ubicación:** Venecia, Antioquia
- **Muestras:** 1,498 (18.7% del dataset)
- **Bosque:** 644 píxeles (43.0%)
- **No-Bosque:** 854 píxeles (57.0%)
- **Ratio:** 1.33:1 ✅✅
- **Duración:** 10.0s
- **Observación:** Excelente balance de clases, calidad óptima

#### **🟢 Zona 4: 35_Bellavista_Albán_Cundinamarca**
- **Ubicación:** Albán, Cundinamarca
- **Muestras:** 271 (3.4% del dataset)
- **Bosque:** 50 píxeles (18.5%)
- **No-Bosque:** 221 píxeles (81.5%)
- **Ratio:** 4.42:1
- **Duración:** 12.8s
- **Observación:** Desbalance moderado, contribución pequeña

#### **🟢 Zona 5: 79_SanJerónimo_Pore_Casanare** ⚠️
- **Ubicación:** Pore, Casanare
- **Muestras:** 1,501 (18.8% del dataset)
- **Bosque:** 2 píxeles (0.1%)
- **No-Bosque:** 1,499 píxeles (99.9%)
- **Ratio:** 749.50:1 ❌
- **Duración:** 11.5s
- **Observación:** Extremadamente desbalanceado, casi sin bosque
- **Recomendación:** Considerar exclusión del dataset

#### **🔴 Zona 6: 42_VillaLuzA_Unguía_Chocó** ❌
- **Ubicación:** Unguía, Chocó
- **Status:** Procesamiento fallido
- **Problema:** 0 píxeles válidos (rasters no cubren área del perímetro)
- **Causa probable:** Desalineación geográfica entre rasters Sentinel-2 y shapefiles
- **Acción requerida:** Reprocesar con clipping correcto o descartar zona

---

## 📁 Estructura de Archivos Generados

```
s3://mineria-project/
│
├── staging/
│   └── 01_rasters_procesados_clipped/
│       ├── 14_ElDanubio_Granada_Meta/
│       │   └── S2*.tif                    # Rasters procesados
│       ├── 29_Cuiva_SantaRosadeOsos_Antioquia/
│       ├── 32_LosNaranjos_Venecia_Antioquia/
│       ├── 35_Bellavista_Albán_Cundinamarca/
│       ├── 42_VillaLuzA_Unguía_Chocó/
│       └── 79_SanJerónimo_Pore_Casanare/
│
├── data/
│   ├── fincas/                            # Datos individuales por zona
│   │   ├── 14_ElDanubio_Granada_Meta/
│   │   │   ├── composite_annual.parquet   # Features agregados
│   │   │   ├── observations_all.parquet   # Observaciones crudas
│   │   │   ├── forest_labels.tif          # Labels rasterizados
│   │   │   └── training_data.parquet      # Tabla de entrenamiento
│   │   ├── 29_Cuiva_SantaRosadeOsos_Antioquia/
│   │   ├── 32_LosNaranjos_Venecia_Antioquia/
│   │   ├── 35_Bellavista_Albán_Cundinamarca/
│   │   └── 79_SanJerónimo_Pore_Casanare/
│   │
│   └── all/
│       └── training_data_all_zones.parquet    # Dataset consolidado ⭐
│
└── logs/
    └── pipeline_report_20251112_163653.json   # Reporte de ejecución
```

---

## 🎯 Calidad del Dataset

### **Fortalezas**

✅ **Cantidad suficiente:** 8,008 muestras para entrenamiento robusto  
✅ **Diversidad geográfica:** 5 zonas en 4 departamentos de Colombia  
✅ **Features espectrales completos:** 15 variables (medianas + percentiles)  
✅ **Etiquetas validadas:** Generadas desde shapefiles oficiales  
✅ **Erosión aplicada:** Reduce contaminación de píxeles de borde  
✅ **Formato eficiente:** Parquet con compresión, ideal para Spark

### **Consideraciones**

⚠️ **Desbalance moderado:** Ratio 3.40:1 (requiere balanceo en entrenamiento)  
⚠️ **Zona 79 problemática:** Solo 2 píxeles de bosque, contamina el balance  
⚠️ **Variabilidad temporal limitada:** Composite anual, sin series temporales  
❌ **Zona 42 excluida:** Datos inválidos, requiere revisión

---

## 🚀 Uso del Dataset

### **Carga en Python (Local)**

```python
import polars as pl

# Cargar dataset completo
df = pl.read_parquet("s3://mineria-project/data/all/training_data_all_zones.parquet")

# Inspección
print(df.head())
print(df.describe())
print(df.groupby("label").count())

# Filtrar zona específica
df_zona29 = df.filter(pl.col("zone") == "29_Cuiva_SantaRosadeOsos_Antioquia")
```

### **Carga en PySpark (EMR)**

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("DeforestationTraining") \
    .getOrCreate()

# Cargar dataset
df = spark.read.parquet("s3://mineria-project/data/all/training_data_all_zones.parquet")

# Ver schema
df.printSchema()

# Estadísticas por clase
df.groupBy("label").count().show()

# Separar features y labels
feature_cols = [f"B{band:02d}_med" for band in [2,3,4,5,6,7,8]] + \
               ["B8A_med", "B11_med", "B12_med"]
```

### **Preparación para Entrenamiento**

```python
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.classification import RandomForestClassifier

# Ensamblar features
feature_cols = [
    "B02_med", "B03_med", "B04_med", "B05_med", "B06_med", 
    "B07_med", "B08_med", "B8A_med", "B11_med", "B12_med",
    "B02_p25", "B03_p25", "B04_p25", "B02_p75", "B03_p75"
]

assembler = VectorAssembler(inputCols=feature_cols, outputCol="features")
df_vectorized = assembler.transform(df)

# Balanceo de clases (calcular pesos)
n_total = df.count()
n_bosque = df.filter("label = 1").count()
n_no_bosque = df.filter("label = 0").count()

weight_bosque = n_total / (2.0 * n_bosque)
weight_no_bosque = n_total / (2.0 * n_no_bosque)

print(f"Peso Bosque: {weight_bosque:.2f}")
print(f"Peso No-Bosque: {weight_no_bosque:.2f}")

# Aplicar pesos
df_weighted = df_vectorized.withColumn(
    "weight",
    when(col("label") == 1, weight_bosque).otherwise(weight_no_bosque)
)

# Entrenar modelo
rf = RandomForestClassifier(
    labelCol="label",
    featuresCol="features",
    weightCol="weight",  # Usar pesos para balanceo
    numTrees=100,
    maxDepth=10,
    subsamplingRate=0.8
)

model = rf.fit(df_weighted)
```

---

## 🔧 Configuración del Pipeline

### **Parámetros Principales**

| Parámetro | Valor por Defecto | Descripción |
|-----------|-------------------|-------------|
| `erosion_pixels` | 1 | Píxeles de erosión morfológica en bordes de bosque |
| `bucket` | mineria-project | Bucket de S3 para datos |
| `nodata_value` | -9999 | Valor de nodata en rasters |
| `crs_target` | EPSG:4326 | Sistema de coordenadas de salida |

### **Ejecución del Pipeline Completo**

```bash
# Procesar todas las zonas disponibles
python scripts/process_all_zones_pipeline.py --erosion_pixels 1

# Procesar zonas específicas
python scripts/process_all_zones_pipeline.py \
  --zones 29_Cuiva_SantaRosadeOsos_Antioquia 32_LosNaranjos_Venecia_Antioquia \
  --erosion_pixels 1
```

### **Ejecución por Pasos Individuales**

```bash
# Paso 2: Tabular features
python scripts/03_tabular_features.py \
  --rasters s3://mineria-project/staging/01_rasters_procesados_clipped/ZONA/ \
  --output s3://mineria-project/data/fincas/ZONA/composite_annual.parquet \
  --save_observations \
  --observations s3://mineria-project/data/fincas/ZONA/observations_all.parquet

# Paso 3: Rasterizar labels
python scripts/04_rasterizar_labels.py \
  --ref s3://mineria-project/staging/01_rasters_procesados_clipped/ZONA/S2*.tif \
  --bosque_shp s3://mineria-project/raw/shapes/ZONA/Bosque.shp \
  --perimetro_shp s3://mineria-project/raw/shapes/ZONA/Perímetro.shp \
  --output s3://mineria-project/data/fincas/ZONA/forest_labels.tif \
  --erosion_pixels 1

# Paso 4: Unir features + labels
python scripts/05_unir_features_labels.py \
  --features s3://mineria-project/data/fincas/ZONA/composite_annual.parquet \
  --labels s3://mineria-project/data/fincas/ZONA/forest_labels.tif \
  --output s3://mineria-project/data/fincas/ZONA/training_data.parquet \
  --format parquet \
  --exclude_ignore
```

---

## 📝 Recomendaciones para Entrenamiento

### **1. Manejo del Desbalance de Clases**

```python
# Opción A: Class weights (recomendado)
from sklearn.utils.class_weight import compute_class_weight

class_weights = compute_class_weight(
    'balanced', 
    classes=[0, 1], 
    y=y_train
)

# Opción B: Oversampling de clase minoritaria
from imblearn.over_sampling import SMOTE

smote = SMOTE(sampling_strategy=0.5)  # 50% de ratio
X_resampled, y_resampled = smote.fit_resample(X_train, y_train)

# Opción C: Undersampling de clase mayoritaria
from imblearn.under_sampling import RandomUnderSampler

rus = RandomUnderSampler(sampling_strategy=0.5)
X_resampled, y_resampled = rus.fit_resample(X_train, y_train)
```

### **2. Exclusión de Zona 79 (Opcional)**

```python
# Filtrar zona 79 si contamina el modelo
df_filtered = df.filter(
    pl.col("zone") != "79_SanJerónimo_Pore_Casanare"
)

# Nuevas estadísticas sin zona 79
# Total: 6,507 muestras
# Bosque: 1,818 (27.9%)
# No-Bosque: 4,689 (72.1%)
# Ratio: 2.58:1 (mejor balance)
```

### **3. Split Train/Test Estratificado**

```python
from sklearn.model_selection import train_test_split

# Split con estratificación por clase
X_train, X_test, y_train, y_test = train_test_split(
    X, y, 
    test_size=0.2, 
    stratify=y,  # Mantiene proporción de clases
    random_state=42
)

# Split adicional por zona (validación geográfica)
zones = df["zone"].to_numpy()
train_zones = ["14_ElDanubio", "29_Cuiva", "32_LosNaranjos"]
test_zones = ["35_Bellavista"]

X_train = X[zones.isin(train_zones)]
X_test = X[zones.isin(test_zones)]
```

### **4. Ingeniería de Features Adicionales**

```python
# Índices de vegetación
df = df.with_columns([
    # NDVI = (NIR - Red) / (NIR + Red)
    ((pl.col("B08_med") - pl.col("B04_med")) / 
     (pl.col("B08_med") + pl.col("B04_med"))).alias("NDVI"),
    
    # EVI = 2.5 * (NIR - Red) / (NIR + 6*Red - 7.5*Blue + 1)
    (2.5 * (pl.col("B08_med") - pl.col("B04_med")) / 
     (pl.col("B08_med") + 6*pl.col("B04_med") - 7.5*pl.col("B02_med") + 1)).alias("EVI"),
    
    # NDMI = (NIR - SWIR1) / (NIR + SWIR1)
    ((pl.col("B08_med") - pl.col("B11_med")) / 
     (pl.col("B08_med") + pl.col("B11_med"))).alias("NDMI")
])
```

---

## 📚 Referencias

### **Bandas Espectrales Sentinel-2**

| Banda | Nombre | Longitud de Onda | Resolución | Uso Principal |
|-------|--------|------------------|------------|---------------|
| B02 | Blue | 490 nm | 10m | Cuerpos de agua, atmósfera |
| B03 | Green | 560 nm | 10m | Vegetación verde, clorofila |
| B04 | Red | 665 nm | 10m | Biomasa, vegetación |
| B05 | Red Edge 1 | 705 nm | 20m | Estado de vegetación |
| B06 | Red Edge 2 | 740 nm | 20m | Estado de vegetación |
| B07 | Red Edge 3 | 783 nm | 20m | Estrés vegetal |
| B08 | NIR | 842 nm | 10m | Biomasa, contenido de agua |
| B8A | NIR Narrow | 865 nm | 20m | Humedad de la vegetación |
| B11 | SWIR 1 | 1610 nm | 20m | Humedad del suelo/vegetación |
| B12 | SWIR 2 | 2190 nm | 20m | Contenido de humedad |

### **Documentación de Scripts**

- `01_procesar_sentinel_clip.py`: Descarga y procesamiento de Sentinel-2
- `03_tabular_features.py`: Extracción y agregación de features espectrales
- `04_rasterizar_labels.py`: Generación de labels desde shapefiles
- `05_unir_features_labels.py`: Unión de features y labels
- `process_all_zones_pipeline.py`: Pipeline automatizado multi-zona

---

## 🐛 Troubleshooting

### **Problema: Zona sin píxeles válidos**
```
Error: 0 píxeles válidos después del clipping
```
**Solución:** Verificar que rasters y shapefiles compartan el mismo CRS o zona geográfica

### **Problema: Desbalance extremo (ratio > 100:1)**
```
Warning: Ratio No-Bosque/Bosque: 749.50:1
```
**Solución:** Excluir zona del dataset o aumentar `erosion_pixels` para capturar más bosque

### **Problema: Memory error en consolidación**
```
MemoryError: Unable to allocate array
```
**Solución:** Procesar zonas en lotes o usar Spark para consolidación

---

## ✅ Checklist de Validación

Antes de entrenar modelos, verificar:

- [ ] Dataset consolidado existe en S3
- [ ] Total de muestras > 5,000
- [ ] Ratio de clases < 5:1 (o aplicar balanceo)
- [ ] No hay valores NaN en features
- [ ] Labels son binarios (0 o 1, sin -1)
- [ ] Distribución de clases en train/test es similar
- [ ] Pipeline report generado sin errores críticos

---

**Última actualización:** 2025-11-12  
**Versión del pipeline:** 1.0  
**Contacto:** Equipo de Data Science - Proyecto Minería
