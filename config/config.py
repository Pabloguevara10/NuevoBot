import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """
    Configuración Centralizada de Sentinel AI Pro V2.0.
    """
    
    # ==========================================
    # 1. CONEXIÓN Y CREDENCIALES
    # ==========================================
    API_KEY = os.getenv('BINANCE_API_KEY', '')
    API_SECRET = os.getenv('BINANCE_API_SECRET', '')
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # Configuración de Red (Prioridad Binance)
    REQUEST_TIMEOUT = 2  # Segundos máximos para esperar respuesta de Binance
    MAX_RETRIES = 3      # Intentos de re-conexión antes de declarar error
    SYNC_CYCLE_FAST = 1  # Ciclo rápido (segundos)
    SYNC_CYCLE_SLOW = 10 # Ciclo lento (segundos)

    # ==========================================
    # 2. GENERAL DEL SISTEMA
    # ==========================================
    MODE = 'TESTNET'      # Opciones: 'SIMULATION', 'TESTNET', 'LIVE'
    SYMBOL = 'AAVEUSDT'   # Par a operar
    LEVERAGE = 5          # Apalancamiento Base
    LOG_LEVEL = 'INFO'    # DEBUG, INFO, WARNING, ERROR

    # ==========================================
    # 3. GESTIÓN DE RIESGO (CAPITAL)
    # ==========================================
    # Capital Base para cálculos de riesgo
    USE_FIXED_CAPITAL = True
    FIXED_CAPITAL_AMOUNT = 1000.0 
    
    # Límites de Seguridad Global (Circuit Breakers)
    MAX_DAILY_LOSS_PCT = 0.04    # 4% Pérdida diaria máxima (apaga el bot)
    DAILY_TARGET_PCT = 0.06      # 6% Meta diaria (detiene operativa agresiva)
    MAX_OPEN_POSITIONS = 3       # Máximo número de operaciones simultáneas

    # ==========================================
    # 4. CONFIGURACIÓN DEL CEREBRO (ESTRATEGIAS)
    # ==========================================
    class BrainConfig:
        # Parámetros Técnicos Tácticos
        RSI_OVERSOLD = 30       # Nivel de sobreventa
        RSI_OVERBOUGHT = 70     # Nivel de sobrecompra
        RSI_TREND_BULLISH = 55  # Confirmación tendencia alcista
        RSI_TREND_BEARISH = 45  # Confirmación tendencia bajista
        
        ADX_TREND_MIN = 25.0    # Fuerza mínima para considerar Tendencia
        
        # Validación Temporal
        CONFIRMATION_TIMEFRAME = '5m' # Marco de tiempo para validar tendencia

    # ==========================================
    # 5. CONFIGURACIÓN DEL TIRADOR (SHOOTER)
    # ==========================================
    class ShooterConfig:
        # Definición de Modos de Operación
        # Cada modo tiene su propia asignación de riesgo (% de la cartera)
        MODES = {
            'SCALP_BB': {
                'wallet_pct': 0.05,  # 5% del capital por operación
                'stop_loss_pct': 0.015,
                'take_profit_type': 'DYNAMIC_BB' # Salida por Bandas
            },
            'TREND_FOLLOWING': {
                'wallet_pct': 0.10,  # 10% del capital
                'stop_loss_pct': 0.02,
                'take_profit_type': 'FIXED_LEVELS'
            },
            'SNIPER_FVG': {
                'wallet_pct': 0.15,  # 15% (Alta convicción)
                'stop_loss_pct': 0.0, # 0.0 significa SL basado en estructura (Gráfico)
                'take_profit_type': 'FIXED_LEVELS'
            },
            'MANUAL': {
                'wallet_pct': 0.05,
                'stop_loss_pct': 0.02,
                'take_profit_type': 'FIXED_LEVELS'
            }
        }
        
        # Configuración de Salidas Fijas (Para TREND y MANUAL)
        TP_SPLIT = [0.30, 0.30, 0.40]      # Cómo dividir la posición (30%, 30%, 40%)
        TP_DISTANCES = [0.015, 0.030, 0.060] # Distancia de los TP (1.5%, 3%, 6%)

        # Configuración DCA (Promediado)
        DCA_ENABLED = True
        DCA_MAX_ADDS = 1          # Máximo 1 recompra
        DCA_TRIGGER_DIST_PCT = 0.015 # Distancia para activar DCA (1.5%)
        DCA_MULTIPLIER = 1.5      # Multiplicador de tamaño (Martingala suave)

    # ==========================================
    # 6. RUTAS DE ARCHIVOS (PERSISTENCIA)
    # ==========================================
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOG_PATH = os.path.join(BASE_DIR, 'logs', 'bitacoras')
    
    # Archivos Críticos
    FILE_STATE = os.path.join(LOG_PATH, 'bot_state.json') # NUEVO: Persistencia de estado
    FILE_ORDERS = os.path.join(LOG_PATH, 'orders_positions.csv')
    FILE_ERRORS = os.path.join(LOG_PATH, 'system_errors.csv')
    FILE_ACTIVITY = os.path.join(LOG_PATH, 'bot_activity.log')