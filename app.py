import streamlit as st

st.set_page_config(
    page_title="ETF Rebalance Simulator",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 ETF動的リバランス・シミュレーター")

st.markdown("""
このアプリケーションは、市場データ（ETF価格、政策金利）に基づき、
ロジックに従ったポートフォリオのリバランス判定および可視化を行います。 [cite: 1]

### 📁 メニュー案内
サイドバーから、以下の判定画面を選択してください。

1. **乖離度リバランス (`1_deviation`)**: 
   - 日次で乖離判定を行い、週1回のリバランス執行ルールを確認します。 [cite: 6, 7]
2. **定期リバランス (`2_periodic`)**: 
   - 3ヶ月に一度、および毎月20日以降の特定ルールに基づく判定を確認します。 [cite: 6, 7]

### 📈 基本構成比率 (Default)
以下の比率を基準として動的調整を行います。 [cite: 7]
| 銘柄 (Ticker) | 基準構成比率 | 役割 |
| :--- | :--- | :--- |
| **BOXX** | 10% | キャッシュ代替・金利享受 |
| **GDE** | 30% | ゴールド + 株式レバレッジ |
| **RSSB** | 30% | 全世界株式 + 債券レバレッジ |
| **DBMF** | 30% | マネージド・フューチャーズ |
""")

st.sidebar.success("↑ 上記ページを選択してください")

# 仮想保有数量の初期値等の状態管理（Session State）の初期化
if 'virtual_holdings' not in st.session_state:
    st.session_state['virtual_holdings'] = {
        'BOXX': 100, # 初期ダミー値
        'GDE': 100,
        'RSSB': 100,
        'DBMF': 100
    }