import pandas as pd
import numpy as np

class MetricCalculator:
    def _calcular_indicadores_base(self, df):
        if df.empty or len(df) < 20: return {}
        df = df.copy()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # StochRSI
        min_rsi = rsi.rolling(14).min()
        max_rsi = rsi.rolling(14).max()
        stoch_rsi = (rsi - min_rsi) / (max_rsi - min_rsi) * 100
        
        # BB
        sma = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        width = upper - lower
        
        # EMA
        ema200 = df['close'].ewm(span=200, adjust=False).mean()

        # ADX
        try:
            high_diff = df['high'].diff()
            low_diff = -df['low'].diff()
            plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
            minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
            tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr)
            minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr)
            dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
            adx_val = dx.rolling(14).mean().iloc[-1]
        except: adx_val = 0.0

        def get_last(series, default=0.0):
            try: return float(series.iloc[-1]) if not np.isnan(series.iloc[-1]) else default
            except: return default

        return {
            'RSI': get_last(rsi, 50.0), 'STOCH_RSI': get_last(stoch_rsi, 50.0),
            'BB_UPPER': get_last(upper), 'BB_LOWER': get_last(lower), 'BB_MID': get_last(sma),
            'BB_WIDTH': get_last(width), 'EMA_200': get_last(ema200), 'ADX': get_last(pd.Series([adx_val])),
            'CLOSE': get_last(df['close'])
        }

    def generar_mtf_completo(self, df_1m):
        if df_1m.empty: return {}, {}
        df_1m = df_1m.copy()
        df_1m['ts'] = pd.to_datetime(df_1m['ts'], unit='ms')
        df_1m.set_index('ts', inplace=True)
        
        mtf_data = {}
        agg = {'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}
        tfs = {'1m': None, '3m': '3min', '5m': '5min', '15m': '15min', '30m': '30min', '1h': '1h', '4h': '4h', '1d': '1D'}
        daily_stats = {'prev_high': 0.0, 'prev_low': 0.0, 'curr_high': 0.0, 'curr_low': 0.0}

        for tf, rule in tfs.items():
            if tf == '1m':
                mtf_data['1m'] = self._calcular_indicadores_base(df_1m.reset_index())
            else:
                try:
                    df_res = df_1m.resample(rule).agg(agg).dropna()
                    if not df_res.empty:
                        mtf_data[tf] = self._calcular_indicadores_base(df_res.reset_index())
                        if tf == '1d':
                            daily_stats['curr_high'] = float(df_res.iloc[-1]['high'])
                            daily_stats['curr_low'] = float(df_res.iloc[-1]['low'])
                            if len(df_res) > 1:
                                daily_stats['prev_high'] = float(df_res.iloc[-2]['high'])
                                daily_stats['prev_low'] = float(df_res.iloc[-2]['low'])
                except: mtf_data[tf] = {}
        return mtf_data, daily_stats