import csv
import os
import traceback
from datetime import datetime
from colorama import Fore, Style
from notifier import TelegramNotifier # NUEVO

class ErrorTracker:
    def __init__(self, config):
        self.cfg = config
        self.notifier = TelegramNotifier(config) # NUEVO
        self._inicializar()

    def _inicializar(self):
        if not os.path.exists(self.cfg.ERROR_LOG_FILE):
            with open(self.cfg.ERROR_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Fecha_Hora', 'Modulo', 'Tipo_Error', 'Mensaje', 'Traceback'])

    def registrar(self, modulo, excepcion, critico=False):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        tipo_error = type(excepcion).__name__
        mensaje = str(excepcion)
        trace = traceback.format_exc()
        
        color = Fore.RED if critico else Fore.YELLOW
        print(f"\n{color}!!! ERROR ({modulo}): {mensaje}{Style.RESET_ALL}")

        try:
            with open(self.cfg.ERROR_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, modulo, tipo_error, mensaje, trace])
        except Exception as e:
            print(f"FATAL: No se pudo loguear el error: {e}")

        # --- NUEVO: TELEGRAM ALERT ---
        if critico:
            msg = f"Módulo: {modulo}\nError: {mensaje}"
            self.notifier.enviar(msg, tipo="ERROR")