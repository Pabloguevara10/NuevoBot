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
from modes import ScalpMode, SwingMode, MomentumMode

# --- UTILIDAD DE REINTENTO ---
def reintentar_api(intentos=3, delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_err = None
            for i in range(intentos):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    print(f"{Fore.YELLOW}[RED] Fallo intento {i+1}/{intentos}: {e}. Reintentando...{Style.RESET_ALL}")
                    time.sleep(delay)
            print(f"{Fore.RED}[RED] Fallo definitivo tras {intentos} intentos.{Style.RESET_ALL}")
            raise last_err
        return wrapper
    return decorator

class DataLogger:
    """
    NUEVA CLASE: Registra la salud del mercado paso a paso para análisis posterior.
    """
    def __init__(self, config):
        self.cfg = config
        self.last_log_time = 0
        self._inicializar()

    def _inicializar(self):
        if not os.path.exists(self.cfg.TELEMETRY_FILE):
            with open(self.cfg.TELEMETRY_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Cabeceras Detalladas para Excel
                headers = [
                    'Timestamp', 'Precio', 'Accion_Bot', 'Posicion_Actual',
                    # 1m (Momentum)
                    'RSI_1m', 'Stoch_1m', 'BB_Width_1m', 'BB_Pos_1m', 'Vol_1m',
                    # 5m (Scalp)
                    'RSI_5m', 'Stoch_5m', 'BB_Width_5m', 'BB_Pos_5m', 'Vol_5m',
                    # 15m (Swing)
                    'RSI_15m', 'Stoch_15m', 'BB_Width_15m', 'BB_Pos_15m',
                    # Momentum Speed
                    'Velocidad_Precio'
                ]
                writer.writerow(headers)

    def registrar_telemetria(self, precio, mtf_data, msg_estrategia, posicion_actual, momentum_speed):
        """Guarda una foto del mercado si ha pasado el tiempo configurado."""
        now = time.time()
        if now - self.last_log_time < self.cfg.TELEMETRY_INTERVAL:
            return # No es momento de guardar todavía

        try:
            # Extraer datos de forma segura
            d1 = mtf_data.get('1m', {})
            d5 = mtf_data.get('5m', {})
            d15 = mtf_data.get('15m', {})
            
            pos_str = "NINGUNA"
            if posicion_actual:
                pos_str = f"{posicion_actual['tipo']} ({posicion_actual['strategy']})"

            row = [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                f"{precio:.2f}",
                msg_estrategia,
                pos_str,
                # 1m
                f"{d1.get('RSI',0):.1f}", f"{d1.get('STOCH_RSI',0):.1f}", f"{d1.get('BB_WIDTH',0):.2f}", d1.get('BB_POS','-'), f"{d1.get('VOL_SCORE',0):.1f}",
                # 5m
                f"{d5.get('RSI',0):.1f}", f"{d5.get('STOCH_RSI',0):.1f}", f"{d5.get('BB_WIDTH',0):.2f}", d5.get('BB_POS','-'), f"{d5.get('VOL_SCORE',0):.1f}",
                # 15m
                f"{d15.get('RSI',0):.1f}", f"{d15.get('STOCH_RSI',0):.1f}", f"{d15.get('BB_WIDTH',0):.2f}", d15.get('BB_POS','-'),
                # Speed
                f"{momentum_speed:+.4f}%"
            ]
            
            with open(self.cfg.TELEMETRY_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
                
            self.last_log_time = now
            
        except Exception as e:
            print(f"[LOGGER ERROR] {e}")

class TradingStats:
    def __init__(self, connector):
        self.conn = connector
        self.start_ts_ms = int(time.time() * 1000)
        self.start_dt = datetime.now()
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0

    def registrar(self, tipo, pnl, estrategia):
        self.total_trades += 1
        if pnl > 0: 
            self.wins += 1
            self.gross_profit += pnl
        else: 
            self.losses += 1
            self.gross_loss += abs(pnl)

    def obtener_reporte_forense(self):
        if self.conn.cfg.MODE == 'SIMULATION': 
            return f"Reporte Simulado: PnL {self.gross_profit - self.gross_loss:.2f}"
            
        duration = datetime.now() - self.start_dt
        print(f"\n{Fore.YELLOW}⏳ Consultando Auditoría Binance...{Style.RESET_ALL}")
        try:
            trades = self.conn.obtener_trades_historicos(self.start_ts_ms)
            realized_pnl = sum([float(t['realizedPnl']) for t in trades])
            commissions = sum([float(t['commission']) for t in trades]) 
            net_pnl = realized_pnl - commissions
            color = Fore.GREEN if net_pnl >= 0 else Fore.RED
            return f"""
            {Fore.CYAN}=== REPORTE DE SESIÓN ==={Style.RESET_ALL}
            ⏱️ Duración: {str(duration).split('.')[0]}
            💰 PnL Neto (API): {color}{net_pnl:.4f} USDT{Style.RESET_ALL} (Comis: {commissions:.4f})
            """
        except Exception as e:
            return f"Error reporte: {e}"

class TradingManager:
    def __init__(self, config, connector):
        self.cfg = config
        self.conn = connector 
        self.step_size = connector.step_size
        self.posicion_abierta = None 
        self.last_closure_time = None
        self.dca_level = 0
        self.stats = TradingStats(connector)
        
        self._inicializar_bitacora()
        
        if self.cfg.MODE in ['TESTNET', 'LIVE']: 
            self._sincronizar_estado_inteligente()

    def _inicializar_bitacora(self):
        if not os.path.exists(self.cfg.TRADES_FILE):
            with open(self.cfg.TRADES_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Fecha_Hora', 'Estrategia', 'Tipo', 'Precio_Entrada', 'Cantidad', 
                    'Monto_USDT', 'Precio_Salida', 'PnL_USDT', 'Motivo_Cierre', 
                    'Proteccion_Validada', 'Trailing_Activado', 'Max_Exposure', 'Estado_Final'
                ])

    def _escribir_bitacora(self, datos):
        try:
            with open(self.cfg.TRADES_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(datos)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"{Fore.RED}[CRÍTICO] Error escribiendo bitácora: {e}{Style.RESET_ALL}")

    def _leer_ultima_operacion_csv(self):
        if not os.path.exists(self.cfg.TRADES_FILE): return None
        try:
            with open(self.cfg.TRADES_FILE, 'r', encoding='utf-8') as f:
                lines = list(csv.reader(f))
                if len(lines) > 1:
                    last = lines[-1]
                    if len(last) > 12 and last[12] == 'OPEN':
                        return {
                            'tipo': last[2], 
                            'entrada': float(last[3]), 
                            'cantidad': float(last[4]),
                            'estrategia': last[1]
                        }
        except: pass
        return None

    def _sincronizar_estado_inteligente(self):
        print(f"{Fore.YELLOW}🔄 Iniciando Protocolo de Sincronización...{Style.RESET_ALL}")
        memoria_csv = self._leer_ultima_operacion_csv()
        
        pos_real = None
        for i in range(self.cfg.MAX_API_RETRIES):
            try:
                pos_real = self.conn.obtener_posicion_abierta()
                break
            except Exception as e:
                print(f"   [Intento {i+1}] Error conectando API: {e}")
                time.sleep(self.cfg.RETRY_DELAY_SECONDS)
        
        if not pos_real or float(pos_real.get('positionAmt', 0)) == 0:
            if memoria_csv:
                print(f"{Fore.GREEN}✅ Sincronizado: La posición del CSV ya fue cerrada en Binance.{Style.RESET_ALL}")
            self.posicion_abierta = None
            return

        amt = float(pos_real['positionAmt'])
        entry_price = float(pos_real['entryPrice'])
        side = 'LONG' if amt > 0 else 'SHORT'
        mark_price = self.conn.obtener_precio_real()
        
        print(f"{Fore.MAGENTA}⚠️  ALERTA: Posición Activa Detectada en Binance: {side} {abs(amt)} @ {entry_price}{Style.RESET_ALL}")
        
        abiertas = self.conn.obtener_ordenes_abiertas()
        tiene_sl = any(o['type'] == 'STOP_MARKET' for o in abiertas)
        
        if tiene_sl:
            print(f"{Fore.GREEN}🛡️  Protecciones verificadas. Restaurando control.{Style.RESET_ALL}")
            self._reconstruir_memoria(side, entry_price, abs(amt), memoria_csv)
        else:
            print(f"{Fore.RED}☢️  PELIGRO: Sin Protecciones. Iniciando Rescate...{Style.RESET_ALL}")
            self._evaluar_rescate(side, entry_price, abs(amt), mark_price, memoria_csv)

    def _reconstruir_memoria(self, side, entry, qty, info_csv):
        strat = info_csv['estrategia'] if info_csv else 'RECOVERED'
        sl_pct = self.cfg.SWING_SL if strat == 'SWING' else self.cfg.SCALP_SL_PCT
        sl = entry * (1 - sl_pct) if side == 'LONG' else entry * (1 + sl_pct)
        
        self.posicion_abierta = {
            'tipo': side, 'entrada': entry, 'cantidad': qty, 
            'tp': 0, 'sl': sl, 'motivo': "RESTAURADO", 'strategy': strat, 
            'break_even_activado': False, 'trailing_activado': False,
            'best_price': entry, 'proteccion_validada': True,
            'tp_mid': 0, 'tp_parcial_ejecutado': False 
        }

    def _evaluar_rescate(self, side, entry, qty, current_price, info_csv):
        if side == 'LONG': pnl_pct = (current_price - entry) / entry
        else: pnl_pct = (entry - current_price) / entry
        max_loss = -self.cfg.SWING_SL
        
        if pnl_pct < max_loss:
            print(f"{Fore.RED}💀 PÉRDIDA IRRECUPERABLE. CIERRE DE EMERGENCIA.{Style.RESET_ALL}")
            self.posicion_abierta = {'tipo': side, 'entrada': entry, 'cantidad': qty, 'strategy': 'RESCUE'}
            self._cerrar_orden("EMERGENCIA_PERDIDA_MAX", current_price, force_market=True)
        else:
            print(f"{Fore.GREEN}🔧 PnL recuperable. Intentando restaurar protecciones...{Style.RESET_ALL}")
            sl_pct = self.cfg.SCALP_SL_PCT
            tp_off = 0.01
            
            if side == 'LONG':
                n_sl = entry * (1 - sl_pct)
                n_tp = entry * (1 + tp_off)
            else:
                n_sl = entry * (1 + sl_pct)
                n_tp = entry * (1 - tp_off)
                
            exito = self._colocar_y_validar_protecciones(side, qty, entry, n_tp, n_sl, 'LONG' if side=='LONG' else 'SHORT')
            
            if exito:
                print(f"{Fore.GREEN}✅ ÉXITO. Posición Asegurada.{Style.RESET_ALL}")
                self._reconstruir_memoria(side, entry, qty, info_csv)
                self.posicion_abierta['sl'] = n_sl 
            else:
                print(f"{Fore.RED}❌ Fallo al restaurar. Cerrando por seguridad.{Style.RESET_ALL}")
                self.posicion_abierta = {'tipo': side, 'entrada': entry, 'cantidad': qty, 'strategy': 'RESCUE'}
                self._cerrar_orden("FALLO_RESTAURACION", current_price, force_market=True)

    def validar_riesgo_capital(self, cantidad, precio):
        nuevo_notional = cantidad * precio
        pos_actual = self.conn.obtener_posicion_abierta()
        exp_actual = float(pos_actual.get('notional', 0)) if pos_actual else 0.0
        
        total = abs(exp_actual) + nuevo_notional
        if total > self.cfg.MAX_EXPOSURE_USDT:
            print(f"{Fore.RED}[RIESGO] Rechazado. Exp Total {total:.2f} > Max {self.cfg.MAX_EXPOSURE_USDT}{Style.RESET_ALL}")
            return False
        return True

    def abrir_orden(self, tipo, precio_ref, tp_final, sl, motivo, tp_mid, estrategia='SCALP', es_dca=False, force_entry=False):
        if self.posicion_abierta is not None and not force_entry and not es_dca: return
        if not es_dca and not force_entry: self.conn.cancelar_todas_ordenes()
        
        leverage = self.cfg.LEVERAGE_SWING if estrategia == 'SWING' else (self.cfg.LEVERAGE_MOMENTUM if estrategia == 'MOMENTUM' else self.cfg.LEVERAGE_SCALP)
        pct = self.cfg.SIZE_SCALP if es_dca else (self.cfg.SIZE_SWING if estrategia == 'SWING' else (self.cfg.SIZE_MOMENTUM if estrategia == 'MOMENTUM' else self.cfg.SIZE_SCALP))
        
        qty = utils.calcular_cantidad_ajustada(precio_ref, self.cfg.CAPITAL_TRABAJO * pct * leverage, self.step_size)
        if qty == 0: return 
        if not self.validar_riesgo_capital(qty, precio_ref): return

        side = 'BUY' if tipo == 'LONG' else 'SELL'
        pos_side = 'LONG' if tipo == 'LONG' else 'SHORT'
        
        print(f"{Fore.MAGENTA}>>> INTENTO ENTRADA [{tipo}] {estrategia}...{Style.RESET_ALL}")
        
        precio_entrada_real = precio_ref
        proteccion_exitosa = True
        
        if self.cfg.MODE in ['TESTNET', 'LIVE']:
            order = self.conn.colocar_orden_market(side, qty, pos_side)
            if not order: 
                print(f"{Fore.RED}❌ Error API al entrar.{Style.RESET_ALL}")
                return
            
            precio_entrada_real = float(order.get('avgPrice', precio_ref))
            if precio_entrada_real == 0: precio_entrada_real = precio_ref
            
            proteccion_exitosa = self._colocar_y_validar_protecciones(tipo, qty, precio_entrada_real, tp_final, sl, pos_side)
            
            if not proteccion_exitosa:
                print(f"{Fore.RED}☢️ EMERGENCIA: FALLO PROTECCIÓN. CERRANDO.{Style.RESET_ALL}")
                self.posicion_abierta = {'tipo': tipo, 'entrada': precio_entrada_real, 'cantidad': qty, 'strategy': 'FAIL_SAFE'}
                self._cerrar_orden("FALLO_PROTECCION_INICIAL", precio_entrada_real, force_market=True)
                return

        dist_sl = abs(sl - precio_ref)
        rsl = precio_entrada_real - dist_sl if tipo=='LONG' else precio_entrada_real + dist_sl

        self.posicion_abierta = {
            'tipo': tipo, 'entrada': precio_entrada_real, 'cantidad': qty, 
            'tp': tp_final, 'sl': rsl, 'motivo': motivo, 'strategy': estrategia, 
            'break_even_activado': False, 'trailing_activado': False,
            'best_price': precio_entrada_real, 'proteccion_validada': proteccion_exitosa,
            'tp_mid': tp_mid, 'tp_parcial_ejecutado': False
        }
        
        monto = precio_entrada_real * qty
        self._escribir_bitacora([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'), estrategia, tipo,
            f"{precio_entrada_real:.4f}", f"{qty}", f"{monto:.2f}",
            "0", "0", "APERTURA", "SI", "NO", f"{self.cfg.MAX_EXPOSURE_USDT}", "OPEN"
        ])
        
        print(f"{Fore.GREEN}✅ POSICIÓN ASEGURADA: {tipo} @ {precio_entrada_real:.2f} | SL: {rsl:.2f} | TP1: {tp_mid:.2f}{Style.RESET_ALL}")

    def _colocar_y_validar_protecciones(self, tipo, qty, entry, tp, sl, pos_side):
        side_cierre = 'SELL' if tipo == 'LONG' else 'BUY'
        sl_ok = False
        
        for i in range(3):
            res = self.conn.colocar_orden_sl_tp(side_cierre, qty, sl, pos_side, 'STOP_MARKET')
            if res: sl_ok = True; break
            time.sleep(0.5)
            
        tp_ok = False
        for i in range(3):
            res = self.conn.colocar_orden_sl_tp(side_cierre, qty, tp, pos_side, 'TAKE_PROFIT_MARKET')
            if res: tp_ok = True; break
            time.sleep(0.5)
        
        if not sl_ok: return False
        
        abiertas = self.conn.obtener_ordenes_abiertas()
        has_sl = any(o['type'] == 'STOP_MARKET' for o in abiertas)
        has_tp = any(o['type'] == 'TAKE_PROFIT_MARKET' for o in abiertas)
        return has_sl and has_tp

    def verificar_salidas(self, precio):
        if not self.posicion_abierta: return None
        
        if self.cfg.MODE in ['TESTNET', 'LIVE']:
            if self._verificar_cierre_externo(precio):
                return "CERRADO_POR_BINANCE"
        
        return self._gestionar_riesgo(precio, self.posicion_abierta)

    def _verificar_cierre_externo(self, precio_actual):
        pos_real = self.conn.obtener_posicion_abierta()
        if not pos_real and self.posicion_abierta:
            self._cerrar_orden("TP/SL_BINANCE", precio_actual, orden_ejecutada_en_binance=True)
            return True
        return False

    def _gestionar_riesgo(self, precio, pos):
        changed = False; msg = None
        
        if not pos['tp_parcial_ejecutado']:
            toco_mid = False
            if pos['tipo'] == 'LONG' and precio >= pos['tp_mid']: toco_mid = True
            if pos['tipo'] == 'SHORT' and precio <= pos['tp_mid']: toco_mid = True
            
            if toco_mid:
                print(f"{Fore.CYAN}🎯 TOCÓ BANDA MEDIA! EJECUTANDO CIERRE PARCIAL Y B/E...{Style.RESET_ALL}")
                
                qty_total = pos['cantidad']
                qty_parcial = utils.calcular_cantidad_ajustada(precio, (qty_total * precio * 0.5), self.step_size)
                
                if qty_parcial > 0:
                    side_cierre = 'SELL' if pos['tipo'] == 'LONG' else 'BUY'
                    self.conn.colocar_orden_market(side_cierre, qty_parcial, 'LONG' if pos['tipo']=='LONG' else 'SHORT')
                    
                    pos['cantidad'] -= qty_parcial
                    pos['tp_parcial_ejecutado'] = True
                    
                    entry_fee_buffer = pos['entrada'] * 1.002 if pos['tipo']=='LONG' else pos['entrada'] * 0.998
                    pos['sl'] = entry_fee_buffer
                    
                    changed = True
                    msg = "TP PARCIAL + B/E"
                    
                    self._escribir_bitacora([
                        datetime.now(), pos['strategy'], pos['tipo'],
                        pos['entrada'], qty_parcial, (qty_parcial*precio),
                        precio, ((precio-pos['entrada'])*qty_parcial if pos['tipo']=='LONG' else (pos['entrada']-precio)*qty_parcial),
                        "TP_PARCIAL_MID", "SI", "SI", 0, "PARTIAL"
                    ])

        if pos['tipo'] == 'LONG':
            pos['best_price'] = max(pos['best_price'], precio)
            pnl_pct = (precio - pos['entrada']) / pos['entrada']
        else:
            pos['best_price'] = min(pos['best_price'], precio)
            pnl_pct = (pos['entrada'] - precio) / pos['entrada']
            
        if pos['tp_parcial_ejecutado'] or (pnl_pct > 0.005): 
            trail_dist = self.cfg.SCALP_TRAIL_DIST 
            if pos['strategy'] == 'MOMENTUM': trail_dist = self.cfg.MOMENTUM_TRAIL_DIST
            
            if pos['tipo'] == 'LONG':
                n_sl = pos['best_price'] * (1 - trail_dist)
                if n_sl > pos['sl']: pos['sl'] = n_sl; changed = True; msg = "TRAILING UP"
            else:
                n_sl = pos['best_price'] * (1 + trail_dist)
                if n_sl < pos['sl']: pos['sl'] = n_sl; changed = True; msg = "TRAILING DOWN"
        
        if changed: self._actualizar_ordenes_proteccion(pos)
        return msg

    def _actualizar_ordenes_proteccion(self, pos):
        if self.cfg.MODE not in ['TESTNET', 'LIVE']: return
        self.conn.cancelar_todas_ordenes()
        self._colocar_y_validar_protecciones(pos['tipo'], pos['cantidad'], pos['entrada'], pos['tp'], pos['sl'], 'LONG' if pos['tipo']=='LONG' else 'SHORT')

    def forzar_cierre_por_jerarquia(self, precio_actual, estrategia_superior):
        if self.posicion_abierta:
            self._cerrar_orden(f"OVERRIDE_BY_{estrategia_superior}", precio_actual)
            return True
        return False

    def cerrar_posicion_panico(self, p):
        if self.posicion_abierta: self._cerrar_orden("PANIC_USER", p, force_market=True)

    def _cerrar_orden(self, motivo, precio_salida, force_market=False, orden_ejecutada_en_binance=False):
        pos = self.posicion_abierta
        if not pos: return

        if self.cfg.MODE in ['TESTNET', 'LIVE']:
            if not orden_ejecutada_en_binance:
                side = 'SELL' if pos['tipo'] == 'LONG' else 'BUY'
                p_side = 'LONG' if pos['tipo'] == 'LONG' else 'SHORT'
                self.conn.colocar_orden_market(side, pos['cantidad'], p_side)
            self.conn.cancelar_todas_ordenes()
        
        pnl = (precio_salida - pos['entrada']) * pos['cantidad'] * (1 if pos['tipo']=='LONG' else -1)
        monto = pos['entrada'] * pos['cantidad']
        
        self.stats.registrar(pos['tipo'], pnl, pos.get('strategy', 'UNK'))
        
        color = Fore.GREEN if pnl >= 0 else Fore.RED
        print(f"{color}>>> CERRADO {motivo} | PnL: {pnl:.2f} USDT{Style.RESET_ALL}")
        
        self._escribir_bitacora([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'), pos.get('strategy', 'UNK'), pos['tipo'],
            f"{pos['entrada']:.4f}", f"{pos['cantidad']}", f"{monto:.2f}",
            f"{precio_salida:.4f}", f"{pnl:.4f}", motivo,
            "SI" if pos.get('proteccion_validada') else "NO",
            "SI" if pos.get('trailing_activado') else "NO",
            f"{self.cfg.MAX_EXPOSURE_USDT}", "CLOSED"
        ])
        
        self.posicion_abierta = None
        self.last_closure_time = datetime.now()

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
        self.trader.abrir_orden(tipo, p, tp, sl, f"MANUAL x{multi}", tp, 'SCALP', False, force_entry=True)

    def ejecutar_estrategia(self, mtf_data, precio):
        self.ultimo_precio = precio
        pos_actual = self.trader.posicion_abierta
        est_activa = pos_actual.get('strategy') if pos_actual else None

        res = self.trader.verificar_salidas(precio)
        if res: return f"Gestionando: {res}"
        
        if self.trader.last_closure_time and (datetime.now() - self.trader.last_closure_time).total_seconds() < self.COOLDOWN_SECONDS:
            return "Cooldown..."

        data_1m = mtf_data.get('1m', {})
        data_5m = mtf_data.get('5m', {})
        data_15m = mtf_data.get('15m', {})

        # 1. SWING
        swing_sig, swing_info = self.swing_mode.evaluar(data_15m)
        if swing_sig:
            if est_activa and est_activa != 'SWING':
                self.trader.forzar_cierre_por_jerarquia(precio, 'SWING')
                pos_actual = None; est_activa = None
            if not est_activa:
                self.trader.abrir_orden(swing_sig, precio, swing_info['tp_final'], swing_info['sl_price'], swing_info['motivo'], swing_info['tp_mid'], 'SWING')
                return f"👑 ENTRADA SWING {swing_sig}"
        if self.swing_mode.gatillo: return f"SWING ARMADO..."
        if est_activa == 'SWING': return "MONITOREO SWING..."

        # 2. SCALP
        scalp_sig, scalp_info = self.scalp_mode.evaluar(data_5m)
        if scalp_sig:
            if est_activa == 'MOMENTUM':
                self.trader.forzar_cierre_por_jerarquia(precio, 'SCALP')
                pos_actual = None; est_activa = None
            if not est_activa:
                self.trader.abrir_orden(scalp_sig, precio, scalp_info['tp_final'], scalp_info['sl_price'], scalp_info['motivo'], scalp_info['tp_mid'], 'SCALP')
                return f"⚔️ DISPARO SCALP {scalp_sig}"
        if self.scalp_mode.gatillo: return f"SCALP ARMADO..."
        if est_activa == 'SCALP': return "MONITOREO SCALP..."

        # 3. MOMENTUM
        mom_sig, mom_info = self.mom_mode.evaluar(data_1m)
        if mom_sig and not est_activa:
            self.trader.abrir_orden(mom_sig, precio, mom_info['tp_final'], mom_info['sl_price'], mom_info['motivo'], mom_info['tp_mid'], 'MOMENTUM')
            return f"🚀 MOMENTUM {mom_sig}"
        if self.mom_mode.gatillo: return f"MOMENTUM ARMADO..."

        return "Escaneo Jerárquico..."