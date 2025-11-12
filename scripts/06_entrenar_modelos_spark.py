#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
spark_train_bosque_nobosque.py
---------------------------------------------------------------
Lee múltiples Parquet con *features anuales + labels* (por finca),
los concatena, realiza un split aleatorio train/test, ejecuta
optimización de hiperparámetros con validación interna (TrainValidationSplit)
para dos modelos: RandomForest y GBT, reentrena el mejor y guarda
el modelo óptimo (Pipeline completo) y métricas.

Uso (ejemplos):
  spark-submit --deploy-mode client spark_train_bosque_nobosque.py \
    --inputs "s3://bucket/processed/*/annual_with_labels/*.parquet" \
    --out_model_dir "s3://bucket/model/bosque_rf_gbt_v1" \
    --label_col label --test_frac 0.15 --seed 42

  # Varias rutas separadas por coma
  spark-submit spark_train_bosque_nobosque.py \
    --inputs "/data/finca1.parquet,/data/finca2.parquet" \
    --out_model_dir "/data/modelos/bosque_v1"

Requisitos:
  - PySpark 3.x
  - Los Parquet deben tener columnas numéricas de features (e.g. Bxx_med, NDVI_med, NDVI_p10, NDVI_p90, NDVI_range, ...)
    y una columna de etiqueta binaria (0/1) indicada por --label_col (por defecto 'label').
Salidas:
  - Modelo óptimo (Pipeline con Assembler+Imputer+Modelo) en --out_model_dir
  - Métricas y parámetros en JSON/CSV en --out_model_dir/metrics/
  - Importancia de variables (si el mejor modelo es RF/GBT) en --out_model_dir/metrics/
Autor: Manu - Minería de Datos
"""

import argparse
import json
import os
from typing import List

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when, count, lit
from pyspark.sql.types import DoubleType

from pyspark.ml import Pipeline
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.classification import RandomForestClassifier, GBTClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator, MulticlassClassificationEvaluator
from pyspark.ml.tuning import ParamGridBuilder, TrainValidationSplit

def parse_args():
    p = argparse.ArgumentParser(description="Entrena RF y GBT (Spark) con optimización de hiperparámetros usando TrainValidationSplit.")
    p.add_argument("--inputs", required=True, help="Rutas Parquet (glob o separadas por coma). Deben contener features + columna label.")
    p.add_argument("--out_model_dir", required=True, help="Directorio de salida para el modelo óptimo (S3 o FS).")
    p.add_argument("--out_metrics_dir", default=None, help="Directorio de salida para métricas. Si no se especifica, usa out_model_dir/metrics")
    p.add_argument("--label_col", default="label", help="Nombre de la columna etiqueta (0/1).")
    p.add_argument("--test_frac", type=float, default=0.15, help="Fracción para test hold-out (0-1).")
    p.add_argument("--seed", type=int, default=42, help="Semilla aleatoria.")
    p.add_argument("--metric", default="areaUnderPR", choices=["areaUnderPR","areaUnderROC"], help="Métrica para seleccionar el mejor modelo.")
    return p.parse_args()

def read_many_parquet(spark: SparkSession, inputs: str):
    # Permite glob y/o lista separada por comas
    paths: List[str] = []
    if "," in inputs:
        paths = [x.strip() for x in inputs.split(",") if x.strip()]
    else:
        paths = [inputs.strip()]
    df = None
    for p in paths:
        if df is None:
            df = spark.read.parquet(p)
        else:
            df = df.unionByName(spark.read.parquet(p), allowMissingColumns=True)
    return df

def infer_feature_cols(df, label_col: str):
    # Tomar todas las columnas numéricas excepto la etiqueta y posibles coordenadas
    ignore = set([label_col, "x", "y", "date", "year", "finca_id"])
    num_cols = [f.name for f in df.schema.fields
                if f.dataType.simpleString().startswith("double") or f.dataType.simpleString().startswith("float") or f.dataType.simpleString().startswith("int")]
    feat_cols = [c for c in num_cols if c not in ignore]
    if label_col in df.columns:
        # Asegurar tipo double en label y features
        df = df.withColumn(label_col, col(label_col).cast("double"))
    # Convertir ints a double en features
    for c in feat_cols:
        df = df.withColumn(c, col(c).cast(DoubleType()))
    return df, feat_cols

def build_pipeline(feature_cols: List[str], label_col: str, estimator):
    # Ensamblar features (handleInvalid='skip' para manejar NaNs automáticamente)
    assembler = VectorAssembler(inputCols=feature_cols, outputCol="features", handleInvalid="skip")
    pipeline = Pipeline(stages=[assembler, estimator])
    return pipeline

def compute_class_weights(df, label_col: str):
    """Calcula pesos para balancear clases automáticamente"""
    total = df.count()
    class_counts = df.groupBy(label_col).count().collect()
    
    weights = {}
    for row in class_counts:
        label = row[label_col]
        count = row['count']
        weight = total / (len(class_counts) * count)
        weights[label] = float(weight)
    
    print(f"\n📊 Distribución de clases:")
    for row in sorted(class_counts, key=lambda x: x[label_col]):
        label = row[label_col]
        count = row['count']
        pct = count / total * 100
        weight = weights[label]
        label_name = "Bosque" if label == 1 else "No-Bosque"
        print(f"  {label_name} ({int(label)}): {count:,} samples ({pct:.1f}%) - peso: {weight:.3f}")
    
    return weights

def add_balanced_weights(df, label_col: str, weights: dict):
    """Añade columna de pesos para balanceo de clases"""
    weight_expr = None
    for label, weight in weights.items():
        if weight_expr is None:
            weight_expr = when(col(label_col) == label, lit(weight))
        else:
            weight_expr = weight_expr.when(col(label_col) == label, lit(weight))
    
    df = df.withColumn("classWeight", weight_expr.otherwise(lit(1.0)))
    return df

def compute_all_metrics(predictions, label_col: str, metric_prefix: str = ""):
    """Calcula múltiples métricas de clasificación"""
    bin_eval_auc = BinaryClassificationEvaluator(labelCol=label_col, rawPredictionCol="rawPrediction", metricName="areaUnderROC")
    bin_eval_pr = BinaryClassificationEvaluator(labelCol=label_col, rawPredictionCol="rawPrediction", metricName="areaUnderPR")
    multi_eval = MulticlassClassificationEvaluator(labelCol=label_col, predictionCol="prediction")
    
    metrics = {
        f"{metric_prefix}areaUnderROC": bin_eval_auc.evaluate(predictions),
        f"{metric_prefix}areaUnderPR": bin_eval_pr.evaluate(predictions),
        f"{metric_prefix}accuracy": multi_eval.evaluate(predictions, {multi_eval.metricName: "accuracy"}),
        f"{metric_prefix}f1": multi_eval.evaluate(predictions, {multi_eval.metricName: "f1"}),
        f"{metric_prefix}precision": multi_eval.evaluate(predictions, {multi_eval.metricName: "weightedPrecision"}),
        f"{metric_prefix}recall": multi_eval.evaluate(predictions, {multi_eval.metricName: "weightedRecall"})
    }
    
    return metrics

def compute_confusion_matrix(predictions, label_col: str):
    """Calcula matriz de confusión"""
    cm = predictions.groupBy(label_col, "prediction").count().collect()
    
    matrix = {}
    for row in cm:
        true_label = int(row[label_col])
        pred_label = int(row["prediction"])
        count = row["count"]
        matrix[(true_label, pred_label)] = count
    
    return matrix

def main():
    args = parse_args()
    spark = (
        SparkSession.builder
        .appName("BosqueNoBosque_RF_GBT_Optimizado")
        .getOrCreate()
    )

    # 1) Lectura y preparación
    df = read_many_parquet(spark, args.inputs)
    if args.label_col not in df.columns:
        raise ValueError(f"No se encontró la columna de etiqueta '{args.label_col}' en el dataset.")
    df, feature_cols = infer_feature_cols(df, args.label_col)
    if not feature_cols:
        raise ValueError("No se encontraron columnas de features numéricas. Revisa tus Parquet.")

    # Filtro de filas sin label
    df = df.filter(col(args.label_col).isNotNull())
    
    print(f"\n{'='*70}")
    print(f"CONFIGURACIÓN DE ENTRENAMIENTO")
    print(f"{'='*70}")
    print(f"  Total muestras: {df.count():,}")
    print(f"  Features: {len(feature_cols)}")
    print(f"  Label col: {args.label_col}")
    print(f"  Test fraction: {args.test_frac}")
    print(f"  Seed: {args.seed}")
    print(f"  Métrica optimización: {args.metric}")
    
    # Calcular pesos para balanceo de clases
    class_weights = compute_class_weights(df, args.label_col)
    df = add_balanced_weights(df, args.label_col, class_weights)

    # 2) Split aleatorio train/val/test (70/15/15 por defecto)
    train_frac = 1.0 - (args.test_frac * 2)  # 70% train
    val_frac = args.test_frac  # 15% validation
    test_frac = args.test_frac  # 15% test
    
    train_df, val_df, test_df = df.randomSplit(
        [train_frac, val_frac, test_frac], 
        seed=args.seed
    )
    
    print(f"\n  Train muestras: {train_df.count():,} ({train_frac*100:.0f}%)")
    print(f"  Validation muestras: {val_df.count():,} ({val_frac*100:.0f}%)")
    print(f"  Test muestras: {test_df.count():,} ({test_frac*100:.0f}%)")

    evaluator = BinaryClassificationEvaluator(labelCol=args.label_col, rawPredictionCol="rawPrediction", metricName=args.metric)

    # -------------------------
    # RANDOM FOREST
    # -------------------------
    print(f"\n{'='*70}")
    print("OPTIMIZANDO RANDOM FOREST...")
    print(f"{'='*70}")
    
    rf = RandomForestClassifier(
        labelCol=args.label_col,
        featuresCol="features",
        weightCol="classWeight",  # ⚠️ Usar pesos para balanceo
        seed=args.seed
    )
    rf_pipe = build_pipeline(feature_cols, args.label_col, rf)
    rf_grid = (ParamGridBuilder()
               .addGrid(rf.numTrees, [200, 400, 600])
               .addGrid(rf.maxDepth, [10, 14, 18])
               .addGrid(rf.maxBins, [64, 128])
               .addGrid(rf.featureSubsetStrategy, ["sqrt", "log2"])
               .build())
    
    print(f"  Grid de hiperparámetros: {len(rf_grid)} combinaciones")
    print(f"  Train ratio (interno): 80% train, 20% validación")
    
    rf_tvs = TrainValidationSplit(
        estimator=rf_pipe,
        estimatorParamMaps=rf_grid,
        evaluator=evaluator,
        trainRatio=0.8,  # 80% train interno, 20% validación interna
        seed=args.seed
    )
    rf_tvs_model = rf_tvs.fit(train_df)
    rf_best_pipeline = rf_tvs_model.bestModel  # PipelineModel ya ajustado sobre todo train_df
    rf_best_params = {p.name: rf_tvs_model.bestModel.stages[-1].getOrDefault(p) for p in rf_tvs_model.bestModel.stages[-1].params}

    rf_internal_val_metric = max(rf_tvs_model.validationMetrics) if hasattr(rf_tvs_model, "validationMetrics") else None
    
    # Evaluar en validation set externo
    rf_val_pred = rf_best_pipeline.transform(val_df)
    rf_val_metrics = compute_all_metrics(rf_val_pred, args.label_col, "val_")
    rf_val_metric = rf_val_metrics[f"val_{args.metric}"]
    
    # Evaluar en test set
    rf_test_pred = rf_best_pipeline.transform(test_df)
    rf_test_metrics = compute_all_metrics(rf_test_pred, args.label_col, "test_")
    rf_test_metric = rf_test_metrics[f"test_{args.metric}"]
    
    print(f"\n  ✓ Mejor {args.metric} en validación interna: {rf_internal_val_metric:.4f}")
    print(f"  ✓ Métricas en VALIDATION SET:")
    for k, v in rf_val_metrics.items():
        print(f"      {k.replace('val_', '')}: {v:.4f}")
    print(f"  ✓ Métricas en TEST:")
    for k, v in rf_test_metrics.items():
        print(f"      {k.replace('test_', '')}: {v:.4f}")

    # -------------------------
    # GBT
    # -------------------------
    print(f"\n{'='*70}")
    print("OPTIMIZANDO GRADIENT BOOSTED TREES...")
    print(f"{'='*70}")
    
    gbt = GBTClassifier(
        labelCol=args.label_col,
        featuresCol="features",
        weightCol="classWeight",  # ⚠️ Usar pesos para balanceo
        seed=args.seed,
        maxIter=100  # valor base; se optimiza en grid
    )
    gbt_pipe = build_pipeline(feature_cols, args.label_col, gbt)
    gbt_grid = (ParamGridBuilder()
                .addGrid(gbt.maxDepth, [6, 8, 10])
                .addGrid(gbt.maxBins, [64, 128])
                .addGrid(gbt.maxIter, [100, 200])
                .addGrid(gbt.stepSize, [0.05, 0.1, 0.2])
                .build())
    
    print(f"  Grid de hiperparámetros: {len(gbt_grid)} combinaciones")
    print(f"  Train ratio (interno): 80% train, 20% validación")
    
    gbt_tvs = TrainValidationSplit(
        estimator=gbt_pipe,
        estimatorParamMaps=gbt_grid,
        evaluator=evaluator,
        trainRatio=0.8,
        seed=args.seed
    )
    gbt_tvs_model = gbt_tvs.fit(train_df)
    gbt_best_pipeline = gbt_tvs_model.bestModel
    gbt_best_params = {p.name: gbt_tvs_model.bestModel.stages[-1].getOrDefault(p) for p in gbt_tvs_model.bestModel.stages[-1].params}

    gbt_internal_val_metric = max(gbt_tvs_model.validationMetrics) if hasattr(gbt_tvs_model, "validationMetrics") else None
    
    # Evaluar en validation set externo
    gbt_val_pred = gbt_best_pipeline.transform(val_df)
    gbt_val_metrics = compute_all_metrics(gbt_val_pred, args.label_col, "val_")
    gbt_val_metric = gbt_val_metrics[f"val_{args.metric}"]
    
    # Evaluar en test set
    gbt_test_pred = gbt_best_pipeline.transform(test_df)
    gbt_test_metrics = compute_all_metrics(gbt_test_pred, args.label_col, "test_")
    gbt_test_metric = gbt_test_metrics[f"test_{args.metric}"]
    
    print(f"\n  ✓ Mejor {args.metric} en validación interna: {gbt_internal_val_metric:.4f}")
    print(f"  ✓ Métricas en VALIDATION SET:")
    for k, v in gbt_val_metrics.items():
        print(f"      {k.replace('val_', '')}: {v:.4f}")
    print(f"  ✓ Métricas en TEST:")
    for k, v in gbt_test_metrics.items():
        print(f"      {k.replace('test_', '')}: {v:.4f}")

    # -------------------------
    # Selección del mejor (por métrica en VALIDATION SET)
    # -------------------------
    print(f"\n{'='*70}")
    print("COMPARACIÓN DE MODELOS")
    print(f"{'='*70}")
    print(f"  RandomForest - {args.metric} (Val): {rf_val_metric:.4f} | (Test): {rf_test_metric:.4f}")
    print(f"  GBT          - {args.metric} (Val): {gbt_val_metric:.4f} | (Test): {gbt_test_metric:.4f}")
    
    # Seleccionar por VALIDATION, no por TEST (para evitar overfitting al test set)
    if gbt_val_metric >= rf_val_metric:
        best_name = "GBT"
        best_pipeline = gbt_best_pipeline
        best_val_metric = gbt_val_metric
        best_val_metrics = gbt_val_metrics
        best_test_metric = gbt_test_metric
        best_test_metrics = gbt_test_metrics
        best_params = gbt_best_params
        best_test_pred = gbt_test_pred
    else:
        best_name = "RandomForest"
        best_pipeline = rf_best_pipeline
        best_val_metric = rf_val_metric
        best_val_metrics = rf_val_metrics
        best_test_metric = rf_test_metric
        best_test_metrics = rf_test_metrics
        best_params = rf_best_params
        best_test_pred = rf_test_pred
    
    print(f"\n  🏆 GANADOR (según validation): {best_name}")
    
    # -------------------------
    # RE-ENTRENAMIENTO CON TODO EL TRAIN SET
    # -------------------------
    print(f"\n{'='*70}")
    print(f"RE-ENTRENANDO {best_name.upper()} CON TODO EL TRAIN SET")
    print(f"{'='*70}")
    
    # Construir estimador con los mejores hiperparámetros
    if best_name == "RandomForest":
        final_estimator = RandomForestClassifier(
            labelCol=args.label_col,
            featuresCol="features",
            weightCol="classWeight",
            seed=args.seed
        )
    else:  # GBT
        final_estimator = GBTClassifier(
            labelCol=args.label_col,
            featuresCol="features",
            weightCol="classWeight",
            seed=args.seed
        )
    
    # Aplicar mejores hiperparámetros
    for param_name, param_value in best_params.items():
        if hasattr(final_estimator, param_name):
            setattr(final_estimator, param_name, param_value)
    
    # Re-entrenar con TODO train_df
    final_pipeline = build_pipeline(feature_cols, args.label_col, final_estimator)
    final_model = final_pipeline.fit(train_df)
    
    # Evaluar en test
    final_test_pred = final_model.transform(test_df)
    final_test_metrics = compute_all_metrics(final_test_pred, args.label_col, "test_")
    
    print(f"\n  ✓ Modelo re-entrenado con {train_df.count():,} muestras")
    print(f"  ✓ Métricas finales en TEST:")
    for k, v in final_test_metrics.items():
        print(f"      {k.replace('test_', '')}: {v:.4f}")
    
    # Matriz de confusión
    conf_matrix = compute_confusion_matrix(final_test_pred, args.label_col)
    print(f"\n  Matriz de confusión (Test):")
    print(f"                 Pred=0  Pred=1")
    print(f"      Real=0  {conf_matrix.get((0, 0), 0):7d} {conf_matrix.get((0, 1), 0):7d}")
    print(f"      Real=1  {conf_matrix.get((1, 0), 0):7d} {conf_matrix.get((1, 1), 0):7d}")

    # Guardado
    print(f"\n{'='*70}")
    print("GUARDANDO MODELO Y MÉTRICAS")
    print(f"{'='*70}")
    
    # Usar directorio de métricas separado si se especifica
    if args.out_metrics_dir:
        metrics_dir = args.out_metrics_dir
    else:
        metrics_dir = os.path.join(args.out_model_dir, "metrics")
    
    try:
        os.makedirs(metrics_dir, exist_ok=True)
    except Exception:
        pass

    # Pipeline completo (RE-ENTRENADO)
    model_path = os.path.join(args.out_model_dir, "pipeline_best")
    final_model.write().overwrite().save(model_path)
    print(f"  ✓ Modelo guardado en: {model_path}")

    # Importancia de variables si aplica
    try:
        importances = final_model.stages[-1].featureImportances
        feat_names = feature_cols
        imp_list = [(feat_names[i], float(importances[i])) for i in range(len(feat_names))]
        imp_list_sorted = sorted(imp_list, key=lambda x: -x[1])
    except Exception:
        imp_list = []
        imp_list_sorted = []

    summary = {
        "metric_used": args.metric,
        "test_frac": args.test_frac,
        "seed": args.seed,
        "train_samples": train_df.count(),
        "val_samples": val_df.count(),
        "test_samples": test_df.count(),
        "n_features": len(feature_cols),
        "class_weights": class_weights,
        "models": {
            "RandomForest": {
                "internal_val_metric": rf_internal_val_metric,
                "val_metrics": {k.replace("val_", ""): v for k, v in rf_val_metrics.items()},
                "test_metrics": {k.replace("test_", ""): v for k, v in rf_test_metrics.items()},
                "best_params": {k: str(v) for k, v in rf_best_params.items()}
            },
            "GBT": {
                "internal_val_metric": gbt_internal_val_metric,
                "val_metrics": {k.replace("val_", ""): v for k, v in gbt_val_metrics.items()},
                "test_metrics": {k.replace("test_", ""): v for k, v in gbt_test_metrics.items()},
                "best_params": {k: str(v) for k, v in gbt_best_params.items()}
            }
        },
        "winner": {
            "name": best_name,
            "val_metrics": {k.replace("val_", ""): v for k, v in best_val_metrics.items()},
            "test_metrics_initial": {k.replace("test_", ""): v for k, v in best_test_metrics.items()},
            "test_metrics_retrained": {k.replace("test_", ""): v for k, v in final_test_metrics.items()},
            "best_params": {k: str(v) for k, v in best_params.items()}
        },
        "confusion_matrix": {
            "TN": conf_matrix.get((0, 0), 0),
            "FP": conf_matrix.get((0, 1), 0),
            "FN": conf_matrix.get((1, 0), 0),
            "TP": conf_matrix.get((1, 1), 0)
        },
        "feature_importances": [{"feature": name, "importance": imp} for name, imp in imp_list_sorted]
    }

    summary_path = os.path.join(metrics_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Resumen guardado en: {summary_path}")

    if imp_list_sorted:
        imp_path = os.path.join(metrics_dir, "feature_importances.csv")
        with open(imp_path, "w", encoding="utf-8") as f:
            f.write("feature,importance\n")
            for name, imp in imp_list_sorted:
                f.write(f"{name},{imp}\n")
        print(f"  ✓ Importancias guardadas en: {imp_path}")
        
        print(f"\n  Top 10 features más importantes:")
        for i, (name, imp) in enumerate(imp_list_sorted[:10], 1):
            print(f"      {i:2d}. {name:<20s} {imp:.4f}")

    print(f"\n{'='*70}")
    print(f" 🏆 MODELO ÓPTIMO: {best_name}")
    print(f" 📊 Accuracy (Test): {final_test_metrics['test_accuracy']:.4f}")
    print(f" 📊 F1-Score (Test): {final_test_metrics['test_f1']:.4f}")
    print(f" 📊 AUC-ROC (Test):  {final_test_metrics['test_areaUnderROC']:.4f}")
    print(f" 💾 Guardado en: {args.out_model_dir}")
    print(f"{'='*70}")

    spark.stop()

if __name__ == "__main__":
    main()
