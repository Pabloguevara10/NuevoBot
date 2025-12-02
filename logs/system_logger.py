import csv
import os
from datetime import datetime
from config.config import Config

class SystemLogger:
    def __init__(self):
        self.cfg = Config()
        self._check_files()

    def _check_files(self):
        if not os.path.exists(self.cfg.LOG_PATH):
            os.makedirs(self.cfg.LOG_PATH)
            
        if not os.path.exists(self.cfg.FILE_ERRORS):
            with open(self.cfg.FILE_ERRORS, 'w', newline='') as f:
                csv.writer(f).writerow(['Timestamp', 'Modulo', 'Mensaje'])
                
        if not os.path.exists(self.cfg.FILE_ACTIVITY):
            with open(self.cfg.FILE_ACTIVITY, 'w') as f:
                f.write(f"--- INICIO BITÁCORA: {datetime.now()} ---\n")

    def log_error(self, modulo, mensaje):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(self.cfg.FILE_ERRORS, 'a', newline='') as f:
            csv.writer(f).writerow([timestamp, modulo, mensaje])
        print(f"!!! ERROR [{modulo}]: {mensaje}")

    def log_operational(self, modulo, mensaje):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f"[{timestamp}] [{modulo.upper()}] {mensaje}\n"
        try:
            with open(self.cfg.FILE_ACTIVITY, 'a', encoding='utf-8') as f:
                f.write(entry)
        except: pass