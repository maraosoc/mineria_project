#!/usr/bin/env python3
"""
Script para procesar todas las zonas en paralelo
Usa multiprocessing para maximizar el uso de CPU
"""

import subprocess
import multiprocessing as mp
from datetime import datetime
import sys
import os
import argparse

# Lista de todas las zonas a procesar
ZONES = [
    "14_ElDanubio_Granada_Meta",
    "21_LaPalmera_Granada_Cundinamarca",
    "28_Montebello_Barrancabermeja_Santander",
    "29_Cuiva_SantaRosadeOsos_Antioquia",
    "32_LosNaranjos_Venecia_Antioquia",
    "35_Bellavista_Albán_Cundinamarca",
    "41_Cárpatos_LaUnión_Antioquia",
    "42_VillaLuzA_Unguía_Chocó",
    "44_SantaRosa_SanLuisdeGaceno_Boyacá",
    "54_LaAlameda_Prado_Tolima",
    "55_ElEdén_SantaRosadeOsos_Antioquia",
    "59_SanGabriel_Belmira_Antioquia",
    "69_Guabineros_Zarzal_ValledelCauca",
    "72_ElPorro_PuebloNuevo_Córdoba",
    "79_SanJerónimo_Pore_Casanare"
]

def process_zone(zone_name):
    """
    Procesa una zona individual
    """
    start_time = datetime.now()
    print(f"\n{'='*80}")
    print(f"[{start_time.strftime('%H:%M:%S')}] INICIO - Zona: {zone_name}")
    print(f"{'='*80}")
    
    # Construir el comando
    cmd = [
        "python3",
        "/home/ubuntu/mineria_project/scripts/01_procesar_sentinel_clip.py",
        "--input", f"s3://mineria-project/raw/raw_copernicus/{zone_name}/",
        "--output", "s3://mineria-project/staging/01_rasters_procesados_clipped/",
        "--zone_name", zone_name,
        "--shape_path", f"s3://mineria-project/raw/shapes/{zone_name}/Perímetro",
        "--clip"
    ]
    
    try:
        # Ejecutar el comando
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200  # 2 horas máximo por zona
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds() / 60
        
        if result.returncode == 0:
            print(f"\n[OK] Zona {zone_name} completada exitosamente")
            print(f"Duración: {duration:.1f} minutos")
            return {
                "zone": zone_name,
                "status": "success",
                "duration_minutes": duration,
                "stdout": result.stdout[-1000:],  # Últimas 1000 líneas
            }
        else:
            print(f"\n[ERROR] Zona {zone_name} falló con código {result.returncode}")
            print(f"Error: {result.stderr[-500:]}")
            return {
                "zone": zone_name,
                "status": "error",
                "duration_minutes": duration,
                "error": result.stderr[-500:],
            }
            
    except subprocess.TimeoutExpired:
        print(f"\n[TIMEOUT] Zona {zone_name} excedió el tiempo límite (2 horas)")
        return {
            "zone": zone_name,
            "status": "timeout",
            "duration_minutes": 120,
        }
    except Exception as e:
        print(f"\n[ERROR] Excepción procesando zona {zone_name}: {str(e)}")
        return {
            "zone": zone_name,
            "status": "exception",
            "error": str(e),
        }

def main():
    parser = argparse.ArgumentParser(description="Procesar todas las zonas en paralelo")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Número de procesos paralelos (default: 4)"
    )
    parser.add_argument(
        "--zones",
        nargs="+",
        default=ZONES,
        help="Lista de zonas específicas a procesar (default: todas)"
    )
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    print(f"\n{'='*80}")
    print(f"PROCESAMIENTO PARALELO DE ZONAS")
    print(f"{'='*80}")
    print(f"Inicio: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Zonas a procesar: {len(args.zones)}")
    print(f"Workers paralelos: {args.workers}")
    print(f"{'='*80}\n")
    
    # Procesar zonas en paralelo
    with mp.Pool(processes=args.workers) as pool:
        results = pool.map(process_zone, args.zones)
    
    # Resumen final
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds() / 60
    
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] == "error")
    timeout_count = sum(1 for r in results if r["status"] == "timeout")
    exception_count = sum(1 for r in results if r["status"] == "exception")
    
    print(f"\n{'='*80}")
    print(f"RESUMEN FINAL")
    print(f"{'='*80}")
    print(f"Fin: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duración total: {total_duration:.1f} minutos")
    print(f"\nResultados:")
    print(f"  [OK] Exitosas: {success_count}")
    print(f"  [ERROR] Errores: {error_count}")
    print(f"  [TIMEOUT] Timeouts: {timeout_count}")
    print(f"  [EXCEPTION] Excepciones: {exception_count}")
    print(f"\nDetalle por zona:")
    
    for result in results:
        status_icon = {
            "success": "[OK]",
            "error": "[ERROR]",
            "timeout": "[TIMEOUT]",
            "exception": "[EXCEPTION]"
        }[result["status"]]
        
        duration = result.get("duration_minutes", 0)
        print(f"  {status_icon} {result['zone']}: {duration:.1f} min")
    
    print(f"{'='*80}\n")
    
    # Verificar logs de corrupción
    print("\nVerificando logs de archivos corruptos...")
    try:
        import boto3
        s3 = boto3.client('s3')
        response = s3.list_objects_v2(
            Bucket='mineria-project',
            Prefix='logs/01_procesar_sentinel/'
        )
        
        if 'Contents' in response:
            log_files = [obj['Key'] for obj in response['Contents']]
            print(f"Se generaron {len(log_files)} archivos de log de corrupción")
            for log_file in log_files:
                print(f"  - {log_file}")
        else:
            print("No se encontraron archivos de log de corrupción")
            
    except Exception as e:
        print(f"Error verificando logs: {e}")
    
    return 0 if error_count + timeout_count + exception_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
