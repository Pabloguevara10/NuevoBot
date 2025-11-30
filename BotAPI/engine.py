import keyboard
import threading
from datetime import datetime
from modes import ScalpMode, SwingMode, MomentumMode
from execution import TradingManager
from pending_manager import PendingOrderManager 
from colorama import Fore, Style
import utils 

class StrategyEngine:
    def __init__(self, config, connector):
        self.cfg = config
        self.trader = TradingManager(config, connector)
        self.pending_mgr = PendingOrderManager(config) 
        self.COOLDOWN_SECONDS = 3 
        self.ultimo_precio = 0.0 
        self.scalp_mode = ScalpMode(config)
        self.swing_mode = SwingMode(config)
        self.mom_mode = MomentumMode(config)
        self.active_triggers = {} 
        self._start_keys()
        
    def _start_keys(self):
        def run():
            try:
                for i in range(1, 10):
                    keyboard.add_hotkey(f'c+{i}', lambda x=i: self._manual('LONG', x))
                    keyboard.add_hotkey(f'v+{i}', lambda x=i: self._manual('SHORT', x))
                keyboard.add_hotkey('z+x+0', lambda: self.trader.cerrar_posicion_panico(self.ultimo_precio))
                keyboard.add_hotkey('ctrl+l', lambda: self.trader.limpiar_ordenes_pendientes())
                keyboard.add_hotkey('ctrl+r', lambda: self.trader.restaurar_protecciones_manual())
                keyboard.add_hotkey('enter', self._activar_gatillo_manual)
                keyboard.add_hotkey('ctrl+o+p', self.pending_mgr.abrir_ventana_input)
                keyboard.wait() 
            except: pass
        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _manual(self, tipo, multi):
        """
        MODO FRANCOTIRADOR:
        Coloca orden LIMIT con desplazamiento de 0.03 a favor.
        Si no entra en 60s, se cancela (Manejado en execution.py).
        """
        p = self.ultimo_precio
        if p == 0: return
        
        # Desplazamiento fijo de 0.03 como solicitaste
        OFFSET = 0.03
        
        # LONG: Compro un poco más barato (Price - 0.03) o Marketable?
        # Si quieres asegurar entrada rapida pero Limit: Price + 0.03 (Cruce)
        # Si quieres esperar retroceso: Price - 0.03
        # Asumiré "Mejor precio" (Maker):
        limit_price = p - OFFSET if tipo == 'LONG' else p + OFFSET
        
        # Protecciones leídas desde config.py
        tp_offset_pct = self.cfg.MANUAL_TP_PCT 
        sl_pct = self.cfg.MANUAL_SL_PCT
        
        tp = limit_price * (1 + tp_offset_pct) if tipo=='LONG' else limit_price * (1 - tp_offset_pct)
        sl = limit_price * (1 - sl_pct) if tipo=='LONG' else limit_price * (1 + sl_pct)
        
        self.trader.abrir_orden(
            tipo, p, tp, sl, 
            f"MANUAL x{multi}", 0, 'MANUAL', 
            False, force_entry=True, 
            tipo_orden='LIMIT', 
            precio_limit=limit_price,
            permitir_stacking=True
        )

    def _activar_gatillo_manual(self):
        modos = [self.mom_mode, self.scalp_mode, self.swing_mode]
        for modo in modos:
            if modo.gatillo:
                self.trader.log_sistema(f"{Fore.MAGENTA}🔥 GATILLO FORZADO MANUALMENTE ({modo.name}){Style.RESET_ALL}")
                res, info = modo.gestionar_gatillo(None, self.ultimo_precio, 0, 0, 0, force_trigger=True)
                if res:
                    self.trader.abrir_orden(res, self.ultimo_precio, info['tp_final'], info['sl_price'], "MANUAL_TRIGGER", info['tp_mid'], modo.name)
                return

    def ejecutar_estrategia(self, mtf_data, precio):
        self.ultimo_precio = precio
        
        # 1. VERIFICAR ORDENES PENDIENTES (PRIORIDAD)
        orden_cercana = self.pending_mgr.verificar_proximidad(precio)
        if orden_cercana:
            pos = self.trader.posicion_abierta
            if pos and pos['strategy'] == 'PENDING_LIMIT':
                return "Gestionando LIMIT activa..."

            if pos and pos['strategy'] != 'PENDING_LIMIT':
                self.trader.log_sistema(f"{Fore.RED}🛑 CERRANDO SCALP/SWING POR PROXIMIDAD DE LIMIT{Style.RESET_ALL}")
                self.trader.forzar_cierre_por_jerarquia(precio, "PENDING_PRIORITY")
            
            self.trader.limpiar_ordenes_pendientes()
            self.trader.log_sistema(f"{Fore.YELLOW}🎯 COLOCANDO LIMIT PENDIENTE @ {orden_cercana['price']}{Style.RESET_ALL}")
            
            qty = utils.calcular_cantidad_ajustada(orden_cercana['price'], orden_cercana['amount'], self.trader.step_size)
            
            tp_dist = orden_cercana['price'] * 0.015 
            sl_dist = orden_cercana['price'] * 0.010 
            
            tp = orden_cercana['price'] + tp_dist if orden_cercana['type'] == 'LONG' else orden_cercana['price'] - tp_dist
            sl = orden_cercana['price'] - sl_dist if orden_cercana['type'] == 'LONG' else orden_cercana['price'] + sl_dist
            
            self.trader.abrir_orden(
                orden_cercana['type'], precio, tp, sl, "PENDING_ACTIVATION", 0, 
                'PENDING_LIMIT', force_entry=True, tipo_orden='LIMIT', precio_limit=orden_cercana['price']
            )
            
            self.pending_mgr.desactivar_orden(orden_cercana['id'])
            return f"🎯 EJECUTANDO LIMIT {orden_cercana['type']}"

        # 2. GESTIONAR POSICIONES ABIERTAS (NO SE BLOQUEA POR CIRCUIT BREAKER)
        pos_actual = self.trader.posicion_abierta
        res = self.trader.verificar_salidas(precio)
        if res: return f"Gestionando: {res}"

        # 3. VERIFICAR CORTACIRCUITOS (Solo si no hay posición)
        if not pos_actual:
            bloqueado, msg_status, pnl_hoy = self.trader.verificar_estado_diario()
            if bloqueado:
                return f"⏸️ {msg_status}"

        # 4. ESTRATEGIAS AUTOMÁTICAS
        est_activa = pos_actual.get('strategy') if pos_actual else None
        
        self.active_triggers = {}
        if self.mom_mode.gatillo: self.active_triggers['MOMENTUM'] = self.mom_mode.gatillo['tipo']
        if self.scalp_mode.gatillo: self.active_triggers['SCALP'] = self.scalp_mode.gatillo['tipo']
        if self.swing_mode.gatillo: self.active_triggers['SWING'] = self.swing_mode.gatillo['tipo']

        if self.trader.last_closure_time and (datetime.now() - self.trader.last_closure_time).total_seconds() < self.COOLDOWN_SECONDS:
            return "Cooldown..."

        d_mom = mtf_data.get('1m', {})
        d_mom_f = mtf_data.get('5m', {})
        d_scalp = mtf_data.get('15m', {})
        d_scalp_f = mtf_data.get('1h', {})
        d_swing = mtf_data.get('1h', {})
        d_swing_f = mtf_data.get('4h', {})

        swing_sig, swing_info = self.swing_mode.evaluar(d_swing, d_swing_f)
        if swing_sig:
            if est_activa and est_activa != 'SWING':
                self.trader.forzar_cierre_por_jerarquia(precio, 'SWING')
                pos_actual = None; est_activa = None
            if not est_activa:
                self.trader.abrir_orden(swing_sig, precio, swing_info['tp_final'], swing_info['sl_price'], swing_info['motivo'], swing_info['tp_mid'], 'SWING')
                return f"👑 ENTRADA SWING {swing_sig}"

        scalp_sig, scalp_info = self.scalp_mode.evaluar(d_scalp, d_scalp_f)
        if scalp_sig:
            if est_activa == 'MOMENTUM':
                self.trader.forzar_cierre_por_jerarquia(precio, 'SCALP')
                pos_actual = None; est_activa = None
            if not est_activa:
                self.trader.abrir_orden(scalp_sig, precio, scalp_info['tp_final'], scalp_info['sl_price'], scalp_info['motivo'], scalp_info['tp_mid'], 'SCALP')
                return f"⚔️ DISPARO SCALP {scalp_sig}"

        mom_sig, mom_info = self.mom_mode.evaluar(d_mom, d_mom_f)
        if mom_sig and not est_activa:
            self.trader.abrir_orden(mom_sig, precio, mom_info['tp_final'], mom_info['sl_price'], mom_info['motivo'], mom_info['tp_mid'], 'MOMENTUM')
            return f"🚀 MOMENTUM {mom_sig}"

        return "Escaneo Jerárquico..."