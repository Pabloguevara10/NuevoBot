import time
import sys
import os
import pandas as pd  # Necesario para validación de tipos

# Ajuste de path para importaciones absolutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.config import Config
from connections.api_manager import APIManager
from logs.system_logger import SystemLogger
from data.metrics_manager import MetricsManager
from core.financials import Financials
from execution.order_manager import OrderManager
from execution.comptroller import Comptroller
from logic.shooter import Shooter
from logic.brain import Brain
from interfaces.dashboard import Dashboard
from interfaces.telegram_bot import TelegramBot
from tools.data_miner import DataMiner

class BotSupervisor:
    """
    SUPERVISOR DE SALUD
    Monitorea la estabilidad del sistema. Si detecta fallos críticos consecutivos,
    ejecuta apagado de emergencia.
    """
    def __init__(self, order_manager, logger):
        self.om = order_manager
        self.log = logger
        self.error_count = 0
        self.MAX_ERRORS = 5

    def reportar_error(self, e):
        self.error_count += 1
        self.log.log_error("SUPERVISOR", f"Error Crítico #{self.error_count}: {str(e)}")
        
        if self.error_count >= self.MAX_ERRORS:
            self._protocolo_emergencia()

    def reportar_exito(self):
        if self.error_count > 0:
            self.error_count = 0

    def _protocolo_emergencia(self):
        self.log.log_error("SUPERVISOR", "🚨 LÍMITE DE ERRORES ALCANZADO. APAGADO DE EMERGENCIA.")
        print("\n!!! PROTOCOLO DE EMERGENCIA ACTIVADO !!!")
        try:
            self.om.cancelar_todo()
        except: pass
        sys.exit(1)

def _verificar_y_generar_historia(cfg, log):
    """
    Verifica si existen los datos históricos. Si faltan, ejecuta el DataMiner.
    """
    data_path = os.path.join(cfg.BASE_DIR, 'logs', 'data_lab')
    required_files = [
        f"history_{cfg.SYMBOL}_1m.csv",
        f"history_{cfg.SYMBOL}_5m.csv",
        f"history_{cfg.SYMBOL}_15m.csv",
        f"history_{cfg.SYMBOL}_1h.csv",
        f"history_{cfg.SYMBOL}_4h.csv"
    ]
    
    missing = False
    for f in required_files:
        if not os.path.exists(os.path.join(data_path, f)):
            missing = True
            break
            
    if missing:
        print("\n⚠️  ALERTA: No se encontraron métricas históricas.")
        print("⚙️  Iniciando Protocolo de Generación Automática (90 Días)...")
        log.log_operational("SYSTEM", "Iniciando DataMiner por falta de historia.")
        
        try:
            miner = DataMiner()
            raw_data = miner.descargar_historia_masiva(dias=90)
            miner.generar_dataset_maestro(raw_data)
            print("✅ Datos Históricos Generados Exitosamente.\n")
        except Exception as e:
            print(f"❌ Error Crítico en DataMiner: {e}")
            log.log_error("SYSTEM", f"Fallo DataMiner: {e}")
            sys.exit(1)
    else:
        print("✅ Métricas Históricas Detectadas. Sistema listo para operar.")

def main():
    print("Iniciando SENTINEL AI PRO (V2.3 Robustez Total)...")
    
    cfg = Config()
    log = SystemLogger()
    
    # Auto-verificación de datos
    _verificar_y_generar_historia(cfg, log)

    dash = Dashboard()
    conn = APIManager(cfg, log)
    
    metrics_mgr = MetricsManager(cfg, conn)
    financials = Financials(cfg, conn)
    order_mgr = OrderManager(cfg, conn, log)
    comptroller = Comptroller(cfg, order_mgr, financials, log)
    shooter = Shooter(cfg, financials, order_mgr, comptroller, log)
    brain = Brain(cfg, shooter, log)
    supervisor = BotSupervisor(order_mgr, log)

    tele = TelegramBot(cfg, shooter, comptroller, order_mgr, log)
    tele.iniciar()

    last_slow_cycle = 0
    mtf_data = {}
    daily_stats = {}
    session_stats = {'wins': 0, 'losses': 0, 'total_ops': 0}

    dash.add_log("Sistema Online. Arquitectura Blindada V2.3.")
    log.log_operational("MAIN", "Sistema Iniciado correctamente.")

    # ==================================================================
    # MAIN LOOP
    # ==================================================================
    while True:
        try:
            start_time = time.time()
            
            # A. DATOS CRÍTICOS
            price = conn.get_real_price()
            if price is None:
                supervisor.reportar_error("Fallo obteniendo precio real.")
                time.sleep(cfg.REQUEST_TIMEOUT)
                continue

            con_status = conn.check_heartbeat()

            # B. CICLO LENTO (Sincronización)
            if start_time - last_slow_cycle > cfg.SYNC_CYCLE_SLOW:
                dash.add_log("Sincronizando...", "DEBUG")
                mtf_data, daily_stats = metrics_mgr.sincronizar_y_calcular()
                comptroller.sincronizar_estado_externo()
                last_slow_cycle = start_time

            # C. CICLO RÁPIDO
            metrics_1m = mtf_data.get('1m')
            
            # 1. Auditoría Local (TP/SL)
            # Validación de Tipo: Solo pasamos si es DataFrame válido
            if isinstance(metrics_1m, pd.DataFrame) and not metrics_1m.empty:
                comptroller.auditar_memoria(price, metrics_1m)
            
            # 2. Cerebro
            brain_msg = ""
            # --- CORRECCIÓN DEL ERROR CRÍTICO ---
            # Validamos explícitamente que sea un DataFrame antes de preguntar .empty
            if isinstance(metrics_1m, pd.DataFrame) and not metrics_1m.empty:
                resultado_brain = brain.procesar_mercado(mtf_data, price)
                
                if isinstance(resultado_brain, str):
                    brain_msg = resultado_brain
                else:
                    brain_msg = resultado_brain
                    dash.add_log(brain_msg)
                    session_stats['total_ops'] += 1
            else:
                brain_msg = "Esperando Datos (Cargando)..."

            # D. RENDER
            supervisor.reportar_exito()
            dash.render(price, mtf_data, daily_stats, comptroller.positions, financials, con_status, brain_msg, session_stats)

            # E. SLEEP DINÁMICO
            elapsed = time.time() - start_time
            sleep_time = max(0, cfg.SYNC_CYCLE_FAST - elapsed)
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\nApagando sistema ordenadamente...")
            log.log_operational("MAIN", "Apagado por usuario.")
            break
            
        except Exception as e:
            supervisor.reportar_error(e)
            time.sleep(5)

if __name__ == "__main__":
    main()