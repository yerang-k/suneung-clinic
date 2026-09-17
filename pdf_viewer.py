import base64
import os
import re
import requests
import streamlit as st
import pypdfium2 as pdfium

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

def load_pdf_doc(base64_pdf: str = None, pdf_path: str = None, pdf_url: str = None):
    """PDF 소스로부터 pypdfium2.PdfDocument 객체를 안전하게 로드"""
    if pdf_path and os.path.exists(pdf_path):
        try:
            return pdfium.PdfDocument(pdf_path)
        except Exception:
            pass

    if base64_pdf:
        try:
            raw_bytes = base64.b64decode(base64_pdf)
            return pdfium.PdfDocument(raw_bytes)
        except Exception:
            pass

    # 구글 드라이브 파일 직접 다운로드 시도
    if pdf_url and "drive.google.com" in pdf_url:
        file_id = extract_drive_file_id(pdf_url)
        if file_id:
            try:
                dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                resp = requests.get(dl_url, timeout=7)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    return pdfium.PdfDocument(resp.content)
            except Exception:
                pass

    return None

def render_pdf_viewer(base64_pdf: str = None, pdf_url: str = None, pdf_path: str = None, initial_page: int = 1, height: int = 720):
    """
    모든 브라우저(크롬, 엣지, 사파리, 모바일)에서 100% 동작하는 실물 시험지 뷰어
    1. pypdfium2로 PDF 페이지를 네이티브 고화질 이미지로 변환하여 렌더링 (보안 차단 이슈 0%)
    2. 이전/다음 페이지 넘김 및 특정 페이지(1~N) 자동 이동
    3. 구글 드라이브 링크가 있는 경우 공식 preview 뷰어 및 새 창 열기 폴백 제공
    """
    doc = load_pdf_doc(base64_pdf=base64_pdf, pdf_path=pdf_path, pdf_url=pdf_url)

    if doc is not None:
        total_pages = len(doc)
        
        # 페이지 상태 키 (문서 및 세션별 고유 키)
        page_state_key = f"pdf_cur_page_{initial_page}_{total_pages}"
        if page_state_key not in st.session_state:
            st.session_state[page_state_key] = max(1, min(initial_page, total_pages))

        cur_page = st.session_state[page_state_key]

        # 상단 네비게이션 바
        col_n1, col_n2, col_n3, col_n4 = st.columns([1.2, 2, 1.2, 1.2])
        with col_n1:
            if st.button("◀ 이전 페이지", key=f"btn_prev_{page_state_key}", disabled=(cur_page <= 1), use_container_width=True):
                st.session_state[page_state_key] = max(1, cur_page - 1)
                st.rerun()
        with col_n2:
            sel_p = st.selectbox(
                "페이지",
                options=list(range(1, total_pages + 1)),
                index=cur_page - 1,
                format_func=lambda x: f"📄 {x} / {total_pages} 페이지",
                label_visibility="collapsed",
                key=f"sel_{page_state_key}"
            )
            if sel_p != cur_page:
                st.session_state[page_state_key] = sel_p
                st.rerun()
        with col_n3:
            if st.button("다음 페이지 ▶", key=f"btn_next_{page_state_key}", disabled=(cur_page >= total_pages), use_container_width=True):
                st.session_state[page_state_key] = min(total_pages, cur_page + 1)
                st.rerun()
        with col_n4:
            if pdf_url and pdf_url.startswith("http"):
                st.link_button("↗ 원문 링크", pdf_url, use_container_width=True)

        # 페이지 초고화질 렌더링 (scale=2.2로 실제 인쇄 품질의 선명도 제공)
        try:
            page_obj = doc[cur_page - 1]
            img = page_obj.render(scale=2.2).to_pil()
            st.image(img, use_container_width=True, caption=f"시험지 {cur_page} / {total_pages} 페이지")
        except Exception as e:
            st.error(f"페이지 렌더링 중 오류: {e}")
        return

    # 구글 드라이브 링크가 있는데 직접 다운로드가 안 된 경우: 구글 공식 preview iframe으로 폴백
    if pdf_url and pdf_url.startswith("http"):
        file_id = extract_drive_file_id(pdf_url)
        preview_url = f"https://drive.google.com/file/d/{file_id}/preview" if file_id else pdf_url
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
