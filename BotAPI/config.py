# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ==========================================
    # 1. MODO Y CREDENCIALES
    # ==========================================
    MODE = os.getenv('MODE', 'TESTNET')
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET')
    
    if not API_KEY or not API_SECRET:
        raise ValueError("❌ ERROR: Faltan las API KEYS en el archivo .env")

    # ==========================================
    # 2. MERCADO
    # ==========================================
    SYMBOL = 'AAVE/USDT'   
    USE_REAL_DATA_FOR_SIM = False 
    
    TF_SCALP = '1m'
    TF_SWING = '15m'
    
    TIMEFRAME_LIVE = TF_SCALP 
    TIMEFRAME_INIT = '5m'
    
    # ==========================================
    # 3. GESTIÓN DE CAPITAL Y APALANCAMIENTO
    # ==========================================
    CAPITAL_TRABAJO = 1000     
    LEVERAGE = 10 
    
    # Apalancamientos Específicos
    LEVERAGE_SCALP = 5   
    LEVERAGE_SWING = 10  
    LEVERAGE_MOMENTUM = 8  
    
    SIZE_SCALP = 0.02  
    SIZE_SWING = 0.10 
    SIZE_MOMENTUM = 0.05   
    
    # ==========================================
    # 4. ESTRATEGIA SCALPING (1m)
    # ==========================================
    SCALP_RSI_PERIOD = 7             
    SCALP_RSI_OB = 70          
    SCALP_RSI_OS = 30          
    SCALP_VOL_THRESHOLD = 15   
    
    SCALP_SL_PCT = 0.002       
    SCALP_TP_OFFSET = 0.001    
    SCALP_BE_TRIGGER = 0.0015  
    SCALP_TRAIL_DIST = 0.001   
    
    # ==========================================
    # 5. ESTRATEGIA SWING (15m)
    # ==========================================
    SWING_RSI_PERIOD = 14
    SWING_RSI_OB = 70
    SWING_RSI_OS = 30
    
    SWING_SL = 0.02        
    SWING_TP = 0.06        
    SWING_BE = 0.01        
    SWING_TRAIL = 0.005    
    
    # ==========================================
    # 6. AUTO-DCA Y FILTROS
    # ==========================================
    ENABLE_AUTO_DCA = True     
    DCA_TRIGGER_PCT = 0.005    
    DCA_MULTIPLIER = 1.5       
    MAX_DCA_LEVELS = 3         
    
    ENABLE_TREND_FILTER = True
    TRIGGER_PATIENCE = 5
    STOCH_K_OVERSOLD = 0.2
    STOCH_K_OVERBOUGHT = 0.8
    VOL_SCORE_THRESHOLD = 15   
    
    SR_WINDOW = 20 

    # ==========================================
    # 7. ARCHIVOS
    # ==========================================
    LOG_FILE = 'system_log.txt'
    TRADES_FILE = 'reporte_ordenes.csv'

    # ==========================================
    # 8. MODO MOMENTUM (ULTRA AGRESIVO - SEGUNDOS)
    # ==========================================
    # --- VARIABLE RECUPERADA ---
    MOMENTUM_WINDOW_SECONDS = 10   # Ventana de tiempo para medir el impulso
    
    # Entradas: Muy Sensibles
    MOMENTUM_VOL_MULTIPLIER = 1.2  # (Nota: Este se usa si volviéramos a lógica de velas, pero el modo V2 usa tiempo)
    MOMENTUM_MIN_CHANGE = 0.0008   # 0.08% de movimiento
    
    # Salidas: "Sniper" 
    MOMENTUM_SL_PCT = 0.0015       # 0.15% Stop Loss
    
    # Gestión de Ganancia
    MOMENTUM_BE_TRIGGER = 0.0030   # 0.30% activa B/E
    MOMENTUM_TRAIL_DIST = 0.0010   # 0.10% Trailing