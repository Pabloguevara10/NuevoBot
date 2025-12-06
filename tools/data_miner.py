import sys
import os
import pandas as pd
import numpy as np
import time

# Ajuste de path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from config.config import Config
from connections.api_manager import APIManager
from logs.system_logger import SystemLogger

class DataMiner:
    def __init__(self):
        print("⛏️  INICIANDO DATA MINER (Modo Integrado)...")
        self.cfg = Config()
        self.log = SystemLogger()
        self.conn = APIManager(self.cfg, self.log)
        
        if not self.conn.check_heartbeat()['binance']:
            print("❌ Error DataMiner: Sin conexión a Binance API.")
            # Nota: Si falla aquí, lanzará excepción en el main
            raise ConnectionError("Sin conexión a Binance")

    def descargar_historia_masiva(self, dias=90):
        """Descarga 'dias' de historia en velas de 1m."""
        symbol = self.cfg.SYMBOL
        interval = '1m'
        limit_per_req = 1000
        
        end_time = int(time.time() * 1000)
        start_time = end_time - (dias * 24 * 60 * 60 * 1000)
        
        print(f"📡 Descargando {dias} días de historia para {symbol}...")
        
        all_klines = []
        current_start = start_time
        
        while True:
            progress = (current_start - start_time) / (end_time - start_time) * 100
            sys.stdout.write(f"\r   Progreso: [{progress:.1f}%] Descargando...")
            sys.stdout.flush()
            
            try:
                klines = self.conn.client.futures_klines(
                    symbol=symbol, 
                    interval=interval, 
                    startTime=current_start,
                    limit=limit_per_req
                )
            except Exception as e:
                print(f"\n⚠️ Error de red: {e}. Reintentando...")
                time.sleep(2)
                continue
            
            if not klines: break
            
            all_klines.extend(klines)
            last_close_time = klines[-1][6]
            current_start = last_close_time + 1
            
            if len(klines) < limit_per_req or current_start >= end_time:
                break
            time.sleep(0.1)

        print(f"\n✅ Descarga completada. Total velas: {len(all_klines)}")
        
        df = pd.DataFrame(all_klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'q_vol', 'trades', 'tb_vol', 'tb_q_vol', 'ignore'
        ])
        
        df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']]
        df.columns = ['ts', 'open', 'high', 'low', 'close', 'volume']
        
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].astype(float)
        
        return df

    def calcular_indicadores(self, df):
        if df.empty: return df
        df = df.copy()

        # Indicadores Base para Brain
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        min_rsi = df['RSI'].rolling(14).min()
        max_rsi = df['RSI'].rolling(14).max()
        denom = (max_rsi - min_rsi).replace(0, 1)
        df['STOCH_RSI'] = (df['RSI'] - min_rsi) / denom * 100
        
        sma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['BB_UPPER'] = sma + (std * 2)
        df['BB_LOWER'] = sma - (std * 2)
        df['BB_MID'] = sma
        
        df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        high_diff = df['high'].diff()
        low_diff = -df['low'].diff()
        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
        
        tr = pd.concat([
            df['high'] - df['low'], 
            (df['high'] - df['close'].shift(1)).abs(), 
            (df['low'] - df['close'].shift(1)).abs()
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(14).mean()
        
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).mean() / atr)
        
        sum_di = (plus_di + minus_di).replace(0, 1)
        dx = (abs(plus_di - minus_di) / sum_di) * 100
        df['ADX'] = dx.rolling(14).mean()
        
        return df.dropna()

    def generar_dataset_maestro(self, df_1m):
        timeframes = {'5m': '5min', '15m': '15min', '1h': '1h', '4h': '4h'}
        agg_rules = {'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}
        
        print("\n⚙️  Procesando temporalidades...")
        
        df_1m['datetime'] = pd.to_datetime(df_1m['ts'], unit='ms')
        
        # 1m
        print("   -> Calculando 1m...")
        df_1m_calc = self.calcular_indicadores(df_1m.copy())
        self._guardar_csv(df_1m_calc, '1m')
        
        # MTF
        for tf, rule in timeframes.items():
            print(f"   -> Calculando {tf}...")
            df_res = df_1m.set_index('datetime').resample(rule).agg(agg_rules).dropna().reset_index()
            df_res['ts'] = df_res['datetime'].astype(np.int64) // 10**6
            df_calc = self.calcular_indicadores(df_res)
            self._guardar_csv(df_calc, tf)

    def _guardar_csv(self, df, tf):
        filename = f"history_{self.cfg.SYMBOL}_{tf}.csv"
        path = os.path.join(self.cfg.BASE_DIR, 'logs', 'data_lab', filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        cols_to_save = ['ts', 'open', 'high', 'low', 'close', 'volume', 
                       'RSI', 'STOCH_RSI', 'BB_UPPER', 'BB_LOWER', 'BB_MID', 'EMA_200', 'ADX']
        final_cols = [c for c in cols_to_save if c in df.columns]
        
        df[final_cols].to_csv(path, index=False)

if __name__ == "__main__":
    miner = DataMiner()
    data = miner.descargar_historia_masiva(dias=90)
    miner.generar_dataset_maestro(data)