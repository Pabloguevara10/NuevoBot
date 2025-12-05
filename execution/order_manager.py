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

    # --- FORMATO ---
    def formatear_precio(self, price):
        return round(price, self.price_precision)

    def formatear_cantidad(self, qty):
        factor = 10 ** self.qty_precision
        return math.floor(qty * factor) / factor

    # --- GESTIÓN ---
    def cancelar_orden_por_id(self, order_id):
        if self.cfg.MODE == 'SIMULATION': return True
        try:
            self.conn.client.futures_cancel_order(symbol=self.cfg.SYMBOL, orderId=order_id)
            return True
        except Exception as e:
            if "-2011" not in str(e): self.log.log_error("GESTOR", f"Fallo cancelando {order_id}: {e}")
            return False

    def _colocar_take_profits_duros(self, side, pos_side, qty_total, tps, tp_split):
        """
        Coloca órdenes LIMIT reduceOnly en Binance para asegurar la salida.
        """
        if self.cfg.MODE == 'SIMULATION': return []
        
        ids_tps = []
        qty_acumulada = 0
        
        for i, precio_obj in enumerate(tps):
            # Calcular cantidad para este escalón
            pct = tp_split[i]
            qty_escalon = self.formatear_cantidad(qty_total * pct)
            
            # Ajuste final para no dejar residuos por redondeo en el último TP
            if i == len(tps) - 1:
                qty_escalon = self.formatear_cantidad(qty_total - qty_acumulada)
            
            if qty_escalon <= 0: continue
            
            qty_acumulada += qty_escalon
            precio_final = self.formatear_precio(precio_obj)
            
            try:
                # Orden LIMIT (Maker) para salir
                params = {
                    'symbol': self.cfg.SYMBOL,
                    'side': side,           # SELL si es Long, BUY si es Short
                    'positionSide': pos_side,
                    'type': 'LIMIT',
                    'timeInForce': 'GTC',   # Good Till Cancel
                    'quantity': qty_escalon,
                    'price': str(precio_final),
                    'reduceOnly': False     # En Hedge Mode no se usa reduceOnly explícito, la dirección lo define
                }
                # NOTA: En Hedge Mode, vender sobre una posición LONG cierra la posición.
                # No se requiere reduceOnly=True si positionSide es correcto, pero por seguridad binance a veces lo pide.
                # Probaremos sin reduceOnly primero ya que en Hedge la API suele rechazarlo si se combina con positionSide.
                
                order = self.conn.client.futures_create_order(**params)
                ids_tps.append(order['orderId'])
                self.log.log_operational("GESTOR", f"TP Hard colocado: {qty_escalon} @ {precio_final}")
                
            except Exception as e:
                self.log.log_error("GESTOR", f"Fallo colocando TP {i+1}: {e}")
                
        return ids_tps

    def ejecutar_estrategia(self, plan_de_tiro):
        if not self.lock.acquire(blocking=False): return False, "Gestor ocupado"
        try:
            order_id = plan_de_tiro['id']
            pos_side = plan_de_tiro['side']
            
            qty = self.formatear_cantidad(plan_de_tiro['qty'])
            sl_price = self.formatear_precio(plan_de_tiro['sl_price'])
            
            self.log.log_operational("GESTOR", f"Iniciando {order_id} ({pos_side}) Qty:{qty}")

            # 1. ENTRY (MARKET)
            action_side = 'BUY' if pos_side == 'LONG' else 'SELL'
            ok_entry, resp_entry = self.conn.place_market_order(action_side, pos_side, qty)
            if not ok_entry: return False, f"Error Entrada: {resp_entry}"

            real_entry_price, real_qty = self._esperar_confirmacion_fill(resp_entry)
            if real_entry_price == 0:
                self.conn.cancel_all_orders()
                return False, "Timeout Entry"

            self._registrar_en_csv(order_id, pos_side, "ENTRY", real_entry_price, real_qty, "FILLED")

            # 2. STOP LOSS (MARKET PROTECCION)
            sl_action_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            ok_sl, resp_sl = self.conn.place_stop_loss(sl_action_side, pos_side, sl_price)

            if not ok_sl:
                self._rollback_emergencia(sl_action_side, pos_side, real_qty)
                return False, "Fallo SL -> Rollback"

            sl_order_id = resp_sl.get('orderId')
            self._registrar_en_csv(order_id, sl_action_side, "STOP_LOSS", sl_price, real_qty, "NEW")
            
            # 3. TAKE PROFITS (HARD LIMIT ORDERS)
            # Colocamos las órdenes en el libro de Binance inmediatamente
            tps_prices = plan_de_tiro.get('tps', [])
            tp_split = self.cfg.ShooterConfig.TP_SPLIT
            
            tp_ids = self._colocar_take_profits_duros(sl_action_side, pos_side, real_qty, tps_prices, tp_split)
            
            # Paquete de retorno
            paquete = plan_de_tiro.copy()
            paquete['entry_price'] = real_entry_price
            paquete['qty'] = real_qty
            paquete['sl_price'] = sl_price
            paquete['sl_order_id'] = sl_order_id
            paquete['tp_order_ids'] = tp_ids # Guardamos los IDs de los TPs
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
        # NOTA: Con TPs duros, esta función se usa menos, pero sirve para salidas manuales o ajustes.
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