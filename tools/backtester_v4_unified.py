import pandas as pd
import numpy as np
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
if project_root not in sys.path: sys.path.append(project_root)

from config.config import Config
from tools.precision_lab import PrecisionLab as Lab

class DynamicFVG:
    def __init__(self, top, bottom, tipo, time):
        self.top = top; self.bottom = bottom; self.type = tipo; self.created_at = time; self.active = True

class BacktesterV4Unified:
    """
    SENTINEL BACKTESTER V4.5 (Support for Triangulation V3.5 + CSV Saving Fixed)
    """
    def __init__(self):
        print("🚀 INICIANDO BACKTESTER V4.5 (Triangulación Trend + Sniper)...")
        self.cfg = Config()
        self.data_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'data_lab')
        self.trades_file = os.path.join(self.cfg.BASE_DIR, 'logs', 'simulation_trades_detailed.csv')
        self.fvg_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'bitacoras', 'fvg_registry.csv')
        self.capital = self.cfg.FIXED_CAPITAL_AMOUNT
        self.fvgs = [] 
        self.trades = []
        
        if os.path.exists(self.fvg_path):
            try:
                static_fvgs = pd.read_csv(self.fvg_path).to_dict('records')
                for f in static_fvgs:
                    self.fvgs.append(DynamicFVG(f['Top'], f['Bottom'], f['Type'], pd.to_datetime('2020-01-01')))
                print(f"   -> {len(self.fvgs)} FVGs estáticos cargados.")
            except: pass

    def _calc_adx(self, df):
        if len(df) < 20: 
            df['ADX'] = 0
            return df
        high_diff = df['high'].diff()
        low_diff = -df['low'].diff()
        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
        tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).mean() / atr)
        df['ADX'] = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0,1) * 100).rolling(14).mean()
        return df

    def _calc_rsi(self, df):
        delta = df['close'].diff()
        gain = (delta.where(delta>0, 0)).rolling(14).mean()
        loss = (-delta.where(delta<0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100/(1+rs))
        return df

    def cargar_datos(self):
        print(f"📂 Preparando Dataframes MTF...")
        try:
            dfs = {}
            # Cargar 1m
            path_1m = os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_1m.csv")
            if not os.path.exists(path_1m): return None
            df_1m = pd.read_csv(path_1m)
            col_ts = next((c for c in df_1m.columns if c in ['ts', 'timestamp', 'datetime']), None)
            if col_ts:
                sample = df_1m[col_ts].iloc[0]
                unit = 'ms' if sample > 1700000000000 else 's'
                df_1m['datetime'] = pd.to_datetime(df_1m[col_ts], unit=unit)
                df_1m.set_index('datetime', inplace=True)
            
            # Calcular RSI para 1m (Necesario para Refinamiento)
            dfs['1m'] = self._calc_rsi(df_1m)

            # Generar/Cargar otros TFs y sus Indicadores
            rules = {'5m': '5min', '15m': '15min', '1h': '1h', '4h': '4h'}
            for name, rule in rules.items():
                # Resample desde 1m para consistencia
                agg_dict = {'open':'first', 'high':'max', 'low':'min', 'close':'last'}
                sub_df = df_1m.resample(rule).agg(agg_dict).dropna()
                
                # Indicadores Específicos para Brain V3.5
                if name == '5m':
                    sub_df['EMA_7'] = sub_df['close'].ewm(span=7).mean()
                    sub_df['EMA_25'] = sub_df['close'].ewm(span=25).mean()
                
                if name == '15m':
                    sub_df = self._calc_adx(sub_df) # Necesario para Confirmación
                
                if name == '1h':
                    sub_df = self._calc_adx(sub_df) # Necesario para Contexto
                    sub_df = self._calc_rsi(sub_df)
                    # StochRSI
                    min_rsi = sub_df['RSI'].rolling(14).min()
                    max_rsi = sub_df['RSI'].rolling(14).max()
                    sub_df['STOCH_RSI'] = (sub_df['RSI'] - min_rsi) / (max_rsi - min_rsi).replace(0,1) * 100
                
                if name == '4h':
                    sub_df['EMA_200'] = sub_df['close'].ewm(span=200).mean()

                dfs[name] = sub_df

            # Merge Maestro (Base 1m)
            base = dfs['1m'].sort_index()
            for tf in ['5m', '15m', '1h', '4h']:
                other = dfs[tf].add_prefix(f"{tf}_").sort_index()
                base = pd.merge_asof(base, other, left_index=True, right_index=True, direction='backward')
            
            return base.dropna()
        except Exception as e:
            print(f"Error data: {e}")
            return None

    def ejecutar(self):
        df = self.cargar_datos()
        if df is None: return
        print(f"⚡ Auditando {len(df)} minutos...")
        
        pos = {}
        in_pos = False
        records = df.reset_index().to_dict('records') 
        
        SNIPER_SL_PCT = 0.025 
        TREND_SL_PCT = 0.015 
        
        for i in range(50, len(records)):
            row = records[i]
            price = row['close']
            
            # --- GESTIÓN DE SALIDAS ---
            if in_pos:
                exit_type = None
                pnl_usd = 0
                if pos['side'] == 'LONG':
                    if row['low'] <= pos['sl']: exit_type = 'STOP_LOSS'
                    elif row['high'] >= pos['tp']: exit_type = 'TAKE_PROFIT'
                else:
                    if row['high'] >= pos['sl']: exit_type = 'STOP_LOSS'
                    elif row['low'] <= pos['tp']: exit_type = 'TAKE_PROFIT'
                
                if exit_type:
                    exit_price = pos['sl'] if exit_type == 'STOP_LOSS' else pos['tp']
                    pct_diff = (exit_price - pos['entry']) / pos['entry'] if pos['side'] == 'LONG' else (pos['entry'] - exit_price) / pos['entry']
                    pnl_usd = self.capital * self.cfg.ShooterConfig.MODES[pos['mode']]['wallet_pct'] * self.cfg.LEVERAGE * pct_diff
                    self.trades.append({
                        'Entry_Time': pos['time'], 'Exit_Time': row['datetime'], 'Mode': pos['mode'], 'Side': pos['side'],
                        'Result': 'WIN' if pnl_usd > 0 else 'LOSS', 'PnL': round(pnl_usd, 2)
                    })
                    self.capital += pnl_usd
                    in_pos = False
                    pos = {}
                continue

            # --- CEREBRO V3.5 LOGIC SIMULATOR ---
            decision = "NONE"
            mode = ""
            side = ""
            
            # Variables de estado
            adx_1h = row.get('1h_ADX', 0)
            stoch_1h = row.get('1h_STOCH_RSI', 50)
            trend_4h = 'ALCISTA' if price > row.get('4h_EMA_200', 0) else 'BAJISTA'
            
            # 1. TREND TRIANGULATION
            # Gatillo 5m
            ema7_5m = row.get('5m_EMA_7', 0)
            ema25_5m = row.get('5m_EMA_25', 0)
            prev_ema7 = records[i-1].get('5m_EMA_7', 0)
            prev_ema25 = records[i-1].get('5m_EMA_25', 0)
            
            cruce_5m = False
            estado_5m = 'ALCISTA' if ema7_5m > ema25_5m else 'BAJISTA'
            prev_estado = 'ALCISTA' if prev_ema7 > prev_ema25 else 'BAJISTA'
            if estado_5m != prev_estado: cruce_5m = True
            
            if cruce_5m:
                # Confirmación 15m
                # No tenemos EMA 50 calculada en DF, usamos approx simple o pasamos
                # En simulacion simplificada asumimos validación ADX
                adx_15m = row.get('15m_ADX', 0)
                if adx_15m > 20:
                    # Refinamiento 1m
                    rsi_1m = row.get('RSI', 50)
                    entrada_ok = False
                    if estado_5m == 'ALCISTA' and rsi_1m < 80: entrada_ok = True
                    if estado_5m == 'BAJISTA' and rsi_1m > 20: entrada_ok = True
                    
                    if entrada_ok and trend_4h == estado_5m:
                        mode = "TREND_FOLLOWING"
                        side = "LONG" if estado_5m == 'ALCISTA' else "SHORT"
                        decision = "AUTHORIZED"

            # 2. SNIPER
            if decision != "AUTHORIZED":
                 for fvg in self.fvgs:
                    hit = (fvg.type=='LONG' and fvg.bottom <= price <= fvg.top) or \
                          (fvg.type=='SHORT' and fvg.top >= price >= fvg.bottom)
                    if hit:
                        mode = "SNIPER_FVG"
                        side = fvg.type
                        if not ((side == 'LONG' and trend_4h == 'BAJISTA') or (side == 'SHORT' and trend_4h == 'ALCISTA')):
                             decision = "AUTHORIZED"
                        break

            if decision == "AUTHORIZED":
                in_pos = True
                sl_pct = SNIPER_SL_PCT if mode == 'SNIPER_FVG' else TREND_SL_PCT
                sl_price = price * (1 - sl_pct) if side == 'LONG' else price * (1 + sl_pct)
                tp_price = price * 1.03 if side == 'LONG' else price * 0.97
                pos = {
                    'time': row['datetime'], 'side': side, 'mode': mode,
                    'entry': price, 'sl': sl_price, 'tp': tp_price
                }

    def generar_reporte(self):
        print("\n" + "="*60)
        print("📊 REPORTE FINAL DE SIMULACIÓN (V4.5 TRIANGULACIÓN)")
        print("="*60)
        if self.trades:
            df_trades = pd.DataFrame(self.trades)
            # GUARDAR CSV (AHORA SÍ)
            df_trades.to_csv(self.trades_file, index=False)
            
            print(f"\n📈 RESULTADOS FINALES:")
            print(f"   - Capital Final:   ${round(self.capital, 2)}")
            print(f"   - PnL Neto:        ${round(df_trades['PnL'].sum(), 2)}")
            print(f"   - Archivo Guardado: {self.trades_file}")
            print("\n   --- DESGLOSE POR MODO ---")
            grouped = df_trades.groupby('Mode').agg({'Result': 'count', 'PnL': 'sum'})
            print(grouped.to_string())

if __name__ == "__main__":
    bt = BacktesterV4Unified()
    bt.ejecutar()
    bt.generar_reporte()