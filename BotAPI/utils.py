# utils.py
import math
from decimal import Decimal

def calcular_cantidad_ajustada(precio_actual, nocional_deseado, step_size):
    if not step_size or not precio_actual or precio_actual == 0: return 0.0
    cantidad_bruta = nocional_deseado / precio_actual
    step_size_float = float(step_size)
    cantidad_ajustada = math.ceil(cantidad_bruta / step_size_float) * step_size_float
    
    if "." in str(step_size_float):
        decimales = len(str(step_size_float).split(".")[1])
    else:
        decimales = 0
        
    return float(f"{cantidad_ajustada:.{decimales}f}")