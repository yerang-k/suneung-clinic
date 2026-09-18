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
    render_student_welcome_header,
    render_stage_navigation_bar,
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
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# ⭐️ 전역 스타일: 상단 GitHub 아이콘, Edit(연필) 아이콘, 햄버거 메뉴, 툴바 완전 제거 & 깔끔한 여백
st.markdown("""
<style>
/* ===================================================
   Lattice Design System (Modern & Clean B2B SaaS)
   =================================================== */

/* 0. 타이포그래피 및 기본 폰트 설정 */
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    color: #404035;
    background-color: #FFFFFF;
}

/* 제목 (Ebony: #0E0E29, Bold, Tight) */
h1, h2, h3, h4, h5, h6 {
    color: #0E0E29 !important;
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.025em !important;
}

/* 본문 줄간격 및 가독성 */
p, span, label, div {
    line-height: 1.55;
}

/* 1. 우측 상단 불필요한 툴바(Share, 별, 연필, 깃허브, 햄버거 메뉴)만 정확히 제거 */
[data-testid="stToolbarActions"],
[data-testid="stHeaderActionElements"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
#MainMenu,
footer,
.stDeployButton,
header a[href*="github.com"] {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
}

/* 2. 상단 헤더: 정상 가시성 유지 & 투명 배경 */
header[data-testid="stHeader"] {
    background: transparent !important;
    z-index: 9999 !important;
    display: flex !important;
    visibility: visible !important;
}

div[class*="stAppToolbar"] {
    display: flex !important;
    visibility: visible !important;
}

/* 3. 좌측 사이드바 펼치기 토글 버튼(>>) - Lattice Teal 스타일 */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
header [data-testid="stSidebarCollapsedControl"],
header [data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    position: fixed !important;
    top: 0.6rem !important;
    left: 0.8rem !important;
    z-index: 100000 !important;
}

[data-testid="stSidebarCollapsedControl"] button,
[data-testid="collapsedControl"] button,
div[data-testid="stSidebarCollapsedControl"] button,
div[data-testid="collapsedControl"] button {
    display: inline-flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    cursor: pointer !important;
    background-color: #FFFFFF !important;
    border: 1.5px solid #046663 !important;
    border-radius: 8px !important;
    color: #046663 !important;
    padding: 4px 10px !important;
    box-shadow: 0 2px 6px rgba(4, 102, 99, 0.15) !important;
    transition: all 0.15s ease-in-out !important;
}

[data-testid="stSidebarCollapsedControl"] button:hover,
[data-testid="collapsedControl"] button:hover {
    background-color: #F0F7F6 !important;
    border-color: #16B8A2 !important;
    color: #16B8A2 !important;
    transform: scale(1.03);
}

[data-testid="stSidebarCollapseButton"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    color: #046663 !important;
}

/* 4. 사이드바(Surface Gray 배경 & 웜그레이 테두리) */
section[data-testid="stSidebar"] {
    background-color: #F6F6F5 !important;
    border-right: 1px solid #EBEBE7 !important;
}

/* 5. 카드 및 패널 컴포넌트 (Soft Shadow, 14px 곡선, 매우 연한 테두리) */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #FFFFFF !important;
    border: 1px solid #EBEBE7 !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 12px -2px rgba(14, 14, 41, 0.05) !important;
    transition: box-shadow 0.2s ease-in-out !important;
}

/* 6. 버튼 스타일링 */
/* Primary Button: Deep Mosque (#046663), White Text, 8px Radius */
button[kind="primary"] {
    background-color: #046663 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.5rem 1rem !important;
    box-shadow: 0 2px 5px rgba(4, 102, 99, 0.2) !important;
    transition: all 0.15s ease-in-out !important;
}
button[kind="primary"]:hover {
    background-color: #035350 !important;
    box-shadow: 0 4px 10px rgba(4, 102, 99, 0.3) !important;
    transform: translateY(-1px) !important;
}

/* Secondary Button: White Background, Ebony Text, Warm Gray Border */
button[kind="secondary"], button:not([kind="primary"]):not([data-testid="stChatInputSubmitButton"]) {
    background-color: #FFFFFF !important;
    color: #0E0E29 !important;
    border: 1px solid #D1D1C8 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.15s ease-in-out !important;
}
button[kind="secondary"]:hover, button:not([kind="primary"]):not([data-testid="stChatInputSubmitButton"]):hover {
    background-color: #F6F6F5 !important;
    border-color: #16B8A2 !important;
    color: #046663 !important;
}

/* 7. 입력창 및 셀렉트박스 (Focus 시 Mountain Meadow #16B8A2 아웃라인) */
input[type="text"], input[type="password"], textarea:not([data-testid="stChatInputTextArea"]), select, .stSelectbox [data-baseweb="select"] {
    border: 1px solid #D1D1C8 !important;
    border-radius: 8px !important;
    color: #0E0E29 !important;
    background-color: #FFFFFF !important;
}
input[type="text"]:focus, input[type="password"]:focus, textarea:not([data-testid="stChatInputTextArea"]):focus {
    border-color: #16B8A2 !important;
    box-shadow: 0 0 0 2px rgba(22, 184, 162, 0.2) !important;
    outline: none !important;
}

/* 7-1. st.chat_input: 1줄 가로 정렬 강제 & 채팅창 길이 자동 조절 & 화살표 인라인 배치 */
[data-testid="stChatInput"] {
    background-color: #FFFFFF !important;
    border: 1px solid #D1D1C8 !important;
    border-radius: 10px !important;
    padding: 3px 6px !important;
    box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.05) !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #16B8A2 !important;
    box-shadow: 0 0 0 2px rgba(22, 184, 162, 0.2) !important;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] form,
[data-testid="stChatInput"] [class*="stChatInput"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    gap: 6px !important;
    width: 100% !important;
}
[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stChatInput"] div:has(> textarea) {
    flex: 1 1 auto !important;
    width: calc(100% - 42px) !important;
    max-width: calc(100% - 42px) !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInputTextArea"] {
    border: none !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    outline: none !important;
    padding: 8px 10px !important;
    font-size: 0.93rem !important;
    line-height: 1.4 !important;
    color: #0E0E29 !important;
    resize: none !important;
    width: 100% !important;
}
[data-testid="stChatInput"] textarea:focus,
[data-testid="stChatInputTextArea"]:focus {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stChatInput"] button,
button[data-testid="stChatInputSubmitButton"] {
    flex: 0 0 34px !important;
    width: 34px !important;
    height: 34px !important;
    min-width: 34px !important;
    min-height: 34px !important;
    border-radius: 8px !important;
    background-color: #046663 !important;
    color: #FFFFFF !important;
    border: none !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
    margin: 0 !important;
    cursor: pointer !important;
    box-shadow: 0 1px 3px rgba(4, 102, 99, 0.2) !important;
    transition: all 0.15s ease-in-out !important;
}
[data-testid="stChatInput"] button:hover,
button[data-testid="stChatInputSubmitButton"]:hover {
    background-color: #035350 !important;
    color: #FFFFFF !important;
    border: none !important;
    transform: scale(1.05) !important;
}
[data-testid="stChatInput"] button svg,
button[data-testid="stChatInputSubmitButton"] svg {
    fill: #FFFFFF !important;
    color: #FFFFFF !important;
    width: 18px !important;
    height: 18px !important;
}

/* 8. 탭 (Tabs) - Lattice 청록색 언더라인 */
.stTabs [data-baseweb="tab-list"] {
    gap: 12px !important;
    border-bottom: 1.5px solid #EBEBE7 !important;
}
.stTabs [data-baseweb="tab"] {
    color: #59594A !important;
    font-weight: 500 !important;
    border-radius: 6px 6px 0 0 !important;
    padding: 8px 16px !important;
}
.stTabs [aria-selected="true"] {
    color: #046663 !important;
    font-weight: 700 !important;
    border-bottom: 2.5px solid #046663 !important;
}

/* 9. 알림 배너 (Info, Success 등 부드러운 라운딩 및 테두리) */
div[data-testid="stAlert"] {
    border-radius: 10px !important;
    border: 1px solid #EBEBE7 !important;
}

/* 메인 컨테이너 상단 여백 최적화 */
.block-container {
    padding-top: 3.5rem !important;
    padding-bottom: 2.5rem !important;
}
</style>
""", unsafe_allow_html=True)

# 데이터 디렉토리 및 기본 설정 초기화
init_data_dirs()

# ⭐️ URL 쿼리 파라미터 기반 접속 모드 자동 분리 (?mode=admin)
# 학생 기본 접속 URL: 파라미터 없음 (오직 학생 화면만 노출되어 혼란 방지)
# 교사 전용 접속 URL: ?mode=admin
query_mode = st.query_params.get("mode", "").lower()
if query_mode == "admin":
    st.session_state.app_mode = "ADMIN"
elif "app_mode" not in st.session_state:
    st.session_state.app_mode = "STUDENT"

# 세션 기본 상태 초기화
if "auth_student" not in st.session_state:
    st.session_state.auth_student = None
if "is_admin_authenticated" not in st.session_state:
    st.session_state.is_admin_authenticated = False
if "student_stage" not in st.session_state:
    st.session_state.student_stage = "LOGIN"

# ==========================================
# 2. 사이드바: 타이틀, 학생 정보 및 Gemini API 설정
# ==========================================
with st.sidebar:
    st.title("🎯 수능 한 문제 더")

    # 교사 전용 모드 접속 중 안내 배너
    if st.session_state.app_mode == "ADMIN":
        st.info("🔒 **교사용 관리자 페이지**\n\n선생님 관리자 모드로 접속 중입니다.")
        if st.button("🎓 학생 학습 모드로 나가기", use_container_width=True):
            st.query_params.clear()
            st.session_state.app_mode = "STUDENT"
            st.rerun()
    else:
        # 학생 모드일 때 학생 정보 카드 및 로그아웃
        if st.session_state.auth_student:
            student = st.session_state.auth_student
            with st.container(border=True):
                st.markdown(f"🎓 **{student['name']}** ({student['student_id']})")
                if st.button("🚪 학생 로그아웃", use_container_width=True):
                    st.session_state.auth_student = None
                    st.session_state.student_stage = "LOGIN"
                    st.rerun()

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

    # 관리자 모드일 때 관리자 로그아웃 버튼
    if st.session_state.app_mode == "ADMIN" and st.session_state.is_admin_authenticated:
        st.divider()
        st.success("교사 마스터 인증 완료 상태")
        if st.button("관리자 인증 로그아웃", use_container_width=True):
            st.session_state.is_admin_authenticated = False
            st.rerun()

    # 학생 모드일 때 사이드바 하단에 은은한 교사 모드 진입 링크
    if st.session_state.app_mode == "STUDENT":
        st.divider()
        if st.button("🔒 교사용 관리자 페이지", use_container_width=True, help="선생님 전용 관리 페이지로 전환합니다."):
            st.query_params["mode"] = "admin"
            st.session_state.app_mode = "ADMIN"
            st.rerun()

# ==========================================
# 3. 메인 뷰 라우팅
# ==========================================
if st.session_state.app_mode == "ADMIN":
    # 🔒 교사용 관리자 모드
    if not st.session_state.is_admin_authenticated:
        st.subheader("🔒 교사용 관리자 로그인")
        
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            st.info("💡 **초기 관리자 마스터 비밀번호**: `teacher1234`\n\n(또는 간편 비밀번호 `1234`도 사용 가능합니다)")
            
            # 원클릭 바로 로그인 버튼
            if st.button("⚡ 초기 비밀번호(teacher1234)로 바로 로그인", type="primary", use_container_width=True, key="btn_quick_admin_login"):
                st.session_state.is_admin_authenticated = True
                st.success("✅ 인증되었습니다! 관리자 화면으로 진입합니다.")
                st.rerun()

            st.write("")
            st.caption("비밀번호를 변경하셨거나 직접 입력하시려면 아래 입력창을 이용하세요:")
            with st.form("admin_login_form"):
                pw_input = st.text_input("관리자 마스터 비밀번호 직접 입력", type="password", placeholder="teacher1234 또는 변경한 비밀번호")
                submitted = st.form_submit_button("관리자 인증", use_container_width=True)
                if submitted:
                    cleaned_pw = (pw_input or "").strip()
                    if not cleaned_pw:
                        st.warning("⚠️ 입력창이 비어 있습니다. 비밀번호를 직접 타이핑하시거나, 위의 [⚡ 초기 비밀번호로 바로 로그인] 버튼을 눌러주세요.")
                    elif verify_admin_password(cleaned_pw):
                        st.session_state.is_admin_authenticated = True
                        st.success("✅ 인증되었습니다!")
                        st.rerun()
                    else:
                        st.error("❌ 비밀번호가 올바르지 않습니다. (초기 비밀번호: teacher1234 또는 1234)")
            
            st.write("")
            if st.button("🎓 학생 학습 화면으로 돌아가기", use_container_width=True):
                st.query_params.clear()
                st.session_state.app_mode = "STUDENT"
                st.rerun()
    else:
        render_admin_dashboard(client)

else:
    # 🎓 학생 모드
    if not st.session_state.auth_student:
        render_student_login()
    else:
        # 학생 인증 완료 상태
        student_tab1, student_tab2 = st.tabs([
            "✏️ 시험 진단실",
            "📊 나의 누적 성장 리포트 (마이페이지)"
        ])
        
        with student_tab1:
            # ⭐️ 1. 최상단 환영 및 진행 상태 헤더 카드 (가장 위에 항상 표시)
            render_student_welcome_header()

            # ⭐️ 2. 상단 3단계 네비게이션 바 & 저장/이어하기 바
            render_stage_navigation_bar()

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
