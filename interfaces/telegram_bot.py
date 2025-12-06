import threading
import time
import requests
import json
from datetime import datetime

class TelegramBot:
    """
    Interfaz de Control vía Telegram.
    Maneja comandos /start, /status, /panic, /balance en segundo plano.
    """
    def __init__(self, config, shooter, comptroller, order_manager, logger):
        self.cfg = config
        self.shooter = shooter
        self.comp = comptroller
        self.om = order_manager
        self.log = logger
        
        self.token = self.cfg.TELEGRAM_TOKEN
        self.chat_id = self.cfg.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/"
        
        self.running = False
        self.thread = None
        self.last_update_id = 0

    def iniciar(self):
        """Inicia el hilo de escucha de Telegram."""
        if not self.token:
            self.log.log_operational("TELEGRAM", "⚠️ Token no configurado. Bot desactivado.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.thread.start()
        self.log.log_operational("TELEGRAM", "Sistema de escucha iniciado.")
        self._send_msg(self.chat_id, "🤖 SENTINEL AI PRO: ONLINE\nSistemas listos. Esperando órdenes.")

    def detener(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _send_msg(self, chat_id, text):
        if not self.token or not chat_id: return
        try:
            url = self.base_url + "sendMessage"
            data = {"chat_id": chat_id, "text": text}
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            self.log.log_error("TELEGRAM", f"Fallo envío: {e}")

    def _get_updates(self):
        try:
            url = self.base_url + "getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 10}
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                result = resp.json().get("result", [])
                return result
        except: pass
        return []

    def _polling_loop(self):
        while self.running:
            try:
                updates = self._get_updates()
                for u in updates:
                    self.last_update_id = u["update_id"]
                    if "message" in u and "text" in u["message"]:
                        text = u["message"]["text"]
                        cid = u["message"]["chat"]["id"]
                        
                        # Seguridad: Solo responder al ID configurado
                        if str(cid) == str(self.chat_id):
                            self._procesar_comando(text, cid)
            except Exception as e:
                self.log.log_error("TELEGRAM", f"Error Polling: {e}")
                time.sleep(5)
            
            time.sleep(1)

    def _procesar_comando(self, text, chat_id):
        cmd = text.lower().strip()
        
        if cmd == "/start":
            self._send_msg(chat_id, "🛡️ Comandos Operativos:\n/status - Estado del Bot\n/balance - Capital Actual\n/panic - 🚨 Cierre de Emergencia")
            
        elif cmd == "/status":
            self._reportar_status(chat_id)
            
        elif cmd == "/panic":
            self._ejecutar_panico(chat_id)
            
        elif cmd == "/balance":
            cap = self.comp.fin.obtener_capital_total()
            self._send_msg(chat_id, f"💰 Capital Total: ${cap:.2f}")

    def _reportar_status(self, chat_id):
        pos = self.comp.positions
        if not pos:
            self._send_msg(chat_id, "💤 Sin posiciones activas. Escaneando mercado...")
            return

        msg = f"📊 REPORTE DE ESTADO:\nPosiciones Abiertas: {len(pos)}\n"
        for pid, record in pos.items():
            data = record['data']
            pnl = record.get('pnl_actual', 0.0)
            msg += f"🔹 {data['side']} {data['mode']} | PnL: ${pnl:.2f}\n"
        self._send_msg(chat_id, msg)

    def _ejecutar_panico(self, chat_id):
        """Cierra todas las posiciones registradas y cancela órdenes."""
        self._send_msg(chat_id, "🚨 EJECUTANDO PÁNICO... DETENIENDO OPERACIONES.")
        
        count = 0
        # Copia estática de claves para evitar error de iteración
        ids_activos = list(self.comp.positions.keys())
        
        for pid in ids_activos:
            if pid in self.comp.positions:
                record = self.comp.positions[pid]
                plan = record['data']
                
                # Cierre a mercado forzoso
                close_side = 'SELL' if plan['side'] == 'LONG' else 'BUY'
                
                try:
                    # Usamos conexión directa del Order Manager
                    self.om.conn.place_market_order(close_side, plan['side'], plan['qty'], reduce_only=True)
                except Exception as e:
                    self.log.log_error("TELEGRAM", f"Fallo cierre {pid}: {e}")
                
                # Borrar de memoria inmediatamente
                del self.comp.positions[pid]
                count += 1
            
        self.comp._guardar_estado() # Guardar estado vacío
        self.om.cancelar_todo() # Borrar SLs y TPs pendientes en Binance
        
        self._send_msg(chat_id, f"✅ Pánico completado. {count} posiciones liquidadas y órdenes canceladas.")