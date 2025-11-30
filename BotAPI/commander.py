import time
import threading
import requests
from colorama import Fore, Style

class TelegramCommander:
    def __init__(self, config, strategy_engine):
        self.cfg = config
        self.engine = strategy_engine 
        self.base_url = f"https://api.telegram.org/bot{self.cfg.TELEGRAM_TOKEN}"
        self.last_update_id = 0
        self.running = True

    def iniciar(self):
        """Arranca el hilo de escucha en segundo plano"""
        if not self.cfg.TELEGRAM_ENABLED: 
            print(f"{Fore.YELLOW}[TELEGRAM] Desactivado en Config.{Style.RESET_ALL}")
            return
        
        print(f"{Fore.CYAN}[TELEGRAM] Iniciando Comandante Remoto...{Style.RESET_ALL}")
        # Verificación inicial de conexión
        self._test_connection()
        
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def _test_connection(self):
        """Prueba si el Token es válido al iniciar"""
        try:
            url = f"{self.base_url}/getMe"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get('ok'):
                bot_name = data['result']['username']
                print(f"{Fore.GREEN}[TELEGRAM] Conectado exitosamente como @{bot_name}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[TELEGRAM ERROR] Token inválido o rechazado: {data}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[TELEGRAM ERROR] No hay conexión con API Telegram: {e}{Style.RESET_ALL}")

    def _poll_loop(self):
        """Bucle infinito que revisa mensajes nuevos"""
        errores_consecutivos = 0
        while self.running:
            try:
                updates = self._get_updates()
                if updates:
                    errores_consecutivos = 0 # Reset si hay éxito
                    for u in updates:
                        self._procesar_mensaje(u)
                time.sleep(1) 
            except Exception as e:
                errores_consecutivos += 1
                if errores_consecutivos < 3: # No llenar la pantalla de spam si se va el internet
                    print(f"[CMD ERROR] {e}")
                time.sleep(5)

    def _get_updates(self):
        url = f"{self.base_url}/getUpdates"
        params = {'offset': self.last_update_id + 1, 'timeout': 5}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get('ok'):
                return data.get('result', [])
            else:
                print(f"{Fore.RED}[TELEGRAM API] Error en respuesta: {data}{Style.RESET_ALL}")
        except Exception as e:
            # Quitamos el 'pass' para ver errores reales si ocurren
            # print(f"{Fore.RED}[TELEGRAM API] Fallo de red: {e}{Style.RESET_ALL}")
            pass # Mantenemos pass en loop para no ensuciar consola si se va internet momentaneo
        return []

    def _procesar_mensaje(self, update):
        self.last_update_id = update['update_id']
        
        if 'message' not in update: return
        msg = update['message']
        chat_id = str(msg.get('chat', {}).get('id'))
        texto = msg.get('text', '').strip().lower()
        usuario = msg.get('from', {}).get('username', 'Desconocido')

        print(f"{Fore.CYAN}[TELEGRAM MSG] De: {usuario} (ID: {chat_id}) | Texto: {texto}{Style.RESET_ALL}")

        # 🔒 SEGURIDAD CON LOGS
        # Comparamos como strings para evitar errores de tipo
        config_id = str(self.cfg.TELEGRAM_CHAT_ID).strip()
        
        if chat_id != config_id:
            print(f"{Fore.RED}[ALERTA] Acceso DENEGADO. ID Entrante: '{chat_id}' vs Config: '{config_id}'{Style.RESET_ALL}")
            self._responder(chat_id, "⛔ <b>ACCESO DENEGADO</b>: Tu ID no está autorizado.")
            return

        # --- LISTA DE COMANDOS ---
        
        # 1. ESTADO (/status)
        if texto == '/status':
            try:
                pos = self.engine.trader.posicion_abierta
                precio = self.engine.ultimo_precio
                estado = "🟢 <b>SISTEMA ONLINE</b>\n"
                estado += f"Precio Actual: <b>{precio}</b>\n"
                
                if pos:
                    pnl = (precio - pos['entrada']) * pos['cantidad']
                    if pos['tipo'] == 'SHORT': pnl *= -1
                    estado += f"\n⚠️ <b>POSICIÓN ACTIVA</b>\n"
                    estado += f"Tipo: {pos['tipo']} (x{pos['cantidad']})\n"
                    estado += f"Entrada: {pos['entrada']:.2f}\n"
                    estado += f"PnL: <b>{pnl:.2f} USDT</b>"
                else:
                    estado += "\n💤 Esperando oportunidad..."
                self._responder(chat_id, estado)
            except Exception as e:
                self._responder(chat_id, f"Error obteniendo estado: {e}")

        # 2. PÁNICO (/panic)
        elif texto == '/panic':
            self._responder(chat_id, "🚨 <b>EJECUTANDO CIERRE DE PÁNICO...</b>")
            self.engine.trader.cerrar_posicion_panico(self.engine.ultimo_precio)
            self.engine.trader.limpiar_ordenes_pendientes()

        # 3. RESTAURAR PROTECCIONES (/protect)
        elif texto == '/protect':
            self._responder(chat_id, "🛡️ <b>RESTAURANDO TP/SL...</b>")
            self.engine.trader.restaurar_protecciones_manual()
            self._responder(chat_id, "✅ Comando enviado.")

        # 4. LIMPIAR PENDIENTES (/clean)
        elif texto == '/clean':
            self._responder(chat_id, "🧹 <b>CANCELANDO ÓRDENES PENDIENTES...</b>")
            self.engine.trader.limpiar_ordenes_pendientes()

        # 5. ABRIR LONG (/long)
        elif texto == '/long':
            self._responder(chat_id, "🚀 <b>INTENTANDO LONG (Sniper)...</b>")
            self.engine._manual('LONG', 1)

        # 6. ABRIR SHORT (/short)
        elif texto == '/short':
            self._responder(chat_id, "📉 <b>INTENTANDO SHORT (Sniper)...</b>")
            self.engine._manual('SHORT', 1)
            
        # 7. AYUDA (/help)
        elif texto == '/help':
            ayuda = (
                "🤖 <b>COMANDOS DISPONIBLES:</b>\n\n"
                "/status - Ver PnL y Precio\n"
                "/panic - 🚨 CERRAR TODO\n"
                "/protect - 🛡️ Restaurar TP/SL perdidos\n"
                "/clean - 🧹 Borrar órdenes pendientes\n"
                "/long - Abrir Long (Limit)\n"
                "/short - Abrir Short (Limit)"
            )
            self._responder(chat_id, ayuda)

    def _responder(self, chat_id, texto):
        url = f"{self.base_url}/sendMessage"
        try:
            requests.post(url, data={'chat_id': chat_id, 'text': texto, 'parse_mode': 'HTML'})
        except Exception as e:
            print(f"[TELEGRAM ERROR] No pude responder: {e}")