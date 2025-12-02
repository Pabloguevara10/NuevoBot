import csv
import os
import time
import math
from datetime import datetime
from binance.exceptions import BinanceAPIException

class OrderManager:
    def __init__(self, config, api_conn, logger):
        self.cfg = config
        self.conn = api_conn
        self.log = logger
        self.qty_precision = 3 
        self._init_db()
        self._configurar_cuenta()
        self._cargar_reglas_simbolo() 

    def _init_db(self):
        if not os.path.exists(self.cfg.FILE_ORDERS):
            with open(self.cfg.FILE_ORDERS, 'w', newline='') as f:
                csv.writer(f).writerow(['ID','Time','Side','Price','Qty','Status','Real_Entry','Real_Qty'])

    def _cargar_reglas_simbolo(self):
        if self.cfg.MODE == 'SIMULATION': return
        try:
            info = self.conn.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == self.cfg.SYMBOL:
                    for f in s['filters']:
                        if f['filterType'] == 'LOT_SIZE':
                            self.qty_precision = int(round(-math.log(float(f['stepSize']), 10), 0))
                            self.log.log_operational("GESTOR", f"Precisión: {self.qty_precision}")
                            return
        except: pass

    def _formatear_cantidad(self, qty): return "{:.{}f}".format(qty, self.qty_precision)

    def _configurar_cuenta(self):
        if self.cfg.MODE == 'SIMULATION': return
        try:
            self.conn.client.futures_change_leverage(symbol=self.cfg.SYMBOL, leverage=self.cfg.LEVERAGE)
            try: self.conn.client.futures_change_margin_type(symbol=self.cfg.SYMBOL, marginType='ISOLATED')
            except: pass
            try: self.conn.client.futures_change_position_mode(dualSidePosition=True)
            except: pass
        except: pass

    def obtener_posicion_real(self):
        if self.cfg.MODE == 'SIMULATION': return 0.0, 0.0
        try:
            positions = self.conn.client.futures_position_information(symbol=self.cfg.SYMBOL)
            for p in positions:
                amt = float(p['positionAmt'])
                if amt != 0: return amt, float(p['entryPrice'])
            return 0.0, 0.0
        except: return 0.0, 0.0

    def _verificar_orden_filled(self, order_id):
        if self.cfg.MODE == 'SIMULATION': return True, 0, 0
        for _ in range(3):
            try:
                ord_stat = self.conn.client.futures_get_order(symbol=self.cfg.SYMBOL, orderId=order_id)
                if ord_stat['status'] == 'FILLED':
                    return True, float(ord_stat['avgPrice']), float(ord_stat['executedQty'])
                elif ord_stat['status'] in ['CANCELED', 'REJECTED']: return False, 0, 0
            except: pass
            time.sleep(1)
        return False, 0, 0

    def _rollback_emergencia(self, position_side, qty):
        try:
            action_side = 'SELL' if position_side == 'LONG' else 'BUY'
            self.conn.client.futures_create_order(
                symbol=self.cfg.SYMBOL, side=action_side, positionSide=position_side,
                type='MARKET', quantity=self._formatear_cantidad(qty), reduceOnly=True
            )
            self.log.log_operational("GESTOR", "ROLLBACK EXITOSO.")
        except Exception as e:
            self.log.log_error("GESTOR", f"FALLO ROLLBACK: {e}")

    def ejecutar_plan(self, plan):
        try:
            qty_str = self._formatear_cantidad(plan['qty'])
            pos_side = plan['side']
            side_ord = 'BUY' if pos_side == 'LONG' else 'SELL'
            
            resp_main = {}
            if self.cfg.MODE == 'SIMULATION':
                resp_main = {'orderId': 'SIM', 'status': 'FILLED', 'avgPrice': str(plan['entry_price']), 'cumQty': qty_str}
            else:
                for _ in range(2):
                    try:
                        resp_main = self.conn.client.futures_create_order(
                            symbol=self.cfg.SYMBOL, side=side_ord, positionSide=pos_side,
                            type='MARKET', quantity=qty_str
                        )
                        break
                    except Exception as e:
                        if "Precision" in str(e): return None
                        time.sleep(0.5)

            if 'orderId' not in resp_main: return None
            
            real_price = float(resp_main.get('avgPrice', 0))
            real_qty = float(resp_main.get('cumQty', 0))
            if real_qty == 0 and self.cfg.MODE != 'SIMULATION':
                filled, rp, rq = self._verificar_orden_filled(resp_main['orderId'])
                if not filled: return None
                real_price, real_qty = rp, rq
            
            plan['entry_price'] = real_price
            plan['qty'] = real_qty
            self.log.log_operational("GESTOR", f"Orden confirmada: {real_qty} @ {real_price}")

            # SL
            sl_ok = False
            if self.cfg.MODE != 'SIMULATION':
                for _ in range(3):
                    try:
                        sl_side = 'SELL' if pos_side == 'LONG' else 'BUY'
                        self.conn.client.futures_create_order(
                            symbol=self.cfg.SYMBOL, side=sl_side, positionSide=pos_side,
                            type='STOP_MARKET', stopPrice="{:.2f}".format(plan['sl']), closePosition=True
                        )
                        sl_ok = True
                        break
                    except: time.sleep(1)
            else: sl_ok = True

            if sl_ok:
                with open(self.cfg.FILE_ORDERS, 'a', newline='') as f:
                    csv.writer(f).writerow([plan['id'], datetime.now(), plan['side'], real_price, real_qty, "FILLED", real_price, real_qty])
                return plan
            else:
                self._rollback_emergencia(pos_side, real_qty)
                return None
        except Exception as e:
            self.log.log_error("GESTOR", f"Excepción Crítica: {e}")
            return None

    def cancelar_todas_ordenes(self):
        if self.cfg.MODE != 'SIMULATION':
            try: self.conn.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
            except: pass

    def forzar_cierre_mercado(self, side, qty):
        if self.cfg.MODE == 'SIMULATION': return True
        try:
            # side aqui es la posicion (LONG/SHORT)
            action_side = 'SELL' if side == 'LONG' else 'BUY'
            self.conn.client.futures_create_order(
                symbol=self.cfg.SYMBOL, side=action_side, positionSide=side,
                type='MARKET', quantity=self._formatear_cantidad(qty), reduceOnly=True
            )
            return True
        except BinanceAPIException as e: return e.code == -2022
        except: return False

    def ejecutar_dca(self, plan_original, current_price):
        try:
            qty_str = self._formatear_cantidad(plan_original['qty'])
            pos_side = plan_original['side']
            action_side = 'BUY' if pos_side == 'LONG' else 'SELL'
            
            if self.cfg.MODE == 'SIMULATION': return True
            
            resp = self.conn.client.futures_create_order(
                symbol=self.cfg.SYMBOL, side=action_side, positionSide=pos_side,
                type='MARKET', quantity=qty_str
            )
            if 'orderId' not in resp: return False
            
            self.conn.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
            sl_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            self.conn.client.futures_create_order(
                symbol=self.cfg.SYMBOL, side=sl_side, positionSide=pos_side,
                type='STOP_MARKET', stopPrice="{:.2f}".format(plan_original['sl']), closePosition=True
            )
            return True
        except: return False

    def ejecutar_cierre_parcial(self, pid, qty, price):
        """Ejecuta cierre parcial."""
        try:
            net_qty, _ = self.obtener_posicion_real()
            if net_qty == 0: return False
            
            pos_side = 'LONG' if net_qty > 0 else 'SHORT'
            action_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            
            if self.cfg.MODE == 'SIMULATION': return True
            
            self.conn.client.futures_create_order(
                symbol=self.cfg.SYMBOL, side=action_side, positionSide=pos_side,
                type='MARKET', quantity=self._formatear_cantidad(qty), reduceOnly=True
            )
            self.log.log_operational("GESTOR", f"TP Parcial {pid} ejecutado.")
            return True
        except Exception as e:
            self.log.log_error("GESTOR", f"Fallo TP Parcial: {e}")
            return False