import pandas as pd
import os
import time
from .calculator import MetricCalculator

class MetricsManager:
    def __init__(self, config, api_conn):
        self.cfg = config
        self.conn = api_conn
        self.calc = MetricCalculator()
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.cfg.LOG_PATH): os.makedirs(self.cfg.LOG_PATH)
        if not os.path.exists(self.cfg.FILE_METRICS):
            pd.DataFrame(columns=['ts','open','high','low','close','volume']).to_csv(self.cfg.FILE_METRICS, index=False)

    def sincronizar_y_calcular(self):
        last_ts = 0
        try:
            df = pd.read_csv(self.cfg.FILE_METRICS)
            if not df.empty: last_ts = float(df.iloc[-1]['ts'])
        except: pass

        now = time.time() * 1000
        limit_req = 1500 if (last_ts == 0 or (now - last_ts) > 86400000) else 100
        start_time = (last_ts + 60000) if last_ts > 0 else None
        
        data = self.conn.get_historical_candles(self.cfg.SYMBOL, '1m', limit=limit_req, start_time=start_time)
        
        if data:
            df_new = pd.DataFrame(data, columns=['ts','open','high','low','close','volume','x','y','z','w','v','u'])
            df_new = df_new[['ts','open','high','low','close','volume']].astype(float)
            mode = 'w' if limit_req == 1500 else 'a'
            df_new.to_csv(self.cfg.FILE_METRICS, mode=mode, header=(mode=='w'), index=False)
        
        try:
            df_full = pd.read_csv(self.cfg.FILE_METRICS).astype(float).tail(3000)
            return self.calc.generar_mtf_completo(df_full)
        except: return {}, {}