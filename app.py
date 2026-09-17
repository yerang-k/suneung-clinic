import os
import streamlit as st
from google import genai

from data_manager import (
    init_data_dirs, verify_admin_password,
    get_effective_api_key, save_student_api_key, clear_student_api_key
)
from admin_view import render_admin_dashboard
from student_view import (
    render_student_login,
    render_omr_stage,
    render_interview_stage,
    render_report_stage,
    render_student_mypage
)

# ==========================================
# 1. 앱 기본 설정
# ==========================================
st.set_page_config(
    page_title="수능 국어 사고 복원 클리닉",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 데이터 디렉토리 및 기본 설정 초기화
init_data_dirs()

# 세션 기본 상태 초기화
if "auth_student" not in st.session_state:
    st.session_state.auth_student = None
if "is_admin_authenticated" not in st.session_state:
    st.session_state.is_admin_authenticated = False
if "student_stage" not in st.session_state:
    st.session_state.student_stage = "LOGIN"
if "app_mode" not in st.session_state:
    st.session_state.app_mode = "STUDENT"  # "STUDENT" or "ADMIN"

# ==========================================
# 2. 사이드바: 모드 전환 및 Gemini API 설정
# ==========================================
with st.sidebar:
    st.title("🧠 수능 한 문제 더")
    st.caption("메타인지 기반 사고 복원 & 평가원 함정 클리닉")

    # API Key 설정 및 영구 저장
    st.divider()
    saved_key, key_source = get_effective_api_key()

    st.markdown("#### 🔑 Gemini API 설정")
    user_api_key = st.text_input(
        "Gemini API Key",
        value=saved_key,
        type="password",
        placeholder="AI Studio 키를 입력하세요",
        help="Google AI Studio에서 발급받은 Gemini API 키입니다."
    )

    col_k1, col_k2 = st.columns([1.3, 1])
    with col_k1:
        if st.button("💾 이 기기에 저장", use_container_width=True, type="primary"):
            if user_api_key.strip():
                save_student_api_key(user_api_key.strip())
                st.success("API 키가 저장되었습니다! 앞으로 새로고침해도 유지됩니다.")
                st.rerun()
            else:
                st.warning("API 키를 먼저 입력해 주세요.")
    with col_k2:
        if st.button("🗑️ 키 삭제", use_container_width=True):
            clear_student_api_key()
            st.info("저장된 API 키가 삭제되었습니다.")
            st.rerun()

    active_key = user_api_key.strip() or saved_key
    client = None
    if active_key:
        try:
            client = genai.Client(api_key=active_key)
            if key_source == "USER":
                st.caption("🟢 이 기기에 저장된 API 키로 동작 중")
            elif key_source == "ADMIN":
                st.caption("🏫 선생님 등록 공용 API 키로 동작 중")
            elif key_source == "ENV":
                st.caption("🌐 시스템 환경변수 API 키로 동작 중")
            else:
                st.caption("🟡 임시 입력 상태입니다. [이 기기에 저장]을 누르면 유지됩니다.")
        except Exception as e:
            st.error(f"API 클라이언트 오류: {e}")
    else:
        st.info("💡 실시간 AI 인터뷰를 위해 API 키를 입력 후 [이 기기에 저장]을 눌러주세요.")

    st.divider()
    # 모드 전환
    mode_selection = st.radio(
        "접속 모드 선택",
        options=["🎓 학생 학습 모드", "🔒 교사용 관리자 모드"],
        index=0 if st.session_state.app_mode == "STUDENT" else 1
    )

    if "교사용" in mode_selection:
        st.session_state.app_mode = "ADMIN"
    else:
        st.session_state.app_mode = "STUDENT"

    # 로그인 상태 표시 및 로그아웃 버튼
    st.divider()
    if st.session_state.app_mode == "STUDENT":
        if st.session_state.auth_student:
            student = st.session_state.auth_student
            st.success(f"로그인 중: **{student['name']}** ({student['student_id']})")
            if st.button("학생 로그아웃", use_container_width=True):
                st.session_state.auth_student = None
                st.session_state.student_stage = "LOGIN"
                st.rerun()
    else:
        if st.session_state.is_admin_authenticated:
            st.success("교사 관리자 인증 완료")
            if st.button("관리자 모드 로그아웃", use_container_width=True):
                st.session_state.is_admin_authenticated = False
                st.rerun()

# ==========================================
# 3. 메인 뷰 라우팅
# ==========================================
if st.session_state.app_mode == "ADMIN":
    # 관리자 모드
    if not st.session_state.is_admin_authenticated:
        st.subheader("🔒 교사용 관리자 로그인")
        st.caption("학생 계정, 시험지 원문 PDF 및 구글 드라이브 처방 링크를 설정하려면 관리자 비밀번호를 입력하세요.")
        
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            with st.form("admin_login_form"):
                pw_input = st.text_input("관리자 마스터 비밀번호", type="password", placeholder="초기 비밀번호: teacher1234")
                submitted = st.form_submit_button("관리자 인증", type="primary", use_container_width=True)
                if submitted:
                    if verify_admin_password(pw_input):
                        st.session_state.is_admin_authenticated = True
                        st.success("인증되었습니다!")
                        st.rerun()
                    else:
                        st.error("비밀번호가 올바르지 않습니다.")
            
            st.write("")
            if st.button("🎓 학생 화면으로 돌아가기", use_container_width=True):
                st.session_state.app_mode = "STUDENT"
                st.rerun()
    else:
        render_admin_dashboard()

else:
    # 학생 모드
    if not st.session_state.auth_student:
        render_student_login()
    else:
        # 학생 인증 완료 상태
        student_tab1, student_tab2 = st.tabs([
            "✏️ 시험 진단실",
            "📊 나의 누적 성장 리포트 (마이페이지)"
        ])
        
        with student_tab1:
            stage = st.session_state.get("student_stage", "OMR")
            
            if stage == "OMR":
                render_omr_stage()
            elif stage == "INTERVIEW":
                if not client:
                    st.error("⚠️ AI 인터뷰를 진행하려면 왼쪽 사이드바에 Gemini API Key를 입력해야 합니다.")
                else:
                    render_interview_stage(client)
            elif stage == "REPORT":
                render_report_stage(client)

        with student_tab2:
            render_student_mypage()
