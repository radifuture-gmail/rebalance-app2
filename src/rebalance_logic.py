import pandas as pd
import numpy as np

# 基準構成比率
BASE_RATIOS = {
    "BOXX": 0.10,
    "GDE": 0.30,
    "RSSB": 0.30,
    "DBMF": 0.30
}

def calculate_dynamic_ratios(indicators, policy_rate):
    """
    動的調整ロジックを適用して各ETFの目標構成比率を算出する。
    1. BOXX調整 (政策金利ベース)
    2. その他ETF調整 (MAベース)
    """
    if indicators.empty:
        return BASE_RATIOS.copy()
        
    ratios = BASE_RATIOS.copy()
    non_boxx_tickers = ["GDE", "RSSB", "DBMF"]
    all_tickers = ["BOXX", "GDE", "RSSB", "DBMF"]
    
    # --- 1. BOXX比率の動的調整 (政策金利 vs ETFリターン) ---
    # 要件: 政策金利 - max(他3銘柄の1ヶ月リターン年換算, 3%)
    # ※政策金利が3%を超えていても、ETFのリターンがそれを上回っている場合はBOXXは増えません。
    other_returns = [indicators.loc[t, "return_1m_annualized"] for t in non_boxx_tickers]
    max_other_return = max(max(other_returns), 0.03)
    
    boxx_diff = policy_rate - max_other_return
    
    if boxx_diff > 0:
        # 増加幅 = 差分 * 3 (上限 40%)
        boxx_increase = min(boxx_diff * 3, 0.40 - ratios["BOXX"])
        ratios["BOXX"] += boxx_increase
        
        # 増分を他の3銘柄から等分に減じる
        for t in non_boxx_tickers:
            ratios[t] -= boxx_increase / len(non_boxx_tickers)

    # --- 2. BOXX以外の銘柄の配分調整 (MA乖離ロジック) ---
    reductions = {t: 0.0 for t in non_boxx_tickers}
    
    for t in non_boxx_tickers:
        ma_1m = indicators.loc[t, "ma_1m"]
        ma_3m = indicators.loc[t, "ma_3m"]
        ma_200d = indicators.loc[t, "ma_200d"]
        
        # 3ヶ月MA / 200日MA の乖離率
        ma_gap = (ma_3m / ma_200d) - 1
        
        # 回復判定: 1ヶ月MA >= 3ヶ月MA
        # 回復している場合は「減算対象から除外（デフォルト比率維持）」
        is_recovering = ma_1m >= ma_3m
        
        if ma_gap < -0.03 and not is_recovering:
            # 乖離率の絶対値を、その時点の比率に乗じて減算
            reduction_amt = ratios[t] * abs(ma_gap)
            reductions[t] = reduction_amt
            ratios[t] -= reduction_amt

    # --- 3. 減算分の再配分 (一番好調なETFへ) ---
    total_reduction = sum(reductions.values())
    if total_reduction > 0:
        # BOXXを含む全銘柄の中で1ヶ月リターン(年換算)が最大のものへ加算
        best_ticker = indicators.loc[all_tickers, "return_1m_annualized"].idxmax()
        
        # BOXXが最良かつ上限40%に達する場合の考慮
        if best_ticker == "BOXX" and (ratios["BOXX"] + total_reduction) > 0.40:
            allowed = max(0, 0.40 - ratios["BOXX"])
            ratios["BOXX"] += allowed
            remaining = total_reduction - allowed
            if remaining > 0:
                # 残りは次に好調な銘柄（BOXX以外）へ
                second_best = indicators.loc[non_boxx_tickers, "return_1m_annualized"].idxmax()
                ratios[second_best] += remaining
        else:
            ratios[best_ticker] += total_reduction

    return ratios

def check_rebalance_trigger(current_holdings, current_prices, target_ratios):
    """
    動調整後のターゲット比率に基づき、乖離度(2σ相当)を判定する。
    """
    total_value = sum(current_holdings[t] * current_prices[t] for t in target_ratios)
    if total_value == 0:
        return False, {t: 0.0 for t in target_ratios}, {t: 0.0 for t in target_ratios}
        
    actual_ratios = {t: (current_holdings[t] * current_prices[t]) / total_value for t in target_ratios}
    
    # ターゲット比率からの乖離を計算
    deviations = {t: actual_ratios[t] - target_ratios[t] for t in target_ratios}
    
    # 乖離判定の閾値 (2σ相当として5%を採用)
    THRESHOLD = 0.05
    is_required = any(abs(dev) > THRESHOLD for dev in deviations.values())
    
    return is_required, actual_ratios, deviations

def calculate_trade_shares(total_value, target_ratios, current_prices, current_holdings):
    """
    リバランス実行のための売買株式数を算出する。
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