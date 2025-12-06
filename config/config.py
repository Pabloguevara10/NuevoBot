import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """
    Configuración Sentinel AI Pro V5.0 (Estrategia Limit + Prioridad Sniper).
    Ajuste de Alto Rendimiento: SL Amplios, TP Ambiciosos y Entradas Limit.
    """
    
    # CREDENCIALES
    API_KEY = os.getenv('BINANCE_API_KEY', '')
    API_SECRET = os.getenv('BINANCE_API_SECRET', '')
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # RED
    REQUEST_TIMEOUT = 2
    MAX_RETRIES = 3
    SYNC_CYCLE_FAST = 1
    SYNC_CYCLE_SLOW = 10

    # GENERAL
    MODE = 'TESTNET'      
    SYMBOL = 'AAVEUSDT'   
    LEVERAGE = 5          
    LOG_LEVEL = 'INFO'

    # GESTIÓN DE CAPITAL (Nuevos Límites V5)
    USE_FIXED_CAPITAL = True
    FIXED_CAPITAL_AMOUNT = 1000.0 
    ENABLE_COMPOUND_INTEREST = True  
    
    # Límites de Seguridad Diaria (Ajustados al nuevo riesgo)
    # Riesgo Sniper por tiro: 25% * 5% SL = 1.25% de la cuenta.
    # Max Loss 5% permite aprox 4 pérdidas consecutivas de Sniper.
    MAX_DAILY_LOSS_PCT = 0.05
    DAILY_TARGET_PCT = 0.08

    MAX_OPEN_POSITIONS = 3

    # CONFIGURACIÓN CEREBRO
    class BrainConfig:
        USE_4H_TREND_FILTER = True
        STOCH_1H_OVERBOUGHT = 80 
        STOCH_1H_OVERSOLD = 20
        ADX_MIN_STRENGTH = 20.0

    # CONFIGURACIÓN TIRADOR
    class ShooterConfig:
        MODES = {
            # --- TREND FOLLOWING (El Soporte) ---
            # Riesgo bajo (0.45% por tiro), TP Moderado (8%)
            'TREND_FOLLOWING': {
                'wallet_pct': 0.15,   
                'stop_loss_pct': 0.03,      # 3% SL
                'take_profit_pct': 0.08,    # 8% TP
                'entry_offset_pct': 0.01,   # Entrada Limit (-1%)
                'take_profit_type': 'FIXED_LEVELS' 
            },
            
            # --- SNIPER FVG (La Estrella) ---
            # Riesgo medio (1.25% por tiro), TP Alto (12%)
            'SNIPER_FVG': {
                'wallet_pct': 0.25,
                'stop_loss_pct': 0.05,      # 5% SL (Holgura máxima)
                'take_profit_pct': 0.12,    # 12% TP
                'entry_offset_pct': 0.01,   # Entrada Limit (-1%)
                'take_profit_type': 'FIXED_LEVELS'
            },
            
            # --- MODOS SECUNDARIOS ---
            'SCALP_BB': {
                'wallet_pct': 0.05,
                'stop_loss_pct': 0.015,
                'take_profit_pct': 0.015,
                'entry_offset_pct': 0.0,
                'take_profit_type': 'DYNAMIC_BB'
            },
            'MANUAL': {
                'wallet_pct': 0.05,
                'stop_loss_pct': 0.02,
                'take_profit_pct': 0.04,
                'entry_offset_pct': 0.0,
                'take_profit_type': 'FIXED_LEVELS'
            }
        }
        
        # Configuración General
        BE_TRIGGER_PCT = 0.015 # Breakeven se activa al +1.5%

        DCA_ENABLED = False # Desactivado en V5 para pureza de entradas
        DCA_MAX_ADDS = 0
        DCA_TRIGGER_DIST_PCT = 0.0
        DCA_MULTIPLIER = 1.0

    # RUTAS
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOG_PATH = os.path.join(BASE_DIR, 'logs', 'bitacoras')
    
    FILE_STATE = os.path.join(LOG_PATH, 'bot_state.json')
    FILE_METRICS = os.path.join(LOG_PATH, 'metrics_history.csv')
    FILE_WALLET = os.path.join(LOG_PATH, 'virtual_wallet.json')
    FILE_ORDERS = os.path.join(LOG_PATH, 'orders_positions.csv')
    FILE_ERRORS = os.path.join(LOG_PATH, 'system_errors.csv')
    FILE_ACTIVITY = os.path.join(LOG_PATH, 'bot_activity.log')