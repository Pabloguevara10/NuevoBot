import time
import sys
from datetime import datetime
from colorama import init, Fore, Style
import pandas as pd

# Módulos del Sistema
import config
import connectors
import dashboard
import indicators
from engine import StrategyEngine
from telemetry import DataLogger
from commander import TelegramCommander 

init(autoreset=True)

def main():
    cfg = config.Config()
    
    print(f"{Fore.CYAN}╔════════════════════════════════════════════════════════════════╗")
    print(f"║      SENTINEL AI - V4.0 (STRICT ORDER & SMART DATA)            ║")
    print(f"╚════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    
    client = connectors.BinanceClient(cfg)
    if cfg.MODE == 'SIMULATION':
        client = connectors.MockClient(cfg)
    else:
        client.inicializar()

    try:
        strategy = StrategyEngine(cfg, client)
        logger = DataLogger(cfg)
        print(f"{Fore.MAGENTA}📡 Iniciando sistema de control remoto...{Style.RESET_ALL}")
        bot_telegram = TelegramCommander(cfg, strategy)
        bot_telegram.iniciar()
    except Exception as e:
        print(f"{Fore.RED}Error de inicio: {e}{Style.RESET_ALL}")
        sys.exit(1)

    # --- CARGA INICIAL DE DATOS (PESADA - SOLO UNA VEZ) ---
    print(f"{Fore.YELLOW}🔥 Descargando base de datos histórica...{Style.RESET_ALL}")
    df_scalp = client.obtener_velas(cfg.TF_SCALP, limit=1000) # 15m
    df_swing = client.obtener_velas(cfg.TF_SWING, limit=1000) # 1h
    # 1m siempre necesitamos historial reciente para momentum
    df_mom = client.obtener_velas(cfg.TF_MOMENTUM, limit=1000) 
    
    print(f"{Fore.GREEN}✅ SISTEMA SINCRONIZADO.{Style.RESET_ALL}")
    time.sleep(1)

    analyzer = indicators.MTFAnalyzer(pd.DataFrame(), pd.DataFrame())
    bot_start_time = datetime.now()
    
    # TEMPORIZADORES DE ACTUALIZACIÓN
    last_update_15m = time.time()
    last_update_1h = time.time()
    
    while True:
        try:
            # 1. PRECIO REAL (CRÍTICO - SIEMPRE FRESCO)
            precio_actual = client.obtener_precio_real()
            if precio_actual is None: continue

            # 2. GESTIÓN DE VELAS (LÓGICA INTELIGENTE)
            now = time.time()
            
            # A. Velas de 1 Minuto (Siempre descargamos las ultimas 3 para precisión de momentum)
            df_mom = client.obtener_velas(cfg.TF_MOMENTUM, limit=50) # Ligero
            
            # B. Velas de 15 Minutos (Descargar solo cada 60s)
            if now - last_update_15m > 60: 
                df_scalp = client.obtener_velas(cfg.TF_SCALP, limit=100) # Refresco
                last_update_15m = now
            else:
                # TRUCO MATEMÁTICO: Actualizamos la última vela localmente
                if not df_scalp.empty:
                    df_scalp.iloc[-1, df_scalp.columns.get_loc('close')] = precio_actual
            
            # C. Velas de 1 Hora (Descargar solo cada 5 min)
            if now - last_update_1h > 300:
                df_swing = client.obtener_velas(cfg.TF_SWING, limit=100)
                last_update_1h = now
            else:
                if not df_swing.empty:
                    df_swing.iloc[-1, df_swing.columns.get_loc('close')] = precio_actual

            # 3. CALCULO DE INDICADORES
            analyzer = indicators.MTFAnalyzer(df_mom, df_scalp) 
            mtf_data = analyzer.generar_matriz()
            
            # Inyección final de precio para dashboard
            for tf in mtf_data: mtf_data[tf]['CLOSE'] = precio_actual 

            # 4. CEREBRO Y ESTRATEGIA
            mensaje_decision = strategy.ejecutar_estrategia(mtf_data, precio_actual)
            
            # 5. TELEMETRÍA
            posicion = strategy.trader.posicion_abierta
            ordenes = client.obtener_ordenes_abiertas()
            mom_speed = strategy.mom_mode.obtener_datos_tiempo_real()
            
            # Guardar CSV cada 5 segundos para no quemar disco
            if int(now) % 5 == 0:
                logger.registrar_telemetria(precio_actual, mtf_data, mensaje_decision, posicion, mom_speed)

            # 6. VISUALIZACIÓN
            notas = strategy.trader.obtener_notificaciones_activas()
            pendientes = strategy.pending_mgr.orders

            dashboard.mostrar_panel(
                df_scalp, df_swing, 
                mtf_data.get('1m', {}).get('VOL_SCORE', 0), 
                mensaje_decision, cfg.MODE, posicion, ordenes, 0, 0, 
                mtf_data=mtf_data, start_time=bot_start_time,
                total_trades=strategy.trader.stats.total_trades,
                notificaciones=notas,
                pnl_acumulado=strategy.trader.stats.gross_profit - strategy.trader.stats.gross_loss,
                triggers_activos=strategy.active_triggers,
                ordenes_pendientes_op=pendientes
            )

            time.sleep(0.5) # Ciclo rápido

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}🛑 DETENIENDO BOT...{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"\n{Fore.RED}CRASH: {e}{Style.RESET_ALL}")
            time.sleep(2)

if __name__ == "__main__":
    main()