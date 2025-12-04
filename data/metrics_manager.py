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
            # Encoding utf-8 para compatibilidad universal
            pd.DataFrame(columns=['ts','open','high','low','close','volume']).to_csv(self.cfg.FILE_METRICS, index=False, encoding='utf-8')

    def sincronizar_y_calcular(self):
        last_ts = 0
        try:
            # Leemos solo la última línea para saber donde quedamos (rápido)
            with open(self.cfg.FILE_METRICS, 'r', encoding='utf-8') as f:
                last_line = f.readlines()[-1]
                if "ts" not in last_line:
                    last_ts = float(last_line.split(',')[0])
        except: pass

        # Lógica de descarga
        now = time.time() * 1000
        # Si falta mucha data (>24h), pedimos bloque grande (1500), si no, solo actualización (100)
        limit_req = 1500 if (last_ts == 0 or (now - last_ts) > 86400000) else 100
        start_time = (int(last_ts) + 60000) if last_ts > 0 else None
        
        data = self.conn.get_historical_candles(self.cfg.SYMBOL, '1m', limit=limit_req, start_time=start_time)
        
        if data:
            df_new = pd.DataFrame(data, columns=['ts','open','high','low','close','volume','x','y','z','w','v','u'])
            df_new = df_new[['ts','open','high','low','close','volume']].astype(float)
            mode = 'w' if limit_req == 1500 else 'a' # Si es carga masiva inicial, sobrescribimos
            header = (mode == 'w')
            df_new.to_csv(self.cfg.FILE_METRICS, mode=mode, header=header, index=False, encoding='utf-8')
        
        try:
            # --- CORRECCIÓN CRÍTICA AQUÍ ---
            # Antes: tail(3000) -> 50 horas (Insuficiente para 4H/1D)
            # Ahora: tail(50000) -> ~35 días. 
            # Suficiente para indicadores de 4H. Para 1D completo se requeriría más RAM,
            # pero 50,000 es un buen balance rendimiento/visibilidad.
            # NOTA: Para ver EMA200 de 1D necesitas 288,000 velas. Si tienes mucha RAM, aumenta este número.
            
            df_full = pd.read_csv(self.cfg.FILE_METRICS, encoding='utf-8').astype(float).tail(60000) 
            
            return self.calc.generar_mtf_completo(df_full)
        except Exception as e:
            print(f"Error calculando métricas: {e}")
            return {}, {}