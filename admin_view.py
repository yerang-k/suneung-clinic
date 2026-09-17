import streamlit as st
import pandas as pd
from data_manager import (
    get_students, add_student, delete_student, save_students,
    get_admin_config, save_admin_config,
    get_exams, save_exam, get_exam_pdf_base64,
    attach_pdf_to_exam, get_exam_pdf_source, delete_exam,
    get_submissions
)
from pdf_viewer import render_pdf_viewer

def render_admin_dashboard():
    st.title("🔒 교사용 관리자 모드")
    st.caption("학생 계정, 시험지 원문 PDF 및 취약점 유형별 구글 드라이브 처방 링크를 관리합니다.")

    tab1, tab2, tab3, tab4 = st.tabs([
        "👥 학생 계정 관리",
        "📄 시험지 및 PDF 업로드",
        "⚙️ 마스터 연동 및 시스템 설정",
        "📊 학생 진단 제출 현황"
    ])

    # ---------------- 탭 1: 학생 계정 관리 ----------------
    with tab1:
        st.subheader("👥 학생 계정 설정")
        col_add, col_csv = st.columns(2, gap="medium")
        
        with col_add:
            with st.form("add_student_form", clear_on_submit=False):
                st.markdown("##### ➕ 개별 학생 등록 / 비밀번호 재설정")
                new_sid = st.text_input("학번 (예: 30101)", placeholder="30101", key="admin_add_sid")
                new_name = st.text_input("학생 이름", placeholder="김수험", key="admin_add_name")
                new_pw = st.text_input("접속 비밀번호", value="1234", key="admin_add_pw")
                submitted = st.form_submit_button("학생 등록 및 저장", type="primary", use_container_width=True)
                if submitted:
                    sid_c = (new_sid or "").strip()
                    name_c = (new_name or "").strip()
                    pw_c = (new_pw or "").strip()
                    if sid_c and name_c and pw_c:
                        ok, msg = add_student(sid_c, name_c, pw_c)
                        st.success(f"✅ {name_c}({sid_c}) {msg}")
                        st.rerun()
                    else:
                        missing = []
                        if not sid_c:
                            missing.append("학번")
                        if not name_c:
                            missing.append("이름")
                        if not pw_c:
                            missing.append("비밀번호")
                        st.error(f"⚠️ {', '.join(missing)}을(를) 모두 입력해주세요.")

        with col_csv:
            st.markdown("##### 📥 CSV 파일로 학생 일괄 등록")
            st.caption("CSV 포맷: `student_id,name,password` (헤더 포함)")
            csv_file = st.file_uploader("학생 명단 CSV 업로드", type=["csv"])
            if csv_file is not None:
                try:
                    df = pd.read_csv(csv_file)
                    required_cols = {"student_id", "name", "password"}
                    if required_cols.issubset(set(df.columns)):
                        if st.button("CSV 학생 일괄 등록 실행", type="primary", use_container_width=True):
                            count = 0
                            for _, row in df.iterrows():
                                add_student(str(row["student_id"]).strip(), str(row["name"]).strip(), str(row["password"]).strip())
                                count += 1
                            st.success(f"총 {count}명의 학생 계정이 등록/갱신되었습니다.")
                            st.rerun()
                    else:
                        st.error(f"CSV 헤더에 student_id, name, password 열이 필요합니다. (현재 열: {list(df.columns)})")
                except Exception as e:
                    st.error(f"CSV 파일 처리 중 오류: {e}")

        st.divider()
        st.markdown("##### 📋 현재 등록된 학생 명단")
        students = get_students()
        if students:
            df_students = pd.DataFrame(students)
            df_students.rename(columns={"student_id": "학번", "name": "이름", "password": "비밀번호"}, inplace=True)
            st.dataframe(df_students, use_container_width=True)

            del_col1, del_col2 = st.columns([2, 1])
            with del_col1:
                del_target = st.selectbox("삭제할 학생 선택", [f"{s['student_id']} - {s['name']}" for s in students])
            with del_col2:
                st.write("")
                st.write("")
                if st.button("선택 학생 삭제", type="secondary", use_container_width=True):
                    target_id = del_target.split(" - ")[0]
                    ok, msg = delete_student(target_id)
                    st.success(msg)
                    st.rerun()
        else:
            st.info("등록된 학생이 없습니다. 상단에서 학생을 등록해 주세요.")

    # ---------------- 탭 2: 시험지 및 PDF 업로드 ----------------
    with tab2:
        st.subheader("📄 시험지 등록 및 원문 PDF 업로드")
        st.caption("학생들이 오답 복원 인터뷰나 실전 방어 훈련을 진행할 때 좌측에 실물 시험지 뷰어로 실시간 제공됩니다.")

        exams = get_exams()

        # 섹션 1: 기존 시험지에 PDF 첨부 (가장 쉽고 빠른 방식)
        with st.container(border=True):
            st.markdown("##### 📌 1단계: 기존 등록된 시험지에 PDF 연결하기")
            st.caption("시험지를 선택하고, 내 컴퓨터의 PDF 파일 또는 구글 드라이브 파일 링크를 연결하세요.")

            if exams:
                target_exam_id = st.selectbox(
                    "PDF를 연결할 시험지 선택",
                    options=list(exams.keys()),
                    format_func=lambda x: f"{exams[x]['title']} ({exams[x]['total_questions']}문항) - {'✅ PDF 연결됨' if exams[x].get('pdf_filename') or exams[x].get('pdf_url') else '❌ PDF 없음'}"
                )

                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    st.markdown("**방법 A: 내 컴퓨터에서 PDF 파일 업로드**")
                    pdf_file = st.file_uploader(f"'{exams[target_exam_id]['title']}' PDF 파일", type=["pdf"], key=f"uploader_{target_exam_id}")
                with col_u2:
                    st.markdown("**방법 B: 구글 드라이브 PDF 공유 링크 (강력 추천)**")
                    st.caption("💡 구글 드라이브 공유 링크를 넣으시면 웹 배포가 재시작되어도 파일이 절대 날아가지 않습니다.")
                    drive_pdf_link = st.text_input(
                        "구글 드라이브 PDF 링크",
                        value=exams[target_exam_id].get("pdf_url", ""),
                        placeholder="https://drive.google.com/file/d/.../view?usp=sharing"
                    )

                if st.button("📥 선택한 시험지에 PDF 저장 및 연결", type="primary", use_container_width=True):
                    pdf_bytes = pdf_file.read() if pdf_file is not None else None
                    fname = pdf_file.name if pdf_file is not None else None
                    
                    if not pdf_bytes and not drive_pdf_link.strip():
                        st.warning("PDF 파일을 선택하거나 구글 드라이브 링크를 입력해 주세요.")
                    else:
                        ok, msg = attach_pdf_to_exam(
                            exam_id=target_exam_id,
                            pdf_bytes=pdf_bytes,
                            filename=fname,
                            pdf_url=drive_pdf_link.strip()
                        )
                        st.success(msg)
                        st.rerun()

        # 섹션 2: 새 시험지 등록 (expander)
        with st.expander("➕ 새로운 시험지 추가 등록하기"):
            with st.form("new_exam_form"):
                col_e1, col_e2, col_e3 = st.columns([1.5, 2, 1])
                with col_e1:
                    new_eid = st.text_input("새 시험 고유 코드", placeholder="예: 2026_11_suneung")
                with col_e2:
                    new_etitle = st.text_input("새 시험 명칭", placeholder="예: 2026학년도 대학수학능력시험 국어영역")
                with col_e3:
                    new_eq = st.number_input("총 문항 수", min_value=5, max_value=60, value=45)

                col_nf1, col_nf2 = st.columns(2)
                with col_nf1:
                    new_pdf_file = st.file_uploader("시험지 PDF 파일", type=["pdf"], key="new_exam_pdf")
                with col_nf2:
                    new_pdf_url = st.text_input("구글 드라이브 PDF 링크 (선택)", placeholder="https://drive.google.com/file/d/...")

                if st.form_submit_button("새 시험지 생성 및 저장", type="primary", use_container_width=True):
                    if not new_eid.strip() or not new_etitle.strip():
                        st.error("시험 코드와 시험 명칭을 모두 입력해 주세요.")
                    else:
                        pdf_bytes = new_pdf_file.read() if new_pdf_file is not None else None
                        fname = new_pdf_file.name if new_pdf_file is not None else None
                        ok, msg = save_exam(
                            exam_id=new_eid.strip(),
                            title=new_etitle.strip(),
                            total_questions=new_eq,
                            pdf_bytes=pdf_bytes,
                            filename=fname,
                            pdf_url=new_pdf_url.strip()
                        )
                        st.success(msg)
                        st.rerun()

        # 섹션 3: 현재 시험지 목록 및 PDF 미리보기
        st.divider()
        st.markdown("##### 📚 등록된 시험지 목록 및 PDF 미리보기")
        if exams:
            preview_eid = st.selectbox(
                "미리보기할 시험지 선택",
                options=list(exams.keys()),
                format_func=lambda x: f"{exams[x]['title']} ({exams[x]['total_questions']}문항)",
                key="preview_exam_select"
            )
            ex_info = exams[preview_eid]
            path, b64, url = get_exam_pdf_source(preview_eid)

            col_pi1, col_pi2, col_pi3 = st.columns([2, 2, 1])
            with col_pi1:
                st.write(f"**시험 코드:** `{ex_info['exam_id']}` | **총 문항 수:** {ex_info['total_questions']}문항")
            with col_pi2:
                has_pdf = bool(path or b64 or url)
                status_txt = "✅ PDF 연결됨" if has_pdf else "❌ PDF 없음 (텍스트 모드로 동작)"
                st.write(f"**PDF 상태:** {status_txt}")
            with col_pi3:
                if st.button("🗑️ 시험지 삭제", key=f"del_exam_{preview_eid}", use_container_width=True):
                    ok, msg = delete_exam(preview_eid)
                    st.success(msg)
                    st.rerun()

            if path or b64 or url:
                st.markdown("###### [원문 PDF 뷰어 미리보기]")
                render_pdf_viewer(base64_pdf=b64, pdf_url=url, pdf_path=path, initial_page=1, height=600)
            else:
                st.warning(f"'{ex_info['title']}'에는 아직 원문 PDF 파일이 등록되지 않았습니다. 상단 '1단계'에서 PDF 파일 또는 구글 드라이브 링크를 연결해 주세요.")

    # ---------------- 탭 3: 마스터 연동 및 시스템 설정 ----------------
    with tab3:
        st.subheader("⚙️ 마스터 연동 및 시스템 설정")
        st.markdown("""
        이곳에서 저장한 설정은 **수정하기 전까지 영구적으로 저장 및 유지**됩니다.  
        선생님이 여기서 Gemini API 키를 등록해두시면, 학생들은 별도의 키 입력 없이도 즉시 AI 인터뷰를 진행할 수 있습니다.
        """)

        cfg = get_admin_config()
        master_url = cfg.get("google_drive_folder_url", "")
        master_api_key = cfg.get("gemini_api_key", "")
        gas_url = cfg.get("gas_api_url", "")

        with st.form("drive_master_form"):
            st.markdown("##### 🔑 교사용 공용 Gemini API Key")
            st.caption("Google AI Studio에서 발급받은 키를 등록하면 학생 계정 전체에 공용으로 자동 적용됩니다.")
            new_api_key = st.text_input(
                "Gemini API Key",
                value=master_api_key,
                type="password",
                placeholder="AI Studio API 키 입력"
            )

            st.divider()
            st.markdown("##### 📂 구글 드라이브 기출 모의고사 마스터 폴더")
            st.caption("최근 수능 및 평가원 모의고사 전체 PDF가 모인 구글 드라이브 폴더 공유 링크를 입력하세요.")
            new_master_url = st.text_input(
                "구글 드라이브 마스터 폴더 URL",
                value=master_url,
                placeholder="https://drive.google.com/drive/folders/..."
            )
            
            st.divider()
            st.markdown("##### 🌐 교사용 구글 스프레드시트(GAS) 웹앱 URL (선택사항)")
            st.caption("학생 진단 제출 시 실시간으로 기록을 누적할 Google Apps Script 웹앱 URL입니다.")
            new_gas_url = st.text_input(
                "GAS 웹앱 /exec URL",
                value=gas_url,
                placeholder="https://script.google.com/macros/s/..."
            )

            st.divider()
            st.markdown("##### 🔒 관리자 마스터 비밀번호 변경")
            st.caption("관리자 모드 접속 시 사용할 비밀번호입니다. (초기값: `teacher1234`)")
            admin_pw_change = st.text_input(
                "새 관리자 비밀번호 입력 (변경할 경우에만 입력)",
                type="password",
                placeholder="현재 비밀번호 유지 시 공란"
            )

            if st.form_submit_button("💾 관리자 설정 영구 저장하기", type="primary", use_container_width=True):
                cfg["gemini_api_key"] = new_api_key.strip()
                cfg["google_drive_folder_url"] = new_master_url.strip()
                cfg["gas_api_url"] = new_gas_url.strip()
                if admin_pw_change.strip():
                    cfg["admin_password"] = admin_pw_change.strip()
                save_admin_config(cfg)
                st.success("✅ 모든 설정이 파일에 안전하게 저장되었습니다! 다시 수정하기 전까지 영구 유지됩니다.")
                st.rerun()

        st.divider()
        st.markdown("##### 📋 현재 저장된 설정 상태")
        col_st1, col_st2 = st.columns(2)
        with col_st1:
            api_status = "🟢 등록됨 (공용 활성화)" if cfg.get("gemini_api_key") else "⚪ 미등록 (학생 개별 입력 필요)"
            st.write(f"• **교사용 API 키:** {api_status}")
            drive_status = "🟢 연동됨" if cfg.get("google_drive_folder_url") else "⚪ 미등록"
            st.write(f"• **구글 드라이브 폴더:** {drive_status}")
        with col_st2:
            gas_status = "🟢 연동됨" if cfg.get("gas_api_url") else "⚪ 미등록"
            st.write(f"• **구글 스프레드시트(GAS):** {gas_status}")
            st.write("• **관리자 비밀번호:** 🔒 설정됨")

        st.divider()
        with st.expander("💡 AI가 자동으로 탐색·매핑하는 6대 취약점별 기출 문항 풀 (인덱스 확인)"):
            st.markdown("""
            AI는 학생의 진단 결과에 따라 아래와 같이 전체 시험지 PDF에서 적합한 문항과 정확한 PDF 페이지를 실시간으로 인출합니다:
            - **🚨 선지 임의 변형**: 2025학년도 9월 21번(7p), 2024학년도 수능 34번(11p)
            - **🚨 선지 후반부 검증 생략**: 2024학년도 6월 15번(5p), 2023학년도 수능 17번(6p)
            - **🚨 기억 부재의 부재화**: 2024학년도 9월 8번(3p), 2025학년도 6월 12번(4p)
            - **🚨 적용 조건 혼동**: 2025학년도 수능 10번(4p), 2024학년도 9월 14번(5p)
            - **🚨 관계어·논리 왜곡**: 2024학년도 수능 10번(4p), 2023학년도 9월 16번(5p)
            - **🚨 과잉 인과 생성**: 2025학년도 6월 31번(10p), 2024학년도 6월 24번(8p)
            """)

    # ---------------- 탭 4: 학생 진단 제출 현황 ----------------
    with tab4:
        st.subheader("📊 학생 진단 제출 로그")
        subs = get_submissions()
        if subs:
            st.write(f"총 {len(subs)}건의 학생 진단 기록이 보관되어 있습니다.")
            rows = []
            for s in subs:
                rows.append({
                    "제출 일시": s.get("timestamp"),
                    "학번": s.get("student_id"),
                    "이름": s.get("student_name"),
                    "시험명": s.get("exam_title"),
                    "분석 문항 수": len(s.get("diagnosed_items", [])),
                    "주요 감지 취약점": ", ".join(s.get("error_tags", []))
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            with st.expander("🔍 학생별 상세 진단 결과 열람"):
                for idx, s in enumerate(reversed(subs)):
                    st.markdown(f"**[{s.get('timestamp')}] {s.get('student_name')}({s.get('student_id')}) - {s.get('exam_title')}**")
                    for d in s.get("diagnosed_items", []):
                        st.markdown(f"- **{d.get('q_num')}번 ({d.get('status')}):** 오류 태그: `{d.get('error_tag')}` | 행동 원칙: *{d.get('action_rule')}*")
                    st.divider()
        else:
            st.info("아직 제출된 학생 진단 기록이 없습니다.")
