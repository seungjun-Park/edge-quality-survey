import streamlit as st
import streamlit.components.v1 as components
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import random
import uuid
import datetime
from cryptography.fernet import Fernet

# --------------------------------------------------------------------------
# 1. 설정 및 UI 스타일링 (CSS 수정)
# --------------------------------------------------------------------------

st.set_page_config(layout="wide", page_title="EQ Survey")

try:
    SECRET_KEY = st.secrets["general"]["encryption_key"]
    cipher_suite = Fernet(SECRET_KEY)
except KeyError:
    st.error("암호화 키(encryption_key)가 secrets.toml에 설정되지 않았습니다.")
    st.stop()

# 뒤로가기 감지 스크립트 (이전 요청사항 유지)
js_code = """
<script>
    window.parent.addEventListener('popstate', function(event) {
        window.parent.location.reload();
    });
</script>
"""
components.html(js_code, height=0)

st.markdown("""
    <style>
    /* 1. 컬럼 내부 요소 중앙 정렬 (이미지와 버튼의 축을 맞춤) */
    div[data-testid="column"] {
        display: flex;
        flex-direction: column;
        align_items: center; /* 가로축 중앙 정렬 */
        justify_content: start;
    }
    
    /* 2. st.form 테두리 및 여백 제거 (버튼처럼 보이게 함) */
    div[data-testid="stForm"] {
        border: none;
        padding: 0;
        margin-top: 10px;
        background-color: transparent;
        width: 100%; /* 폼이 컬럼 너비를 꽉 채우게 */
    }

    /* 3. 버튼 스타일링 */
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        height: 3.5em;
        font-weight: 600;
        border: 1px solid #555;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        border-color: #E694FF;
        color: #E694FF;
    }
    
    .img-caption {
        text-align: center;
        font-size: 1.1em;
        margin-bottom: 8px;
        color: #aaa;
    }
    .stApp > header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

TOTAL_QUESTIONS = 37

# --------------------------------------------------------------------------
# 2. 데이터 및 연결 관리
# --------------------------------------------------------------------------

def encrypt_state(data_dict):
    """딕셔너리 -> JSON 문자열 -> 암호화 -> URL Safe 문자열"""
    json_str = json.dumps(data_dict)
    token = cipher_suite.encrypt(json_str.encode('utf-8'))
    return token.decode('utf-8')

def decrypt_state(token_str):
    """URL Safe 문자열 -> 복호화 -> JSON 파싱 -> 딕셔너리"""
    try:
        json_bytes = cipher_suite.decrypt(token_str.encode('utf-8'))
        return json.loads(json_bytes.decode('utf-8'))
    except Exception:
        # URL이 조작되었거나 복호화 실패 시 None 반환
        return None

@st.cache_resource
def get_google_sheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet_url = st.secrets["spreadsheets"]["url"]
        return client.open_by_url(sheet_url).sheet1
    except Exception as e:
        st.error(f"DB Error: {e}")
        return None

def get_image_url(file_id):
    if not file_id: return None
    # 썸네일 API (속도 최적화)
    return f"https://lh3.googleusercontent.com/d/{file_id}=w2000"

@st.cache_data
def load_metadata():
    try:
        with open('./pairs_list.json', 'r') as f:
            return json.load(f)
    except:
        return []

# --------------------------------------------------------------------------
# 3. 상태 관리 (암호화 적용)
# --------------------------------------------------------------------------

# URL에서 'q' 파라미터 읽기
encrypted_token = st.query_params.get("q")
state_data = None

if encrypted_token:
    state_data = decrypt_state(encrypted_token)

# 상태 데이터가 없거나 복호화 실패 시 초기화
if not state_data:
    new_uid = uuid.uuid4().hex[:6]
    initial_state = {
        "uid": new_uid,
        "step": -1,
        "ans": ""
    }
    # 초기 상태를 암호화하여 URL에 반영
    encrypted_init = encrypt_state(initial_state)
    st.query_params["q"] = encrypted_init
    
    # 변수 할당
    user_id = new_uid
    current_step = -1
    saved_answers_str = ""
else:
    # 복호화 성공 시 변수 할당
    user_id = state_data["uid"]
    current_step = int(state_data["step"])
    saved_answers_str = state_data["ans"]

# 랜덤 시드 고정
random.seed(user_id)
raw_data = load_metadata()

survey_plan = []    # 실제 보여줄 이미지 페어 정보 (UI용)
survey_indices = [] # 선택된 페어의 인덱스 번호 (저장용) - [0, 2, 1, 5, ...]

if raw_data:
    for idx in range(min(len(raw_data), TOTAL_QUESTIONS)):
        pairs = raw_data[idx]
        if pairs:
            # [수정] choice 대신 randrange를 사용하여 인덱스를 직접 추출
            r_idx = random.randrange(len(pairs))
            
            # 인덱스 저장
            survey_indices.append(r_idx)
            # 해당 인덱스의 페어 저장
            survey_plan.append(pairs[r_idx])
        else:
            survey_indices.append(-1) # 데이터 없음
            survey_plan.append(None)
else:
    st.error("데이터 파일이 없습니다.")
    st.stop()

# --------------------------------------------------------------------------
# 4. 로직 및 렌더링
# --------------------------------------------------------------------------

def start_survey():
    """소개 페이지 -> 설문 1번 문제로 이동"""
    new_state = {
        "uid": user_id,
        "step": 0, # 0번 문제로 설정
        "ans": ""  # 답변 초기화
    }
    token = encrypt_state(new_state)
    st.query_params["q"] = token
    st.rerun()

def next_step(choice):
    """
    다음 상태를 암호화하여 URL 업데이트
    """
    new_state = {
        "uid": user_id,
        "step": current_step + 1,
        "ans": saved_answers_str + choice
    }
    
    # 전체 상태를 묶어서 암호화
    token = encrypt_state(new_state)
    
    # URL 쿼리 파라미터를 'q' 하나로 통일
    st.query_params["q"] = token
    st.rerun()

def submit():
    sheet = get_google_sheet()
    if sheet:
        with st.spinner("Saving..."):
            try:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 답변 리스트 생성
                final_answers = list(saved_answers_str)
                if len(final_answers) < TOTAL_QUESTIONS:
                    final_answers += [""] * (TOTAL_QUESTIONS - len(final_answers))
                
                new_answers = []
                for answer, idx in zip(final_answers, survey_indices):
                    new_answers.append(f'{answer}_{idx}')

                # [수정] 저장할 데이터 구성: 
                # 타임스탬프 + UID + 답변리스트(37개) + 랜덤인덱스리스트(37개)
                row_data = [timestamp, user_id] + new_answers
                
                sheet.append_row(row_data)
                
                st.session_state["submitted"] = True
                st.success("Done!")
                st.balloons()
            except Exception as e:
                st.error(f"Save Failed: {e}")
# --- UI 렌더링 ---


st.markdown(f"<h3 style='text-align: center;'>Sample {current_step + 1} / {TOTAL_QUESTIONS}</h3>", unsafe_allow_html=True)

st.progress(min(current_step / TOTAL_QUESTIONS, 1.0))

if current_step == -1:
    st.markdown("<br><br>", unsafe_allow_html=True) # 상단 여백
    
    # 중앙 정렬을 위한 컬럼 분할
    _, col_main, _ = st.columns([1, 2, 1])
    
    with col_main:
        st.markdown("""
        <div class="intro-box">
            <h1 style="text-align: center; color: #E694FF;">엣지 품질 평가 설문</h1>
            <hr style="border-color: #555;">
            <p style="font-size: 1.1em; line-height: 1.6;">
                안녕하세요.<br>
                본 설문은 왜곡된 엣지들이 얼마나 기준 엣지와 비슷한지 평가하기 위해 진행됩니다.<br>
                총 <strong>37개의 문항</strong>으로 구성되어 있으며, 
                중앙의 기준 이미지(GT)와 비교하여 더 비슷하다고 생각되는 엣지를 선택해 주시면 됩니다.
            </p>
            <ul style="line-height: 1.6; margin-bottom: 20px;">
                <li>⏱ 소요 시간: 약 5분 내외</li>
                <li>💾 데이터 처리: 응답 결과는 익명으로 연구 목적으로만 활용됩니다.</li>
                <li>⚠️ 주의: 브라우저를 닫으면 진행 상황이 초기화될 수 있습니다.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # 시작 버튼
        if st.button("설문 시작하기 (Start)", type="primary"):
            start_survey()

if current_step < TOTAL_QUESTIONS:
    pair_ids = survey_plan[current_step]
    
    if not pair_ids:
        next_step("N")
        st.stop()

    gt_id, dist_a_id, dist_b_id = pair_ids
    
    url_gt = get_image_url(gt_id)
    url_a = get_image_url(dist_a_id)
    url_b = get_image_url(dist_b_id)

    c1, c2, c3 = st.columns([1, 1, 1], gap="medium")

    with c1:
        st.markdown("<div class='img-caption'>Option A</div>", unsafe_allow_html=True)
        st.image(url_a, use_container_width=True)
        with st.form(key=f"form_a_{current_step}", clear_on_submit=True):
            if st.form_submit_button("Select A", use_container_width=True):
                next_step("A")

    with c2:
        st.markdown("<div class='img-caption' style='color:#E694FF;'>Ground Truth</div>", unsafe_allow_html=True)
        st.image(url_gt, use_container_width=True)

    with c3:
        st.markdown("<div class='img-caption'>Option B</div>", unsafe_allow_html=True)
        st.image(url_b, use_container_width=True)
        with st.form(key=f"form_b_{current_step}", clear_on_submit=True):
            if st.form_submit_button("Select B", use_container_width=True):
                next_step("B")

else:
    if st.session_state.get("submitted"):
        st.info("설문이 완료되었습니다. 창을 닫으셔도 됩니다.")
    else:
        st.markdown("### 설문 종료")
        st.write("모든 문항에 응답하셨습니다.")
        with st.form(key="submit_form"):
            if st.form_submit_button("결과 제출 (Submit)", type="primary", use_container_width=True):
                submit()