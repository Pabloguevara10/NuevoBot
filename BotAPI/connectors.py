import math
import logging
import time
import pandas as pd
from colorama import Fore, Style
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Configuración de Logs internos de conexión
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

    # --- NUEVO: OBTENER SALDO USDT ---
    def obtener_saldo_usdt(self):
        try:
            balances = self.client.futures_account_balance()
            for asset in balances:
                if asset['asset'] == 'USDT':
                    return float(asset['balance'])
            return 0.0
        except Exception as e:
            print(f"[WARN] No se pudo leer saldo: {e}")
            return 0.0

    # --- GESTIÓN DE ÓRDENES ---

    def colocar_orden_market(self, side, quantity, position_side):
        try:
            logger_ordenes.info(f"INTENTO MARKET: {side} {quantity}")
            return self.client.futures_create_order(
                symbol=self._formatear_simbolo(), side=side, positionSide=position_side, type='MARKET', quantity=quantity
            )
        except Exception as e:
            print(f"{Fore.RED}[ERROR API] Market: {e}{Style.RESET_ALL}")
            return None

    def colocar_orden_limit(self, side, quantity, price, position_side):
        try:
            p_final = self._redondear_precio(price)
            logger_ordenes.info(f"INTENTO LIMIT: {side} {quantity} @ {p_final}")
            return self.client.futures_create_order(
                symbol=self._formatear_simbolo(), 
                side=side, 
                positionSide=position_side, 
                type='LIMIT',
                price=p_final, 
                quantity=quantity, 
                timeInForce='GTC'
            )
        except Exception as e:
            print(f"{Fore.RED}[ERROR API] Limit: {e}{Style.RESET_ALL}")
            return None

    def colocar_orden_sl_tp(self, side, quantity, stop_price, position_side, tipo):
        try:
            p_final = self._redondear_precio(stop_price)
            return self.client.futures_create_order(
                symbol=self._formatear_simbolo(), side=side, positionSide=position_side, type=tipo,
                stopPrice=p_final, quantity=quantity, timeInForce='GTC', workingType='CONTRACT_PRICE' 
            )
        except BinanceAPIException as e:
            return None

    def verificar_estado_orden(self, order_id):
        try: 
            return self.client.futures_get_order(symbol=self._formatear_simbolo(), orderId=order_id)['status']
        except: return None

    def cancelar_orden(self, order_id):
        try: return self.client.futures_cancel_order(symbol=self._formatear_simbolo(), orderId=order_id)
        except: return False

    def cancelar_todas_ordenes(self):
        symbol = self._formatear_simbolo()
        try: self.client.futures_cancel_all_open_orders(symbol=symbol); return True
        except: return False

    # --- GESTIÓN DE DATOS ---

    def obtener_precio_real(self):
        try: return float(self.client.futures_symbol_ticker(symbol=self._formatear_simbolo())['price'])
        except: return None

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

    def obtener_velas(self, timeframe=None, limit=None):
        try:
            if timeframe is None: timeframe = self.cfg.TF_SCALP
            if timeframe not in self._cache_velas: req_limit = 1000 
            else: req_limit = 50   
            if limit: req_limit = limit

            k = self.client.futures_klines(symbol=self._formatear_simbolo(), interval=timeframe, limit=req_limit)
            new_df = pd.DataFrame(k, columns=['ts','open','high','low','close','volume','x','y','z','w','v','u'])
            new_df = new_df[['ts','open','high','low','close','volume']]
            new_df['timestamp'] = pd.to_datetime(new_df['ts'], unit='ms')
            cols = ['open','high','low','close','volume']
            new_df[cols] = new_df[cols].astype(float)
            
            if timeframe not in self._cache_velas: self._cache_velas[timeframe] = new_df
            else:
                combined = pd.concat([self._cache_velas[timeframe], new_df]).drop_duplicates(subset=['ts'], keep='last')
                self._cache_velas[timeframe] = combined.iloc[-1000:].sort_values('ts').reset_index(drop=True)
            return self._cache_velas[timeframe]
        except Exception as e: 
            return self._cache_velas.get(timeframe, pd.DataFrame())

    def obtener_trades_historicos(self, start_time_ms):
        try: return self.client.futures_account_trades(symbol=self._formatear_simbolo(), startTime=int(start_time_ms))
        except: return []

    def obtener_ordenes_historicas(self, start_time_ms):
        try: return self.client.futures_get_all_orders(symbol=self._formatear_simbolo(), startTime=int(start_time_ms))
        except: return []

# --- CLIENTE SIMULADO (MOCK) ---
class MockClient:
    def __init__(self, config): 
        self.cfg = config
        self.step_size = 0.01
        self.simulated_balance = self.cfg.CAPITAL_TRABAJO
    
    def inicializar(self): pass
    def obtener_precio_real(self): return 100.0
    def obtener_velas(self, timeframe=None, limit=None): return pd.DataFrame()
    def obtener_ordenes_abiertas(self): return []
    def obtener_posicion_abierta(self): return {}
    def obtener_trades_historicos(self, x): return []
    
    # NUEVO: Saldo simulado
    def obtener_saldo_usdt(self): return self.simulated_balance
    
    def colocar_orden_market(self, side, qty, pos_side): return {'orderId': 1}
    def colocar_orden_limit(self, side, qty, price, pos_side): return {'orderId': 2} 
    def colocar_orden_sl_tp(self, side, qty, stop, pos, tipo): return {'orderId': 3}
    def verificar_estado_orden(self, oid): return 'FILLED'
    def cancelar_orden(self, oid): return True
    def cancelar_todas_ordenes(self): return True