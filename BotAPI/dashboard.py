# dashboard.py
from colorama import Fore, Back, Style
from datetime import datetime 
import os
import sys

_first_run = True

def mostrar_panel(df_scalp, df_swing, vol_score, funcion_activa, modo, trader_state, open_orders_real, mom_ratio, mom_chg):
    global _first_run
    if _first_run: 
        os.system('cls' if os.name == 'nt' else 'clear')
        _first_run = False
    
    print("\033[H", end="")
    
    last_s = df_scalp.iloc[-1]
    last_w = df_swing.iloc[-1]
    ahora = datetime.now().strftime('%H:%M:%S')
    
    trend_s = f"{Fore.GREEN}ALCISTA" if last_s['MA7'] > last_s['MA25'] else f"{Fore.RED}BAJISTA"
    trend_w = f"{Fore.GREEN}ALCISTA" if last_w['MA7'] > last_w['MA25'] else f"{Fore.RED}BAJISTA"
    
    def c_rsi(v, s): 
        return Fore.RED if (s and v>75) or (not s and v>70) else Fore.GREEN if (s and v<25) or (not s and v<30) else Fore.WHITE

    # HEADER
    print(f"{Back.BLUE}{Fore.WHITE}=== SENTINEL PRO DUAL ({modo}) - {ahora} ==={Style.RESET_ALL}".center(80))
    print(f" PRECIO ACTUAL: {Fore.YELLOW}{Style.BRIGHT}{last_s['close']:.2f}{Style.RESET_ALL}".center(80))
    print("-" * 78)
    
    # COLUMNAS TÉCNICAS
    print(f"{Fore.CYAN}{'   ⚡ MOTOR SCALPING (1m)':<38} | {Fore.MAGENTA}{'   🌊 MOTOR SWING (15m)':<38}{Style.RESET_ALL}")
    print("-" * 78)
    
    print(f" Tendencia: {trend_s:<26}{Style.RESET_ALL} |  Tendencia: {trend_w:<26}{Style.RESET_ALL}")
    
    rsi_s_txt = f"{c_rsi(last_s['RSI'],1)}{last_s['RSI']:.1f}"
    rsi_w_txt = f"{c_rsi(last_w['RSI'],0)}{last_w['RSI']:.1f}"
    print(f" RSI:       {rsi_s_txt}{Style.RESET_ALL:<26} |  RSI:       {rsi_w_txt}{Style.RESET_ALL}")

    print(f" Stoch K:   {last_s['StochRSI_k']:<26.2f} |  Stoch K:   {last_w['StochRSI_k']:.2f}")
    print(f" MA99:      {last_s['MA99']:<26.1f} |  MA99:      {last_w['MA99']:.1f}")
    print("-" * 78)

    # --- NUEVA SECCIÓN MOMENTUM ---
    # Umbrales visuales (Referencia visual hardcodeada basada en config típica)
    c_mom_vol = Fore.GREEN if mom_ratio > 2.5 else Fore.WHITE
    c_mom_chg = Fore.GREEN if abs(mom_chg) > 0.25 else Fore.WHITE
    
    print(f"   🚀 {Style.BRIGHT}MOTOR MOMENTUM (Inercia en Tiempo Real):{Style.RESET_ALL}")
    print(f"      Volumen Relativo: {c_mom_vol}x{mom_ratio:.2f}{Style.RESET_ALL} (Meta: >2.5x)")
    print(f"      Explosividad 1m:  {c_mom_chg}{mom_chg:+.2f}%{Style.RESET_ALL} (Meta: >0.25%)")
    print("-" * 78)
    
    # FOOTER
    c_vol = Fore.GREEN if vol_score > 20 else Fore.RED
    estado = f"{Fore.YELLOW}ARMADO{Style.RESET_ALL}" if "GATILLO" in funcion_activa else "ESPERANDO"
    print(f" 📊 Score Vol (Scalp): {c_vol}{vol_score}%{Style.RESET_ALL} | STATUS: {estado} | MSG: {funcion_activa}")
    print("=" * 78)
    
    # PANEL POSICIÓN
    if trader_state:
        t = trader_state
        pnl = (last_s['close'] - t['entrada']) * t['cantidad'] * (1 if t['tipo']=='LONG' else -1)
        bg = Back.GREEN if pnl >= 0 else Back.RED
        
        print(f"{bg}{Fore.WHITE}  POSICIÓN INTERNA: {t['tipo']} ({t.get('strategy','UNK')}) {Style.RESET_ALL} PnL: {pnl:.2f}")
        print(f"  Entrada: {t['entrada']:.2f} | SL: {t['sl']:.2f} | TP: {t['tp']:.2f}")
        
        print(f"\n  {Fore.YELLOW}>>> ÓRDENES ACTIVAS EN BINANCE:{Style.RESET_ALL}")
        if open_orders_real:
            for o in open_orders_real:
                tipo = o['type']
                precio = o.get('stopPrice', o.get('price', '0'))
                print(f"   • {o['side']} {o['origQty']} | {tipo} @ {precio}")
        else:
            print(f"   {Fore.RED}[ALERTA] No hay órdenes de protección en Binance.{Style.RESET_ALL}")
    else:
        print(f"{Style.DIM}\n       [ NO HAY POSICIONES ABIERTAS ]\n{Style.RESET_ALL}")

    print("=" * 78)
    print("\033[J", end="")
    sys.stdout.flush()