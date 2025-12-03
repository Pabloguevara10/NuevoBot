import requests
import threading
import time

class TelegramBot:
    """
    INTERFACE TELEGRAM
    Permite control remoto y monitoreo.
    Ahora integrado con el flujo seguro del Shooter y Comptroller.
    """
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
        if not self.cfg.TELEGRAM_TOKEN: 
            self.log.log_operational("TELEGRAM", "Token no configurado. Bot desactivado.")
            return
            
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()
        self.log.log_operational("TELEGRAM", "Escuchando comandos...")

    def _poll_loop(self):
        while self.running:
            try:
                updates = self._get_updates()
                for u in updates:
                    self._process_message(u)
                time.sleep(1)
            except Exception as e:
                # Errores de red en Telegram no deben tumbar el bot principal
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

        self.log.log_operational("TELEGRAM", f"CMD Recibido: {text}")

        if text == '/report':
            self._send_report(chat_id)
            
        elif text in ['/long', '/short']:
            # EJECUCIÓN MANUAL SEGURA
            side = 'LONG' if text == '/long' else 'SHORT'
            self._send_msg(chat_id, f"🔄 Procesando {side} Manual...")
            
            # Obtenemos precio actual para la señal
            price = self.om.conn.get_real_price()
            if not price:
                self._send_msg(chat_id, "❌ Error obteniendo precio. Intente de nuevo.")
                return

            # Creamos una señal manual sintética
            senal_manual = {
                'side': side,
                'mode': 'MANUAL',
                'price': price
                # Nota: MANUAL usa stop_loss_pct del config, no necesita sl_ref
            }
            
            # Pasamos la señal al Shooter (él valida capital, slots, etc.)
            res = self.shooter.ejecutar_senal(senal_manual)
            self._send_msg(chat_id, res)

        elif text == '/panic':
            self._ejecutar_panico(chat_id)
            
        elif text == '/help':
            help_msg = (
                "🤖 <b>COMANDOS SENTINEL V2</b>\n"
                "/report - Estado de cuenta y posiciones\n"
                "/long - Abrir LONG (Gestión Manual)\n"
                "/short - Abrir SHORT (Gestión Manual)\n"
                "/panic - 🚨 CERRAR TODO INMEDIATAMENTE"
            )
            self._send_msg(chat_id, help_msg)

    def _ejecutar_panico(self, chat_id):
        """Cierra todas las posiciones registradas y cancela órdenes."""
        self._send_msg(chat_id, "🚨 EJECUTANDO PÁNICO...")
        
        count = 0
        # Iteramos sobre una copia de las claves para poder modificar el dict
        ids_to_remove = []
        
        for pid, record in self.comp.positions.items():
            plan = record['data']
            # Cierre a mercado
            close_side = 'SELL' if plan['side'] == 'LONG' else 'BUY'
            self.om.conn.place_market_order(close_side, plan['qty'], reduce_only=True)
            ids_to_remove.append(pid)
            count += 1
            
        # Limpieza de memoria y órdenes pendientes
        for pid in ids_to_remove:
            del self.comp.positions[pid]
            
        self.comp._guardar_estado() # Actualizar JSON vacio
        self.om.cancelar_todo()
        
        self._send_msg(chat_id, f"✅ Pánico completado. {count} posiciones cerradas.")

    def _send_report(self, chat_id):
        # Construir reporte basado en la MEMORIA DEL CONTRALOR
        pos_count = len(self.comp.positions)
        wallet = self.shooter.fin.obtener_capital_total()
        
        msg = f"📊 <b>REPORTE SENTINEL V2</b>\n\n"
        msg += f"💰 Balance: {wallet:.2f} USDT\n"
        msg += f"🛡️ Posiciones Activas: {pos_count}\n"
        
        if pos_count > 0:
            current_price = self.om.conn.get_real_price() or 0
            
            for pid, record in self.comp.positions.items():
                d = record['data']
                entry = d['entry_price']
                side = d['side']
                qty = d['qty']
                
                # Estimación rápida de PnL
                if current_price > 0:
                    diff = (current_price - entry) if side == 'LONG' else (entry - current_price)
                    pnl_est = diff * qty
                    icon = "🟢" if pnl_est >= 0 else "🔴"
                    pnl_str = f"{pnl_est:.2f} USDT"
                else:
                    icon = "⚪"
                    pnl_str = "Calc..."

                msg += f"\n{icon} <b>{side}</b> | {d['mode']}\n"
                msg += f"Entrada: {entry:.2f}\n"
                msg += f"PnL Aprox: {pnl_str}\n"
                msg += f"Estado: TP Level {record['tp_level_index']} | BE: {'Sí' if record['be_active'] else 'No'}\n"
        else:
            msg += "\n<i>💤 Sistema en espera de oportunidades...</i>"

        self._send_msg(chat_id, msg)

    def _send_msg(self, chat_id, text):
        url = f"{self.base_url}/sendMessage"
        try:
            requests.post(url, data={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}, timeout=2)
        except: pass