import csv
import time
import threading
from datetime import datetime

class OrderManager:
    """
    GESTOR DE ÓRDENES (ORDER MANAGER)
    Responsabilidad: Ejecución atómica y segura de operaciones.
    Protocolo: Orden -> Validar -> Log -> Proteger -> Validar -> Log -> Entregar.
    """
    def __init__(self, config, api_conn, logger):
        self.cfg = config
        self.conn = api_conn
        self.log = logger
        self.lock = threading.Lock() # SEGURIDAD DE HILOS
        self._verificar_archivo_ordenes()

    def _verificar_archivo_ordenes(self):
        try:
            with open(self.cfg.FILE_ORDERS, 'a') as f: pass
        except:
            with open(self.cfg.FILE_ORDERS, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['ID', 'Timestamp', 'Symbol', 'Side', 'Type', 'Price', 'Qty', 'Status', 'Message'])

    def ejecutar_estrategia(self, plan_de_tiro):
        """
        Ejecuta una secuencia completa de entrada al mercado con protección.
        Retorna: (bool_exito, dict_datos_confirmados)
        """
        # 1. BLOQUEO DE RECURSOS (Thread Safety)
        if not self.lock.acquire(blocking=False):
            return False, "⚠️ Gestor ocupado. Intento rechazado."
        
        try:
            order_id = plan_de_tiro['id']
            side = plan_de_tiro['side']
            qty = plan_de_tiro['qty']
            sl_price = plan_de_tiro['sl_price']
            
            self.log.log_operational("GESTOR", f"Iniciando secuencia para {order_id} ({side})")

            # ---------------------------------------------------------
            # PASO 1: COLOCAR ORDEN DE ENTRADA (MARKET)
            # ---------------------------------------------------------
            ok_entry, resp_entry = self.conn.place_market_order(side, qty)
            if not ok_entry:
                self.log.log_error("GESTOR", f"Fallo entrada {order_id}: {resp_entry}")
                return False, f"Error Entrada: {resp_entry}"

            # ---------------------------------------------------------
            # PASO 2: VALIDAR ORDEN DE ENTRADA (Binance Confirmation)
            # ---------------------------------------------------------
            # Esperamos confirmación de 'FILLED' y obtenemos precio real promedio
            real_entry_price, real_qty = self._esperar_confirmacion_fill(resp_entry)
            
            if real_entry_price == 0:
                self.log.log_error("GESTOR", "Orden enviada pero no confirmada (Timeout). Cancelando todo.")
                self.conn.cancel_all_orders()
                return False, "Timeout esperando confirmación ENTRY"

            # ---------------------------------------------------------
            # PASO 3: REGISTRO PRIMARIO (Log)
            # ---------------------------------------------------------
            self._registrar_en_csv(order_id, side, "ENTRY", real_entry_price, real_qty, "FILLED")
            self.log.log_operational("GESTOR", f"Entrada confirmada: {real_qty} @ {real_entry_price}")

            # ---------------------------------------------------------
            # PASO 4: COLOCAR PROTECCIÓN (STOP LOSS)
            # ---------------------------------------------------------
            # El SL va en dirección contraria a la entrada
            sl_side = 'SELL' if side == 'LONG' else 'BUY'
            ok_sl, resp_sl = self.conn.place_stop_loss(sl_side, sl_price)

            # ---------------------------------------------------------
            # PASO 5: VALIDAR PROTECCIÓN Y ROLLBACK (Safety Net)
            # ---------------------------------------------------------
            if not ok_sl:
                self.log.log_error("GESTOR", f"❌ FALLO CRÍTICO AL PONER SL: {resp_sl}. EJECUTANDO ROLLBACK.")
                # ROLLBACK: Cerrar la posición inmediatamente porque está desprotegida
                self._rollback_emergencia(sl_side, real_qty)
                return False, "Fallo SL -> Rollback Ejecutado"

            # ---------------------------------------------------------
            # PASO 6: REGISTRO FINAL Y ENTREGA (Handover)
            # ---------------------------------------------------------
            self._registrar_en_csv(order_id, sl_side, "STOP_LOSS", sl_price, real_qty, "NEW")
            
            # Paquete final para el Contralor
            paquete_confirmado = plan_de_tiro.copy()
            paquete_confirmado['entry_price'] = real_entry_price
            paquete_confirmado['qty'] = real_qty
            paquete_confirmado['status'] = 'OPEN'
            paquete_confirmado['open_time'] = time.time()
            
            return True, paquete_confirmado

        except Exception as e:
            self.log.log_error("GESTOR", f"Excepción No Manejada: {e}")
            return False, f"Excepción: {e}"
        finally:
            self.lock.release()

    def _esperar_confirmacion_fill(self, order_response):
        """Consulta repetidamente a Binance hasta ver status='FILLED'."""
        if self.cfg.MODE == 'SIMULATION':
            return float(order_response.get('avgPrice', 0) or 0), float(order_response.get('cumQty', 0) or 0)

        oid = order_response.get('orderId')
        if not oid: return 0.0, 0.0

        retries = 5
        for _ in range(retries):
            try:
                # Usamos el cliente raw de la conexión para verificar estado
                ord_status = self.conn.client.futures_get_order(symbol=self.cfg.SYMBOL, orderId=oid)
                if ord_status['status'] == 'FILLED':
                    return float(ord_status['avgPrice']), float(ord_status['executedQty'])
                elif ord_status['status'] in ['CANCELED', 'REJECTED', 'EXPIRED']:
                    return 0.0, 0.0
            except: pass
            time.sleep(1) # Espera 1 seg entre chequeos
        return 0.0, 0.0

    def _rollback_emergencia(self, close_side, qty):
        """Cierra la posición a mercado inmediatamente."""
        self.log.log_operational("GESTOR", "⚠️ EJECUTANDO CIERRE DE EMERGENCIA.")
        self.conn.place_market_order(close_side, qty, reduce_only=True)
        self.conn.cancel_all_orders()

    def _registrar_en_csv(self, oid, side, type_, price, qty, status):
        try:
            with open(self.cfg.FILE_ORDERS, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    oid, datetime.now().isoformat(), self.cfg.SYMBOL,
                    side, type_, f"{price:.4f}", qty, status, ""
                ])
        except: pass

    def ejecutar_cierre_parcial(self, pos_data, pct_cierre):
        """Ejecuta un Take Profit parcial (Reduce Only)."""
        if not self.lock.acquire(blocking=False): return False

        try:
            qty_total = pos_data['qty']
            qty_to_close = qty_total * pct_cierre
            # Formatear cantidad según precisión (simplificado, idealmente usar stepSize)
            qty_to_close = round(qty_to_close, 3) 
            
            if qty_to_close <= 0: return False

            close_side = 'SELL' if pos_data['side'] == 'LONG' else 'BUY'
            
            ok, resp = self.conn.place_market_order(close_side, qty_to_close, reduce_only=True)
            if ok:
                self.log.log_operational("GESTOR", f"Cierre Parcial Ejecutado: {qty_to_close}")
                self._registrar_en_csv(pos_data['id'], close_side, "TP_PARTIAL", 0, qty_to_close, "FILLED")
                return True
            return False
        finally:
            self.lock.release()
            
    def cancelar_todo(self):
        with self.lock:
            self.conn.cancel_all_orders()