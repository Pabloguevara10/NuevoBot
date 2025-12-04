import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# Ajuste de path para importar config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.config import Config

class PatternMiner:
    """
    MINERO DE PATRONES PROFUNDO (DEEP PATTERN MINER)
    Genera una radiografía completa de todos los indicadores (RSI, ADX, MACD, EMAs, Stoch)
    en una ventana de -3/+3 velas alrededor de un cruce de medias.
    """
    def __init__(self):
        print("🕵️  INICIANDO PATTERN MINER (MODO PROFUNDO)...")
        self.cfg = Config()
        self.data_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'data_lab')
        self.output_file = os.path.join(self.cfg.BASE_DIR, 'logs', 'patterns_db_full.csv')
        self.datasets = {}
        
    def cargar_datos(self):
        """Carga los CSV generados por DataMiner."""
        tfs = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'] # Agregado 30m por si acaso
        print("📂 Cargando Laboratorio de Datos...")
        
        for tf in tfs:
            filename = f"history_{self.cfg.SYMBOL}_{tf}.csv"
            path = os.path.join(self.data_path, filename)
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    # Compatibilidad con nombres de columnas
                    df.columns = df.columns.str.strip()
                    if 'ts' in df.columns:
                        df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
                    elif 'timestamp' in df.columns:
                        df['datetime'] = pd.to_datetime(df['timestamp'])
                        
                    df = df.sort_values('datetime').reset_index(drop=True)
                    self.datasets[tf] = df
                    print(f"   -> {tf}: {len(df)} registros listos.")
                except Exception as e:
                    print(f"   x Error leyendo {tf}: {e}")
            else:
                pass # Silencioso si falta alguno

    def _calcular_indicadores_faltantes(self, df):
        """
        Calcula indicadores que no vienen en el CSV original (EMAs cortas, MACD).
        El CSV ya trae: RSI, STOCH_RSI, ADX, BB_*, EMA_200.
        Nosotros agregamos: EMA 7, 25, 99 y MACD.
        """
        df = df.copy()
        
        # 1. EMAs Tácticas
        df['EMA_7'] = df['close'].ewm(span=7, adjust=False).mean()
        df['EMA_25'] = df['close'].ewm(span=25, adjust=False).mean()
        df['EMA_99'] = df['close'].ewm(span=99, adjust=False).mean()
        
        # 2. MACD (12, 26, 9)
        k_fast = df['close'].ewm(span=12, adjust=False).mean()
        k_slow = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD_DIF'] = k_fast - k_slow
        df['MACD_DEA'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_HIST'] = df['MACD_DIF'] - df['MACD_DEA']
        
        return df

    def refinar_evento_con_1m(self, trigger_time, timeframe_str, tipo_evento):
        """Busca el precio pivote exacto en la data de 1m."""
        if '1m' not in self.datasets: return trigger_time, 0
        
        df_1m = self.datasets['1m']
        
        # Mapeo de duración de vela
        deltas = {
            '5m': 5, '15m': 15, '30m': 30, 
            '1h': 60, '4h': 240, '1d': 1440
        }
        minutes = deltas.get(timeframe_str, 1)
        
        # La vela de TF mayor termina en trigger_time. Buscamos hacia atrás.
        end_search = trigger_time
        start_search = trigger_time - timedelta(minutes=minutes)
        
        mask = (df_1m['datetime'] > start_search) & (df_1m['datetime'] <= end_search)
        subset = df_1m.loc[mask]
        
        if subset.empty: return trigger_time, 0
        
        # Lógica de Pivote:
        # Cruce ALCISTA (Golden) -> El precio venía bajando y rebotó -> Buscamos MÍNIMO
        # Cruce BAJISTA (Death) -> El precio venía subiendo y cayó -> Buscamos MÁXIMO
        if 'BULL' in tipo_evento:
            idx = subset['low'].idxmin()
            return subset.loc[idx]['datetime'], subset.loc[idx]['low']
        else:
            idx = subset['high'].idxmax()
            return subset.loc[idx]['datetime'], subset.loc[idx]['high']

    def minar_patrones(self):
        if not self.datasets: 
            print("❌ No hay datos cargados.")
            return
        
        patrones = []
        print("\n🔨 Minando Patrones Complejos...")
        
        # Lista de indicadores a reportar en la secuencia -3 a +3
        indicadores_clave = [
            'close', 'RSI', 'STOCH_RSI', 'ADX', 
            'EMA_7', 'EMA_25', 'EMA_99', 'EMA_200', 
            'MACD_DIF', 'MACD_DEA', 'MACD_HIST',
            'BB_UPPER', 'BB_LOWER' # Para calcular ancho o posición
        ]
        
        for tf, df_raw in self.datasets.items():
            if tf == '1m': continue # 1m es solo para lupa
            
            print(f"   Analizando Temporalidad: {tf}...")
            df = self._calcular_indicadores_faltantes(df_raw)
            
            # Detectar Cruces EMA 7/25
            df['prev_ema7'] = df['EMA_7'].shift(1)
            df['prev_ema25'] = df['EMA_25'].shift(1)
            
            cross_bull = (df['prev_ema7'] < df['prev_ema25']) & (df['EMA_7'] > df['EMA_25'])
            cross_bear = (df['prev_ema7'] > df['prev_ema25']) & (df['EMA_7'] < df['EMA_25'])
            
            # Recolectar eventos
            eventos = []
            eventos.extend([(i, 'CROSS_BULL') for i in df.index[cross_bull]])
            eventos.extend([(i, 'CROSS_BEAR') for i in df.index[cross_bear]])
            
            for idx, tipo in eventos:
                # Validar bordes (necesitamos espacio para -3 y +3)
                if idx < 3 or idx >= len(df) - 3: continue
                
                row = df.iloc[idx]
                
                # 1. Refinamiento con Lupa 1m
                ts_exacto, precio_exacto = self.refinar_evento_con_1m(row['datetime'], tf, tipo)
                
                # 2. Construir la Ficha del Patrón
                ficha = {
                    'Timeframe': tf,
                    'Event_Type': tipo,
                    'Trigger_Time': row['datetime'],
                    'Refined_Time': ts_exacto,
                    'Refined_Price': precio_exacto,
                    'Trend_Context': 'BULL' if row['close'] > row['EMA_99'] else 'BEAR'
                }
                
                # 3. Capturar Secuencia (-3 a +3) de TODOS los indicadores
                for offset in range(-3, 4):
                    r_offset = df.iloc[idx + offset]
                    prefijo = f"T{offset}" # T-3, T0, T3
                    
                    for ind in indicadores_clave:
                        val = r_offset.get(ind, 0)
                        # Redondeo inteligente para ahorrar espacio
                        if 'RSI' in ind or 'STOCH' in ind or 'ADX' in ind: val = round(val, 1)
                        elif 'MACD' in ind: val = round(val, 4)
                        else: val = round(val, 2)
                        
                        ficha[f"{prefijo}_{ind}"] = val
                        
                patrones.append(ficha)

        # Guardar
        if patrones:
            df_final = pd.DataFrame(patrones)
            df_final.to_csv(self.output_file, index=False)
            print(f"\n✅ REPORTE GENERADO: {self.output_file}")
            print(f"   Total Patrones Detectados: {len(df_final)}")
            print("   Columnas generadas por patrón: RSI, STOCH, ADX, MACD, EMAs (x7 intervalos)")
        else:
            print("⚠️ No se encontraron patrones de cruce en los datos actuales.")

if __name__ == "__main__":
    miner = PatternMiner()
    miner.cargar_datos()
    miner.minar_patrones()