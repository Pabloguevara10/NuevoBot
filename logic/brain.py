import pandas as pd
import os
import time
from datetime import datetime
from tools.precision_lab import PrecisionLab as Lab

class Brain:
    """
    CEREBRO V3.3 (Scalping 15m/5m & Sniper FVG)
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

    def _calcular_sl_estructural(self, fvg, df_1h):
        """Busca el Máximo/Mínimo previo para SL Sniper."""
        try:
            created_at = pd.to_datetime(fvg['Created_At'])
            mask = (df_1h.index < created_at)
            history = df_1h.loc[mask].tail(5)
            
            if history.empty:
                return float(fvg['Bottom']) * 0.995 if fvg['Type'] == 'LONG' else float(fvg['Top']) * 1.005

            if fvg['Type'] == 'LONG':
                return history['low'].min() * 0.998 
            else:
                return history['high'].max() * 1.002 
        except:
            return float(fvg['Bottom']) * 0.99 if fvg['Type'] == 'LONG' else float(fvg['Top']) * 1.01

    def procesar_mercado(self, mtf_data, current_price):
        if not mtf_data: return "Esperando Datos..."
        
        # 1. Recuperar Historial (Agregamos 15m)
        df_1m = mtf_data.get('df_1m', pd.DataFrame())
        df_5m = mtf_data.get('df_5m', pd.DataFrame())
        df_15m = mtf_data.get('df_15m', pd.DataFrame()) # <--- NUEVO REQUERIMIENTO
        df_1h = mtf_data.get('df_1h', pd.DataFrame())
        df_4h = mtf_data.get('df_4h', pd.DataFrame())
        
        if df_1h.empty or df_4h.empty or df_5m.empty or df_15m.empty: 
            return "Cargando Buffer..."

        if time.time() - self.last_fvg_reload > 60:
            self._cargar_fvgs()
            self.last_fvg_reload = time.time()

        # --- FASE 1: CONTEXTO GLOBAL ---
        ema_macro = df_4h.iloc[-1].get('EMA_200', df_4h.iloc[-1].get('EMA_99', 0))
        tendencia_4h = 'ALCISTA' if current_price > ema_macro else 'BAJISTA'
        stoch_1h = Lab.analizar_stoch(df_1h)
        adx_1h = Lab.analizar_adx(df_1h)
        
        msg_estado = f"Macro: {tendencia_4h} | ADX 1H: {adx_1h['valor']}"

        senal = None

        # --- ESTRATEGIA 1: TREND FOLLOWING (La Locomotora) ---
        # Solo si hay fuerza (ADX > 20)
        if adx_1h['fuerza'] == 'TENDENCIA':
            emas_1m = Lab.analizar_medias(df_1m, 'EMA_7', 'EMA_25')
            
            if emas_1m['estado'] == 'ALCISTA' and tendencia_4h == 'ALCISTA':
                if stoch_1h['zona'] != 'TECHO':
                    senal = {'side': 'LONG', 'mode': 'TREND_FOLLOWING', 'price': current_price}

            elif emas_1m['estado'] == 'BAJISTA' and tendencia_4h == 'BAJISTA':
                if stoch_1h['zona'] != 'SUELO':
                    senal = {'side': 'SHORT', 'mode': 'TREND_FOLLOWING', 'price': current_price}

        # --- ESTRATEGIA 2: SNIPER FVG (El Francotirador) ---
        # Oportunista: Busca zonas de valor
        if not senal:
            for fvg in self.fvg_db:
                tipo = fvg['Type']
                top = float(fvg['Top'])
                bottom = float(fvg['Bottom'])
                
                en_zona = (tipo=='LONG' and bottom <= current_price <= top) or \
                          (tipo=='SHORT' and top >= current_price >= bottom)
                
                if en_zona:
                    validado = True
                    # Filtros de Seguridad (Aduana)
                    if tipo == 'LONG' and (tendencia_4h == 'BAJISTA' or stoch_1h['zona'] == 'TECHO'): validado = False
                    if tipo == 'SHORT' and (tendencia_4h == 'ALCISTA' or stoch_1h['zona'] == 'SUELO'): validado = False
                    
                    if validado:
                        # Gatillo: Divergencia en 1m (Ultra precisión dentro de la zona)
                        div = Lab.detectar_divergencia(df_1m, ventana=15)
                        if (tipo == 'LONG' and div == 'BULLISH_DIV') or \
                           (tipo == 'SHORT' and div == 'BEARISH_DIV'):
                            
                            sl_struct = self._calcular_sl_estructural(fvg, df_1h)
                            tp_struct = df_4h.iloc[-1]['BB_UPPER'] if tipo=='LONG' else df_4h.iloc[-1]['BB_LOWER']

                            senal = {
                                'side': tipo, 
                                'mode': 'SNIPER_FVG', 
                                'price': current_price,
                                'sl_ref': sl_struct,
                                'structural_target': tp_struct
                            }
                            break
        
        # --- ESTRATEGIA 3: SCALP BB (El Relleno) ---
        # Solo si mercado lateral (ADX < 20)
        if not senal and adx_1h['fuerza'] == 'RANGO': 
             # 1. SETUP: Analizamos Bandas en 15m (Estructura más fuerte que 1m)
             bb_15m = Lab.analizar_bb(df_15m)
             
             # 2. GATILLO: Refinamos en 5m (Buscamos el giro)
             rsi_5m = Lab.analizar_rsi(df_5m, rango=2)

             # Oportunidad de COMPRA (Precio toca fondo en 15m + RSI sube en 5m)
             if bb_15m['ubicacion'] == 'ROMPIENDO_ABAJO':
                 # Filtro: No ir contra tendencia macro bajista fuerte ni comprar en techo de 1h
                 if tendencia_4h == 'ALCISTA' and stoch_1h['zona'] != 'TECHO':
                     if rsi_5m['direccion'] == 'ALCISTA': # Gatillo 5m
                        senal = {'side': 'LONG', 'mode': 'SCALP_BB', 'price': current_price}

             # Oportunidad de VENTA (Precio toca techo en 15m + RSI baja en 5m)
             elif bb_15m['ubicacion'] == 'ROMPIENDO_ARRIBA':
                 if tendencia_4h == 'BAJISTA' and stoch_1h['zona'] != 'SUELO':
                     if rsi_5m['direccion'] == 'BAJISTA': # Gatillo 5m
                        senal = {'side': 'SHORT', 'mode': 'SCALP_BB', 'price': current_price}

        # Ejecución
        if senal:
            return self.shooter.ejecutar_senal(senal)

        return msg_estado