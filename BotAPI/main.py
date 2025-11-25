# main.py
import time
import logging
import traceback
from colorama import init, Fore
from config import Config
from connectors import BinanceClient, MockClient
from indicators import MarketAnalyzer
from strategies import StrategyEngine
import dashboard

init(autoreset=True)

def main():
    cfg = Config()
    logging.basicConfig(filename=cfg.LOG_FILE, level=logging.INFO)
    print(f"{Fore.CYAN}Iniciando SENTINEL PRO (Modo: {cfg.MODE})...{Fore.RESET}")
    
    client = MockClient(cfg) if cfg.MODE == 'SIMULATION' else BinanceClient(cfg)
    client.inicializar()
    strategy = StrategyEngine(cfg, client)
    
    print("Sincronizando Timeframes...")
    time.sleep(2)

    try:
        while True:
            # Ciclo de 1 segundo para Momentum
            time.sleep(1) 

            df_scalp = client.obtener_velas(cfg.TF_SCALP)
            df_swing = client.obtener_velas(cfg.TF_SWING)
            
            if df_scalp.empty or df_swing.empty: continue

            precio = client.obtener_precio_real()
            
            # Validación crítica de precio
            if not precio: 
                continue 

            # Inyección de precio real
            df_scalp.iloc[-1, df_scalp.columns.get_loc('close')] = precio
            df_scalp.iloc[-1, df_scalp.columns.get_loc('high')] = max(df_scalp.iloc[-1]['high'], precio)
            df_scalp.iloc[-1, df_scalp.columns.get_loc('low')] = min(df_scalp.iloc[-1]['low'], precio)
            df_swing.iloc[-1, df_swing.columns.get_loc('close')] = precio

            # Indicadores
            ana_s = MarketAnalyzer(df_scalp); df_s = ana_s.calcular_todo(cfg.SCALP_RSI_PERIOD)
            ana_w = MarketAnalyzer(df_swing); df_w = ana_w.calcular_todo(cfg.SWING_RSI_PERIOD)
            rmin, rmax = ana_s.obtener_extremos_locales()

            # Ejecución Estrategia
            msg = strategy.ejecutar_estrategia(df_s, df_w, rmin, rmax, precio)
            
            # --- CORRECCIÓN AQUÍ ---
            # 1. Volumetría solo para Scalp
            vol = strategy.scalp_mode.analizar_volumetria(df_s)
            
            # 2. Datos Momentum (Solo obtenemos el cambio %, el ratio ya no aplica en segundos)
            mom_chg = strategy.mom_mode.obtener_datos_tiempo_real()
            mom_ratio = 0.0 # Valor placeholder para el dashboard
            
            ordenes_reales = client.obtener_ordenes_abiertas() if cfg.MODE != 'SIMULATION' else []

            dashboard.mostrar_panel(
                df_s, df_w, vol, msg, cfg.MODE, 
                strategy.trader.posicion_abierta,
                ordenes_reales, 
                mom_ratio, mom_chg
            )

    except KeyboardInterrupt:
        print(strategy.trader.stats.obtener_reporte_forense())
    except Exception as e:
        logging.error(traceback.format_exc())
        print(f"\nERROR: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()