import json
import os
from datetime import datetime

class Financials:
    """
    MÓDULO FINANCIERO CON INTERÉS COMPUESTO
    Gestiona el capital de trabajo y registra Ganancias/Pérdidas (PnL).
    """
    def __init__(self, config, api_conn):
        self.cfg = config
        self.conn = api_conn
        
        # Variables de estado
        self.daily_pnl = 0.0
        self.virtual_wallet = self.cfg.FIXED_CAPITAL_AMOUNT
        self.last_reset_date = datetime.now().strftime("%Y-%m-%d")
        
        # Cargar billetera persistente
        self._cargar_billetera()

    def _cargar_billetera(self):
        """Carga el capital acumulado desde el disco."""
        if os.path.exists(self.cfg.FILE_WALLET):
            try:
                with open(self.cfg.FILE_WALLET, 'r') as f:
                    data = json.load(f)
                    self.virtual_wallet = data.get('capital', self.cfg.FIXED_CAPITAL_AMOUNT)
                    self.daily_pnl = data.get('daily_pnl', 0.0)
                    self.last_reset_date = data.get('date', self.last_reset_date)
                    
                    # Verificar si es un nuevo día para resetear solo el contador visual de PnL Diario
                    hoy = datetime.now().strftime("%Y-%m-%d")
                    if hoy != self.last_reset_date:
                        self.daily_pnl = 0.0
                        self.last_reset_date = hoy
                        self._guardar_billetera()
            except:
                self.virtual_wallet = self.cfg.FIXED_CAPITAL_AMOUNT
        else:
            # Primera vez: Inicializamos con el capital fijo config
            self.virtual_wallet = self.cfg.FIXED_CAPITAL_AMOUNT
            self._guardar_billetera()

    def _guardar_billetera(self):
        """Guarda el estado actual de la billetera."""
        data = {
            'capital': self.virtual_wallet,
            'daily_pnl': self.daily_pnl,
            'date': self.last_reset_date
        }
        try:
            with open(self.cfg.FILE_WALLET, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"!!! Error guardando billetera: {e}")

    def obtener_capital_total(self):
        """
        Retorna el capital base para cálculos de riesgo.
        """
        # MODO 1: Interés Compuesto (Billetera Virtual Dinámica)
        if self.cfg.ENABLE_COMPOUND_INTEREST:
            return self.virtual_wallet
            
        # MODO 2: Capital Fijo Estático (Reinicia cada vez)
        if self.cfg.USE_FIXED_CAPITAL:
            return self.cfg.FIXED_CAPITAL_AMOUNT
            
        # MODO 3: Saldo Real de Binance (Todo el portafolio)
        return self.conn.get_account_balance()

    def registrar_pnl(self, pnl_realizado):
        """
        Registra el resultado de una operación cerrada.
        """
        # 1. Actualizar PnL Diario (Solo informativo/dashboard)
        self.daily_pnl += pnl_realizado
        
        # 2. Actualizar Billetera Virtual (Interés Compuesto)
        if self.cfg.ENABLE_COMPOUND_INTEREST:
            self.virtual_wallet += pnl_realizado
            # Protección: Evitar capital negativo o cero
            if self.virtual_wallet < 10.0: 
                self.virtual_wallet = 10.0 
        
        # 3. Persistencia Inmediata
        self._guardar_billetera()

    def puedo_operar(self):
        """Verifica salud financiera básica."""
        capital = self.obtener_capital_total()
        
        if capital <= 10:
            return False, "Capital insuficiente (<10 USDT)"
            
        # Circuit Breaker: Pérdida Diaria Máxima
        # Si hemos perdido más del X% del capital HOY, paramos.
        loss_pct = abs(self.daily_pnl) / capital
        if self.daily_pnl < 0 and loss_pct >= self.cfg.MAX_DAILY_LOSS_PCT:
            return False, f"⛔ Stop Loss Diario Alcanzado (-{loss_pct*100:.1f}%)"
            
        return True, "OK"