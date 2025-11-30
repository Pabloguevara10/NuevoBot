import time
from collections import deque 

class BaseMode:
    def __init__(self, config):
        self.cfg = config
        self.gatillo = None 
        self.name = "BASE"

    def gestionar_gatillo(self, data, precio_actual, tp_banda, sl_pct, tp_offset_pct, force_trigger=False):
        """
        tp_offset_pct: Ahora se recibe como porcentaje (ej. 0.002 para 0.2%)
        """
        if not self.gatillo: return None, None
        
        # 1. Verificar Caducidad
        self.gatillo['ticks'] -= 1
        if self.gatillo['ticks'] <= 0:
            self.gatillo = None
            return None, "GATILLO EXPIRADO"
            
        # 2. Verificar DISPARO
        tipo = self.gatillo['tipo']
        
        disparo = False
        if force_trigger:
            disparo = True
            # Usar valores de fallback si se fuerza manual
            tp_banda = precio_actual * (1.01 if tipo == 'LONG' else 0.99)
        else:
            banda_ref = self.gatillo['banda_ref']
            if tipo == 'LONG' and precio_actual > banda_ref: disparo = True
            if tipo == 'SHORT' and precio_actual < banda_ref: disparo = True
        
        if disparo:
            tp_mid_val = self.gatillo.get('bb_mid', precio_actual)
            self.gatillo = None
            
            tp_final = 0.0
            if tipo == 'LONG':
                # LONG: Target = Banda Superior - Porcentaje
                tp_final = tp_banda * (1 - tp_offset_pct)
                sl_price = precio_actual * (1 - sl_pct)
            else:
                # SHORT: Target = Banda Inferior + Porcentaje
                tp_final = tp_banda * (1 + tp_offset_pct)
                sl_price = precio_actual * (1 + sl_pct)

            return tipo, {
                'motivo': f"{self.name} CONFIRMADO", 
                'sl_price': sl_price, 
                'tp_mid': tp_mid_val,
                'tp_final': tp_final
            }
            
        return None, f"GATILLO {tipo} ARMADO (Esperando...)"

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
                precio_base = p; break
        if precio_base is None: precio_base = self.price_buffer[0][1]
        if precio_base == 0: return 0.0
        return ((precio_actual - precio_base) / precio_base) * 100

    def evaluar(self, data_sig, data_filter): # 1m, 5m
        if not data_sig or 'CLOSE' not in data_sig: return None, None
        
        precio = data_sig['CLOSE']
        self.registrar_precio(precio)
        
        ema_filter = data_filter.get('EMA_200', 0) # 5m EMA
        permitir_long = precio > ema_filter if ema_filter > 0 else True
        permitir_short = precio < ema_filter if ema_filter > 0 else True

        # Gestión Gatillo
        bb_high = data_sig['BB_UPPER']
        bb_low = data_sig['BB_LOWER']
        
        res, info = self.gestionar_gatillo(
            data_sig, precio, 
            tp_banda=bb_high if self.gatillo and self.gatillo['tipo']=='LONG' else bb_low,
            sl_pct=self.cfg.MOMENTUM_SL_PCT,
            tp_offset_pct=self.cfg.MOMENTUM_TP_OFFSET
        )
        if res or info: return res, info

        # Armado
        if data_sig['BB_WIDTH'] <= self.cfg.MOM_BB_WIDTH_MIN: return None, None
        if not (self.cfg.MOM_VOL_MIN < data_sig['VOL_SCORE'] < self.cfg.MOM_VOL_MAX): return None, None

        if data_sig['STOCH_RSI'] < self.cfg.MOM_STOCH_LOW and data_sig['RSI'] < self.cfg.MOM_RSI_LOW and precio < bb_low and permitir_long:
            self.gatillo = {'tipo': 'LONG', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_low, 'bb_mid': data_sig['BB_MID']}
            return None, "MOMENTUM LONG ARMADO"

        if data_sig['STOCH_RSI'] > self.cfg.MOM_STOCH_HIGH and data_sig['RSI'] > self.cfg.MOM_RSI_HIGH and precio > bb_high and permitir_short:
            self.gatillo = {'tipo': 'SHORT', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_high, 'bb_mid': data_sig['BB_MID']}
            return None, "MOMENTUM SHORT ARMADO"
        return None, None

class ScalpMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.name = "SCALP"

    def evaluar(self, data_sig, data_filter): # 15m, 1h
        if not data_sig or 'CLOSE' not in data_sig: return None, None

        precio = data_sig['CLOSE']
        ema_filter = data_filter.get('EMA_200', 0) # 1h EMA
        permitir_long = precio > ema_filter if ema_filter > 0 else True
        permitir_short = precio < ema_filter if ema_filter > 0 else True

        bb_high = data_sig['BB_UPPER']
        bb_low = data_sig['BB_LOWER']

        res, info = self.gestionar_gatillo(
            data_sig, precio, 
            tp_banda=bb_high if self.gatillo and self.gatillo['tipo']=='LONG' else bb_low,
            sl_pct=self.cfg.SCALP_SL_PCT,
            tp_offset_pct=self.cfg.SCALP_TP_OFFSET
        )
        if res or info: return res, info

        if data_sig['BB_WIDTH'] <= self.cfg.SCALP_BB_WIDTH_MIN: return None, None
        if not (self.cfg.SCALP_VOL_MIN < data_sig['VOL_SCORE'] < self.cfg.SCALP_VOL_MAX): return None, None

        if data_sig['STOCH_RSI'] < self.cfg.SCALP_STOCH_LOW and data_sig['RSI'] < self.cfg.SCALP_RSI_LOW and precio < bb_low and permitir_long:
            self.gatillo = {'tipo': 'LONG', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_low, 'bb_mid': data_sig['BB_MID']}
            return None, "SCALP LONG ARMADO"

        if data_sig['STOCH_RSI'] > self.cfg.SCALP_STOCH_HIGH and data_sig['RSI'] > self.cfg.SCALP_RSI_HIGH and precio > bb_high and permitir_short:
            self.gatillo = {'tipo': 'SHORT', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_high, 'bb_mid': data_sig['BB_MID']}
            return None, "SCALP SHORT ARMADO"
        return None, None

class SwingMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.name = "SWING"

    def evaluar(self, data_sig, data_filter): # 1h, 4h
        if not data_sig or 'CLOSE' not in data_sig: return None, None

        precio = data_sig['CLOSE']
        ema_filter = data_filter.get('EMA_200', 0) # 4h EMA
        permitir_long = precio > ema_filter if ema_filter > 0 else True
        permitir_short = precio < ema_filter if ema_filter > 0 else True

        bb_high = data_sig['BB_UPPER']
        bb_low = data_sig['BB_LOWER']

        res, info = self.gestionar_gatillo(
            data_sig, precio, 
            tp_banda=bb_high if self.gatillo and self.gatillo['tipo']=='LONG' else bb_low,
            sl_pct=self.cfg.SWING_SL,
            tp_offset_pct=self.cfg.SWING_TP_OFFSET
        )
        if res or info: return res, info

        if data_sig['BB_WIDTH'] <= self.cfg.SWING_BB_WIDTH_MIN: return None, None
        if not (self.cfg.SWING_VOL_MIN < data_sig['VOL_SCORE'] < self.cfg.SWING_VOL_MAX): return None, None

        if data_sig['STOCH_RSI'] < self.cfg.SWING_STOCH_LOW and data_sig['RSI'] < self.cfg.SWING_RSI_LOW and precio < bb_low and permitir_long:
            self.gatillo = {'tipo': 'LONG', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_low, 'bb_mid': data_sig['BB_MID']}
            return None, "SWING LONG ARMADO"

        if data_sig['STOCH_RSI'] > self.cfg.SWING_STOCH_HIGH and data_sig['RSI'] > self.cfg.SWING_RSI_HIGH and precio > bb_high and permitir_short:
            self.gatillo = {'tipo': 'SHORT', 'ticks': self.cfg.TRIGGER_PATIENCE, 'banda_ref': bb_high, 'bb_mid': data_sig['BB_MID']}
            return None, "SWING SHORT ARMADO"
        return None, None