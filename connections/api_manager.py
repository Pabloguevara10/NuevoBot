import requests
import time
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from requests.exceptions import RequestException

class APIManager:
    def __init__(self, config, logger):
        self.cfg = config
        self.log = logger
        self.client = None
        self.session = requests.Session()
        self.status = {'binance': False, 'telegram': False}
        self._conectar_binance()

    def _conectar_binance(self):
        try:
            self.client = Client(
                self.cfg.API_KEY, 
                self.cfg.API_SECRET, 
                testnet=(self.cfg.MODE == 'TESTNET')
            )
            self.client.ping()
            self.status['binance'] = True
            self.log.log_operational("API", f"Conectado a Binance ({self.cfg.MODE})")
        except Exception as e:
            self.log.log_error("API_INIT", f"Fallo crítico conectando Binance: {e}")
            self.status['binance'] = False

    def check_heartbeat(self):
        try:
            self.client.ping() 
            self.status['binance'] = True
        except Exception:
            self.status['binance'] = False
            if not self.status['binance']: 
                self._conectar_binance()
            
        try:
            url = f"https://api.telegram.org/bot{self.cfg.TELEGRAM_TOKEN}/getMe"
            r = self.session.get(url, timeout=2)
            self.status['telegram'] = r.status_code == 200
        except: 
            self.status['telegram'] = False
            
        return self.status

    def get_historical_candles(self, symbol, interval, limit=100, start_time=None):
        try:
            if start_time:
                return self.client.futures_klines(
                    symbol=symbol, interval=interval, startTime=int(start_time), limit=1000
                )
            return self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        except (BinanceAPIException, BinanceRequestException) as e:
            self.log.log_error("API_DATA", f"Error Binance: {e}")
            return []
        except RequestException as e:
            self.log.log_error("API_NET", f"Error Red: {e}")
            return []
        except Exception as e:
            self.log.log_error("API_UNKNOWN", f"Error Desconocido: {e}")
            return []

    def get_real_price(self):
        try:
            ticker = self.client.futures_symbol_ticker(symbol=self.cfg.SYMBOL)
            return float(ticker['price'])
        except Exception as e:
            self.log.log_error("API_PRICE", f"Fallo obteniendo precio: {e}")
            return None

    def get_account_balance(self):
        if self.cfg.MODE == 'SIMULATION': 
            return self.cfg.FIXED_CAPITAL_AMOUNT
            
        try:
            info = self.client.futures_account_balance()
            for asset in info:
                if asset['asset'] == 'USDT':
                    return float(asset['balance'])
            return 0.0
        except Exception as e:
            self.log.log_error("API_BALANCE", f"Error obteniendo saldo: {e}")
            return 0.0

    # ==========================================
    # MÉTODOS DE EJECUCIÓN (CORREGIDOS HEDGE MODE)
    # ==========================================
    def place_market_order(self, side, position_side, qty, reduce_only=False):
        """
        side: 'BUY' o 'SELL'
        position_side: 'LONG' o 'SHORT'
        NOTA: En Hedge Mode NO se envía reduceOnly. Binance determina cierre
        automáticamente si envías la orden contraria sobre el mismo positionSide.
        """
        if self.cfg.MODE == 'SIMULATION':
            return True, {'orderId': 'SIM_ORD', 'avgPrice': 0, 'cumQty': qty}

        try:
            params = {
                'symbol': self.cfg.SYMBOL,
                'side': side,
                'positionSide': position_side,
                'type': 'MARKET',
                'quantity': qty,
                # 'reduceOnly': reduce_only  <-- ELIMINADO: Causa error en Hedge Mode
            }
            order = self.client.futures_create_order(**params)
            return True, order
        except BinanceAPIException as e:
            return False, f"API Error: {e.message}"
        except Exception as e:
            return False, f"Net Error: {str(e)}"

    def place_stop_loss(self, side, position_side, stop_price):
        """
        Coloca orden STOP_MARKET para cierre de posición.
        """
        if self.cfg.MODE == 'SIMULATION': return True, {}
        
        try:
            order = self.client.futures_create_order(
                symbol=self.cfg.SYMBOL,
                side=side,
                positionSide=position_side,
                type='STOP_MARKET',
                stopPrice=str(stop_price),
                closePosition=True # Esto funciona correctamente en Hedge Mode
            )
            return True, order
        except Exception as e:
            return False, str(e)

    def cancel_all_orders(self):
        if self.cfg.MODE == 'SIMULATION': return
        try:
            self.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
        except: pass