import pandas as pd
import numpy as np
import os
import sys
import time
from datetime import datetime

# -------------------------------------------------------------------------
# IMPORTACIÓN CORRECTA DE CONFIGURACIÓN DEL PROYECTO
# -------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.append(project_root)

from config.config import Config

class FVGTracker:
    """Clase para gestionar el ciclo de vida de un FVG individual."""
    def __init__(self, data):
        self.data = data
        self.top = float(data['Top'])
        self.bottom = float(data['Bottom'])
        self.type = data['Type']
        self.state = 'WAITING' # WAITING -> TOUCHED -> VALIDATED -> RETEST -> USED
        self.last_interaction_time = None

    def update(self, price, time):
        in_zone = self.bottom <= price <= self.top
        
        if self.state == 'WAITING':
            if in_zone:
                self.state = 'TOUCHED'
                self.last_interaction_time = time
                
        elif self.state == 'TOUCHED':
            umbral_validacion = 0.002 # 0.2% rebote
            if self.type == 'LONG' and price > self.top * (1 + umbral_validacion):
                self.state = 'VALIDATED'
            elif self.type == 'SHORT' and price < self.bottom * (1 - umbral_validacion):
                self.state = 'VALIDATED'
                
        elif self.state == 'VALIDATED':
            if in_zone:
                self.state = 'RETEST_READY' # Gatillo listo
                return True
        
        return False

class BacktesterV3:
    """
    SENTINEL BACKTESTER V3 PRO (FVG + Estructura + Filtros)
    """
    def __init__(self):
        print("🚀 INICIANDO BACKTESTER V3 (Estrategia FVG Retest + Filtros)...")
        self.cfg = Config()
        self.data_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'data_lab')
        self.fvg_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'bitacoras', 'fvg_registry.csv')
        
        # Capital
        self.initial_capital = 1000.0
        self.current_capital = self.initial_capital
        
        # Stats
        self.stats = {
            'total_signals': 0,
            'authorized': 0,
            'rejected': {'4H_Trend': 0, '1H_Stoch': 0},
            'trades': [],
            'be_activated': 0,
            'be_near_miss': 0
        }
        
        # Config
        self.WALLET_PCT = 0.15 
        self.LEVERAGE = 5
        self.BE_TRIGGER = 0.008 
        self.BE_NEAR_THRESHOLD = 0.005 
        self.SL_PCT = 0.02 
        
        self.active_fvgs = []

    def load_data(self):
        print(f"📂 Cargando datos...")
        # Cargar 1m base
        path = os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_1m.csv")
        if not os.path.exists(path): return None
        df_1m = pd.read_csv(path)
        df_1m.columns = df_1m.columns.str.strip()
        
        # Parseo
        if 'ts' in df_1m.columns: df_1m['datetime'] = pd.to_datetime(df_1m['ts'], unit='ms')
        elif 'timestamp' in df_1m.columns: df_1m['datetime'] = pd.to_datetime(df_1m['timestamp'])
        df_1m = df_1m.sort_values('datetime').reset_index(drop=True)
        
        # Cargar Filtros MTF (4H y 1H)
        # Hacemos un merge simple para tener el contexto en cada vela de 1m
        path_4h = os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_4h.csv")
        path_1h = os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_1h.csv")
        
        df_4h = pd.read_csv(path_4h) if os.path.exists(path_4h) else pd.DataFrame()
        df_1h = pd.read_csv(path_1h) if os.path.exists(path_1h) else pd.DataFrame()
        
        # Calculamos indicadores macro si faltan
        if not df_4h.empty:
            df_4h['EMA_200'] = df_4h['close'].ewm(span=200, adjust=False).mean()
            if 'ts' in df_4h.columns: df_4h['datetime'] = pd.to_datetime(df_4h['ts'], unit='ms')
            df_4h = df_4h.set_index('datetime').add_prefix('4h_')
            
        if not df_1h.empty:
            # StochRSI
            delta = df_1h['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            min_rsi = rsi.rolling(14).min()
            max_rsi = rsi.rolling(14).max()
            df_1h['STOCH_RSI'] = (rsi - min_rsi) / (max_rsi - min_rsi).replace(0,1) * 100
            
            if 'ts' in df_1h.columns: df_1h['datetime'] = pd.to_datetime(df_1h['ts'], unit='ms')
            df_1h = df_1h.set_index('datetime').add_prefix('1h_')

        # Merge final
        df_final = pd.merge_asof(df_1m, df_1h, on='datetime', direction='backward')
        df_final = pd.merge_asof(df_final, df_4h, on='datetime', direction='backward')
        
        return df_final

    def cargar_fvgs(self):
        if os.path.exists(self.fvg_path):
            raw_fvgs = pd.read_csv(self.fvg_path).to_dict('records')
            self.active_fvgs = [FVGTracker(f) for f in raw_fvgs]
            print(f"✅ {len(self.active_fvgs)} Zonas FVG cargadas.")
        else:
            print("⚠️ Sin archivo FVG. (No habrá entradas)")

    def ejecutar_simulacion(self):
        df = self.load_data()
        self.cargar_fvgs()
        
        if df is None or not self.active_fvgs: return

        print(f"⚡ Ejecutando Motor sobre {len(df)} velas...")
        
        in_position = False
        position = {}
        records = df.to_dict('records')
        
        for i, row in enumerate(records):
            if i < 50: continue
            
            # 1. GESTIÓN POSICIÓN
            if in_position:
                self._gestionar_salida(row, position)
                if position['status'] == 'CLOSED':
                    self.current_capital += position['pnl_realized']
                    self.stats['trades'].append(position.copy())
                    in_position = False
                continue

            # 2. SCANNER DE ZONAS + MAQUINA DE ESTADOS
            price = row['close']
            signal_side = None
            fvg_trigger = None
            
            for fvg in self.active_fvgs:
                is_retest = fvg.update(price, row['datetime'])
                
                if is_retest:
                    # 3. FILTROS DE CONTEXTO (Brain Logic)
                    # Filtro 4H Trend
                    ema_4h = row.get('4h_EMA_200')
                    if pd.notna(ema_4h):
                        is_bullish = price > ema_4h
                        if fvg.type == 'LONG' and not is_bullish:
                            self.stats['rejected']['4H_Trend'] += 1
                            continue
                        if fvg.type == 'SHORT' and is_bullish:
                            self.stats['rejected']['4H_Trend'] += 1
                            continue
                    
                    # Filtro 1H Momento
                    stoch_1h = row.get('1h_STOCH_RSI')
                    if pd.notna(stoch_1h):
                        if fvg.type == 'LONG' and stoch_1h > 80:
                            self.stats['rejected']['1H_Stoch'] += 1
                            continue
                        if fvg.type == 'SHORT' and stoch_1h < 20:
                            self.stats['rejected']['1H_Stoch'] += 1
                            continue

                    # Si pasa filtros, buscamos confirmación de vela (simple)
                    # En simulación asumimos que el retesteo es la confirmación
                    signal_side = fvg.type
                    fvg_trigger = fvg
                    break
            
            if not signal_side: continue
            
            # ¡AUTORIZADO!
            self.stats['authorized'] += 1
            fvg_trigger.state = 'USED'
            
            margin = self.current_capital * self.WALLET_PCT
            qty = (margin * self.LEVERAGE) / price
            
            # TP Estructural (Simplificado a 3% para prueba FVG)
            tp_price = price * (1.03 if signal_side == 'LONG' else 0.97)
            sl_price = price * (0.98 if signal_side == 'LONG' else 1.02)
            
            in_position = True
            position = {
                'entry_time': row['datetime'],
                'side': signal_side,
                'entry_price': price,
                'qty': qty,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'be_active': False,
                'max_pnl': -0.01,
                'status': 'OPEN',
                'pnl_realized': 0.0
            }

    def _gestionar_salida(self, row, pos):
        curr = row['close']
        entry = pos['entry_price']
        side = pos['side']
        qty = pos['qty']
        
        pnl_pct = (curr - entry)/entry if side=='LONG' else (entry - curr)/entry
        if pnl_pct > pos['max_pnl']: pos['max_pnl'] = pnl_pct
        
        if not pos['be_active'] and pnl_pct >= self.BE_TRIGGER:
            pos['be_active'] = True
            self.stats['be_activated'] += 1
            
        sl_limit = entry if pos['be_active'] else pos['sl_price']
        hit_sl = (side=='LONG' and curr<=sl_limit) or (side=='SHORT' and curr>=sl_limit)
        
        if hit_sl:
            pos['status'] = 'CLOSED'
            if pos['be_active']:
                pos['pnl_realized'] = 0
            else:
                loss = qty * abs(entry - sl_limit) * -1
                pos['pnl_realized'] = loss
                if pos['max_pnl'] > self.BE_NEAR_THRESHOLD:
                    self.stats['be_near_miss'] += 1
            return

        hit_tp = (side=='LONG' and curr>=pos['tp_price']) or (side=='SHORT' and curr<=pos['tp_price'])
        if hit_tp:
            pos['status'] = 'CLOSED'
            gain = qty * abs(entry - pos['tp_price'])
            pos['pnl_realized'] = gain

    def reporte(self):
        print("\n" + "="*50)
        print("📊 REPORTE: ESTRATEGIA FVG (RETEST + FILTROS)")
        print("="*50)
        
        trades = self.stats['trades']
        if not trades:
            print("⚠️ No hubo entradas (Revisa si hay FVGs cargados).")
            return
            
        wins = len([t for t in trades if t['pnl_realized'] > 0])
        losses = len([t for t in trades if t['pnl_realized'] < 0])
        
        print(f"Capital Inicial: {self.initial_capital} USDT")
        print(f"Capital Final:   {self.current_capital:.2f} USDT")
        print(f"Retorno Neto:    {(self.current_capital-self.initial_capital)/self.initial_capital*100:.2f}%")
        print("-" * 30)
        print(f"Total Ops:       {len(trades)}")
        print(f"Ganadoras:       {wins}")
        print(f"Perdedoras:      {losses}")
        print(f"Filtradas:       {self.stats['total_signals'] - self.stats['authorized']}")
        print(f"Breakevens:      {self.stats['be_activated']}")

if __name__ == "__main__":
    bt = BacktesterV3()
    bt.ejecutar_simulacion()
    bt.reporte()