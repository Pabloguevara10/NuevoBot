import time

class Comptroller:
    def __init__(self, config, order_manager, financials, logger):
        self.cfg = config
        self.om = order_manager
        self.fin = financials
        self.log = logger
        self.positions = {} 

    def registrar_posicion(self, plan):
        if not plan: return
        self.positions[plan['id']] = {
            'data': plan,
            'tp_level': 0,
            'dca_applied': False,
            'be_active': False,
            'status': 'CUSTODIA',
            'pnl_actual': 0.0
        }
        self.log.log_operational("CONTRALOR", f"Posición {plan['id']} registrada en Bitácora.")

    # --- FUNCIÓN LENTA (Llamar cada 10s) ---
    def sincronizar_estado_externo(self, current_price):
        """
        Solo esta función tiene permiso de consultar a Binance para buscar
        posiciones huérfanas o validar inconsistencias.
        """
        if self.cfg.MODE == 'SIMULATION': return

        # Consultar realidad
        real_qty, real_entry = self.om.obtener_posicion_real()
        
        # 1. DETECCIÓN DE HUÉRFANAS (Binance tiene, Yo no)
        if real_qty != 0 and len(self.positions) == 0:
            side = 'LONG' if real_qty > 0 else 'SHORT'
            qty_abs = abs(real_qty)
            pid = f"REC_{int(time.time())}"
            
            self.log.log_operational("CONTRALOR", f"⚠️ Sincronización: Detectada posición no registrada ({side}). Adoptando...")
            
            # Crear registro de emergencia
            sl_dist = current_price * 0.02
            sl_price = (current_price - sl_dist) if side == 'LONG' else (current_price + sl_dist)
            
            plan_adopcion = {
                'id': pid, 'side': side, 'qty': qty_abs,
                'entry_price': real_entry if real_entry > 0 else current_price,
                'sl': sl_price, 'tps': [], 'mode': 'SCALP_BB',
                'usdt_value': qty_abs * current_price, 'leverage': self.cfg.LEVERAGE
            }
            self.registrar_posicion(plan_adopcion)
            
            # Proteger
            self.om.cancelar_todas_ordenes()
            self._mover_sl_dinamico(plan_adopcion, sl_price)

        # 2. VALIDACIÓN DE FANTASMAS (Yo tengo, Binance no)
        # Si tengo posición en memoria, pero Binance dice 0, debo limpiar.
        if len(self.positions) > 0 and real_qty == 0:
            self.log.log_operational("CONTRALOR", "Sincronización: La posición ya no existe en Binance. Limpiando bitácora.")
            self.positions.clear()
            self.om.cancelar_todas_ordenes()

    # --- FUNCIÓN RÁPIDA (Llamar cada 1s) ---
    def auditar_memoria(self, current_price, mtf_data):
        """
        Calcula PnL, TP y SL basándose EXCLUSIVAMENTE en la Bitácora local.
        No hace consultas de lectura a Binance.
        Solo llama al Gestor si necesita EJECUTAR una acción.
        """
        metrics = mtf_data.get('1m', {})
        if not metrics: return

        for pid, pos in list(self.positions.items()):
            d = pos['data']
            side = d['side']
            mode = d.get('mode', 'TREND')
            
            # Cálculo Matemático Local
            diff = (current_price - d['entry_price']) if side == 'LONG' else (d['entry_price'] - current_price)
            pos['pnl_actual'] = diff * d['qty']

            # Estrategias (Lógica Pura)
            if mode == 'SCALP_BB':
                self._gestionar_acorralamiento(pid, pos, current_price, metrics)
            else:
                self._gestionar_tp_fijo(pid, pos, current_price)

            if self.cfg.DCA_ENABLED and not pos['dca_applied']:
                self._gestionar_dca(pid, pos, current_price, metrics)

            # Verificación de SL (Matemática)
            self._verificar_sl_local(pid, pos, current_price)

    # --- SUB-RUTINAS DE GESTIÓN ---
    def cerrar_todo_panico(self):
        self.log.log_operational("CONTRALOR", "EJECUTANDO CIERRE DE PÁNICO.")
        if not self.positions: return
        for pid, pos in list(self.positions.items()):
            d = pos['data']
            close_side = 'SELL' if d['side'] == 'LONG' else 'BUY'
            self.om.forzar_cierre_mercado(close_side, d['qty'])
            del self.positions[pid]
        self.log.log_operational("CONTRALOR", "Cartera limpia.")

    def restaurar_seguridad(self):
        self.log.log_operational("CONTRALOR", "Restaurando SL...")
        self.om.cancelar_todas_ordenes()
        if not self.positions: return
        for pid, pos in self.positions.items():
            d = pos['data']
            self._mover_sl_dinamico(d, d['sl'])

    def _mover_sl_dinamico(self, data, new_price):
        if self.cfg.MODE == 'SIMULATION': return True
        try:
            # Acción de Escritura (Necesaria)
            self.om.conn.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
            sl_action_side = 'SELL' if data['side'] == 'LONG' else 'BUY'
            self.om.conn.client.futures_create_order(
                symbol=self.cfg.SYMBOL, side=sl_action_side, positionSide=data['side'],
                type='STOP_MARKET', stopPrice="{:.2f}".format(new_price), closePosition=True
            )
            data['sl'] = new_price
            self.log.log_operational("CONTRALOR", f"Stop Loss actualizado a {new_price:.2f}")
            return True
        except: return False

    def _gestionar_acorralamiento(self, pid, pos, current_price, metrics):
        d = pos['data']
        side = d['side']
        bb_mid = metrics.get('BB_MID', 0)
        bb_upper = metrics.get('BB_UPPER', 0)
        bb_lower = metrics.get('BB_LOWER', 0)
        if bb_mid == 0: return

        if pos['tp_level'] == 0:
            tocado = (side == 'LONG' and current_price >= bb_mid) or \
                     (side == 'SHORT' and current_price <= bb_mid)
            if tocado:
                qty_close = d['qty'] * 0.50
                self.log.log_operational("CONTRALOR", f"{pid} tocó BB MEDIA. Cerrando 50%.")
                self.om.ejecutar_cierre_parcial(pid, qty_close, current_price)
                be_price = d['entry_price'] * (1.001 if side == 'LONG' else 0.999)
                self._mover_sl_dinamico(d, be_price)
                self.fin.registrar_pnl(pos['pnl_actual'] * 0.5)
                pos['tp_level'] = 1
                pos['be_active'] = True
                pos['status'] = "BB_MID (B/E)"

        elif pos['tp_level'] == 1:
            target = bb_upper if side == 'LONG' else bb_lower
            tocado = (side == 'LONG' and current_price >= target) or \
                     (side == 'SHORT' and current_price <= target)
            if tocado:
                self.log.log_operational("CONTRALOR", f"{pid} tocó BB OPUESTA. Cerrando total.")
                qty_close = d['qty'] * 0.5 
                self.om.forzar_cierre_mercado(d['side'] == 'LONG' and 'SELL' or 'BUY', qty_close)
                self.fin.registrar_pnl(pos['pnl_actual'] * 0.5)
                self.om.cancelar_todas_ordenes()
                del self.positions[pid]

    def _gestionar_tp_fijo(self, pid, pos, current_price):
        d = pos['data']
        next_tp_idx = pos['tp_level']
        if next_tp_idx < len(d['tps']):
            target = d['tps'][next_tp_idx]
            side = d['side']
            hit = (side == 'LONG' and current_price >= target) or (side == 'SHORT' and current_price <= target)
            if hit:
                pct = self.cfg.TP_SPLIT[next_tp_idx]
                qty_close = d['qty'] * pct
                self.om.ejecutar_cierre_parcial(pid, qty_close, current_price)
                self.fin.registrar_pnl(abs(d['entry_price'] - target) * qty_close)
                pos['tp_level'] += 1
                pos['status'] = f"TP{pos['tp_level']} ALCANZADO"

    def _gestionar_dca(self, pid, pos, current_price, metrics):
        d = pos['data']
        dist_total_sl = abs(d['entry_price'] - d['sl'])
        dist_recorrida = abs(d['entry_price'] - current_price)
        is_losing = pos['pnl_actual'] < 0
        
        if is_losing and dist_total_sl > 0:
            pct_recorrido = dist_recorrida / dist_total_sl
            if pct_recorrido >= self.cfg.DCA_TRIGGER_DIST:
                rsi = metrics.get('RSI', 50)
                indicators_ok = False
                if d['side'] == 'LONG' and rsi < 40: indicators_ok = True
                if d['side'] == 'SHORT' and rsi > 60: indicators_ok = True
                
                if indicators_ok:
                    self.log.log_operational("CONTRALOR", f"ALERTA DCA {pid}.")
                    exito = self.om.ejecutar_dca(d, current_price)
                    if exito:
                        pos['dca_applied'] = True
                        pos['status'] = "DCA APLICADO"
                        d['entry_price'] = (d['entry_price'] + current_price) / 2
                        d['qty'] *= 2

    def _verificar_sl_local(self, pid, pos, current_price):
        """Verifica SL usando solo matemáticas locales. Si toca, asume cierre."""
        d = pos['data']
        side = d['side']
        sl_hit = (side == 'LONG' and current_price <= d['sl']) or (side == 'SHORT' and current_price >= d['sl'])
        
        if sl_hit:
            self.log.log_operational("CONTRALOR", f"PRECIO TOCÓ SL ({pid}). Asumiendo cierre por protección.")
            # No llamamos a Binance. Asumimos que la orden STOP_MARKET que pusimos al inicio funcionó.
            # Limpiamos nuestra memoria.
            self.fin.registrar_pnl(pos['pnl_actual'])
            del self.positions[pid]
            # La limpieza real de órdenes huerfanas ocurrirá en el ciclo lento de 10s