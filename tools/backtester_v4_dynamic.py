import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# -------------------------------------------------------------------------
# CONFIGURACIÓN DE ENTORNO
# -------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.append(project_root)

from config.config import Config
from tools.precision_lab import PrecisionLab as Lab

class DynamicFVG:
    def __init__(self, top, bottom, tipo, candle_time):
        self.top = top
        self.bottom = bottom
        self.type = tipo
        self.created_at = candle_time
        self.active = True

class BacktesterV4:
    """
    SENTINEL AUDITOR V4 (Unified Logic + Detailed Reporting)
    Simula la lógica exacta del Brain V3.0 y genera un reporte detallado de cada decisión.
    """
    def __init__(self):
        print("🚀 INICIANDO AUDITORÍA V4 (Lógica Unificada)...")
        self.cfg = Config()
        self.data_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'data_lab')
        self.audit_file = os.path.join(self.cfg.BASE_DIR, 'logs', 'simulation_audit_full.csv')
        
        self.capital = 1000.0
        self.fvgs = []
        self.audit_log = [] 
        self.trades = []

    def cargar_datos(self):
        print("📂 Cargando Datos MTF (1m, 5m, 1h, 4h)...")
        try:
            dfs = {}
            # Cargamos 1m como base
            path_1m = os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_1m.csv")
            if not os.path.exists(path_1m):
                print(f"❌ Falta archivo: {path_1m}")
                return None
                
            df_main = pd.read_csv(path_1m)
            df_main.columns = df_main.columns.str.strip()
            
            # Parseo de fechas
            if 'ts' in df_main.columns: 
                df_main['datetime'] = pd.to_datetime(df_main['ts'], unit='ms')
            elif 'timestamp' in df_main.columns: 
                df_main['datetime'] = pd.to_datetime(df_main['timestamp'])
            elif 'datetime' in df_main.columns: 
                df_main['datetime'] = pd.to_datetime(df_main['datetime'])
            
            df_main.set_index('datetime', inplace=True)
            
            # Resamplear a 5m para indicadores de Trend
            df_5m = df_main.resample('5min').agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}).dropna()
            
            # Calcular EMAs 5m
            df_5m['EMA_7'] = df_5m['close'].ewm(span=7).mean()
            df_5m['EMA_25'] = df_5m['close'].ewm(span=25).mean()
            
            # --- CORRECCIÓN: Cálculo directo de RSI 5m (Eliminada llamada prematura a Lab) ---
            delta = df_5m['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            df_5m['RSI'] = 100 - (100 / (1 + rs))
            
            # Cargar 1h y 4h para Filtros
            path_1h = os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_1h.csv")
            path_4h = os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_4h.csv")
            
            if not os.path.exists(path_1h) or not os.path.exists(path_4h):
                print("❌ Faltan archivos de 1h o 4h. Ejecuta data_miner.")
                return None

            df_1h = pd.read_csv(path_1h)
            df_4h = pd.read_csv(path_4h)
            
            # Parseo y Configuración 1H/4H
            for df in [df_1h, df_4h]:
                df.columns = df.columns.str.strip()
                if 'ts' in df.columns: df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
                elif 'timestamp' in df.columns: df['datetime'] = pd.to_datetime(df['timestamp'])
                elif 'datetime' in df.columns: df['datetime'] = pd.to_datetime(df['datetime'])
                df.set_index('datetime', inplace=True)
            
            # Asegurar indicadores Filtro
            if 'EMA_200' not in df_4h.columns:
                df_4h['EMA_200'] = df_4h['close'].ewm(span=200).mean()
            
            # Stoch 1H
            if 'STOCH_RSI' not in df_1h.columns:
                delta = df_1h['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                min_rsi = rsi.rolling(14).min()
                max_rsi = rsi.rolling(14).max()
                df_1h['STOCH_RSI'] = (rsi - min_rsi) / (max_rsi - min_rsi).replace(0, 1) * 100
            
            # Merge Final
            df_1h = df_1h.add_prefix('1h_')
            df_4h = df_4h.add_prefix('4h_')
            df_5m = df_5m.add_prefix('5m_')
            
            print("   Sincronizando Reloj Maestro...")
            df_final = pd.merge_asof(df_main.sort_index(), df_5m.sort_index(), left_index=True, right_index=True, direction='backward')
            df_final = pd.merge_asof(df_final, df_1h.sort_index(), left_index=True, right_index=True, direction='backward')
            df_final = pd.merge_asof(df_final, df_4h.sort_index(), left_index=True, right_index=True, direction='backward')
            
            return df_final.dropna()

        except Exception as e:
            print(f"❌ Error cargando datos: {e}")
            import traceback
            traceback.print_exc()
            return None

    def detectar_fvg_dinamico(self, row, prev_row, prev2_row):
        # Lógica simplificada de FVG en 1m
        if prev2_row['high'] < row['low']:
            gap = row['low'] - prev2_row['high']
            if gap > (row['close'] * 0.001):
                return DynamicFVG(row['low'], prev2_row['high'], 'LONG', row['datetime'])
        if prev2_row['low'] > row['high']:
            gap = prev2_row['low'] - row['high']
            if gap > (row['close'] * 0.001):
                return DynamicFVG(prev2_row['low'], row['high'], 'SHORT', row['datetime'])
        return None

    def ejecutar(self):
        df = self.cargar_datos()
        if df is None: return

        print(f"⚡ Auditando {len(df)} velas...")
        
        in_pos = False
        pos = {}
        records = df.reset_index().to_dict('records')
        
        for i in range(50, len(records)):
            row = records[i]
            
            # 1. MANTENIMIENTO FVG
            self.fvgs = [f for f in self.fvgs if (row['datetime'] - f.created_at).total_seconds() < 14400]
            new_fvg = self.detectar_fvg_dinamico(row, records[i-1], records[i-2])
            if new_fvg: self.fvgs.append(new_fvg)
            
            # 2. GESTIÓN DE POSICIÓN
            if in_pos:
                self._gestionar_salida(row, pos)
                if pos['status'] == 'CLOSED':
                    self.trades.append(pos)
                    self.capital += pos['pnl']
                    in_pos = False
                continue

            # 3. EVALUACIÓN DE ESTRATEGIAS
            price = row['close']
            
            # Datos de Contexto
            trend_4h = 'ALCISTA' if price > row['4h_EMA_200'] else 'BAJISTA'
            stoch_1h = row.get('1h_STOCH_RSI', 50)
            adx_1h = row.get('1h_ADX', 0)
            
            # --- ESCENARIO A: SNIPER FVG ---
            fvg_signal = None
            for fvg in self.fvgs:
                if fvg.active:
                    en_zona = (fvg.type == 'LONG' and fvg.bottom <= price <= fvg.top) or \
                              (fvg.type == 'SHORT' and fvg.top >= price >= fvg.bottom)
                    if en_zona:
                        fvg_signal = fvg
                        break
            
            # --- ESCENARIO B: TREND FOLLOWING ---
            trend_signal = None
            ema7_5m = row['5m_EMA_7']
            ema25_5m = row['5m_EMA_25']
            diff_ema = ema7_5m - ema25_5m
            
            if diff_ema > 0 and diff_ema < (price*0.001): trend_signal = 'LONG'
            elif diff_ema < 0 and abs(diff_ema) < (price*0.001): trend_signal = 'SHORT'

            # --- DECISIÓN Y REGISTRO ---
            decision = "NONE"
            reason = "No Signal"
            mode = ""
            side = ""
            
            if fvg_signal:
                mode = "SNIPER_FVG"
                side = fvg_signal.type
                
                if (side == 'LONG' and trend_4h == 'BAJISTA') or (side == 'SHORT' and trend_4h == 'ALCISTA'):
                    decision = "REJECTED"
                    reason = "Contra Tendencia 4H"
                elif (side == 'LONG' and stoch_1h > 80) or (side == 'SHORT' and stoch_1h < 20):
                    decision = "REJECTED"
                    reason = "1H Agotado (Stoch)"
                else:
                    rsi_1m = row['RSI'] if 'RSI' in row else 50
                    if (side == 'LONG' and rsi_1m < 40) or (side == 'SHORT' and rsi_1m > 60):
                        decision = "AUTHORIZED"
                        reason = "FVG + Filtros OK + Gatillo OK"
                    else:
                        decision = "REJECTED"
                        reason = "Falta Gatillo RSI 1m"

            elif trend_signal:
                mode = "TREND_FOLLOWING"
                side = trend_signal
                
                if adx_1h < 25:
                    decision = "REJECTED"
                    reason = "ADX 1H Débil"
                elif (side == 'LONG' and trend_4h == 'BAJISTA') or (side == 'SHORT' and trend_4h == 'ALCISTA'):
                    decision = "REJECTED"
                    reason = "Contra Tendencia 4H"
                elif (side == 'LONG' and stoch_1h > 80) or (side == 'SHORT' and stoch_1h < 20):
                    decision = "REJECTED"
                    reason = "1H Agotado (Stoch)"
                else:
                    decision = "AUTHORIZED"
                    reason = "Tendencia + Fuerza + Filtros OK"

            # REGISTRO DE AUDITORÍA
            if mode != "":
                self.audit_log.append({
                    'Time': row['datetime'],
                    'Price': price,
                    'Signal_Mode': mode,
                    'Side': side,
                    '4H_Trend': trend_4h,
                    '1H_Stoch': round(stoch_1h, 1),
                    '1H_ADX': round(adx_1h, 1),
                    '5m_EMA_Diff': round(diff_ema, 2) if trend_signal else 0,
                    'Decision': decision,
                    'Reason': reason
                })

            # EJECUCIÓN
            if decision == "AUTHORIZED":
                in_pos = True
                pos = {
                    'time': row['datetime'],
                    'type': side,
                    'mode': mode,
                    'entry': price,
                    'sl': price * (0.99 if side=='LONG' else 1.01),
                    'tp': price * (1.02 if side=='LONG' else 0.98),
                    'status': 'OPEN',
                    'pnl': 0
                }
                if fvg_signal: fvg_signal.active = False

    def _gestionar_salida(self, row, pos):
        price = row['close']
        if pos['type'] == 'LONG':
            if price <= pos['sl']:
                pos['status'] = 'CLOSED'
                pos['pnl'] = -10
                pos['result'] = 'LOSS'
            elif price >= pos['tp']:
                pos['status'] = 'CLOSED'
                pos['pnl'] = 20
                pos['result'] = 'WIN'
        else:
            if price >= pos['sl']:
                pos['status'] = 'CLOSED'
                pos['pnl'] = -10
                pos['result'] = 'LOSS'
            elif price <= pos['tp']:
                pos['status'] = 'CLOSED'
                pos['pnl'] = 20
                pos['result'] = 'WIN'

    def generar_reporte_auditoria(self):
        print("\n" + "="*50)
        print("📊 GENERANDO REPORTE DE AUDITORÍA DETALLADO...")
        print("="*50)
        
        if not self.audit_log:
            print("⚠️ No se registraron señales para auditar.")
            return

        df_audit = pd.DataFrame(self.audit_log)
        
        # Guardar CSV
        try:
            df_audit.to_csv(self.audit_file, index=False)
            print(f"✅ Reporte guardado en: {self.audit_file}")
            print(f"   Total Eventos Registrados: {len(df_audit)}")
            print("\n   Resumen de Decisiones:")
            print(df_audit['Decision'].value_counts().to_string())
            print("\n   Top 5 Razones de Rechazo:")
            print(df_audit[df_audit['Decision']=='REJECTED']['Reason'].value_counts().head(5).to_string())
        except Exception as e:
            print(f"Error guardando reporte: {e}")

if __name__ == "__main__":
    bt = BacktesterV4()
    bt.ejecutar()
    bt.generar_reporte_auditoria()