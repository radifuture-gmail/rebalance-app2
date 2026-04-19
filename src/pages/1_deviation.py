import streamlit as st
from src.data_loader import get_etf_data, get_risk_free_rate, calculate_technical_indicators
from src.rebalance_logic import calculate_dynamic_ratios, check_rebalance_trigger, calculate_trade_shares
from src.visualizer import (
    plot_price_with_ma, show_metrics, plot_ratio_comparison, 
    show_logic_summary, show_rebalance_status, show_action_table
)

st.set_page_config(page_title="乖離度リバランス判定", layout="wide")

st.title("🔍 乖離度リバランス判定 (Daily Check)")

# 1. データ取得
with st.spinner("最新データを取得中..."):
    tickers = ["BOXX", "GDE", "RSSB", "DBMF"]
    df_prices = get_etf_data(tickers)
    policy_rate = get_risk_free_rate()
    indicators = calculate_technical_indicators(df_prices)

# 2. 市場概況の表示
st.header("1. 市場データ・インジケーター")
show_metrics(policy_rate, indicators)
plot_price_with_ma(df_prices, tickers)

# 3. 動的ターゲット比率の算出
target_ratios = calculate_dynamic_ratios(indicators, policy_rate)

# 4. 現在の保有状況の入力（シミュレーション用）
st.header("2. 保有資産状況と乖離判定")
with st.expander("現在の保有数量を編集", expanded=False):
    col_input = st.columns(len(tickers))
    current_holdings = {}
    for i, t in enumerate(tickers):
        current_holdings[t] = col_input[i].number_input(
            f"{t} 保有数量", 
            value=st.session_state['virtual_holdings'][t],
            step=1
        )
        st.session_state['virtual_holdings'][t] = current_holdings[t]

# 5. リバランス判定実行
current_prices = indicators["current_price"].to_dict()
is_required, actual_ratios, deviations = check_rebalance_trigger(
    current_holdings, current_prices, target_ratios
)

# 可視化
show_rebalance_status(is_required, deviations)
plot_ratio_comparison(actual_ratios, target_ratios)

# 6. 判断過程の明示
show_logic_summary(indicators, target_ratios, policy_rate)

# 7. 具体的なアクション
if is_required:
    st.header("3. 執行プラン")
    total_value = sum(current_holdings[t] * current_prices[t] for t in tickers)
    df_actions = calculate_trade_shares(total_value, target_ratios, current_prices, current_holdings)
    show_action_table(df_actions)
else:
    st.info("ターゲット比率内に収まっているため、売買アクションは不要です。")