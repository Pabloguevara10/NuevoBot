import uuid
import time
# Opcional: from tools.precision_lab import PrecisionLab as Lab

class Shooter:
    def __init__(self, config, financials, order_manager, comptroller, logger):
        self.cfg = config
        self.fin = financials
        self.om = order_manager
        self.comp = comptroller
        self.log = logger

    def ejecutar_senal(self, senal):
        mode = senal['mode']
        side = senal['side']
        price = senal['price']
        
        # 1. Validaciones
        if len(self.comp.positions) >= self.cfg.MAX_OPEN_POSITIONS:
            return "⛔ Max Posiciones."
        active = [p['data']['mode'] for p in self.comp.positions.values()]
        if mode in active and mode != 'MANUAL': return f"⛔ Modo {mode} ocupado."
        
        ok, msg = self.fin.puedo_operar()
        if not ok and mode != 'MANUAL': return msg

        # 2. Configuración
        mode_cfg = self.cfg.ShooterConfig.MODES.get(mode, self.cfg.ShooterConfig.MODES['MANUAL'])
        capital = self.fin.obtener_capital_total()
        margin = capital * mode_cfg['wallet_pct']
        qty = round((margin * self.cfg.LEVERAGE) / price, 3)
        
        if qty <= 0: return "⛔ Cantidad 0."

        # 3. Stop Loss
        sl_price = senal.get('sl_ref', 0.0)
        if sl_price == 0.0:
            pct = mode_cfg['stop_loss_pct']
            sl_price = price * (1 - pct) if side == 'LONG' else price * (1 + pct)

        # 4. Take Profit Inteligente (Laddering)
        tps = []
        target_final = senal.get('structural_target')
        
        if target_final and mode == 'TREND_FOLLOWING':
            # Si hay objetivo estructural, construimos escalera hacia él
            dist = abs(target_final - price)
            if dist/price > 0.005: # Solo si vale la pena (>0.5%)
                tp1 = price + ((target_final - price) * 0.33)
                tp2 = price + ((target_final - price) * 0.66)
                tps = [tp1, tp2, target_final]
            else:
                tps = [price * (1 + (d * (1 if side=='LONG' else -1))) for d in self.cfg.ShooterConfig.TP_DISTANCES]
        else:
            # Fallback a fijos
            mult = 1 if side == 'LONG' else -1
            tps = [price * (1 + (d * mult)) for d in self.cfg.ShooterConfig.TP_DISTANCES]

        # 5. Ejecutar
        plan = {
            'id': str(uuid.uuid4())[:8].upper(),
            'side': side, 'mode': mode, 'qty': qty,
            'sl_price': sl_price, 'tps': tps,
            'leverage': self.cfg.LEVERAGE, 'timestamp': time.time()
        }
        
        ok, res = self.om.ejecutar_estrategia(plan)
        if ok:
            self.comp.registrar_posicion(res)
            return f"✅ ORDEN {res['id']} EJECUTADA"
        return f"❌ {res}"