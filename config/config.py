import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- CREDENCIALES ---
    API_KEY = os.getenv('BINANCE_API_KEY', '')
    API_SECRET = os.getenv('BINANCE_API_SECRET', '')
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # --- GENERAL ---
    MODE = 'TESTNET'  # SIMULATION, TESTNET, LIVE
    SYMBOL = 'AAVEUSDT'
    LEVERAGE = 5
    
    # --- CAPITAL BASE FIJO (SEGURIDAD) ---
    USE_FIXED_CAPITAL = True
    FIXED_CAPITAL_AMOUNT = 1000.0 
    
    # --- GESTIÓN DE CAPITAL (Wallet %) ---
    MAX_WALLET_PCT_TREND = 0.10    # 10%
    MAX_WALLET_PCT_REVERSAL = 0.05 # 5%
    MAX_WALLET_PCT_FVG = 0.15      # 15% (Alta Probabilidad)
    
    # Límites de Seguridad Global
    MAX_DAILY_LOSS_PCT = 0.04
    DAILY_TARGET_PCT = 0.06
    
    # --- PARAMETROS DE SALIDA ---
    TP_SPLIT = [0.30, 0.30, 0.40] 
    TP_DISTANCES = [0.015, 0.030, 0.060] 
    
    SL_DISTANCE_PCT = 0.02 
    
    DCA_ENABLED = True
    DCA_TRIGGER_DIST = 0.70
    
    # --- RUTAS ---
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOG_PATH = os.path.join(BASE_DIR, 'logs', 'bitacoras')
    FILE_METRICS = os.path.join(LOG_PATH, 'metrics_history.csv')
    FILE_ORDERS = os.path.join(LOG_PATH, 'orders_positions.csv')
    FILE_ERRORS = os.path.join(LOG_PATH, 'system_errors.csv')
    FILE_ACTIVITY = os.path.join(LOG_PATH, 'bot_activity.log')