import os
from colorama import Fore, Style, Back, init
from datetime import datetime

init(autoreset=True)

class Dashboard:
    def __init__(self):
        self.logs = []

    def add_log(self, msg, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {msg}")
        if len(self.logs) > 4: self.logs.pop(0)

    # ... (MANTENER MÉTODOS DE PINTURA IGUAL QUE ANTES: _pintar_rsi, _pintar_stoch, etc.) ...
    def _pintar_rsi(self, val):
        val_str = f"{val:.1f}"
        if val >= 70: return f"{Fore.RED}{Style.BRIGHT}{val_str:^7}{Style.RESET_ALL}"
        if val <= 30: return f"{Fore.GREEN}{Style.BRIGHT}{val_str:^7}{Style.RESET_ALL}"
        return f"{val_str:^7}"
        
    def _pintar_stoch(self, val):
        val_str = f"{val:.1f}"
        if val >= 80: return f"{Fore.RED}{val_str:^7}{Style.RESET_ALL}"
        if val <= 20: return f"{Fore.GREEN}{val_str:^7}{Style.RESET_ALL}"
        return f"{val_str:^7}"

    def _pintar_adx(self, val):
        val_str = f"{val:.1f}"
        if val > 25: return f"{Fore.YELLOW}{Style.BRIGHT}{val_str:^7}{Style.RESET_ALL}"
        return f"{Fore.LIGHTBLACK_EX}{val_str:^7}{Style.RESET_ALL}"

    def _pintar_pnl(self, val):
        color = Fore.GREEN if val >= 0 else Fore.RED
        return f"{color}{val:>8.2f} USDT{Style.RESET_ALL}"

    def _pintar_dist_mid(self, val):
        color = Fore.GREEN if val >= 0 else Fore.RED
        return f"{color}{val:^7.2f}{Style.RESET_ALL}"

    def _pintar_dist_lim(self, dist, context):
        txt = f"{dist:.2f}"
        if dist < 0:
            if context == 'UPPER': return f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}{txt:^7}{Style.RESET_ALL}"
            else: return f"{Back.GREEN}{Fore.WHITE}{Style.BRIGHT}{txt:^7}{Style.RESET_ALL}"
        return f"{Fore.LIGHTBLACK_EX}{txt:^7}{Style.RESET_ALL}"
    
    def _status(self, connected):
        return f"{Fore.GREEN}● ONLINE{Style.RESET_ALL}" if connected else f"{Fore.RED}● OFFLINE{Style.RESET_ALL}"

    def render(self, price, mtf_data, daily_stats, positions, financials, connections, brain_msg, session_stats):
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # HEADER
        print(f"{Back.BLUE}{Fore.WHITE} 🛡️ SENTINEL AI PRO {Style.RESET_ALL}")
        print(f" 💵 PRECIO: {Fore.YELLOW}{Style.BRIGHT}{price:.2f}{Style.RESET_ALL} │ BINANCE: {self._status(connections['binance'])} │ TELEGRAM: {self._status(connections['telegram'])}")
        
        # ESTADÍSTICAS DIARIAS
        print("-" * 92)
        d_high = daily_stats.get('curr_high', 0)
        d_low = daily_stats.get('curr_low', 0)
        p_high = daily_stats.get('prev_high', 0)
        p_low = daily_stats.get('prev_low', 0)
        print(f" 📅 DÍA ACTUAL:  Max {Fore.GREEN}{d_high:.2f}{Style.RESET_ALL} │ Min {Fore.RED}{d_low:.2f}{Style.RESET_ALL}")
        print(f" ⏪ DÍA PREVIO:  Max {Fore.GREEN}{p_high:.2f}{Style.RESET_ALL} │ Min {Fore.RED}{p_low:.2f}{Style.RESET_ALL}")
        
        # MATRIZ MULTI-TEMPORAL
        print("-" * 92)
        if mtf_data:
            tfs = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d']
            print(f"{Fore.CYAN} 📊 MATRIZ MULTI-TEMPORAL{Style.RESET_ALL}")
            
            header = f" {'IND':<6} │"
            for tf in tfs: header += f" {tf:^7} │"
            print(header)
            print(" " + "─"*6 + "┼" + ("─"*9 + "┼") * 8)
            
            row_rsi = f" {'RSI':<6} │"
            row_stoch = f" {'STOCH':<6} │"
            row_adx = f" {'ADX':<6} │"
            row_bbw = f" {'BB_W':<6} │"
            
            row_bb_up = f" {'BB_UP':<6} │"
            row_bb_lo = f" {'BB_LO':<6} │"
            row_dmid = f" {'D.MID':<6} │"
            row_dlim = f" {'D.LIM':<6} │"
            
            for tf in tfs:
                d = mtf_data.get(tf, {})
                close_p = d.get('CLOSE', price)
                
                row_rsi += f" {self._pintar_rsi(d.get('RSI', 50))} │"
                row_stoch += f" {self._pintar_stoch(d.get('STOCH_RSI', 50))} │"
                row_adx += f" {self._pintar_adx(d.get('ADX', 0))} │"
                row_bbw += f"{Fore.CYAN}{d.get('BB_WIDTH',0):^7.2f}{Style.RESET_ALL} │"
                
                row_bb_up += f"{Fore.LIGHTBLACK_EX}{d.get('BB_UPPER',0):^7.1f}{Style.RESET_ALL} │"
                row_bb_lo += f"{Fore.LIGHTBLACK_EX}{d.get('BB_LOWER',0):^7.1f}{Style.RESET_ALL} │"
                
                mid = d.get('BB_MID', 0)
                dist_mid = close_p - mid
                row_dmid += f" {self._pintar_dist_mid(dist_mid)} │"
                
                upper = d.get('BB_UPPER', 0)
                lower = d.get('BB_LOWER', 0)
                if dist_mid >= 0:
                    dist_lim = upper - close_p 
                    row_dlim += f" {self._pintar_dist_lim(dist_lim, 'UPPER')} │"
                else:
                    dist_lim = close_p - lower
                    row_dlim += f" {self._pintar_dist_lim(dist_lim, 'LOWER')} │"

            print(row_rsi)
            print(row_stoch)
            print(row_adx)
            print(row_bbw)
            print(" " + "─"*6 + "┼" + ("─"*9 + "┼") * 8)
            print(row_bb_up)
            print(row_bb_lo)
            print(row_dmid)
            print(row_dlim)
        
        # TABLA DE POSICIONES
        print("-" * 92)
        print(f"{Fore.CYAN} 💎 POSICIONES ACTIVAS ({len(positions)}){Style.RESET_ALL}")
        
        if not positions:
            print(f"   {Fore.LIGHTBLACK_EX}(Esperando entrada...){Style.RESET_ALL}")
        else:
            print(f" {'ID':<8} {'TIPO':<5} {'ENTRADA':<9} {'CANT':<6} {'USDT':<7} {'COMIS':<6} {'PRECIO BE':<9} {'PNL':<12} {'ESTADO'}")
            for pid, pos in positions.items():
                d = pos['data']
                entry_p = d.get('entry_price', 0)
                qty = d.get('qty', 0)
                side = d.get('side', 'FLAT')
                
                val_usdt = d.get('usdt_value', qty * entry_p)
                comision_est = val_usdt * 0.0005 * 2
                
                be_price = entry_p * (1.001 if side=='LONG' else 0.999)
                
                # --- CORRECCIÓN AQUÍ: .get('pnl_actual', 0.0) ---
                pnl_val = pos.get('pnl_actual', 0.0)
                
                print(f" {pid:<8} {side:<5} {entry_p:<9.2f} {qty:<6.2f} {val_usdt:<7.1f} {comision_est:<6.2f} {be_price:<9.2f} {self._pintar_pnl(pnl_val)} {pos['status']}")

        # FOOTER
        print("-" * 92)
        total_ops = session_stats['wins'] + session_stats['losses']
        win_rate = (session_stats['wins'] / total_ops * 100) if total_ops > 0 else 0
        pnl_neto = getattr(financials, 'daily_pnl', 0.0)

        print(f" 📈 SESIÓN: Ops: {total_ops} (Gan: {session_stats['wins']} / Per: {session_stats['losses']}) │ WinRate: {win_rate:.1f}%")
        print(f" 💰 PnL Neto Sesión: {self._pintar_pnl(pnl_neto)}")
        print("-" * 92)
        print(f" 🧠 CEREBRO: {brain_msg}")
        print(f"{Fore.MAGENTA} 📝 ACTIVIDAD RECIENTE:{Style.RESET_ALL}")
        for l in self.logs:
            print(f" > {l}")
        print(f"{Fore.LIGHTBLACK_EX} ℹ️  Sistema operando en modo {financials.cfg.MODE}...{Style.RESET_ALL}")