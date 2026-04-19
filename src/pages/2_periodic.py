import streamlit as st
from datetime import datetime
from src.data_loader import get_etf_data, get_risk_free_rate, calculate_technical_indicators
from src.rebalance_logic import calculate_dynamic_ratios, calculate_trade_shares
from src.visualizer import (
    plot_price_with_ma, show_metrics, plot_ratio_comparison, 
    show_logic_summary, show_action_table
)

st.set_page_config(page_title="定期リバランス判定", layout="wide")

st.title("📅 定期リバランス判定 (Quarterly/Monthly)")

# 1. 定期判定ロジック
today = datetime.now()
# 簡略化：3, 6, 9, 12月の20日以降をリバランス期間と仮定
is_rebalance_month = today.month in [3, 6, 9, 12]
is_after_20th = today.day >= 20
is_periodic_trigger = is_rebalance_month and is_after_20th

st.info(f"本日の日付: {today.strftime('%Y-%m-%d')}")
if is_periodic_trigger:
    st.warning("🔔 定期リバランスの実施時期（四半期末・20日以降）に該当します。")
else:
    st.success("ℹ️ 現在は定期リバランスの実施期間外です。")

# 2. データ取得
with st.spinner("最新データを取得中..."):
    tickers = ["BOXX", "GDE", "RSSB", "DBMF"]
    df_prices = get_etf_data(tickers)
    policy_rate = get_risk_free_rate()
    indicators = calculate_technical_indicators(df_prices)

# 3. 市場概況
st.header("1. 市場データ・インジケーター")
show_metrics(policy_rate, indicators)
plot_price_with_ma(df_prices, tickers)

# 4. 動的ターゲット比率の算出
target_ratios = calculate_dynamic_ratios(indicators, policy_rate)

# 5. 現在の保有状況（Session Stateを使用）
st.header("2. 保有資産状況")
current_holdings = st.session_state['virtual_holdings']
current_prices = indicators["current_price"].to_dict()
total_value = sum(current_holdings[t] * current_prices[t] for t in tickers)
actual_ratios = {t: (current_holdings[t] * current_prices[t]) / total_value for t in tickers}

plot_ratio_comparison(actual_ratios, target_ratios)
show_logic_summary(indicators, target_ratios, policy_rate)

# 6. 執行プラン（定期リバランス時は乖離に関わらず計算を表示）
st.header("3. 執行プラン")
if is_periodic_trigger:
    st.write("定期ルールに基づき、ターゲット比率への調整案を表示します。")
    df_actions = calculate_trade_shares(total_value, target_ratios, current_prices, current_holdings)
    show_action_table(df_actions)
    
    if st.button("リバランスを実行したとして保有数を更新(模擬)"):
        for t in tickers:
            target_val = total_value * target_ratios[t]
            st.session_state['virtual_holdings'][t] = target_val / current_prices[t]
        st.experimental_rerun()
else:
    st.write("定期リバランス期間外のため、本日のターゲット比率確認のみ行います。")
    with st.expander("参考：今リバランスした場合のアクションを表示"):
        df_actions = calculate_trade_shares(total_value, target_ratios, current_prices, current_holdings)
        show_action_table(df_actions)