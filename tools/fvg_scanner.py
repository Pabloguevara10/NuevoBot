import pandas as pd
import os
import sys
from datetime import datetime

# Ajuste para importar config desde la carpeta superior
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.config import Config

class FVGScanner:
    def __init__(self):
        print("🛰️  INICIANDO RADAR INSTITUCIONAL (FVG SCANNER)...")
        self.cfg = Config()
        self.data_path = 'logs/data_lab'
        self.output_file = os.path.join('logs', 'bitacoras', 'fvg_registry.csv')

    def cargar_datos(self, timeframe):
        """Carga el histórico generado por el Data Miner."""
        filename = f"history_{self.cfg.SYMBOL}_{timeframe}.csv"
        path = os.path.join(self.data_path, filename)
        
        if not os.path.exists(path):
            print(f"⚠️  No se encontró data para {timeframe}. (Saltando)")
            return pd.DataFrame()
            
        df = pd.read_csv(path)
        # Asegurar fechas
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
        elif 'ts' in df.columns:
            df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
            
        return df

    def detectar_fvg(self, df, timeframe):
        """
        Escanea el DataFrame buscando FVGs no mitigados (Vírgenes).
        Retorna lista de zonas activas.
        """
        fvgs = []
        print(f"   🔍 Analizando {timeframe} ({len(df)} velas)...", end="")
        
        if len(df) < 3: 
            print(" Insuficiente data.")
            return []

        count_found = 0
        
        # Iterar buscando el patrón
        # i = Vela 1, i+1 = Vela 2 (Explosión), i+2 = Vela 3
        # No analizamos las últimas 2 velas porque el FVG necesita la vela 3 cerrada
        for i in range(len(df) - 3):
            c1 = df.iloc[i]
            c2 = df.iloc[i+1] # La vela del movimiento
            c3 = df.iloc[i+2]
            
            fvg_type = None
            top = 0.0
            bottom = 0.0
            
            # --- 1. DETECCIÓN MATEMÁTICA ---
            
            # FVG ALCISTA (Soporte): Hueco entre High(1) y Low(3)
            # El precio subió tan rápido que dejó un vacío sin negociar
            if c3['low'] > c1['high']:
                gap_size = c3['low'] - c1['high']
                # Filtro de Calidad: El hueco debe ser > 0.1% del precio (evita ruido)
                if gap_size > (c2['close'] * 0.001): 
                    fvg_type = 'LONG' # Zona de Compra
                    top = c3['low']      # Techo del hueco (Entrada agresiva)
                    bottom = c1['high']  # Piso del hueco (Stop Loss estructural)

            # FVG BAJISTA (Resistencia): Hueco entre Low(1) y High(3)
            # El precio bajó tan rápido que dejó un vacío
            elif c3['high'] < c1['low']:
                gap_size = c1['low'] - c3['high']
                if gap_size > (c2['close'] * 0.001):
                    fvg_type = 'SHORT' # Zona de Venta
                    top = c1['low']      # Techo del hueco (Stop Loss estructural)
                    bottom = c3['high']  # Piso del hueco (Entrada agresiva)
            
            # --- 2. VERIFICACIÓN DE MITIGACIÓN (¿Sigue vivo?) ---
            if fvg_type:
                mitigado = False
                # Revisamos el futuro: desde la vela i+3 hasta AHORA
                future_candles = df.iloc[i+3:]
                
                for _, fc in future_candles.iterrows():
                    # Si el precio toca la zona, se considera mitigado (usado)
                    if fvg_type == 'LONG':
                        # El precio baja y toca el techo del FVG
                        if fc['low'] <= top: 
                            mitigado = True
                            break
                    else: # SHORT
                        # El precio sube y toca el piso del FVG
                        if fc['high'] >= bottom:
                            mitigado = True
                            break
                
                # Si sobrevivió al paso del tiempo, es una joya.
                if not mitigado:
                    fvgs.append({
                        'Symbol': self.cfg.SYMBOL,
                        'Timeframe': timeframe,
                        'Type': fvg_type,
                        'Top': float(f"{top:.2f}"),
                        'Bottom': float(f"{bottom:.2f}"),
                        'Created_At': str(c2['datetime']),
                        'Gap_Size_Pct': float(f"{(abs(top-bottom)/c2['close'])*100:.2f}")
                    })
                    count_found += 1

        print(f" -> {count_found} Activos.")
        return fvgs

    def ejecutar_barrido(self):
        """Barre todas las temporalidades y actualiza la bitácora."""
        all_fvgs = []
        
        # Temporalidades Institucionales
        # 1h: Intradía fuerte
        # 4h: Swing Trading (Muy fiable)
        # 1d: Inversión (Imán gigante)
        tfs = ['1h', '4h', '1d']
        
        for tf in tfs:
            df = self.cargar_datos(tf)
            if not df.empty:
                fvg_list = self.detectar_fvg(df, tf)
                all_fvgs.extend(fvg_list)
        
        # Guardar en Bitácora
        if all_fvgs:
            df_result = pd.DataFrame(all_fvgs)
            # Ordenar: Los más recientes arriba
            df_result = df_result.sort_values('Created_At', ascending=False)
            
            # Asegurar directorio
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            
            df_result.to_csv(self.output_file, index=False)
            
            print("\n✅ REGISTRO FVG ACTUALIZADO.")
            print(f"📍 Archivo: {self.output_file}")
            print("\nÚltimos 5 Puntos de Interés Detectados:")
            print(df_result[['Timeframe', 'Type', 'Bottom', 'Top', 'Gap_Size_Pct']].head(5).to_string(index=False))
        else:
            print("\n⚠️ No se encontraron FVGs activos. El mercado está eficiente (o muy comprimido).")

if __name__ == "__main__":
    scanner = FVGScanner()
    scanner.ejecutar_barrido()