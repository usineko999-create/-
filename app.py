import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- ページ設定 ---
st.set_page_config(page_title="正誤クイズアプリ", page_icon="📝", layout="centered")

# --- Googleスプレッドシート連携の設定 ---
CREDENTIALS_FILE = "secret_key.json"
SPREADSHEET_KEY = "1NHaNYmOv9TOXdmaDmWbVmIa3RFsXkXhVUYkFgASHtTk"

# 【高速化1】接続情報をキャッシュ（記憶）し、毎回通信するのを防ぐ
@st.cache_resource
def get_worksheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_KEY).sheet1

# --- セッション状態の初期化 ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'setup' # 'setup' or 'quiz' or 'result'
if 'questions' not in st.session_state:
    st.session_state.questions = []
if 'current_idx' not in st.session_state:
    st.session_state.current_idx = 0
if 'answered' not in st.session_state:
    st.session_state.answered = False
if 'is_correct' not in st.session_state:
    st.session_state.is_correct = False
# 【追加】更新データを一時保存するリスト
if 'pending_updates' not in st.session_state:
    st.session_state.pending_updates = {}

st.title("📝 正誤クイズ学習アプリ")

# ワークシートの取得（キャッシュされるため高速）
try:
    worksheet = # 【追加】jsonモジュールをインポート（ファイルの先頭付近のimport群に追加してください）
import json

# （中略：ページ設定やSPREADSHEET_KEYの指定などはそのまま）

# 【修正】クラウドとローカルの両方に対応した接続関数
@st.cache_resource
def get_worksheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. クラウド（Streamlit Community Cloud）で動かす場合
    if "gcp_service_account" in st.secrets:
        # Streamlitの安全な金庫（Secrets）から鍵情報を読み込む
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        
    # 2. ローカルPCで動かす場合（今まで通り）
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_KEY).sheet1
except Exception as e:
    st.error(f"スプレッドシートの接続に失敗しました。\nエラー内容: {e}")
    st.stop()

# ==========================================
# 設定画面 (stage: setup)
# ==========================================
if st.session_state.stage == 'setup':
    st.subheader("出題設定")
    
    # 【高速化2】データの全件読み込みは設定画面を開いた時だけ行う
    with st.spinner("問題データを読み込んでいます..."):
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 列名の表記揺れを吸収
        if '子フォルダ名' in df.columns and '分野' not in df.columns:
            df = df.rename(columns={'子フォルダ名': '分野'})
        if '解答' in df.columns and '答え' not in df.columns:
            df = df.rename(columns={'解答': '答え'})
            
        # E列（間違えた回数）の処理
        if '間違えた回数' not in df.columns:
            df['間違えた回数'] = 0
        else:
            df['間違えた回数'] = pd.to_numeric(df['間違えた回数'], errors='coerce').fillna(0).astype(int)
            
        df['row_num'] = df.index + 2 

    # 出題範囲の選択
    categories = ["全範囲"] + list(df['分野'].dropna().unique())
    selected_category = st.selectbox("出題範囲を選択", categories)
    
    # 出題モードの選択
    modes = ["すべて（ランダム出題）", "一度でも間違えた問題（ランダム）", "間違いが多い順（苦手克服）"]
    selected_mode = st.radio("出題モードを選択", modes)
    
    if st.button("クイズスタート！", type="primary"):
        # フィルタリング処理
        target_df = df.copy()
        
        if selected_category != "全範囲":
            target_df = target_df[target_df['分野'] == selected_category]
            
        if selected_mode == "一度でも間違えた問題（ランダム）":
            target_df = target_df[target_df['間違えた回数'] > 0]
            target_df = target_df.sample(frac=1).reset_index(drop=True)
        elif selected_mode == "間違いが多い順（苦手克服）":
            target_df = target_df[target_df['間違えた回数'] > 0]
            target_df = target_df.sort_values(by='間違えた回数', ascending=False).reset_index(drop=True)
        else:
            target_df = target_df.sample(frac=1).reset_index(drop=True)
            
        if len(target_df) == 0:
            st.warning("条件に一致する問題がありません。")
        else:
            st.session_state.questions = target_df.to_dict('records')
            st.session_state.current_idx = 0
            st.session_state.answered = False
            st.session_state.pending_updates = {} # 更新リストをリセット
            st.session_state.stage = 'quiz'
            st.rerun()

# ==========================================
# クイズ画面 (stage: quiz)
# ==========================================
elif st.session_state.stage == 'quiz':
    total_q = len(st.session_state.questions)
    current_q_num = st.session_state.current_idx + 1
    
    st.progress(current_q_num / total_q)
    st.caption(f"問題 {current_q_num} / {total_q}")
    
    current_q = st.session_state.questions[st.session_state.current_idx]
    
    st.markdown(f"**【{current_q['分野']}】**")
    st.subheader(current_q['問題'])
    
    def check_answer(user_ans):
        correct_ans = str(current_q['答え']).strip()
        
        if user_ans == correct_ans:
            st.session_state.is_correct = True
        else:
            st.session_state.is_correct = False
            
            # 【高速化3】ここでは書き込まず、更新予定リストにメモだけ残す
            new_count = int(current_q['間違えた回数']) + 1
            row = int(current_q['row_num'])
            st.session_state.pending_updates[row] = new_count
            
            # 画面表示用に現在のデータだけ更新
            st.session_state.questions[st.session_state.current_idx]['間違えた回数'] = new_count
            
        st.session_state.answered = True

    # 解答前：ボタンを表示
    if not st.session_state.answered:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("正しい ⭕️", use_container_width=True):
                check_answer("正しい")
                st.rerun()
        with col2:
            if st.button("誤り ❌", use_container_width=True):
                check_answer("誤り")
                st.rerun()
                
    # 解答後：結果と解説を表示
    else:
        if st.session_state.is_correct:
            st.success("🎉 正解！")
        else:
            st.error("💦 不正解...")
            st.caption(f"※この問題を間違えた回数: {current_q['間違えた回数']}回")
            
        st.info(f"**【解説】**\n\n{current_q['解説']}")
        
        if current_q_num < total_q:
            if st.button("次の問題へ ➔", type="primary"):
                st.session_state.current_idx += 1
                st.session_state.answered = False
                st.rerun()
        else:
            if st.button("結果画面へ", type="primary"):
                st.session_state.stage = 'result'
                st.rerun()

# ==========================================
# 結果画面 (stage: result)
# ==========================================
elif st.session_state.stage == 'result':
    st.balloons()
    st.subheader("お疲れ様でした！全問終了です。")
    
    # 【追加】溜まっていた「間違えた回数」をここで一気に書き込む
    if st.session_state.pending_updates:
        with st.spinner("学習記録を保存しています..."):
            for row, count in st.session_state.pending_updates.items():
                worksheet.update_cell(row, 5, count) # E列を更新
        st.success("学習記録がスプレッドシートに保存されました！")
        st.session_state.pending_updates = {} # クリア
        
    if st.button("設定画面に戻る"):
        st.session_state.stage = 'setup'
        st.rerun()