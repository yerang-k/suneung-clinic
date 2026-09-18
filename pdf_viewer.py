import base64
import os
import re
import io
import requests
import streamlit as st

# Streamlit Cloud 등 리눅스 컨테이너 환경에서 pypdfium2 로딩 실패(version.json KeyError 등) 방지
try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

def extract_drive_file_id(url: str) -> str:
    """구글 드라이브 URL에서 file_id 추출"""
    if not url:
        return ""
    m = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    return ""

@st.cache_data(show_spinner=False, ttl=7200, max_entries=5)
def get_pdf_bytes_cached(pdf_url: str = None, pdf_path: str = None, base64_pdf: str = None) -> bytes:
    """
    시험지 PDF 바이너리를 메모리에 캐시하여, 
    채팅이나 페이지 넘김 시 반복적인 드라이브 다운로드를 0초로 만듭니다.
    """
    if pdf_path and os.path.exists(pdf_path):
        try:
            with open(pdf_path, "rb") as f:
                return f.read()
        except Exception:
            pass

    if base64_pdf:
        try:
            return base64.b64decode(base64_pdf)
        except Exception:
            pass

    if pdf_url:
        if "drive.google.com" in pdf_url:
            file_id = extract_drive_file_id(pdf_url)
            if file_id:
                try:
                    dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                    resp = requests.get(dl_url, timeout=10)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        return resp.content
                except Exception:
                    pass
        elif pdf_url.startswith("http"):
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(pdf_url, headers=headers, timeout=10)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    return resp.content
            except Exception:
                pass

    return None

@st.cache_data(show_spinner=False, max_entries=10)
def get_pdf_total_pages_cached(pdf_bytes: bytes) -> int:
    """PDF 전체 페이지 수 조회 (캐시됨)"""
    if not pdf_bytes:
        return 16
    if pdfium is not None:
        try:
            doc = pdfium.PdfDocument(pdf_bytes)
            return len(doc)
        except Exception:
            pass
    # Fallback to pure-python pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        return len(reader.pages)
    except Exception:
        return 16

@st.cache_data(show_spinner=False, max_entries=80)
def render_pdf_page_cached(pdf_bytes: bytes, page_index: int, scale: float = 2.0) -> bytes:
    """
    지정된 페이지를 고화질 JPEG 이미지 바이트로 렌더링하여 캐시합니다.
    한 번 렌더링된 페이지는 0.01초 만에 즉각 화면에 표시됩니다.
    """
    if not pdf_bytes or pdfium is None:
        return None
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
        if 0 <= page_index < len(doc):
            page = doc[page_index]
            pil_img = page.render(scale=scale).to_pil()
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
    except Exception:
        pass
    return None

# KICE 16-page empirical mapping (표준 수능 국어 45문항 배분표)
KICE_16_PAGE_MAP = {
    1: 1, 2: 1, 3: 1,
    4: 2, 5: 2, 6: 2,
    7: 3, 8: 3, 9: 3,
    10: 4, 11: 4,
    12: 5, 13: 5,
    14: 6, 15: 6,
    16: 7, 17: 7,
    18: 8, 19: 8, 20: 8, 21: 8,
    22: 9, 23: 9, 24: 9,
    25: 10, 26: 10, 27: 10,
    28: 11, 29: 11, 30: 11, 31: 11,
    32: 12, 33: 12, 34: 12,
    35: 13, 36: 13, 37: 13,
    38: 14, 39: 14, 40: 14,
    41: 15, 42: 15,
    43: 16, 44: 16, 45: 16
}

@st.cache_data(show_spinner=False, max_entries=50)
def get_page_for_question_cached(pdf_bytes: bytes, q_num: int, total_pages: int = 16) -> int:
    """
    시험지 PDF에서 q_num번 문항이 위치한 페이지 번호(1-indexed)를 반환합니다.
    1. PDF 텍스트 레이어가 있는 경우 pypdf로 해당 문항 번호 패턴(예: '45.' 또는 '45번')을 우선 탐색
    2. 텍스트가 없거나 스캔본인 경우 평가원 표준 16페이지 문항 배분표로 자동 계산
    """
    if not q_num or q_num < 1:
        return 1

    if pdf_bytes:
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            actual_total = len(reader.pages)
            if actual_total > 0:
                total_pages = actual_total
                std_p = KICE_16_PAGE_MAP.get(q_num, int(round((q_num - 1) / 44 * (total_pages - 1))) + 1)
                std_p = max(1, min(std_p, total_pages))
                
                priorities = [std_p]
                if std_p - 1 >= 1: priorities.append(std_p - 1)
                if std_p + 1 <= total_pages: priorities.append(std_p + 1)
                remaining = [p for p in range(1, total_pages + 1) if p not in priorities]
                search_order = priorities + remaining

                pat = re.compile(r'(?:^|\s|[^\d])' + str(q_num) + r'\s*[\.번]')
                for p in search_order:
                    text = reader.pages[p - 1].extract_text() or ""
                    if pat.search(text):
                        return p
        except Exception:
            pass

    # 2. 표준 평가원 배분표 비례 스케일링
    if total_pages == 16:
        return KICE_16_PAGE_MAP.get(q_num, min(max(1, int(round((q_num - 1) / 44 * 15)) + 1), 16))
    elif total_pages <= 1:
        return 1
    else:
        std_page = KICE_16_PAGE_MAP.get(q_num, (q_num - 1) / 44 * 15 + 1)
        scaled = int(round((std_page - 1) / 15 * (total_pages - 1))) + 1
        return max(1, min(scaled, total_pages))

def render_pdf_viewer(base64_pdf: str = None, pdf_url: str = None, pdf_path: str = None, initial_page: int = 1, q_num: int = None, height: int = 720, viewer_id: str = "default"):
    """
    초고속 캐싱 및 문항별 자동 이동이 적용된 실물 시험지 뷰어
    - 특정 문항(예: 45번) 선택 시 해당 시험지 페이지로 0.01초 자동 점프
    - 상단 문항 바로가기 드롭다운(1~45번) 지원
    - 구글 드라이브 다운로드 1회 메모리 캐시 및 페이지 이미지 렌더링 캐시
    """
    pdf_bytes = get_pdf_bytes_cached(pdf_url=pdf_url, pdf_path=pdf_path, base64_pdf=base64_pdf)

    if pdf_bytes:
        total_pages = get_pdf_total_pages_cached(pdf_bytes)
        if total_pages > 0:
            page_state_key = f"pdf_cur_page_{viewer_id}"
            last_q_key = f"pdf_last_q_{viewer_id}"

            # ⭐️ q_num이 지정되었거나 변경되었을 때 해당 문항의 페이지로 즉시 자동 점프
            if q_num is not None:
                if st.session_state.get(last_q_key) != q_num:
                    st.session_state[last_q_key] = q_num
                    target_page = get_page_for_question_cached(pdf_bytes, q_num, total_pages)
                    st.session_state[page_state_key] = target_page
            elif page_state_key not in st.session_state:
                st.session_state[page_state_key] = max(1, min(initial_page, total_pages))

            cur_page = st.session_state.get(page_state_key, max(1, min(initial_page, total_pages)))
            cur_page = max(1, min(cur_page, total_pages))
            st.session_state[page_state_key] = cur_page

            # 상단 네비게이션 바 (이전 | 페이지선택 | 🎯 문항이동 | 다음 | 원문열기)
            col_n1, col_n2, col_n3, col_n4, col_n5 = st.columns([1, 1.6, 1.7, 1, 1])
            with col_n1:
                if st.button("◀ 이전", key=f"btn_prev_{viewer_id}_{cur_page}", disabled=(cur_page <= 1), use_container_width=True):
                    st.session_state[page_state_key] = max(1, cur_page - 1)
                    st.rerun()
            with col_n2:
                sel_p = st.selectbox(
                    "페이지",
                    options=list(range(1, total_pages + 1)),
                    index=cur_page - 1,
                    format_func=lambda x: f"📄 {x} / {total_pages} 페이지",
                    label_visibility="collapsed",
                    key=f"sel_p_{viewer_id}_{cur_page}"
                )
                if sel_p != cur_page:
                    st.session_state[page_state_key] = sel_p
                    st.rerun()
            with col_n3:
                # 🎯 문항 바로가기 드롭다운
                default_lbl = f"🎯 {q_num}번 문항 이동" if q_num else "🎯 문항 이동..."
                q_options = [default_lbl] + [f"{i}번 문항" for i in range(1, 46) if not (q_num and i == q_num)]
                sel_q = st.selectbox(
                    "문항 이동",
                    options=q_options,
                    label_visibility="collapsed",
                    key=f"sel_q_{viewer_id}_{cur_page}"
                )
                if sel_q != default_lbl:
                    chosen_q = int(re.search(r'\d+', sel_q).group())
                    jump_p = get_page_for_question_cached(pdf_bytes, chosen_q, total_pages)
                    st.session_state[page_state_key] = jump_p
                    st.session_state[last_q_key] = chosen_q
                    st.rerun()
            with col_n4:
                if st.button("다음 ▶", key=f"btn_next_{viewer_id}_{cur_page}", disabled=(cur_page >= total_pages), use_container_width=True):
                    st.session_state[page_state_key] = min(total_pages, cur_page + 1)
                    st.rerun()
            with col_n5:
                if pdf_url and pdf_url.startswith("http"):
                    st.link_button("↗ 원문", pdf_url, use_container_width=True)

            # 캐시된 초고속 페이지 이미지 출력 (독립 고정 스크롤 박스 적용)
            img_bytes = render_pdf_page_cached(pdf_bytes, cur_page - 1, scale=2.0)
            if img_bytes:
                caption_parts = [f"📄 {cur_page} / {total_pages} 페이지 (마우스 휠로 위아래 스크롤)"]
                if q_num:
                    caption_parts.insert(0, f"🎯 **{q_num}번 문항** 위치")
                with st.container(height=height):
                    st.image(img_bytes, use_container_width=True, caption=" | ".join(caption_parts))
                return

    # 구글 드라이브 링크가 있는데 직접 다운로드가 안 된 경우: 구글 공식 preview iframe으로 폴백
    if pdf_url and pdf_url.startswith("http"):
        file_id = extract_drive_file_id(pdf_url)
        target_p = initial_page
        if q_num:
            target_p = KICE_16_PAGE_MAP.get(q_num, 16 if q_num == 45 else 1)
        preview_url = f"https://drive.google.com/file/d/{file_id}/preview" if file_id else pdf_url
        if target_p > 1:
            preview_url += f"#page={target_p}"

        st.markdown(f"""
        <div style="margin-bottom: 8px; display: flex; justify-content: flex-end;">
            <a href="{pdf_url}" target="_blank" style="text-decoration: none;">
                <button style="background-color: #0284c7; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold; cursor: pointer;">
                    ↗ 새 창에서 시험지 전체화면 열기
                </button>
            </a>
        </div>
        <div style="border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <iframe 
                src="{preview_url}" 
                width="100%" 
                height="{height}px" 
                style="border: none;"
                allow="autoplay">
            </iframe>
        </div>
        """, unsafe_allow_html=True)
        return

    st.warning("📄 등록된 시험지 PDF 파일이 없습니다. [교사용 관리자 모드] ➔ [📄 시험지 및 PDF 업로드] 탭에서 해당 시험지의 PDF 파일이나 구글 드라이브 링크를 연결해 주세요.")

def render_csat_text_view(question_item: dict, my_pick: int, status_tag: str):
    """
    PDF가 없거나 텍스트로 자세히 볼 때 평가원 모의고사 양식으로 깔끔하게 렌더링하는 뷰어
    """
    options_symbol = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}
    
    st.markdown(f"""
    <div style="background-color: #ffffff; padding: 1.2rem; border-radius: 8px; border: 1px solid #e2e8f0; font-family: 'Nanum Myeongjo', 'Batang', serif;">
        <div style="border-bottom: 2px solid #0f172a; padding-bottom: 6px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: bold; font-size: 1.1rem; color: #0f172a;">[ {question_item.get('q_num', '')} 번 ] {question_item.get('question', '')}</span>
            <span style="font-size: 0.85rem; color: #64748b; background: #f1f5f9; padding: 2px 8px; border-radius: 4px;">{status_tag}</span>
        </div>
        <div style="background-color: #f8fafc; padding: 14px; border: 1px solid #cbd5e1; border-radius: 6px; line-height: 1.75; font-size: 0.95rem; margin-bottom: 16px; color: #1e293b; white-space: pre-wrap;">
{question_item.get('passage', '지문 텍스트가 등록되지 않았습니다.')}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**[선지]**")
    for opt_num, opt_text in question_item.get("options", {}).items():
        sym = options_symbol.get(opt_num, f"{opt_num}.")
        if opt_num == my_pick:
            st.error(f"👉 **{sym} {opt_text}** `(내가 고른 선지)`")
        elif opt_num == question_item.get("correct"):
            st.success(f"**{sym} {opt_text}** `(실제 정답)`")
        else:
            st.write(f"**{sym}** {opt_text}")
