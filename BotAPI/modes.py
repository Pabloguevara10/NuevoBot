# modes.py
import time
from collections import deque 

class BaseMode:
    def __init__(self, config):
        self.cfg = config
        self.gatillo = None 

    def gestionar_gatillo(self, data, precio_actual, tp_banda, sl_pct):
        if not self.gatillo: return None, None
        
        self.gatillo['ticks'] -= 1
        if self.gatillo['ticks'] <= 0:
            self.gatillo = None
            return None, "GATILLO EXPIRADO"
            
        tipo = self.gatillo['tipo']
        banda_ref = self.gatillo['banda_ref']
        
        disparo = False
        if tipo == 'LONG' and precio_actual > banda_ref: disparo = True
        if tipo == 'SHORT' and precio_actual < banda_ref: disparo = True
        
        if disparo:
            self.gatillo = None
            return tipo, {
                'motivo': f"{self.name} CONFIRMADO", 
                'sl_price': precio_actual * (1 - sl_pct) if tipo == 'LONG' else precio_actual * (1 + sl_pct), 
                'tp_price': tp_banda 
            }
            
        return None, f"GATILLO {tipo} ARMADO (Esperando Rebote)"

class MomentumMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.name = "MOMENTUM"
        self.price_buffer = deque(maxlen=60) 

    def registrar_precio(self, precio):
        if precio is None: return 
        now = time.time()
        self.price_buffer.append((now, precio))

    def obtener_datos_tiempo_real(self):
        if len(self.price_buffer) < 2: return 0.0
        now = time.time()
        precio_actual = self.price_buffer[-1][1]
        
        precio_base = None
        for ts, p in self.price_buffer:
            if now - ts <= self.cfg.MOMENTUM_WINDOW_SECONDS:
                precio_base = p
                break
        if precio_base is None: precio_base = self.price_buffer[0][1]
        if precio_base == 0: return 0.0
        return ((precio_actual - precio_base) / precio_base) * 100

    def evaluar(self, data_1m):
        if not data_1m or 'CLOSE' not in data_1m: return None, None
        
        precio = data_1m['CLOSE']
        self.registrar_precio(precio)
        
        bb_w = data_1m['BB_WIDTH']
        stoch = data_1m['STOCH_RSI']
        rsi = data_1m['RSI']
        vol = data_1m['VOL_SCORE']
        bb_low = data_1m['BB_LOWER']
        bb_high = data_1m['BB_UPPER']
        bb_mid = data_1m['BB_MID'] # Necesario para gestión interna
        
        res, info = self.gestionar_gatillo(
            data_1m, precio, 
            tp_banda=bb_high if self.gatillo and self.gatillo['tipo']=='LONG' else bb_low,
            sl_pct=self.cfg.MOMENTUM_SL_PCT
        )
        if res or info: return res, info

        # --- CONDICIONES ---
        if bb_w <= self.cfg.MOM_BB_WIDTH_MIN: return None, None
        
        # AJUSTE DE VOLUMEN (RANGO)
        if not (self.cfg.MOM_VOL_MIN < vol < self.cfg.MOM_VOL_MAX): return None, None

        if stoch < self.cfg.MOM_STOCH_LOW and rsi < self.cfg.MOM_RSI_LOW and precio < bb_low:
            self.gatillo = {'tipo': 'LONG', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_low}
            return None, "MOMENTUM LONG ARMADO"

        if stoch > self.cfg.MOM_STOCH_HIGH and rsi > self.cfg.MOM_RSI_HIGH and precio > bb_high:
            self.gatillo = {'tipo': 'SHORT', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_high}
            return None, "MOMENTUM SHORT ARMADO"
            
        return None, None

class ScalpMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.name = "SCALP"

    def evaluar(self, data_5m):
        if not data_5m or 'CLOSE' not in data_5m: return None, None

        precio = data_5m['CLOSE']
        bb_w = data_5m['BB_WIDTH']
        stoch = data_5m['STOCH_RSI']
        rsi = data_5m['RSI']
        vol = data_5m['VOL_SCORE']
        bb_low = data_5m['BB_LOWER']
        bb_high = data_5m['BB_UPPER']
        
        res, info = self.gestionar_gatillo(
            data_5m, precio, 
            tp_banda=bb_high if self.gatillo and self.gatillo['tipo']=='LONG' else bb_low,
            sl_pct=self.cfg.SCALP_SL_PCT
        )
        if res or info: return res, info

        if bb_w <= self.cfg.SCALP_BB_WIDTH_MIN: return None, None
        
        # AJUSTE DE VOLUMEN (RANGO)
        if not (self.cfg.SCALP_VOL_MIN < vol < self.cfg.SCALP_VOL_MAX): return None, None

        if stoch < self.cfg.SCALP_STOCH_LOW and rsi < self.cfg.SCALP_RSI_LOW and precio < bb_low:
            self.gatillo = {'tipo': 'LONG', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_low}
            return None, "SCALP LONG ARMADO"

        if stoch > self.cfg.SCALP_STOCH_HIGH and rsi > self.cfg.SCALP_RSI_HIGH and precio > bb_high:
            self.gatillo = {'tipo': 'SHORT', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_high}
            return None, "SCALP SHORT ARMADO"
            
        return None, None

class SwingMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.name = "SWING"

    def evaluar(self, data_15m):
        if not data_15m or 'CLOSE' not in data_15m: return None, None

        precio = data_15m['CLOSE']
        bb_w = data_15m['BB_WIDTH']
        stoch = data_15m['STOCH_RSI']
        rsi = data_15m['RSI']
        vol = data_15m['VOL_SCORE']
        bb_low = data_15m['BB_LOWER']
        bb_high = data_15m['BB_UPPER']
        
        res, info = self.gestionar_gatillo(
            data_15m, precio, 
            tp_banda=bb_high if self.gatillo and self.gatillo['tipo']=='LONG' else bb_low,
            sl_pct=self.cfg.SWING_SL
        )
        if res or info: return res, info

        if bb_w <= self.cfg.SWING_BB_WIDTH_MIN: return None, None
        
        # AJUSTE DE VOLUMEN (RANGO)
        if not (self.cfg.SWING_VOL_MIN < vol < self.cfg.SWING_VOL_MAX): return None, None

        if stoch < self.cfg.SWING_STOCH_LOW and rsi < self.cfg.SWING_RSI_LOW and precio < bb_low:
            self.gatillo = {'tipo': 'LONG', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_low}
            return None, "SWING LONG ARMADO"

        if stoch > self.cfg.SWING_STOCH_HIGH and rsi > self.cfg.SWING_RSI_HIGH and precio > bb_high:
            self.gatillo = {'tipo': 'SHORT', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_high}
            return None, "SWING SHORT ARMADO"
            
        return None, None