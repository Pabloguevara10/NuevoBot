import pandas as pd

class SmartMoneyLogic:
    """
    GESTOR DE CONTEXTO INSTITUCIONAL (SMC)
    Rastrea Liquidez Diaria, Puntos de Interés (POIs) y Secuencias de Entrada.
    """
    def __init__(self):
        self.pdh = None # Previous Day High
        self.pdl = None # Previous Day Low
        self.bias = 'NEUTRAL'
        self.state = 'ESPERANDO_LIQUIDEZ' 
        # Estados: ESPERANDO_LIQUIDEZ -> LIQUIDEZ_TOMADA -> FVG_DETECTADO -> EN_ZONA
        
        self.active_poi = None # El nivel que estamos vigilando
        self.active_fvg = None # El FVG generado tras la toma de liquidez

    def iniciar_nuevo_dia(self, vela_ayer):
        """Se llama al inicio de cada día (00:00 UTC) con la vela D1 cerrada."""
        self.pdh = vela_ayer['high']
        self.pdl = vela_ayer['low']
        # Definir sesgo simple basado en cierre vs apertura
        self.bias = 'ALCISTA' if vela_ayer['close'] > vela_ayer['open'] else 'BAJISTA'
        
        self.state = 'ESPERANDO_LIQUIDEZ'
        self.active_poi = None
        self.active_fvg = None
        
        return f"Nuevos POIs: PDH={self.pdh:.2f}, PDL={self.pdl:.2f} ({self.bias})"

    def verificar_toma_liquidez(self, vela_actual):
        """
        Verifica si el precio actual 'barrió' un nivel importante y regresó.
        Se debe ejecutar en temporalidad media (ej. 15m o 1H).
        """
        if not self.pdh or not self.pdl: return None

        # Toma de Liquidez Bajista (Barrido de Máximos)
        # El precio supera el PDH pero cierra por debajo (Rechazo)
        if vela_actual['high'] > self.pdh and vela_actual['close'] < self.pdh:
            self.state = 'LIQUIDEZ_TOMADA'
            self.active_poi = {'tipo': 'PDH', 'nivel': self.pdh, 'direccion': 'SHORT'}
            return 'SWEEP_HIGH'

        # Toma de Liquidez Alcista (Barrido de Mínimos)
        # El precio baja del PDL pero cierra por encima (Rechazo)
        if vela_actual['low'] < self.pdl and vela_actual['close'] > self.pdl:
            self.state = 'LIQUIDEZ_TOMADA'
            self.active_poi = {'tipo': 'PDL', 'nivel': self.pdl, 'direccion': 'LONG'}
            return 'SWEEP_LOW'
            
        return None

    def registrar_fvg_post_sweep(self, fvg):
        """Si detectamos un FVG justo después de la toma de liquidez, lo guardamos."""
        if self.state == 'LIQUIDEZ_TOMADA':
            # Validar dirección: Si barrimos altos (Short), buscamos FVG Bajista
            if self.active_poi['direccion'] == 'SHORT' and fvg.type == 'SHORT':
                self.state = 'FVG_DETECTADO'
                self.active_fvg = fvg
                return True
            
            # Si barrimos bajos (Long), buscamos FVG Alcista
            if self.active_poi['direccion'] == 'LONG' and fvg.type == 'LONG':
                self.state = 'FVG_DETECTADO'
                self.active_fvg = fvg
                return True
                
        return False