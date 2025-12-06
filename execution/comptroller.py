import json
import time
import os

class Comptroller:
    def __init__(self, config, order_manager, financials, logger):
        self.cfg = config
        self.om = order_manager
        self.fin = financials
        self.log = logger
        self.positions = {} 
        self._cargar_estado()

    def _cargar_estado(self):
        if os.path.exists(self.cfg.FILE_STATE):
            try:
                with open(self.cfg.FILE_STATE, 'r') as f:
                    self.positions = json.load(f)
            except: self.positions = {}

    def _guardar_estado(self):
        try:
            with open(self.cfg.FILE_STATE, 'w') as f:
                json.dump(self.positions, f, indent=4)
        except: pass

    def registrar_posicion(self, paquete):
        pid = paquete['id']
        record = {
            'data': paquete,
            'tp_level_index': 0,
            'be_active': False,
            'sl_order_id': paquete.get('sl_order_id'),
            'status': 'RUNNING',
            'pnl_actual': 0.0
        }
        self.positions[pid] = record
        self._guardar_estado()
        self.log.log_operational("CONTRALOR", f"Posición {pid} registrada.")

    def sincronizar_estado_externo(self):
        if self.cfg.MODE == 'SIMULATION': return
        try:
            raw_positions = self.om.conn.client.futures_position_information(symbol=self.cfg.SYMBOL)
            raw_orders = self.om.conn.client.futures_get_open_orders(symbol=self.cfg.SYMBOL)
        except: return

        real_positions = {}
        for p in raw_positions:
            amt = float(p['positionAmt'])
            if amt != 0:
                side = 'LONG' if amt > 0 else 'SHORT'
                real_positions[side] = {'qty': abs(amt), 'entry': float(p['entryPrice'])}

        active_order_ids = [o['orderId'] for o in raw_orders]

        # FASE A: Fantasmas
        for pid, record in list(self.positions.items()):
            side = record['data']['side']
            if side not in real_positions:
                self.log.log_operational("CONTRALOR", f"👻 Fantasma {pid}. Limpiando.")
                if record.get('sl_order_id'):
                    self.om.cancelar_orden_por_id(record['sl_order_id'])
                del self.positions[pid]
                self._guardar_estado()

        # FASE B: Huérfanas
        if len(self.positions) == 0 and len(real_positions) > 0:
            for side, info in real_positions.items():
                self.log.log_operational("CONTRALOR", f"⚠️ Huérfana {side}. Adoptando...")
                self._adoptar_posicion_huerfana(info['qty'], info['entry'], side)

        # FASE C: Auditoría de Protección
        for pid, record in self.positions.items():
            sl_id = record.get('sl_order_id')
            if sl_id not in active_order_ids:
                self.log.log_operational("CONTRALOR", f"🚨 Alerta: {pid} DESNUDA.")
                self._regenerar_proteccion(pid, record)

    def _regenerar_proteccion(self, pid, record):
        d = record['data']
        # CORRECCIÓN: Formatear precio antes de enviar
        sl_price = self.om.formatear_precio(d['sl_price'])
        side = d['side']
        sl_side = 'SELL' if side == 'LONG' else 'BUY'
        
        ok, resp = self.om.conn.place_stop_loss(sl_side, side, sl_price)
        if ok:
            new_id = resp.get('orderId')
            record['sl_order_id'] = new_id
            self.log.log_operational("CONTRALOR", f"✅ Protección restaurada {pid}. SL: {sl_price}")
            self._guardar_estado()
        else:
            self.log.log_error("CONTRALOR", f"Fallo restaurando protección: {resp}")

    def _adoptar_posicion_huerfana(self, qty, entry_price, side):
        pid = f"REC_{int(time.time())}"
        sl_pct = 0.02
        sl_price = entry_price * (1 - sl_pct) if side == 'LONG' else entry_price * (1 + sl_pct)
        plan = {
            'id': pid, 'side': side, 'qty': qty, 'entry_price': entry_price,
            'sl_price': sl_price, 'mode': 'MANUAL', 'tps': []
        }
        self.registrar_posicion(plan)

    def auditar_memoria(self, current_price, metrics_1m):
        if not self.positions or current_price is None: return

        for pid, record in list(self.positions.items()):
            plan = record['data']
            side = plan['side']
            entry = plan['entry_price']
            
            diff = (current_price - entry) if side == 'LONG' else (entry - current_price)
            record['pnl_actual'] = diff * plan['qty']

            self._gestionar_tp_fijo(pid, record, current_price)

            pnl_pct = (current_price - entry) / entry if side == 'LONG' else (entry - current_price) / entry
            if not record['be_active'] and pnl_pct > 0.008:
                self._activar_breakeven(pid, record, entry, side)

    def _gestionar_tp_fijo(self, pid, record, current_price):
        plan = record['data']
        tps = plan.get('tps', [])
        idx = record['tp_level_index']
        if idx < len(tps):
            target = tps[idx]
            side = plan['side']
            hit = (side == 'LONG' and current_price >= target) or \
                  (side == 'SHORT' and current_price <= target)
            if hit:
                pct = self.cfg.ShooterConfig.TP_SPLIT[idx]
                
                # --- [FIX CRÍTICO INTERÉS COMPUESTO] ---
                # 1. Calcular PnL Realizado
                qty_cerrada = plan['qty'] * pct
                pnl_realizado = (target - plan['entry_price']) * qty_cerrada if side == 'LONG' else (plan['entry_price'] - target) * qty_cerrada
                
                # 2. Ejecutar cierre en Exchange
                if self.om.ejecutar_cierre_parcial(plan, pct):
                    # 3. Registrar Ganancia en Billetera (Aquí estaba el fallo)
                    self.fin.registrar_pnl(pnl_realizado)
                    self.log.log_operational("CONTRALOR", f"💰 PnL Registrado y Sumado: ${pnl_realizado:.2f}")
                    
                    # 4. Actualizar memoria
                    record['tp_level_index'] += 1
                    plan['qty'] *= (1 - pct)
                    self._guardar_estado()

    def _activar_breakeven(self, pid, record, entry_price, side):
        # 1. Calcular precio BE
        raw_be_price = entry_price * 1.001 if side == 'LONG' else entry_price * 0.999
        # CORRECCIÓN: Formatear precio para que Binance no lo rechace
        be_price = self.om.formatear_precio(raw_be_price)
        
        sl_side = 'SELL' if side == 'LONG' else 'BUY'
        old_sl_id = record.get('sl_order_id')

        # 2. Intentar colocar NUEVO SL primero (Seguridad)
        ok, resp = self.om.conn.place_stop_loss(sl_side, side, be_price)
        
        if ok:
            # Si éxito, cancelamos el viejo y actualizamos estado
            if old_sl_id: self.om.cancelar_orden_por_id(old_sl_id)
            
            record['be_active'] = True
            record['data']['sl_price'] = be_price
            record['sl_order_id'] = resp.get('orderId')
            self._guardar_estado()
            self.log.log_operational("CONTRALOR", f"🛡️ Breakeven {pid} activado en {be_price}.")
        else:
            # Si falla, no hacemos nada (el viejo SL sigue protegiendo)
            self.log.log_error("CONTRALOR", f"Fallo activando BE {pid}: {resp}")