import time
import sys
import os

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

def main():
    print("Iniciando SENTINEL AI PRO (V2.0)...")
    
    cfg = Config()
    log = SystemLogger()
    dash = Dashboard()
    conn = APIManager(cfg, log)
    metrics_mgr = MetricsManager(cfg, conn)
    financials = Financials(cfg, conn)
    order_mgr = OrderManager(cfg, conn, log)
    comptroller = Comptroller(cfg, order_mgr, financials, log)
    shooter = Shooter(cfg, financials, order_mgr, comptroller, log)
    brain = Brain(cfg, shooter, log)
    
    human = HumanInput(cfg, shooter, order_mgr, comptroller, log)
    human.iniciar()
    tele = TelegramBot(cfg, shooter, comptroller, order_mgr, log)
    tele.iniciar()
    
    session_stats = {'wins': 0, 'losses': 0, 'total_ops': 0}
    last_slow_cycle = 0
    mtf_data, daily_stats = {}, {}

    dash.add_log("Sistema Online. Arquitectura Dual Speed.")
    
    while True:
        try:
            now = time.time()
            price = conn.get_real_price()
            con_status = conn.check_heartbeat()

            # Ciclo Lento (10s)
            if now - last_slow_cycle > 10:
                mtf_data, daily_stats = metrics_mgr.sincronizar_y_calcular()
                comptroller.sincronizar_estado_externo(price)
                last_slow_cycle = now

            # Ciclo Rápido (1s)
            comptroller.auditar_memoria(price, mtf_data)
            
            metrics_1m = mtf_data.get('1m', {})
            brain_decision = brain.procesar_mercado(metrics_1m, price)
            
            brain_msg = ""
            if isinstance(brain_decision, dict):
                order_id = brain_decision['id']
                dash.add_log(f"Orden: {order_id} ({brain_decision['side']})")
                comptroller.registrar_posicion(brain_decision)
                session_stats['total_ops'] += 1
                brain_msg = f"EJECUTADO {order_id}"
            else:
                brain_msg = str(brain_decision)

            dash.render(price, mtf_data, daily_stats, comptroller.positions, financials, con_status, brain_msg, session_stats)
            time.sleep(1)

        except KeyboardInterrupt:
            print("\nApagando...")
            break
        except Exception as e:
            log.log_error("MAIN", str(e))
            time.sleep(5)

if __name__ == "__main__":
    main()