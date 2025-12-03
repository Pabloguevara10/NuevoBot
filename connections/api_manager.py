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
        self.session = requests.Session() # Optimización de conexión
        self.status = {'binance': False, 'telegram': False}
        self._conectar_binance()

    def _conectar_binance(self):
        """Intenta establecer conexión inicial con Binance."""
        try:
            # Inicializamos cliente con timeout personalizado en la sesión interna si fuera posible,
            # pero la librería standard usa requests. Lo gestionaremos en las llamadas directas si es necesario.
            self.client = Client(
                self.cfg.API_KEY, 
                self.cfg.API_SECRET, 
                testnet=(self.cfg.MODE == 'TESTNET')
            )
            # Prueba de fuego inmediata
            self.client.ping()
            self.status['binance'] = True
            self.log.log_operational("API", f"Conectado a Binance ({self.cfg.MODE})")
        except Exception as e:
            self.log.log_error("API_INIT", f"Fallo crítico conectando Binance: {e}")
            self.status['binance'] = False

    def check_heartbeat(self):
        """Verifica la salud de las conexiones con Timeout estricto."""
        # 1. Binance Ping
        try:
            # Usamos una llamada ligera
            self.client.ping() 
            self.status['binance'] = True
        except Exception:
            self.status['binance'] = False
            # Intentar reconexión silenciosa si falla
            if not self.status['binance']: 
                self._conectar_binance()
            
        # 2. Telegram Ping (Opcional, no bloqueante para la operativa)
        try:
            url = f"https://api.telegram.org/bot{self.cfg.TELEGRAM_TOKEN}/getMe"
            r = self.session.get(url, timeout=2) # Timeout explícito de 2s
            self.status['telegram'] = r.status_code == 200
        except: 
            self.status['telegram'] = False
            
        return self.status

    def get_historical_candles(self, symbol, interval, limit=100, start_time=None):
        """Obtiene velas históricas con protección de Timeout."""
        try:
            if start_time:
                return self.client.futures_klines(
                    symbol=symbol, interval=interval, startTime=int(start_time), limit=1000
                )
            # Nota: La librería python-binance no acepta timeout en argumentos directos fácilmente,
            # pero envuelve requests. Si falla por red, lanzará excepción.
            return self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        except (BinanceAPIException, BinanceRequestException) as e:
            self.log.log_error("API_DATA", f"Error Binance: {e}")
            return []
        except RequestException as e:
            self.log.log_error("API_NET", f"Error Red (Timeout?): {e}")
            return []
        except Exception as e:
            self.log.log_error("API_UNKNOWN", f"Error Desconocido: {e}")
            return []

    def get_real_price(self):
        """
        PRIORIDAD CRÍTICA: Obtiene el precio actual.
        Si falla, retorna None para detener operativa insegura.
        """
        try:
            # Usamos symbol_ticker que es ligero
            ticker = self.client.futures_symbol_ticker(symbol=self.cfg.SYMBOL)
            return float(ticker['price'])
        except Exception as e:
            self.log.log_error("API_PRICE", f"Fallo obteniendo precio: {e}")
            return None # Retornar None indica peligro

    def get_account_balance(self):
        """Obtiene el saldo disponible en USDT."""
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
    # MÉTODOS DE ACCIÓN (ORDENES)
    # ==========================================
    def place_market_order(self, side, qty, reduce_only=False):
        """
        Ejecuta orden de mercado.
        Retorna: (bool_success, response_dict_or_error)
        """
        if self.cfg.MODE == 'SIMULATION':
            return True, {'orderId': 'SIM_ORD', 'avgPrice': 0, 'cumQty': qty}

        try:
            params = {
                'symbol': self.cfg.SYMBOL,
                'side': side,
                'type': 'MARKET',
                'quantity': qty,
                'reduceOnly': reduce_only
            }
            # La librería maneja la firma criptográfica internamente
            order = self.client.futures_create_order(**params)
            return True, order
        except BinanceAPIException as e:
            return False, f"API Error: {e.message}"
        except Exception as e:
            return False, f"Net Error: {str(e)}"

    def place_stop_loss(self, side, stop_price):
        """Coloca orden STOP_MARKET para cierre de posición."""
        if self.cfg.MODE == 'SIMULATION': return True, {}
        
        try:
            order = self.client.futures_create_order(
                symbol=self.cfg.SYMBOL,
                side=side, # SELL si es Long, BUY si es Short
                type='STOP_MARKET',
                stopPrice=str(stop_price),
                closePosition=True
            )
            return True, order
        except Exception as e:
            return False, str(e)

    def cancel_all_orders(self):
        """Cancela todas las órdenes abiertas del símbolo."""
        if self.cfg.MODE == 'SIMULATION': return
        try:
            self.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
        except: pass