#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Versión rápida - Solo Random Forest con parámetros fijos
"""

import argparse
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    classification_report
)
import joblib

def parse_args():
    p = argparse.ArgumentParser(description="Entrena Random Forest rápidamente")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()

def main():
    args = parse_args()
    
    print("="*70)
    print("🎯 ENTRENAMIENTO RÁPIDO - RANDOM FOREST")
    print("="*70)
    
    # Cargar datos
    print(f"\n📂 Cargando datos...")
    df = pd.read_parquet(args.input)
    print(f"   ✓ {len(df):,} muestras")
    
    # Preparar features
    print(f"\n🔧 Preparando features...")
    label_col = 'label'
    exclude = {label_col, 'x', 'y', 'date', 'year', 'finca_id', 'zone', 'zone_name'}
    feature_cols = [c for c in df.columns if c not in exclude]
    
    X = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    y = df[label_col]
    
    print(f"   ✓ {len(feature_cols)} features")
    print(f"   ✓ Clase 0: {(y==0).sum():,} | Clase 1: {(y==1).sum():,}")
    
    # Split 70/15/15
    print(f"\n✂️  Dividiendo datos...")
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y, test_size=0.15, random_state=args.seed, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp, test_size=0.176, random_state=args.seed, stratify=y_temp  # 0.176 ≈ 15/85
    )
    
    print(f"   ✓ Train: {len(X_train):,}")
    print(f"   ✓ Val: {len(X_val):,}")
    print(f"   ✓ Test: {len(X_test):,}")
    
    # Entrenar RF con buenos parámetros
    print(f"\n🌲 Entrenando Random Forest...")
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=10,
        min_samples_leaf=5,
        class_weight='balanced',
        random_state=args.seed,
        n_jobs=-1,
        verbose=1
    )
    
    rf.fit(X_train, y_train)
    print(f"   ✓ Entrenamiento completado")
    
    # Evaluar en validación
    print(f"\n📊 Evaluando en VALIDACIÓN...")
    y_val_pred = rf.predict(X_val)
    y_val_proba = rf.predict_proba(X_val)[:, 1]
    
    val_metrics = {
        'accuracy': accuracy_score(y_val, y_val_pred),
        'precision': precision_score(y_val, y_val_pred, zero_division=0),
        'recall': recall_score(y_val, y_val_pred, zero_division=0),
        'f1': f1_score(y_val, y_val_pred, zero_division=0),
        'roc_auc': roc_auc_score(y_val, y_val_proba),
        'pr_auc': average_precision_score(y_val, y_val_proba)
    }
    
    cm_val = confusion_matrix(y_val, y_val_pred)
    
    print(f"\n   Métricas de VALIDACIÓN:")
    print(f"   {'='*50}")
    print(f"   Accuracy:  {val_metrics['accuracy']:.4f} ({val_metrics['accuracy']*100:.2f}%)")
    print(f"   Precision: {val_metrics['precision']:.4f}")
    print(f"   Recall:    {val_metrics['recall']:.4f}")
    print(f"   F1-Score:  {val_metrics['f1']:.4f}")
    print(f"   ROC AUC:   {val_metrics['roc_auc']:.4f}")
    print(f"   PR AUC:    {val_metrics['pr_auc']:.4f}")
    print(f"\n   Matriz de Confusión (Validación):")
    print(f"   TN: {cm_val[0,0]:4d}  FP: {cm_val[0,1]:4d}")
    print(f"   FN: {cm_val[1,0]:4d}  TP: {cm_val[1,1]:4d}")
    
    # Evaluar en test
    print(f"\n📊 Evaluando en TEST (hold-out final)...")
    y_test_pred = rf.predict(X_test)
    y_test_proba = rf.predict_proba(X_test)[:, 1]
    
    test_metrics = {
        'accuracy': accuracy_score(y_test, y_test_pred),
        'precision': precision_score(y_test, y_test_pred, zero_division=0),
        'recall': recall_score(y_test, y_test_pred, zero_division=0),
        'f1': f1_score(y_test, y_test_pred, zero_division=0),
        'roc_auc': roc_auc_score(y_test, y_test_proba),
        'pr_auc': average_precision_score(y_test, y_test_proba)
    }
    
    cm_test = confusion_matrix(y_test, y_test_pred)
    
    print(f"\n   Métricas de TEST:")
    print(f"   {'='*50}")
    print(f"   Accuracy:  {test_metrics['accuracy']:.4f} ({test_metrics['accuracy']*100:.2f}%)")
    print(f"   Precision: {test_metrics['precision']:.4f}")
    print(f"   Recall:    {test_metrics['recall']:.4f}")
    print(f"   F1-Score:  {test_metrics['f1']:.4f}")
    print(f"   ROC AUC:   {test_metrics['roc_auc']:.4f}")
    print(f"   PR AUC:    {test_metrics['pr_auc']:.4f}")
    print(f"\n   Matriz de Confusión (Test):")
    print(f"   TN: {cm_test[0,0]:4d}  FP: {cm_test[0,1]:4d}")
    print(f"   FN: {cm_test[1,0]:4d}  TP: {cm_test[1,1]:4d}")
    
    # Guardar resultados
    print(f"\n💾 Guardando resultados...")
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Modelo
    joblib.dump(rf, output_path / "random_forest_model.pkl")
    
    # Métricas
    summary = {
        'timestamp': datetime.now().isoformat(),
        'model': 'RandomForest',
        'params': {
            'n_estimators': 100,
            'max_depth': 10,
            'min_samples_split': 10,
            'min_samples_leaf': 5,
            'class_weight': 'balanced'
        },
        'data_split': {
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'test_samples': len(X_test)
        },
        'val_metrics': val_metrics,
        'test_metrics': test_metrics,
        'confusion_matrix_val': cm_val.tolist(),
        'confusion_matrix_test': cm_test.tolist(),
        'feature_count': len(feature_cols)
    }
    
    with open(output_path / "training_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Feature importance
    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'importance': rf.feature_importances_
    }).sort_values('importance', ascending=False)
    
    importance_df.to_csv(output_path / "feature_importance.csv", index=False)
    
    print(f"   ✓ Modelo: {output_path / 'random_forest_model.pkl'}")
    print(f"   ✓ Métricas: {output_path / 'training_summary.json'}")
    print(f"   ✓ Features: {output_path / 'feature_importance.csv'}")
    
    # Top 10 features
    print(f"\n🔝 Top 10 Features más importantes:")
    print(f"   {'='*50}")
    for i, row in importance_df.head(10).iterrows():
        print(f"   {row['feature']:20s}: {row['importance']:.4f}")
    
    print(f"\n✅ ¡Entrenamiento completado exitosamente!")
    print(f"   Modelo final con PR AUC = {test_metrics['pr_auc']:.4f} en test")

if __name__ == "__main__":
    main()
