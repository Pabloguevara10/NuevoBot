import csv
import os
import time
from datetime import datetime
from colorama import Fore, Style
import utils
from errors import ErrorTracker
from notifier import TelegramNotifier 

class TradingStats:
    def __init__(self, connector):
        self.conn = connector
        self.start_ts_ms = int(time.time() * 1000)
        self.start_dt = datetime.now()
        self.total_trades = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0

    def registrar(self, tipo, pnl, estrategia):
        self.total_trades += 1
        if pnl > 0: self.gross_profit += pnl
        else: self.gross_loss += abs(pnl)

class TradingManager:
    def __init__(self, config, connector):
        self.cfg = config
        self.conn = connector 
        self.step_size = connector.step_size
        
        # --- ESTADOS ---
        self.posicion_abierta = None  # Posición confirmada en Binance
        self.orden_espera = None      # Orden Limit enviada, esperando llenarse
        
        self.last_closure_time = None
        self.stats = TradingStats(connector)
        self.error_tracker = ErrorTracker(config)
        self.notifier = TelegramNotifier(config) 
        self.notificaciones = [] 
        self._inicializar_bitacora()
        if self.cfg.MODE in ['TESTNET', 'LIVE']: 
            self._sincronizar_estado_inteligente()

    def log_sistema(self, mensaje):
        self.notificaciones.append((time.time(), mensaje))

    def obtener_notificaciones_activas(self):
        now = time.time()
        self.notificaciones = [n for n in self.notificaciones if now - n[0] < 10]
        return [n[1] for n in self.notificaciones]

    def _inicializar_bitacora(self):
        if not os.path.exists(self.cfg.TRADES_FILE):
            with open(self.cfg.TRADES_FILE, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(['Fecha', 'Estrategia', 'Tipo', 'Entrada', 'Qty', 'Monto', 'Salida', 'PnL', 'Motivo', 'Estado'])

    def _escribir_bitacora(self, datos):
        try:
            with open(self.cfg.TRADES_FILE, 'a', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(datos)
        except: pass

    # --- CORTACIRCUITOS DIARIO ---
    def verificar_estado_diario(self):
        if not self.cfg.ENABLE_CIRCUIT_BREAKER: 
            return False, "OK", 0.0
        
        hoy = datetime.now().strftime('%Y-%m-%d')
        pnl_acumulado = 0.0
        
        if os.path.exists(self.cfg.TRADES_FILE):
            try:
                with open(self.cfg.TRADES_FILE, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        fecha = row.get('Fecha', '') or row.get('Fecha_Hora', '')
                        if fecha.startswith(hoy):
                            try:
                                val_pnl = float(row.get('PnL', 0) or row.get('PnL_USDT', 0))
                                pnl_acumulado += val_pnl
                            except: pass
            except: pass
        
        if pnl_acumulado <= (self.cfg.MAX_DAILY_LOSS_USDT * -1):
            return True, f"🛑 STOP LOSS DIARIO ({pnl_acumulado:.2f})", pnl_acumulado
            
        if pnl_acumulado >= self.cfg.TARGET_DAILY_PROFIT_USDT:
            return True, f"🎉 META DIARIA LOGRADA ({pnl_acumulado:.2f})", pnl_acumulado
            
        return False, "OPERATIVO", pnl_acumulado

    # --- HERRAMIENTAS MANUALES ---
    def limpiar_ordenes_pendientes(self):
        # NOTA: Si hay una orden de espera (Limit de aumento), esto la cancelará.
        self.log_sistema(f"{Fore.YELLOW}🧹 Limpiando órdenes...{Style.RESET_ALL}")
        self.conn.cancelar_todas_ordenes()
        self.orden_espera = None
        
        # Si teníamos posición abierta, al limpiar órdenes borramos su SL/TP.
        # Debemos intentar restaurar la protección de la posición base inmediatamente.
        if self.posicion_abierta:
            self.log_sistema(f"{Fore.CYAN}🛡️ Restaurando protección de posición base...{Style.RESET_ALL}")
            self.restaurar_protecciones_manual()

    def restaurar_protecciones_manual(self):
        pos = self.conn.obtener_posicion_abierta()
        if not pos or float(pos['positionAmt']) == 0: 
            self.log_sistema("⚠️ No hay posición para proteger.")
            return

        qty = abs(float(pos['positionAmt']))
        entry = float(pos['entryPrice'])
        tipo = 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT'
        
        sl_pct = self.cfg.MANUAL_SL_PCT
        tp_pct = self.cfg.MANUAL_TP_PCT
        
        sl = entry * (1 - sl_pct) if tipo == 'LONG' else entry * (1 + sl_pct)
        tp = entry * (1 + tp_pct) if tipo == 'LONG' else entry * (1 - tp_pct)
        
        side_cierre = 'SELL' if tipo == 'LONG' else 'BUY'
        pos_side = 'LONG' if tipo == 'LONG' else 'SHORT'
        
        self.conn.cancelar_todas_ordenes()
        self.conn.colocar_orden_sl_tp(side_cierre, qty, sl, pos_side, 'STOP_MARKET')
        self.conn.colocar_orden_sl_tp(side_cierre, qty, tp, pos_side, 'TAKE_PROFIT_MARKET')
        
        self.posicion_abierta = {
            'tipo': tipo, 'entrada': entry, 'cantidad': qty,
            'tp': tp, 'sl': sl, 'strategy': 'MANUAL_RESTORED',
            'break_even_activado': False, 'best_price': entry
        }
        self.log_sistema(f"{Fore.GREEN}✅ Protecciones Restauradas.{Style.RESET_ALL}")

    def _sincronizar_estado_inteligente(self):
        pos = self.conn.obtener_posicion_abierta()
        if pos and float(pos['positionAmt']) != 0:
            self.posicion_abierta = {
                'tipo': 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT',
                'entrada': float(pos['entryPrice']),
                'cantidad': abs(float(pos['positionAmt'])),
                'sl': 0, 'tp': 0,
                'strategy': 'RECOVERED',
                'break_even_activado': False,
                'best_price': float(pos['entryPrice'])
            }

    # --- PASO 1: COLOCAR LA ORDEN (LÓGICA CONSOLIDACIÓN) ---
    def abrir_orden(self, tipo, precio_ref, tp_final, sl, motivo, tp_mid, estrategia='SCALP', force_entry=False, tipo_orden='MARKET', precio_limit=0.0, permitir_stacking=False):
        
        # 1. Verificar si estamos CONSOLIDANDO (Mismo sentido)
        es_consolidacion = False
        if self.posicion_abierta:
            if self.posicion_abierta['tipo'] == tipo:
                es_consolidacion = True
                self.log_sistema(f"{Fore.CYAN}➕ CONSOLIDANDO: Agregando capital a posición {tipo} existente...{Style.RESET_ALL}")
            elif not force_entry:
                self.log_sistema(f"{Fore.YELLOW}⚠️ Ignorando orden {tipo}: Ya existe posición contraria.{Style.RESET_ALL}")
                return # Sentido contrario y no forzado: Ignorar
            else:
                # Sentido contrario y forzado: Cerrar anterior (Flip)
                self.log_sistema(f"{Fore.YELLOW}🔄 FLIP: Cerrando posición contraria para entrar en {tipo}.{Style.RESET_ALL}")
                self._cerrar_orden_logica("FLIP_DIRECTION", precio_ref, force_market=True)

        # 2. Gestión de Órdenes Pendientes
        # Si NO es consolidación, limpiamos todo antes de entrar
        if not es_consolidacion:
            self.conn.cancelar_todas_ordenes()
        # Si ES consolidación, MANTENEMOS los SL/TP actuales hasta que la nueva orden entre
        # (Binance permite tener Limit Orders + SL/TP activos simultáneamente)

        # 3. Cálculo de Capital
        capital = self.cfg.CAPITAL_TRABAJO
        if self.cfg.ENABLE_COMPOUND:
            bal = self.conn.obtener_saldo_usdt()
            if bal > 10: capital = bal
            
        leverage = self.cfg.LEVERAGE_SWING if estrategia == 'SWING' else self.cfg.LEVERAGE_SCALP
        pct = self.cfg.SIZE_SWING if estrategia == 'SWING' else self.cfg.SIZE_SCALP
        qty = utils.calcular_cantidad_ajustada(precio_ref, capital * pct * leverage, self.step_size)
        
        if qty == 0: return

        side, pos_side = ('BUY', 'LONG') if tipo == 'LONG' else ('SELL', 'SHORT')
        
        self.log_sistema(f"{Fore.MAGENTA}🚀 ENVIANDO ORDEN {tipo} ({tipo_orden})...{Style.RESET_ALL}")
        
        orden = None
        if tipo_orden == 'MARKET':
            orden = self.conn.colocar_orden_market(side, qty, pos_side)
        else:
            orden = self.conn.colocar_orden_limit(side, qty, precio_limit, pos_side)

        if orden:
            # REGISTRAR ESPERA
            # Guardamos los parámetros de protección que QUEREMOS aplicar al TOTAL
            # una vez que esta orden se consolide con la existente.
            self.orden_espera = {
                'id': orden.get('orderId'),
                'tipo': tipo,
                'estrategia': estrategia,
                'sl_deseado': sl, # Este SL se aplicará al monto consolidado
                'tp_deseado': tp_final,
                'timestamp': time.time()
            }
            self.log_sistema(f"{Fore.YELLOW}⏳ Orden Enviada. Esperando consolidación...{Style.RESET_ALL}")

    # --- PASO 2 Y 3: VERIFICAR Y PROTEGER (LÓGICA ESTRICTA) ---
    def verificar_salidas(self, precio_actual):
        pos_binance = None
        if self.cfg.MODE in ['TESTNET', 'LIVE']:
            pos_binance = self.conn.obtener_posicion_abierta()
        
        # B. DETECCIÓN DE CAMBIO: ¿Se llenó la orden de espera?
        if self.orden_espera:
            # CASO 1: Ya teníamos posición y ahora aumentó (Consolidación)
            if self.posicion_abierta and pos_binance:
                qty_ant = self.posicion_abierta['cantidad']
                qty_nueva = abs(float(pos_binance['positionAmt']))
                
                # Si la cantidad aumentó, significa que la orden entró
                if qty_nueva > qty_ant:
                    self.log_sistema(f"{Fore.GREEN}✅ CONSOLIDACIÓN COMPLETADA (Qty: {qty_ant} -> {qty_nueva}){Style.RESET_ALL}")
                    self._activar_posicion_real(pos_binance) # Re-protegemos el total
            
            # CASO 2: No teníamos posición y ahora sí (Entrada nueva)
            elif not self.posicion_abierta and pos_binance and float(pos_binance['positionAmt']) != 0:
                self._activar_posicion_real(pos_binance)
            
            # CASO 3: Timeout (60s)
            elif (time.time() - self.orden_espera['timestamp']) > 60:
                self.log_sistema(f"{Fore.RED}🗑️ Orden Limit expirada. Cancelando.{Style.RESET_ALL}")
                
                # Si es consolidación, NO cancelamos TODO (borraríamos el SL de la posición base).
                # Solo cancelamos la orden Limit específica si tenemos el ID.
                # Como la API de 'cancelar_orden' requiere ID, intentamos eso.
                # Si no, cancelamos todo y restauramos.
                oid = self.orden_espera['id']
                exito = self.conn.cancelar_orden(oid)
                
                if not exito: 
                    # Si falla cancelación individual, limpieza agresiva y restauración
                    self.conn.cancelar_todas_ordenes()
                    if self.posicion_abierta: self.restaurar_protecciones_manual()
                
                self.orden_espera = None

        # C. DETECCIÓN DE CIERRE EXTERNO
        if self.posicion_abierta and self.cfg.MODE in ['TESTNET', 'LIVE']:
            if not pos_binance:
                self._cerrar_orden_logica("TP/SL_BINANCE", precio_actual)
                return "CERRADO"

        # D. GESTIÓN DE B/E Y TRAILING
        if self.posicion_abierta:
            return self._gestionar_riesgo_activo(precio_actual)
            
        return None

    def _activar_posicion_real(self, pos_data):
        # Esta función se llama cuando se confirma un cambio de posición (Nueva o Aumentada)
        
        qty_real = abs(float(pos_data['positionAmt']))
        entry_real = float(pos_data['entryPrice'])
        
        sl = self.orden_espera['sl_deseado']
        tp = self.orden_espera['tp_deseado']
        tipo = self.orden_espera['tipo']
        strat = self.orden_espera['estrategia']
        
        side_cierre = 'SELL' if tipo == 'LONG' else 'BUY'
        pos_side = 'LONG' if tipo == 'LONG' else 'SHORT'
        
        # Primero limpiamos órdenes viejas (SL/TP anteriores o Limits huerfanas)
        self.conn.cancelar_todas_ordenes()
        
        self.log_sistema(f"{Fore.CYAN}🛡️ Actualizando TP/SL para Total: {qty_real} monedas...{Style.RESET_ALL}")
        self.conn.colocar_orden_sl_tp(side_cierre, qty_real, sl, pos_side, 'STOP_MARKET')
        self.conn.colocar_orden_sl_tp(side_cierre, qty_real, tp, pos_side, 'TAKE_PROFIT_MARKET')
        
        self.posicion_abierta = {
            'tipo': tipo, 'entrada': entry_real, 'cantidad': qty_real,
            'tp': tp, 'sl': sl, 'strategy': strat,
            'break_even_activado': False, 'best_price': entry_real
        }
        self.orden_espera = None 
        
        self._escribir_bitacora([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'), strat, tipo, 
            f"{entry_real}", f"{qty_real}", "0", "0", "0", "CONSOLIDACION", "OPEN"
        ])

    def _gestionar_riesgo_activo(self, precio):
        pos = self.posicion_abierta
        changed = False; msg = None
        
        if not pos['break_even_activado']:
            pnl_bruto = (precio - pos['entrada']) * pos['cantidad']
            if pos['tipo'] == 'SHORT': pnl_bruto *= -1
            
            if pnl_bruto >= self.cfg.MIN_NET_PROFIT_USDT:
                new_sl = pos['entrada'] * (1.002 if pos['tipo']=='LONG' else 0.998)
                
                self.log_sistema(f"{Fore.BLUE}🔒 Activando B/E Seguro...{Style.RESET_ALL}")
                
                if self.cfg.MODE in ['TESTNET', 'LIVE']:
                    pos_real = self.conn.obtener_posicion_abierta()
                    if not pos_real: return 
                    
                    qty_real = abs(float(pos_real['positionAmt']))
                    
                    self.conn.cancelar_todas_ordenes()
                    
                    side_cierre = 'SELL' if pos['tipo'] == 'LONG' else 'BUY'
                    pos_side = 'LONG' if pos['tipo'] == 'LONG' else 'SHORT'
                    
                    res = self.conn.colocar_orden_sl_tp(side_cierre, qty_real, new_sl, pos_side, 'STOP_MARKET')
                    self.conn.colocar_orden_sl_tp(side_cierre, qty_real, pos['tp'], pos_side, 'TAKE_PROFIT_MARKET')
                    
                    if res:
                        pos['sl'] = new_sl
                        pos['break_even_activado'] = True
                        msg = "B/E ACTIVADO"
                    else:
                        self.log_sistema(f"{Fore.RED}⚠️ Falló B/E. Revertiendo SL...{Style.RESET_ALL}")
                        self.conn.colocar_orden_sl_tp(side_cierre, qty_real, pos['sl'], pos_side, 'STOP_MARKET')
                else:
                    pos['break_even_activado'] = True 
                    
        return msg

    def forzar_cierre_por_jerarquia(self, precio, nueva_estrategia):
        if self.posicion_abierta:
            self.log_sistema(f"{Fore.YELLOW}🔄 Cambio de Prioridad: {nueva_estrategia} desplaza a actual.{Style.RESET_ALL}")
            self._cerrar_orden_logica(f"OVERRIDE_{nueva_estrategia}", precio)

    def cerrar_posicion_panico(self, precio):
        if self.posicion_abierta:
            self._cerrar_orden_logica("PANIC_USER", precio, force_market=True)

    def _cerrar_orden_logica(self, motivo, precio, force_market=False):
        if not self.posicion_abierta: return
        
        pos = self.posicion_abierta
        
        if force_market and self.cfg.MODE in ['TESTNET', 'LIVE']:
            p_real = self.conn.obtener_posicion_abierta()
            qty = abs(float(p_real['positionAmt'])) if p_real else pos['cantidad']
            self.conn.colocar_orden_market('SELL' if pos['tipo']=='LONG' else 'BUY', qty, 'LONG' if pos['tipo']=='LONG' else 'SHORT')
            self.conn.cancelar_todas_ordenes()

        pnl = (precio - pos['entrada']) * pos['cantidad']
        if pos['tipo'] == 'SHORT': pnl *= -1
        
        self.stats.registrar(pos['tipo'], pnl, pos['strategy'])
        self.log_sistema(f"{Fore.GREEN if pnl>0 else Fore.RED}🏁 CERRADO {motivo} | PnL: {pnl:.2f}{Style.RESET_ALL}")
        
        self.notifier.enviar(f"Cierre: {motivo}\nPnL: {pnl:.2f}", "PROFIT" if pnl>0 else "LOSS")
        self.posicion_abierta = None
        self.orden_espera = None