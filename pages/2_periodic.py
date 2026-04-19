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

st.info("💡 運用ルール：毎月20日以降で初めに訪れる米国カレンダー上の平日に行うロジックとする。")

# 1. 定期判定ロジック
today = datetime.now()
is_rebalance_month = today.month in [3, 6, 9, 12]
is_after_20th = today.day >= 20
is_periodic_trigger = is_rebalance_month and is_after_20th

st.write(f"本日の日付: **{today.strftime('%Y-%m-%d')}**")
if is_periodic_trigger:
    st.warning("🔔 現在は定期リバランス（四半期末）の実施期間に該当します。")
else:
    st.info("ℹ️ 現在は定期リバランスの実施期間外ですが、現在のターゲット比率を確認できます。")

# 2. データ取得
with st.spinner("最新データを取得中..."):
    tickers = ["BOXX", "GDE", "RSSB", "DBMF"]
    df_prices = get_etf_data(tickers)
    policy_rate = get_risk_free_rate()
    indicators = calculate_technical_indicators(df_prices)

if indicators.empty:
    st.error("データの取得または計算に失敗しました。")
    st.stop()

# 3. 市場概況
st.header("1. 市場データ・インジケーター")
show_metrics(policy_rate, indicators)
plot_price_with_ma(df_prices, tickers)

# 4. 動的ターゲット比率の算出
# 金利調整およびMA調整がすべて反映された比率を算出
target_ratios = calculate_dynamic_ratios(indicators, policy_rate)

# 5. 現在の保有資産状況
st.header("2. 保有資産状況")

# 【修正】型エラー防止のため、Session Stateからの取得時に明示的にfloatへ変換
current_holdings = {t: float(st.session_state['virtual_holdings'][t]) for t in tickers}
current_prices = indicators["current_price"].to_dict()
total_value = sum(current_holdings[t] * current_prices[t] for t in tickers)

actual_ratios = {t: (current_holdings[t] * current_prices[t]) / total_value if total_value > 0 else 0 for t in tickers}

# チャート表示（調整後のターゲットと比較）
plot_ratio_comparison(actual_ratios, target_ratios)

# 判断過程の可視化
show_logic_summary(indicators, target_ratios, policy_rate)

# 6. 執行プラン
st.header("3. 執行プラン")
# 最新の調整後ターゲットへのリバランス案を表示
df_actions = calculate_trade_shares(total_value, target_ratios, current_prices, current_holdings)
show_action_table(df_actions)

if is_periodic_trigger:
    if st.button("定期リバランスを実行（仮想保有数を更新）"):
        for t in tickers:
            target_val = total_value * target_ratios[t]
            # 更新値もfloatで保存
            st.session_state['virtual_holdings'][t] = float(target_val / current_prices[t])
        st.success("リバランス後の状態で保有数を更新しました。")
        st.rerun()
else:
    st.caption("※現在は期間外のため、上記は参考値（今実行した場合の数値）です。")