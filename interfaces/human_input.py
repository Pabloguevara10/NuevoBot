import keyboard
import time
import threading
from colorama import Fore, Style

class HumanInput:
    def __init__(self, config, shooter, order_manager, comptroller, logger):
        self.cfg = config
        self.shooter = shooter
        self.om = order_manager
        self.comp = comptroller
        self.log = logger
        self.running = True

    def iniciar(self):
        """Arranca el listener en un hilo separado"""
        t = threading.Thread(target=self._listen_loop, daemon=True)
        t.start()
        self.log.log_operational("HIM", "Módulo de Intervención Manual (Teclado) Activo.")

    def _listen_loop(self):
        # 1. DISPAROS MANUALES (Space + L / Space + S)
        # Nota: Usamos una lambda para pasar los argumentos
        keyboard.add_hotkey('space+l', lambda: self._manual_trigger('LONG'))
        keyboard.add_hotkey('space+s', lambda: self._manual_trigger('SHORT'))

        # 2. PÁNICO (z + x + 0) - Cierre Total Inmediato
        keyboard.add_hotkey('z+x+0', self._panic_sequence)

        # 3. BORRAR ÓRDENES PENDIENTES (b + o)
        keyboard.add_hotkey('b+o', self._clean_orders)

        # 4. RESTAURAR PROTECCIONES (r + o)
        keyboard.add_hotkey('r+o', self._restore_protections)

        # Mantener el hilo vivo
        while self.running:
            time.sleep(1)

    def _manual_trigger(self, side):
        print(f"\n{Fore.CYAN}⌨️  COMANDO MANUAL DETECTADO: {side}{Style.RESET_ALL}")
        self.log.log_operational("MANUAL", f"Usuario solicitó entrada {side} vía Teclado.")
        
        # Enviamos price=0 para que el Shooter busque el precio real actual
        # mode='MANUAL' activa la gestión de riesgo al 5%
        res = self.shooter.analizar_disparo(side, 0, mode='MANUAL')
        
        # Feedback en consola inmediato
        if isinstance(res, dict):
             print(f"{Fore.GREEN}>> ORDEN EJECUTADA: {res['id']}{Style.RESET_ALL}")
        else:
             print(f"{Fore.RED}>> RECHAZADO: {res}{Style.RESET_ALL}")

    def _panic_sequence(self):
        print(f"\n{Fore.RED}🚨 SECUENCIA DE PÁNICO INICIADA (Z+X+0){Style.RESET_ALL}")
        self.log.log_operational("MANUAL", "!!! PÁNICO ACTIVADO POR USUARIO !!!")
        
        # 1. Cancelar todas las órdenes pendientes en el Exchange
        self.om.cancelar_todas_ordenes()
        
        # 2. Cerrar todas las posiciones abiertas a mercado
        self.comp.cerrar_todo_panico()

    def _clean_orders(self):
        print(f"\n{Fore.YELLOW}🧹 Limpiando órdenes pendientes (B+O)...{Style.RESET_ALL}")
        self.log.log_operational("MANUAL", "Usuario solicitó limpieza de órdenes (B+O).")
        self.om.cancelar_todas_ordenes()

    def _restore_protections(self):
        print(f"\n{Fore.GREEN}🛡️ Restaurando protecciones (R+O)...{Style.RESET_ALL}")
        self.log.log_operational("MANUAL", "Usuario solicitó restaurar protecciones (R+O).")
        self.comp.restaurar_seguridad()