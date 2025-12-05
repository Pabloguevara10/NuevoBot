import pandas as pd
import numpy as np

class MetricCalculator:
    def _calcular_indicadores_base(self, df):
        if df.empty or len(df) < 20: return {}, None
        df = df.copy()
        
        # 1. RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 2. StochRSI
        min_rsi = df['RSI'].rolling(14).min()
        max_rsi = df['RSI'].rolling(14).max()
        denom = (max_rsi - min_rsi).replace(0, 1)
        df['STOCH_RSI'] = (df['RSI'] - min_rsi) / denom * 100
        
        # 3. Bollinger
        sma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['BB_UPPER'] = sma + (std * 2)
        df['BB_LOWER'] = sma - (std * 2)
        df['BB_MID'] = sma
        df['BB_WIDTH'] = (df['BB_UPPER'] - df['BB_LOWER']) / df['BB_MID']
        
        # 4. EMAs
        df['EMA_7'] = df['close'].ewm(span=7, adjust=False).mean()
        df['EMA_25'] = df['close'].ewm(span=25, adjust=False).mean()
        df['EMA_99'] = df['close'].ewm(span=99, adjust=False).mean()
        df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()

        # 5. ADX
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
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0,1)) * 100
        df['ADX'] = dx.rolling(14).mean()
        
        # 6. MACD
        k_fast = df['close'].ewm(span=12, adjust=False).mean()
        k_slow = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD_DIF'] = k_fast - k_slow
        df['MACD_DEA'] = df['MACD_DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_HIST'] = df['MACD_DIF'] - df['MACD_DEA']

        # Extraer última fila para Dashboard (Resumen)
        last_row = df.iloc[-1].to_dict()
        last_row['CLOSE'] = last_row['close']
        
        # Retornamos el Resumen Y el DataFrame completo
        return last_row, df 

    def generar_mtf_completo(self, df_1m):
        if df_1m.empty: return {}, {}
        df_1m = df_1m.copy()
        
        if 'ts' in df_1m.columns:
            df_1m['datetime'] = pd.to_datetime(df_1m['ts'], unit='ms')
            df_1m.set_index('datetime', inplace=True)
        
        mtf_data = {}
        agg = {'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}
        tfs = {'1m': None, '3m': '3min', '5m': '5min', '15m': '15min', '30m': '30min', '1h': '1h', '4h': '4h', '1d': '1D'}
        daily_stats = {'prev_high': 0.0, 'prev_low': 0.0, 'curr_high': 0.0, 'curr_low': 0.0}

        for tf, rule in tfs.items():
            try:
                if tf == '1m':
                    df_res = df_1m
                else:
                    df_res = df_1m.resample(rule).agg(agg).dropna()
                
                if not df_res.empty:
                    resumen, df_calculado = self._calcular_indicadores_base(df_res.reset_index())
                    
                    # Guardamos AMBOS datos
                    mtf_data[tf] = resumen          # Para Dashboard (ligero)
                    mtf_data[f'df_{tf}'] = df_calculado # Para PrecisionLab (pesado)
                    
                    if tf == '1d':
                        daily_stats['curr_high'] = float(df_res.iloc[-1]['high'])
                        daily_stats['curr_low'] = float(df_res.iloc[-1]['low'])
                        if len(df_res) > 1:
                            daily_stats['prev_high'] = float(df_res.iloc[-2]['high'])
                            daily_stats['prev_low'] = float(df_res.iloc[-2]['low'])
            except:
                mtf_data[tf] = {}

        return mtf_data, daily_stats