# 📊 Resultados del Entrenamiento - Detección de Deforestación

**Fecha**: 12 de noviembre de 2025  
**Modelo**: Random Forest Classifier  
**Dataset**: 8,008 muestras de 5 zonas

---

## 🎯 Resumen Ejecutivo

Se entrenó exitosamente un modelo Random Forest para detectar deforestación utilizando imágenes satelitales Sentinel-2. El modelo alcanzó un **90.35% de accuracy** y un **85.42% de PR AUC** en el conjunto de prueba.

### Métricas Clave (Test Set)

| Métrica | Valor |
|---------|-------|
| **Accuracy** | 90.35% |
| **Precision** | 72.89% |
| **Recall** | 91.58% |
| **F1-Score** | 81.17% |
| **ROC AUC** | 96.16% |
| **PR AUC** | 85.42% |

---

## 📈 División de Datos

- **Entrenamiento**: 5,608 muestras (70%)
- **Validación**: 1,198 muestras (15%)
- **Test**: 1,202 muestras (15%)

### Distribución de Clases

- **Clase 0 (No Bosque)**: 6,188 muestras (77.3%)
- **Clase 1 (Bosque)**: 1,820 muestras (22.7%)

---

## 🔧 Configuración del Modelo

```python
RandomForestClassifier(
    n_estimators=100,
    max_depth=10,
    min_samples_split=10,
    min_samples_leaf=5,
    class_weight='balanced',
    random_state=42
)
```

---

## 📊 Matriz de Confusión (Test)

```
                Predicho
              No Bosque  Bosque
Real  No Bosque    836      93
      Bosque         23     250
```

### Interpretación

- **True Negatives (TN)**: 836 - Correctamente identificados como "no bosque"
- **False Positives (FP)**: 93 - Incorrectamente clasificados como "bosque"
- **False Negatives (FN)**: 23 - Bosque perdido (no detectado)
- **True Positives (TP)**: 250 - Correctamente identificados como "bosque"

**Tasa de Falsos Negativos**: 8.42% (23/273) - El modelo pierde algunas áreas de bosque

---

## 🔝 Top 10 Features Más Importantes

| Rank | Feature | Importancia | Descripción |
|------|---------|-------------|-------------|
| 1 | `B03_med` | 18.90% | Banda 3 (Verde) - Media |
| 2 | `NDVI_range` | 11.67% | Rango de NDVI (variabilidad) |
| 3 | `B11_med` | 9.99% | Banda 11 (SWIR) - Media |
| 4 | `B05_med` | 9.31% | Banda 5 (Red Edge) - Media |
| 5 | `n_obs` | 8.94% | Número de observaciones |
| 6 | `B02_med` | 8.68% | Banda 2 (Azul) - Media |
| 7 | `B04_med` | 7.40% | Banda 4 (Rojo) - Media |
| 8 | `B12_med` | 6.58% | Banda 12 (SWIR) - Media |
| 9 | `NDVI_p90` | 3.94% | Percentil 90 de NDVI |
| 10 | `NDVI_p10` | 3.89% | Percentil 10 de NDVI |

### Análisis de Features

- Las **bandas espectrales medias** (B03, B11, B05, B02, B04, B12) son las más importantes, representando el 61.86% de la importancia total
- El **NDVI_range** (variabilidad del NDVI) es crucial para distinguir bosque de no-bosque
- El **número de observaciones** (n_obs) es importante, indicando que la calidad temporal de los datos afecta la predicción

---

## ✅ Conclusiones

### Fortalezas

1. **Alto Recall (91.58%)**: El modelo detecta la mayoría de las áreas boscosas
2. **Excelente ROC AUC (96.16%)**: Muy buena capacidad de discriminación
3. **Buen Balance**: F1-Score de 81.17% muestra equilibrio entre precision y recall
4. **Features Interpretables**: Las bandas espectrales y NDVI son características conocidas y validadas

### Áreas de Mejora

1. **Precision (72.89%)**: ~27% de falsos positivos podrían reducirse con:
   - Más datos de entrenamiento
   - Ajuste de umbrales de clasificación
   - Features adicionales (texturas, temporales)

2. **Desbalance de Clases**: 77.3% no-bosque vs 22.7% bosque
   - Se usó `class_weight='balanced'` para mitigar
   - Considerar técnicas de oversampling (SMOTE) o undersampling

### Recomendaciones

1. **Validación en Campo**: Verificar predicciones en zonas no incluidas en el entrenamiento
2. **Análisis Temporal**: Incorporar cambios temporales (detección de deforestación activa)
3. **Features Adicionales**: 
   - Índices de vegetación adicionales (EVI, SAVI)
   - Métricas de textura (GLCM)
   - Variables climáticas
4. **Ensemble**: Considerar combinar con Gradient Boosting para mejorar performance

---

## 📁 Archivos Generados

- **Modelo**: `s3://mineria-project/models/random_forest_model.pkl`
- **Métricas**: `s3://mineria-project/results/training_summary.json`
- **Feature Importance**: `s3://mineria-project/results/feature_importance.csv`

---

## 🚀 Próximos Pasos

1. **Evaluación en Producción**: Aplicar modelo a nuevas zonas
2. **Monitoreo**: Tracking de performance en datos nuevos
3. **Re-entrenamiento**: Actualizar modelo con nuevos datos cada 3-6 meses
4. **Deployment**: Integrar en pipeline de predicción automatizada

---

**Generado por**: Sistema de ML - Proyecto Minería  
**Contacto**: [Tu equipo]
