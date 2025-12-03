import sys
import os
import pandas as pd
import time
from datetime import datetime

# Configuración de rutas para importar módulos del core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.config import Config
from logic.brain import Brain
from logic.shooter import Shooter

# --- CLASES MOCK (SIMULADORES) ---
class MockFinancials:
    def __init__(self, initial_balance=1000.0):
        self.balance = initial_balance
    
    def obtener_capital_total(self):
        return self.balance
    
    def puedo_operar(self):
        return True, "OK"
    
    def registrar_pnl(self, pnl):
        self.balance += pnl

class MockOrderManager:
    def __init__(self, financials):
        self.fin = financials
        self.history = []
        self.active_trades = []
        self.current_market_price = 0.0 # Variable para rastrear precio actual
    
    def ejecutar_estrategia(self, plan):
        """Simula la ejecución de una orden."""
        plan['status'] = 'OPEN'
        plan['entry_time'] = plan.get('timestamp', time.time())
        
        # CORRECCIÓN CRÍTICA: Asignar precio de entrada simulado
        # En el bot real, esto viene de la respuesta de Binance.
        # Aquí, usamos el precio actual de la vela que estamos iterando.
        plan['entry_price'] = self.current_market_price
        
        self.active_trades.append(plan)
        return True, plan

    def actualizar_posiciones(self, current_price, current_ts):
        """Revisa si toca SL o TP."""
        self.current_market_price = current_price # Actualizar referencia interna
        
        for trade in list(self.active_trades):
            side = trade['side']
            entry = trade['entry_price'] # Ahora sí existe esta clave
            qty = trade['qty']
            sl = trade['sl_price'] 
            tps = trade.get('tps', [])
            
            # 1. Verificar Stop Loss
            hit_sl = (side == 'LONG' and current_price <= sl) or \
                     (side == 'SHORT' and current_price >= sl)
            
            if hit_sl:
                pnl = (sl - entry) * qty if side == 'LONG' else (entry - sl) * qty
                self._cerrar_trade(trade, sl, pnl, "STOP_LOSS", current_ts)
                continue

            # 2. Verificar Take Profits (Simulación: Cierre al TP1)
            if tps:
                tp1 = tps[0]
                hit_tp = (side == 'LONG' and current_price >= tp1) or \
                         (side == 'SHORT' and current_price <= tp1)
                
                if hit_tp:
                    pnl = (tp1 - entry) * qty if side == 'LONG' else (entry - tp1) * qty
                    self._cerrar_trade(trade, tp1, pnl, "TAKE_PROFIT", current_ts)

    def _cerrar_trade(self, trade, exit_price, pnl, reason, ts):
        self.fin.registrar_pnl(pnl)
        self.history.append({
            'entry_time': datetime.fromtimestamp(trade['entry_time']),
            'exit_time': datetime.fromtimestamp(ts),
            'side': trade['side'],
            'mode': trade['mode'],
            'entry': trade['entry_price'],
            'exit': exit_price,
            'pnl': pnl,
            'reason': reason
        })
        self.active_trades.remove(trade)

class MockComptroller:
    def __init__(self, mock_om):
        self.om = mock_om
    
    @property
    def positions(self):
        pos_dict = {}
        for t in self.om.active_trades:
            pos_dict[t['id']] = {'data': t}
        return pos_dict
        
    def registrar_posicion(self, plan):
        pass 

class MockLogger:
    def log_operational(self, mod, msg): pass
    def log_error(self, mod, msg): 
        # Filtrar errores de "datos insuficientes" que son normales al inicio
        if "Datos insuficientes" not in msg:
            print(f"ERR [{mod}]: {msg}")

# --- MOTOR PRINCIPAL ---

class BacktesterV2:
    def __init__(self):
        print("🚀 INICIANDO BACKTESTER V2 (CORREGIDO)...")
        self.cfg = Config()
        self.log = MockLogger()
        
        self.fin = MockFinancials(initial_balance=1000.0)
        self.om = MockOrderManager(self.fin)
        self.comp = MockComptroller(self.om)
        
        self.shooter = Shooter(self.cfg, self.fin, self.om, self.comp, self.log)
        self.brain = Brain(self.cfg, self.shooter, self.log)
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = os.path.join(base_dir, 'logs', 'data_lab')
        self.datasets = {}

    def cargar_datos(self):
        print("📂 Cargando datasets Multi-Timeframe...")
        tfs = ['1m', '5m', '15m', '1h', '4h', '1d']
        for tf in tfs:
            try:
                # Busca archivo oficial
                target_file = f"history_{self.cfg.SYMBOL}_{tf}.csv"
                target_path = os.path.join(self.data_path, target_file)
                
                if os.path.exists(target_path):
                    df = pd.read_csv(target_path)
                    df.columns = df.columns.str.strip() # Limpieza
                    
                    if 'ts' not in df.columns:
                        print(f"   ❌ Error en {target_file}: Falta columna 'ts'.")
                        continue

                    df['ts_sec'] = df['ts'] / 1000 
                    self.datasets[tf] = df.sort_values('ts').reset_index(drop=True)
                    print(f"   -> {tf}: {len(df)} velas cargadas.")
                else:
                    print(f"   ⚠️ No encontrado: {target_file}")

            except Exception as e:
                print(f"   x Error cargando {tf}: {e}")

    def _construir_mtf_data(self, current_ts_ms):
        mtf_data = {}
        ts_sec = current_ts_ms / 1000
        
        for tf, df in self.datasets.items():
            # Buscar índice sin mirar al futuro
            idx = df['ts_sec'].searchsorted(ts_sec, side='right') - 1
            
            if idx >= 0:
                last_row = df.iloc[idx]
                mtf_data[tf] = last_row.to_dict()
                if 'close' in mtf_data[tf]: mtf_data[tf]['CLOSE'] = mtf_data[tf]['close']
                
        return mtf_data

    def run(self):
        if '1m' not in self.datasets:
            print("❌ Error Fatal: No hay data de 1m para iterar.")
            return

        df_1m = self.datasets['1m']
        print(f"⚡ Ejecutando simulación ({len(df_1m)} velas)...")
        
        total_velas = len(df_1m)
        check_step = max(1, total_velas // 20)

        for row in df_1m.itertuples():
            idx = row.Index
            current_ts = row.ts
            current_price = row.close
            
            # 1. Actualizar Mocks (Y pasar el precio actual al OrderManager)
            # Esto corrige el KeyError 'entry_price'
            self.om.actualizar_posiciones(current_price, current_ts/1000)
            
            # 2. Preparar Datos MTF
            mtf_data = self._construir_mtf_data(current_ts)
            
            # 3. Brain
            self.brain.procesar_mercado(mtf_data, current_price)
            
            if idx % check_step == 0:
                prog = (idx / total_velas) * 100
                sys.stdout.write(f"\r   Progreso: [{prog:.1f}%] Trades: {len(self.om.history)}")
                sys.stdout.flush()

        print("\n\n🏁 Simulación Finalizada.")
        self._reportar()

    def _reportar(self):
        trades = self.om.history
        if not trades:
            print("⚠️ No se realizaron operaciones.")
            print("   Sugerencia: Revisa los parámetros en config.py (RSI, ADX) o si hay data suficiente.")
            return

        df_res = pd.DataFrame(trades)
        wins = len(df_res[df_res['pnl'] > 0])
        total = len(df_res)
        wr = (wins/total) * 100 if total > 0 else 0
        total_pnl = df_res['pnl'].sum()
        
        print("\n📊 REPORTE DE RESULTADOS")
        print("==============================")
        print(f"Total Operaciones: {total}")
        print(f"Win Rate:          {wr:.2f}%")
        print(f"PnL Total:         {total_pnl:.2f} USDT")
        print(f"Balance Final:     {self.fin.balance:.2f} USDT")
        print("==============================")
        
        print("\nÚltimas 5 Operaciones:")
        print(df_res[['entry_time', 'side', 'mode', 'pnl', 'reason']].tail(5).to_string(index=False))
        
        df_res.to_csv("Backtest_V2_Results.csv", index=False)
        print("\n✅ Reporte detallado guardado en 'Backtest_V2_Results.csv'")

if __name__ == "__main__":
    bt = BacktesterV2()
    bt.cargar_datos()
    bt.run()