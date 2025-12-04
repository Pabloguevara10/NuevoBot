import csv
import time
import threading
import math
from datetime import datetime

class OrderManager:
    def __init__(self, config, api_conn, logger):
        self.cfg = config
        self.conn = api_conn
        self.log = logger
        self.lock = threading.Lock()
        
        self.qty_precision = 3
        self.price_precision = 2
        
        self._verificar_archivo_ordenes()
        self._configurar_cuenta()
        self._calibrar_precision_simbolo()

    # ... (Mantener _verificar_archivo_ordenes y _configurar_cuenta igual) ...
    def _verificar_archivo_ordenes(self):
        try:
            with open(self.cfg.FILE_ORDERS, 'a') as f: pass
        except:
            with open(self.cfg.FILE_ORDERS, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['ID', 'Timestamp', 'Symbol', 'Side', 'Type', 'Price', 'Qty', 'Status', 'Message'])

    def _configurar_cuenta(self):
        if self.cfg.MODE == 'SIMULATION': return
        try:
            self.conn.client.futures_change_position_mode(dualSidePosition=True)
        except Exception as e:
            if "No need to change" not in str(e):
                self.log.log_operational("GESTOR", f"Config cuenta (Hedge): {e}")

    def _calibrar_precision_simbolo(self):
        if self.cfg.MODE == 'SIMULATION': return
        try:
            info = self.conn.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == self.cfg.SYMBOL:
                    for f in s['filters']:
                        if f['filterType'] == 'LOT_SIZE':
                            step_size = float(f['stepSize'])
                            self.qty_precision = int(round(-math.log(step_size, 10), 0))
                        if f['filterType'] == 'PRICE_FILTER':
                            tick_size = float(f['tickSize'])
                            self.price_precision = int(round(-math.log(tick_size, 10), 0))
                    self.log.log_operational("GESTOR", f"Calibrado: Qty={self.qty_precision}, Price={self.price_precision}")
        except: pass

    # --- MÉTODOS PÚBLICOS DE FORMATO (NUEVO) ---
    def formatear_precio(self, price):
        """Redondea el precio a los decimales permitidos por Binance."""
        return round(price, self.price_precision)

    def formatear_cantidad(self, qty):
        """Ajusta la cantidad a los decimales permitidos (floor)."""
        factor = 10 ** self.qty_precision
        return math.floor(qty * factor) / factor

    # --- MÉTODOS DE GESTIÓN ---
    def cancelar_orden_por_id(self, order_id):
        if self.cfg.MODE == 'SIMULATION': return True
        try:
            self.conn.client.futures_cancel_order(symbol=self.cfg.SYMBOL, orderId=order_id)
            return True
        except Exception as e:
            # Ignoramos error si la orden ya no existe (Unknown order)
            if "-2011" not in str(e):
                self.log.log_error("GESTOR", f"Fallo cancelando {order_id}: {e}")
            return False

    def ejecutar_estrategia(self, plan_de_tiro):
        if not self.lock.acquire(blocking=False): return False, "Gestor ocupado"
        try:
            order_id = plan_de_tiro['id']
            pos_side = plan_de_tiro['side']
            
            # Usamos los métodos de formato
            qty = self.formatear_cantidad(plan_de_tiro['qty'])
            sl_price = self.formatear_precio(plan_de_tiro['sl_price'])
            
            self.log.log_operational("GESTOR", f"Iniciando {order_id} ({pos_side}) Qty:{qty}")

            # 1. ENTRY
            action_side = 'BUY' if pos_side == 'LONG' else 'SELL'
            ok_entry, resp_entry = self.conn.place_market_order(action_side, pos_side, qty)
            if not ok_entry: return False, f"Error Entrada: {resp_entry}"

            real_entry_price, real_qty = self._esperar_confirmacion_fill(resp_entry)
            if real_entry_price == 0:
                self.conn.cancel_all_orders()
                return False, "Timeout Entry"

            self._registrar_en_csv(order_id, pos_side, "ENTRY", real_entry_price, real_qty, "FILLED")

            # 2. STOP LOSS
            sl_action_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            ok_sl, resp_sl = self.conn.place_stop_loss(sl_action_side, pos_side, sl_price)

            if not ok_sl:
                self._rollback_emergencia(sl_action_side, pos_side, real_qty)
                return False, "Fallo SL -> Rollback"

            sl_order_id = resp_sl.get('orderId')
            self._registrar_en_csv(order_id, sl_action_side, "STOP_LOSS", sl_price, real_qty, "NEW")
            
            paquete = plan_de_tiro.copy()
            paquete['entry_price'] = real_entry_price
            paquete['qty'] = real_qty
            paquete['sl_price'] = sl_price
            paquete['sl_order_id'] = sl_order_id
            paquete['status'] = 'OPEN'
            
            return True, paquete
        except Exception as e:
            self.log.log_error("GESTOR", f"Excepción: {e}")
            return False, str(e)
        finally:
            self.lock.release()

    def _esperar_confirmacion_fill(self, order_response):
        if self.cfg.MODE == 'SIMULATION':
            return float(order_response.get('avgPrice', 0) or 0), float(order_response.get('cumQty', 0) or 0)
        oid = order_response.get('orderId')
        for _ in range(5):
            try:
                ord_status = self.conn.client.futures_get_order(symbol=self.cfg.SYMBOL, orderId=oid)
                if ord_status['status'] == 'FILLED':
                    return float(ord_status['avgPrice']), float(ord_status['executedQty'])
            except: pass
            time.sleep(1)
        return 0.0, 0.0

    def _rollback_emergencia(self, close_side, pos_side, qty):
        self.conn.place_market_order(close_side, pos_side, qty, reduce_only=True)
        self.conn.cancel_all_orders()

    def _registrar_en_csv(self, oid, side, type_, price, qty, status):
        try:
            with open(self.cfg.FILE_ORDERS, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([oid, datetime.now().isoformat(), self.cfg.SYMBOL, side, type_, f"{price:.4f}", qty, status, ""])
        except: pass

    def ejecutar_cierre_parcial(self, pos_data, pct_cierre):
        if not self.lock.acquire(blocking=False): return False
        try:
            qty = self.formatear_cantidad(pos_data['qty'] * pct_cierre)
            if qty <= 0: return False

            pos_side = pos_data['side']
            close_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            
            ok, _ = self.conn.place_market_order(close_side, pos_side, qty, reduce_only=True)
            if ok:
                self._registrar_en_csv(pos_data['id'], close_side, "TP_PARTIAL", 0, qty, "FILLED")
                return True
            return False
        finally:
            self.lock.release()
            
    def cancelar_todo(self):
        with self.lock:
            self.conn.cancel_all_orders()