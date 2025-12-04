import csv
import os
import sys
from datetime import datetime
from config.config import Config

class SystemLogger:
    def __init__(self):
        self.cfg = Config()
        
        # 1. Forzar UTF-8 en la consola de Windows para evitar errores de print()
        if sys.platform == 'win32':
            try:
                sys.stdout.reconfigure(encoding='utf-8')
                sys.stderr.reconfigure(encoding='utf-8')
            except: pass

        self._check_files()

    def _check_files(self):
        if not os.path.exists(self.cfg.LOG_PATH):
            os.makedirs(self.cfg.LOG_PATH)
            
        if not os.path.exists(self.cfg.FILE_ERRORS):
            # IMPORTANTE: encoding='utf-8' para soportar emojis y caracteres especiales
            with open(self.cfg.FILE_ERRORS, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(['Timestamp', 'Modulo', 'Mensaje'])
                
        if not os.path.exists(self.cfg.FILE_ACTIVITY):
            # IMPORTANTE: encoding='utf-8'
            with open(self.cfg.FILE_ACTIVITY, 'w', encoding='utf-8') as f:
                f.write(f"--- INICIO BITÁCORA: {datetime.now()} ---\n")

    def log_error(self, modulo, mensaje):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            # Escritura segura en CSV con UTF-8
            with open(self.cfg.FILE_ERRORS, 'a', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([timestamp, modulo, str(mensaje)])
            
            # Impresión segura en consola
            print(f"!!! ERROR [{modulo}]: {mensaje}")
        except Exception as e:
            # Si falla el logueo, imprimimos un fallback simple sin emojis
            print(f"!!! LOGGING ERROR: {e}")

    def log_operational(self, modulo, mensaje):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f"[{timestamp}] [{modulo.upper()}] {mensaje}\n"
        try:
            # Escritura segura en archivo de texto con UTF-8
            with open(self.cfg.FILE_ACTIVITY, 'a', encoding='utf-8') as f:
                f.write(entry)
        except Exception:
            pass # Si falla el log operativo, no detenemos el bot