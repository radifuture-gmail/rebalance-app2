import streamlit as st
from src.data_loader import get_etf_data, get_risk_free_rate, calculate_technical_indicators
from src.rebalance_logic import calculate_dynamic_ratios, check_rebalance_trigger, calculate_trade_shares
from src.visualizer import (
    plot_price_with_ma, show_metrics, plot_ratio_comparison, 
    show_logic_summary, show_rebalance_status, show_action_table
)

st.set_page_config(page_title="乖離度リバランス判定", layout="wide")

st.title("🔍 乖離度リバランス判定 (Daily Check)")

# 運用ルール表示
st.info("💡 運用ルール：乖離判定は日次で行うが、リバランス執行は週1回までとする。")

# 1. データ取得
with st.spinner("最新市場データを取得中..."):
    tickers = ["BOXX", "GDE", "RSSB", "DBMF"]
    df_prices = get_etf_data(tickers)
    policy_rate = get_risk_free_rate()
    indicators = calculate_technical_indicators(df_prices)

if indicators.empty:
    st.error("インジケーターの計算に必要なデータが不足しています。")
    st.stop()

# 2. 市場概況
st.header("1. 市場データ・インジケーター")
show_metrics(policy_rate, indicators)
plot_price_with_ma(df_prices, tickers)

# 3. 動的ターゲット比率算出
target_ratios = calculate_dynamic_ratios(indicators, policy_rate)

# 4. 保有状況入力
st.header("2. 保有資産状況と乖離判定")
with st.expander("現在の保有数量を編集", expanded=False):
    col_input = st.columns(len(tickers))
    current_holdings = {}
    for i, t in enumerate(tickers):
        # 【修正】valueを明示的にfloatに変換し、stepも1.0(float)に統一
        val = float(st.session_state['virtual_holdings'][t])
        current_holdings[t] = col_input[i].number_input(
            f"{t} 保有数量", 
            value=val,
            step=1.0,
            key=f"input_{t}"
        )
        st.session_state['virtual_holdings'][t] = current_holdings[t]

# 5. リバランス判定
current_prices = indicators["current_price"].to_dict()
is_required, actual_ratios, deviations = check_rebalance_trigger(
    current_holdings, current_prices, target_ratios
)

show_rebalance_status(is_required, deviations)
plot_ratio_comparison(actual_ratios, target_ratios)

# 6. 判断過程
show_logic_summary(indicators, target_ratios, policy_rate)

# 7. アクション
if is_required:
    st.header("3. 執行プラン")
    total_value = sum(current_holdings[t] * current_prices[t] for t in tickers)
    df_actions = calculate_trade_shares(total_value, target_ratios, current_prices, current_holdings)
    show_action_table(df_actions)
    
    if st.button("リバランスを実行したとして保有数を更新(模擬)"):
        for t in tickers:
            target_val = total_value * target_ratios[t]
            st.session_state['virtual_holdings'][t] = target_val / current_prices[t]
        st.rerun()
else:
    st.success("現在のポートフォリオは、動的調整後のターゲット比率に対して許容範囲内です。")