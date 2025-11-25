# indicators.py
import pandas as pd
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.trend import SMAIndicator, MACD
from ta.volume import OnBalanceVolumeIndicator, AccDistIndexIndicator, VolumeWeightedAveragePrice
from config import Config

class MarketAnalyzer:
    def __init__(self, df):
        self.df = df
        self.SR_WINDOW = getattr(Config, 'SR_WINDOW', 20)

    def calcular_todo(self, rsi_period=14):
        if self.df.empty: return self.df

        self.df['MA7'] = SMAIndicator(self.df['close'], window=7).sma_indicator()
        self.df['MA25'] = SMAIndicator(self.df['close'], window=25).sma_indicator()
        self.df['MA99'] = SMAIndicator(self.df['close'], window=99).sma_indicator()

        self.df['RSI'] = RSIIndicator(self.df['close'], window=rsi_period).rsi()
        stoch = StochRSIIndicator(self.df['close'], window=14, smooth1=3, smooth2=3)
        self.df['StochRSI_k'] = stoch.stochrsi_k()

        self.df['OBV'] = OnBalanceVolumeIndicator(self.df['close'], self.df['volume']).on_balance_volume()
        self.df['ADI'] = AccDistIndexIndicator(self.df['high'], self.df['low'], self.df['close'], self.df['volume']).acc_dist_index()
        
        try:
            vwap = VolumeWeightedAveragePrice(self.df['high'], self.df['low'], self.df['close'], self.df['volume'])
            self.df['VWAP'] = vwap.volume_weighted_average_price()
        except:
            self.df['VWAP'] = self.df['close']

        self.df['Roll_Max'] = self.df['high'].rolling(window=self.SR_WINDOW).max()
        self.df['Roll_Min'] = self.df['low'].rolling(window=self.SR_WINDOW).min()

        self.df.bfill(inplace=True)
        self.df.ffill(inplace=True)
        self.df['VWAP'] = self.df['VWAP'].fillna(self.df['close'])
        
        return self.df

    def obtener_extremos_locales(self):
        if self.df.empty or 'Roll_Max' not in self.df.columns: return 0, 0
        last = self.df.iloc[-1]
        return last['Roll_Min'], last['Roll_Max']