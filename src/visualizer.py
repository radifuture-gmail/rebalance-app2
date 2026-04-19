import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

def plot_price_with_ma(df, tickers):
    """
    対象ETFの価格推移と移動平均線のマルチラインチャートを表示 [cite: 1]
    """
    fig = go.Figure()
    for t in tickers:
        fig.add_trace(go.Scatter(x=df.index, y=df[t], name=f"{t} Price"))
        # 3ヶ月(63日)移動平均線を追加
        ma3 = df[t].rolling(window=63).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ma3, name=f"{t} MA(3M)", line=dict(dash='dot')))
    
    fig.update_layout(title="ETF価格推移と移動平均線", template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)

def show_metrics(policy_rate, indicators):
    """
    政策金利と比較対象ETFのリターンをメトリックカードで表示 [cite: 1]
    """
    cols = st.columns(len(indicators) + 1)
    cols[0].metric("米国政策金利 (FF)", f"{policy_rate:.2%}")
    for i, (ticker, row) in enumerate(indicators.iterrows()):
        cols[i+1].metric(f"{ticker} 1Mリターン", f"{row['return_1m_annualized']:.2%}")

def plot_ratio_comparison(actual_ratios, target_ratios):
    """
    「現在の構成比率」と「理想の構成比率」を並列表示 [cite: 1]
    """
    col1, col2 = st.columns(2)
    
    with col1:
        fig_curr = px.pie(values=list(actual_ratios.values()), names=list(actual_ratios.keys()), 
                          title="現在の構成比率", hole=0.4)
        st.plotly_chart(fig_curr, use_container_width=True)
        
    with col2:
        fig_target = px.pie(values=list(target_ratios.values()), names=list(target_ratios.keys()), 
                            title="理想の構成比率 (動的調整後)", hole=0.4)
        st.plotly_chart(fig_target, use_container_width=True)

def show_logic_summary(indicators, final_ratios, policy_rate):
    """
    判断過程（BOXX調整、MA乖離など）のサマリーテーブルを表示 [cite: 1, 2, 3, 4]
    """
    st.subheader("💡 判断過程の可視化")
    
    summary_data = []
    for ticker in ["GDE", "RSSB", "DBMF"]:
        ma_ratio = (indicators.loc[ticker, "ma_3m"] / indicators.loc[ticker, "ma_200d"]) - 1
        recovery = "回復中" if indicators.loc[ticker, "ma_1m"] >= indicators.loc[ticker, "ma_3m"] else "劣後"
        
        summary_data.append({
            "項目": f"{ticker} 乖離率(3M/200D)",
            "計算値": f"{ma_ratio:.2%}",
            "閾値": "< -3.0%",
            "判定結果": "減算対象" if ma_ratio < -0.03 else "正常"
        })
        summary_data.append({
            "項目": f"{ticker} 回復判定(1M/3M)",
            "計算値": recovery,
            "閾値": "1M >= 3M",
            "判定結果": "適用（減算実行）" if ma_ratio < -0.03 and recovery == "劣後" else "除外"
        })
    
    st.table(pd.DataFrame(summary_data)) # [cite: 2, 3, 4]

def show_rebalance_status(is_required, deviations):
    """
    リバランス要否のアラートと乖離度ヒートマップを表示 [cite: 6]
    """
    if is_required:
        st.error("⚠️ リバランスを推奨します（乖離度 $2\\sigma$ 超過）")
    else:
        st.success("✅ 現在リバランスは不要です")

    # 乖離度ヒートマップ風表示
    dev_df = pd.DataFrame([deviations], index=["乖離率"])
    st.write("各銘柄のターゲットからの乖離度:")
    st.dataframe(dev_df.style.background_gradient(cmap='RdBu_r', axis=1))

def show_action_table(df_actions):
    """
    売買株式数とBefore/Afterの可視化 [cite: 6]
    """
    st.subheader("🛒 注文予定表 (Action Table)")
    
    def color_diff(val):
        color = 'blue' if val > 0 else 'red' if val < 0 else 'black'
        return f'color: {color}'

    st.dataframe(df_actions.style.applymap(color_diff, subset=['差分']))

    # Before/After 比較グラフ
    st.write("リバランス前後 構成比推移 (概算)")
    fig = px.bar(df_actions, x="銘柄", y=["現在数", "変更後数"], barmode="group")
    st.plotly_chart(fig, use_container_width=True)