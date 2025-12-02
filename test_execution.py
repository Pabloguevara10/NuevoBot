import time
import sys
import os
import uuid

# --- CONFIGURACIÓN DE RUTAS ---
# Esto permite importar tus módulos actuales para probarlos
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from config.config import Config
from connections.api_manager import APIManager
from logs.system_logger import SystemLogger
from execution.order_manager import OrderManager

def run_test():
    print("=========================================")
    print("🧪 INICIANDO PRUEBA DE FUEGO (EJECUCIÓN)")
    print("=========================================")

    # 1. INICIALIZACIÓN
    print("[1/5] Inicializando Módulos...")
    try:
        cfg = Config()
        # Forzamos modo TESTNET por seguridad
        cfg.MODE = 'TESTNET'
        
        log = SystemLogger()
        conn = APIManager(cfg, log)
        
        # Verificar conexión
        if not conn.check_heartbeat()['binance']:
            print("❌ ERROR: No hay conexión con Binance.")
            return

        # Inicializar al protagonista: El Gestor
        om = OrderManager(cfg, conn, log)
        print("✅ Módulos cargados correctamente.")
        
    except Exception as e:
        print(f"❌ Error iniciando módulos: {e}")
        return

    # 2. OBTENER DATOS DE MERCADO
    print("\n[2/5] Obteniendo Precio y Saldo...")
    price = conn.get_real_price()
    print(f"   Precio Actual {cfg.SYMBOL}: {price} USDT")
    
    if price == 0:
        print("❌ Error: Precio es 0.")
        return

    # 3. PREPARAR ORDEN DE PRUEBA (Mínima viable)
    # Calculamos una cantidad que valga aprox 20 USDT para cumplir el mínimo de Binance
    target_usdt = 20.0
    qty_test = target_usdt / price
    
    # Definimos un SL lejos para que no salte inmediatamente
    sl_price = price * 0.95 # 5% abajo
    
    test_plan = {
        'id': 'TEST_' + str(uuid.uuid4())[:4],
        'side': 'LONG',
        'qty': qty_test,
        'entry_price': price,
        'sl': sl_price,
        'leverage': 5
    }
    
    print(f"   Plan de Prueba: LONG {qty_test:.3f} {cfg.SYMBOL} (Valor: ~{target_usdt} USDT)")

    # 4. EJECUTAR ENTRADA (La prueba de fuego)
    print("\n[3/5] ⚡ INTENTANDO ABRIR POSICIÓN...")
    resultado = om.ejecutar_plan(test_plan)
    
    if resultado:
        print(f"✅ ¡ÉXITO! Orden {resultado['id']} abierta y confirmada.")
        print("   Verifica en Binance que la posición y el SL existan.")
    else:
        print("❌ FALLO: El Gestor no pudo abrir la orden.")
        print("   Revisa 'system_errors.csv' para ver el motivo exacto.")
        return # Abortar si no abrió

    # 5. ESPERA (Para que veas la orden viva)
    print("\n[4/5] ⏳ Esperando 10 segundos antes de cerrar...")
    for i in range(10, 0, -1):
        print(f"   Cerrando en {i}...", end='\r')
        time.sleep(1)
    print(" " * 20)

    # 6. CERRAR POSICIÓN (Limpieza)
    print("\n[5/5] 🧹 CERRANDO POSICIÓN...")
    # Usamos la cantidad real reportada por el gestor si es posible, sino la teórica
    qty_real = resultado['qty']
    
    cierre_ok = om.forzar_cierre_mercado('SELL', qty_real)
    
    if cierre_ok:
        print("✅ CIERRE EXITOSO. Prueba completada.")
        
        # Limpieza extra de órdenes pendientes (SL)
        om.cancelar_todas_ordenes()
        print("   Órdenes pendientes limpiadas.")
    else:
        print("❌ FALLO AL CERRAR. ¡Revisa tu cuenta manualmente!")

if __name__ == "__main__":
    run_test()