import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 設定 ---
TICKERS = ["GDE", "DBMF", "RSSB", "BOXX"]
RATE_TICKER = "^IRX" # 米13週国債利回り（政策金利のプロキシ）

st.set_page_config(page_title="Dynamic Rebalance App 2026", layout="wide")

st.title("🚀 資産運用リバランス・シミュレーター")
st.caption("yfinanceベースの堅牢なロジック執行エンジン")

# --- データ取得エンジン ---
@st.cache_data(ttl=3600)
def get_all_data():
    all_tickers = TICKERS + [RATE_TICKER]
    end_date = datetime.now()
    start_date = end_date - timedelta(days=400) # MA200日＋アルファ
    
    df = yf.download(all_tickers, start=start_date, end=end_date)
    
    # 価格データの抽出（Adj Close優先、なければClose）
    if 'Adj Close' in df.columns.levels[0]:
        prices = df['Adj Close'][TICKERS]
    else:
        prices = df['Close'][TICKERS]
    
    # 政策金利(代用)の抽出
    irx_data = df['Close'][RATE_TICKER].ffill()
    current_rate = irx_data.iloc[-1] / 100  # 指数は%表記なので小数に変換
    
    return prices.ffill().dropna(), current_rate

try:
    price_data, auto_policy_rate = get_all_data()
except Exception as e:
    st.error(f"データ取得エラー: {e}")
    st.stop()

# --- サイドバー入力 ---
with st.sidebar:
    st.header("パラメータ設定")
    policy_rate = st.number_input("適用政策金利 (%)", value=float(auto_policy_rate * 100), format="%.2f") / 100
    total_assets = st.number_input("運用総額 ($)", value=100000, step=1000)
    st.divider()
    st.write("現在の保有数")
    current_shares = {t: st.number_input(f"{t} 株", value=100, step=1) for t in TICKERS}

# --- ロジック計算 ---
def run_rebalance_logic(prices, p_rate):
    # 1. トータルリターン（年換算）
    # 直近21営業日（約1ヶ月）のリターン
    monthly_ret = (prices.iloc[-1] / prices.iloc[-21] - 1) * 12
    max_other_ret = monthly_ret.drop("BOXX").max()
    
    # 2. BOXX比率の計算
    # ロジック: p_rate - max(max_other_ret, 3%) がプラスなら その3倍増やす
    diff = p_rate - max(max_other_ret, 0.03)
    boxx_boost = max(0, diff * 3)
    target_boxx = min(0.1 + boxx_boost, 0.4) # デフォルト10%〜最大40%
    
    # 3. 他のETFのデフォルト配分
    rem_weight = (1.0 - target_boxx) / 3
    base_weights = {t: rem_weight for t in TICKERS if t != "BOXX"}
    base_weights["BOXX"] = target_boxx
    
    # 4. 動的調整 (MA 3m vs 200d)
    ma_1m = prices.rolling(21).mean().iloc[-1]
    ma_3m = prices.rolling(63).mean().iloc[-1]
    ma_200d = prices.rolling(200).mean().iloc[-1]
    
    final_weights = base_weights.copy()
    reduction_pool = 0
    
    # 減算判定
    for t in ["GDE", "DBMF", "RSSB"]:
        under_pct = (ma_200d[t] - ma_3m[t]) / ma_200d[t]
        # 3%以上下回る、かつ1mMAが3mMAを上回っていない（回復基調にない）
        if under_pct > 0.03 and ma_1m[t] < ma_3m[t]:
            reduction = final_weights[t] * under_pct
            final_weights[t] -= reduction
            reduction_pool += reduction
            
    # 加算先判定（一番マシなETFへ）
    relative_perf = (ma_3m / ma_200d) - 1
    best_t = relative_perf.idxmax()
    final_weights[best_t] += reduction_pool
    
    return final_weights, monthly_ret, ma_3m, ma_200d

final_w, m_ret, m3, m200 = run_rebalance_logic(price_data, policy_rate)

# --- 結果の可視化 ---
c1, c2 = st.columns(2)

with c1:
    st.subheader("📊 目標ポートフォリオ")
    fig = go.Figure(data=[go.Pie(labels=list(final_w.keys()), values=list(final_w.values()), hole=.4)])
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("🔍 判断根拠データ")
    metrics = pd.DataFrame({
        "1ヶ月リターン(年換)": m_ret.map("{:.2%}".format),
        "3ヶ月移動平均": m3.map("{:.2f}".format),
        "200日移動平均": m200.map("{:.2f}".format)
    })
    st.table(metrics)

# --- 売買シミュレーション ---
st.divider()
st.subheader("🛒 リバランス実行指図")

current_prices = price_data.iloc[-1]
rebalance_list = []
for t in TICKERS:
    current_val = current_shares[t] * current_prices[t]
    target_val = total_assets * final_w[t]
    diff_val = target_val - current_val
    diff_qty = diff_val / current_prices[t]
    
    rebalance_list.append({
        "銘柄": t,
        "現在比率": f"{(current_val/total_assets):.1%}",
        "目標比率": f"{final_w[t]:.1%}",
        "売買金額 ($)": f"{diff_val:,.2f}",
        "必要売買数": int(diff_qty)
    })

st.dataframe(pd.DataFrame(rebalance_list), use_container_width=True)

# 定期リバランス判定（簡易版）
is_20th_later = datetime.now().day >= 20
st.info(f"💡 判定メモ: 本日は20日以降ですか？ -> {'Yes' if is_20th_later else 'No'}. 週次制限を考慮して執行してください。")