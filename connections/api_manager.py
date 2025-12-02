import requests
from binance.client import Client

class APIManager:
    def __init__(self, config, logger):
        self.cfg = config
        self.log = logger
        self.client = None
        self.status = {'binance': False, 'telegram': False}
        self._conectar_binance()

    def _conectar_binance(self):
        try:
            self.client = Client(self.cfg.API_KEY, self.cfg.API_SECRET, testnet=(self.cfg.MODE == 'TESTNET'))
            self.client.ping()
            self.status['binance'] = True
        except Exception as e:
            self.log.log_error("API_MANAGER", f"Fallo al conectar Binance: {e}")
            self.status['binance'] = False

    def check_heartbeat(self):
        try:
            self.client.ping()
            self.status['binance'] = True
        except: self.status['binance'] = False
            
        try:
            url = f"https://api.telegram.org/bot{self.cfg.TELEGRAM_TOKEN}/getMe"
            r = requests.get(url, timeout=2)
            self.status['telegram'] = r.status_code == 200
        except: self.status['telegram'] = False
            
        return self.status

    def get_historical_candles(self, symbol, interval, limit=100, start_time=None):
        try:
            if start_time:
                return self.client.futures_klines(symbol=symbol, interval=interval, startTime=int(start_time), limit=1000)
            return self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        except Exception as e:
            self.log.log_error("API_DATA", f"Error descarga velas: {e}")
            return []

    def get_real_price(self):
        try:
            ticker = self.client.futures_symbol_ticker(symbol=self.cfg.SYMBOL)
            return float(ticker['price'])
        except: return 0.0
            
    def get_account_balance(self):
        if self.cfg.MODE == 'SIMULATION': return 1000.0
        try:
            info = self.client.futures_account_balance()
            for asset in info:
                if asset['asset'] == 'USDT': return float(asset['balance'])
        except: pass
        return 0.0