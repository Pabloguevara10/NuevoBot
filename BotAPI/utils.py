import math

def calcular_cantidad_ajustada(precio, capital_usdt, step_size):
    """
    Calcula la cantidad de activo a comprar basada en el capital en USDT,
    ajustada a la precisión (step_size) permitida por el exchange.
    """
    if precio == 0: return 0.0
    
    cantidad_bruta = capital_usdt / precio
    
    # Ajuste de precisión (Step Size)
    precision = int(round(-math.log(step_size, 10), 0))
    
    # Redondear hacia abajo para no exceder capital
    cantidad_ajustada = math.floor(cantidad_bruta / step_size) * step_size
    
    return round(cantidad_ajustada, precision)