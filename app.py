import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. アプリ設定 & スタイル ---
st.set_page_config(page_title="Portfolio Rebalancer 2026", layout="wide")
st.markdown("""
    <style>
    .reportview-container .main .block-container{ max-width: 1200px; }
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 定数・要件定義 ---
TICKERS = ["BOXX", "GDE", "RSSB", "DBMF"]
DEFAULT_WEIGHTS = {"BOXX": 0.10, "GDE": 0.30, "RSSB": 0.30, "DBMF": 0.30}
RATE_TICKER = "^IRX"  # 米国13週国債利回り

# --- 3. データ取得エンジン (エラー回避/堅牢性) ---
@st.cache_data(ttl=3600)
def fetch_data():
    try:
        # MA200日のために十分な期間を取得
        end_date = datetime.now()
        start_date = end_date - timedelta(days=450)
        
        data = yf.download(TICKERS + [RATE_TICKER], start=start_date, end=end_date, interval="1d")
        
        if data.empty:
            return None, None
        
        # マルチインデックス対策
        prices = data['Adj Close'].ffill().dropna()
        # 政策金利の取得 (直近値)
        latest_rate = data['Adj Close'][RATE_TICKER].ffill().iloc[-1] / 100
        
        return prices[TICKERS], latest_rate
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return None, None

def is_us_business_day(date):
    """土日を除外した簡易営業日判定"""
    return date.weekday() < 5

def get_target_rebalance_day(date):
    """毎月20日以降の最初の平日を計算"""
    target = date.replace(day=20)
    while not is_us_business_day(target):
        target += timedelta(days=1)
    return target.date()

# --- 4. ロジック計算エンジン ---
def calculate_logic(prices, policy_rate):
    last_price = prices.iloc[-1]
    
    # A. 1ヶ月トータルリターン (年換算)
    # 21営業日前との比較
    ret_1m = (prices.iloc[-1] / prices.iloc[-21]) - 1
    ret_1m_ann = ret_1m * 12  # 簡易年換算
    
    # B. BOXXブースト判定
    max_other_ret = ret_1m_ann.drop("BOXX").max()
    diff_rate = policy_rate - max(max_other_ret, 0.03)
    boxx_boost = max(0, diff_rate * 3)
    target_boxx = min(0.1 + boxx_boost, 0.4)
    
    # C. 移動平均 (1m=21d, 3m=63d, 200d)
    ma1m = prices.rolling(21).mean().iloc[-1]
    ma3m = prices.rolling(63).mean().iloc[-1]
    ma200d = prices.rolling(200).mean().iloc[-1]
    
    # D. 配分調整
    weights = {t: (1.0 - target_boxx) / 3 for t in TICKERS if t != "BOXX"}
    weights["BOXX"] = target_boxx
    
    reduction_pool = 0
    details = []
    
    for t in ["GDE", "RSSB", "DBMF"]:
        under_pct = (ma200d[t] - ma3m[t]) / ma200d[t]
        is_recovery = ma1m[t] >= ma3m[t]
        
        status = "Default"
        if under_pct >= 0.03 and not is_recovery:
            reduction = weights[t] * under_pct
            weights[t] -= reduction
            reduction_pool += reduction
            status = f"Reduced (-{under_pct:.1%})"
        elif is_recovery:
            status = "Recovery (Protected)"
            
        details.append({"Ticker": t, "MA3m/MA200d": 1-under_pct, "Status": status})

    # 減算分を一番マシなETFへ加算
    perf_ratio = ma3m / ma200d
    best_ticker = perf_ratio.idxmax()
    weights[best_ticker] += reduction_pool
    
    return weights, details, ret_1m_ann, ma3m, ma200d, ma1m

# --- 5. メイン UI ---
prices, auto_rate = fetch_data()

if prices is not None:
    st.title("⚖️ Strategic Portfolio Rebalancer")
    
    # サイドバー: ユーザー入力
    with st.sidebar:
        st.header("Settings")
        user_rate = st.number_input("Policy Rate (%)", value=float(auto_rate*100), step=0.1) / 100
        total_cash = st.number_input("Total Assets ($)", value=100000)
        st.divider()
        st.write("Current Holdings (Shares)")
        shares = {t: st.number_input(f"{t}", value=100) for t in TICKERS}
        last_rebal_date = st.date_input("Last Rebalance Date", datetime.now() - timedelta(days=10))

    # 計算実行
    target_weights, logic_details, ret_ann, m3, m200, m1 = calculate_logic(prices, user_rate)
    
    # --- 要件1: 判定データの可視化 ---
    st.header("1. Market Data & Signals")
    col1, col2, col3 = st.columns(3)
    col1.metric("Policy Rate", f"{user_rate:.2%}")
    col2.metric("Max ETF Return (1m)", f"{ret_ann.drop('BOXX').max():.2%}")
    col3.metric("BOXX Target Weight", f"{target_weights['BOXX']:.1%}")

    # 移動平均の比較図
    df_ma = pd.DataFrame({"1m MA": m1, "3m MA": m3, "200d MA": m200})
    st.bar_chart(df_ma)

    # --- 要件2: 判断過程の可視化 ---
    st.header("2. Logic Judgment Process")
    
    # BOXX判定
    with st.expander("BOXX Boost Logic Details", expanded=True):
        st.write(f"Formula: `{user_rate:.2%} - max({ret_ann.drop('BOXX').max():.2%}, 3.00%) = {user_rate - max(ret_ann.drop('BOXX').max(), 0.03):.4%}`")
        if (user_rate - max(ret_ann.drop('BOXX').max(), 0.03)) > 0:
            st.success("BOXX Boost Applied")
        else:
            st.info("No BOXX Boost (Below threshold)")

    # 動的配分詳細
    st.table(pd.DataFrame(logic_details))

    # --- 要件3: リバランス要否の可視化 ---
    st.header("3. Execution Decision")
    
    today = datetime.now().date()
    target_date = get_target_rebalance_day(today)
    is_periodic = today >= target_date
    
    # 乖離度判定 (σ2相当として現在比率と目標比率の合計乖離を利用)
    current_vals = {t: shares[t] * prices[t].iloc[-1] for t in TICKERS}
    curr_total = sum(current_vals.values())
    curr_weights = {t: v / curr_total for t, v in current_vals.items()}
    drift = sum([abs(curr_weights[t] - target_weights[t]) for t in TICKERS])
    is_drifted = drift > 0.05 # 5%以上の乖離をトリガーとする例
    
    # 週1制限
    is_week_passed = (today - last_rebal_date).days >= 7

    rebal_needed = (is_periodic or is_drifted) and is_week_passed

    c1, c2, c3, c4 = st.columns(4)
    c1.info(f"Monthly Target: {target_date}")
    c2.write(f"Drift Level: {drift:.1%}")
    c3.write(f"Week Limit: {'OK' if is_week_passed else 'Wait'}")
    
    if rebal_needed:
        st.error("🚨 REBALANCE REQUIRED")
        if is_periodic: st.write("- Reason: Regular monthly schedule reached.")
        if is_drifted: st.write("- Reason: Portfolio drift exceeded threshold.")
    else:
        st.success("✅ NO ACTION REQUIRED")
        if not is_week_passed: st.warning("Execution locked (Last rebalance was within 7 days).")

    # --- 要件4: 売買株式数の可視化 ---
    st.header("4. Trading Instructions")
    
    trade_data = []
    for t in TICKERS:
        target_val = total_cash * target_weights[t]
        diff_val = target_val - current_vals[t]
        shares_to_trade = diff_val / prices[t].iloc[-1]
        
        trade_data.append({
            "Ticker": t,
            "Current %": f"{curr_weights[t]:.1%}",
            "Target %": f"{target_weights[t]:.1%}",
            "Action": "BUY" if shares_to_trade > 0 else "SELL",
            "Shares": abs(int(shares_to_trade)),
            "Est. Value ($)": round(diff_val, 2)
        })

    st.dataframe(pd.DataFrame(trade_data), use_container_width=True)
    
    # Before/After Chart
    fig = go.Figure(data=[
        go.Bar(name='Current', x=TICKERS, y=[curr_weights[t] for t in TICKERS]),
        go.Bar(name='Target', x=TICKERS, y=[target_weights[t] for t in TICKERS])
    ])
    fig.update_layout(barmode='group', title="Weight Comparison")
    st.plotly_chart(fig)

else:
    st.error("データの取得に失敗しました。週末や市場休場日の直後の場合、データが未更新の可能性があります。")