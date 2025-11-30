import csv
import pandas as pd
import time
import os
from datetime import datetime
from colorama import init, Fore, Style

# --- IMPORTACIONES ---
import config
from engine import StrategyEngine       
from execution import TradingManager    
from indicators import MTFAnalyzer

init(autoreset=True)

# --- CLASES MOCK (SIMULACIÓN) ---
class MockBacktestClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.step_size = 0.01
        self.orders = []
        self.position = None 
        self.current_price = 0.0
        self.cash = 1000.0 

    def inicializar(self): pass

    def obtener_precio_real(self):
        return self.current_price

    def obtener_posicion_abierta(self):
        if not self.position: return {}
        return {
            'positionAmt': self.position['amt'], 
            'entryPrice': self.position['entry'],
            'notional': abs(self.position['amt'] * self.current_price)
        }

    def obtener_ordenes_abiertas(self):
        return self.orders

    def cancelar_todas_ordenes(self):
        self.orders = []
        return True

    def colocar_orden_market(self, side, qty, pos_side):
        if self.position:
            # Es un cierre (Total o Parcial)
            # Calcular PnL solo sobre la cantidad que se está cerrando (qty)
            
            # Dirección del cierre:
            # Si tengo Long (amt > 0) y vendo -> PnL = (Precio - Entrada) * Qty
            # Si tengo Short (amt < 0) y compro -> PnL = (Entrada - Precio) * Qty
            
            pnl = 0.0
            if self.position['amt'] > 0: # Long
                pnl = (self.current_price - self.position['entry']) * qty
            else: # Short
                pnl = (self.position['entry'] - self.current_price) * qty
            
            self.cash += pnl
            
            # Actualizar tamaño posición
            if qty >= abs(self.position['amt']):
                self.position = None # Cierre Total
            else:
                # Cierre Parcial
                nuevo_amt = abs(self.position['amt']) - qty
                if self.position['amt'] < 0: nuevo_amt *= -1
                self.position['amt'] = nuevo_amt
        else:
            # Apertura Nueva
            amt = qty if side == 'BUY' else -qty
            self.position = {'amt': amt, 'entry': self.current_price}
            
        return {'avgPrice': self.current_price, 'orderId': 12345}

    def colocar_orden_sl_tp(self, side, qty, stop_price, pos_side, tipo):
        self.orders.append({
            'type': tipo, 'side': side, 
            'stopPrice': stop_price, 'origQty': qty, 'positionSide': pos_side
        })
        return {'orderId': 67890}

    def check_triggers(self, current_p):
        if not self.position: return None
        triggered = None
        for order in self.orders[:]:
            trig = float(order['stopPrice'])
            executed = False
            
            if order['type'] == 'STOP_MARKET':
                if self.position['amt'] > 0 and current_p <= trig: executed = True
                if self.position['amt'] < 0 and current_p >= trig: executed = True
            
            elif order['type'] == 'TAKE_PROFIT_MARKET':
                if self.position['amt'] > 0 and current_p >= trig: executed = True
                if self.position['amt'] < 0 and current_p <= trig: executed = True
                
            if executed:
                # Ejecutar cierre simulado
                self.colocar_orden_market(order['side'], order['origQty'], order['positionSide']) 
                triggered = order['type']
                break 
        return triggered

# --- MOTOR DE DATOS ---
def parse_mtf_row(row):
    """Reconstruye datos desde el CSV."""
    def safe_float(val):
        try: return float(val)
        except: return 0.0

    price = safe_float(row['Precio'])
    
    def build_tf_data(suffix):
        try:
            width = safe_float(row[f'BB_Width_{suffix}'])
            pos = row[f'BB_Pos_{suffix}']
            rsi = safe_float(row[f'RSI_{suffix}'])
            stoch = safe_float(row[f'Stoch_{suffix}'])
            vol = safe_float(row.get(f'Vol_{suffix}', 0))
        except KeyError: return {}

        mid = price
        half = width / 2
        upper = mid + half
        lower = mid - half
        
        # Ajuste para replicar estado de bandas
        if pos == 'LOWER': lower = price + 0.01 
        if pos == 'UPPER': upper = price - 0.01 
        
        return {
            'RSI': rsi, 'STOCH_RSI': stoch, 'BB_WIDTH': width, 
            'VOL_SCORE': vol, 'CLOSE': price, 'BB_LOWER': lower, 
            'BB_UPPER': upper, 'BB_MID': mid, 'BB_POS': pos,
            'EMA_200': 0 # Simplificación: Asumimos 0 o pasar si estuviera en CSV
        }

    return {'1m': build_tf_data('1m'), '5m': build_tf_data('5m'), '15m': build_tf_data('15m')}

def run_simulation(file_path):
    print(f"{Fore.CYAN}🚀 INICIANDO SIMULADOR DE ALTA VELOCIDAD{Style.RESET_ALL}")
    print(f"📂 Archivo: {file_path}")
    
    cfg = config.Config()
    cfg.MODE = 'SIMULATION'
    cfg.TRADES_FILE = 'simulacion_resultados.csv'
    
    # --- LIMPIEZA PREVIA (CORRECCIÓN CRÍTICA) ---
    # Borramos el archivo ANTES de iniciar el bot para que él lo cree con encabezados
    if os.path.exists(cfg.TRADES_FILE): 
        os.remove(cfg.TRADES_FILE)
    
    # --- TWEAKS DE PRUEBA ---
    # cfg.MOM_VOL_MIN = 15
    # ------------------------
    
    client = MockBacktestClient(cfg)
    bot = StrategyEngine(cfg, client)

    try:
        df = pd.read_csv(file_path)
        total = len(df)
        print(f"📊 Procesando {total} registros...\n")
        
        start = time.time()
        
        for index, row in df.iterrows():
            try:
                price = float(row['Precio'])
            except: continue

            client.current_price = price
            client.check_triggers(price)
            
            mtf_data = parse_mtf_row(row)
            bot.ejecutar_estrategia(mtf_data, price)
            
            if index % 100 == 0:
                print(f"\rProgreso: {index}/{total} | PnL Simulado: {client.cash - 1000:.2f} USDT", end="")

        dur = time.time() - start
        print(f"\n\n{Fore.GREEN}✅ FINALIZADO en {dur:.2f}s{Style.RESET_ALL}")
        print(f"💰 Balance Final: {client.cash:.2f} USDT")
        
        if os.path.exists(cfg.TRADES_FILE):
            res = pd.read_csv(cfg.TRADES_FILE)
            # Filtramos operaciones cerradas o parciales
            closed = res[res['Estado_Final'].isin(['CLOSED', 'PARTIAL'])]
            
            print(f"\n--- ESTADÍSTICAS ---")
            print(f"Total Eventos: {len(res)}")
            print(f"Cierres/Parciales: {len(closed)}")
            
            if not closed.empty:
                print("\nPnL por Estrategia:")
                print(closed.groupby('Estrategia')['PnL_USDT'].sum())
                
                wins = len(closed[closed['PnL_USDT'] > 0])
                win_rate = (wins / len(closed)) * 100
                print(f"\nWin Rate Global: {win_rate:.2f}%")
        else:
            print("\n⚠️ Sin operaciones registradas.")

    except FileNotFoundError:
        print(f"{Fore.RED}❌ No existe {file_path}.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}❌ Error: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    run_simulation('telemetria_mercado.csv')