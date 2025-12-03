import json
import time
import os

class Comptroller:
    """
    CONTRALOR (COMPTROLLER)
    Responsabilidad: Custodia de posiciones, Gestión de TP/SL dinámicos y Auditoría de Estado.
    Características: Persistencia en Disco y Auto-corrección (Huérfanas/Fantasmas).
    """
    def __init__(self, config, order_manager, financials, logger):
        self.cfg = config
        self.om = order_manager
        self.fin = financials
        self.log = logger
        self.positions = {} # Memoria Volátil
        
        # Al iniciar, recuperamos la memoria desde el disco
        self._cargar_estado()

    # ==========================================================
    # 1. PERSISTENCIA DE ESTADO (MEMORIA EN DISCO)
    # ==========================================================
    def _cargar_estado(self):
        """Carga las posiciones activas desde el archivo JSON."""
        if os.path.exists(self.cfg.FILE_STATE):
            try:
                with open(self.cfg.FILE_STATE, 'r') as f:
                    self.positions = json.load(f)
                self.log.log_operational("CONTRALOR", f"Estado recuperado: {len(self.positions)} posiciones activas.")
            except Exception as e:
                self.log.log_error("CONTRALOR", f"Error cargando estado: {e}")
                self.positions = {}
        else:
            self.positions = {}

    def _guardar_estado(self):
        """Guarda el estado actual de las posiciones en JSON."""
        try:
            with open(self.cfg.FILE_STATE, 'w') as f:
                json.dump(self.positions, f, indent=4)
        except Exception as e:
            self.log.log_error("CONTRALOR", f"Error guardando estado: {e}")

    def registrar_posicion(self, paquete_confirmado):
        """Recibe una nueva posición confirmada del Gestor."""
        pid = paquete_confirmado['id']
        
        # Estructura de control enriquecida
        pos_record = {
            'data': paquete_confirmado,
            'tp_level_index': 0,      # Índice del siguiente TP a buscar
            'dca_count': 0,           # Contador de recompras
            'be_active': False,       # Flag de Breakeven
            'max_pnl_reached': 0.0,   # Para Trailing Stop futuro
            'status': 'RUNNING'
        }
        
        self.positions[pid] = pos_record
        self._guardar_estado() # Persistencia inmediata
        self.log.log_operational("CONTRALOR", f"Posición {pid} bajo custodia.")

    # ==========================================================
    # 2. CICLO LENTO (10s): SINCRONIZACIÓN CON REALIDAD
    # ==========================================================
    def sincronizar_estado_externo(self):
        """
        Consulta a Binance para verificar inconsistencias.
        Maneja 'Huérfanas' (Binance tiene, Yo no) y 'Fantasmas' (Yo tengo, Binance no).
        """
        if self.cfg.MODE == 'SIMULATION': return

        # Obtenemos posición neta real
        real_qty = 0.0
        real_entry = 0.0
        try:
            # Esta llamada debe estar en APIManager, asumimos que existe o accedemos al cliente
            # Para robustez, idealmente APIManager debería tener get_current_position()
            # Aquí usamos el cliente directo por simplicidad en el ejemplo, 
            # pero en producción usa conn.get_position_data()
            positions = self.om.conn.client.futures_position_information(symbol=self.cfg.SYMBOL)
            for p in positions:
                amt = float(p['positionAmt'])
                if amt != 0:
                    real_qty = amt
                    real_entry = float(p['entryPrice'])
                    break
        except Exception:
            return # Si falla la API, no tomamos decisiones drásticas

        net_memory_qty = sum([p['data']['qty'] * (1 if p['data']['side'] == 'LONG' else -1) for p in self.positions.values()])

        # CASO 1: FANTASMAS (Yo creo que tengo, pero Binance dice 0)
        # Significa que se cerró por SL o Liquidación fuera de mi control
        if len(self.positions) > 0 and real_qty == 0:
            self.log.log_operational("CONTRALOR", "⚠️ Detectado Cierre Externo (SL/Liquidación). Limpiando memoria.")
            self.positions.clear()
            self._guardar_estado()
            # Cancelamos cualquier orden pendiente por higiene
            self.om.cancelar_todo()

        # CASO 2: HUÉRFANAS (Binance tiene posición, Yo no)
        # Significa que reinicié y perdí el JSON, o puse una orden manual fuera del bot
        elif len(self.positions) == 0 and real_qty != 0:
            self.log.log_operational("CONTRALOR", f"⚠️ Detectada Posición Huérfana ({real_qty}). Adoptando...")
            self._adoptar_posicion_huerfana(real_qty, real_entry)

    def _adoptar_posicion_huerfana(self, qty, entry_price):
        """Crea un registro de emergencia para gestionar una posición encontrada."""
        side = 'LONG' if qty > 0 else 'SHORT'
        pid = f"ADOPTED_{int(time.time())}"
        
        # Reconstruimos un plan básico
        sl_pct = self.cfg.ShooterConfig.MODES['MANUAL']['stop_loss_pct']
        sl_price = entry_price * (1 - sl_pct) if side == 'LONG' else entry_price * (1 + sl_pct)
        
        dummy_plan = {
            'id': pid, 'side': side, 'qty': abs(qty), 
            'entry_price': entry_price, 'sl_price': sl_price,
            'mode': 'MANUAL', 'tps': [] # Sin TPs definidos, solo SL
        }
        
        # Nos aseguramos de ponerle un SL en Binance si no lo tiene
        sl_side = 'SELL' if side == 'LONG' else 'BUY'
        self.om.conn.place_stop_loss(sl_side, sl_price)
        
        self.registrar_posicion(dummy_plan)

    # ==========================================================
    # 3. CICLO RÁPIDO (1s): AUDITORÍA Y EJECUCIÓN TÁCTICA
    # ==========================================================
    def auditar_memoria(self, current_price, metrics_1m):
        """Revisa reglas de salida (TP, Trailing, BB) y ejecuta acciones."""
        if not self.positions or current_price is None: return

        # Iteramos sobre una copia para poder modificar el dict original
        for pid, record in list(self.positions.items()):
            plan = record['data']
            side = plan['side']
            mode = plan.get('mode', 'TREND')
            entry = plan['entry_price']
            
            # Cálculo de PnL no realizado
            pnl_pct = (current_price - entry) / entry if side == 'LONG' else (entry - current_price) / entry
            
            # --- LÓGICA DE TAKE PROFIT ---
            if mode == 'SCALP_BB':
                self._gestionar_salida_bb(pid, record, current_price, metrics_1m)
            else:
                self._gestionar_tp_fijo(pid, record, current_price)

            # --- LÓGICA DE BREAKEVEN (Protección de Ganancias) ---
            # Si supera 0.8% de ganancia, mover SL a entrada
            if not record['be_active'] and pnl_pct > 0.008:
                self._activar_breakeven(pid, record, entry, side)

    def _gestionar_tp_fijo(self, pid, record, current_price):
        """Verifica si el precio alcanzó los niveles de TP definidos."""
        plan = record['data']
        tps = plan.get('tps', [])
        idx = record['tp_level_index']
        
        if idx < len(tps):
            target = tps[idx]
            side = plan['side']
            
            hit = (side == 'LONG' and current_price >= target) or \
                  (side == 'SHORT' and current_price <= target)
            
            if hit:
                # Calcular cantidad a cerrar
                tp_splits = self.cfg.ShooterConfig.TP_SPLIT
                pct_to_close = tp_splits[idx] if idx < len(tp_splits) else 1.0
                
                self.log.log_operational("CONTRALOR", f"🎯 TP{idx+1} Alcanzado para {pid}")
                
                # Ejecutar cierre parcial
                if self.om.ejecutar_cierre_parcial(plan, pct_to_close):
                    record['tp_level_index'] += 1
                    # Actualizamos cantidad restante en memoria (aproximado)
                    plan['qty'] = plan['qty'] * (1 - pct_to_close)
                    self._guardar_estado()

    def _gestionar_salida_bb(self, pid, record, current_price, metrics):
        """Salida dinámica basada en Bandas de Bollinger para Scalping."""
        plan = record['data']
        side = plan['side']
        bb_upper = metrics.get('BB_UPPER', 0)
        bb_lower = metrics.get('BB_LOWER', 0)
        
        if bb_upper == 0: return # Faltan datos

        target = bb_upper if side == 'LONG' else bb_lower
        
        # Si el precio toca la banda opuesta, cerramos TODO
        hit = (side == 'LONG' and current_price >= target) or \
              (side == 'SHORT' and current_price <= target)
              
        if hit:
            self.log.log_operational("CONTRALOR", f"💥 Salida por Bandas (Scalp) para {pid}")
            close_side = 'SELL' if side == 'LONG' else 'BUY'
            self.om.conn.place_market_order(close_side, plan['qty'], reduce_only=True)
            del self.positions[pid] # Eliminamos de memoria
            self._guardar_estado()

    def _activar_breakeven(self, pid, record, entry_price, side):
        """Mueve el SL al precio de entrada para asegurar capital."""
        be_price = entry_price * 1.001 if side == 'LONG' else entry_price * 0.999
        sl_side = 'SELL' if side == 'LONG' else 'BUY'
        
        # Primero cancelamos SL anterior
        self.om.conn.client.futures_cancel_all_open_orders(symbol=self.cfg.SYMBOL)
        # Ponemos nuevo SL
        ok, _ = self.om.conn.place_stop_loss(sl_side, be_price)
        
        if ok:
            record['be_active'] = True
            record['data']['sl_price'] = be_price
            self._guardar_estado()
            self.log.log_operational("CONTRALOR", f"🛡️ Breakeven activado para {pid}")