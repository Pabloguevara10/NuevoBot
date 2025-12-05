import pandas as pd
import os
import sys

# Importar el Laboratorio
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'tools')))
from precision_lab import PrecisionLab

def probar_herramientas():
    print("🔬 INICIANDO PRUEBA DE HERRAMIENTAS DE PRECISIÓN...\n")
    
    # 1. Cargar datos reales (Ej: 1 hora)
    path = 'logs/data_lab/history_AAVEUSDT_1h.csv'
    if not os.path.exists(path):
        print("❌ No se encontró archivo de datos. Ejecuta data_miner.py primero.")
        return

    df = pd.read_csv(path)
    print(f"📂 Datos cargados: {len(df)} velas de 1H.")
    print(f"   Último Precio: {df.iloc[-1]['close']}\n")

    # 2. Ejecutar Pruebas Individuales
    print("--- 1. ANÁLISIS RSI ---")
    res = PrecisionLab.analizar_rsi(df)
    print(res)

    print("\n--- 2. ANÁLISIS ADX ---")
    res = PrecisionLab.analizar_adx(df)
    print(res)

    print("\n--- 3. ANÁLISIS STOCH ---")
    res = PrecisionLab.analizar_stoch(df)
    print(res)

    print("\n--- 4. ANÁLISIS MACD ---")
    res = PrecisionLab.analizar_macd(df)
    print(res)
    
    print("\n--- 5. ANÁLISIS BOLLINGER ---")
    res = PrecisionLab.analizar_bb(df)
    print(res)

    print("\n✅ PRUEBA FINALIZADA. Las herramientas están listas para el Brain.")

if __name__ == "__main__":
    probar_herramientas()