import requests
import threading
import time
from colorama import Fore

class TelegramBot:
    def __init__(self, config, shooter, comptroller, order_manager, logger):
        self.cfg = config
        self.shooter = shooter
        self.comp = comptroller
        self.om = order_manager
        self.log = logger
        self.base_url = f"https://api.telegram.org/bot{self.cfg.TELEGRAM_TOKEN}"
        self.last_update_id = 0
        self.running = True

    def iniciar(self):
        if not self.cfg.TELEGRAM_TOKEN: return
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()
        self.log.log_operational("TELEGRAM", "Bot de Telegram escuchando comandos.")

    def _poll_loop(self):
        while self.running:
            try:
                updates = self._get_updates()
                for u in updates:
                    self._process_message(u)
                time.sleep(1)
            except Exception as e:
                time.sleep(5)

    def _get_updates(self):
        url = f"{self.base_url}/getUpdates"
        params = {'offset': self.last_update_id + 1, 'timeout': 5}
        try:
            r = requests.get(url, params=params, timeout=5)
            data = r.json()
            if data.get('ok'): return data.get('result', [])
        except: pass
        return []

    def _process_message(self, update):
        self.last_update_id = update['update_id']
        if 'message' not in update: return
        msg = update['message']
        text = msg.get('text', '').lower().strip()
        chat_id = str(msg.get('chat', {}).get('id'))
        
        # Seguridad de ID
        if chat_id != str(self.cfg.TELEGRAM_CHAT_ID): return

        self.log.log_operational("TELEGRAM", f"Comando recibido: {text}")

        if text == '/report':
            self._send_report(chat_id)
        elif text == '/long':
            self._send_msg(chat_id, "🚀 Procesando LONG Manual...")
            res = self.shooter.analizar_disparo('LONG', 0, 'MANUAL')
            self._send_response(chat_id, res)
        elif text == '/short':
            self._send_msg(chat_id, "📉 Procesando SHORT Manual...")
            res = self.shooter.analizar_disparo('SHORT', 0, 'MANUAL')
            self._send_response(chat_id, res)
        elif text == '/panic':
            self.comp.cerrar_todo_panico()
            self.om.cancelar_todas_ordenes()
            self._send_msg(chat_id, "🚨 PÁNICO EJECUTADO. Todo cerrado.")

    def _send_response(self, chat_id, res):
        if isinstance(res, dict):
            self._send_msg(chat_id, f"✅ Orden Ejecutada: {res['id']}")
        else:
            self._send_msg(chat_id, f"❌ Rechazado: {res}")

    def _send_report(self, chat_id):
        # Construir reporte
        pos_count = len(self.comp.positions)
        wallet = self.shooter.fin.obtener_capital_total()
        
        msg = f"📊 <b>REPORTE DE ESTADO</b>\n\n"
        msg += f"💰 Balance: {wallet:.2f} USDT\n"
        msg += f"💎 Posiciones Activas: {pos_count}\n"
        
        if pos_count > 0:
            for pid, pos in self.comp.positions.items():
                d = pos['data']
                pnl = pos.get('pnl_actual', 0)
                icon = "🟢" if pnl >= 0 else "🔴"
                msg += f"\n{icon} <b>{d['side']}</b> ({pid})\n"
                msg += f"Entrada: {d['entry_price']:.2f}\n"
                msg += f"PnL: {pnl:.2f} USDT\n"
                msg += f"Estado: {pos['status']}\n"
        else:
            msg += "\n<i>No hay posiciones activas.</i>"

        self._send_msg(chat_id, msg)

    def _send_msg(self, chat_id, text):
        url = f"{self.base_url}/sendMessage"
        try:
            requests.post(url, data={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'})
        except: pass