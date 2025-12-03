import uuid
import time

class Shooter:
    """
    TIRADOR (SHOOTER) - Módulo de Ejecución Táctica
    Responsabilidad: Validar riesgo, calcular tamaño de posición y emitir orden de ejecución.
    Transforma una 'Señal' (del Brain) en un 'Plan de Tiro' (para el OrderManager).
    """
    def __init__(self, config, financials, order_manager, comptroller, logger):
        self.cfg = config
        self.fin = financials
        self.om = order_manager
        self.comp = comptroller
        self.log = logger

    def ejecutar_senal(self, senal):
        """
        Recibe una señal {side, mode, price, [sl_ref]} y coordina la ejecución.
        """
        mode = senal['mode']
        side = senal['side']
        price = senal['price']
        
        # 1. VERIFICACIÓN DE SLOTS (¿Tengo cupo?)
        # Evitamos abrir múltiples operaciones del mismo tipo
        active_modes = [p['data']['mode'] for p in self.comp.positions.values()]
        
        if len(self.comp.positions) >= self.cfg.MAX_OPEN_POSITIONS:
            return "⛔ Máximo de posiciones alcanzado."
        
        if mode in active_modes and mode != 'MANUAL':
            return f"⛔ Ya existe una operación {mode} activa."

        # 2. VERIFICACIÓN DE CAPITAL (Financials)
        ok_fin, msg_fin = self.fin.puedo_operar()
        if not ok_fin and mode != 'MANUAL':
            return f"⛔ Capital insuficiente: {msg_fin}"

        # 3. CÁLCULO DE TAMAÑO (RISK MANAGEMENT)
        # Obtenemos la configuración específica para este modo
        mode_cfg = self.cfg.ShooterConfig.MODES.get(mode, self.cfg.ShooterConfig.MODES['MANUAL'])
        
        capital_total = self.fin.obtener_capital_total()
        margin_usdt = capital_total * mode_cfg['wallet_pct']
        
        # Ajuste de cantidad por apalancamiento
        # Qty = (Margen * Leverage) / Precio
        raw_qty = (margin_usdt * self.cfg.LEVERAGE) / price
        
        # Redondear cantidad a la precisión soportada (simplificado a 3 decimales, idealmente dinámico)
        qty_asset = round(raw_qty, 3)
        
        if qty_asset <= 0: return "⛔ Cantidad calculada cero."

        self.log.log_operational("TIRADOR", f"Preparando {side} ({mode}). Margen: {margin_usdt:.1f} USDT")

        # 4. DEFINICIÓN DE STOP LOSS Y TAKE PROFIT
        # Si la estrategia provee un nivel de referencia (ej. FVG Bottom), lo usamos.
        # Si no, usamos porcentaje fijo.
        sl_price = 0.0
        
        if 'sl_ref' in senal:
            # SL Estructural
            sl_price = senal['sl_ref']
        else:
            # SL Porcentual
            dist_pct = mode_cfg['stop_loss_pct']
            sl_dist = price * dist_pct
            sl_price = (price - sl_dist) if side == 'LONG' else (price + sl_dist)

        # Cálculo de TPs (Objetivos fijos para el Contralor)
        tps = []
        mult = 1 if side == 'LONG' else -1
        for dist in self.cfg.ShooterConfig.TP_DISTANCES:
            tp_price = price * (1 + (dist * mult))
            tps.append(tp_price)

        # 5. CONSTRUCCIÓN DEL PLAN DE TIRO
        plan = {
            'id': str(uuid.uuid4())[:8].upper(),
            'side': side,
            'mode': mode,
            'qty': qty_asset,
            'sl_price': sl_price,  # El OrderManager necesita esto para la orden de protección
            'tps': tps,            # El Comptroller necesita esto para gestionar salidas
            'leverage': self.cfg.LEVERAGE,
            'timestamp': time.time()
        }

        # 6. TRANSFERENCIA DE MANDO AL GESTOR (HANDOVER)
        # Llamamos al OrderManager para que ejecute la 'Regla de Oro'
        exito, resultado = self.om.ejecutar_estrategia(plan)
        
        if exito:
            # Si el gestor tuvo éxito, registramos la posición en el Contralor
            self.comp.registrar_posicion(resultado)
            return f"✅ EJECUTADO: {resultado['id']}"
        else:
            return f"❌ FALLO EJECUCIÓN: {resultado}"