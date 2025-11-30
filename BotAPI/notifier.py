import requests
import threading
import time
from colorama import Fore, Style

class TelegramNotifier:
    def __init__(self, config):
        self.cfg = config
        # Construcción de la URL base
        self.base_url = f"https://api.telegram.org/bot{self.cfg.TELEGRAM_TOKEN}/sendMessage"
        
        # Verificación simple para no intentar enviar si no hay datos
        self.enabled = self.cfg.TELEGRAM_ENABLED and \
                       self.cfg.TELEGRAM_TOKEN != 'TU_TOKEN_AQUI' and \
                       self.cfg.TELEGRAM_CHAT_ID != 'TU_CHAT_ID_AQUI'

    def enviar(self, mensaje, tipo="INFO"):
        """
        Envía mensaje en segundo plano para no bloquear el trading.
        """
        if not self.enabled: return

        # Decoración de mensajes con Emojis
        icono = "ℹ️"
        if tipo == "PROFIT": icono = "💰 <b>PROFIT!</b>"
        elif tipo == "LOSS": icono = "💀 <b>LOSS</b>"
        elif tipo == "OPEN": icono = "⚔️ <b>OPEN</b>"
        elif tipo == "ERROR": icono = "⚠️ <b>ERROR CRÍTICO</b>"
        elif tipo == "SYSTEM": icono = "🖥️ <b>SISTEMA</b>"
        
        texto_final = f"{icono}\n{mensaje}"

        # Lanzar en hilo separado
        t = threading.Thread(target=self._send_request, args=(texto_final,))
        t.start()

    def _send_request(self, texto):
        try:
            payload = {
                'chat_id': self.cfg.TELEGRAM_CHAT_ID,
                'text': texto,
                'parse_mode': 'HTML'
            }
            # Timeout corto (5s) para no colgar procesos si Telegram falla
            requests.post(self.base_url, data=payload, timeout=5)
        except Exception as e:
            print(f"{Fore.RED}[TELEGRAM ERROR] No se pudo enviar: {e}{Style.RESET_ALL}")