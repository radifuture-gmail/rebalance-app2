import yfinance as yf
import pandas as pd
from pandas_datareader import data as web
from datetime import datetime, timedelta

def get_etf_data(tickers=["BOXX", "GDE", "RSSB", "DBMF"], period="2y"):
    """
    Yahoo FinanceからETFの価格データを取得する [cite: 1, 7]
    """
    data = yf.download(tickers, period=period)["Adj Close"]
    # 欠損値を前方埋め
    data = data.ffill()
    return data

def get_risk_free_rate():
    """
    FREDから米国の政策金利(FF Rate)を取得する [cite: 1, 7]
    """
    try:
        # FREDから実効フェデラル・ファンド・レート(月次)の直近値を取得
        start = datetime.now() - timedelta(days=90)
        df = web.DataReader("FEDFUNDS", "fred", start)
        # 最新の値を小数(例: 0.0533)で返す
        latest_rate = df.iloc[-1, 0] / 100.0
        return latest_rate
    except Exception:
        # 接続エラー時のフォールバック値
        return 0.0533

def calculate_technical_indicators(df):
    """
    ロジック判定に必要な移動平均とリターンを計算する [cite: 1, 2]
    1ヶ月(21日), 3ヶ月(63日), 200日の窓関数を使用
    """
    indicators = pd.DataFrame(index=df.columns)
    
    # 最新価格
    indicators["current_price"] = df.iloc[-1]
    
    # 移動平均 (MA)
    indicators["ma_1m"] = df.rolling(window=21).mean().iloc[-1]
    indicators["ma_3m"] = df.rolling(window=63).mean().iloc[-1]
    indicators["ma_200d"] = df.rolling(window=200).mean().iloc[-1]
    
    # 1ヶ月トータルリターン実績（年換算用） [cite: 1, 7]
    # (価格 / 21日前価格 - 1) * 12ヶ月
    indicators["return_1m_annualized"] = (df.iloc[-1] / df.iloc[-21] - 1) * 12
    
    return indicators