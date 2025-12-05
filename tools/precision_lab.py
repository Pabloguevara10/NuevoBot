import pandas as pd
import numpy as np

class PrecisionLab:
    """
    LABORATORIO DE PRECISIÓN (TOOLKIT ATÓMICO V3)
    Funciones independientes para disecar indicadores específicos.
    Incluye: RSI, ADX, StochRSI, MACD, Bollinger, EMAs y Divergencias.
    """

    # --- UTILITARIOS ---
    @staticmethod
    def _calcular_pendiente(serie, rango=3):
        """Calcula velocidad de cambio (Positivo=Sube, Negativo=Baja)."""
        if len(serie) < rango: return 0.0
        inicial = serie.iloc[-rango]
        final = serie.iloc[-1]
        return (final - inicial) / rango

    # --- 1. RSI (Fuerza Relativa) ---
    @staticmethod
    def analizar_rsi(df, rango=3):
        if 'RSI' not in df.columns: return {'valor': 50, 'estado': 'NEUTRAL', 'pendiente': 0, 'direccion': 'NEUTRAL'}
        val = df.iloc[-1]['RSI']
        pendiente = PrecisionLab._calcular_pendiente(df['RSI'], rango)
        
        estado = 'NEUTRAL'
        if val > 70: estado = 'SOBRECOMPRA'
        elif val < 30: estado = 'SOBREVENTA'
        
        return {
            'tipo': 'RSI',
            'valor': round(val, 2),
            'estado': estado,
            'direccion': 'ALCISTA' if pendiente > 0 else 'BAJISTA',
            'pendiente': round(pendiente, 4)
        }

    # --- 2. ADX (Fuerza de Tendencia) ---
    @staticmethod
    def analizar_adx(df, rango=3):
        if 'ADX' not in df.columns: return {'valor': 0, 'fuerza': 'NEUTRAL', 'evolucion': 'NEUTRAL'}
        val = df.iloc[-1]['ADX']
        pendiente = PrecisionLab._calcular_pendiente(df['ADX'], rango)
        
        return {
            'tipo': 'ADX',
            'valor': round(val, 2),
            'fuerza': 'TENDENCIA' if val > 25 else 'LATERAL',
            'evolucion': 'FORTALECIENDO' if pendiente > 0 else 'DEBILITANDO'
        }

    # --- 3. STOCH RSI (Ciclos) ---
    @staticmethod
    def analizar_stoch(df, rango=3):
        """Analiza el oscilador estocástico."""
        # Si no existe la columna, devolvemos un valor neutro para evitar crash
        if 'STOCH_RSI' not in df.columns: 
            return {'valor': 50, 'zona': 'NEUTRAL', 'posible_giro': False}
            
        val = df.iloc[-1]['STOCH_RSI']
        pendiente = PrecisionLab._calcular_pendiente(df['STOCH_RSI'], rango)
        
        zona = 'NEUTRAL'
        if val > 80: zona = 'TECHO'
        elif val < 20: zona = 'SUELO'
        
        # Detectar giro potencial
        giro = False
        if zona == 'TECHO' and pendiente < 0: giro = True # Empieza a caer
        if zona == 'SUELO' and pendiente > 0: giro = True # Empieza a subir
        
        return {
            'tipo': 'STOCH',
            'valor': round(val, 2),
            'zona': zona,
            'posible_giro': giro
        }

    # --- 4. MACD (Momento) ---
    @staticmethod
    def analizar_macd(df):
        if 'MACD_HIST' not in df.columns:
            # Calculo de emergencia si falta
            k = df['close'].ewm(span=12, adjust=False).mean()
            d = df['close'].ewm(span=26, adjust=False).mean()
            dif = k - d
            dea = dif.ewm(span=9, adjust=False).mean()
            hist = dif - dea
        else:
            hist = df['MACD_HIST']

        val_hist = hist.iloc[-1]
        prev_hist = hist.iloc[-2] if len(hist) > 1 else 0
        
        return {
            'tipo': 'MACD',
            'histograma': round(val_hist, 4),
            'fase': 'BULL' if val_hist > 0 else 'BEAR',
            'impulso': 'CRECIENTE' if val_hist > prev_hist else 'DECRECIENTE'
        }

    # --- 5. BOLLINGER (Volatilidad) ---
    @staticmethod
    def analizar_bb(df):
        if 'BB_UPPER' not in df.columns: return {'ubicacion': 'DENTRO', 'rango_precio': 0}
        price = df.iloc[-1]['close']
        up = df.iloc[-1]['BB_UPPER']
        low = df.iloc[-1]['BB_LOWER']
        
        pos = 'DENTRO'
        if price >= up: pos = 'ROMPIENDO_ARRIBA'
        elif price <= low: pos = 'ROMPIENDO_ABAJO'
        
        return {
            'tipo': 'BB',
            'ubicacion': pos,
            'rango_precio': round(up - low, 2)
        }

    # --- 6. EMAs (Tendencia) ---
    @staticmethod
    def analizar_medias(df, rapida='EMA_7', lenta='EMA_25'):
        """Analiza el cruce y estado de dos medias móviles."""
        # Calcular si no existen en el DF
        if rapida not in df.columns:
            span = int(rapida.split('_')[1])
            serie_rapida = df['close'].ewm(span=span, adjust=False).mean()
        else:
            serie_rapida = df[rapida]
            
        if lenta not in df.columns:
            span = int(lenta.split('_')[1])
            serie_lenta = df['close'].ewm(span=span, adjust=False).mean()
        else:
            serie_lenta = df[lenta]
            
        val_r = serie_rapida.iloc[-1]
        val_l = serie_lenta.iloc[-1]
        
        return {
            'indicador': 'EMAS',
            'estado': 'ALCISTA' if val_r > val_l else 'BAJISTA',
            'spread': round(abs(val_r - val_l), 4)
        }

    # --- 7. DIVERGENCIAS (Gatillo Sniper) ---
    @staticmethod
    def detectar_divergencia(df, ventana=10):
        """
        Busca divergencias Regulares entre Precio y RSI.
        Retorna: 'BULLISH_DIV', 'BEARISH_DIV' o None.
        """
        if len(df) < ventana or 'RSI' not in df.columns: return None
        
        subset = df.tail(ventana)
        
        # Datos actuales (Vela 0, la más reciente)
        curr_high = subset.iloc[-1]['high']
        curr_low = subset.iloc[-1]['low']
        curr_rsi = subset.iloc[-1]['RSI']
        
        # Datos previos (excluyendo la vela actual)
        prev_subset = subset.iloc[:-1]
        if prev_subset.empty: return None
        
        max_price_prev = prev_subset['high'].max()
        min_price_prev = prev_subset['low'].min()
        max_rsi_prev = prev_subset['RSI'].max()
        min_rsi_prev = prev_subset['RSI'].min()
        
        # Divergencia Bajista (Precio sube, RSI baja)
        if curr_high >= max_price_prev and curr_rsi < max_rsi_prev * 0.98:
            return 'BEARISH_DIV'
                
        # Divergencia Alcista (Precio baja, RSI sube)
        if curr_low <= min_price_prev and curr_rsi > min_rsi_prev * 1.02:
            return 'BULLISH_DIV'
            
        return None