import streamlit as st
import pandas as pd
import google.generativeai as genai
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from PIL import Image
import json
import gspread
from google.oauth2.service_account import Credentials

# 1. 環境変数の読み込み（.envファイルからAPIキーを取得）
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# 2. ページ設定（ブラウザのタブ名やアイコン）
st.set_page_config(
    page_title="MIYAKAKU LEATHER 投稿作成ツール",
    page_icon="✨",
    layout="centered"
)

# --- 画面上部の余白を削り、不要なメニューを非表示にするカスタムCSS ---
st.markdown("""
    <style>
        /* 右上のヘッダー（Deployボタンやメニュー）を完全に非表示にする */
        header {
            visibility: hidden;
        }
        /* メインコンテンツ周りの余白（上部・下部）を調整 */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        /* 折りたたみメニュー（エキスパンダー）のタイトルと展開後の背景を真っ白にする */
        div[data-testid="stExpander"] details,
        div[data-testid="stExpander"] summary {
            background-color: #FFFFFF !important;
            border-radius: 8px;
        }
        div[data-testid="stExpander"] details > div {
            background-color: #FFFFFF !important;
        }
    </style>
""", unsafe_allow_html=True)

# === バージョン（世代）管理の初期設定 ===
# まだバージョン番号がなければ「1」をセットする
if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 1

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

# --- ここから追加：Google Drive & Sheets 認証設定 ---
def get_gcp_credentials():
    # スプレッドシートの操作と、ファイル名検索のためのドライブ権限を指定
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds_path = os.path.join(".streamlit", "credentials.json")
    
    # パターン1: ローカルPCの場合（credentials.jsonが存在する）
    if os.path.exists(creds_path):
        return Credentials.from_service_account_file(creds_path, scopes=scopes)
    
    # パターン2: クラウド（本番環境）の場合（Streamlitの金庫から読み込む）
    else:
        creds_dict = json.loads(st.secrets["gcp_service_account_json"])
        return Credentials.from_service_account_info(creds_dict, scopes=scopes)
# --- 追加ここまで ---

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

st.markdown("##### MIYAKAKU LEATHER 投稿作成ツール")
st.caption("100年の歴史を持つ「宮覚」の魂を乗せたInstagramキャプションを自動生成します。")

st.markdown("###### 📝 投稿内容の設定")

# --- UI: シリーズ選択 ---
series_options = {
    "クラフトキャンバス": "歴史に名を刻む有名絵画からインスピレーションを受け、革製品に新たな命を吹き込む試み。アートの要素を取り入れたエレガントなデザイン。",
    "モータークラフト": "バイクへの情熱と共に生まれたシリーズ。ライダーに必要な機能性とスタイルに職人技を掛け合わせた、耐久性と快適な使い心地が特徴。",
    "クラシックエレメンツ": "宮覚ブランドの核となる伝統と革新の融合を最も強く反映したオーソドックススタイル。丁寧な手仕事とクラシカルな美しさを追求。",
    "その他（日常・作業風景）": "特定のシリーズには属さない、職人の日々の思いや工房のリアルな作業風景。作品のアピールではなく、モノづくりへの静かな情熱やプロセスエコノミーを意識したエッセイ調の記述。"
}
# help="説明文" を追加し、タイトルの横に「？」マーク（ツールチップ）を表示させて画面をスッキリさせます
selected_series = st.selectbox(
    "1. シリーズを選択してください", 
    list(series_options.keys()),
    help="【クラフトキャンバス】アート要素\n【モータークラフト】ライダー向け\n【クラシックエレメンツ】伝統スタイル\n【その他】日々の作業風景や想い",
    key=f"input_series_{st.session_state.reset_counter}"
)

# --- UI: テーマ入力 ---
# スマホで見たときに圧迫感がないよう、タイトルを短くしました
theme_input = st.text_area(
    "2. 今日の作業内容、アピールポイント", 
    placeholder="例：モータークラフトの新作バッグ。分厚い栃木レザーを手縫いで仕上げました。",
    help="具体的な商品名や、今日行った作業（ステッチ、裁断など）、特にアピールしたいこだわりを入力してください。",
    key=f"input_theme_{st.session_state.reset_counter}"
)

# --- UI: 画像アップロード ---
# 頻繁に使う画像アップロードを上部に引き上げ、タイトルを短縮しました
uploaded_files = st.file_uploader(
    "3. 写真をアップロード", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True,
    help="革の質感やステッチをAIに見せるための写真です。複数枚選択できます。",
    key=f"input_files_{st.session_state.reset_counter}"
)
if uploaded_files:
    cols = st.columns(len(uploaded_files))
    for i, file in enumerate(uploaded_files):
        image_preview = Image.open(file)
        cols[i].image(image_preview, caption=f"写真 {i+1}", use_container_width=True)

# --- UI: 詳細設定（折りたたみアコーディオン） ---
# 毎回変更しなくていい設定項目を「⚙️ 詳細設定」の中に隠してスクロール量を減らします
with st.expander("⚙️ 詳細設定（文章の長さ・ブランド濃度）"):
    
    length_mapping = {
        1: "短め（サクッと読めるSNS向け。挨拶とハッシュタグを中心に簡潔に）",
        2: "普通（ストーリーを伝える基本の長さ。作業内容や想いを適度に盛り込む）",
        3: "長め（深く語りかける長文。職人としてのこだわりや技術の奥深さをじっくり読ませる）"
    }
    length_slider = st.select_slider(
        "文章のボリューム",
        options=[1, 2, 3],
        format_func=lambda x: {1: "短め", 2: "普通", 3: "長め"}[x],
        help="1:短め（挨拶中心） / 2:普通（適度なストーリー） / 3:長め（こだわりをじっくり読ませる）",
        key=f"input_length_{st.session_state.reset_counter}"
    )

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
        "ブランドコンセプトの濃度",
        options=[1, 2, 3, 4, 5],
        value=3,
        format_func=lambda x: slider_labels[x],
        help="右にいくほど、100年の歴史や3世代の職人魂といった熱いストーリーが濃く反映されます。",
        key=f"input_concept_{st.session_state.reset_counter}"
    )

    # モデル選択も詳細設定の中に収納します
    valid_models = []
    try:
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except Exception as e:
        st.error(f"モデル一覧の取得に失敗しました: {e}")

    if valid_models:
        selected_model = st.selectbox(
            "使用するAIモデル", 
            valid_models, 
            help="通常は一番上のモデルをそのままご使用ください。",
            key=f"input_model_{st.session_state.reset_counter}"
        )
    else:
        st.warning("利用可能なAIモデルが見つかりません。")
        selected_model = None

# ==========================================
# AI生成処理の実行
# ==========================================

# スマホで押しやすいように use_container_width=True を追加してボタンを画面幅いっぱいに広げます
if st.button("✨ AIでキャプションを生成する", type="primary", use_container_width=True):
    if not theme_input:
        st.warning("「今日の作業内容、具体的な商品名、アピールしたいポイント」を入力してください。")
    else:
        with st.spinner("MIYAKAKU LEATHERの魂を込めた文章を生成中..."):
            
            # 現在の日付を取得して季節感を演出
            jst_now = datetime.now(timezone(timedelta(hours=9)))
            today_str = jst_now.strftime("%Y年%m月%d日")

            # 「その他」が選ばれた場合と、シリーズ品が選ばれた場合でAIへの指示を切り替える
            if selected_series == "その他（日常・作業風景）":
                series_context = f"""
【今回の投稿の焦点：工房の日常とプロセス】
今回は特定のシリーズ（完成品）の紹介ではありません。
職人の日々の思い、手仕事のプロセス、工房の匂いや空気感が伝わるような、静かで熱量のあるエッセイ調の文章にしてください。
作品を「売る」ためのアピールではなく、「モノづくりに向き合う姿勢」やプロセスエコノミーを読者と共有することを目的としています。
"""
            else:
                series_context = f"""
【今回焦点を当てるシリーズ】
シリーズ名: {selected_series}
シリーズの特徴: {series_options[selected_series]}
"""

            # AIに渡す「完璧なプロンプト（指示書）」の組み立て
            system_prompt = f"""
あなたは「MIYAKAKU LEATHER（宮覚）」の専属SNSライターであり、ブランドの魂を完璧に理解しています。
以下のブランドコンセプトと指示に基づいて、Instagram用の魅力的なキャプションとハッシュタグを作成してください。

【現在の日付と状況】
- 本日の日付: {today_str} (この時期に合った自然な季節感を文章の冒頭などに軽く織り交ぜてください)
- 現在のステータス: ブランドの正式オープンに向けた準備期間であり、制作の記録や工房の様子を日々発信しています。

【ブランドコンセプト】
- 100年の歴史を持つ「MIYAKAKU(宮覚)」の屋号を復活させたレザーブランド。
- 曽祖父の建具職人の魂、父が60年以上磨き上げたハンドバッグ製作の技、そして自身のデザイナーとしての20年以上の経験。これら3世代の職人の心と技とデザインを融合。
- 「サステナブル」でタイムレスな「技」と「デザイン」。
{series_context}
【ユーザーからの指示（具体的な商品やテーマ）】
{theme_input}

【出力の条件】
- トーン＆マナー: プロの革職人としての確かな技術や誇りは持ちつつも、工房を訪れたお客様に直接語りかけるような、親しみやすくあたたかい温度感（です・ます調）で書いてください。適度に絵文字も交えてください。
- 文章の長さの目安: {length_mapping[length_slider]}
- ブランドストーリーの濃度: {concept_mapping[concept_slider]}
- もし画像が提供されている場合は、写真に写っている革の質感、色合い、ステッチの細かさ、形状などを自ら観察し、その具体的な様子を文章の描写に反映させてください。
- ハッシュタグ: #MIYAKAKULEATHER と #宮覚 を必ず含めた上で、Instagramの最新トレンドを考慮し、拡散力の高いビッグワードとコアなファンに届くニッチなワードをバランス良く合計5〜7個提案してください。
- 固定フレーズ: キャプションの一番最後に必ず「※現在、正式オープンへ向けた制作記録をお届けしています。」という一文を独立した行で添えてください。
- 出力は生成されたキャプションのテキストのみとし、解説などは不要です。
"""
            try:
                if not selected_model:
                    st.error("AIモデルが選択されていないため、生成を実行できません。")
                    st.stop()

                # 画面のプルダウンで選択されたモデル名を使ってAPIを呼び出す
                model = genai.GenerativeModel(selected_model)
                
                # 画像の有無でAIに渡すデータを変える
                if uploaded_files:
                    # 複数の画像を読み込んでリストにまとめる
                    content_parts = [system_prompt]
                    for f in uploaded_files:
                        content_parts.append(Image.open(f))
                    
                    # 画像リストとテキストをまとめてAIに渡す
                    response = model.generate_content(content_parts)
                else:
                    # テキストのみ渡す
                    response = model.generate_content(system_prompt)
                    
                generated_text = response.text

                # 結果の表示
                st.subheader("💡 生成されたInstagramキャプション")
                st.info(generated_text)
                
                # 画像の保存処理（複数枚対応）
                saved_image_paths = []
                current_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                if uploaded_files:
                    for i, f in enumerate(uploaded_files):
                        ext = f.name.split(".")[-1]
                        file_name = f"image_{current_time_str}_{i}.{ext}"
                        
                        # ローカルへ保存
                        path = os.path.join(IMAGE_DIR, file_name)
                        img_data = Image.open(f)
                        img_data.save(path)
                        saved_image_paths.append(path)
                
                # パスのリストをカンマ区切りの文字列にして記録用にする
                saved_image_path_str = ",".join(saved_image_paths)

                # 1. ローカルのCSVへ保存（バックアップ）
                history_df = load_history()
                new_data = pd.DataFrame([{
                    "日時": jst_now.strftime("%Y/%m/%d %H:%M:%S"),
                    "シリーズ": selected_series,
                    "テーマ・商品": theme_input,
                    "長さ": {1: "短め", 2: "普通", 3: "長め"}[length_slider],
                    "濃度": slider_labels[concept_slider],
                    "画像パス": saved_image_path_str,
                    "生成キャプション": generated_text
                }])
                history_df = pd.concat([new_data, history_df], ignore_index=True)
                save_history(history_df)
                
                # 2. スプレッドシートへ保存
                with st.spinner("スプレッドシートへ履歴を書き込み中..."):
                    creds = get_gcp_credentials()
                    client = gspread.authorize(creds)
                    # スプレッドシート「履歴」を開き、最初のシートを取得
                    sheet = client.open("履歴").sheet1
                    
                    # スプレッドシートが空の場合はヘッダー（1行目）を自動追加
                    if not sheet.get_all_values():
                        sheet.append_row(["日時", "シリーズ", "テーマ・商品", "長さ", "濃度", "画像ファイル名", "生成キャプション"])
                    
                    # データの追加
                    sheet.append_row([
                        jst_now.strftime("%Y/%m/%d %H:%M:%S"),
                        selected_series,
                        theme_input,
                        {1: "短め", 2: "普通", 3: "長め"}[length_slider],
                        slider_labels[concept_slider],
                        saved_image_path_str,
                        generated_text
                    ])
                
                st.success("履歴と画像ファイル名をスプレッドシートに保存しました！この文章をコピーして、Instagramへ投稿してください。")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

# --- ここから追加：リセットボタン ---
st.markdown("<br>", unsafe_allow_html=True)

# 記憶を完全に消去し、新しい世代（バージョン）に進める専用関数
def reset_inputs():
    # 今のバージョン番号を一時保存
    current_counter = st.session_state.reset_counter
    # 古い記憶をすべて消去（ここで古い写真データ等も消滅します）
    st.session_state.clear()
    # バージョン番号を+1して、新しい世代として再セット
    st.session_state.reset_counter = current_counter + 1

# on_clickでボタンが押された瞬間に世代交代を実行します
st.button("🔄 入力内容をリセットして次の投稿を作る", use_container_width=True, on_click=reset_inputs)
# --- 追加ここまで ---

# ==========================================
# 履歴の表示
# ==========================================
st.divider()
st.markdown("##### 📊 過去の投稿履歴")
history_df = load_history()
if not history_df.empty:
    # 履歴を1件ずつ展開できるアコーディオン形式で表示
    for index, row in history_df.iterrows():
        with st.expander(f"投稿日時: {row['日時']} | シリーズ: {row['シリーズ']}"):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # 画像パスが記録されていれば、カンマで分割して複数表示する
                if pd.notna(row.get("画像パス")) and row["画像パス"] != "":
                    paths = row["画像パス"].split(",")
                    for p in paths:
                        if os.path.exists(p):
                            st.image(p, use_container_width=True)
                else:
                    st.info("写真なし")
                    
            with col2:
                st.write(f"**テーマ・商品:** {row['テーマ・商品']}")
                if "濃度" in row:
                    st.write(f"**設定:** 長さ = {row['長さ']} / 濃度 = {row['濃度']}")
                st.text_area("生成キャプション", row['生成キャプション'], height=200, key=f"cap_{index}")
                
else:
    st.write("まだ履歴がありません。キャプションを生成するとここに保存され、エクセル(CSV)としても記録されます。")