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
        print("⚠️  ADVERTENCIA: API KEYS no detectadas.")

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
    # 3. GESTIÓN DE CAPITAL Y SEGURIDAD
    # ==========================================
    CAPITAL_TRABAJO = 1000     
    LEVERAGE = 10 
    MAX_EXPOSURE_USDT = 5000.0 
    
    MAX_API_RETRIES = 5        
    RETRY_DELAY_SECONDS = 2    
    
    LEVERAGE_SCALP = 5   
    LEVERAGE_SWING = 10  
    LEVERAGE_MOMENTUM = 8  
    
    SIZE_SCALP = 0.02   
    SIZE_SWING = 0.05   
    SIZE_MOMENTUM = 0.05 
    
    # ==========================================
    # 4. INDICADORES GENERALES
    # ==========================================
    BB_PERIOD = 20
    BB_STD_DEV = 2.0
    RSI_PERIOD = 14
    STOCH_RSI_PERIOD = 14
    
    TRIGGER_PATIENCE = 10 

    # ==========================================
    # 5. ESTRATEGIA SCALPING (1m / 5m)
    # ==========================================
    SCALP_RSI_PERIOD = 14      
    SCALP_VOL_THRESHOLD = 15   

    # Gatillo (Mean Reversion):
    SCALP_BB_WIDTH_MIN = 2.5
    SCALP_STOCH_LOW = 10
    SCALP_STOCH_HIGH = 90
    SCALP_RSI_LOW = 30
    SCALP_RSI_HIGH = 60
    
    # Ajuste Volumen
    SCALP_VOL_MIN = 30
    SCALP_VOL_MAX = 75
    
    # Salida
    SCALP_SL_PCT = 0.008       
    SCALP_TP_OFFSET = 0.003    
    SCALP_BE_TRIGGER = 0.005   
    SCALP_TRAIL_DIST = 0.002   
    
    # ==========================================
    # 6. ESTRATEGIA SWING (15m)
    # ==========================================
    SWING_RSI_PERIOD = 14

    # Gatillo:
    SWING_BB_WIDTH_MIN = 3.75
    SWING_STOCH_LOW = 5
    SWING_STOCH_HIGH = 95
    SWING_RSI_LOW = 30
    SWING_RSI_HIGH = 70
    
    # Ajuste Volumen
    SWING_VOL_MIN = 30
    SWING_VOL_MAX = 70
    
    # Salida
    SWING_SL = 0.02        
    SWING_TP_OFFSET = 0.2      
    SWING_BE = 0.01        
    SWING_TRAIL = 0.005    
    
    # ==========================================
    # 7. AUTO-DCA Y FILTROS
    # ==========================================
    ENABLE_AUTO_DCA = True     
    DCA_TRIGGER_PCT = 0.010    
    DCA_MULTIPLIER = 1.5       
    MAX_DCA_LEVELS = 3         
    
    ENABLE_TREND_FILTER = True
    VOL_SCORE_THRESHOLD = 15
    SR_WINDOW = 20 

    # ==========================================
    # 8. LOGS Y TELEMETRÍA
    # ==========================================
    LOG_FILE = 'system_log.txt'
    TRADES_FILE = 'bitacora_operaciones_blindada.csv'
    
    # --- VARIABLES RECUPERADAS (CRÍTICAS) ---
    TELEMETRY_FILE = 'telemetria_mercado.csv'
    TELEMETRY_INTERVAL = 15 
    # ----------------------------------------

    # ==========================================
    # 9. MODO MOMENTUM (1m)
    # ==========================================
    # Gatillo:
    MOM_BB_WIDTH_MIN = 1.25
    MOM_STOCH_LOW = 15
    MOM_STOCH_HIGH = 90
    MOM_RSI_LOW = 25
    MOM_RSI_HIGH = 90
    
    # Ajuste Volumen
    MOM_VOL_MIN = 25
    MOM_VOL_MAX = 65

    MOMENTUM_WINDOW_SECONDS = 10   
    MOMENTUM_VOL_MULTIPLIER = 1.2  
    MOMENTUM_MIN_CHANGE = 0.0008   
    
    MOMENTUM_SL_PCT = 0.006        
    MOMENTUM_TP_OFFSET = 0.2
    MOMENTUM_BE_TRIGGER = 0.004    
    MOMENTUM_TRAIL_DIST = 0.002