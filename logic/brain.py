import pandas as pd
import os
import time

class Brain:
    """
    CEREBRO (BRAIN) - Módulo Analítico
    Responsabilidad: Analizar mercado, validar tendencias y emitir señales de compra/venta.
    No ejecuta órdenes, solo sugiere 'Intenciones'.
    """
    def __init__(self, config, shooter, logger):
        self.cfg = config
        self.shooter = shooter
        self.log = logger
        
        # Base de datos de zonas estratégicas (FVG)
        self.fvg_db = []
        self.last_fvg_reload = 0
        self._cargar_fvgs()

    def _cargar_fvgs(self):
        """Carga zonas de interés desde CSV generado por DataMiner/Backtester."""
        try:
            path = os.path.join(self.cfg.LOG_PATH, 'fvg_registry.csv')
            if os.path.exists(path):
                self.fvg_db = pd.read_csv(path).to_dict('records')
                # Conversión de tipos segura
                for z in self.fvg_db:
                    z['Top'] = float(z['Top'])
                    z['Bottom'] = float(z['Bottom'])
            else:
                self.fvg_db = []
        except Exception as e:
            self.log.log_error("CEREBRO", f"Error cargando FVG DB: {e}")

    def procesar_mercado(self, mtf_data, current_price):
        """
        Analiza indicadores y busca configuraciones de alta probabilidad.
        Retorna: String de estado o llama al Shooter si hay señal.
        """
        if not mtf_data: return "Esperando Datos..."
        
        # 1. Recarga periódica de zonas (cada 60s)
        if time.time() - self.last_fvg_reload > 60:
            self._cargar_fvgs()
            self.last_fvg_reload = time.time()

        # 2. Datos Clave (Timeframe Principal 1m y Confirmación 5m)
        m1 = mtf_data.get('1m', {})
        m5 = mtf_data.get(self.cfg.BrainConfig.CONFIRMATION_TIMEFRAME, {})
        
        if not m1: return "Datos insuficientes (1m)"

        # Extraer métricas limpias del Config
        c_brain = self.cfg.BrainConfig

        # --- ANÁLISIS 1: ESTRATÉGICO (FVG / Zonas de Oferta-Demanda) ---
        # Prioridad Alta: Si estamos en zona FVG, ignoramos scalping básico
        senal_fvg = self._analizar_fvg(current_price, m1)
        if senal_fvg:
            return self.shooter.ejecutar_senal(senal_fvg)

        # --- ANÁLISIS 2: TÁCTICO (Scalping y Tendencia) ---
        # Filtro Macro: ¿Hacia dónde va el mercado en 5m?
        trend_macro = self._evaluar_tendencia_macro(m5, c_brain)
        
        adx = m1.get('ADX', 0)
        rsi = m1.get('RSI', 50)
        stoch = m1.get('STOCH_RSI', 50)
        
        msg_estado = f"Macro: {trend_macro} | ADX: {adx:.1f} | RSI: {rsi:.1f}"

        # Lógica de Disparo Táctica
        senal_tactica = None

        # A. SCALPING DE REVERSIÓN (Bandas Bollinger) - Mercado Lateral (ADX bajo)
        if adx < c_brain.ADX_TREND_MIN:
            bb_low = m1.get('BB_LOWER', 0)
            bb_up = m1.get('BB_UPPER', 0)
            
            # Long: Precio rompe abajo + RSI Sobrevendido + Macro no es Bajista fuerte
            if current_price < bb_low and rsi < c_brain.RSI_OVERSOLD and trend_macro != 'BAJISTA':
                senal_tactica = {'side': 'LONG', 'mode': 'SCALP_BB', 'price': current_price}
            
            # Short: Precio rompe arriba + RSI Sobrecomprado + Macro no es Alcista fuerte
            elif current_price > bb_up and rsi > c_brain.RSI_OVERBOUGHT and trend_macro != 'ALCISTA':
                senal_tactica = {'side': 'SHORT', 'mode': 'SCALP_BB', 'price': current_price}

        # B. SEGUIMIENTO DE TENDENCIA (Trend Following) - Mercado Direccional (ADX alto)
        else:
            ema_200 = m1.get('EMA_200', 0)
            
            # Long: Precio sobre EMA200 + RSI en zona de impulso + Macro Alcista
            if trend_macro == 'ALCISTA' and current_price > ema_200:
                if c_brain.RSI_TREND_BEARISH < rsi < c_brain.RSI_OVERBOUGHT: # Pullback en tendencia
                    senal_tactica = {'side': 'LONG', 'mode': 'TREND_FOLLOWING', 'price': current_price}
            
            # Short: Precio bajo EMA200 + RSI en zona de caída + Macro Bajista
            elif trend_macro == 'BAJISTA' and current_price < ema_200:
                if c_brain.RSI_TREND_BULLISH > rsi > c_brain.RSI_OVERSOLD:
                    senal_tactica = {'side': 'SHORT', 'mode': 'TREND_FOLLOWING', 'price': current_price}

        # Ejecución si hay señal válida
        if senal_tactica:
            return self.shooter.ejecutar_senal(senal_tactica)

        return msg_estado

    def _evaluar_tendencia_macro(self, metrics_macro, config):
        """Define la tendencia en temporalidad superior."""
        if not metrics_macro: return "NEUTRAL"
        price = metrics_macro.get('CLOSE', 0)
        ema = metrics_macro.get('EMA_200', 0)
        rsi = metrics_macro.get('RSI', 50)
        
        if price > ema and rsi > 50: return "ALCISTA"
        if price < ema and rsi < 50: return "BAJISTA"
        return "NEUTRAL"

    def _analizar_fvg(self, current_price, metrics):
        """Busca coincidencias con zonas FVG cargadas."""
        stoch = metrics.get('STOCH_RSI', 50)
        
        for z in self.fvg_db:
            # FVG Alcista (Zona de demanda)
            if z['Type'] == 'LONG' and z['Bottom'] <= current_price <= z['Top']:
                # Confirmación con oscilador para no entrar cayendo a plomo
                if stoch < 30: 
                    return {
                        'side': 'LONG', 'mode': 'SNIPER_FVG', 
                        'price': current_price, 'sl_ref': z['Bottom']
                    }
            
            # FVG Bajista (Zona de oferta)
            elif z['Type'] == 'SHORT' and z['Top'] >= current_price >= z['Bottom']:
                if stoch > 70:
                    return {
                        'side': 'SHORT', 'mode': 'SNIPER_FVG', 
                        'price': current_price, 'sl_ref': z['Top']
                    }
        return None