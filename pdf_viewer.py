import re
import streamlit as st

def format_drive_preview_url(url: str) -> str:
    """구글 드라이브 공유 링크를 임베드 가능한 /preview 링크로 변환"""
    if not url:
        return ""
    # /file/d/FILE_ID/ 형식 매칭
    match = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/file/d/{file_id}/preview"
    # id=FILE_ID 형식 매칭
    match = re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/file/d/{file_id}/preview"
    return url

def render_pdf_viewer(base64_pdf: str = None, pdf_url: str = None, initial_page: int = 1, height: int = 720):
    """
    시험지 원문 PDF 뷰어
    - 구글 드라이브 또는 웹 URL이 있는 경우 안정적인 공식 임베드 뷰어로 출력
    - 로컬 Base64 PDF 파일이 있는 경우 Base64 데이터 스트림으로 출력
    """
    if pdf_url and pdf_url.startswith("http"):
        preview_url = format_drive_preview_url(pdf_url)
        st.markdown(f"""
        <div style="margin-bottom: 8px; display: flex; justify-content: flex-end;">
            <a href="{pdf_url}" target="_blank" style="text-decoration: none;">
                <button style="background-color: #f1f5f9; border: 1px solid #cbd5e1; color: #1e293b; padding: 4px 10px; border-radius: 4px; font-size: 0.85rem; cursor: pointer;">
                    ↗ 새 창에서 원문 열기
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

    if base64_pdf:
        pdf_display = f"""
        <div style="border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <iframe 
                src="data:application/pdf;base64,{base64_pdf}#page={initial_page}&toolbar=1&navpanes=0&scrollbar=1" 
                width="100%" 
                height="{height}px" 
                type="application/pdf"
                style="border: none;">
            </iframe>
        </div>
        """
        st.markdown(pdf_display, unsafe_allow_html=True)
        return

    st.warning("📄 등록된 시험지 PDF 파일이 없습니다. [교사용 관리자 모드]에서 시험지 PDF 또는 링크를 등록해 주세요.")

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
