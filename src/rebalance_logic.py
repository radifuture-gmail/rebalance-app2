import pandas as pd
import numpy as np

# 基準構成比率の定義 [cite: 1, 7]
DEFAULT_RATIOS = {
    "BOXX": 0.10,
    "GDE": 0.30,
    "RSSB": 0.30,
    "DBMF": 0.30
}

def calculate_dynamic_ratios(indicators, policy_rate):
    """
    動的調整ロジックを適用して各ETFの目標構成比率を算出する [cite: 7]
    """
    ratios = DEFAULT_RATIOS.copy()
    tickers = ["GDE", "RSSB", "DBMF"]
    
    # 1. BOXX増分判定 [cite: 2, 7]
    # 政策金利 - max(他ETF 1ヶ月リターン実績年換算, 3%)
    other_returns = [indicators.loc[t, "return_1m_annualized"] for t in tickers]
    max_other_return = max(max(other_returns), 0.03)
    boxx_diff = policy_rate - max_other_return
    
    boxx_adjustment = 0
    if boxx_diff > 0:
        # 正の場合、当該プラス×3ずつBOXX比率を上げる（上限40%） [cite: 7]
        boxx_adjustment = min(boxx_diff * 3, 0.40 - DEFAULT_RATIOS["BOXX"])
        ratios["BOXX"] += boxx_adjustment
        
        # 増分を他のETFから等分に減じる
        for t in tickers:
            ratios[t] -= boxx_adjustment / len(tickers)

    # 2. 各ETFの配分減算判定 (MAロジック) [cite: 2, 7]
    adjustments = {t: 0.0 for t in tickers}
    total_reduction = 0.0
    
    for t in tickers:
        ma_3m = indicators.loc[t, "ma_3m"]
        ma_200d = indicators.loc[t, "ma_200d"]
        ma_1m = indicators.loc[t, "ma_1m"]
        
        # 3ヶ月MAが200日MAを3%以上下回っているか [cite: 7]
        ma_ratio = (ma_3m / ma_200d) - 1
        
        # 減算除外判定: 1ヶ月MA >= 3ヶ月MA (トレンド回復) [cite: 2, 7]
        if ma_ratio < -0.03 and not (ma_1m >= ma_3m):
            # 比率に当該%を乗じて減じる [cite: 7]
            reduction = ratios[t] * abs(ma_ratio)
            adjustments[t] = -reduction
            total_reduction += reduction

    # 3. 減算分の再配分 (一番好調なETFへ) [cite: 2, 7]
    if total_reduction > 0:
        # BOXXを含む全ETFの中で1ヶ月リターンが最大のもの [cite: 7]
        best_ticker = indicators["return_1m_annualized"].idxmax()
        ratios[best_ticker] += total_reduction
        for t in tickers:
            ratios[t] += adjustments[t]

    return ratios

def check_rebalance_trigger(current_holdings, current_prices, target_ratios):
    """
    乖離度(2σ)に基づくリバランス要否判定 [cite: 3, 7]
    """
    total_value = sum(current_holdings[t] * current_prices[t] for t in current_holdings)
    actual_ratios = {t: (current_holdings[t] * current_prices[t]) / total_value for t in current_holdings}
    
    # 乖離率の計算
    deviations = {t: actual_ratios[t] - target_ratios[t] for t in target_ratios}
    
    # ここでは簡易的に各銘柄の乖離絶対値の合計や特定閾値(2σ相当の仮定)で判定
    # 要件に基づき「2σ超過」をリバランス推奨とする [cite: 3]
    is_required = any(abs(dev) > 0.05 for dev in deviations.values()) # 5%を仮の2σ閾値とする
    
    return is_required, actual_ratios, deviations

def calculate_trade_shares(total_value, target_ratios, current_prices, current_holdings):
    """
    売買株式数の算出 [cite: 5]
    """
    actions = []
    for t in target_ratios:
        target_val = total_value * target_ratios[t]
        target_shares = target_val / current_prices[t]
        diff_shares = target_shares - current_holdings[t]
        
        actions.append({
            "銘柄": t,
            "現在数": int(current_holdings[t]),
            "変更後数": int(target_shares),
            "差分": int(diff_shares),
            "概算約定金額": diff_shares * current_prices[t]
        })
    return pd.DataFrame(actions)