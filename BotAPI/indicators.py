# indicators.py
import pandas as pd
import numpy as np

class MarketAnalyzer:
    """(Legacy) Visualización Header."""
    def __init__(self, df):
        self.df = df
    
    def calcular_todo(self, rsi_period=14):
        if self.df.empty: return self.df
        df = self.df.copy()
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        return df.fillna(0)

    def obtener_extremos_locales(self, window=20):
        if self.df.empty: return 0, 0
        return self.df['low'].tail(window).min(), self.df['high'].tail(window).max()

class MTFAnalyzer:
    """Generador de Matriz Multi-Temporalidad."""
    def __init__(self, df_1m, df_15m):
        self.df_1m = df_1m
        self.df_15m = df_15m
        self.data = {}

    def _resample(self, df_origin, timeframe_rule):
        if df_origin.empty: return pd.DataFrame()
        df = df_origin.copy()
        if 'timestamp' in df.columns:
            df.set_index('timestamp', inplace=True)
        agg_rules = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        try: return df.resample(timeframe_rule).agg(agg_rules).dropna()
        except: return pd.DataFrame()

    def _calc_metrics(self, df):
        if len(df) < 200: # Necesitamos 200 velas para la EMA
            return {
                'RSI': 50.0, 'STOCH_RSI': 50.0, 'K': 50.0, 'BB_UPPER': 0.0, 'BB_MID': 0.0, 
                'BB_LOWER': 0.0, 'BB_WIDTH': 0.0, 'VOL_SCORE': 0.0, 'CLOSE': 0.0, 
                'BB_POS': 'MID', 'EMA_200': 0.0
            }
        
        # Indicadores Básicos
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        min_rsi = rsi.rolling(14).min()
        max_rsi = rsi.rolling(14).max()
        stoch_rsi = (rsi - min_rsi) / (max_rsi - min_rsi) * 100
        
        low14 = df['low'].rolling(14).min()
        high14 = df['high'].rolling(14).max()
        k = 100 * ((df['close'] - low14) / (high14 - low14))
        
        # Bollinger
        sma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        width = upper - lower
        
        # Volumen
        vol_ma = df['volume'].rolling(20).mean()
        vol_ref = vol_ma.iloc[-1] if vol_ma.iloc[-1] > 0 else 1
        vol_score = (df['volume'].iloc[-1] / vol_ref) * 50
        vol_score = min(100, max(0, vol_score))

        # EMA 200 (FILTRO DE TENDENCIA)
        ema200 = df['close'].ewm(span=200, adjust=False).mean()

        last_c = df['close'].iloc[-1]
        last_u = upper.iloc[-1]
        last_l = lower.iloc[-1]
        bb_pos = 'MID'
        if last_c >= last_u: bb_pos = 'UPPER'
        elif last_c <= last_l: bb_pos = 'LOWER'
        
        return {
            'RSI': float(rsi.iloc[-1]),
            'STOCH_RSI': float(stoch_rsi.iloc[-1]), 
            'K': float(k.iloc[-1]),
            'BB_UPPER': float(last_u),
            'BB_MID': float(sma.iloc[-1]),
            'BB_LOWER': float(last_l),
            'BB_WIDTH': float(width.iloc[-1]),
            'VOL_SCORE': float(vol_score),
            'CLOSE': float(last_c),
            'BB_POS': bb_pos,
            'EMA_200': float(ema200.iloc[-1]) # <--- NUEVO
        }

    def generar_matriz(self):
        self.data['1m'] = self._calc_metrics(self.df_1m)
        self.data['3m'] = self._calc_metrics(self._resample(self.df_1m, '3min'))
        self.data['5m'] = self._calc_metrics(self._resample(self.df_1m, '5min'))
        self.data['15m'] = self._calc_metrics(self.df_15m)
        self.data['30m'] = self._calc_metrics(self._resample(self.df_15m, '30min'))
        self.data['1h'] = self._calc_metrics(self._resample(self.df_15m, '1h'))
        self.data['4h'] = self._calc_metrics(self._resample(self.df_15m, '4h'))
        return self.data