# simulation_test.py
import time
import random
import pandas as pd
from colorama import init, Fore, Style
from config import Config
from strategies import StrategyEngine
from connectors import MockClient

init(autoreset=True)

class ChaosGenerator:
    def __init__(self, start_price=100.0):
        self.price = start_price
        self.volatility = 0.0005 
    
    def next_tick(self, scenario):
        noise = random.uniform(-self.volatility, self.volatility)
        
        if scenario == 'MOMENTUM_ZONE':
            self.volatility = 0.0005; change = noise # Volatilidad baja
        elif scenario == 'SCALP_ZONE':
            self.volatility = 0.0015; change = noise + (0.001 if random.random() > 0.5 else -0.001)
        elif scenario == 'SWING_TREND':
            self.volatility = 0.001; change = 0.004 + noise 
            
        self.price = self.price * (1 + change)
        return self.price

# 1. Configuración Simulada
cfg = Config()
cfg.MODE = 'SIMULATION'
cfg.CAPITAL_TRABAJO = 10000
cfg.SWING_RSI_OB = 60 
cfg.SWING_RSI_OS = 40 
cfg.MOMENTUM_MIN_CHANGE = 0.0001 

# 2. Inicialización
print(f"{Fore.CYAN}=== INICIANDO PRUEBA DE ESTRÉS JERÁRQUICO ==={Style.RESET_ALL}")
client = MockClient(cfg) 
client.cfg = cfg  
client.step_size = 0.01 
client.obtener_posicion_abierta = lambda: {} 
client.obtener_ordenes_historicas = lambda x: []
client.obtener_trades_historicos = lambda x: []

bot = StrategyEngine(cfg, client)
# --- FIX CRÍTICO: Eliminamos el Cooldown para la simulación ---
bot.COOLDOWN_SECONDS = 0 

chaos = ChaosGenerator(start_price=2000)

# Mock de DataFrames
cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'RSI', 'OBV', 'VWAP', 'ADI', 'MA99']
df_dummy = pd.DataFrame([{c: 0.0 for c in cols} for _ in range(50)]) 
df_dummy['RSI'] = 50.0 

def correr_fase(nombre, ticks, escenario, override_rsi=50, override_gatillo=None):
    print(f"\n{Fore.YELLOW}--- FASE: {nombre} ---{Style.RESET_ALL}")
    df_dummy['RSI'] = override_rsi
    if override_gatillo: bot.scalp_mode.gatillo = override_gatillo

    for i in range(ticks):
        price = chaos.next_tick(escenario)
        # Inyectamos precio actual al DF
        df_dummy.iloc[-1, df_dummy.columns.get_loc('close')] = price
        df_dummy.iloc[-1, df_dummy.columns.get_loc('high')] = price * 1.001
        df_dummy.iloc[-1, df_dummy.columns.get_loc('low')] = price * 0.999
        
        # Ejecutamos lógica
        status = bot.ejecutar_estrategia(df_dummy, df_dummy, price*0.9, price*1.1, price)
        
        pos = bot.trader.posicion_abierta
        estrat = pos['strategy'] if pos else "NINGUNA"
        color = Fore.GREEN if pos else Fore.WHITE
        
        print(f"Tick {i+1}: Precio {price:.2f} | Acción: {status} | Activa: {color}{estrat}{Style.RESET_ALL}")
        time.sleep(0.05)

# --- EJECUCIÓN ---

# 1. Fase Momentum (Buscamos que entre y se mantenga viva)
correr_fase("1. MOMENTUM PURO", 15, 'MOMENTUM_ZONE')

# 2. Fase Scalp (Debería forzar cierre de Momentum)
# Preparamos un gatillo "fake" armado listo para disparar
gatillo_fake = {'tipo': 'LONG', 'price': chaos.price, 'ticks': 20}
correr_fase("2. IRRUPCIÓN SCALP", 15, 'SCALP_ZONE', override_gatillo=gatillo_fake)

# 3. Fase Swing (Debería matar Scalp o Momentum)
correr_fase("3. DOMINIO SWING (RSI EXTREMO)", 15, 'SWING_TREND', override_rsi=20)

print(bot.trader.stats.obtener_reporte_forense())