# dashboard.py
import os
from colorama import Fore, Style, Back

def limpiar_pantalla():
    os.system('cls' if os.name == 'nt' else 'clear')

def _pintar_valor(tipo, valor, contexto=None):
    """
    Colorea valores numéricos para análisis rápido.
    """
    if valor is None: return "N/A"
    
    if tipo == 'RSI':
        val_str = f"{valor:>5.1f}"
        if valor >= 70: return f"{Fore.RED}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
        if valor <= 30: return f"{Fore.GREEN}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
        return f"{Fore.WHITE}{val_str}{Style.RESET_ALL}"
        
    elif tipo == 'K': # Stochastic
        val_str = f"{valor:>5.1f}"
        if valor >= 80: return f"{Fore.RED}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
        if valor <= 20: return f"{Fore.GREEN}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
        return f"{Fore.WHITE}{val_str}{Style.RESET_ALL}"
        
    elif tipo == 'BB_VAL': # Valores absolutos de bandas (Gris tenue)
        return f"{Fore.LIGHTBLACK_EX}{valor:>7.2f}{Style.RESET_ALL}"
        
    elif tipo == 'BB_DIST': # Distancia a la banda
        # contexto: 'UPPER' (buscando short) o 'LOWER' (buscando long)
        val_str = f"{valor:>6.2f}"
        
        # Si el valor es negativo o muy cercano a 0, es ruptura inminente
        if valor <= 0: 
            bg = Back.RED if contexto == 'UPPER' else Back.GREEN
            fg = Fore.WHITE
            return f"{bg}{fg}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
            
        if contexto == 'UPPER': # Acercandose a techo (Rojo)
            return f"{Fore.RED}{val_str}{Style.RESET_ALL}"
        else: # Acercandose a piso (Verde)
            return f"{Fore.GREEN}{val_str}{Style.RESET_ALL}"
            
    return f"{Fore.WHITE}{valor}{Style.RESET_ALL}"

def mostrar_mtf_table(matrix):
    """Imprime tabla comparativa detallada con valores de Bollinger."""
    print(f"{Fore.BLUE}─" * 94)
    print(f"{Fore.CYAN}📊 ANÁLISIS MULTI-TEMPORALIDAD (DETALLE BOLLINGER){Style.RESET_ALL}")
    # Ajustamos el ancho de la tabla para que quepan los precios
    print(f"{Fore.CYAN}╔════════════╦══════════════════════════════════╦══════════════════════════════════════════════╗")
    print(f"║ {Style.BRIGHT}INDICADOR {Style.NORMAL} ║             SCALPING             ║                    SWING                     ║")
    print(f"╠════════════╬────────┬────────┬────────┬───────╬────────┬─────────┬─────────┬─────────┬───────╣")
    print(f"║ TIMEFRAME  ║   1m   │   3m   │   5m   │       ║   15m  │   30m   │    1H   │    4H   │       ║")
    print(f"╠════════════╬────────┼────────┼────────┼───────╬────────┼─────────┼─────────┼─────────┼───────╣")
    
    timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '4h']
    
    # 1. RSI
    row_rsi = f"║ RSI (14)   ║"
    for tf in timeframes:
        if tf == '15m': row_rsi += "       ║" # Espaciador visual para separar grupos
        val = matrix.get(tf, {}).get('RSI', 0)
        row_rsi += f" {_pintar_valor('RSI', val)}  │"
    print(row_rsi[:-2] + "║") # Cierre de linea
    
    # 2. STOCH
    row_k = f"║ STOCH K    ║"
    for tf in timeframes:
        if tf == '15m': row_k += "       ║"
        val = matrix.get(tf, {}).get('K', 0)
        row_k += f" {_pintar_valor('K', val)}  │"
    print(row_k[:-2] + "║")
    
    print(f"╠════════════╬────────┼────────┼────────┼───────╬────────┼─────────┼─────────┼─────────┼───────╣")
    
    # 3. BB UPPER
    row_upp = f"║ BB HIGH    ║"
    for tf in timeframes:
        if tf == '15m': row_upp += "       ║"
        val = matrix.get(tf, {}).get('BB_UPPER', 0)
        row_upp += f" {_pintar_valor('BB_VAL', val)} │"
    print(row_upp[:-2] + "║")
    
    # 4. BB MID
    row_mid = f"║ BB MID     ║"
    for tf in timeframes:
        if tf == '15m': row_mid += "       ║"
        val = matrix.get(tf, {}).get('BB_MID', 0)
        row_mid += f" {_pintar_valor('BB_VAL', val)} │"
    print(row_mid[:-2] + "║")

    # 5. BB LOW
    row_low = f"║ BB LOW     ║"
    for tf in timeframes:
        if tf == '15m': row_low += "       ║"
        val = matrix.get(tf, {}).get('BB_LOWER', 0)
        row_low += f" {_pintar_valor('BB_VAL', val)} │"
    print(row_low[:-2] + "║")
    
    # 6. DISTANCIA (La Fila Mágica)
    print(f"╠════════════╬────────┼────────┼────────┼───────╬────────┼─────────┼─────────┼─────────┼───────╣")
    row_dist = f"║ DISTANCIA  ║"
    for tf in timeframes:
        if tf == '15m': row_dist += "       ║"
        data = matrix.get(tf, {})
        price = data.get('CLOSE', 0)
        mid = data.get('BB_MID', 0)
        upper = data.get('BB_UPPER', 0)
        lower = data.get('BB_LOWER', 0)
        
        dist = 0
        contexto = 'MID'
        
        if price > mid:
            # Está en la mitad superior, medimos distancia al techo
            dist = upper - price
            contexto = 'UPPER'
        else:
            # Está en la mitad inferior, medimos distancia al piso
            dist = price - lower
            contexto = 'LOWER'
            
        row_dist += f" {_pintar_valor('BB_DIST', dist, contexto)} │"
    print(row_dist[:-2] + "║")
    
    print(f"╚════════════╩════════┴════════┴════════╩═══════╩════════┴═════════┴═════════┴═════════╩═══════╝{Style.RESET_ALL}")

def mostrar_panel(df_scalp, df_swing, vol_score, mensaje_estrategia, modo, posicion, ordenes, mom_ratio, mom_chg, mtf_data=None):
    limpiar_pantalla()
    
    last_p = df_scalp.iloc[-1]['close']
    rsi_s = df_scalp.iloc[-1]['RSI']
    rsi_w = df_swing.iloc[-1]['RSI']
    
    color_rsi_s = Fore.GREEN if rsi_s < 30 else (Fore.RED if rsi_s > 70 else Fore.WHITE)
    color_rsi_w = Fore.GREEN if rsi_w < 30 else (Fore.RED if rsi_w > 70 else Fore.WHITE)

    print(f"{Fore.BLUE}==============================================================================================")
    print(f"   SENTINEL AI - {modo} | {Fore.YELLOW}PRECIO: {last_p:.2f}{Fore.BLUE} | VOL SCORE: {vol_score}")
    print(f"=============================================================================================={Style.RESET_ALL}")

    print(f"\n{Fore.MAGENTA}🔎 ESTADO DEL SISTEMA:{Style.RESET_ALL}")
    print(f"   • Momentum Chg (10s): {mom_chg:+.4f}%")
    print(f"   • Scalp RSI: {color_rsi_s}{rsi_s:.1f}{Style.RESET_ALL}")
    print(f"   • Swing RSI: {color_rsi_w}{rsi_w:.1f}{Style.RESET_ALL}")
    print(f"   • Acción Actual: {Style.BRIGHT}{mensaje_estrategia}{Style.RESET_ALL}")

    if posicion:
        pnl_u = (last_p - posicion['entrada']) * posicion['cantidad']
        if posicion['tipo'] == 'SHORT': pnl_u *= -1
        c_pnl = Fore.GREEN if pnl_u > 0 else Fore.RED
        
        tp_display = posicion['tp']
        sl_display = posicion['sl']
        if ordenes:
            for o in ordenes:
                trig_price = float(o.get('stopPrice', 0))
                if trig_price == 0: continue
                if o['type'] == 'TAKE_PROFIT_MARKET': tp_display = trig_price
                elif o['type'] == 'STOP_MARKET': sl_display = trig_price

        print(f"\n{Fore.GREEN}💎 POSICIÓN ABIERTA ({posicion['strategy']}):{Style.RESET_ALL}")
        print(f"   {posicion['tipo']} x{posicion.get('cantidad',0)} @ {posicion['entrada']:.2f}")
        print(f"   TP: {tp_display:.2f} | SL: {sl_display:.2f}")
        print(f"   PnL: {c_pnl}{pnl_u:.2f} USDT{Style.RESET_ALL} | B/E Activo: {posicion['break_even_activado']}")
    else:
        print(f"\n{Fore.CYAN}💤 ESPERANDO OPORTUNIDAD...{Style.RESET_ALL}")
        
    if ordenes:
        print(f"\n{Fore.YELLOW}📜 Órdenes Pendientes ({len(ordenes)}):{Style.RESET_ALL}")
        for o in ordenes[:5]:
            tipo = o['type']
            lado = o['side']
            precio_final = float(o.get('price', 0))
            if precio_final == 0: precio_final = float(o.get('stopPrice', 0))
            print(f"   [{tipo}] {lado} @ {precio_final:.2f}")

    if mtf_data:
        print("\n")
        mostrar_mtf_table(mtf_data)