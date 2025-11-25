# strategies.py
import csv
import os
import time
import keyboard
import threading
import concurrent.futures
from datetime import datetime
from colorama import Fore, Style
import utils
import pandas as pd

# Importamos los modos de decisión
from modes import ScalpMode, SwingMode, MomentumMode

class TradingStats:
    """
    Motor Híbrido: Lleva conteo en vivo Y audita con Binance al final.
    """
    def __init__(self, connector):
        self.conn = connector
        self.start_ts_ms = int(time.time() * 1000)
        self.start_dt = datetime.now()
        
        # --- MEMORIA EN VIVO (Restaurada) ---
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self.trade_history = []

    def registrar(self, tipo, pnl, estrategia):
        """Registra operación en memoria RAM para métricas en vivo."""
        self.total_trades += 1
        
        if pnl > 0: 
            self.wins += 1
            self.gross_profit += pnl
        else: 
            self.losses += 1
            self.gross_loss += abs(pnl)

        self.trade_history.append({
            'hora': datetime.now().strftime('%H:%M:%S'), 
            'tipo': tipo, 
            'strat': estrategia, 
            'pnl': pnl
        })

    def obtener_reporte_forense(self):
        """Consulta la verdad absoluta a la API de Binance al cerrar."""
        if self.conn.cfg.MODE == 'SIMULATION': 
            return self._obtener_reporte_simulado()
            
        duration = datetime.now() - self.start_dt
        print(f"\n{Fore.YELLOW}⏳ Descargando auditoría de la Blockchain...{Style.RESET_ALL}")
        
        try:
            orders = self.conn.obtener_ordenes_historicas(self.start_ts_ms)
            trades = self.conn.obtener_trades_historicos(self.start_ts_ms)
            
            filled = [o for o in orders if o['status'] == 'FILLED']
            realized_pnl = sum([float(t['realizedPnl']) for t in trades])
            commissions = sum([float(t['commission']) for t in trades]) # Ojo: Puede estar en BNB
            net_pnl = realized_pnl - commissions
            
            color_pnl = Fore.GREEN if net_pnl >= 0 else Fore.RED
            
            tabla = ""
            for o in orders[-15:]: 
                ts = datetime.fromtimestamp(o['updateTime']/1000).strftime('%H:%M:%S')
                s = o['status']
                c = Fore.GREEN if s=='FILLED' else (Fore.RED if s=='CANCELED' else Fore.WHITE)
                price = float(o.get('avgPrice', 0))
                if price == 0 and 'stopPrice' in o: price = f"Trig: {o['stopPrice']}"
                
                tabla += f"   {ts} | {o['type']:<10} | {o['side']:<4} | {c}{s:<8}{Style.RESET_ALL} | {price}\n"

            return f"""
            {Fore.CYAN}=============================================================
            📊 REPORTE FORENSE (BINANCE API)
            ============================================================={Style.RESET_ALL}
            ⏱️  Tiempo: {str(duration).split('.')[0]}
            🔢  Órdenes: {len(orders)} Total | {len(filled)} Ejecutadas
            💰  PnL NETO: {color_pnl}{Style.BRIGHT}{net_pnl:.4f} USDT{Style.RESET_ALL} (Comis: {commissions:.4f})
            
            📜  TRAZA RECIENTE:
            {tabla}
            """
        except Exception as e:
            return f"Error generando reporte forense: {e}. Usando datos locales: PnL {self.gross_profit - self.gross_loss}"

    def _obtener_reporte_simulado(self):
        net = self.gross_profit - self.gross_loss
        return f"Reporte Simulado: PnL {net:.2f} | Ops: {self.total_trades}"

class TradingManager:
    def __init__(self, config, connector):
        self.cfg = config
        self.conn = connector 
        self.step_size = connector.step_size
        self.posicion_abierta = None 
        self.last_closure_time = None
        self.consecutive_losses = 0
        self.dca_level = 0
        self.stats = TradingStats(connector)
        self._inicializar_csv()
        
        if self.cfg.MODE in ['TESTNET', 'LIVE']: 
            self._sincronizar_estado_inicial()

    def _sincronizar_estado_inicial(self):
        try:
            pos_data = self.conn.obtener_posicion_abierta()
            if pos_data and isinstance(pos_data, dict) and pos_data.get('positionAmt'):
                amt = float(pos_data['positionAmt'])
                if amt != 0:
                    side = 'LONG' if amt > 0 else 'SHORT'
                    entry = float(pos_data['entryPrice'])
                    print(f"{Fore.YELLOW}[MEMORIA] Restaurando {side}...{Style.RESET_ALL}")
                    
                    sl_pct = self.cfg.SCALP_SL_PCT
                    tp_def = 0.01 
                    if side == 'LONG': 
                        sl = entry*(1-sl_pct); tp = entry*(1+tp_def)
                    else: 
                        sl = entry*(1+sl_pct); tp = entry*(1-tp_def)

                    self.posicion_abierta = {
                        'tipo': side, 'entrada': entry, 'cantidad': abs(amt),
                        'tp': tp, 'sl': sl, 'motivo': "RECUPERADO", 
                        'strategy': 'RECOVERED', 'break_even_activado': False, 
                        'best_price': entry, 'sl_order_id': None, 'tp_order_id': None
                    }
                    print(f"{Fore.CYAN}[RECUPERACIÓN] Enviando protecciones...{Style.RESET_ALL}")
                    self._actualizar_ordenes_proteccion(self.posicion_abierta)
        except Exception: pass

    def _inicializar_csv(self):
        if not os.path.exists(self.cfg.TRADES_FILE):
            with open(self.cfg.TRADES_FILE, 'w', newline='') as f:
                csv.writer(f).writerow(['Time', 'Type', 'Entry', 'Qty', 'Strat', 'TP', 'SL', 'Status', 'PnL'])

    def _actualizar_ordenes_proteccion(self, pos):
        if self.cfg.MODE not in ['TESTNET', 'LIVE']: return
        
        if pos.get('sl_order_id'): self.conn.cancelar_orden(pos['sl_order_id']); pos['sl_order_id'] = None
        if pos.get('tp_order_id'): self.conn.cancelar_orden(pos['tp_order_id']); pos['tp_order_id'] = None

        side_cierre = 'SELL' if pos['tipo'] == 'LONG' else 'BUY'
        pos_side = 'LONG' if pos['tipo'] == 'LONG' else 'SHORT'
        qty = pos['cantidad']
        
        def enviar_sl():
            if pos['sl'] > 0:
                res = self.conn.colocar_orden_sl_tp(side_cierre, qty, pos['sl'], pos_side, 'STOP_MARKET')
                if res: pos['sl_order_id'] = res['orderId']

        def enviar_tp():
            if pos['tp'] > 0:
                res = self.conn.colocar_orden_sl_tp(side_cierre, qty, pos['tp'], pos_side, 'TAKE_PROFIT_MARKET')
                if res: pos['tp_order_id'] = res['orderId']

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(enviar_sl)
            executor.submit(enviar_tp)

    def abrir_orden(self, tipo, precio_ref, tp, sl, motivo, estrategia='SCALP', es_dca=False):
        leverage = self.cfg.LEVERAGE_SWING if estrategia == 'SWING' else (self.cfg.LEVERAGE_MOMENTUM if estrategia == 'MOMENTUM' else self.cfg.LEVERAGE_SCALP)
        pct = self.cfg.SIZE_SWING if estrategia == 'SWING' else (self.cfg.SIZE_MOMENTUM if estrategia == 'MOMENTUM' else self.cfg.SIZE_SCALP)
        if es_dca: pct = self.cfg.SIZE_SCALP
        
        qty = utils.calcular_cantidad_ajustada(precio_ref, self.cfg.CAPITAL_TRABAJO * pct * leverage, self.step_size)
        if qty == 0: return print(f"{Fore.RED}Error Qty 0{Style.RESET_ALL}")

        side = 'BUY' if tipo == 'LONG' else 'SELL'
        pos_side = 'LONG' if tipo == 'LONG' else 'SHORT'
        precio_entrada_real = 0.0

        if self.cfg.MODE in ['TESTNET', 'LIVE']:
            if estrategia == 'MOMENTUM' or es_dca:
                order = self.conn.colocar_orden_market(side, qty, pos_side)
                if not order: return
                precio_entrada_real = precio_ref 
            else: 
                print(f"{Fore.YELLOW}⏳ Limit Chase...{Style.RESET_ALL}")
                orden_llenada = False
                for i in range(3): 
                    p_limit = self.conn.obtener_mejor_precio_libro(side)
                    if not p_limit: break
                    orden = self.conn.colocar_orden_limit(side, qty, p_limit, pos_side)
                    if not orden: continue
                    oid = orden['orderId']
                    time.sleep(1) 
                    for _ in range(4):
                        if self.conn.verificar_estado_orden(oid) == 'FILLED':
                            orden_llenada = True; precio_entrada_real = p_limit; break
                        time.sleep(0.5)
                    if orden_llenada: 
                        print(f"   {Fore.GREEN}✅ Orden Llenada!{Style.RESET_ALL}")
                        break
                    self.conn.cancelar_orden(oid) 
                
                if not orden_llenada: 
                    print(f"{Fore.RED}❌ Falló Limit Chase.{Style.RESET_ALL}")
                    return
        else: 
            precio_entrada_real = precio_ref

        if self.posicion_abierta:
            pos = self.posicion_abierta
            if self.posicion_abierta['strategy'] != 'SCALP' and estrategia != self.posicion_abierta['strategy']: return
            if self.posicion_abierta['tipo'] != tipo: return
            new_qty = pos['cantidad'] + qty
            new_entry = ((pos['entrada']*pos['cantidad']) + (precio_entrada_real*qty)) / new_qty
            pos.update({'entrada': new_entry, 'cantidad': new_qty, 'break_even_activado': False})
            if es_dca: self.dca_level += 1
            self._actualizar_ordenes_proteccion(pos)
        else:
            dist_tp = abs(tp - precio_ref); dist_sl = abs(sl - precio_ref)
            rtp = precio_entrada_real + dist_tp if tipo=='LONG' else precio_entrada_real - dist_tp
            rsl = precio_entrada_real - dist_sl if tipo=='LONG' else precio_entrada_real + dist_sl
            
            self.posicion_abierta = {
                'tipo': tipo, 'entrada': precio_entrada_real, 'cantidad': qty, 
                'tp': rtp, 'sl': rsl,
                'motivo': motivo, 'strategy': estrategia, 
                'break_even_activado': False, 'best_price': precio_entrada_real, 
                'sl_order_id': None, 'tp_order_id': None
            }
            self._actualizar_ordenes_proteccion(self.posicion_abierta)
            lev_tag = f"x{leverage}"
            print(f"{Fore.MAGENTA}>>> [{tipo}] {estrategia} {lev_tag} OPEN @ {precio_entrada_real:.2f}{Style.RESET_ALL}")

    def verificar_salidas(self, precio):
        if not self.posicion_abierta: return None
        
        if self.cfg.MODE in ['TESTNET', 'LIVE']:
            if self._verificar_cierre_externo(precio):
                return "CERRADO_POR_BINANCE"
        
        pos = self.posicion_abierta
        if pos['strategy'] == 'SCALP' and self.cfg.ENABLE_AUTO_DCA and self.dca_level < self.cfg.MAX_DCA_LEVELS:
            trig = 1 - self.cfg.DCA_TRIGGER_PCT if pos['tipo'] == 'LONG' else 1 + self.cfg.DCA_TRIGGER_PCT
            if (pos['tipo']=='LONG' and precio<=pos['entrada']*trig) or (pos['tipo']=='SHORT' and precio>=pos['entrada']*trig):
                self.abrir_orden(pos['tipo'], precio, pos['entrada'], pos['sl'], "AUTO_DCA", 'SCALP', True)
                return "DCA EJECUTADO"

        return self._gestionar_riesgo(precio, pos)

    def _verificar_cierre_externo(self, precio_actual):
        pos_real = self.conn.obtener_posicion_abierta()
        if pos_real is None: return False
        
        if not pos_real:
            pos = self.posicion_abierta
            if pos:
                # Calculamos PnL estimado
                pnl_estimado = (precio_actual - pos['entrada']) * pos['cantidad']
                if pos['tipo'] == 'SHORT': pnl_estimado *= -1
                
                # REGISTRO EN MEMORIA PARA EL ERROR QUE TUVISTE
                self.stats.registrar(pos['tipo'], pnl_estimado, pos.get('strategy', 'SCALP'))
                
                self._registrar_log(pos, precio_actual, pnl_estimado, "TP/SL_BINANCE")
                print(f"{Fore.GREEN}>>> Cierre externo detectado. PnL Est: {pnl_estimado:.2f}{Style.RESET_ALL}")
            
            if self.cfg.MODE in ['TESTNET', 'LIVE']:
                self.conn.cancelar_todas_ordenes()
            
            self.posicion_abierta = None
            return True
        return False

    def _gestionar_riesgo(self, precio, pos):
        strat = pos.get('strategy', 'SCALP')
        if strat == 'SWING': be_trig = self.cfg.SWING_BE; trail = self.cfg.SWING_TRAIL
        elif strat == 'MOMENTUM': be_trig = self.cfg.MOMENTUM_BE_TRIGGER; trail = self.cfg.MOMENTUM_TRAIL_DIST
        else: be_trig = self.cfg.SCALP_BE_TRIGGER; trail = self.cfg.SCALP_TRAIL_DIST
        
        changed = False; msg = None
        if pos['entrada'] == 0: return None
        pnl_pct = (precio - pos['entrada'])/pos['entrada'] if pos['tipo']=='LONG' else (pos['entrada'] - precio)/pos['entrada']
        
        if pnl_pct >= be_trig and not pos['break_even_activado']:
            pos['sl'] = pos['entrada'] * (1.001 if pos['tipo']=='LONG' else 0.999)
            pos['break_even_activado'] = True; changed = True; msg = "B/E ACTIVADO"
        
        update_trail = False
        if strat == 'MOMENTUM' and pnl_pct > 0: update_trail = True
        elif pos['break_even_activado']: update_trail = True
            
        if update_trail:
            if pos['tipo'] == 'LONG':
                pos['best_price'] = max(pos['best_price'], precio)
                n_sl = pos['best_price'] * (1 - trail)
                if n_sl > pos['sl']: pos['sl'] = n_sl; changed = True; msg = "TRAILING UPDATE"
            else:
                pos['best_price'] = min(pos['best_price'], precio)
                n_sl = pos['best_price'] * (1 + trail)
                if n_sl < pos['sl']: pos['sl'] = n_sl; changed = True; msg = "TRAILING UPDATE"
        
        if changed: self._actualizar_ordenes_proteccion(pos)
        return msg

    def forzar_cierre_scalping(self, precio_actual):
        if self.posicion_abierta and self.posicion_abierta.get('strategy') != 'SWING':
            print(f"{Fore.YELLOW}[PRIORIDAD] Cerrando Scalping...{Style.RESET_ALL}")
            self._cerrar_orden("SWING_OVERRIDE", precio_actual)
            return True
        return False

    def cerrar_posicion_panico(self, p):
        if self.posicion_abierta: self._cerrar_orden("PANIC", p)

    def _cerrar_orden(self, motivo, precio_salida, orden_ejecutada_en_binance=False):
        pos = self.posicion_abierta
        if self.cfg.MODE in ['TESTNET', 'LIVE']:
            if not orden_ejecutada_en_binance and motivo != "CERRADO_POR_BINANCE":
                side = 'SELL' if pos['tipo'] == 'LONG' else 'BUY'
                pos_side = 'LONG' if pos['tipo'] == 'LONG' else 'SHORT'
                self.conn.colocar_orden_market(side, pos['cantidad'], pos_side)
            self.conn.cancelar_todas_ordenes()
        
        # Calculo PnL
        pnl = (precio_salida - pos['entrada']) * pos['cantidad'] * (1 if pos['tipo']=='LONG' else -1)
        
        self.stats.registrar(pos['tipo'], pnl, pos.get('strategy', 'SCALP'))
        print(f"{Fore.GREEN}>>> CERRADO {motivo} | PnL: {pnl:.2f}{Style.RESET_ALL}")
        self._registrar_log(pos, precio_salida, pnl, motivo)
        self.posicion_abierta = None

    def _registrar_log(self, pos, exit_price, pnl, motivo): 
        try:
            with open(self.cfg.TRADES_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([datetime.now().strftime('%H:%M:%S'), pos['tipo'], f"{pos['entrada']:.2f}", pos['cantidad'], pos.get('strategy', 'UNK'), f"{pos['tp']:.2f}", f"{pos['sl']:.2f}", motivo, f"{pnl:.2f}"])
        except: pass

class StrategyEngine:
    def __init__(self, config, connector):
        self.cfg = config
        self.trader = TradingManager(config, connector)
        self.COOLDOWN_SECONDS = 3 
        self.ultimo_precio = 0.0 
        self.scalp_mode = ScalpMode(config)
        self.swing_mode = SwingMode(config)
        self.mom_mode = MomentumMode(config)
        self._start_keys()
        
    def _start_keys(self):
        def run():
            try:
                for i in range(1, 10):
                    keyboard.add_hotkey(f'c+{i}', lambda x=i: self._manual('LONG', x))
                    keyboard.add_hotkey(f'v+{i}', lambda x=i: self._manual('SHORT', x))
                keyboard.add_hotkey('z+x+0', lambda: self.trader.cerrar_posicion_panico(self.ultimo_precio))
                keyboard.wait() 
            except: pass
        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _manual(self, tipo, multi):
        p = self.ultimo_precio
        if p == 0: return
        tp = p * 1.01 if tipo=='LONG' else p * 0.99
        sl = p * 0.995 if tipo=='LONG' else p * 1.005
        self.trader.abrir_orden(tipo, p, tp, sl, f"MANUAL x{multi}", 'SCALP', False)

    def ejecutar_estrategia(self, df_scalp, df_swing, roll_min, roll_max, precio):
        last_s = df_scalp.iloc[-1]; last_w = df_swing.iloc[-1]; self.ultimo_precio = precio
        
        res = self.trader.verificar_salidas(precio)
        if res: return f"Gestionando: {res}"

        if self.trader.last_closure_time and (datetime.now() - self.trader.last_closure_time).total_seconds() < self.COOLDOWN_SECONDS: return "Cooldown..."

        # Prioridad 1: Momentum
        mom_signal, mom_data = self.mom_mode.evaluar(precio)
        if mom_signal:
            if not self.trader.posicion_abierta:
                self.trader.abrir_orden(mom_signal, precio, mom_data['tp_price'], mom_data['sl_price'], mom_data['motivo'], 'MOMENTUM')
                return f"🚀 MOMENTUM {mom_signal}"

        # Prioridad 2: Swing
        swing_signal, swing_data = self.swing_mode.evaluar(df_swing, precio)
        if swing_signal:
            if not self.trader.posicion_abierta or self.trader.posicion_abierta.get('strategy') != 'SWING':
                self.trader.forzar_cierre_scalping(precio)
                if swing_signal == 'LONG': tp = roll_max; sl = precio * swing_data['sl_factor']
                else: tp = roll_min; sl = precio * swing_data['sl_factor']
                self.trader.abrir_orden(swing_signal, precio, tp, sl, swing_data['motivo'], 'SWING')
                return f"ENTRADA SWING {swing_signal}"

        if self.trader.posicion_abierta and self.trader.posicion_abierta.get('strategy') == 'SWING': return "MONITOREO SWING..."

        # Prioridad 3: Scalp
        signal, info = self.scalp_mode.evaluar(df_scalp, precio)
        if signal: 
            if signal == 'LONG': tp = roll_max * (1 - info['tp_offset']); sl = info['sl_price']
            else: tp = roll_min * (1 + info['tp_offset']); sl = info['sl_price']
            self.trader.abrir_orden(signal, precio, tp, sl, info['motivo'], 'SCALP')
            return f"DISPARO SCALP {signal}"
            
        return info if info else "Escaneo Triple..."