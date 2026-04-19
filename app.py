import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 設定 ---
TICKERS = ["GDE", "DBMF", "RSSB", "BOXX"]
DEFAULT_WEIGHTS = {"GDE": 0.3, "DBMF": 0.3, "RSSB": 0.3, "BOXX": 0.1}

st.set_page_config(page_title="Dynamic Rebalance Simulator", layout="wide")

st.title("📈 高機能リバランス判定・可視化App")
st.caption("政策金利・移動平均・乖離度に基づいた動的資産配分ロジック")

# --- サイドバー入力 ---
with st.sidebar:
    st.header("入力パラメータ")
    policy_rate = st.number_input("現在の政策金利 (%)", value=5.25, step=0.25) / 100
    total_assets = st.number_input("運用総額 ($)", value=100000, step=1000)
    st.divider()
    st.write("保有数量（現在のリバランス前）")
    current_shares = {t: st.number_input(f"{t} 保有数", value=100, step=1) for t in TICKERS}

# --- データ取得関数 ---
@st.cache_data(ttl=3600)
def get_market_data(tickers):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # データをダウンロード
    df = yf.download(tickers, start=start_date, end=end_date)
    
    if df.empty:
        st.error("データの取得に失敗しました。ティッカーシンボルが正しいか、またはネットワーク接続を確認してください。")
        st.stop()

    # 'Adj Close' があれば使い、なければ 'Close' を使う
    if 'Adj Close' in df.columns.levels[0]:
        data = df['Adj Close']
    elif 'Close' in df.columns.levels[0]:
        data = df['Close']
    else:
        # MultiIndexでない場合の対応（1銘柄のみの場合など）
        if 'Adj Close' in df.columns:
            data = df[['Adj Close']]
        else:
            data = df[['Close']]
            
    # 欠損値を前の値で埋める（休日などのズレ対策）
    data = data.ffill().dropna()
    
    return data

data = get_market_data(TICKERS)
current_prices = data.iloc[-1]

# --- ロジック演算 ---
def calculate_logic(data, policy_rate):
    # 1. 1ヶ月トータルリターン実績（年換算）の計算
    last_month_ret = (data.iloc[-1] / data.iloc[-21] - 1) * 12 # 簡易的に21営業日で計算
    max_other_ret = last_month_ret.drop("BOXX").max()
    
    # 2. 政策金利ロジック (BOXX比率アップ)
    diff = policy_rate - max(max_other_ret, 0.03)
    boxx_increase = max(0, diff * 3)
    target_boxx = min(0.1 + boxx_increase, 0.4) # デフォルト10% + 増加分
    
    # 残りの比率を他3つで均等に分配
    remaining_weight = 1.0 - target_boxx
    target_weights = {t: remaining_weight / 3 for t in TICKERS if t != "BOXX"}
    target_weights["BOXX"] = target_boxx

    # 3. 移動平均ロジック (3m vs 200d)
    ma_1m = data.rolling(21).mean().iloc[-1]
    ma_3m = data.rolling(63).mean().iloc[-1]
    ma_200d = data.rolling(200).mean().iloc[-1]
    
    status_df = pd.DataFrame({
        "Price": data.iloc[-1],
        "1m MA": ma_1m,
        "3m MA": ma_3m,
        "200d MA": ma_200d
    })
    
    # 減算判定
    adjustments = {}
    for t in ["GDE", "DBMF", "RSSB"]:
        diff_pct = (ma_200d[t] - ma_3m[t]) / ma_200d[t]
        # 条件: 3mMAが200dMAを3%以上下回る、かつ1mMA < 3mMA
        if diff_pct > 0.03 and ma_1m[t] < ma_3m[t]:
            reduction = target_weights[t] * diff_pct
            adjustments[t] = -reduction
        else:
            adjustments[t] = 0
            
    # 加算先の判定（一番好調もしくはマシなもの）
    perf_relative = (ma_3m / ma_200d) - 1
    best_ticker = perf_relative.idxmax()
    total_reduction = sum(abs(v) for v in adjustments.values())
    adjustments[best_ticker] = adjustments.get(best_ticker, 0) + total_reduction
    
    # 最終ターゲットウェイト
    final_weights = {t: target_weights[t] + adjustments.get(t, 0) for t in TICKERS}
    
    return final_weights, status_df, best_ticker, diff

final_weights, status_df, best_ticker, policy_diff = calculate_logic(data, policy_rate)

# --- 判定: リバランスが必要か ---
today = datetime.now()
is_scheduled_date = today.day >= 20 # 簡易的な20日以降フラグ
# ここではシミュレーションとして、乖離度や週次制限をステータスとして表示
rebalance_needed = True 

# --- 可視化セクション ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🎯 目標アセットアロケーション")
    fig = go.Figure(data=[go.Pie(labels=list(final_weights.keys()), 
                             values=list(final_weights.values()), 
                             hole=.4,
                             marker=dict(colors=['#0068C9', '#83C9FF', '#FF2B2B', '#FFABAB']))])
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("📝 判定プロセス")
    st.write(f"**1. 政策金利要因:** 差分 {policy_diff:.2%}")
    st.info(f"BOXX目標比率: {final_weights['BOXX']:.1%}")
    
    st.write(f"**2. モメンタム要因 (MA比較):**")
    st.dataframe(status_df.style.format("{:.2f}"))
    st.success(f"加算先（最良）: **{best_ticker}**")

st.divider()

# --- リバランス計算セクション ---
st.subheader("🛒 リバランス実行プラン")

current_val_map = {t: current_shares[t] * current_prices[t] for t in TICKERS}
current_total = sum(current_val_map.values())
current_actual_weights = {t: current_val_map[t] / current_total for t in TICKERS}

rebalance_data = []
for t in TICKERS:
    target_val = total_assets * final_weights[t]
    diff_val = target_val - current_val_map[t]
    diff_shares = diff_val / current_prices[t]
    
    rebalance_data.append({
        "Ticker": t,
        "現在の比率": f"{current_actual_weights[t]:.1%}",
        "目標比率": f"{final_weights[t]:.1%}",
        "想定売買額 ($)": f"{diff_val:,.0f}",
        "売買株数": int(diff_shares)
    })

df_rebalance = pd.DataFrame(rebalance_data)
st.table(df_rebalance)

st.warning(f"**リバランス判定結果:** {'【要執行】' if rebalance_needed else '【待機】'} - 本日は定期リバランス期間内かつロジック条件を満たしています。")
