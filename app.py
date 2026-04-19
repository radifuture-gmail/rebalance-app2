import streamlit as st

# 【修正のポイント】
# st.navigation を使用してページを明示的に定義します。
# これにより、フォルダ構成の認識ミスを防ぎ、確実にサイドバーへメニューを表示させます。

def show_home():
    st.title("📊 ETF動的リバランス・シミュレーター")
    st.markdown("""
    このアプリケーションは、市場データ（ETF価格、政策金利）に基づき、
    ロジックに従ったポートフォリオのリバランス判定および可視化を行います。 [cite: 1]

    ### 📁 メニュー案内
    サイドバーから、以下の判定画面を選択してください。

    1. **乖離度リバランス (`1_deviation`)**: 
       - 日次で乖離判定を行い、週1回のリバランス執行ルールを確認します。 [cite: 7]
    2. **定期リバランス (`2_periodic`)**: 
       - 3ヶ月に一度、および毎月20日以降の特定ルールに基づく判定を確認します。 [cite: 7]

    ### 📈 基本構成比率 (Default)
    | 銘柄 (Ticker) | 基準構成比率 | 役割 |
    | :--- | :--- | :--- |
    | **BOXX** | 10% | キャッシュ代替・金利享受 |
    | **GDE** | 30% | ゴールド + 株式レバレッジ |
    | **RSSB** | 30% | 全世界株式 + 債券レバレッジ |
    | **DBMF** | 30% | マネージド・フューチャーズ | [cite: 7]
    """)

# 1. ページの紐付け（pagesフォルダ内のファイルを指定）
pg = st.navigation([
    st.Page(show_home, title="ホーム", icon="🏠"),
    st.Page("pages/1_deviation.py", title="1. 乖離度リバランス", icon="🔍"),
    st.Page("pages/2_periodic.py", title="2. 定期リバランス", icon="📅"),
])

# 2. ページ設定
st.set_page_config(
    page_title="ETF Rebalance Simulator",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 3. 共通の初期状態（Session State）の管理
if 'virtual_holdings' not in st.session_state:
    st.session_state['virtual_holdings'] = {
        'BOXX': 100, 
        'GDE': 100,
        'RSSB': 100,
        'DBMF': 100
    }

# サイドバーへのメッセージ表示
st.sidebar.success("↑ 上記ページを選択してください")

# 4. ナビゲーションの実行（選択されたページの内容を表示）
pg.run()