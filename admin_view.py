import streamlit as st
import pandas as pd
from data_manager import (
    get_students, add_student, delete_student, save_students,
    get_admin_config, save_admin_config,
    get_exams, save_exam, get_exam_pdf_base64,
    get_submissions
)
from pdf_viewer import render_pdf_viewer

def render_admin_dashboard():
    st.title("🔒 교사용 관리자 모드")
    st.caption("학생 계정, 시험지 원문 PDF 및 취약점 유형별 구글 드라이브 처방 링크를 관리합니다.")

    tab1, tab2, tab3, tab4 = st.tabs([
        "👥 학생 계정 관리",
        "📄 시험지 및 PDF 업로드",
        "🔗 구글 드라이브 처방 링크",
        "📊 학생 진단 제출 현황"
    ])

    # ---------------- 탭 1: 학생 계정 관리 ----------------
    with tab1:
        st.subheader("👥 학생 계정 설정")
        col_add, col_csv = st.columns(2, gap="medium")
        
        with col_add:
            with st.form("add_student_form", clear_on_submit=True):
                st.markdown("##### ➕ 개별 학생 등록 / 비밀번호 재설정")
                new_sid = st.text_input("학번 (예: 30101)", placeholder="30101")
                new_name = st.text_input("학생 이름", placeholder="김수험")
                new_pw = st.text_input("접속 비밀번호", value="1234")
                submitted = st.form_submit_button("학생 등록 및 저장", type="primary", use_container_width=True)
                if submitted:
                    if new_sid.strip() and new_name.strip() and new_pw.strip():
                        ok, msg = add_student(new_sid.strip(), new_name.strip(), new_pw.strip())
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error("학번, 이름, 비밀번호를 모두 입력해주세요.")

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
        st.caption("업로드된 시험지 PDF는 학생들이 오답 복원 인터뷰를 진행할 때 좌측에 실물 시험지 뷰어로 실시간 제공됩니다.")

        with st.form("exam_upload_form"):
            col_e1, col_e2, col_e3 = st.columns([1.5, 2, 1])
            with col_e1:
                exam_id_input = st.text_input("시험 고유 코드", placeholder="예: 2026_09_mock")
            with col_e2:
                exam_title_input = st.text_input("시험 명칭", placeholder="예: 2026학년도 9월 모의평가 국어영역")
            with col_e3:
                exam_total_q = st.number_input("총 문항 수", min_value=5, max_value=60, value=45)
            
            uploaded_pdf = st.file_uploader("시험지 원문 PDF 파일 선택 (최대 50MB)", type=["pdf"])
            submit_exam = st.form_submit_button("시험지 등록 및 PDF 저장", type="primary", use_container_width=True)

            if submit_exam:
                if not exam_id_input.strip() or not exam_title_input.strip():
                    st.error("시험 코드와 시험 명칭을 모두 입력해 주세요.")
                else:
                    pdf_bytes = uploaded_pdf.read() if uploaded_pdf is not None else None
                    fname = uploaded_pdf.name if uploaded_pdf is not None else None
                    ok, msg = save_exam(
                        exam_id=exam_id_input.strip(),
                        title=exam_title_input.strip(),
                        total_questions=exam_total_q,
                        pdf_bytes=pdf_bytes,
                        filename=fname
                    )
                    st.success(msg)
                    st.rerun()

        st.divider()
        st.markdown("##### 📚 등록된 시험지 목록 및 PDF 미리보기")
        exams = get_exams()
        selected_exam_id = st.selectbox(
            "확인할 시험지 선택",
            options=list(exams.keys()),
            format_func=lambda x: f"{exams[x]['title']} ({exams[x]['total_questions']}문항)"
        )

        if selected_exam_id:
            exam_info = exams[selected_exam_id]
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.write(f"**시험 코드:** `{exam_info['exam_id']}`")
                st.write(f"**총 문항 수:** {exam_info['total_questions']}문항")
            with col_info2:
                pdf_status = "✅ PDF 탑재됨" if exam_info.get("pdf_filename") else "❌ PDF 없음 (텍스트 모드로 동작)"
                st.write(f"**PDF 등록 상태:** {pdf_status}")
                st.write(f"**등록일:** {exam_info.get('created_at', '-')}")

            # PDF 미리보기
            pdf_b64 = get_exam_pdf_base64(selected_exam_id)
            if pdf_b64:
                st.markdown("###### [원문 PDF 뷰어 미리보기]")
                render_pdf_viewer(pdf_b64, initial_page=1, height=600)
            else:
                st.warning("이 시험지에는 아직 원문 PDF 파일이 등록되지 않았습니다. 상단에서 PDF 파일을 업로드해 주세요.")

    # ---------------- 탭 3: 구글 드라이브 기출 PDF 마스터 폴더 설정 ----------------
    with tab3:
        st.subheader("🔗 구글 드라이브 기출 모의고사 마스터 폴더 연동")
        st.markdown("""
        선생님의 구글 드라이브에 보관된 **최근 수능 및 평가원 모의고사 전체 PDF 폴더 링크**를 등록하세요.  
        유형별로 문제지를 따로 쪼개놓지 않으셔도 괜찮습니다.  
        **AI가 학생의 취약점(오류 태그)을 분석하여 해당 폴더 내 시험지 중 가장 적합한 문항과 페이지를 스스로 찾아내어 앱 내 실물 시험지로 즉시 띄워줍니다.**
        """)

        cfg = get_admin_config()
        master_url = cfg.get("google_drive_folder_url", "")

        with st.form("drive_master_form"):
            new_master_url = st.text_input(
                "📂 최근 수능/평가원 기출 PDF 보관 구글 드라이브 마스터 폴더 URL",
                value=master_url,
                placeholder="https://drive.google.com/drive/folders/..."
            )
            
            st.divider()
            gas_url = st.text_input("🌐 교사용 구글 스프레드시트(GAS) 웹앱 URL (선택사항)", value=cfg.get("gas_api_url", ""), placeholder="https://script.google.com/macros/s/...")
            admin_pw_change = st.text_input("🔑 관리자 비밀번호 변경 (변경할 경우에만 입력)", type="password", placeholder="현재 비밀번호 유지 시 공란")

            if st.form_submit_button("마스터 설정 저장하기", type="primary", use_container_width=True):
                cfg["google_drive_folder_url"] = new_master_url.strip()
                cfg["gas_api_url"] = gas_url.strip()
                if admin_pw_change.strip():
                    cfg["admin_password"] = admin_pw_change.strip()
                save_admin_config(cfg)
                st.success("구글 드라이브 마스터 폴더 URL 및 관리자 설정이 저장되었습니다!")
                st.rerun()

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
