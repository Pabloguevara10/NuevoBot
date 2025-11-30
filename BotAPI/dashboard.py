import os
from datetime import datetime
from colorama import Fore, Style, Back

def limpiar_pantalla():
    os.system('cls' if os.name == 'nt' else 'clear')

def _pintar_valor(tipo, valor, contexto=None):
    if valor is None: return f"{'N/A':^8}"
    
    val_str = ""
    if isinstance(valor, (int, float)):
        val_str = f"{valor:^8.1f}" if tipo in ['RSI', 'K'] else f"{valor:^8.2f}"
    else:
        val_str = f"{str(valor):^8}"

    if tipo == 'RSI':
        if valor >= 66: return f"{Fore.RED}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
        if valor <= 34: return f"{Fore.GREEN}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
        return f"{Fore.WHITE}{val_str}{Style.RESET_ALL}"
    
    elif tipo == 'K': 
        if valor >= 80: return f"{Fore.RED}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
        if valor <= 20: return f"{Fore.GREEN}{Style.BRIGHT}{val_str}{Style.RESET_ALL}"
        return f"{Fore.WHITE}{val_str}{Style.RESET_ALL}"
    
    elif tipo == 'BB_VAL':
        return f"{Fore.LIGHTBLACK_EX}{val_str}{Style.RESET_ALL}"
    
    elif tipo == 'BB_DIST_MID':
        color = Fore.GREEN if valor >= 0 else Fore.RED
        return f"{color}{f'{valor:+.2f}':^8}{Style.RESET_ALL}"
        
    elif tipo == 'BB_DIST_LIMIT':
        txt_val = f"{valor:>6.2f}"
        if valor <= 0: 
            bg = Back.RED if contexto == 'UPPER' else Back.GREEN
            fg = Fore.WHITE
            return f"{bg}{fg}{Style.BRIGHT}{txt_val:^8}{Style.RESET_ALL}"
        
        color = Fore.RED if contexto == 'UPPER' else Fore.GREEN
        return f"{color}{txt_val:^8}{Style.RESET_ALL}"
        
    return f"{Fore.WHITE}{val_str}{Style.RESET_ALL}"

def mostrar_mtf_table(matrix):
    print(f"{Fore.BLUE}─" * 106)
    print(f"{Fore.CYAN}📊 ANÁLISIS MULTI-TEMPORALIDAD (Vista Completa){Style.RESET_ALL}")
    
    headers = f"║ {Style.BRIGHT}{'INDICADOR':<10}{Style.NORMAL} ║ {'1m':^8} │ {'3m':^8} │ {'5m':^8} ║ {'15m':^8} │ {'30m':^8} │ {'1h':^8} │ {'4h':^8} ║"
    
    print(f"{Fore.CYAN}╔════════════╦═══════════════════════════════╦══════════════════════════════════════════╗")
    print(headers)
    print(f"╠════════════╬─────────┼──────────┼──────────╬──────────┼──────────┼──────────┼──────────╣")
    
    timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '4h']
    
    # RSI
    row_rsi = f"║ {'RSI (14)':<10} ║"
    for tf in timeframes:
        sep = " ║ " if tf == '5m' else (" ║" if tf == '4h' else " │ ")
        val = matrix.get(tf, {}).get('RSI', 0)
        row_rsi += _pintar_valor('RSI', val) + sep
    print(row_rsi)
    
    # STOCH
    row_k = f"║ {'STOCH K':<10} ║"
    for tf in timeframes:
        sep = " ║ " if tf == '5m' else (" ║" if tf == '4h' else " │ ")
        val = matrix.get(tf, {}).get('K', 0)
        row_k += _pintar_valor('K', val) + sep
    print(row_k)

    print(f"╠════════════╬─────────┼──────────┼──────────╬──────────┼──────────┼──────────┼──────────╣")

    # DIST MID
    row_dmid = f"║ {'DIST MID':<10} ║"
    for tf in timeframes:
        sep = " ║ " if tf == '5m' else (" ║" if tf == '4h' else " │ ")
        data = matrix.get(tf, {})
        diff = data.get('CLOSE', 0) - data.get('BB_MID', 0)
        row_dmid += _pintar_valor('BB_DIST_MID', diff) + sep
    print(row_dmid)

    # BANDAS
    for key in ['BB_UPPER', 'BB_MID', 'BB_LOWER']:
        row = f"║ {key[:8]:<10} ║"
        for tf in timeframes:
            sep = " ║ " if tf == '5m' else (" ║" if tf == '4h' else " │ ")
            val = matrix.get(tf, {}).get(key, 0)
            row += _pintar_valor('BB_VAL', val) + sep
        print(row)

    print(f"╠════════════╬─────────┼──────────┼──────────╬──────────┼──────────┼──────────┼──────────╣")

    # DIST BANDA
    row_dist = f"║ {'DIST BANDA':<10} ║"
    for tf in timeframes:
        sep = " ║ " if tf == '5m' else (" ║" if tf == '4h' else " │ ")
        data = matrix.get(tf, {})
        price = data.get('CLOSE', 0)
        mid = data.get('BB_MID', 0)
        upper = data.get('BB_UPPER', 0)
        lower = data.get('BB_LOWER', 0)
        
        dist = 0; contexto = 'MID'
        if price > mid: 
            dist = upper - price
            contexto = 'UPPER'
        else: 
            dist = price - lower
            contexto = 'LOWER'
            
        row_dist += _pintar_valor('BB_DIST_LIMIT', dist, contexto) + sep
    print(row_dist)

    print(f"╚════════════╩═════════╧══════════╧══════════╩══════════╧══════════╧══════════╧══════════╝{Style.RESET_ALL}")

# --- FUNCIÓN CORREGIDA ---
def mostrar_panel(df_scalp, df_swing, vol_score, mensaje_estrategia, modo, posicion, ordenes, mom_ratio, mom_chg, mtf_data=None, start_time=None, total_trades=0, notificaciones=[], pnl_acumulado=0.0, triggers_activos={}, ordenes_pendientes_op=[]):
    limpiar_pantalla()
    
    last_p = df_scalp.iloc[-1]['close']
    uptime = str(datetime.now() - start_time).split('.')[0] if start_time else "0:00:00"
    c_pnl_global = Fore.GREEN if pnl_acumulado > 0 else (Fore.RED if pnl_acumulado < 0 else Fore.WHITE)

    print(f"{Fore.BLUE}=========================================================================================================={Style.RESET_ALL}")
    print(f"   SENTINEL AI - {modo} | {Fore.YELLOW}PRECIO: {last_p:.2f}{Fore.BLUE} | VOL SCORE: {vol_score:.2f}")
    print(f"{Fore.BLUE}=========================================================================================================={Style.RESET_ALL}")
    print(f"   ⏱️  TIEMPO: {Fore.CYAN}{uptime}{Style.RESET_ALL} | 🔢 OPS: {Fore.CYAN}{total_trades}{Style.RESET_ALL} | 📜 ORD: {Fore.YELLOW}{len(ordenes)}{Style.RESET_ALL} | 💰 PnL: {c_pnl_global}{pnl_acumulado:.2f} USDT{Style.RESET_ALL}")
    print(f"{Fore.BLUE}----------------------------------------------------------------------------------------------------------{Style.RESET_ALL}")

    modes_display = []
    for m in ['MOMENTUM', 'SCALP', 'SWING']:
        status = f"{Fore.LIGHTBLACK_EX}INACTIVO{Style.RESET_ALL}"
        if m in triggers_activos:
            status = f"{Fore.MAGENTA}🔥 ARMADO ({triggers_activos[m]}){Style.RESET_ALL}"
        modes_display.append(f"{m}: {status}")
    
    print(f"   MODOS: {' | '.join(modes_display)}")

    if ordenes_pendientes_op:
        op_list = []
        for op in ordenes_pendientes_op:
            if op['active']:
                color_op = Fore.GREEN if op['type'] == 'LONG' else Fore.RED
                op_str = f"{color_op}{op['type']} @ {op['price']:.2f}{Style.RESET_ALL} ({op['dist_pct']}%)"
                op_list.append(op_str)
        
        if op_list:
            print(f"   🎯 OP ESPERA: {' | '.join(op_list)}")
            
    print(f"{Fore.BLUE}----------------------------------------------------------------------------------------------------------{Style.RESET_ALL}")

    if notificaciones:
        print(f"\n{Fore.YELLOW}🔔 NOTIFICACIONES RECIENTES:{Style.RESET_ALL}")
        for nota in notificaciones: print(f"   > {nota}")
        print(f"{Fore.BLUE}----------------------------------------------------------------------------------------------------------{Style.RESET_ALL}")

    if posicion:
        pnl_u = (last_p - posicion['entrada']) * posicion['cantidad']
        if posicion['tipo'] == 'SHORT': pnl_u *= -1
        
        be_price = posicion['entrada'] * (1.001 if posicion['tipo']=='LONG' else 0.999) 
        
        fee_rate = 0.0005 
        val_entry = posicion['entrada'] * posicion['cantidad']
        val_exit = last_p * posicion['cantidad']
        est_fees = (val_entry * fee_rate) + (val_exit * fee_rate)
        
        c_pnl = Fore.GREEN if pnl_u > 0 else Fore.RED
        
        print(f"\n{Fore.GREEN}💎 POSICIÓN ({posicion['strategy']}):{Style.RESET_ALL}")
        print(f"   {posicion['tipo']} x{posicion.get('cantidad',0)} @ {posicion['entrada']:.2f}")
        print(f"   Valor: ${val_entry:.2f} | B/E Est.: {be_price:.2f} | {Fore.RED}Coms: -${est_fees:.2f}{Style.RESET_ALL}")
        print(f"   TP: {posicion['tp']:.2f} | SL: {posicion['sl']:.2f}")
        print(f"   PnL: {c_pnl}{pnl_u:.2f} USDT{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.CYAN}💤 ESPERANDO OPORTUNIDAD... (Enter para forzar gatillo){Style.RESET_ALL}")
        
    if ordenes:
        print(f"\n{Fore.YELLOW}📜 Órdenes ({len(ordenes)}):{Style.RESET_ALL}")
        for o in ordenes[:5]:
            p = float(o.get('price', 0))
            if p == 0: p = float(o.get('stopPrice', 0))
            print(f"   [{o['type']}] {o['side']} @ {p:.2f}")

    if mtf_data:
        print("\n")
        mostrar_mtf_table(mtf_data)