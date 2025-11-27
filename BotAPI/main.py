# main.py
import time
import logging
import traceback
from colorama import init, Fore, Style
from config import Config
from connectors import BinanceClient, MockClient
from indicators import MarketAnalyzer, MTFAnalyzer
from strategies import StrategyEngine, DataLogger 
import dashboard # <--- LÍNEA RECUPERADA

init(autoreset=True)

def main():
    cfg = Config()
    logging.basicConfig(filename=cfg.LOG_FILE, level=logging.INFO)
    print(f"{Fore.CYAN}Iniciando SENTINEL PRO (Modo: {cfg.MODE})...{Fore.RESET}")
    
    # Selección de cliente
    client = MockClient(cfg) if cfg.MODE == 'SIMULATION' else BinanceClient(cfg)
    client.inicializar()
    strategy = StrategyEngine(cfg, client)
    
    # --- INICIALIZAR LOGGER (TELEMETRÍA) ---
    logger = DataLogger(cfg)
    
    # --- PRE-CARGA HISTORIAL ---
    if cfg.MODE != 'SIMULATION':
        print(f"{Fore.YELLOW}📥 Descargando Historial Profundo (Base de Datos Real)...{Style.RESET_ALL}")
        client.obtener_velas(cfg.TF_SCALP) 
        print(f"   ✅ Base Scalping (1m, 3m, 5m) lista.")
        client.obtener_velas(cfg.TF_SWING)
        print(f"   ✅ Base Swing (15m, 1h, 4h) lista.")
    
    print("Sincronizando Sistema...")
    time.sleep(1)

    try:
        while True:
            time.sleep(0.5) 

            df_scalp = client.obtener_velas(cfg.TF_SCALP)
            df_swing = client.obtener_velas(cfg.TF_SWING)
            
            if df_scalp.empty or df_swing.empty: continue

            precio = client.obtener_precio_real()
            if not precio: continue 

            df_scalp.iloc[-1, df_scalp.columns.get_loc('close')] = precio
            df_scalp.iloc[-1, df_scalp.columns.get_loc('high')] = max(df_scalp.iloc[-1]['high'], precio)
            df_scalp.iloc[-1, df_scalp.columns.get_loc('low')] = min(df_scalp.iloc[-1]['low'], precio)
            df_swing.iloc[-1, df_swing.columns.get_loc('close')] = precio

            mtf = MTFAnalyzer(df_scalp, df_swing)
            mtf_data = mtf.generar_matriz()

            ana_s = MarketAnalyzer(df_scalp); df_s = ana_s.calcular_todo(cfg.SCALP_RSI_PERIOD)
            ana_w = MarketAnalyzer(df_swing); df_w = ana_w.calcular_todo(cfg.SWING_RSI_PERIOD)

            # Ejecución
            msg = strategy.ejecutar_estrategia(mtf_data, precio)
            
            # Datos Aux
            vol_score = mtf_data.get('1m', {}).get('VOL_SCORE', 0)
            mom_chg = strategy.mom_mode.obtener_datos_tiempo_real()
            ordenes_reales = client.obtener_ordenes_abiertas() if cfg.MODE != 'SIMULATION' else []

            # --- REGISTRAR TELEMETRÍA ---
            logger.registrar_telemetria(
                precio, 
                mtf_data, 
                msg, 
                strategy.trader.posicion_abierta, 
                mom_chg
            )

            dashboard.mostrar_panel(
                df_s, df_w, vol_score, msg, cfg.MODE, 
                strategy.trader.posicion_abierta,
                ordenes_reales, 
                0.0, mom_chg,
                mtf_data=mtf_data 
            )

    except KeyboardInterrupt:
        print(strategy.trader.stats.obtener_reporte_forense())
    except Exception as e:
        logging.error(traceback.format_exc())
        print(f"\nERROR CRÍTICO EN MAIN: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()