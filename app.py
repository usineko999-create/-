import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- ページ設定 ---
st.set_page_config(page_title="正誤クイズアプリ", page_icon="📝", layout="centered")

# --- Googleスプレッドシート連携の設定 ---
CREDENTIALS_FILE = "secret_key.json"
DEFAULT_SPREADSHEET_KEY = "1NHaNYmOv9TOXdmaDmWbVmIa3RFsXkXhVUYkFgASHtTk"

# 6つの科目の設定
SUBJECTS = {
    "特許・実用新案": {"key": DEFAULT_SPREADSHEET_KEY, "sheet": "特許・実用新案"},
    "意匠": {"key": DEFAULT_SPREADSHEET_KEY, "sheet": "意匠"},
    "商標": {"key": DEFAULT_SPREADSHEET_KEY, "sheet": "商標"},
    "協定・条約": {"key": DEFAULT_SPREADSHEET_KEY, "sheet": "協定・条約"},
    "不正競争・著作権": {"key": DEFAULT_SPREADSHEET_KEY, "sheet": "不正競争・著作権"},
    "全問題": {"key": DEFAULT_SPREADSHEET_KEY, "sheet": "全問題"}
}

@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

# --- セッション状態の初期化 ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'select_subject' 
if 'df' not in st.session_state:
    st.session_state.df = None
if 'selected_subject_name' not in st.session_state:
    st.session_state.selected_subject_name = None
if 'questions' not in st.session_state:
    st.session_state.questions = []
if 'current_idx' not in st.session_state:
    st.session_state.current_idx = 0
if 'answered' not in st.session_state:
    st.session_state.answered = False
if 'is_correct' not in st.session_state:
    st.session_state.is_correct = False
if 'pending_updates' not in st.session_state:
    st.session_state.pending_updates = {}

# ==========================================
# 同期保存用の共通関数（ここが今回のキモです）
# ==========================================
def save_learning_records():
    if not st.session_state.pending_updates:
        return
        
    client = get_gspread_client()
    current_subj = st.session_state.selected_subject_name
    current_info = SUBJECTS[current_subj]
    
    # 1. 現在学習中のシートを更新
    current_ws = client.open_by_key(current_info["key"]).worksheet(current_info["sheet"])
    for q_text, data in st.session_state.pending_updates.items():
        current_ws.update_cell(data['row_num'], 5, data['count'])
        
    # 2. 他のシートへ同期（問題文をB列から検索して合致する行を更新）
    if current_subj != "全問題":
        # 科目別シートを使用中の場合 -> 「全問題」シートへ同期
        try:
            sync_ws = client.open_by_key(SUBJECTS["全問題"]["key"]).worksheet("全問題")
            q_col = sync_ws.col_values(2) # B列（問題文）を取得
            for q_text, data in st.session_state.pending_updates.items():
                if q_text in q_col:
                    sync_row = q_col.index(q_text) + 1 # 1行目から始まるため+1
                    sync_ws.update_cell(sync_row, 5, data['count'])
        except Exception as e:
            pass # シートが無いなどのエラー時はスキップ
    else:
        # 「全問題」シートを使用中の場合 -> 各科目別シートへ同期
        remaining = list(st.session_state.pending_updates.keys())
        for subj_name in SUBJECTS.keys():
            if subj_name == "全問題" or not remaining:
                continue
            try:
                sync_ws = client.open_by_key(SUBJECTS[subj_name]["key"]).worksheet(SUBJECTS[subj_name]["sheet"])
                q_col = sync_ws.col_values(2)
                found = []
                for q_text in remaining:
                    if q_text in q_col:
                        sync_row = q_col.index(q_text) + 1
                        sync_ws.update_cell(sync_row, 5, st.session_state.pending_updates[q_text]['count'])
                        found.append(q_text)
                # 見つかった問題は以降のシート探索から除外（高速化）
                for f in found:
                    remaining.remove(f)
            except Exception:
                continue
                
    # 保存完了後にリストをリセット
    st.session_state.pending_updates = {}

# --- メインUI ---
st.title("📝 正誤クイズ学習アプリ")

# ==========================================
# 科目選択画面 (stage: select_subject)
# ==========================================
if st.session_state.stage == 'select_subject':
    st.subheader("1. 科目の選択")
    
    selected_subject = st.radio(
        "学習する科目を選んでください", 
        list(SUBJECTS.keys()), 
        index=0
    )
    
    if st.button("次へ（データ読み込み）", type="primary"):
        try:
            with st.spinner(f"「{selected_subject}」のデータを読み込んでいます..."):
                client = get_gspread_client()
                subject_info = SUBJECTS[selected_subject]
                
                worksheet = client.open_by_key(subject_info["key"]).worksheet(subject_info["sheet"])
                data = worksheet.get_all_records()
                df = pd.DataFrame(data)
                
                if '子フォルダ名' in df.columns and '分野' not in df.columns:
                    df = df.rename(columns={'子フォルダ名': '分野'})
                if '解答' in df.columns and '答え' not in df.columns:
                    df = df.rename(columns={'解答': '答え'})
                    
                if '間違えた回数' not in df.columns:
                    df['間違えた回数'] = 0
                else:
                    df['間違えた回数'] = pd.to_numeric(df['間違えた回数'], errors='coerce').fillna(0).astype(int)
                    
                df['row_num'] = df.index + 2 
                
                # セッションに保存
                st.session_state.df = df
                st.session_state.selected_subject_name = selected_subject
                st.session_state.stage = 'setup'
                st.rerun()
                
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"スプレッドシート内に「{subject_info['sheet']}」という名前のシートが見つかりません。")
        except Exception as e:
            st.error(f"データの読み込みに失敗しました。\nエラー内容: {e}")

# ==========================================
# 設定画面 (stage: setup)
# ==========================================
elif st.session_state.stage == 'setup':
    st.subheader(f"2. 出題設定（{st.session_state.selected_subject_name}）")
    
    df = st.session_state.df
    
    categories = list(df['分野'].dropna().unique())
    selected_categories = st.multiselect(
        "出題範囲（単元）を選択してください", 
        options=categories,
        default=None,
        placeholder="クリックして文字検索・複数選択（未選択の場合は全範囲）"
    )
    
    modes = ["すべて（ランダム出題）", "一度でも間違えた問題（ランダム）", "間違いが多い順（苦手克服）"]
    selected_mode = st.radio("出題モードを選択", modes)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("クイズスタート！", type="primary"):
            target_df = df.copy()
            
            if len(selected_categories) > 0:
                target_df = target_df[target_df['分野'].isin(selected_categories)]
                
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
                st.session_state.pending_updates = {}
                st.session_state.stage = 'quiz'
                st.rerun()
                
    with col2:
        if st.button("🔙 科目選択に戻る"):
            st.session_state.stage = 'select_subject'
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
            
            new_count = int(current_q['間違えた回数']) + 1
            row = int(current_q['row_num'])
            
            # 【変更】行番号だけでなく、問題文をキーにして同期用に記憶しておく
            q_text = str(current_q['問題']).strip()
            st.session_state.pending_updates[q_text] = {'row_num': row, 'count': new_count}
            
            st.session_state.questions[st.session_state.current_idx]['間違えた回数'] = new_count
            
        st.session_state.answered = True

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

    st.markdown("---")
    if st.button("⏸️ 中断してここまでの記録を保存", use_container_width=True):
        if st.session_state.pending_updates:
            with st.spinner("シートを跨いで学習記録を同期保存しています..."):
                save_learning_records()
        st.session_state.stage = 'select_subject'
        st.rerun()

# ==========================================
# 結果画面 (stage: result)
# ==========================================
elif st.session_state.stage == 'result':
    st.balloons()
    st.subheader("お疲れ様でした！全問終了です。")
    
    if st.session_state.pending_updates:
        with st.spinner("シートを跨いで学習記録を同期保存しています..."):
            save_learning_records()
        st.success("すべてのシートに学習記録が保存・同期されました！")
        
    if st.button("科目選択に戻る"):
        st.session_state.stage = 'select_subject'
        st.rerun()
