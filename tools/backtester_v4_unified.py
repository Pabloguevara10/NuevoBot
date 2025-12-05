import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# -------------------------------------------------------------------------
# 1. CONFIGURACIÓN DINÁMICA DE ENTORNO
# -------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from config.config import Config
from tools.precision_lab import PrecisionLab as Lab

class DynamicFVG:
    def __init__(self, top, bottom, tipo, time):
        self.top = top; self.bottom = bottom; self.type = tipo; self.created_at = time; self.active = True

class BacktesterV4Unified:
    """
    SENTINEL BACKTESTER V4.1 (Unified Logic + Forensic Audit)
    Simula estrategias, gestiona capital y audita oportunidades perdidas.
    """
    def __init__(self):
        print("🚀 INICIANDO BACKTESTER V4.1 (Entorno Local Detectado)...")
        self.cfg = Config()
        self.data_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'data_lab')
        self.audit_file = os.path.join(self.cfg.BASE_DIR, 'logs', 'simulation_audit_final.csv')
        self.fvg_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'bitacoras', 'fvg_registry.csv')
        
        self.capital = self.cfg.FIXED_CAPITAL_AMOUNT
        self.fvgs = [] 
        self.audit_log = [] 
        self.trades = []
        
        # Cargar FVGs estáticos si existen
        if os.path.exists(self.fvg_path):
            try:
                static_fvgs = pd.read_csv(self.fvg_path).to_dict('records')
                for f in static_fvgs:
                    self.fvgs.append(DynamicFVG(f['Top'], f['Bottom'], f['Type'], pd.to_datetime('2020-01-01')))
                print(f"   -> {len(self.fvgs)} FVGs estáticos cargados como base.")
            except: pass

    def cargar_datos(self):
        print(f"📂 Buscando datos en: {self.data_path}")
        try:
            dfs = {}
            # CORRECCIÓN: Agregado '15m' a la lista requerida
            tfs_requeridos = ['1m', '5m', '15m', '1h', '4h']
            
            for tf in tfs_requeridos:
                path = os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_{tf}.csv")
                
                # Lógica de Carga o Generación
                df = None
                if os.path.exists(path):
                    df = pd.read_csv(path)
                    df.columns = df.columns.str.strip()
                    # Parseo fechas
                    col_ts = next((c for c in df.columns if c in ['ts', 'timestamp', 'datetime']), None)
                    if col_ts:
                        if col_ts == 'ts': df['datetime'] = pd.to_datetime(df[col_ts], unit='ms')
                        else: df['datetime'] = pd.to_datetime(df[col_ts])
                        df.set_index('datetime', inplace=True)
                
                # Si falta archivo o falló carga, intentar generar desde 1m
                if df is None or df.empty:
                    if tf in ['5m', '15m'] and '1m' in dfs:
                        # print(f"   Generando {tf} desde 1m...")
                        rule = '5min' if tf == '5m' else '15min'
                        df = dfs['1m'].resample(rule).agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}).dropna()
                    else:
                        print(f"❌ Falta archivo crítico: {path}")
                        return None
                
                dfs[tf] = df

            # Calcular Indicadores Auxiliares
            for tf, df in dfs.items():
                df['EMA_7'] = df['close'].ewm(span=7).mean()
                df['EMA_25'] = df['close'].ewm(span=25).mean()
                
                if tf in ['1h', '4h']: 
                    df['EMA_200'] = df['close'].ewm(span=200).mean()
                    if 'EMA_99' not in df.columns: df['EMA_99'] = df['close'].ewm(span=99).mean()
                
                if 'RSI' not in df.columns:
                    delta = df['close'].diff()
                    gain = (delta.where(delta>0, 0)).rolling(14).mean()
                    loss = (-delta.where(delta<0, 0)).rolling(14).mean()
                    rs = gain / loss
                    df['RSI'] = 100 - (100/(1+rs))

                if tf == '1h':
                    min_rsi = df['RSI'].rolling(14).min()
                    max_rsi = df['RSI'].rolling(14).max()
                    df['STOCH_RSI'] = (df['RSI'] - min_rsi) / (max_rsi - min_rsi).replace(0,1) * 100
                    
                    # ADX Simple
                    high_diff = df['high'].diff()
                    low_diff = -df['low'].diff()
                    plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
                    minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
                    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift(1)).abs(), (df['low']-df['close'].shift(1)).abs()], axis=1).max(axis=1)
                    atr = tr.rolling(14).mean()
                    plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr)
                    minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr)
                    df['ADX'] = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0,1) * 100).rolling(14).mean()
                
                if tf == '15m':
                    sma = df['close'].rolling(20).mean()
                    std = df['close'].rolling(20).std()
                    df['BB_UPPER'] = sma + (std * 2)
                    df['BB_LOWER'] = sma - (std * 2)

            # Merge Maestro
            print("   Sincronizando Reloj Maestro...")
            base = dfs['1m'].sort_index()
            for tf in ['5m', '15m', '1h', '4h']:
                other = dfs[tf].add_prefix(f"{tf}_").sort_index()
                base = pd.merge_asof(base, other, left_index=True, right_index=True, direction='backward')
            
            return base.dropna()

        except Exception as e:
            print(f"❌ Error procesando datos: {e}")
            # import traceback
            # traceback.print_exc()
            return None

    def detectar_fvg(self, row, prev, prev2):
        if prev2['high'] < row['low']:
            gap = row['low'] - prev2['high']
            if gap > (row['close'] * 0.001): return DynamicFVG(row['low'], prev2['high'], 'LONG', row['datetime'])
        if prev2['low'] > row['high']:
            gap = prev2['low'] - row['high']
            if gap > (row['close'] * 0.001): return DynamicFVG(prev2['low'], row['high'], 'SHORT', row['datetime'])
        return None

    def ejecutar(self):
        df = self.cargar_datos()
        if df is None: return

        print(f"⚡ Auditando {len(df)} minutos de mercado...")
        
        in_pos = False
        pos = {}
        records = df.reset_index().to_dict('records') 
        
        for i in range(50, len(records)):
            row = records[i]
            
            # 1. MANTENIMIENTO FVG
            self.fvgs = [f for f in self.fvgs if (row['datetime'] - f.created_at).total_seconds() < 14400]
            new_fvg = self.detectar_fvg(row, records[i-1], records[i-2])
            if new_fvg: self.fvgs.append(new_fvg)
            
            # 2. GESTIÓN DE POSICIÓN (Salida Simulado)
            if in_pos:
                price = row['close']
                exit_type = None
                pnl_trade = 0
                
                if pos['side'] == 'LONG':
                    if price <= pos['sl']: exit_type, pnl_trade = 'SL', -15
                    elif price >= pos['tp']: exit_type, pnl_trade = 'TP', 30
                else:
                    if price >= pos['sl']: exit_type, pnl_trade = 'SL', -15
                    elif price <= pos['tp']: exit_type, pnl_trade = 'TP', 30
                
                if exit_type:
                    pos['status'] = 'CLOSED'
                    pos['result'] = 'WIN' if pnl_trade > 0 else 'LOSS'
                    pos['pnl'] = pnl_trade
                    pos['exit_reason'] = exit_type
                    self.trades.append(pos)
                    self.capital += pnl_trade
                    in_pos = False
                continue

            # 3. CEREBRO V3.3
            price = row['close']
            
            # Contexto
            trend_4h = 'ALCISTA' if price > row['4h_EMA_200'] else 'BAJISTA'
            stoch_1h = row.get('1h_STOCH_RSI', 50)
            adx_1h = row.get('1h_ADX', 0)
            
            decision = "NONE"
            reason = "No Signal"
            mode = ""
            side = ""
            
            # --- ESTRATEGIA A: TREND FOLLOWING ---
            trend_signal = None
            ema7 = row['5m_EMA_7']; ema25 = row['5m_EMA_25']
            if ema7 > ema25 and records[i-1]['5m_EMA_7'] <= records[i-1]['5m_EMA_25']: trend_signal = 'LONG'
            if ema7 < ema25 and records[i-1]['5m_EMA_7'] >= records[i-1]['5m_EMA_25']: trend_signal = 'SHORT'
            
            if trend_signal and adx_1h > 20:
                mode = "TREND_FOLLOWING"
                side = trend_signal
                
                if (side=='LONG' and trend_4h=='BAJISTA') or (side=='SHORT' and trend_4h=='ALCISTA'):
                    decision = "REJECTED"; reason = "Contra Tendencia 4H"
                elif (side=='LONG' and stoch_1h > 80) or (side=='SHORT' and stoch_1h < 20):
                    decision = "REJECTED"; reason = "1H Agotado"
                else:
                    decision = "AUTHORIZED"; reason = "Trend Validada"

            # --- ESTRATEGIA B: SNIPER FVG ---
            if decision != "AUTHORIZED":
                for fvg in self.fvgs:
                    if fvg.active:
                        if (fvg.type=='LONG' and fvg.bottom<=price<=fvg.top) or (fvg.type=='SHORT' and fvg.top>=price>=fvg.bottom):
                            mode = "SNIPER_FVG"
                            side = fvg.type
                            
                            if (side == 'LONG' and trend_4h == 'BAJISTA') or (side == 'SHORT' and trend_4h == 'ALCISTA'):
                                decision = "REJECTED"; reason = "Contra Tendencia 4H (FVG)"
                            elif (side == 'LONG' and stoch_1h > 80) or (side == 'SHORT' and stoch_1h < 20):
                                decision = "REJECTED"; reason = "1H Agotado (FVG)"
                            else:
                                # Gatillo: Divergencia 1m (Simulada con RSI)
                                subset = pd.DataFrame(records[i-15:i+1])
                                div = Lab.detectar_divergencia(subset)
                                if (side=='LONG' and div=='BULLISH_DIV') or (side=='SHORT' and div=='BEARISH_DIV'):
                                    decision = "AUTHORIZED"; reason = "FVG + Div Confirmada"
                                else:
                                    decision = "REJECTED"; reason = "Falta Divergencia 1m"
                            break

            # --- ESTRATEGIA C: SCALP BB ---
            if decision != "AUTHORIZED" and adx_1h < 20:
                bb_up = row['15m_BB_UPPER']; bb_low = row['15m_BB_LOWER']
                scalp_side = None
                if price <= bb_low: scalp_side = 'LONG'
                elif price >= bb_up: scalp_side = 'SHORT'
                
                if scalp_side:
                    mode = "SCALP_BB"
                    side = scalp_side
                    
                    # Gatillo 5m
                    rsi_5m = row['5m_RSI']
                    rsi_prev = records[i-5]['5m_RSI']
                    slope = rsi_5m - rsi_prev
                    
                    if (side=='LONG' and trend_4h=='ALCISTA' and stoch_1h < 80):
                        if rsi_5m < 40 and slope > 0:
                            decision = "AUTHORIZED"; reason = "Scalp 15m + Giro 5m"
                        else:
                            decision = "REJECTED"; reason = "Falta Giro RSI 5m"
                    elif (side=='SHORT' and trend_4h=='BAJISTA' and stoch_1h > 20):
                        if rsi_5m > 60 and slope < 0:
                            decision = "AUTHORIZED"; reason = "Scalp 15m + Giro 5m"
                        else:
                            decision = "REJECTED"; reason = "Falta Giro RSI 5m"
                    else:
                         decision = "REJECTED"; reason = "Scalp Contra Tendencia"

            # REGISTRO
            if mode != "":
                self.audit_log.append({
                    'Time': row['datetime'], 'Price': price, 'Signal_Mode': mode, 'Side': side,
                    '4H_Trend': trend_4h, '1H_Stoch': round(stoch_1h, 1), '1H_ADX': round(adx_1h, 1),
                    'Decision': decision, 'Reason': reason, 'idx_in_data': i
                })

            if decision == "AUTHORIZED":
                in_pos = True
                pos = {
                    'time': row['datetime'], 'side': side, 'mode': mode,
                    'entry': price, 'sl': price*0.985, 'tp': price*1.03, # R:R 1:2
                    'status': 'OPEN', 'pnl': 0
                }
                if mode == "SNIPER_FVG": fvg.active = False

    def analisis_forense(self):
        print("\n" + "="*50)
        print("🕵️ ANÁLISIS FORENSE: OPORTUNIDADES PERDIDAS VS GANADAS")
        print("="*50)
        
        if not self.audit_log:
            print("⚠️ No hay registros para auditar.")
            return
            
        df_audit = pd.DataFrame(self.audit_log)
        rejected = df_audit[df_audit['Decision'] == 'REJECTED']
        
        print(f"Total Señales: {len(df_audit)}")
        print(f"Ejecutadas:    {len(df_audit[df_audit['Decision']=='AUTHORIZED'])}")
        print(f"Rechazadas:    {len(rejected)}")
        
        print("\n🚫 Top Razones de Rechazo:")
        print(rejected['Reason'].value_counts().head(5).to_string())
        
        # Guardar CSV
        df_audit.to_csv(self.audit_file, index=False)
        print(f"\n✅ Reporte detallado guardado en: {self.audit_file}")

if __name__ == "__main__":
    bt = BacktesterV4Unified()
    bt.ejecutar()
    bt.analisis_forense()