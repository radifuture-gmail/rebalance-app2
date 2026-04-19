import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 設定 ---
TICKERS = ["BOXX", "GDE", "RSSB", "DBMF"]
DEFAULT_WEIGHTS = {"BOXX": 0.10, "GDE": 0.30, "RSSB": 0.30, "DBMF": 0.30}
RATE_TICKER = "^IRX"  # 米国13週国債利回り

st.set_page_config(page_title="Strategic Rebalancer 2026", layout="wide")

# カスタムCSSで視認性を向上
st.markdown("""
    <style>
    .metric-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #2e77d1; }
    .status-box { padding: 15px; border-radius: 5px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- ヘルパー関数 ---
def is_business_day(date):
    return date.weekday() < 5  # 0-4 is Mon-Fri

def get_first_weekday_after_20th(year, month):
    dt = datetime(year, month, 20)
    while not is_business_day(dt):
        dt += timedelta(days=1)
    return dt.date()

# --- データ取得 ---
@st.cache_data(ttl=3600)
def fetch_data():
    all_symbols = TICKERS + [RATE_TICKER]
    # MA200日＋余裕を持って1.5年分
    data = yf.download(all_symbols, period="2y", interval="1d")
    prices = data['Adj Close'].ffill()
    return prices

# --- メインロジック ---
def calculate_dynamic_logic(prices, policy_rate):
    # 1. 指標計算
    # 1ヶ月トータルリターン年換算 (21営業日)
    ret_1m = (prices.iloc[-1] / prices.iloc[-21] - 1) * 12
    # 移動平均
    ma1m = prices.rolling(window=21).mean().iloc[-1]
    ma3m = prices.rolling(window=63).mean().iloc[-1]
    ma200d = prices.rolling(window=200).mean().iloc[-1]
    
    # 2. BOXX比率の決定
    other_etfs = ["GDE", "RSSB", "DBMF"]
    max_other_ret = max(ret_1m[other_etfs].max(), 0.03)
    diff = policy_rate - max_other_ret
    
    boxx_boost = max(0, diff * 3)
    target_boxx = min(0.10 + boxx_boost, 0.40)
    
    # 基本比率の構築
    rem_w = (1.0 - target_boxx) / 3
    weights = {t: (target_boxx if t == "BOXX" else rem_w) for t in TICKERS}
    
    # 3. MA乖離による動的調整
    adjustment_logs = []
    reduction_pool = 0
    
    # 各銘柄の「マシ」度合い判定（加算先決定用）
    relative_perf = (ma3m / ma200d) - 1
    best_ticker = relative_perf.idxmax()

    for t in other_etfs:
        under_pct = (ma200d[t] - ma3m[t]) / ma200d[t]
        # 条件: 3%以上下回る かつ 1mMAが3mMAを下回っている（回復していない）
        if under_pct > 0.03 and ma1m[t] < ma3m[t]:
            reduction = weights[t] * under_pct
            weights[t] -= reduction
            reduction_pool += reduction
            adjustment_logs.append(f"⚠️ {t}: MA乖離 {under_pct:.1%} 低迷により比率削減")
        elif ma1m[t] >= ma3m[t] and t != "BOXX":
            adjustment_logs.append(f"✅ {t}: 回復基調(1mMA > 3mMA)のためデフォルト維持")

    weights[best_ticker] += reduction_pool
    if reduction_pool > 0:
        adjustment_logs.append(f"ℹ️ 削減分 {reduction_pool:.1%} を最も好調な {best_ticker} へ配分")

    return weights, ret_1m, ma1m, ma3m, ma200d, adjustment_logs, target_boxx

# --- UIレイアウト ---
st.title("🦅 Advanced Dynamic Rebalancer")
st.markdown(f"**分析実行日:** {datetime.now().strftime('%Y-%m-%d')}")

try:
    price_df = fetch_data()
    latest_prices = price_df[TICKERS].iloc[-1]
    raw_rate = yf.Ticker(RATE_TICKER).fast_info['last_price'] / 100
except:
    st.error("データの取得に失敗しました。")
    st.stop()

# サイドバー
with st.sidebar:
    st.header("⚙️ システム設定")
    user_rate = st.number_input("政策金利プロキシ (%)", value=raw_rate*100, step=0.1) / 100
    total_capital = st.number_input("運用総額 ($)", value=100000, step=1000)
    
    st.divider()
    st.subheader("現在の保有株数")
    holdings = {t: st.number_input(f"{t}", value=100) for t in TICKERS}
    
    st.divider()
    last_reb_date = st.date_input("前回リバランス日", datetime.now() - timedelta(days=10))

# 計算実行
final_w, ret1m, m1, m3, m200, logs, b_target = calculate_dynamic_logic(price_df, user_rate)

# --- 1. 判定データの網羅的表示 ---
st.header("1. 判定基盤データの解析")
col_stats = st.columns(4)
for i, t in enumerate(TICKERS):
    with col_stats[i]:
        st.markdown(f"**{t}**")
        st.write(f"価格: ${latest_prices[t]:.2f}")
        st.write(f"1mリターン: {ret1m[t]:.1%}")
        st.caption(f"3mMA: {m3[t]:.1f} / 200dMA: {m200[t]:.1f}")

# --- 2. 判断プロセスの可視化 ---
st.header("2. リバランス判断プロセス")
proc_col1, proc_col2 = st.columns(2)

with proc_col1:
    st.subheader("Step A: BOXX比率の決定")
    boxx_diff = user_rate - max(ret1m.drop("BOXX").max(), 0.03)
    st.code(f"政策金利({user_rate:.1%}) - Max(他リターン, 3%) = 乖離({boxx_diff:.1%})")
    st.write(f"結果: BOXX目標比率 **{b_target:.1%}** (Base 10% + 加算)")
    
    fig_ma = go.Figure()
    for t in ["GDE", "RSSB", "DBMF"]:
        gap = (m3[t]/m200[t] - 1) * 100
        fig_ma.add_trace(go.Bar(x=[t], y=[gap], name=t, marker_color='red' if gap < -3 else 'blue'))
    fig_ma.update_layout(title="MA乖離率 (%) [3m / 200d]", yc軸_title="%", height=300)
    st.plotly_chart(fig_ma, use_container_width=True)

with proc_col2:
    st.subheader("Step B: 動的配分調整")
    if not logs:
        st.write("調整なし: 全銘柄が基準内です。")
    for log in logs:
        st.write(log)

# --- 3. リバランス要否の判定 ---
st.header("3. リバランス実行判定")
today = datetime.now().date()
is_periodic = today >= get_first_weekday_after_20th(today.year, today.month) and today.month % 3 == 0
days_since_last = (today - last_reb_date).days
is_weekly_limit = days_since_last < 7

# 乖離判定 (現在の評価額ベースの比率 vs 目標比率)
current_values = {t: holdings[t] * latest_prices[t] for t in TICKERS}
actual_total = sum(current_values.values())
current_weights = {t: current_values[t]/actual_total for t in TICKERS}
drift_trigger = any(abs(current_weights[t] - final_w[t]) > 0.05 for t in TICKERS) # 5%以上の乖離をσ2のプロキシとして設定

rebalance_needed = (is_periodic or drift_trigger) and not is_weekly_limit

c_status1, c_status2, c_status3 = st.columns(3)
with c_status1:
    st.metric("定期リバランス期", "Yes" if is_periodic else "No")
with c_status2:
    st.metric("乖離(Drift)検知", "⚠️ 発生中" if drift_trigger else "正常")
with c_status3:
    st.metric("実行制限(週1回)", "OK" if not is_weekly_limit else "待機中", delta=f"{days_since_last}日経過")

if rebalance_needed:
    st.error("🚨 【判定】リバランス実行を推奨します")
else:
    st.success("✅ 【判定】現在は維持（No Action）で問題ありません")

# --- 4. 売買指図の可視化 ---
st.header("4. リバランス実行指図")
trade_data = []
for t in TICKERS:
    target_val = total_capital * final_w[t]
    current_val = current_values[t]
    diff_val = target_val - current_val
    diff_qty = diff_val / latest_prices[t]
    
    trade_data.append({
        "銘柄": t,
        "現在比率": f"{current_weights[t]:.1%}",
        "目標比率": f"{final_w[t]:.1%}",
        "差分額 ($)": f"{diff_val:+,.2f}",
        "アクション": "BUY" if diff_qty > 0 else "SELL",
        "株数": abs(int(diff_qty))
    })

df_trade = pd.DataFrame(trade_data)
st.table(df_trade)

# ポートフォリオ比較
fig_compare = go.Figure(data=[
    go.Bar(name='Current', x=TICKERS, y=[current_weights[t] for t in TICKERS]),
    go.Bar(name='Target', x=TICKERS, y=[final_w[t] for t in TICKERS])
])
fig_compare.update_layout(barmode='group', title="ポートフォリオ構成比較", height=400)
st.plotly_chart(fig_compare, use_container_width=True)

st.caption("※判定ロジック：3ヶ月移動平均が200日移動平均を3%以上下回った場合、その乖離分を比率から減算し、最もパフォーマンスが良い銘柄へ加算。ただし1ヶ月MAが3ヶ月MA以上なら回復とみなし減算を免除。")