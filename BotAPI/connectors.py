# connectors.py
import math
import logging
import time
import pandas as pd
from colorama import Fore, Style
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger_ordenes = logging.getLogger('audit_orders')
logger_ordenes.setLevel(logging.INFO)
fh = logging.FileHandler('debug_ordenes.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger_ordenes.addHandler(fh)

class BinanceClient:
    def __init__(self, config):
        self.cfg = config
        self.client = Client(self.cfg.API_KEY, self.cfg.API_SECRET, testnet=(self.cfg.MODE == 'TESTNET'))
        self.step_size = None
        self.tick_size = None
        self._cache_velas = {} 

    def inicializar(self):
        try:
            self.client.futures_ping()
            print(f"{Fore.GREEN}[BINANCE] Conexión Futuros {self.cfg.MODE} OK.{Style.RESET_ALL}")
            self._cargar_reglas_simbolo()
            self._configurar_cuenta()
        except BinanceAPIException as e:
            print(f"{Fore.RED}[ERROR CRÍTICO] Fallo conexión: {e}{Style.RESET_ALL}")

    def _formatear_simbolo(self): return self.cfg.SYMBOL.replace('/', '')

    def _cargar_reglas_simbolo(self):
        try:
            info = self.client.futures_exchange_info()
            symbol = self._formatear_simbolo()
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    for f in s['filters']:
                        if f['filterType'] == 'LOT_SIZE': self.step_size = float(f['stepSize'])
                        if f['filterType'] == 'PRICE_FILTER': self.tick_size = float(f['tickSize'])
                    if self.step_size and self.tick_size:
                        print(f"[INFO] Reglas {symbol}: Step={self.step_size}, Tick={self.tick_size}")
                    break
        except Exception as e: print(f"[WARN] Error reglas: {e}")

    def _redondear_precio(self, precio):
        if not self.tick_size: return "{:.2f}".format(precio)
        precision = int(round(-math.log(self.tick_size, 10), 0))
        return "{:.{}f}".format(precio, precision)

    def _configurar_cuenta(self):
        if self.cfg.MODE == 'SIMULATION': return
        try: self.client.futures_change_position_mode(dualSidePosition=True)
        except: pass
        try:
            self.client.futures_change_margin_type(symbol=self._formatear_simbolo(), marginType='ISOLATED')
            self.client.futures_change_leverage(symbol=self._formatear_simbolo(), leverage=self.cfg.LEVERAGE)
        except: pass

    def obtener_mejor_precio_libro(self, side):
        try:
            depth = self.client.futures_order_book(symbol=self._formatear_simbolo(), limit=5)
            return float(depth['bids'][0][0]) if side == 'BUY' else float(depth['asks'][0][0])
        except: return None

    def colocar_orden_market(self, side, quantity, position_side):
        try:
            logger_ordenes.info(f"INTENTO MARKET: {side} {quantity}")
            order = self.client.futures_create_order(
                symbol=self._formatear_simbolo(), side=side, positionSide=position_side, type='MARKET', quantity=quantity
            )
            logger_ordenes.info(f"EXITO MARKET ID: {order['orderId']}")
            return order
        except Exception as e:
            print(f"{Fore.RED}[ERROR API] Market: {e}{Style.RESET_ALL}")
            return None

    def colocar_orden_limit(self, side, quantity, price, position_side):
        try:
            p_final = self._redondear_precio(price)
            logger_ordenes.info(f"INTENTO LIMIT: {side} {quantity} @ {p_final}")
            return self.client.futures_create_order(
                symbol=self._formatear_simbolo(), side=side, positionSide=position_side, type='LIMIT',
                price=p_final, quantity=quantity, timeInForce='GTC'
            )
        except Exception as e:
            logger_ordenes.error(f"FALLO LIMIT: {e}")
            return None

    def colocar_orden_sl_tp(self, side, quantity, stop_price, position_side, tipo):
        try:
            p_final = self._redondear_precio(stop_price)
            logger_ordenes.info(f"INTENTO {tipo}: {side} {quantity} @ {p_final}")
            return self.client.futures_create_order(
                symbol=self._formatear_simbolo(), side=side, positionSide=position_side, type=tipo,
                stopPrice=p_final, quantity=quantity, timeInForce='GTC', 
                # CAMBIO CRÍTICO: Usar CONTRACT_PRICE (Last Price) en vez de MARK_PRICE
                workingType='CONTRACT_PRICE' 
            )
        except BinanceAPIException as e:
            logger_ordenes.error(f"RECHAZO {tipo}: {e.message}")
            return None

    def verificar_estado_orden(self, order_id):
        try: return self.client.futures_get_order(symbol=self._formatear_simbolo(), orderId=order_id)['status']
        except: return None

    def cancelar_orden(self, order_id):
        try: return self.client.futures_cancel_order(symbol=self._formatear_simbolo(), orderId=order_id)
        except: return False

    def cancelar_todas_ordenes(self):
        symbol = self._formatear_simbolo()
        for i in range(3):
            try:
                self.client.futures_cancel_all_open_orders(symbol=symbol)
                time.sleep(0.2)
                if len(self.client.futures_get_open_orders(symbol=symbol)) == 0:
                    logger_ordenes.info("LIMPIEZA COMPLETADA")
                    return True
            except: time.sleep(0.5)
        return False

    def obtener_precio_real(self):
        try: return float(self.client.futures_symbol_ticker(symbol=self._formatear_simbolo())['price'])
        except: return None

    def obtener_velas(self, timeframe=None, limit=None):
        try:
            if timeframe is None: timeframe = self.cfg.TF_SCALP
            req_limit = 200 if timeframe not in self._cache_velas else 5
            k = self.client.futures_klines(symbol=self._formatear_simbolo(), interval=timeframe, limit=req_limit)
            new_df = pd.DataFrame(k, columns=['ts','open','high','low','close','volume','x','y','z','w','v','u'])
            new_df = new_df[['ts','open','high','low','close','volume']]
            new_df['timestamp'] = pd.to_datetime(new_df['ts'], unit='ms')
            cols = ['open','high','low','close','volume']
            new_df[cols] = new_df[cols].astype(float)
            if timeframe not in self._cache_velas: self._cache_velas[timeframe] = new_df
            else:
                combined = pd.concat([self._cache_velas[timeframe], new_df]).drop_duplicates(subset=['ts'], keep='last')
                self._cache_velas[timeframe] = combined.iloc[-500:].sort_values('ts').reset_index(drop=True)
            return self._cache_velas[timeframe]
        except: return self._cache_velas.get(timeframe, pd.DataFrame())

    def obtener_posicion_abierta(self):
        try:
            info = self.client.futures_position_information(symbol=self._formatear_simbolo())
            if info:
                for pos in info:
                    if float(pos['positionAmt']) != 0: return pos
            return {}
        except: return None

    def obtener_ordenes_abiertas(self):
        try: return self.client.futures_get_open_orders(symbol=self._formatear_simbolo())
        except: return []

    def obtener_ordenes_historicas(self, start_time_ms):
        try: return self.client.futures_get_all_orders(symbol=self._formatear_simbolo(), startTime=int(start_time_ms))
        except: return []

    def obtener_trades_historicos(self, start_time_ms):
        try: return self.client.futures_account_trades(symbol=self._formatear_simbolo(), startTime=int(start_time_ms))
        except: return []

class MockClient:
    def __init__(self, config): pass
    def inicializar(self): pass