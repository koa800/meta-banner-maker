import streamlit as st
from banner_generator import analyze_lp, build_banner_prompts

# ============================================================
# ページ設定
# ============================================================
st.set_page_config(
    page_title="Meta広告バナーメーカー",
    page_icon="🎨",
    layout="wide",
)

# ============================================================
# カスタムCSS
# ============================================================
st.markdown("""
<style>
    /* 全体 */
    .block-container { max-width: 1000px; padding-top: 2rem; }

    /* ヘッダー */
    .main-title {
        text-align: center;
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        text-align: center;
        color: #888;
        font-size: 1rem;
        margin-bottom: 2rem;
    }

    /* 解析カード */
    .analysis-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    .analysis-card h3 { margin-top: 0; color: #333; }

    /* プロンプトカード */
    .prompt-card {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        background: #fafafa;
    }

    /* バッジ */
    .badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .badge-price { background: #ffeef0; color: #c0392b; }
    .badge-concern { background: #eef0ff; color: #2c3e8c; }
    .badge-trust { background: #eefff4; color: #1e7a46; }

    /* ステップ表示 */
    .step-box {
        background: #f0f2f6;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin: 0.5rem 0;
    }
    .step-box code {
        background: #fff;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.9rem;
    }

    /* コピーボタンの横のテキストエリアを小さく */
    .stTextArea textarea { font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# ヘッダー
# ============================================================
st.markdown('<div class="main-title">Meta広告バナーメーカー</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">LPのURLを入力 → 自動解析 → バナー生成プロンプトをコピーしてChatGPTへ</div>', unsafe_allow_html=True)

# ============================================================
# URL 入力
# ============================================================
col_input, col_btn = st.columns([4, 1])
with col_input:
    url = st.text_input(
        "LP URL",
        placeholder="https://example.com/lp",
        label_visibility="collapsed",
    )
with col_btn:
    analyze_btn = st.button("🔍 解析する", use_container_width=True, type="primary")

# ============================================================
# メイン処理
# ============================================================
if analyze_btn and url:
    # URLバリデーション
    if not url.startswith("http"):
        st.error("URLは http:// または https:// から始めてください。")
        st.stop()

    # 解析実行
    with st.spinner("LPを解析中..."):
        try:
            analysis = analyze_lp(url)
            prompts = build_banner_prompts(analysis)
        except Exception as e:
            st.error(f"LP取得に失敗しました: {e}")
            st.stop()

    # ----- 解析結果 -----
    st.markdown("---")
    st.subheader("📊 LP解析結果")

    title = analysis["meta"].get("title", "") or analysis["meta"].get("og_title", "")
    description = analysis["meta"].get("description", "") or analysis["meta"].get("og_description", "")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**商品/サービス名**")
        st.info(title if title else "（取得できませんでした）")
        st.markdown(f"**カテゴリ**")
        st.info(analysis["category"])
    with col2:
        st.markdown(f"**説明**")
        st.info(description if description else "（取得できませんでした）")
        if analysis["prices"]:
            st.markdown("**価格情報**")
            st.info(" / ".join(analysis["prices"][:5]))

    if analysis["selling_points"]:
        st.markdown("**セールスポイント**")
        sp_cols = st.columns(2)
        for i, sp in enumerate(analysis["selling_points"][:8]):
            with sp_cols[i % 2]:
                st.markdown(f"- {sp}")

    # ----- プロンプト出力 -----
    st.markdown("---")
    st.subheader("🎨 バナー生成プロンプト")
    st.markdown("以下のプロンプトをコピーして **ChatGPT** に貼り付けると、バナー画像が生成されます。")

    # タブ切り替え
    tab_a, tab_b, tab_c, tab_all = st.tabs([
        "🏷️ A: 価格訴求",
        "💭 B: 悩み訴求",
        "🏛️ C: 信頼訴求",
        "📋 まとめてコピー",
    ])

    for tab, prompt_data in [(tab_a, prompts[0]), (tab_b, prompts[1]), (tab_c, prompts[2])]:
        with tab:
            badge_class = {
                "A": "badge-price",
                "B": "badge-concern",
                "C": "badge-trust",
            }[prompt_data["pattern"]]

            st.markdown(
                f'<span class="badge {badge_class}">パターン{prompt_data["pattern"]}</span> '
                f'**{prompt_data["name"]}** ({prompt_data["focus"]})',
                unsafe_allow_html=True,
            )

            # ChatGPT用に整形したプロンプト
            chatgpt_prompt = (
                f"以下の指示に従って、Meta広告用の正方形バナー画像を1枚生成してください。\n\n"
                f"{prompt_data['prompt']}"
            )

            st.code(chatgpt_prompt, language=None)

            st.markdown(
                f'<div class="step-box">'
                f'<strong>使い方:</strong> 上のテキストをコピー → '
                f'<a href="https://chat.openai.com" target="_blank">ChatGPT</a> '
                f'に貼り付け → 画像が生成されます'
                f'</div>',
                unsafe_allow_html=True,
            )

    with tab_all:
        st.markdown("3パターンまとめて生成する場合は、以下をコピーしてChatGPTに貼ってください。")

        all_prompt = (
            f"以下のLP情報をもとに、Meta広告用の正方形バナー画像を **3パターン** 生成してください。\n"
            f"1枚ずつ順番に生成してください。\n\n"
        )
        for p in prompts:
            all_prompt += f"--- パターン{p['pattern']}: {p['name']} ---\n{p['prompt']}\n\n"

        st.code(all_prompt, language=None)

    # ----- 使い方ガイド -----
    st.markdown("---")
    st.subheader("📖 使い方")
    st.markdown("""
1. 上の「解析する」ボタンでLPを解析
2. 生成されたプロンプトの **コピーボタン**（右上）をクリック
3. **[ChatGPT](https://chat.openai.com)** を開いてペースト
4. ChatGPTがDALL-Eでバナー画像を生成してくれます
5. 気に入らなければ「もう少し○○にして」と追加指示するだけ

> **💡 Tips:** 「まとめてコピー」タブを使えば、3パターン一括で生成を依頼できます。
""")

elif analyze_btn and not url:
    st.warning("URLを入力してください。")
