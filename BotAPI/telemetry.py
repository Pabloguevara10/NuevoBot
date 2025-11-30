import csv
import os
import time
from datetime import datetime

class DataLogger:
    def __init__(self, config):
        self.cfg = config
        self.last_log_time = 0
        self._inicializar()

    def _inicializar(self):
        if not os.path.exists(self.cfg.TELEMETRY_FILE):
            with open(self.cfg.TELEMETRY_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                headers = [
                    'Timestamp', 'Precio', 'Accion_Bot', 'Posicion_Actual',
                    'RSI_1m', 'Stoch_1m', 'BB_Width_1m', 'BB_Pos_1m', 'Vol_1m',
                    'RSI_5m', 'Stoch_5m', 'BB_Width_5m', 'BB_Pos_5m', 'Vol_5m',
                    'RSI_15m', 'Stoch_15m', 'BB_Width_15m', 'BB_Pos_15m',
                    'Velocidad_Precio'
                ]
                writer.writerow(headers)

    def registrar_telemetria(self, precio, mtf_data, msg_estrategia, posicion_actual, momentum_speed):
        now = time.time()
        if now - self.last_log_time < self.cfg.TELEMETRY_INTERVAL: return

        try:
            d1 = mtf_data.get('1m', {})
            d5 = mtf_data.get('5m', {})
            d15 = mtf_data.get('15m', {})
            
            pos_str = "NINGUNA"
            if posicion_actual:
                pos_str = f"{posicion_actual['tipo']} ({posicion_actual['strategy']})"

            row = [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                f"{precio:.2f}",
                msg_estrategia,
                pos_str,
                f"{d1.get('RSI',0):.1f}", f"{d1.get('STOCH_RSI',0):.1f}", f"{d1.get('BB_WIDTH',0):.2f}", d1.get('BB_POS','-'), f"{d1.get('VOL_SCORE',0):.1f}",
                f"{d5.get('RSI',0):.1f}", f"{d5.get('STOCH_RSI',0):.1f}", f"{d5.get('BB_WIDTH',0):.2f}", d5.get('BB_POS','-'), f"{d5.get('VOL_SCORE',0):.1f}",
                f"{d15.get('RSI',0):.1f}", f"{d15.get('STOCH_RSI',0):.1f}", f"{d15.get('BB_WIDTH',0):.2f}", d15.get('BB_POS','-'),
                f"{momentum_speed:+.4f}%"
            ]
            
            with open(self.cfg.TELEMETRY_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
                
            self.last_log_time = now
        except Exception as e:
            print(f"[LOGGER ERROR] {e}")