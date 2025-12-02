import uuid

class Shooter:
    def __init__(self, config, financials, order_manager, comptroller, logger):
        self.cfg = config
        self.fin = financials
        self.om = order_manager
        self.comp = comptroller
        self.log = logger

    def analizar_disparo(self, side, price, mode, stop_loss_ref=None):
        if price == 0: price = self.om.conn.get_real_price()
        
        # SLOTS
        active_modes = [p['data']['mode'] for p in self.comp.positions.values()]
        if mode == 'SNIPER_FVG' and 'SNIPER_FVG' in active_modes: return "⛔ Slot FVG lleno."
        if mode in ['TREND', 'SCALP_BB'] and ('TREND' in active_modes or 'SCALP_BB' in active_modes): return "⛔ Slot Táctico lleno."

        # CAPITAL
        ok, msg = self.fin.puedo_operar()
        if not ok and mode != 'MANUAL': return msg
        
        capital = self.fin.obtener_capital_total()
        pct = self.cfg.MAX_WALLET_PCT_FVG if mode == 'SNIPER_FVG' else self.cfg.MAX_WALLET_PCT_REVERSAL
        if mode == 'TREND': pct = self.cfg.MAX_WALLET_PCT_TREND
        
        margin_usdt = capital * pct
        qty_asset = (margin_usdt * self.cfg.LEVERAGE) / price
        
        self.log.log_operational("TIRADOR", f"AUTORIZADO {side} ({mode}). Margen: {margin_usdt:.2f}")

        # SL / TP
        if stop_loss_ref:
            sl_price = stop_loss_ref * 0.998 if side == 'LONG' else stop_loss_ref * 1.002
        else:
            sl_dist = price * self.cfg.SL_DISTANCE_PCT
            sl_price = (price - sl_dist) if side == 'LONG' else (price + sl_dist)
            
        tps = []
        mult = 1 if side == 'LONG' else -1
        for d in self.cfg.TP_DISTANCES: tps.append(price * (1 + (d * mult)))

        plan = {
            'id': str(uuid.uuid4())[:8].upper(),
            'side': side, 'qty': qty_asset, 'entry_price': price,
            'sl': sl_price, 'tps': tps, 'mode': mode, 'leverage': self.cfg.LEVERAGE
        }
        return self.om.ejecutar_plan(plan)