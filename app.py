import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas_market_calendars as mcal

# --- 設定・定数 ---
TICKERS = ["BOXX", "GDE", "RSSB", "DBMF"]
DEFAULT_WEIGHTS = {"BOXX": 0.1, "GDE": 0.3, "RSSB": 0.3, "DBMF": 0.3}
RATE_TICKER = "^IRX"  # 13周米国債利回り

st.set_page_config(page_title="Dynamic Rebalance Pro 2026", layout="wide")

# --- スタイル設定 ---
st.markdown("""
    <style>
    .reportview-container { background: #f0f2f6; }
    .status-box { padding: 20px; border-radius: 10px; margin-bottom: 20px; }
    .buy-action { color: #2ecc71; font-weight: bold; }
    .sell-action { color: #e74c3c; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- データ取得 ---
@st.cache_data(ttl=3600)
def fetch_data():
    all_symbols = TICKERS + [RATE_TICKER]
    # MA200日＋余裕分として約300日分取得
    data = yf.download(all_symbols, period="2y", interval="1d")
    prices = data['Adj Close'][TICKERS].ffill()
    rates = data['Adj Close'][RATE_TICKER].ffill() / 100
    return prices, rates

try:
    price_df, rate_df = fetch_data()
    current_prices = price_df.iloc[-1]
    last_rate = rate_df.iloc[-1]
except Exception as e:
    st.error(f"データ取得に失敗しました: {e}")
    st.stop()

# --- サイドバー: 現在の資産状況入力 ---
with st.sidebar:
    st.header("📌 現在の資産状況")
    total_assets = st.number_input("運用総額 ($)", value=100000, step=1000)
    st.divider()
    st.subheader("保有株式数")
    current_shares = {t: st.number_input(f"{t}", value=0, step=1) for t in TICKERS}
    
    st.divider()
    st.header("⚙️ ロジック設定")
    last_rebalance_date = st.date_input("前回のリバランス実施日", datetime.now() - timedelta(days=10))

# --- ロジック演算エンジン ---
def calculate_logic(prices, rate):
    # 1. 1ヶ月トータルリターン実績（年換算）
    # 直近21営業日のリターンを年率化
    ret_1m = (prices.iloc[-1] / prices.iloc[-21] - 1) * 12
    max_other_ret = ret_1m.drop("BOXX").max()
    
    # 2. BOXX増分ロジック
    diff = rate - max(max_other_ret, 0.03)
    boxx_boost = max(0, diff * 3)
    target_boxx = min(0.1 + boxx_boost, 0.4)
    
    # 3. 移動平均計算
    ma1m = prices.rolling(21).mean().iloc[-1]
    ma3m = prices.rolling(63).mean().iloc[-1]
    ma200 = prices.rolling(252).mean().iloc[-1]
    
    # 4. 構成比率の動的調整
    base_rem_weight = (1.0 - target_boxx) / 3
    weights = {t: base_rem_weight for t in TICKERS if t != "BOXX"}
    weights["BOXX"] = target_boxx
    
    reduction_pool = 0
    reduction_details = {}
    
    for t in ["GDE", "RSSB", "DBMF"]:
        under_pct = (ma200[t] - ma3m[t]) / ma200[t]
        # 乖離が3%以上 かつ 回復基調にない(1mMA < 3mMA)
        if under_pct > 0.03 and ma1m[t] < ma3m[t]:
            reduction = weights[t] * under_pct
            weights[t] -= reduction
            reduction_pool += reduction
            reduction_details[t] = under_pct
        else:
            reduction_details[t] = 0.0

    # 加算先判定（一番マシなETF）
    # 相対パフォーマンス = (3mMA / 200mMA) - 1
    rel_perf = (ma3m / ma200) - 1
    best_ticker = rel_perf.idxmax()
    weights[best_ticker] += reduction_pool
    
    return weights, ret_1m, ma1m, ma3m, ma200, reduction_details, best_ticker

# 計算実行
target_weights, returns, m1, m3, m200, reduct_info, best_t = calculate_logic(price_df, last_rate)

# --- 判定: リバランス要否 ---
def check_necessity(weights, current_shares, prices, total_val, last_date):
    reasons = []
    
    # A. 定期リバランス（毎月20日以降の初平日）判定
    today = datetime.now().date()
    nyse = mcal.get_calendar('NYSE')
    schedule = nyse.schedule(start_date=today.replace(day=1), end_date=today + timedelta(days=31))
    valid_days = [d.date() for d in schedule.index if d.date().day >= 20]
    is_periodic_day = (today == valid_days[0]) if valid_days else False
    if is_periodic_day: reasons.append("定期リバランス日（20日以降の初回営業日）")

    # B. 乖離度(2σ)判定
    # 簡易的に各銘柄のウェイト乖離が目標比の10%以上(あるいは絶対値で5%以上等)をσの代用として判定
    current_vals = {t: current_shares[t] * prices[t] for t in TICKERS}
    curr_total = sum(current_vals.values())
    if curr_total > 0:
        for t in TICKERS:
            curr_w = current_vals[t] / curr_total
            if abs(curr_w - weights[t]) > 0.05: # 5%以上の乖離をトリガーとする
                reasons.append(f"乖離度超過: {t}")

    # C. 週1回制限
    days_since_last = (today - last_date).days
    ready_by_time = days_since_last >= 7
    
    is_required = len(reasons) > 0 and ready_by_time
    return is_required, reasons, ready_by_time

is_req, req_reasons, time_ok = check_necessity(target_weights, current_shares, current_prices, total_assets, last_rebalance_date)

# --- UI表示 ---

# 1. 判定ステータス
st.subheader("📢 リバランス要否ステータス")
if is_req:
    st.error(f"### 【要実行】リバランス条件に合致しました\n理由: {', '.join(req_reasons)}")
else:
    if not time_ok:
        st.warning("### 【待機】ロジック上の条件は満たしていますが、週1回の実行制限内です。")
    else:
        st.success("### 【維持】現在リバランスの必要はありません。")

# 2. 判断プロセスの可視化
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("適用政策金利 (BOXX閾値)", f"{last_rate:.2%}")
    st.write("**BOXX比率の決定過程**")
    st.caption(f"他銘柄最大リターン: {returns.drop('BOXX').max():.2%}")
    st.progress(target_weights["BOXX"], text=f"BOXX目標比率: {target_weights['BOXX']:.1%}")

with col2:
    st.write("**トレンド調整判定 (3m vs 200d)**")
    adjust_df = pd.DataFrame({
        "乖離率": {t: f"{(m3[t]/m200[t]-1):.2%}" for t in ["GDE", "RSSB", "DBMF"]},
        "減算対象": {t: "YES" if reduct_info[t] > 0 else "NO" for t in ["GDE", "RSSB", "DBMF"]}
    })
    st.table(adjust_df)

with col3:
    st.write("**資金の再配分先**")
    st.info(f"もっとも好調な銘柄: **{best_t}**")
    st.caption("減算された比率は上記銘柄に集約されます。")

# 3. データの網羅的表示（グラフ）
st.divider()
st.subheader("📈 判定に用いた市場データの推移")
tab1, tab2 = st.tabs(["価格・移動平均", "ポートフォリオ乖離"])

with tab1:
    selected_t = st.selectbox("銘柄を選択して詳細を確認", TICKERS)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=price_df.index, y=price_df[selected_t], name="Price"))
    fig.add_trace(go.Scatter(x=price_df.index, y=price_df[selected_t].rolling(63).mean(), name="3m MA", line=dict(dash='dash')))
    fig.add_trace(go.Scatter(x=price_df.index, y=price_df[selected_t].rolling(252).mean(), name="200d MA", line=dict(width=3)))
    fig.update_layout(height=400, margin=dict(l=0,r=0,b=0,t=0))
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    # 現在のポートフォリオ比率 vs 目標
    curr_v = {t: current_shares[t] * current_prices[t] for t in TICKERS}
    total_v = sum(curr_v.values()) if sum(curr_v.values()) > 0 else 1
    
    comp_df = pd.DataFrame({
        "現在": [curr_v[t]/total_v for t in TICKERS],
        "目標": [target_weights[t] for t in TICKERS]
    }, index=TICKERS)
    st.bar_chart(comp_df)

# 4. 売買実行指図
st.divider()
st.subheader("🛒 リバランス実行指図（売買シミュレーション）")

action_data = []
for t in TICKERS:
    target_val = total_assets * target_weights[t]
    current_val = current_shares[t] * current_prices[t]
    diff_val = target_val - current_val
    diff_qty = diff_val / current_prices[t]
    
    action = "BUY" if diff_qty > 0 else "SELL"
    color_class = "buy-action" if action == "BUY" else "sell-action"
    
    action_data.append({
        "銘柄": t,
        "目標比率": f"{target_weights[t]:.1%}",
        "現在比率": f"{(current_val/total_assets if total_assets >0 else 0):.1%}",
        "アクション": action,
        "数量": abs(int(diff_qty)),
        "概算金額": f"${abs(diff_val):,.2f}"
    })

st.table(pd.DataFrame(action_data))

st.caption(f"Data updated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Source: yfinance)")