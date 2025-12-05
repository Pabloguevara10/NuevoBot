import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# Configuración
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(current_dir, '..')))
from config.config import Config
from tools.precision_lab import PrecisionLab as Lab
from tools.smart_money_logic import SmartMoneyLogic

class DynamicFVG:
    def __init__(self, top, bottom, tipo, time):
        self.top = top; self.bottom = bottom; self.type = tipo; self.time = time

class BacktesterV5Forensic:
    def __init__(self):
        print("🚀 INICIANDO FORENSE V5 (Análisis de Oportunidades Perdidas)...")
        self.cfg = Config()
        self.data_path = os.path.join(self.cfg.BASE_DIR, 'logs', 'data_lab')
        self.smc = SmartMoneyLogic()
        
        self.rejected_setups = [] # Aquí guardaremos lo que NO operamos
        self.executed_trades = []

    def cargar_datos(self):
        print("📂 Cargando datos...")
        try:
            df_1m = pd.read_csv(os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_1m.csv"))
            df_1d = pd.read_csv(os.path.join(self.data_path, f"history_{self.cfg.SYMBOL}_1d.csv"))
            
            for df in [df_1m, df_1d]:
                df.columns = df.columns.str.strip()
                col_ts = 'ts' if 'ts' in df.columns else 'timestamp'
                df['datetime'] = pd.to_datetime(df[col_ts], unit='ms') if 'ts' in df.columns else pd.to_datetime(df[col_ts])
                df.set_index('datetime', inplace=True)

            # RSI para divergencias
            delta = df_1m['close'].diff()
            gain = (delta.where(delta>0, 0)).rolling(14).mean()
            loss = (-delta.where(delta<0, 0)).rolling(14).mean()
            rs = gain / loss
            df_1m['RSI'] = 100 - (100/(1+rs))

            return df_1m.dropna(), df_1d.dropna()
        except Exception as e:
            print(f"❌ Error: {e}")
            return None, None

    def ejecutar(self):
        df_1m, df_1d = self.cargar_datos()
        if df_1m is None: return

        print(f"⚡ Auditando flujo SMC sobre {len(df_1m)} minutos...")
        
        dias_unicos = df_1m.index.normalize().unique()
        records_all = df_1m.reset_index().to_dict('records')
        
        # Mapa rápido para acceso por índice
        # Usaremos índices numéricos para velocidad
        
        # Estado de Simulación
        current_day_idx = 0
        
        # Iteramos por días para resetear lógica SMC
        for dia in dias_unicos:
            ayer = dia - timedelta(days=1)
            if ayer not in df_1d.index: continue
            
            vela_ayer = df_1d.loc[ayer]
            self.smc.iniciar_nuevo_dia(vela_ayer)
            
            # Indices del día en df_1m
            mask = (df_1m.index >= dia) & (df_1m.index < dia + timedelta(days=1))
            indices_dia = np.where(mask)[0]
            if len(indices_dia) < 10: continue
            
            # Loop intra-día
            for i in indices_dia:
                if i < 15: continue # Warmup
                row = records_all[i]
                
                # 1. LÓGICA SMC
                if self.smc.state == 'ESPERANDO_LIQUIDEZ':
                    self.smc.verificar_toma_liquidez(row)

                elif self.smc.state == 'LIQUIDEZ_TOMADA':
                    prev2 = records_all[i-2]
                    fvg_cand = None
                    if prev2['high'] < row['low']:
                         fvg_cand = DynamicFVG(row['low'], prev2['high'], 'LONG', row['datetime'])
                    elif prev2['low'] > row['high']:
                         fvg_cand = DynamicFVG(prev2['low'], row['high'], 'SHORT', row['datetime'])
                    
                    if fvg_cand: self.smc.registrar_fvg_post_sweep(fvg_cand)

                elif self.smc.state == 'FVG_DETECTADO':
                    fvg = self.smc.active_fvg
                    price = row['close']
                    
                    # Verificar Zona
                    en_zona = (fvg.type == 'LONG' and fvg.bottom <= price <= fvg.top) or \
                              (fvg.type == 'SHORT' and fvg.top >= price >= fvg.bottom)
                    
                    if en_zona:
                        # BUSCAR DIVERGENCIA (El Gatillo)
                        subset = pd.DataFrame(records_all[i-15:i+1])
                        div = Lab.detectar_divergencia(subset, ventana=10)
                        
                        # Definir parámetros del trade potencial
                        tp = self.smc.pdh if fvg.type == 'LONG' else self.smc.pdl
                        sl = price * (0.995 if fvg.type=='LONG' else 1.005)
                        
                        trade_setup = {
                            'time': row['datetime'],
                            'type': fvg.type,
                            'entry': price,
                            'tp': tp,
                            'sl': sl,
                            'rsi_val': row['RSI'],
                            'div_detected': div
                        }
                        
                        if (fvg.type == 'LONG' and div == 'BULLISH_DIV') or \
                           (fvg.type == 'SHORT' and div == 'BEARISH_DIV'):
                            # Trade EJECUTADO
                            self.verificar_resultado(trade_setup, records_all, i, 'EXECUTED')
                            # Reset tras disparo
                            self.smc.state = 'ESPERANDO_LIQUIDEZ'
                        else:
                            # Trade RECHAZADO (Potencial Oportunidad Perdida)
                            # Lo registramos para ver "qué hubiera pasado"
                            self.verificar_resultado(trade_setup, records_all, i, 'REJECTED')

    def verificar_resultado(self, setup, data, current_idx, status):
        """Mira al futuro para ver si hubiera ganado."""
        entry = setup['entry']
        tp = setup['tp']
        sl = setup['sl']
        side = setup['type']
        
        # Miramos hasta 4 horas en el futuro (240 velas)
        future_data = data[current_idx+1 : current_idx+241]
        
        outcome = 'FLAT'
        pnl_sim = 0
        
        for candle in future_data:
            # Check SL
            if (side=='LONG' and candle['low'] <= sl) or (side=='SHORT' and candle['high'] >= sl):
                outcome = 'LOSS'
                pnl_sim = -1 # Unidad de riesgo
                break
            # Check TP
            if (side=='LONG' and candle['high'] >= tp) or (side=='SHORT' and candle['low'] <= tp):
                outcome = 'WIN'
                pnl_sim = 5 # R:R 1:5 aprox (SMC suele dar altos R)
                break
        
        setup['outcome'] = outcome
        setup['status'] = status
        
        if status == 'EXECUTED':
            self.executed_trades.append(setup)
        else:
            # Solo guardamos rechazos que NO se superponen (simple filter)
            # Para no llenar el log con 10 rechazos en la misma vela
            if not self.rejected_setups or (setup['time'] - self.rejected_setups[-1]['time']).total_seconds() > 300:
                self.rejected_setups.append(setup)

    def generar_forense(self):
        print("\n" + "="*60)
        print("📊 REPORTE FORENSE: DIVERGENCIAS PERDIDAS")
        print("="*60)
        
        # 1. Análisis de Rechazos Ganadores
        missed_wins = [t for t in self.rejected_setups if t['outcome'] == 'WIN']
        missed_losses = [t for t in self.rejected_setups if t['outcome'] == 'LOSS']
        
        print(f"Total Señales Rechazadas (Falta Divergencia): {len(self.rejected_setups)}")
        print(f" -> Hubieran sido WIN:  {len(missed_wins)} ({len(missed_wins)/len(self.rejected_setups)*100:.1f}%)")
        print(f" -> Hubieran sido LOSS: {len(missed_losses)}")
        
        # 2. Comparativa de Indicadores (El ADN del Error)
        if missed_wins:
            avg_rsi_missed = sum(t['rsi_val'] for t in missed_wins) / len(missed_wins)
            print(f"\n🔍 ADN de las Ganadoras Perdidas:")
            print(f"   RSI Promedio al momento del rechazo: {avg_rsi_missed:.2f}")
            print(f"   (El bot esperaba divergencia, pero el precio giró con este RSI)")
            
            print("\n   Ejemplos de Oportunidades Perdidas:")
            for t in missed_wins[:5]:
                print(f"   - {t['time']} {t['type']} @ {t['entry']:.2f} | RSI: {t['rsi_val']:.1f} | Outcome: WIN")

        # 3. Comparativa con Ejecutadas
        print(f"\n✅ Trades Ejecutados (Con Divergencia): {len(self.executed_trades)}")
        real_wins = len([t for t in self.executed_trades if t['outcome'] == 'WIN'])
        if self.executed_trades:
            print(f"   Win Rate Real: {real_wins/len(self.executed_trades)*100:.1f}%")

if __name__ == "__main__":
    audit = BacktesterV5Forensic()
    audit.ejecutar()
    audit.generar_forense()