import streamlit as st
import pandas as pd
import google.generativeai as genai
import os
from dotenv import load_dotenv
from datetime import datetime
from PIL import Image

# 1. 環境変数の読み込み（.envファイルからAPIキーを取得）
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# 2. ページ設定（ブラウザのタブ名やアイコン）
st.set_page_config(
    page_title="MIYAKAKU LEATHER 投稿作成ツール",
    page_icon="✨",
    layout="centered"
)

# 3. APIキーの設定確認
if not api_key:
    st.error("APIキーが見つかりません。.envファイルに GEMINI_API_KEY が正しく設定されているか確認してください。")
    st.stop()

# Gemini APIの初期設定
genai.configure(api_key=api_key)

# 4. 履歴データを保存・読み込みするための関数設定
CSV_FILE = "posts_data.csv"
IMAGE_DIR = "history_images"

# 写真保存用のフォルダがなければ自動作成する
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

def load_history():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)
    else:
        # ファイルがない場合は空の表を作る（濃度と画像パスの列を追加）
        return pd.DataFrame(columns=["日時", "シリーズ", "テーマ・商品", "長さ", "濃度", "画像パス", "生成キャプション"])

def save_history(df):
    df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")

# ==========================================
# 画面のUI（見た目）構築
# ==========================================

st.title("MIYAKAKU LEATHER 投稿作成ツール")
st.markdown("100年の歴史を持つ「宮覚」の魂を乗せたInstagramキャプションを自動生成します。")

st.header("📝 投稿内容の設定")

# --- UI: シリーズ選択 ---
# いただいたパワポ資料に基づき、AIに伝える詳細な特徴を設定
series_options = {
    "クラフトキャンバス": "歴史に名を刻む有名絵画からインスピレーションを受け、革製品に新たな命を吹き込む試み。アートの要素を取り入れたエレガントなデザイン。",
    "モータークラフト": "バイクへの情熱と共に生まれたシリーズ。ライダーに必要な機能性とスタイルに職人技を掛け合わせた、耐久性と快適な使い心地が特徴。",
    "クラシックエレメンツ": "宮覚ブランドの核となる伝統と革新の融合を最も強く反映したオーソドックススタイル。丁寧な手仕事とクラシカルな美しさを追求。"
}
selected_series = st.selectbox("1. シリーズを選択してください", list(series_options.keys()))

# --- UI: テーマ入力 ---
theme_input = st.text_area(
    "2. 今日の作業内容、具体的な商品名、アピールしたいポイントを入力してください", 
    placeholder="例：モータークラフトシリーズの新作ツーリングバッグ。分厚い栃木レザーを手縫いで仕上げました。耐久性をアピールしたいです。"
)

# --- UI: 長さスライダー ---
length_mapping = {
    1: "短め（サクッと読めるSNS向け。挨拶とハッシュタグを中心に簡潔に）",
    2: "普通（ストーリーを伝える基本の長さ。作業内容や想いを適度に盛り込む）",
    3: "長め（深く語りかける長文。職人としてのこだわりや技術の奥深さをじっくり読ませる）"
}
length_slider = st.select_slider(
    "3. 文章のボリュームを選択してください",
    options=[1, 2, 3],
    format_func=lambda x: {1: "短め", 2: "普通", 3: "長め"}[x]
)

# --- UI: コンセプト濃度スライダー（5段階） ---
concept_mapping = {
    1: "レベル1：商品フォーカス（ブランドの歴史には触れず、純粋な商品の魅力や作業内容を端的に伝える）",
    2: "レベル2：ほのかな職人感（商品を主役にしつつ、丁寧な手仕事など職人のエッセンスを少し添える）",
    3: "レベル3：バランス型（商品の魅力と、父から受け継いだ技術などブランドのアイデンティティを自然に織り交ぜる）",
    4: "レベル4：ストーリー強め（100年の歴史、3世代の職人魂など、ブランドの核となるストーリーをしっかり語る）",
    5: "レベル5：フル・エモーション（屋号復活の情熱、サステナブルな想いなど、ブランド哲学を前面に押し出した熱い長文）"
}
slider_labels = {
    1: "レベル1（あっさり / 商品重視）",
    2: "レベル2（ややあっさり）",
    3: "レベル3（標準 / バランス）",
    4: "レベル4（濃いめ / ストーリー重視）",
    5: "レベル5（情熱的 / フル・エモーション）"
}
concept_slider = st.select_slider(
    "4. ブランドコンセプトの濃度を選択してください",
    options=[1, 2, 3, 4, 5],
    value=3,
    format_func=lambda x: slider_labels[x]
)

# --- UI: 画像アップロード ---
uploaded_file = st.file_uploader("5. 写真をアップロード（任意・革の質感をAIに見せます）", type=["jpg", "jpeg", "png"])
if uploaded_file is not None:
    image_preview = Image.open(uploaded_file)
    st.image(image_preview, caption="アップロードされた写真", use_container_width=True)

# --- UI: AIモデル選択 ---
# APIを使って、現在利用可能なモデルのリストを取得
valid_models = []
try:
    valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
except Exception as e:
    st.error(f"モデル一覧の取得に失敗しました: {e}")

# リストが空でなければ、プルダウンを表示（デフォルトはリストの先頭）
if valid_models:
    selected_model = st.selectbox("4. 使用するAIモデルを選択してください", valid_models)
else:
    st.warning("利用可能なAIモデルが見つかりません。")
    selected_model = None

# ==========================================
# AI生成処理の実行
# ==========================================

if st.button("✨ AIでキャプションを生成する", type="primary"):
    if not theme_input:
        st.warning("「今日の作業内容、具体的な商品名、アピールしたいポイント」を入力してください。")
    else:
        with st.spinner("MIYAKAKU LEATHERの魂を込めた文章を生成中..."):
            
            # AIに渡す「完璧なプロンプト（指示書）」の組み立て
            system_prompt = f"""
あなたは「MIYAKAKU LEATHER（宮覚）」の専属SNSライターであり、ブランドの魂を完璧に理解しています。
以下のブランドコンセプトと指示に基づいて、Instagram用の魅力的なキャプションとハッシュタグを作成してください。

【ブランドコンセプト】
- 100年の歴史を持つ「MIYAKAKU(宮覚)」の屋号を復活させたレザーブランド。
- 曽祖父の建具職人の魂、父が60年以上磨き上げたハンドバッグ製作の技、そして自身のデザイナーとしての20年以上の経験。これら3世代の職人の心と技とデザインを融合。
- 「サステナブル」でタイムレスな「技」と「デザイン」。
- 1年後の受注生産オープンへ向け、制作の記録を現在公開中。

【今回焦点を当てるシリーズ】
シリーズ名: {selected_series}
シリーズの特徴: {series_options[selected_series]}

【ユーザーからの指示（具体的な商品やテーマ）】
{theme_input}

【出力の条件】
- 文章の長さの目安: {length_mapping[length_slider]}
- ブランドストーリーの濃度: {concept_mapping[concept_slider]}
- もし画像が提供されている場合は、写真に写っている革の質感、色合い、ステッチの細かさ、形状などを自ら観察し、その具体的な様子を文章の描写に反映させてください。
- プロの革職人・デザイナーとしての誇りや情熱が伝わる、洗練されたトーン＆マナーで書くこと。
- 最後に、Instagramに最適なハッシュタグをいくつか（#MIYAKAKULEATHER #宮覚 などを必ず含めて）提案すること。
- 出力は生成されたキャプションのテキストのみとし、解説などは不要です。
"""
            try:
                if not selected_model:
                    st.error("AIモデルが選択されていないため、生成を実行できません。")
                    st.stop()

                # 画面のプルダウンで選択されたモデル名を使ってAPIを呼び出す
                model = genai.GenerativeModel(selected_model)
                
                # 画像の有無でAIに渡すデータを変える
                if uploaded_file is not None:
                    # 画像とテキストの両方を渡す
                    img_data = Image.open(uploaded_file)
                    response = model.generate_content([system_prompt, img_data])
                else:
                    # テキストのみ渡す
                    response = model.generate_content(system_prompt)
                    
                generated_text = response.text

                # 結果の表示
                st.subheader("💡 生成されたInstagramキャプション")
                st.info(generated_text)
                
                # 画像の保存処理
                saved_image_path = ""
                current_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                if uploaded_file is not None:
                    # 拡張子を取得して保存ファイル名を決定
                    ext = uploaded_file.name.split(".")[-1]
                    saved_image_path = os.path.join(IMAGE_DIR, f"image_{current_time_str}.{ext}")
                    # 画像をフォルダに保存
                    img_data = Image.open(uploaded_file)
                    img_data.save(saved_image_path)

                # Pandasを使って履歴へ保存
                history_df = load_history()
                new_data = pd.DataFrame([{
                    "日時": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                    "シリーズ": selected_series,
                    "テーマ・商品": theme_input,
                    "長さ": {1: "短め", 2: "普通", 3: "長め"}[length_slider],
                    "濃度": slider_labels[concept_slider],
                    "画像パス": saved_image_path,
                    "生成キャプション": generated_text
                }])
                history_df = pd.concat([new_data, history_df], ignore_index=True)
                save_history(history_df)
                
                st.success("履歴と写真を保存しました！この文章をコピーして、Instagramへ投稿してください。")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

# ==========================================
# 履歴の表示
# ==========================================
st.divider()
st.header("📊 過去の投稿履歴")
history_df = load_history()
if not history_df.empty:
    # 履歴を1件ずつ展開できるアコーディオン形式で表示
    for index, row in history_df.iterrows():
        with st.expander(f"投稿日時: {row['日時']} | シリーズ: {row['シリーズ']}"):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # 画像パスが記録されており、かつ実際のファイルが存在すれば表示
                if pd.notna(row.get("画像パス")) and row["画像パス"] != "" and os.path.exists(row["画像パス"]):
                    st.image(row["画像パス"], use_container_width=True)
                else:
                    st.info("写真なし")
                    
            with col2:
                st.write(f"**テーマ・商品:** {row['テーマ・商品']}")
                if "濃度" in row:
                    st.write(f"**設定:** 長さ = {row['長さ']} / 濃度 = {row['濃度']}")
                st.text_area("生成キャプション", row['生成キャプション'], height=200, key=f"cap_{index}")
                
else:
    st.write("まだ履歴がありません。キャプションを生成するとここに保存され、エクセル(CSV)としても記録されます。")