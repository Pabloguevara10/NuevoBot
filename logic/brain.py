import pandas as pd
import os
import time

class Brain:
    def __init__(self, config, shooter, logger):
        self.cfg = config
        self.shooter = shooter
        self.log = logger
        self.gatillo_armado = None
        self.fvg_db = []
        self.last_fvg_reload = 0
        self._cargar_fvgs()

    def _cargar_fvgs(self):
        try:
            path = os.path.join(self.cfg.LOG_PATH, 'fvg_registry.csv')
            if os.path.exists(path):
                self.fvg_db = pd.read_csv(path).to_dict('records')
                self.log.log_operational("CEREBRO", f"FVG DB: {len(self.fvg_db)} zonas.")
            else: self.fvg_db = []
        except: pass

    def procesar_mercado(self, metrics, current_price):
        if not metrics: return None
        if time.time() - self.last_fvg_reload > 60:
            self._cargar_fvgs()
            self.last_fvg_reload = time.time()

        # Datos
        ema_200 = metrics.get('EMA_200', 0)
        rsi = metrics.get('RSI', 50)
        stoch = metrics.get('STOCH_RSI', 50)
        adx = metrics.get('ADX', 0)
        
        # 1. FVG SCAN (Estratégico)
        for z in self.fvg_db:
            if z['Type'] == 'LONG' and z['Bottom'] <= current_price <= z['Top']:
                if stoch < 30: 
                    return self.shooter.analizar_disparo('LONG', current_price, 'SNIPER_FVG', stop_loss_ref=z['Bottom'])
            elif z['Type'] == 'SHORT' and z['Top'] >= current_price >= z['Bottom']:
                if stoch > 70:
                    return self.shooter.analizar_disparo('SHORT', current_price, 'SNIPER_FVG', stop_loss_ref=z['Top'])

        # 2. TÁCTICO (Trend/Scalp)
        trend_dir = "ALCISTA" if current_price > ema_200 else "BAJISTA"
        mode = "TREND" if adx > 25 else "SCALP_BB"
        msg = f"{trend_dir} ({mode}) ADX:{adx:.1f}"

        if not self.gatillo_armado:
            bb_low = metrics.get('BB_LOWER', 0)
            bb_up = metrics.get('BB_UPPER', 0)
            bb_mid = metrics.get('BB_MID', 0)

            if mode == "SCALP_BB":
                if rsi < 30 and current_price < bb_low: self._armar('LONG', bb_low, mode)
                elif rsi > 70 and current_price > bb_up: self._armar('SHORT', bb_up, mode)
            elif mode == "TREND":
                if trend_dir == "ALCISTA" and rsi < 45: self._armar('LONG', bb_mid, mode)
                elif trend_dir == "BAJISTA" and rsi > 55: self._armar('SHORT', bb_mid, mode)
        else:
            return self._verificar_disparo(current_price)

        return msg

    def _armar(self, tipo, ref, mode):
        self.gatillo_armado = {'tipo': tipo, 'ref': ref, 'life': 10, 'mode': mode}
        self.log.log_operational("CEREBRO", f"Gatillo {tipo} ({mode}) Armado.")

    def _verificar_disparo(self, current_price):
        self.gatillo_armado['life'] -= 1
        if self.gatillo_armado['life'] <= 0:
            self.gatillo_armado = None
            return "❌ Gatillo Expirado"
        
        disparo = False
        if self.gatillo_armado['tipo'] == 'LONG' and current_price > self.gatillo_armado['ref']: disparo = True
        elif self.gatillo_armado['tipo'] == 'SHORT' and current_price < self.gatillo_armado['ref']: disparo = True
        
        if disparo:
            self.log.log_operational("CEREBRO", f"DISPARO {self.gatillo_armado['tipo']} CONFIRMADO.")
            res = self.shooter.analizar_disparo(self.gatillo_armado['tipo'], current_price, self.gatillo_armado['mode'])
            self.gatillo_armado = None
            return res
        return "Esperando confirmación..."