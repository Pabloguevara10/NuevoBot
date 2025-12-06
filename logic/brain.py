import pandas as pd
import os
import time
from datetime import datetime
from tools.precision_lab import PrecisionLab as Lab

class Brain:
    """
    CEREBRO V5.2 (Keys Corregidas + Prioridad Sniper)
    """
    def __init__(self, config, shooter, logger):
        self.cfg = config
        self.shooter = shooter
        self.log = logger
        
        self.fvg_db = []
        self.last_fvg_reload = 0
        self._cargar_fvgs()

    def _cargar_fvgs(self):
        try:
            path = os.path.join(self.cfg.LOG_PATH, 'fvg_registry.csv')
            if os.path.exists(path):
                self.fvg_db = pd.read_csv(path).to_dict('records')
            else:
                self.fvg_db = []
        except: pass

    def procesar_mercado(self, mtf_data, current_price):
        if not mtf_data: return "Esperando Datos..."
        
        # 1. RECUPERAR DATAFRAMES (Usando las Keys correctas '1m', '5m'...)
        df_1m = mtf_data.get('1m')
        df_5m = mtf_data.get('5m')
        df_15m = mtf_data.get('15m')
        df_1h = mtf_data.get('1h')
        df_4h = mtf_data.get('4h')
        
        # 2. VALIDACIÓN DE SEGURIDAD (Critical Check)
        # Si falta CUALQUIER dato, salimos antes de que explote el código.
        required = [df_1m, df_5m, df_15m, df_1h, df_4h]
        if any(d is None or d.empty for d in required):
            missing = []
            if df_1m is None: missing.append('1m')
            if df_4h is None: missing.append('4h')
            return f"Cargando Buffer {missing}..."

        # Refresco de FVGs cada minuto
        if time.time() - self.last_fvg_reload > 60:
            self._cargar_fvgs()
            self.last_fvg_reload = time.time()

        # 3. ANÁLISIS MACRO (Ahora es seguro usar iloc)
        try:
            # Usamos get con default 0 para evitar error si falta la columna
            ema_macro = df_4h.iloc[-1].get('EMA_200', 0)
            tendencia_4h = 'ALCISTA' if current_price > ema_macro else 'BAJISTA'
            stoch_1h = Lab.analizar_stoch(df_1h)
        except Exception as e:
            return f"Error Indicadores: {e}"
        
        msg_estado = f"Macro: {tendencia_4h} | Trend: Escaneando..."
        senal = None

        # ==========================================================
        # ESTRATEGIA 1: SNIPER FVG (PRIORIDAD ALTA)
        # ==========================================================
        for fvg in self.fvg_db:
            try:
                tipo = fvg['Type']
                top, bottom = float(fvg['Top']), float(fvg['Bottom'])
                
                en_zona = (tipo=='LONG' and bottom <= current_price <= top) or \
                          (tipo=='SHORT' and top >= current_price >= bottom)
                
                if en_zona:
                    validado = True
                    # Filtro de Tendencia Macro y Saturación
                    if tipo == 'LONG' and (tendencia_4h == 'BAJISTA' or stoch_1h['zona'] == 'TECHO'): validado = False
                    if tipo == 'SHORT' and (tendencia_4h == 'ALCISTA' or stoch_1h['zona'] == 'SUELO'): validado = False
                    
                    if validado:
                        # Gatillo: Divergencia en 1m
                        div = Lab.detectar_divergencia(df_1m, ventana=15)
                        if (tipo == 'LONG' and div == 'BULLISH_DIV') or (tipo == 'SHORT' and div == 'BEARISH_DIV'):
                            senal = {
                                'side': tipo, 'mode': 'SNIPER_FVG', 
                                'price': current_price, 'sl_ref': 0.0 
                            }
                            return self.shooter.ejecutar_senal(senal)
            except: continue

        # ==========================================================
        # ESTRATEGIA 2: TREND FOLLOWING (PRIORIDAD MEDIA)
        # ==========================================================
        if not senal:
            try:
                # 1. GATILLO (5 min)
                emas_5m = Lab.analizar_medias(df_5m, 'EMA_7', 'EMA_25')
                
                # Verificamos la clave 'cruce' (fix del error anterior)
                if emas_5m.get('cruce'): 
                    # 2. CONFIRMACIÓN (15 min)
                    ema_trend_15m = df_15m['close'].ewm(span=50).mean().iloc[-1]
                    adx_15m = Lab.analizar_adx(df_15m)
                    
                    confirmado = False
                    if emas_5m['estado'] == 'ALCISTA' and df_15m.iloc[-1]['close'] > ema_trend_15m:
                        confirmado = True
                    elif emas_5m['estado'] == 'BAJISTA' and df_15m.iloc[-1]['close'] < ema_trend_15m:
                        confirmado = True
                    
                    if confirmado and adx_15m['valor'] > 20:
                        # 3. REFINAMIENTO (1 min)
                        rsi_1m = Lab.analizar_rsi(df_1m)
                        entrada_ok = False
                        
                        if emas_5m['estado'] == 'ALCISTA' and rsi_1m['valor'] < 80: entrada_ok = True
                        if emas_5m['estado'] == 'BAJISTA' and rsi_1m['valor'] > 20: entrada_ok = True
                        
                        if entrada_ok and tendencia_4h == emas_5m['estado']:
                            senal = {
                                'side': 'LONG' if emas_5m['estado']=='ALCISTA' else 'SHORT', 
                                'mode': 'TREND_FOLLOWING', 'price': current_price
                            }
                            return self.shooter.ejecutar_senal(senal)
            except Exception as e:
                # Log silencioso para no spammear consola
                pass
        
        return msg_estado