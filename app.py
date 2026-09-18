import os
import streamlit as st

# ==========================================
# 1. 앱 기본 설정 (Streamlit 최우선 실행 필수)
# ==========================================
st.set_page_config(
    page_title="수능 국어 사고 복원 클리닉",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "### 수능 국어 메타인지 사고 복원 클리닉 2.0\n학생의 오답 경로를 정밀 진단하고 평가원 함정 방어 원칙을 수립합니다."
    }
)

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
# 2. 스타일 및 CSS 설정
# ==========================================
# ⭐️ 전역 스타일: 상단 GitHub 아이콘, Edit(연필) 아이콘, 햄버거 메뉴, 툴바 완전 제거 & 깔끔한 여백
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css');

/* ===================================================
   Paper Clinic Editorial Design System
   (Stitch 디자인 시스템 "Paper Clinic Editorial"을 적용한 디자인 토큰)
   디자인 토큰: 색상/여백/모서리 반경/폰트 크기를 한 곳에서 관리.
   앱 전역의 커스텀 HTML(inline style)에서도 var(--token)으로 동일하게 참조 가능.
   =================================================== */
:root {
    /* 색상: 따뜻한 아이보리 캔버스 + 딥 차콜 잉크 + 세이지/테라코타 포인트 */
    --color-bg: #FAF8F5;
    --color-surface: #FFFFFF;
    --color-surface-muted: #F5F2EB;
    --color-surface-accent: #E3EAE2;
    --color-surface-accent-soft: #F1F5F0;
    --color-border: #E6E1DA;
    --color-border-strong: #CDC5BD;
    --color-border-accent: #C7D6CB;
    --color-text: #2B2927;
    --color-text-muted: #4B4640;
    --color-text-subtle: #7C766F;
    --color-primary: #2B2927;
    --color-primary-hover: #3A3530;
    --color-accent: #5E7966;
    --color-danger: #C86446;
    /* 여백 */
    --space-xs: 4px;
    --space-sm: 8px;
    --space-md: 16px;
    --space-lg: 24px;
    /* 모서리 반경 */
    --radius-sm: 4px;
    --radius-md: 6px;
    --radius-lg: 8px;
    /* 그림자 (은은한 웜톤 그림자, 네온/과한 광택 지양) */
    --shadow-sm: 0 1px 3px rgba(43, 41, 39, 0.04), 0 1px 2px rgba(43, 41, 39, 0.02);
    --shadow-md: 0 4px 12px rgba(43, 41, 39, 0.06), 0 1px 3px rgba(43, 41, 39, 0.04);
    /* 제목 위계(페이지 제목 > 섹션 제목 > 카드 제목 > 보조 라벨) */
    --font-h1: 1.6rem;
    --font-h2: 1.3rem;
    --font-h3: 1.1rem;
    --font-h4: 1rem;
    --font-h5: 0.92rem;
}

/* 0. 타이포그래피 및 기본 폰트 설정: 한글은 Pretendard, 숫자/영문은 Inter */
html, body, [class*="css"] {
    font-family: 'Pretendard Variable', Pretendard, 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    color: var(--color-text-muted);
    background-color: var(--color-bg);
}

/* 제목 위계: 페이지 제목(h1) > 섹션 제목(h2~h3) > 카드/보조 제목(h4~h6)
   모든 레벨이 동일한 굵기/크기로 보이던 문제를 해결하기 위해 레벨별 크기를 명확히 분리 */
h1, h2, h3, h4, h5, h6 {
    color: var(--color-text) !important;
    font-family: 'Pretendard Variable', Pretendard, 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.015em !important;
}
h1 { font-size: var(--font-h1) !important; }
h2 { font-size: var(--font-h2) !important; }
h3 { font-size: var(--font-h3) !important; }
h4 { font-size: var(--font-h4) !important; }
h5, h6 {
    font-size: var(--font-h5) !important;
    font-weight: 600 !important;
    color: var(--color-text-muted) !important;
}
/* 좁은 화면에서 페이지 제목이 2줄로 줄바꿈되며 화면 상단을 과도하게 차지하지 않도록 */
@media (max-width: 640px) {
    h1 { font-size: 1.35rem !important; }
    h2 { font-size: 1.15rem !important; }
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

/* 3. 좌측 사이드바 펼치기 토글 버튼(>>) */
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
    background-color: var(--color-surface) !important;
    border: 1.5px solid var(--color-primary) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--color-primary) !important;
    padding: 4px 10px !important;
    box-shadow: 0 2px 6px rgba(43, 41, 39, 0.15) !important;
    transition: all 0.15s ease-in-out !important;
}

[data-testid="stSidebarCollapsedControl"] button:hover,
[data-testid="collapsedControl"] button:hover {
    background-color: var(--color-surface-accent-soft) !important;
    border-color: var(--color-accent) !important;
    color: var(--color-accent) !important;
    transform: scale(1.03);
}

[data-testid="stSidebarCollapseButton"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    color: var(--color-primary) !important;
}

/* 4. 사이드바(Surface Gray 배경 & 웜그레이 테두리) */
section[data-testid="stSidebar"] {
    background-color: var(--color-surface-muted) !important;
    border-right: 1px solid var(--color-border) !important;
}

/* 5. 카드 및 패널 컴포넌트 (Soft Shadow, 14px 곡선, 매우 연한 테두리) */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: var(--color-surface) !important;
    border: 1px solid var(--color-border) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-md) !important;
    transition: box-shadow 0.2s ease-in-out !important;
}

/* 6. 버튼 스타일링 */
/* Primary Button: Deep Warm Charcoal, White Text */
button[kind="primary"] {
    background-color: var(--color-primary) !important;
    color: #FDFBF7 !important;
    border: 1px solid var(--color-primary) !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    padding: 0.5rem 1rem !important;
    box-shadow: 0 2px 5px rgba(43, 41, 39, 0.15) !important;
    transition: all 0.15s ease-in-out !important;
}
button[kind="primary"]:hover {
    background-color: var(--color-primary-hover) !important;
    border-color: var(--color-primary-hover) !important;
    box-shadow: 0 4px 10px rgba(43, 41, 39, 0.2) !important;
    transform: translateY(-1px) !important;
}

/* Secondary Button: White Background, Charcoal Ink Text, Warm Stone Border */
button[kind="secondary"], button:not([kind="primary"]):not([data-testid="stChatInputSubmitButton"]) {
    background-color: var(--color-surface) !important;
    color: var(--color-text) !important;
    border: 1px solid var(--color-border-strong) !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important;
    transition: all 0.15s ease-in-out !important;
}
button[kind="secondary"]:hover, button:not([kind="primary"]):not([data-testid="stChatInputSubmitButton"]):hover {
    background-color: var(--color-surface-muted) !important;
    border-color: var(--color-accent) !important;
    color: var(--color-primary) !important;
}

/* 7. 입력창 및 셀렉트박스 (Focus 시 딥 차콜 아웃라인) */
input[type="text"], input[type="password"], textarea:not([data-testid="stChatInputTextArea"]), select, .stSelectbox [data-baseweb="select"] {
    border: 1px solid var(--color-border-strong) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--color-text) !important;
    background-color: var(--color-surface) !important;
}
input[type="text"]:focus, input[type="password"]:focus, textarea:not([data-testid="stChatInputTextArea"]):focus {
    border-color: var(--color-primary) !important;
    box-shadow: 0 0 0 1px var(--color-primary) !important;
    outline: none !important;
}

/* 7-1. st.chat_input: 1줄 가로 정렬 강제 & 채팅창 길이 자동 조절 & 화살표 인라인 배치 */
[data-testid="stChatInput"] {
    background-color: var(--color-surface) !important;
    border: 1px solid var(--color-border-strong) !important;
    border-radius: var(--radius-md) !important;
    padding: 3px 6px !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: var(--color-primary) !important;
    box-shadow: 0 0 0 1px var(--color-primary) !important;
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
    color: var(--color-text) !important;
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
    border-radius: var(--radius-sm) !important;
    background-color: var(--color-primary) !important;
    color: #FDFBF7 !important;
    border: none !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
    margin: 0 !important;
    cursor: pointer !important;
    box-shadow: 0 1px 3px rgba(43, 41, 39, 0.2) !important;
    transition: all 0.15s ease-in-out !important;
}
[data-testid="stChatInput"] button:hover,
button[data-testid="stChatInputSubmitButton"]:hover {
    background-color: var(--color-primary-hover) !important;
    color: #FDFBF7 !important;
    border: none !important;
    transform: scale(1.05) !important;
}
[data-testid="stChatInput"] button svg,
button[data-testid="stChatInputSubmitButton"] svg {
    fill: #FDFBF7 !important;
    color: #FDFBF7 !important;
    width: 18px !important;
    height: 18px !important;
}

/* 8. 탭 (Tabs) - 딥 차콜 언더라인 */
.stTabs [data-baseweb="tab-list"] {
    gap: 12px !important;
    border-bottom: 1.5px solid var(--color-border) !important;
    overflow-x: auto !important;
    flex-wrap: nowrap !important;
}
.stTabs [data-baseweb="tab"] {
    color: var(--color-text-muted) !important;
    font-weight: 500 !important;
    border-radius: 6px 6px 0 0 !important;
    padding: 8px 16px !important;
    white-space: nowrap !important;
}
.stTabs [aria-selected="true"] {
    color: var(--color-primary) !important;
    font-weight: 700 !important;
    border-bottom: 2.5px solid var(--color-primary) !important;
}
/* 좁은 화면에서는 탭 라벨을 촘촘히 줄여 스크롤 없이 더 많은 탭이 보이도록 */
@media (max-width: 640px) {
    .stTabs [data-baseweb="tab"] {
        padding: 8px 10px !important;
        font-size: 0.88rem !important;
    }
}

/* 9. 알림 배너 (Info, Success 등 부드러운 라운딩 및 테두리) */
div[data-testid="stAlert"] {
    border-radius: var(--radius-md) !important;
    border: 1px solid var(--color-border) !important;
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
