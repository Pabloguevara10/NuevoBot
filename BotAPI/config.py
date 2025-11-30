import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- MODO Y CREDENCIALES ---
    MODE = os.getenv('MODE', 'TESTNET') # OPTIONS: SIMULATION, TESTNET, LIVE
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET')
    
    if not API_KEY or not API_SECRET:
        print("⚠️  ADVERTENCIA: API KEYS no detectadas.")

    # --- MERCADO ---
    SYMBOL = 'AAVE/USDT'   
    USE_REAL_DATA_FOR_SIM = False 
    
    TF_MOMENTUM = '1m'
    TF_SCALP = '15m'   
    TF_SWING = '1h'    
    
    TF_FILTER_MOM = '5m'
    TF_FILTER_SCALP = '1h'
    TF_FILTER_SWING = '4h'

    # --- CAPITAL Y SEGURIDAD ---
    CAPITAL_TRABAJO = 1000.0   # Capital Base (si Compound está OFF)
    
    # --- INTERÉS COMPUESTO ---
    ENABLE_COMPOUND = True     # True = Usa el saldo real de la billetera.
    
    LEVERAGE = 10 
    MAX_EXPOSURE_USDT = 5000.0 
    MAX_API_RETRIES = 5        
    RETRY_DELAY_SECONDS = 2    
    
    # Apalancamiento por estrategia
    LEVERAGE_SCALP = 5   
    LEVERAGE_SWING = 10  
    LEVERAGE_MOMENTUM = 8  
    
    # Tamaño de la posición (% del Capital Total)
    SIZE_SCALP = 0.02      # 2% del saldo
    SIZE_SWING = 0.05      # 5% del saldo
    SIZE_MOMENTUM = 0.05   # 5% del saldo
    
    # --- COSTOS Y B/E ---
    FEE_MAKER = 0.0002 
    FEE_TAKER = 0.0005 
    MIN_NET_PROFIT_USDT = 0.60 

    # --- ORDENES PENDIENTES ---
    PENDING_ORDERS_FILE = 'ordenes_pendientes.csv'
    DEFAULT_PENDING_DIST_PCT = 2.0  

    # --- CORTACIRCUITOS FINANCIERO ---
    ENABLE_CIRCUIT_BREAKER = True
    MAX_DAILY_LOSS_USDT = 20.0   
    TARGET_DAILY_PROFIT_USDT = 50.0 

    # --- NOTIFICACIONES TELEGRAM ---
    TELEGRAM_ENABLED = True
    TELEGRAM_TOKEN = '8543480983:AAHhIgNIf3GXoE0SHO58PNE6tfvVB0HNDMM' 
    TELEGRAM_CHAT_ID = '8583871097'

    # --- INDICADORES GENERALES ---
    BB_PERIOD = 20
    BB_STD_DEV = 2.0
    RSI_PERIOD = 14
    STOCH_RSI_PERIOD = 14
    EMA_TREND_PERIOD = 200
    TRIGGER_PATIENCE = 10 

    # --- ESTRATEGIA SCALPING ---
    SCALP_RSI_PERIOD = 14      
    SCALP_BB_WIDTH_MIN = 1.60
    SCALP_STOCH_LOW = 15
    SCALP_STOCH_HIGH = 85
    SCALP_RSI_LOW = 34
    SCALP_RSI_HIGH = 66
    SCALP_VOL_MIN = 2.0
    SCALP_VOL_MAX = 100
    SCALP_SL_PCT = 0.008       
    # AHORA ES PORCENTAJE: 0.003 = 0.3% antes de la banda
    SCALP_TP_OFFSET = 0.003    
    SCALP_TRAIL_DIST = 0.002   
    
    # --- ESTRATEGIA SWING ---
    SWING_RSI_PERIOD = 14
    SWING_BB_WIDTH_MIN = 3.0
    SWING_STOCH_LOW = 10
    SWING_STOCH_HIGH = 90
    SWING_RSI_LOW = 35
    SWING_RSI_HIGH = 65
    SWING_VOL_MIN = 5.0
    SWING_VOL_MAX = 100
    SWING_SL = 0.02        
    # AHORA ES PORCENTAJE: 0.005 = 0.5% antes de la banda
    SWING_TP_OFFSET = 0.005      
    SWING_TRAIL = 0.005    
    
    # --- ESTRATEGIA MOMENTUM ---
    MOM_BB_WIDTH_MIN = 1.0
    MOM_STOCH_LOW = 20
    MOM_STOCH_HIGH = 80
    MOM_RSI_LOW = 28
    MOM_RSI_HIGH = 72
    MOM_VOL_MIN = 20
    MOM_VOL_MAX = 100
    MOMENTUM_WINDOW_SECONDS = 10   
    MOMENTUM_VOL_MULTIPLIER = 1.2  
    MOMENTUM_MIN_CHANGE = 0.0008   
    MOMENTUM_SL_PCT = 0.006        
    # AHORA ES PORCENTAJE: 0.002 = 0.2% antes de la banda
    MOMENTUM_TP_OFFSET = 0.002
    MOMENTUM_TRAIL_DIST = 0.002 
    
    # --- ESTRATEGIA MANUAL (CONFIGURACIÓN PERSONALIZADA) ---
    # Aquí defines qué tan lejos quieres el TP y SL cuando usas Telegram o Teclado
    MANUAL_TP_PCT = 0.030   # 3.0% de ganancia (Antes era 0.003 / 0.3%)
    MANUAL_SL_PCT = 0.015   # 1.5% de pérdida máxima (Antes era 0.005 / 0.5%)

    # --- OTROS ---
    ENABLE_AUTO_DCA = True     
    DCA_TRIGGER_PCT = 0.010    
    DCA_MULTIPLIER = 1.5       
    MAX_DCA_LEVELS = 3         
    ENABLE_TREND_FILTER = True
    VOL_SCORE_THRESHOLD = 15
    SR_WINDOW = 20 

    # --- LOGS Y ARCHIVOS ---
    LOG_FILE = 'system_log.txt'
    TRADES_FILE = 'bitacora_operaciones_blindada.csv'
    TELEMETRY_FILE = 'telemetria_mercado.csv'
    TELEMETRY_INTERVAL = 15 
    ERROR_LOG_FILE = 'registro_errores.csv'