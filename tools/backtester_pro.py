print("--- CARGANDO SCRIPT... ---") # DEBUG INICIAL

import pandas as pd
import numpy as np
import os
import sys
import uuid
from datetime import datetime

# Ajuste de rutas para encontrar config y logs
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class BacktesterPro:
    def __init__(self):
        print("🚀 INICIANDO BACKTESTER PRO (Motor de Alta Velocidad)...")
        # Rutas relativas asumiendo ejecución desde la raíz o tools
        # Ajustamos para buscar siempre en la raiz del proyecto
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = os.path.join(base_dir, 'logs', 'data_lab')
        self.fvg_path = os.path.join(base_dir, 'logs', 'bitacoras', 'fvg_registry.csv')
        self.output_path = os.path.join(base_dir, 'logs')
        
        self.datasets = {}
        self.fvgs = []
        
        # --- CONFIGURACIÓN DE ESTRATEGIA ---
        self.balance = 1000.0
        self.leverage = 5
        self.SL_PCT = 0.02
        self.TP_FIXED = [0.015, 0.030, 0.060]
        self.TP_SPLIT = [0.30, 0.30, 0.40]
        self.DCA_TRIGGER = 0.70
        
        # Estado
        self.positions = []
        self.history = []
        self.slot_strategic = False 
        self.slot_tactical = False  

    def cargar_datos(self):
        print(f"📂 Buscando datos en: {self.data_path}")
        tfs = ['1m', '5m', '15m', '1h', '4h']
        
        # 1. Cargar Históricos
        for tf in tfs:
            try:
                # Buscar archivos que contengan el timeframe (ej. history_AAVEUSDT_1m.csv)
                if not os.path.exists(self.data_path):
                    print(f"❌ Error: No existe la carpeta {self.data_path}")
                    return

                files = [f for f in os.listdir(self.data_path) if f.endswith(f"_{tf}.csv")]
                if not files:
                    print(f"⚠️ No se encontró data para {tf}. (Saltando)")
                    continue
                
                path = os.path.join(self.data_path, files[0])
                df = pd.read_csv(path)
                
                # Estandarizar fechas
                if 'ts' in df.columns: df['ts'] = pd.to_datetime(df['ts'], unit='ms')
                elif 'datetime' in df.columns: df['ts'] = pd.to_datetime(df['datetime'])
                
                self.datasets[tf] = df.sort_values('ts').reset_index(drop=True)
                print(f"   -> Cargado {tf}: {len(df)} velas.")
                
            except Exception as e:
                print(f"❌ Error cargando {tf}: {e}")

        # 2. Cargar FVGs
        if os.path.exists(self.fvg_path):
            self.fvgs = pd.read_csv(self.fvg_path).to_dict('records')
            print(f"   -> Cargados {len(self.fvgs)} FVGs para análisis.")
        else:
            print("⚠️ No hay registro de FVG (fvg_registry.csv). Se omitirá estrategia Sniper.")

    def run(self):
        if '1m' not in self.datasets:
            print("❌ Error Fatal: No hay data de 1m para iterar. Ejecuta data_miner.py primero.")
            return

        df_sim = self.datasets['1m']
        print(f"⚡ Ejecutando simulación sobre {len(df_sim)} velas de 1m...")
        
        for index, row in df_sim.iterrows():
            # 1. Gestión de Posiciones (Contralor Virtual)
            self._gestionar_posiciones(row)
            
            # 2. Detección de Entradas (Cerebro Virtual)
            if not self.slot_strategic or not self.slot_tactical:
                signal, mode, sl_ref = self._check_entry(row)
                if signal:
                    self._abrir_posicion(row, signal, mode, sl_ref)
        
        print("🏁 Simulación terminada.")
        self._generar_reporte_excel()

    def _check_entry(self, row):
        # A. FVG (Estratégico)
        if not self.slot_strategic:
            for fvg in self.fvgs:
                if fvg['Type'] == 'LONG':
                    if fvg['Bottom'] <= row['low'] <= fvg['Top']:
                        if row.get('STOCH_K', 50) < 30:
                            return 'LONG', 'SNIPER_FVG', fvg['Bottom']
                elif fvg['Type'] == 'SHORT':
                    if fvg['Top'] >= row['high'] >= fvg['Bottom']:
                        if row.get('STOCH_K', 50) > 70:
                            return 'SHORT', 'SNIPER_FVG', fvg['Top']

        # B. Táctico (Trend/Scalp)
        if not self.slot_tactical:
            adx = row.get('ADX', 0)
            rsi = row.get('RSI', 50)
            market_mode = "TREND" if adx > 25 else "SCALP_BB"
            
            if market_mode == "SCALP_BB":
                if rsi < 30 and row['close'] < row.get('BB_LO', 0):
                    return 'LONG', 'SCALP_BB', None
                elif rsi > 70 and row['close'] > row.get('BB_UP', 0):
                    return 'SHORT', 'SCALP_BB', None
                    
            elif market_mode == "TREND":
                is_bullish = row['close'] > row.get('EMA_200', 0)
                if is_bullish and rsi < 45:
                    return 'LONG', 'TREND', None
                elif not is_bullish and rsi > 55:
                    return 'SHORT', 'TREND', None
        
        return None, None, None

    def _abrir_posicion(self, row, side, mode, sl_ref):
        if mode == 'SNIPER_FVG':
            allocation = 0.15
            self.slot_strategic = True
        else:
            allocation = 0.05
            self.slot_tactical = True
            
        margin = self.balance * allocation
        size = margin * self.leverage
        entry_price = row['close']
        qty = size / entry_price
        
        # SL
        if sl_ref:
            sl_price = sl_ref * 0.998 if side == 'LONG' else sl_ref * 1.002
        else:
            sl_dist = entry_price * self.SL_PCT
            sl_price = (entry_price - sl_dist) if side == 'LONG' else (entry_price + sl_dist)

        pos = {
            'id': str(uuid.uuid4())[:8],
            'time': row['ts'],
            'side': side,
            'mode': mode,
            'entry': entry_price,
            'qty': qty,
            'sl': sl_price,
            'tp_level': 0,
            'status': 'OPEN',
            'pnl_realized': 0.0,
            'dca_applied': False
        }
        self.positions.append(pos)

    def _gestionar_posiciones(self, row):
        active = [p for p in self.positions if p['status'] == 'OPEN']
        
        for pos in active:
            # 1. Verificar Stop Loss
            hit_sl = False
            if pos['side'] == 'LONG':
                if row['low'] <= pos['sl']: hit_sl = True
            else:
                if row['high'] >= pos['sl']: hit_sl = True
            
            if hit_sl:
                self._cerrar_posicion(pos, 'SL', pos['sl'])
                continue

            # 2. Verificar DCA
            if not pos['dca_applied']:
                curr_price = row['close']
                dist_sl = abs(pos['entry'] - pos['sl'])
                curr_dist = abs(pos['entry'] - curr_price)
                
                is_losing = (pos['side'] == 'LONG' and curr_price < pos['entry']) or \
                            (pos['side'] == 'SHORT' and curr_price > pos['entry'])
                
                if is_losing and dist_sl > 0 and (curr_dist / dist_sl) > self.DCA_TRIGGER:
                    pos['dca_applied'] = True
                    pos['entry'] = (pos['entry'] + curr_price) / 2
                    pos['qty'] *= 2

            # 3. Verificar Take Profit
            tp_prices = []
            if pos['side'] == 'LONG':
                tp_prices = [pos['entry'] * (1 + p) for p in self.TP_FIXED]
            else:
                tp_prices = [pos['entry'] * (1 - p) for p in self.TP_FIXED]
            
            for i, tp in enumerate(tp_prices):
                if i < pos['tp_level']: continue
                
                hit_tp = False
                if pos['side'] == 'LONG' and row['high'] >= tp: hit_tp = True
                if pos['side'] == 'SHORT' and row['low'] <= tp: hit_tp = True
                
                if hit_tp:
                    qty_close = pos['qty'] * self.TP_SPLIT[i] if i < 2 else pos['qty']
                    price_close = tp
                    
                    pnl = (price_close - pos['entry']) * qty_close if pos['side'] == 'LONG' else (pos['entry'] - price_close) * qty_close
                    pos['pnl_realized'] += pnl
                    pos['qty'] -= qty_close
                    pos['tp_level'] += 1
                    
                    if i == 0: pos['sl'] = pos['entry'] # Move to BE
                    if i == 2: self._cerrar_posicion(pos, 'TP3', price_close)

    def _cerrar_posicion(self, pos, reason, price):
        remaining = pos['qty']
        if remaining > 0:
            pnl = (price - pos['entry']) * remaining if pos['side'] == 'LONG' else (pos['entry'] - price) * remaining
            pos['pnl_realized'] += pnl
        
        pos['status'] = 'CLOSED'
        self.history.append({
            'Fecha': pos['time'],
            'Tipo': pos['side'],
            'Modo': pos['mode'],
            'Precio Entrada': pos['entry'],
            'Precio Salida': price,
            'Resultado': 'GANADORA' if pos['pnl_realized'] > 0 else 'PERDEDORA',
            'PnL (USDT)': round(pos['pnl_realized'], 2),
            'Motivo': reason
        })
        
        if pos['mode'] == 'SNIPER_FVG': self.slot_strategic = False
        else: self.slot_tactical = False

    def _generar_reporte_excel(self):
        if not self.history:
            print("⚠️ No hubo operaciones para reportar.")
            return

        print("📊 Enriqueciendo datos con indicadores Multi-Timeframe...")
        enriched_data = []
        
        for trade in self.history:
            entry_time = trade['Fecha']
            row = trade.copy()
            
            for tf in ['5m', '15m', '1h', '4h']:
                if tf not in self.datasets: continue
                df = self.datasets[tf]
                
                mask = df['ts'] <= entry_time
                if mask.any():
                    metrics = df.loc[mask].iloc[-1]
                    row[f'{tf}_RSI'] = round(metrics.get('RSI', 0), 1)
                    row[f'{tf}_Stoch'] = round(metrics.get('STOCH_K', 0), 1)
                    row[f'{tf}_ADX'] = round(metrics.get('ADX', 0), 1)
                    try:
                        bbw = round(metrics.get('BB_UP', 0) - metrics.get('BB_LO', 0), 2)
                    except: bbw = 0
                    row[f'{tf}_BBW'] = bbw
                else:
                    row[f'{tf}_RSI'] = 0
            
            enriched_data.append(row)
            
        df_final = pd.DataFrame(enriched_data)
        
        # Guardar Excel
        filename = f"Backtest_Result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path = os.path.join(self.output_path, filename)
        
        try:
            df_final.to_excel(path, index=False)
            print(f"\n✅ REPORTE GENERADO: {path}")
            
            wins = len(df_final[df_final['PnL (USDT)'] > 0])
            total = len(df_final)
            print(f"   Total Ops: {total}")
            print(f"   Win Rate: {(wins/total)*100:.1f}%")
            print(f"   PnL Neto: {df_final['PnL (USDT)'].sum():.2f} USDT")
        except ImportError:
            print("\n❌ Error: Necesitas instalar 'openpyxl' para guardar Excel.")
            print("   Ejecuta: pip install openpyxl")
            # Fallback a CSV
            csv_path = path.replace('.xlsx', '.csv')
            df_final.to_csv(csv_path, index=False)
            print(f"   (Se guardó como CSV en su lugar: {csv_path})")

if __name__ == "__main__":
    bt = BacktesterPro()
    bt.cargar_datos()
    bt.run()