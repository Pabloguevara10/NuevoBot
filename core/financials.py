class Financials:
    def __init__(self, config, api_conn):
        self.cfg = config
        self.conn = api_conn
        self.daily_pnl = 0.0
        self.capital_inicial = self.cfg.FIXED_CAPITAL_AMOUNT if self.cfg.USE_FIXED_CAPITAL else 1000.0

    def registrar_pnl(self, amount):
        self.daily_pnl += amount

    def puedo_operar(self):
        base = self.cfg.FIXED_CAPITAL_AMOUNT if self.cfg.USE_FIXED_CAPITAL else self.capital_inicial
        if self.daily_pnl <= -(base * self.cfg.MAX_DAILY_LOSS_PCT):
            return False, "CORTACIRCUITO: Límite diario excedido."
        if self.daily_pnl >= (base * self.cfg.DAILY_TARGET_PCT):
            return False, "META CUMPLIDA."
        return True, "OK"

    def obtener_capital_total(self):
        if self.cfg.USE_FIXED_CAPITAL: return self.cfg.FIXED_CAPITAL_AMOUNT
        return self.conn.get_account_balance() or 1000.0