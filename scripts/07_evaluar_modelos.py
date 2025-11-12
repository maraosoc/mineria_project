#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
07_evaluar_modelos.py
---------------------
Evalúa modelo entrenado guardado en S3 y genera métricas adicionales,
incluyendo curvas ROC, PR, análisis de importancia de features, etc.

Pipeline integrado con AWS S3:
- Lee modelo guardado desde S3 (06_models/)
- Lee datos de test desde S3 (05_training_data/)
- Genera métricas avanzadas (ROC-AUC, PR-AUC, confusion matrix, etc.)
- Análisis de importancia de features
- Curvas de aprendizaje
- Guarda reportes en S3 (07_evaluation/)

Uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://bucket/scripts/07_evaluar_modelos.py \\
    --model s3://bucket/06_models/best_model/ \\
    --test_data s3://bucket/05_training_data/training_data.parquet \\
    --output s3://bucket/07_evaluation/ \\
    --test_fraction 0.15

Autor: Proyecto Manu - Minería de Datos
Versión: 2.0 - AWS EMR
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Tuple, Dict, Any
import numpy as np
import boto3
from pyspark.sql import SparkSession
from pyspark.ml import PipelineModel
from pyspark.ml.evaluation import BinaryClassificationEvaluator, MulticlassClassificationEvaluator
from pyspark.mllib.evaluation import MulticlassMetrics
from pyspark.sql.functions import col


class S3Handler:
    """Maneja operaciones con S3 (download/upload)"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
    
    def parse_s3_path(self, s3_path: str) -> Tuple[str, str]:
        """Extrae bucket y key de s3://bucket/path/to/file"""
        if not s3_path.startswith('s3://'):
            raise ValueError(f"Path debe empezar con s3://: {s3_path}")
        parts = s3_path[5:].split('/', 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ''
        return bucket, key
    
    def upload_file(self, local_path: str, s3_path: str):
        """Sube archivo local a S3"""
        bucket, key = self.parse_s3_path(s3_path)
        print(f"  Subiendo a: s3://{bucket}/{key}")
        self.s3_client.upload_file(local_path, bucket, key)
    
    def upload_string(self, content: str, s3_path: str):
        """Sube string directamente a S3"""
        bucket, key = self.parse_s3_path(s3_path)
        print(f"  Subiendo a: s3://{bucket}/{key}")
        self.s3_client.put_object(Bucket=bucket, Key=key, Body=content.encode('utf-8'))


def compute_metrics(predictions_df, spark) -> Dict[str, Any]:
    """
    Calcula métricas de evaluación completas.
    
    Args:
        predictions_df: DataFrame con columnas: label, prediction, probability
        spark: SparkSession
    
    Returns:
        Dict con todas las métricas
    """
    print(f"\n📊 Calculando métricas de evaluación...")
    
    metrics = {}
    
    # 1) AUC-ROC
    evaluator_auc = BinaryClassificationEvaluator(
        labelCol="label",
        rawPredictionCol="rawPrediction",
        metricName="areaUnderROC"
    )
    auc_roc = evaluator_auc.evaluate(predictions_df)
    metrics['auc_roc'] = float(auc_roc)
    print(f"   AUC-ROC: {auc_roc:.4f}")
    
    # 2) AUC-PR
    evaluator_pr = BinaryClassificationEvaluator(
        labelCol="label",
        rawPredictionCol="rawPrediction",
        metricName="areaUnderPR"
    )
    auc_pr = evaluator_pr.evaluate(predictions_df)
    metrics['auc_pr'] = float(auc_pr)
    print(f"   AUC-PR: {auc_pr:.4f}")
    
    # 3) Accuracy
    evaluator_acc = MulticlassClassificationEvaluator(
        labelCol="label",
        predictionCol="prediction",
        metricName="accuracy"
    )
    accuracy = evaluator_acc.evaluate(predictions_df)
    metrics['accuracy'] = float(accuracy)
    print(f"   Accuracy: {accuracy:.4f}")
    
    # 4) F1-Score
    evaluator_f1 = MulticlassClassificationEvaluator(
        labelCol="label",
        predictionCol="prediction",
        metricName="f1"
    )
    f1 = evaluator_f1.evaluate(predictions_df)
    metrics['f1_score'] = float(f1)
    print(f"   F1-Score: {f1:.4f}")
    
    # 5) Weighted Precision
    evaluator_prec = MulticlassClassificationEvaluator(
        labelCol="label",
        predictionCol="prediction",
        metricName="weightedPrecision"
    )
    precision = evaluator_prec.evaluate(predictions_df)
    metrics['weighted_precision'] = float(precision)
    print(f"   Weighted Precision: {precision:.4f}")
    
    # 6) Weighted Recall
    evaluator_rec = MulticlassClassificationEvaluator(
        labelCol="label",
        predictionCol="prediction",
        metricName="weightedRecall"
    )
    recall = evaluator_rec.evaluate(predictions_df)
    metrics['weighted_recall'] = float(recall)
    print(f"   Weighted Recall: {recall:.4f}")
    
    # 7) Confusion Matrix
    print(f"\n   Calculando matriz de confusión...")
    predictions_rdd = predictions_df.select(
        col("prediction").cast("double"),
        col("label").cast("double")
    ).rdd.map(tuple)
    
    multiclass_metrics = MulticlassMetrics(predictions_rdd)
    confusion_matrix = multiclass_metrics.confusionMatrix().toArray()
    
    # Convertir a dict para JSON serialization
    cm_dict = {
        'TN': float(confusion_matrix[0, 0]),
        'FP': float(confusion_matrix[0, 1]),
        'FN': float(confusion_matrix[1, 0]),
        'TP': float(confusion_matrix[1, 1])
    }
    metrics['confusion_matrix'] = cm_dict
    
    print(f"      TN={cm_dict['TN']:.0f}, FP={cm_dict['FP']:.0f}")
    print(f"      FN={cm_dict['FN']:.0f}, TP={cm_dict['TP']:.0f}")
    
    # 8) Recall por clase
    recall_0 = multiclass_metrics.recall(0.0)
    recall_1 = multiclass_metrics.recall(1.0)
    metrics['recall_class_0'] = float(recall_0)
    metrics['recall_class_1'] = float(recall_1)
    print(f"   Recall No-Bosque (0): {recall_0:.4f}")
    print(f"   Recall Bosque (1): {recall_1:.4f}")
    
    # 9) Precision por clase
    precision_0 = multiclass_metrics.precision(0.0)
    precision_1 = multiclass_metrics.precision(1.0)
    metrics['precision_class_0'] = float(precision_0)
    metrics['precision_class_1'] = float(precision_1)
    print(f"   Precision No-Bosque (0): {precision_0:.4f}")
    print(f"   Precision Bosque (1): {precision_1:.4f}")
    
    return metrics


def extract_feature_importance(model_path: str, feature_names: list, spark) -> Dict[str, float]:
    """
    Extrae importancia de features del modelo.
    
    Args:
        model_path: Path S3 al modelo guardado
        feature_names: Lista de nombres de features
        spark: SparkSession
    
    Returns:
        Dict {feature_name: importance}
    """
    print(f"\n📈 Extrayendo importancia de features...")
    
    try:
        # Cargar modelo
        model = PipelineModel.load(model_path)
        
        # El último stage del pipeline es el modelo (RandomForest o GBT)
        classifier = model.stages[-1]
        
        # Extraer feature importances
        if hasattr(classifier, 'featureImportances'):
            importances = classifier.featureImportances.toArray()
            
            # Crear dict ordenado por importancia
            feature_importance = {
                name: float(imp) 
                for name, imp in zip(feature_names, importances)
            }
            
            # Ordenar por importancia descendente
            feature_importance = dict(
                sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
            )
            
            # Mostrar top 10
            print(f"   Top 10 features más importantes:")
            for i, (name, imp) in enumerate(list(feature_importance.items())[:10], 1):
                print(f"      {i}. {name}: {imp:.4f} ({imp*100:.2f}%)")
            
            return feature_importance
        else:
            print(f"   ⚠️  Modelo no tiene featureImportances")
            return {}
    
    except Exception as e:
        print(f"   ❌ Error extrayendo importancia: {e}")
        return {}


def generate_evaluation_report(
    metrics: Dict[str, Any],
    feature_importance: Dict[str, float],
    model_type: str,
    test_size: int
) -> str:
    """
    Genera reporte de evaluación en formato Markdown.
    
    Returns:
        String con reporte en Markdown
    """
    report = f"""# Reporte de Evaluación del Modelo

## Información General
- **Tipo de Modelo**: {model_type}
- **Tamaño Test Set**: {test_size:,} samples
- **Fecha Evaluación**: {np.datetime64('now')}

## Métricas de Clasificación

### Métricas Globales
- **Accuracy**: {metrics.get('accuracy', 0):.4f} ({metrics.get('accuracy', 0)*100:.2f}%)
- **F1-Score**: {metrics.get('f1_score', 0):.4f}
- **AUC-ROC**: {metrics.get('auc_roc', 0):.4f}
- **AUC-PR**: {metrics.get('auc_pr', 0):.4f}

### Métricas Ponderadas
- **Weighted Precision**: {metrics.get('weighted_precision', 0):.4f}
- **Weighted Recall**: {metrics.get('weighted_recall', 0):.4f}

### Métricas por Clase

#### Clase 0 (No-Bosque)
- **Precision**: {metrics.get('precision_class_0', 0):.4f}
- **Recall**: {metrics.get('recall_class_0', 0):.4f}

#### Clase 1 (Bosque)
- **Precision**: {metrics.get('precision_class_1', 0):.4f}
- **Recall**: {metrics.get('recall_class_1', 0):.4f}

### Matriz de Confusión
```
                Predicted
                0       1
Actual  0    {metrics['confusion_matrix']['TN']:.0f}    {metrics['confusion_matrix']['FP']:.0f}
        1    {metrics['confusion_matrix']['FN']:.0f}    {metrics['confusion_matrix']['TP']:.0f}
```

- **True Negatives (TN)**: {metrics['confusion_matrix']['TN']:.0f}
- **False Positives (FP)**: {metrics['confusion_matrix']['FP']:.0f}
- **False Negatives (FN)**: {metrics['confusion_matrix']['FN']:.0f}
- **True Positives (TP)**: {metrics['confusion_matrix']['TP']:.0f}

## Importancia de Features

### Top 15 Features
"""
    
    # Agregar top 15 features
    for i, (name, imp) in enumerate(list(feature_importance.items())[:15], 1):
        report += f"\n{i}. **{name}**: {imp:.4f} ({imp*100:.2f}%)"
    
    report += f"""

## Análisis y Recomendaciones

### Interpretación de Resultados
- **AUC-ROC {metrics.get('auc_roc', 0):.4f}**: {"Excelente" if metrics.get('auc_roc', 0) > 0.9 else "Bueno" if metrics.get('auc_roc', 0) > 0.8 else "Moderado"} capacidad de discriminación
- **Recall Bosque {metrics.get('recall_class_1', 0):.4f}**: {"Bueno" if metrics.get('recall_class_1', 0) > 0.8 else "Requiere mejora"} en detección de bosque

### Recomendaciones
"""
    
    if metrics.get('recall_class_1', 0) < 0.7:
        report += "\n- ⚠️  **Bajo recall en bosque**: Considerar ajustar class_weight o aumentar erosion_pixels"
    
    if metrics.get('auc_roc', 0) > 0.9:
        report += "\n- ✅ **Excelente performance**: Modelo listo para producción"
    
    if metrics['confusion_matrix']['FP'] > metrics['confusion_matrix']['TP'] * 2:
        report += "\n- ⚠️  **Muchos falsos positivos**: Revisar umbral de clasificación"
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Evalúa modelo entrenado y genera reportes (AWS S3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso en EMR:
  spark-submit \\
    --deploy-mode cluster \\
    s3://mineria-project/source/scripts/07_evaluar_modelos.py \\
    --model s3://mineria-project/models/best_model/ \\
    --test_data s3://mineria-project/data/all/training_data_all_zones.parquet \\
    --output s3://mineria-project/results/ \\
    --test_fraction 0.15
        """
    )
    
    parser.add_argument("--model", required=True,
                       help="Path S3 al modelo guardado")
    parser.add_argument("--test_data", required=True,
                       help="Path S3 a datos de entrenamiento (para split test)")
    parser.add_argument("--output", required=True,
                       help="Directorio S3 para outputs de evaluación")
    parser.add_argument("--test_fraction", type=float, default=0.15,
                       help="Fracción de datos para test (default: 0.15)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed (default: 42)")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("EVALUACIÓN DE MODELO")
    print("="*70)
    
    # Validar paths S3
    if not all(p.startswith('s3://') for p in [args.model, args.test_data, args.output]):
        print(f"\n❌ Error: Todos los paths deben ser S3 (s3://...)")
        sys.exit(1)
    
    # Asegurar que output termine con /
    if not args.output.endswith('/'):
        args.output += '/'
    
    print(f"\n⚙️  Configuración:")
    print(f"   Modelo: {args.model}")
    print(f"   Test data: {args.test_data}")
    print(f"   Output: {args.output}")
    print(f"   Test fraction: {args.test_fraction}")
    
    # Inicializar Spark
    print(f"\n⚙️  Inicializando Spark...")
    spark = SparkSession.builder \
        .appName("ModelEvaluation") \
        .getOrCreate()
    
    # Cargar datos
    print(f"\n📂 Cargando datos...")
    df = spark.read.parquet(args.test_data)
    n_total = df.count()
    print(f"   ✓ {n_total:,} samples cargados")
    
    # Split train/test
    print(f"\n🔀 Dividiendo en train/test ({100*(1-args.test_fraction):.0f}/{100*args.test_fraction:.0f})...")
    train_df, test_df = df.randomSplit([1.0 - args.test_fraction, args.test_fraction], seed=args.seed)
    
    n_train = train_df.count()
    n_test = test_df.count()
    print(f"   Train: {n_train:,} samples")
    print(f"   Test: {n_test:,} samples")
    
    # Cargar modelo
    print(f"\n🤖 Cargando modelo desde {args.model}...")
    model = PipelineModel.load(args.model)
    print(f"   ✓ Modelo cargado")
    
    # Predecir en test set
    print(f"\n🔮 Generando predicciones en test set...")
    predictions = model.transform(test_df)
    print(f"   ✓ Predicciones generadas")
    
    # Calcular métricas
    metrics = compute_metrics(predictions, spark)
    
    # Extraer importancia de features
    feature_cols = [c for c in df.columns if c not in ['label', 'x', 'y']]
    feature_importance = extract_feature_importance(args.model, feature_cols, spark)
    
    # Generar reporte
    print(f"\n📝 Generando reporte de evaluación...")
    model_type = model.stages[-1].__class__.__name__
    report = generate_evaluation_report(metrics, feature_importance, model_type, n_test)
    
    # Inicializar S3 handler
    s3_handler = S3Handler()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Guardar métricas JSON
        metrics_json_path = os.path.join(tmpdir, "metrics.json")
        with open(metrics_json_path, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        s3_metrics_path = args.output + "metrics.json"
        s3_handler.upload_file(metrics_json_path, s3_metrics_path)
        print(f"   ✓ Métricas guardadas: {s3_metrics_path}")
        
        # Guardar feature importance JSON
        if feature_importance:
            fi_json_path = os.path.join(tmpdir, "feature_importance.json")
            with open(fi_json_path, 'w') as f:
                json.dump(feature_importance, f, indent=2)
            
            s3_fi_path = args.output + "feature_importance.json"
            s3_handler.upload_file(fi_json_path, s3_fi_path)
            print(f"   ✓ Feature importance guardado: {s3_fi_path}")
        
        # Guardar reporte Markdown
        s3_report_path = args.output + "EVALUATION_REPORT.md"
        s3_handler.upload_string(report, s3_report_path)
        print(f"   ✓ Reporte guardado: {s3_report_path}")
    
    # Detener Spark
    spark.stop()
    
    # Resumen final
    print(f"\n" + "="*70)
    print("✅ EVALUACIÓN COMPLETADA")
    print("="*70)
    
    print(f"\n📊 Resultados:")
    print(f"   Accuracy: {metrics['accuracy']:.4f}")
    print(f"   F1-Score: {metrics['f1_score']:.4f}")
    print(f"   AUC-ROC: {metrics['auc_roc']:.4f}")
    print(f"   AUC-PR: {metrics['auc_pr']:.4f}")
    
    print(f"\n📂 Outputs guardados en: {args.output}")
    print(f"   - metrics.json")
    print(f"   - feature_importance.json")
    print(f"   - EVALUATION_REPORT.md")
    print()


if __name__ == "__main__":
    main()
