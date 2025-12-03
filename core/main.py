import time
import sys
import os
import threading

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
from interfaces.human_input import HumanInput
from interfaces.telegram_bot import TelegramBot

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
        # Si un ciclo se completa bien, reseteamos el contador
        if self.error_count > 0:
            self.error_count = 0

    def _protocolo_emergencia(self):
        self.log.log_error("SUPERVISOR", "🚨 LÍMITE DE ERRORES ALCANZADO. APAGADO DE EMERGENCIA.")
        print("\n!!! PROTOCOLO DE EMERGENCIA ACTIVADO !!!")
        try:
            self.om.cancelar_todo()
        except: pass
        sys.exit(1)

def main():
    print("Iniciando SENTINEL AI PRO (V2.0 Refactored)...")
    
    # 1. INICIALIZACIÓN DE MÓDULOS
    cfg = Config()
    log = SystemLogger()
    dash = Dashboard()
    
    # Conexión Blindada
    conn = APIManager(cfg, log)
    
    # Núcleo de Datos y Finanzas
    metrics_mgr = MetricsManager(cfg, conn)
    financials = Financials(cfg, conn)
    
    # Núcleo de Ejecución (La Fortaleza)
    order_mgr = OrderManager(cfg, conn, log)
    comptroller = Comptroller(cfg, order_mgr, financials, log)
    
    # Lógica Estratégica
    shooter = Shooter(cfg, financials, order_mgr, comptroller, log)
    brain = Brain(cfg, shooter, log)
    
    # Supervisor
    supervisor = BotSupervisor(order_mgr, log)

    # 2. INTERFACES EN HILOS SECUNDARIOS
    # Telegram
    tele = TelegramBot(cfg, shooter, comptroller, order_mgr, log)
    tele.iniciar()
    
    # Input Humano (Opcional, si se usa en consola)
    # human = HumanInput(cfg, shooter, order_mgr, comptroller, log)
    # human.iniciar()

    # Variables de Control de Ciclos
    last_slow_cycle = 0
    mtf_data = {}
    daily_stats = {}
    session_stats = {'wins': 0, 'losses': 0, 'total_ops': 0} # Placeholder para dashboard

    dash.add_log("Sistema Online. Arquitectura Blindada V2.")
    log.log_operational("MAIN", "Sistema Iniciado correctamente.")

    # ==================================================================
    # MAIN LOOP (CICLO INFINITO)
    # ==================================================================
    while True:
        try:
            start_time = time.time()
            
            # A. OBTENCIÓN DE DATOS CRÍTICOS (Síncrono)
            price = conn.get_real_price()
            if price is None:
                # Si no hay precio, no podemos hacer NADA. Esperamos y reintentamos.
                supervisor.reportar_error("Fallo obteniendo precio real.")
                time.sleep(cfg.REQUEST_TIMEOUT)
                continue

            con_status = conn.check_heartbeat()

            # B. CICLO LENTO (Sincronización y Cálculos Pesados)
            # Frecuencia: Config.SYNC_CYCLE_SLOW (10s)
            if start_time - last_slow_cycle > cfg.SYNC_CYCLE_SLOW:
                dash.add_log("Sincronizando...", "DEBUG")
                
                # 1. Actualizar Indicadores MTF
                mtf_data, daily_stats = metrics_mgr.sincronizar_y_calcular()
                
                # 2. Auditoría de Posiciones (Huérfanas/Fantasmas)
                comptroller.sincronizar_estado_externo()
                
                last_slow_cycle = start_time

            # C. CICLO RÁPIDO (Ejecución Táctica)
            # Frecuencia: Cada iteración (aprox 1s)
            
            # 1. Auditoría Local (TP/SL/Trailing)
            # El Comptroller decide si cierra algo basado en el precio actual
            metrics_1m = mtf_data.get('1m', {})
            comptroller.auditar_memoria(price, metrics_1m)

            # 2. Cerebro (Análisis y Señales)
            # Solo procesamos si tenemos datos frescos
            brain_msg = ""
            if metrics_1m:
                resultado_brain = brain.procesar_mercado(mtf_data, price)
                
                if isinstance(resultado_brain, str):
                    # Es un mensaje de estado (ej. "Esperando...")
                    brain_msg = resultado_brain
                else:
                    # Es una confirmación de ejecución (ej. "✅ EJECUTADO...")
                    brain_msg = resultado_brain
                    dash.add_log(brain_msg)
                    session_stats['total_ops'] += 1

            # D. REPORTAR SALUD Y RENDERIZAR
            supervisor.reportar_exito()
            dash.render(price, mtf_data, daily_stats, comptroller.positions, financials, con_status, brain_msg, session_stats)

            # E. CONTROL DE TIEMPO (Sleep Dinámico)
            # Asegura que el ciclo dure al menos 1s para no saturar CPU/API
            elapsed = time.time() - start_time
            sleep_time = max(0, cfg.SYNC_CYCLE_FAST - elapsed)
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\nApagando sistema ordenadamente...")
            log.log_operational("MAIN", "Apagado por usuario.")
            break
            
        except Exception as e:
            # Captura cualquier error no previsto en los módulos
            supervisor.reportar_error(e)
            time.sleep(5) # Pausa de seguridad antes de reiniciar ciclo

if __name__ == "__main__":
    main()