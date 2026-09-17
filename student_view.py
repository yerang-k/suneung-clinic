import streamlit as st
import json
import re
import requests
import pandas as pd
from data_manager import (
    verify_student, get_exams, get_exam_pdf_base64,
    get_admin_config, save_submission
)
from pdf_viewer import render_pdf_viewer, render_csat_text_view
from prescription_engine import get_prescription_problems, evaluate_student_defense
from google.genai import types

# 6대 사고 오류 전 항목에 대한 기본 추천 기출 DB
RECOMMENDATION_DB = {
    "선지 임의 변형": [
        {"year": "2025학년도 9월", "q_num": 21, "mission": "선지의 서술어가 지문의 인과와 정확히 일치하는지 단어 단위로 끊어 검증할 것"},
        {"year": "2024학년도 수능", "q_num": 34, "mission": "내 상식으로 문맥을 보완하지 말고, 선지가 제시한 주어-목적어 관계만 확인할 것"}
    ],
    "선지 후반부 검증 생략": [
        {"year": "2024학년도 6월", "q_num": 15, "mission": "복합 선지의 앞부분(A)에 밑줄 긋고 참/거짓 판별 후, 뒷부분(B)을 독립적으로 검증할 것"},
        {"year": "2023학년도 수능", "q_num": 17, "mission": "전반부 수식어가 맞다고 해서 후반부 핵심 술어를 건너뛰지 말 것"}
    ],
    "기억 부재의 부재화": [
        {"year": "2024학년도 9월", "q_num": 8, "mission": "기억나지 않는다고 '틀린 선지'로 단정하지 말고, 반드시 지문 해당 단락으로 돌아가 눈으로 확인할 것"},
        {"year": "2025학년도 6월", "q_num": 12, "mission": "내 기억의 확신도와 실제 지문 텍스트는 다를 수 있음을 인정하고 근거 문장을 재탐색할 것"}
    ],
    "적용 조건 혼동": [
        {"year": "2025학년도 수능", "q_num": 10, "mission": "원리 지문에서 제시된 '전제 조건'과 '<보기>의 구체적 상황'을 1:1로 대응시킬 것"},
        {"year": "2024학년도 9월", "q_num": 14, "mission": "예외 조항과 기본 규칙의 적용 범위를 지문 기호로 명확히 분리할 것"}
    ],
    "관계어·논리 왜곡": [
        {"year": "2024학년도 수능", "q_num": 10, "mission": "지문의 'A일수록 B'라는 비례 관계를 'A이면 C'라는 인과 관계로 왜곡하지 말 것"},
        {"year": "2023학년도 9월", "q_num": 16, "mission": "필요조건과 충분조건, 주체와 대상의 전도 현상을 선지에서 역추적할 것"}
    ],
    "과잉 인과 생성": [
        {"year": "2025학년도 6월", "q_num": 31, "mission": "문학에서 시간적 인접성을 필연적 인과로 단정하지 말고, 선지의 연결 어미를 따져볼 것"},
        {"year": "2024학년도 6월", "q_num": 24, "mission": "작품 속 인물의 심리와 행동 사이에 지문에 없는 독자적 개연성을 부여하지 말 것"}
    ]
}

SAMPLE_QUESTIONS_TEXT = {
    27: {
        "q_num": 27,
        "passage": "앞줄의 아름드리나무 그늘 속에 숨어 있는 늦된 나무는 햇빛을 받지 못해 꽃을 늦게 피운다. (중략) 나도 늦된 나무처럼 천천히, 그러나 단단하게 뿌리를 내리며 나만의 꽃을 준비하고 있다.",
        "question": "윗글에 대한 이해로 적절하지 않은 것은?",
        "options": {
            1: "그늘은 늦된 나무가 다른 나무들로부터 자신의 몸을 감추기 위해 선택한 공간이다.",
            2: "늦된 나무의 개화는 앞줄 나무들과의 생존 경쟁에서 비롯된 결과이다.",
            3: "화자는 늦된 나무의 생태를 관찰하며 자신의 삶에 대한 성찰을 이끌어내고 있다.",
            4: "아름드리나무는 늦된 나무와 대비되는 존재로, 외부적 환경의 한계를 상징한다.",
            5: "꽃을 늦게 피우는 현상을 통해 지연의 가치를 긍정적으로 인식하고 있다."
        },
        "correct": 1
    },
    14: {
        "q_num": 14,
        "passage": "데이터 전송 과정에서 잡음으로 인한 비트 반전을 검출하기 위해 패리티 비트를 추가한다. 홀수 패리티 방식은 전체 비트 중 1의 개수가 홀수가 되도록 검사 비트를 할당하며, 전송 중 1비트의 오류가 발생하면 즉시 검출할 수 있으나 2비트 동시 반전 오류는 정상 데이터로 오인하는 한계를 지닌다.",
        "question": "윗글을 바탕으로 추론한 내용으로 가장 적절한 것은?",
        "options": {
            1: "홀수 패리티 방식은 2비트 오류가 발생했을 때 수신 측에서 재전송을 요청한다.",
            2: "패리티 비트는 데이터 비트의 위치 정보까지 파악하여 자체 교정을 수행한다.",
            3: "홀수 패리티를 적용한 8비트 데이터 프레임의 '1'의 총 개수는 항상 홀수여야 한다.",
            4: "잡음의 세기가 커질수록 패리티 비트의 검출 한계는 짝수 비트로 이동한다.",
            5: "비트 반전이 3번 일어난 경우 홀수 패리티 방식으로는 오류를 검출할 수 없다."
        },
        "correct": 3
    }
}

def build_gemini_contents(chat_history):
    contents = []
    for idx, msg in enumerate(chat_history):
        role = "model" if msg["role"] == "assistant" else "user"
        if idx == 0 and role == "model":
            contents.append({
                "role": "user",
                "parts": [{"text": "시험 당시 제 사고 과정을 복원하고 싶습니다. 인터뷰를 시작해 주세요."}]
            })
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })
    return contents

def safe_parse_json(text: str):
    cleaned = re.sub(r"^```(?:json)?\s*|```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("JSON 응답을 해석할 수 없습니다.")

# ==========================================
# 1. 학생 로그인 뷰
# ==========================================
def render_student_login():
    st.markdown("""
    <div style="text-align: center; margin-top: 2rem; margin-bottom: 2rem;">
        <h1 style="color: #0f172a;">🧠 수능 국어 사고 복원 클리닉</h1>
        <p style="color: #64748b; font-size: 1.1rem;">
            오답을 단순히 외우지 않고, <b>시험장 당시 나의 왜곡된 사고 경로</b>를 복원하여 평가원의 함정을 깨뜨립니다.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.container(border=True):
            st.subheader("🎓 학생 로그인")
            st.caption("선생님이 등록해주신 학번, 이름, 비밀번호로 로그인하세요.")
            sid = st.text_input("학번 (예: 30101)", placeholder="30101")
            name = st.text_input("이름", placeholder="김수험")
            pw = st.text_input("비밀번호", type="password", placeholder="초기 비밀번호 입력")
            
            if st.button("로그인 및 진단 시작", type="primary", use_container_width=True):
                if sid.strip() and name.strip() and pw.strip():
                    ok, res = verify_student(sid, name, pw)
                    if ok:
                        st.session_state.auth_student = res
                        st.session_state.student_stage = "OMR"
                        st.session_state.chat_history = []
                        st.session_state.interview_step = "CHAT"
                        st.session_state.vulnerable_queue = []
                        st.session_state.queue_index = 0
                        st.session_state.diagnosed_items = []
                        if "omr_df" in st.session_state:
                            del st.session_state["omr_df"]
                        st.rerun()
                    else:
                        st.error(res)
                else:
                    st.warning("학번, 이름, 비밀번호를 모두 입력해 주세요.")
            
            st.divider()
            st.caption("💡 테스트용 계정: 학번 `30101`, 이름 `김수험`, 비밀번호 `1234`")
            
            st.write("")
            if st.button("🔒 교사용 관리자 모드로 전환", use_container_width=True):
                st.session_state.app_mode = "ADMIN"
                st.rerun()

# ==========================================
# 2. OMR 일괄 상태 입력 뷰
# ==========================================
def render_omr_stage():
    student = st.session_state.auth_student
    st.markdown(f"### 👋 반가워요, **{student['name']}** ({student['student_id']}) 학생!")
    st.markdown("""
    오프라인에서 시간 맞춰 푼 시험지를 책상 위에 펼쳐놓으세요.  
    **모든 문제를 다 대화할 필요는 없습니다.** `확신`하고 맞힌 문제는 자동으로 건너뛰고,  
    **`확신 없는 정답`, `오답`, `시간부족/찍음`**으로 체크된 문제들만 AI와 1:1로 사고 복원을 진행합니다.
    """)

    exams = get_exams()
    exam_options = list(exams.keys())

    col_meta1, col_meta2, col_meta3 = st.columns([2, 1, 1.2])
    with col_meta1:
        selected_exam_id = st.selectbox(
            "📝 진단할 시험지 선택",
            options=exam_options,
            format_func=lambda x: f"{exams[x]['title']} ({exams[x]['total_questions']}문항)"
        )
    with col_meta2:
        total_time = st.number_input("전체 풀이 소요 시간 (분)", min_value=10, max_value=120, value=78)
    with col_meta3:
        time_pressure = st.selectbox("시험 당시 시간 압박감", ["충분했음", "쫓기며 풀었음", "시간 부족으로 찍음/못풂"])

    cur_exam = exams[selected_exam_id]
    total_q = cur_exam["total_questions"]

    st.divider()
    st.subheader(f"📋 {cur_exam['title']} - 전체 문항 풀이 상태 기록")
    st.caption("기본값은 '확신'입니다. 틀렸거나 헷갈렸거나 찍었던 문제만 상태를 변경해 주시면 됩니다.")

    # 시험지가 변경되었거나 OMR 데이터가 없는 경우 안전하게 초기화
    if "current_exam_id" not in st.session_state or st.session_state.current_exam_id != selected_exam_id or "omr_df" not in st.session_state:
        st.session_state.current_exam_id = selected_exam_id
        init_rows = [
            {
                "문항": i,
                "🔴 오답": False,
                "🟡 확신 없음": False,
                "⏱️ 찍음": False,
                "고른 선지": 1
            }
            for i in range(1, total_q + 1)
        ]
        st.session_state.omr_df = pd.DataFrame(init_rows)
        st.session_state.omr_editor_nonce = st.session_state.get("omr_editor_nonce", 0) + 1

    # 1. 빠른 번호 일괄 지정 폼 (체크박스 자동 토글)
    with st.expander("⚡ 번호 직접 입력으로 빠르게 체크하기 (선택사항)", expanded=False):
        st.caption("문항 번호를 적고 [일괄 적용]을 누르면 아래 체크박스가 자동으로 켜집니다.")
        with st.form("quick_omr_form"):
            col_q1, col_q2, col_q3 = st.columns(3)
            with col_q1:
                wrong_input = st.text_input("🔴 오답 번호들", placeholder="예: 14, 27, 34")
            with col_q2:
                unsure_input = st.text_input("🟡 확신 없는 정답 번호들", placeholder="예: 8, 21")
            with col_q3:
                time_input = st.text_input("⏱️ 찍음 / 시간부족 번호들", placeholder="예: 44, 45")

            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                submit_quick = st.form_submit_button("⚡ 위 문항들 체크박스 자동 적용", type="primary", use_container_width=True)
            with col_btn2:
                reset_all = st.form_submit_button("🔄 전체 체크박스 해제 (초기화)", use_container_width=True)

            if submit_quick:
                def parse_q_numbers(text: str):
                    if not text:
                        return []
                    parts = re.split(r"[,/\\s]+", text.strip())
                    return [int(p) for p in parts if p.isdigit()]

                w_list = parse_q_numbers(wrong_input)
                u_list = parse_q_numbers(unsure_input)
                t_list = parse_q_numbers(time_input)

                applied_count = 0
                for q in w_list:
                    if 1 <= q <= total_q:
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🔴 오답"] = True
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🟡 확신 없음"] = False
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "⏱️ 찍음"] = False
                        applied_count += 1
                for q in u_list:
                    if 1 <= q <= total_q:
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🔴 오답"] = False
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🟡 확신 없음"] = True
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "⏱️ 찍음"] = False
                        applied_count += 1
                for q in t_list:
                    if 1 <= q <= total_q:
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🔴 오답"] = False
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🟡 확신 없음"] = False
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "⏱️ 찍음"] = True
                        applied_count += 1

                st.session_state.omr_editor_nonce = st.session_state.get("omr_editor_nonce", 0) + 1
                st.success(f"총 {applied_count}개 문항의 체크박스가 자동 설정되었습니다.")
                st.rerun()

            if reset_all:
                init_rows = [
                    {
                        "문항": i,
                        "🔴 오답": False,
                        "🟡 확신 없음": False,
                        "⏱️ 찍음": False,
                        "고른 선지": 1
                    }
                    for i in range(1, total_q + 1)
                ]
                st.session_state.omr_df = pd.DataFrame(init_rows)
                st.session_state.omr_editor_nonce = st.session_state.get("omr_editor_nonce", 0) + 1
                st.info("전체 문항의 체크가 해제되었습니다. (모두 확신 상태)")
                st.rerun()

    # 2. 체크박스 OMR 마킹 시트
    st.markdown("##### ☑️ OMR 체크박스 마킹 시트")
    st.caption("드롭다운 없이 클릭 한 번으로 선택할 수 있습니다. 틀렸거나 헷갈린 문항의 체크박스(☑️)를 툭툭 눌러주세요. (아무것도 체크하지 않은 문제는 자동으로 '🟢 확신'으로 스킵됩니다)")

    editor_key = f"omr_editor_{st.session_state.current_exam_id}_{st.session_state.get('omr_editor_nonce', 0)}"

    edited_df = st.data_editor(
        st.session_state.omr_df,
        key=editor_key,
        column_config={
            "문항": st.column_config.NumberColumn("문항 번호", disabled=True, width="small"),
            "🔴 오답": st.column_config.CheckboxColumn("🔴 오답", default=False, width="small"),
            "🟡 확신 없음": st.column_config.CheckboxColumn("🟡 확신 없음", default=False, width="small"),
            "⏱️ 찍음": st.column_config.CheckboxColumn("⏱️ 찍음/시간부족", default=False, width="small"),
            "고른 선지": st.column_config.SelectboxColumn("내가 고른 선지", options=[1, 2, 3, 4, 5], required=True, width="small"),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        height=380
    )
    st.session_state.omr_df = edited_df

    # 상태 판정 함수
    def resolve_status(row):
        if row["🔴 오답"]:
            return "🔴 오답"
        elif row["⏱️ 찍음"]:
            return "⏱️ 시간부족/찍음"
        elif row["🟡 확신 없음"]:
            return "🟡 확신 없는 정답"
        return "🟢 확신 (건너뜀)"

    # 취약 문항 필터링 및 통계
    vulnerable_rows = []
    wrong_count = 0
    unsure_count = 0
    time_count = 0

    for _, row in edited_df.iterrows():
        stt = resolve_status(row)
        if stt != "🟢 확신 (건너뜀)":
            q_num = int(row["문항"])
            pick = int(row["고른 선지"])
            vulnerable_rows.append({
                "q_num": q_num,
                "status": stt,
                "my_pick": pick
            })
            if stt == "🔴 오답":
                wrong_count += 1
            elif stt == "🟡 확신 없는 정답":
                unsure_count += 1
            elif stt == "⏱️ 시간부족/찍음":
                time_count += 1

    vuln_count = len(vulnerable_rows)

    st.markdown(f"""
    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; padding: 12px 16px; border-radius: 8px; margin: 14px 0;">
        <span style="font-size: 1.05rem; font-weight: bold; color: #0f172a;">
            🔍 복원 대상 취약 문항: 총 {vuln_count}개
        </span>
        <div style="margin-top: 6px; font-size: 0.95rem; color: #475569;">
            🔴 오답: <b>{wrong_count}개</b> &nbsp;|&nbsp; 
            🟡 확신 없음: <b>{unsure_count}개</b> &nbsp;|&nbsp; 
            ⏱️ 찍음: <b>{time_count}개</b> &nbsp;|&nbsp; 
            🟢 확신: <b>{total_q - vuln_count}개</b> (자동 스킵)
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🚀 취약 문항 1:1 사고 복원 인터뷰 시작하기", type="primary", use_container_width=True):
        if vuln_count == 0:
            st.balloons()
            st.success("🎉 모든 문항에 확신을 가지고 풀었습니다! 복원할 취약 문항이 없습니다.")
        else:
            st.session_state.exam_info = cur_exam
            st.session_state.total_time = total_time
            st.session_state.time_pressure = time_pressure
            st.session_state.vulnerable_queue = vulnerable_rows
            st.session_state.queue_index = 0
            st.session_state.diagnosed_items = []
            st.session_state.student_stage = "INTERVIEW"
            
            # 첫 번째 문항 인터뷰 세팅
            first_q = vulnerable_rows[0]
            st.session_state.interview_step = "CHAT"
            st.session_state.chat_history = [{
                "role": "assistant",
                "content": f"안녕, {student['name']}! {cur_exam['title']} **{first_q['q_num']}번** 문항을 [{first_q['status']}] 상태로 표시하고 **{first_q['my_pick']}번** 선지를 골랐네.\n\n정답을 맞히는 건 나중 문제니까, 시험장에서 이 문제를 풀 때 **왜 {first_q['my_pick']}번에 끌렸는지, 지문이나 선지의 어떤 표현 때문에 고민했는지** 당시 생각부터 편하게 말해줄래?"
            }]
            st.session_state.draft_summary = ""
            st.session_state.current_analysis = None
            st.rerun()

# ==========================================
# 3. 순차 사고 복원 인터뷰 뷰 (Queue Runner)
# ==========================================
def render_interview_stage(client):
    queue = st.session_state.vulnerable_queue
    q_idx = st.session_state.queue_index
    current_q_meta = queue[q_idx]
    q_num = current_q_meta["q_num"]
    my_pick = current_q_meta["my_pick"]
    status_label = current_q_meta["status"]
    exam_info = st.session_state.exam_info
    student = st.session_state.auth_student

    # 상단 진행 인디케이터
    total_in_queue = len(queue)
    st.progress((q_idx + 1) / total_in_queue)
    col_stat1, col_stat2 = st.columns([3, 1])
    with col_stat1:
        st.markdown(f"#### 🎯 취약 문항 복원 중: **{q_idx + 1} / {total_in_queue} 번째** (문항 번호: **{q_num}번**)")
        st.caption(f"학생: **{student['name']}** | 상태: `{status_label}` | 내가 고른 선지: **{my_pick}번**")
    with col_stat2:
        if st.button("⏹️ 진단 중단 및 OMR로 돌아가기"):
            st.session_state.student_stage = "OMR"
            st.rerun()

    col_paper, col_chat = st.columns([1.1, 1.1], gap="large")

    # [좌측 열] 시험지 원문 뷰어 (PDF 또는 평가원 텍스트 뷰어)
    with col_paper:
        pdf_b64 = get_exam_pdf_base64(exam_info["exam_id"])
        
        tab_pdf, tab_text = st.tabs(["📄 시험지 원문 (PDF)", "📝 문항 텍스트 집중 보기"])
        
        with tab_pdf:
            if pdf_b64:
                st.caption("💡 실제 시험지 PDF 원문입니다. 확대/축소 및 페이지를 자유롭게 넘겨보며 당시 시야를 복기하세요.")
                render_pdf_viewer(pdf_b64, initial_page=1, height=720)
            else:
                st.info("선생님이 아직 이 시험지의 원문 PDF를 업로드하지 않았습니다. [문항 텍스트 집중 보기] 탭을 확인해 주세요.")
                if q_num in SAMPLE_QUESTIONS_TEXT:
                    render_csat_text_view(SAMPLE_QUESTIONS_TEXT[q_num], my_pick, status_label)
                else:
                    st.write(f"**{q_num}번 문항 원문을 책상 위 종이 시험지에서 확인해 주세요.**")

        with tab_text:
            if q_num in SAMPLE_QUESTIONS_TEXT:
                render_csat_text_view(SAMPLE_QUESTIONS_TEXT[q_num], my_pick, status_label)
            else:
                st.write(f"현재 등록된 텍스트 지문이 없습니다. 오프라인 시험지의 **{q_num}번 문항**을 함께 보면서 진행해주세요.")

    # [우측 열] Gemini 소크라테스 인터뷰
    with col_chat:
        if st.session_state.interview_step == "CHAT":
            st.subheader("💬 AI 사고 복원 인터뷰")
            
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

            if user_input := st.chat_input("당시 들었던 생각, 헷갈렸던 문장이나 단어를 솔직히 적어주세요..."):
                st.session_state.chat_history.append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.write(user_input)

                # 문제 텍스트 보강
                q_context = ""
                if q_num in SAMPLE_QUESTIONS_TEXT:
                    item = SAMPLE_QUESTIONS_TEXT[q_num]
                    q_context = f"\n[문항 세부 정보]\n- 지문: {item['passage']}\n- 발문: {item['question']}\n- 학생 선택 선지: {my_pick}번 ({item['options'].get(my_pick, '')})\n- 실제 정답 선지: {item['correct']}번 ({item['options'].get(item['correct'], '')})"

                system_prompt = f"""
                당신은 수능 국어 '사고 복원 전문 인터뷰어'입니다. 학생이 시험장에서 범한 인지 오류와 독해 습관을 스스로 깨닫도록 돕습니다.
                
                [현재 분석 문항]
                - 시험: {exam_info['title']}
                - 문항 번호: {q_num}번
                - 학생 풀이 상태: {status_label}
                - 학생이 고른 선지: {my_pick}번
                {q_context}
                
                [인터뷰어 핵심 행동 지침]
                1. 절대 선지의 옳고 그름(정오)을 먼저 알려주거나 직접 해설 강의를 하지 마십시오.
                2. 학생이 답변한 내용을 바탕으로, '지문의 어떤 문장을 어떻게 오독했는지', '선지의 특정 어휘를 임의로 왜곡했는지', '기억이 안 나서 지레짐작했는지'를 날카롭게 파고드는 질문을 '딱 1개'만 던지십시오.
                3. 친절하지만 수능적 엄밀함을 유지하는 어조를 사용하십시오.
                """

                gemini_contents = build_gemini_contents(st.session_state.chat_history)

                with st.spinner("생각의 경로를 분석 중입니다..."):
                    try:
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=gemini_contents,
                            config=types.GenerateContentConfig(
                                system_instruction=system_prompt,
                                temperature=0.3
                            )
                        )
                        st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                    except Exception as e:
                        st.error(f"응답 생성 오류: {e}")
                st.rerun()

            if len(st.session_state.chat_history) >= 3:
                st.divider()
                if st.button("📝 대화 종료 및 내 사고 요약안 작성하기", use_container_width=True, type="primary"):
                    with st.spinner("당시 사고 경로를 1인칭으로 요약 중입니다..."):
                        summary_prompt = "지금까지의 대화 전문을 바탕으로, 학생이 시험장에서 해당 선지를 고르게 된 '인지 왜곡 및 사고 경로'를 1~2문장으로 요약해 주십시오. 1인칭('나는 ~라고 생각하여 ~했다') 시점으로 작성하세요."
                        contents_for_summary = build_gemini_contents(st.session_state.chat_history)
                        contents_for_summary.append({"role": "user", "parts": [{"text": summary_prompt}]})
                        try:
                            summary_res = client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=contents_for_summary
                            )
                            st.session_state.draft_summary = summary_res.text
                            st.session_state.interview_step = "REVIEW"
                        except Exception as e:
                            st.error(f"요약 중 오류: {e}")
                    st.rerun()

        elif st.session_state.interview_step == "REVIEW":
            st.subheader("🔍 사고 복원 내용 확인 및 수정")
            st.info("💡 AI가 대화를 바탕으로 복원한 사고 과정입니다. 실제 내 생각과 다른 부분이 있다면 직접 수정해 주세요.")
            edited_thought = st.text_area("시험 당시 나의 사고 흐름 (수정 가능)", value=st.session_state.draft_summary, height=130)

            if st.button("✅ 내 사고로 확정하고 정밀 분석 완료하기", type="primary", use_container_width=True):
                with st.spinner("사고 패턴 태깅 및 평가원 함정 구조 분석 중..."):
                    json_prompt = f"""
                    문항: {exam_info['title']} {q_num}번
                    학생의 확정된 사고 과정: "{edited_thought}"
                    학생 선택: {my_pick}번 선지
                    
                    이 사고 과정을 바탕으로 다음 3가지 항목을 JSON 형식으로 출력하십시오.
                    {{
                        "error_tag": "선지 임의 변형, 선지 후반부 검증 생략, 기억 부재의 부재화, 적용 조건 혼동, 관계어·논리 왜곡, 과잉 인과 생성 중 가장 적합한 1개",
                        "evaluator_trap": "학생의 인지 왜곡을 역이용하여 평가원이 이 오답 선지를 설계한 함정의 논리 구조 (1문장)",
                        "action_rule": "학생이 다음 시험장에서 이 오류를 반복하지 않기 위해 되뇌어야 할 단 한 문장의 구체적 행동 원칙"
                    }}
                    """
                    try:
                        json_res = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=json_prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                temperature=0.1
                            )
                        )
                        analysis_data = safe_parse_json(json_res.text)
                        analysis_data["q_num"] = q_num
                        analysis_data["status"] = status_label
                        analysis_data["my_pick"] = my_pick
                        analysis_data["student_thought"] = edited_thought

                        st.session_state.current_analysis = analysis_data
                        st.session_state.diagnosed_items.append(analysis_data)
                        st.session_state.interview_step = "ITEM_COMPLETED"
                    except Exception as e:
                        st.error(f"분석 중 오류: {e}")
                st.rerun()

        elif st.session_state.interview_step == "ITEM_COMPLETED":
            res = st.session_state.current_analysis
            st.success(f"🎉 **{q_num}번 문항** 사고 복원 완료!")
            
            st.markdown(f"**🧠 복원된 나의 사고**\n> *\"{res['student_thought']}\"*")
            st.markdown(f"**🚨 사고 오류 태그:** `{res['error_tag']}`")
            st.markdown(f"**😈 평가원의 함정 설계:** {res['evaluator_trap']}")
            st.markdown(f"**💡 나만의 행동 원칙:** *{res['action_rule']}*")

            st.divider()
            # 큐의 다음 문항으로 이동할지 여부 결정
            if q_idx + 1 < len(queue):
                next_q = queue[q_idx + 1]
                if st.button(f"➡️ 다음 취약 문항 복원하기 ({q_idx + 2} / {len(queue)} - {next_q['q_num']}번)", type="primary", use_container_width=True):
                    st.session_state.queue_index += 1
                    st.session_state.interview_step = "CHAT"
                    st.session_state.current_analysis = None
                    st.session_state.chat_history = [{
                        "role": "assistant",
                        "content": f"좋아! 다음은 **{next_q['q_num']}번** 문항이야. [{next_q['status']}] 상태로 **{next_q['my_pick']}번**을 골랐네. 이 문항에서는 어떤 점이 헷갈렸는지 편하게 말해줘!"
                    }]
                    st.rerun()
            else:
                if st.button("🏁 모든 취약 문항 복원 완료! 종합 진단 보고서 및 맞춤 처방 보기", type="primary", use_container_width=True):
                    st.session_state.student_stage = "REPORT"
                    st.rerun()

# ==========================================
# 4. 종합 진단 보고서 & AI 기출 탐색 및 인앱 즉석 방어 훈련
# ==========================================
def render_report_stage(client):
    student = st.session_state.auth_student
    exam_info = st.session_state.exam_info
    diagnosed = st.session_state.diagnosed_items
    cfg = get_admin_config()
    master_drive_url = cfg.get("google_drive_folder_url", "")

    if "active_training_problem" not in st.session_state:
        st.session_state.active_training_problem = None
    if "training_feedback" not in st.session_state:
        st.session_state.training_feedback = None

    st.markdown("""
    <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 1.5rem; border-radius: 10px; margin-bottom: 1.5rem;">
        <h2 style="color: #166534; margin: 0;">🎉 종합 사고 복원 완료 리포트 & AI 기출 맞춤 처방</h2>
        <p style="color: #15803d; margin-top: 6px;">
            모든 취약 문항의 사고 경로 복원을 마쳤습니다. AI가 전체 모의고사 PDF에서 학생의 약점에 맞는 문항을 자동으로 찾아내었습니다.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 상단 구글 드라이브 마스터 폴더 바로가기
    if master_drive_url and master_drive_url.startswith("http"):
        st.markdown(f"""
        <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; padding: 12px 18px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #1e40af; font-weight: 500;">
                📂 선생님의 구글 드라이브에 최근 수능 및 평가원 모의고사 원문 PDF 전체가 보관되어 있습니다.
            </span>
            <a href="{master_drive_url}" target="_blank" style="text-decoration: none;">
                <button style="background-color: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer;">
                    구글 드라이브 전체 기출 폴더 열기 ↗
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)

    col_sum1, col_sum2, col_sum3 = st.columns(3)
    with col_sum1:
        st.metric("학생 이름", f"{student['name']} ({student['student_id']})")
    with col_sum2:
        st.metric("진단 시험", exam_info['title'])
    with col_sum3:
        st.metric("분석된 취약 문항", f"{len(diagnosed)}개")

    st.divider()

    # 오류 태그 집계
    tag_counts = {}
    for item in diagnosed:
        t = item["error_tag"]
        tag_counts[t] = tag_counts.get(t, 0) + 1

    st.subheader("📊 나의 수능 국어 인지 오류 패턴 분포")
    col_chart, col_tags = st.columns([1, 1.2])
    with col_chart:
        df_tags = pd.DataFrame(list(tag_counts.items()), columns=["오류 유형", "빈도"])
        st.bar_chart(df_tags.set_index("오류 유형"))
    with col_tags:
        st.write("시험장에서 가장 빈번하게 발생한 취약점 유형입니다:")
        for t, cnt in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True):
            st.markdown(f"- 🚨 **`{t}`**: 총 **{cnt}회** 발생")

    st.divider()

    # ---------------- AI 맞춤 기출 탐색 및 즉석 방어 훈련 영역 ----------------
    st.subheader("🎯 AI 맞춤 기출 탐색 & 실전 방어 훈련")
    st.markdown("""
    AI가 최근 3개년 평가원 기출 모의고사 전체 시험지 속에서 **학생의 취약점과 동일한 평가원 함정 구조를 가진 문항**을 탐색했습니다.  
    아래 문항 중 하나를 선택하여 **인앱 실물 시험지 뷰어로 해당 페이지를 직접 띄우고 즉석 방어 훈련**을 진행해 보세요!
    """)

    # 현재 실전 방어 훈련 중인 문항이 있는 경우 상단에 인터랙티브 뷰 렌더링
    if st.session_state.active_training_problem:
        prob = st.session_state.active_training_problem
        with st.container(border=True):
            col_th1, col_th2 = st.columns([3, 1])
            with col_th1:
                st.markdown(f"### 🛡️ [실전 방어 훈련] {prob['exam_title']} **{prob['q_num']}번** ({prob['page']}페이지)")
                st.caption(f"제재: {prob['genre']} | 문항 주제: {prob['topic']}")
            with col_th2:
                if st.button("❌ 훈련 닫기", use_container_width=True):
                    st.session_state.active_training_problem = None
                    st.session_state.training_feedback = None
                    st.rerun()

            col_train_pdf, col_train_act = st.columns([1.1, 1.1], gap="large")

            # 좌측: 해당 시험지 PDF 원문 뷰어 (해당 문제 페이지로 자동 점프)
            with col_train_pdf:
                target_pdf_b64 = get_exam_pdf_base64(prob["exam_id"])
                if target_pdf_b64:
                    st.caption(f"📄 원문 시험지 **{prob['page']}페이지**로 자동 이동되었습니다. {prob['q_num']}번 문제를 확인하세요.")
                    render_pdf_viewer(target_pdf_b64, initial_page=prob["page"], height=680)
                else:
                    st.warning(f"📄 '{prob['exam_title']}' 원문 PDF가 앱 내에 아직 등록되지 않았습니다.")
                    if master_drive_url:
                        st.markdown(f"""
                        <a href="{master_drive_url}" target="_blank">
                            <button style="background-color: #0284c7; color: white; border: none; padding: 8px 14px; border-radius: 6px; font-weight: bold; cursor: pointer;">
                                📂 구글 드라이브에서 '{prob['exam_title']}' 원문 파일 열기 ↗
                            </button>
                        </a>
                        """, unsafe_allow_html=True)
                    st.info(f"👉 시험지의 **{prob['page']}페이지 {prob['q_num']}번 문항**을 종이 시험지나 구글 드라이브에서 펼쳐주세요.")

            # 우측: 방어 미션 수행 및 AI 피드백
            with col_train_act:
                st.markdown(f"""
                <div style="background-color: #fef2f2; border: 1px solid #fecaca; padding: 12px 16px; border-radius: 8px; margin-bottom: 12px;">
                    <b style="color: #991b1b;">😈 평가원의 함정 설계:</b><br>
                    <span style="color: #7f1d1d; font-size: 0.95rem;">{prob['trap_concept']}</span>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px;">
                    <b style="color: #166534;">💡 방어 훈련 미션:</b><br>
                    <span style="color: #14532d; font-size: 0.95rem;">👉 <b>{prob['mission']}</b></span>
                </div>
                """, unsafe_allow_html=True)

                defense_input = st.text_area(
                    f"📝 위 시험지의 {prob['q_num']}번 문제를 보고, 방어 미션에 맞추어 선지를 검증한 생각이나 오답 판별 근거를 적어보세요:",
                    height=140,
                    placeholder="예: 선지의 '~하기 위하여'라는 목적 표현이 지문의 2문단 3번째 줄에 서술된 '결과'와 인과관계가 전도되어 있어 오답으로 판별했습니다."
                )

                if st.button("🚀 AI에게 방어 검증 받기", type="primary", use_container_width=True):
                    if not client:
                        st.error("Gemini API Key가 설정되지 않아 피드백을 생성할 수 없습니다.")
                    elif not defense_input.strip():
                        st.warning("선지를 검증한 생각을 먼저 적어주세요.")
                    else:
                        with st.spinner("방어 논리를 정밀 분석하고 있습니다..."):
                            try:
                                fb = evaluate_student_defense(client, prob, defense_input)
                                st.session_state.training_feedback = fb
                            except Exception as e:
                                st.error(f"피드백 생성 오류: {e}")
                        st.rerun()

                if st.session_state.training_feedback:
                    st.divider()
                    st.markdown(f"""
                    <div style="background-color: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #3b82f6; padding: 14px; border-radius: 6px;">
                        <b style="color: #1e3a8a;">👨‍🏫 AI 1:1 방어 코칭:</b><br>
                        <div style="margin-top: 6px; color: #334155; line-height: 1.6;">
                            {st.session_state.training_feedback}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            st.divider()

    # 오류 태그별 AI 탐색 기출 문항 카드 리스트
    for t, cnt in tag_counts.items():
        problems = get_prescription_problems(t)
        with st.container(border=True):
            st.markdown(f"#### 🚨 [{t}] 극복 솔루션 (이번 시험 {cnt}회 감지)")
            st.write(f"AI가 전체 모의고사 PDF 중에서 `{t}` 함정이 가장 날카롭게 설계된 **{len(problems)}개 기출 문제**를 선별했습니다:")
            
            p_cols = st.columns(len(problems))
            for idx, p in enumerate(problems):
                with p_cols[idx]:
                    with st.container(border=True):
                        st.markdown(f"📌 **{p['exam_title']} {p['q_num']}번**")
                        st.caption(f"**제재:** {p['genre']} ({p['page']}p)")
                        st.caption(f"**주제:** {p['topic']}")
                        st.markdown(f"**수행 미션:** *{p['mission']}*")
                        
                        if st.button(f"🎯 실물 시험지 띄우고 방어 훈련 ({p['q_num']}번)", key=f"btn_train_{p['id']}", use_container_width=True):
                            st.session_state.active_training_problem = p
                            st.session_state.training_feedback = None
                            st.rerun()

    st.divider()
    st.subheader("📝 문항별 복원된 나의 사고 & 행동 원칙 총정리")
    for item in diagnosed:
        with st.expander(f"📌 {item['q_num']}번 문항 (선택: {item['my_pick']}번 | 태그: {item['error_tag']})"):
            st.markdown(f"**🧠 나의 사고 과정:** {item['student_thought']}")
            st.markdown(f"**😈 평가원 함정 구조:** {item['evaluator_trap']}")
            st.info(f"**💡 행동 원칙:** {item['action_rule']}")

    st.divider()
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("💾 이 진단 결과를 교사 대시보드로 제출", type="primary", use_container_width=True):
            sub_data = {
                "student_id": student["student_id"],
                "student_name": student["name"],
                "exam_id": exam_info["exam_id"],
                "exam_title": exam_info["title"],
                "total_time": st.session_state.total_time,
                "time_pressure": st.session_state.time_pressure,
                "diagnosed_items": diagnosed,
                "error_tags": list(tag_counts.keys())
            }
            save_submission(sub_data)
            
            # 구글 시트 연동 전송
            gas_url = cfg.get("gas_api_url", "")
            if gas_url and gas_url.startswith("http"):
                try:
                    requests.post(gas_url, json=sub_data, timeout=5)
                except Exception:
                    pass
            st.toast("선생님께 진단 리포트가 성공적으로 제출되었습니다!", icon="✅")

    with col_b2:
        if st.button("🔄 새로운 시험 진단하기 (초기화)", use_container_width=True):
            st.session_state.student_stage = "OMR"
            st.session_state.vulnerable_queue = []
            st.session_state.queue_index = 0
            st.session_state.diagnosed_items = []
            st.session_state.active_training_problem = None
            st.session_state.training_feedback = None
            if "omr_df" in st.session_state:
                del st.session_state["omr_df"]
            st.rerun()
