# modes.py
import pandas as pd
import numpy as np
from collections import deque
import time

class SwingMode:
    def __init__(self, config):
        self.cfg = config
    def evaluar(self, df, precio):
        if df.empty or pd.isna(df.iloc[-1]['RSI']): return None, None
        rsi = df.iloc[-1]['RSI']
        if rsi < self.cfg.SWING_RSI_OS: return 'LONG', {'motivo': "SWING RSI OS", 'sl_factor': 1-self.cfg.SWING_SL}
        if rsi > self.cfg.SWING_RSI_OB: return 'SHORT', {'motivo': "SWING RSI OB", 'sl_factor': 1+self.cfg.SWING_SL}
        return None, None

class ScalpMode:
    def __init__(self, config):
        self.cfg = config
        self.gatillo = None
    
    def analizar_volumetria(self, df):
        if len(df) < 2: return 0
        curr, prev = df.iloc[-1], df.iloc[-2]
        score = 0
        try:
            if (curr['OBV'] > prev['OBV']) == (curr['close'] > prev['close']): score += 45
            if curr['close'] > curr['VWAP']: score += 35
            if curr['ADI'] > prev['ADI']: score += 20
        except: pass
        return score

    def evaluar(self, df, precio):
        if df.empty: return None, None
        last = df.iloc[-1]
        if self.gatillo:
            self.gatillo['ticks'] -= 1
            if self.gatillo['ticks'] <= 0: 
                self.gatillo = None; return None, "GATILLO EXPIRADO"
            tipo = self.gatillo['tipo']
            verde = last['close'] > last['open']
            if (tipo=='LONG' and verde and precio>self.gatillo['price']) or (tipo=='SHORT' and not verde and precio<self.gatillo['price']):
                self.gatillo = None
                return tipo, {'motivo': "SCALP CONFIRMADO", 'sl_price': precio*(1-self.cfg.SCALP_SL_PCT if tipo=='LONG' else 1+self.cfg.SCALP_SL_PCT), 'tp_offset': self.cfg.SCALP_TP_OFFSET}
            return None, "GATILLO ARMADO"

        vol = self.analizar_volumetria(df)
        ma99 = last.get('MA99')
        if pd.isna(ma99): return None, None
        
        if last['RSI'] < self.cfg.SCALP_RSI_OS:
            if self.cfg.ENABLE_TREND_FILTER and precio < ma99: return None, "FILTRO MA99 (LONG)"
            if vol >= self.cfg.SCALP_VOL_THRESHOLD:
                self.gatillo = {'tipo': 'LONG', 'price': precio, 'ticks': self.cfg.TRIGGER_PATIENCE}
                return None, "SEÑAL SCALP LONG (Armando)"
        elif last['RSI'] > self.cfg.SCALP_RSI_OB:
            if self.cfg.ENABLE_TREND_FILTER and precio > ma99: return None, "FILTRO MA99 (SHORT)"
            if vol >= self.cfg.SCALP_VOL_THRESHOLD:
                self.gatillo = {'tipo': 'SHORT', 'price': precio, 'ticks': self.cfg.TRIGGER_PATIENCE}
                return None, "SEÑAL SCALP SHORT (Armando)"
        return None, None

class MomentumMode:
    """
    MODO TURBO V2: Análisis en ventana de SEGUNDOS (Time-Based).
    """
    def __init__(self, config):
        self.cfg = config
        self.name = "MOMENTUM"
        self.price_buffer = deque(maxlen=60) 

    def registrar_precio(self, precio):
        if precio is None: return # Protección
        now = time.time()
        self.price_buffer.append((now, precio))

    def obtener_datos_tiempo_real(self):
        """Retorna cambio porcentual en la ventana definida."""
        if len(self.price_buffer) < 2: return 0.0
        
        now = time.time()
        precio_actual = self.price_buffer[-1][1]
        
        # Buscar precio base (hace X segundos)
        precio_base = None
        for ts, p in self.price_buffer:
            if now - ts <= self.cfg.MOMENTUM_WINDOW_SECONDS:
                precio_base = p
                break
        
        if precio_base is None: precio_base = self.price_buffer[0][1]
        
        if precio_base == 0: return 0.0
        change_pct = ((precio_actual - precio_base) / precio_base) * 100
        return change_pct

    def evaluar(self, precio_actual):
        # 1. PROTECCIÓN CONTRA DATOS NULOS
        if precio_actual is None: return None, None
        
        # Actualizamos buffer
        self.registrar_precio(precio_actual)
        
        if len(self.price_buffer) < 5: return None, None 
        
        # Calculamos cambio
        change_pct = self.obtener_datos_tiempo_real()
        
        umbral = self.cfg.MOMENTUM_MIN_CHANGE * 100
        
        if change_pct > umbral:
            return 'LONG', {
                'motivo': f"TURBO IMPULSO (+{change_pct:.3f}%)",
                'sl_price': precio_actual * (1 - self.cfg.MOMENTUM_SL_PCT),
                'tp_price': precio_actual * 1.03 
            }
        elif change_pct < -umbral:
            return 'SHORT', {
                'motivo': f"TURBO IMPULSO ({change_pct:.3f}%)",
                'sl_price': precio_actual * (1 + self.cfg.MOMENTUM_SL_PCT),
                'tp_price': precio_actual * 0.97
            }
            
        return None, None