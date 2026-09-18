import streamlit as st
import pandas as pd
from data_manager import (
    get_students, add_student, delete_student, save_students,
    get_admin_config, save_admin_config,
    get_exams, save_exam, get_exam_pdf_base64,
    attach_pdf_to_exam, get_exam_pdf_source, delete_exam,
    get_exam_answer_key, save_exam_answer_key, parse_answer_string, extract_answers_from_pdf,
    get_submissions, get_student_vulnerability_profile, get_student_submissions,
    sync_from_google_sheets, push_all_to_google_sheets, get_last_sync_time, get_gas_api_url
)
from pdf_viewer import render_pdf_viewer

def render_admin_dashboard(client=None):
    col_t1, col_t2 = st.columns([3, 1.2])
    with col_t1:
        st.title("🔒 교사용 관리자 모드")
        st.caption("학생 계정, 시험지 원문 PDF 및 취약점 유형별 구글 드라이브 처방 링크를 관리합니다.")
    with col_t2:
        st.write("")
        if st.button("🎓 학생 학습 화면으로 나가기", use_container_width=True):
            st.query_params.clear()
            st.session_state.app_mode = "STUDENT"
            st.rerun()

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

    # ---------------- 탭 2: 시험지 및 PDF 관리 ----------------
    with tab2:
        st.subheader("📄 시험지 등록 및 원문 PDF 관리")
        st.caption("시험지를 선택하여 기본 정보, 원문 PDF(파일/구글 드라이브 링크), 공식 정답표를 한 화면에서 한 번에 설정하고 저장합니다.")

        exams = get_exams()
        NEW_EXAM_OPT = "➕ [새로운 시험지 추가 등록하기]"
        # ⭐️ 시험지 목록을 이름(제목) 순으로 깔끔하게 정렬
        sorted_exam_keys = sorted(list(exams.keys()), key=lambda x: str(exams[x].get("title", "")))
        exam_options = sorted_exam_keys + [NEW_EXAM_OPT]

        if not exams:
            # 등록된 시험지가 하나도 없을 때
            selected_eid = NEW_EXAM_OPT
        else:
            selected_eid = st.selectbox(
                "📋 관리할 시험지를 선택하세요",
                options=exam_options,
                format_func=lambda x: NEW_EXAM_OPT if x == NEW_EXAM_OPT else f"{exams[x]['title']} ({exams[x].get('total_questions', 45)}문항) - {'✅ PDF 연결됨' if (exams[x].get('pdf_filename') or exams[x].get('pdf_url')) else '❌ PDF 없음'}",
                help="시험지를 선택하면 아래에 해당 시험지의 모든 설정(기본정보, PDF, 정답표)이 표시됩니다."
            )

        st.divider()

        # ==========================================
        # CASE A: 새 시험지 등록 화면
        # ==========================================
        if selected_eid == NEW_EXAM_OPT:
            with st.container(border=True):
                st.markdown("#### ➕ 새로운 시험지 등록")
                st.caption("새로운 시험지의 기본 정보와 PDF, 정답표를 입력하고 한 번에 등록하세요.")

                col_e1, col_e2, col_e3 = st.columns([1.5, 2, 1])
                with col_e1:
                    new_eid = st.text_input("새 시험 고유 코드", placeholder="예: 2026_11_suneung", key="new_eid_input")
                with col_e2:
                    new_title = st.text_input("새 시험 명칭", placeholder="예: 2026학년도 대학수학능력시험 국어영역", key="new_title_input")
                with col_e3:
                    new_total_q = st.number_input("총 문항 수", min_value=5, max_value=60, value=45, key="new_tq_input")

                st.markdown("##### 📄 원문 PDF 연결 (파일 업로드 또는 구글 드라이브 링크)")
                col_np1, col_np2 = st.columns(2)
                with col_np1:
                    st.markdown("**방법 A: 내 컴퓨터에서 PDF 파일 업로드**")
                    new_pdf_file = st.file_uploader("PDF 파일 선택", type=["pdf"], key="new_pdf_file_uploader")
                with col_np2:
                    st.markdown("**방법 B: 구글 드라이브 PDF 공유 링크 (강력 추천)**")
                    st.caption("💡 구글 드라이브 링크를 연결해두면 웹 배포가 재시작되어도 파일이 영구 유지됩니다.")
                    new_pdf_url = st.text_input("구글 드라이브 PDF 공유 링크", placeholder="https://drive.google.com/file/d/.../view?usp=sharing", key="new_pdf_url_input")

                st.markdown("##### 🎯 공식 정답표 (선택 사항)")
                st.caption("평가원 정답표 PDF를 업로드하면 AI가 1~45번 정답을 자동으로 판독해 채워줍니다.")

                # 새 시험지 정답표 PDF 업로드 컨테이너
                with st.container(border=True):
                    st.markdown("###### 📄 평가원 공식 정답표 PDF로 자동 채우기")
                    col_nap1, col_nap2 = st.columns([2.5, 1])
                    with col_nap1:
                        new_ans_pdf_file = st.file_uploader("정답표 PDF 파일 선택", type=["pdf"], key="new_exam_ans_pdf_uploader")
                    with col_nap2:
                        st.write("")
                        st.write("")
                        if st.button("⚡ 정답 자동 추출", type="secondary", use_container_width=True, key="btn_extract_new_ans"):
                            if not new_ans_pdf_file:
                                st.warning("정답표 PDF 파일을 먼저 선택해 주세요.")
                            else:
                                with st.spinner("AI가 정답표 PDF를 분석 중입니다..."):
                                    pdf_bytes = new_ans_pdf_file.read()
                                    extracted_dict, msg = extract_answers_from_pdf(pdf_bytes, client=client)
                                    if extracted_dict:
                                        st.session_state["new_extracted_ans"] = extracted_dict
                                        st.toast(msg, icon="✅")
                                        st.rerun()
                                    else:
                                        st.error(msg)

                new_extracted = st.session_state.get("new_extracted_ans", {})
                if new_extracted:
                    st.info(f"💡 정답표 PDF에서 **총 {len(new_extracted)}개 문항 정답**이 추출되었습니다!")
                    new_str_parts = [str(new_extracted.get(i, "")) for i in range(1, new_total_q + 1)]
                    new_preview_str = " ".join(["".join(new_str_parts[j:j+5]) for j in range(0, new_total_q, 5)]).strip()
                else:
                    new_preview_str = ""

                new_ans_str = st.text_area(
                    "1번~45번 정답 빠른 붙여넣기 (1부터 5까지 숫자)",
                    value=new_preview_str,
                    placeholder="예: 11423 53423 25415 35413 24153 24253 41523 41523 41523",
                    key="new_ans_str_input"
                )

                st.write("")
                if st.button("➕ 새 시험지 저장 및 등록", type="primary", use_container_width=True, key="btn_create_new_exam"):
                    eid_c = (new_eid or "").strip()
                    title_c = (new_title or "").strip()
                    if not eid_c or not title_c:
                        st.error("시험 고유 코드와 시험 명칭을 모두 입력해 주세요.")
                    else:
                        pdf_bytes = new_pdf_file.read() if new_pdf_file is not None else None
                        fname = new_pdf_file.name if new_pdf_file is not None else None
                        parsed_ans = parse_answer_string(new_ans_str) if new_ans_str.strip() else new_extracted

                        ok, msg = save_exam(
                            exam_id=eid_c,
                            title=title_c,
                            total_questions=new_total_q,
                            pdf_bytes=pdf_bytes,
                            filename=fname,
                            pdf_url=new_pdf_url.strip(),
                            answer_key=parsed_ans
                        )
                        st.session_state.pop("new_extracted_ans", None)
                        st.success(f"✅ '{title_c}' 시험지가 성공적으로 등록되었습니다!")
                        st.rerun()

        # ==========================================
        # CASE B: 선택된 기존 시험지 상세 설정 화면
        # ==========================================
        else:
            cur_exam = exams[selected_eid]
            cur_key = get_exam_answer_key(selected_eid)
            path, b64, url = get_exam_pdf_source(selected_eid)
            has_pdf = bool(path or b64 or url)
            total_q = cur_exam.get("total_questions", 45)
            ans_count = len(cur_key)

            with st.container(border=True):
                # 1. 헤더 및 상태 뱃지
                col_h1, col_h2 = st.columns([3, 1.5])
                with col_h1:
                    st.markdown(f"#### ⚙️ [{cur_exam['title']}] 상세 설정")
                    st.caption(f"시험 코드: `{cur_exam['exam_id']}` | 등록일: {cur_exam.get('created_at', '-')}")
                with col_h2:
                    pdf_badge = "🟢 PDF 연결됨" if has_pdf else "🔴 PDF 없음"
                    ans_badge = f"🟢 정답표 ({ans_count}/{total_q})" if ans_count >= total_q else (f"🟡 정답표 일부 ({ans_count}/{total_q})" if ans_count > 0 else "🔴 정답표 미등록")
                    st.markdown(f"<div style='text-align: right; padding-top: 5px;'><b>상태:</b> {pdf_badge} | {ans_badge}</div>", unsafe_allow_html=True)

                st.divider()

                # 2. 기본 정보 설정
                st.markdown("##### 1️⃣ 기본 정보")
                col_i1, col_i2 = st.columns([3, 1])
                with col_i1:
                    edit_title = st.text_input("시험 명칭", value=cur_exam.get("title", ""), key=f"title_{selected_eid}")
                with col_i2:
                    edit_total_q = st.number_input("총 문항 수", min_value=5, max_value=60, value=total_q, key=f"tq_{selected_eid}")

                st.divider()

                # 3. 원문 PDF 연결 설정
                st.markdown("##### 2️⃣ 원문 PDF 연결")
                if has_pdf:
                    src_desc = f"구글 드라이브 링크 연결됨 (`{cur_exam.get('pdf_url')}`)" if cur_exam.get('pdf_url') else f"로컬 파일 저장됨 (`{cur_exam.get('pdf_filename')}`)"
                    st.success(f"현재 PDF 상태: **{src_desc}**")
                else:
                    st.warning("현재 연결된 원문 PDF가 없습니다. 아래에서 PDF 파일을 올리거나 구글 드라이브 링크를 넣어주세요.")

                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    st.markdown("**방법 A: 내 컴퓨터에서 PDF 파일 업로드**")
                    st.caption("기존 PDF를 교체하려면 새 파일을 선택하세요.")
                    edit_pdf_file = st.file_uploader(f"새 PDF 파일 선택", type=["pdf"], key=f"pdf_file_{selected_eid}")
                with col_p2:
                    st.markdown("**방법 B: 구글 드라이브 PDF 공유 링크 (추천)**")
                    st.caption("💡 웹 서버가 재시작되어도 링크가 영구 보존됩니다.")
                    edit_pdf_url = st.text_input("구글 드라이브 PDF 공유 링크", value=cur_exam.get("pdf_url", ""), placeholder="https://drive.google.com/file/d/.../view?usp=sharing", key=f"pdf_url_{selected_eid}")

                st.divider()

                # 4. 공식 정답표 (Answer Key) 설정
                st.markdown("##### 3️⃣ 공식 정답표 (Answer Key)")
                st.caption("공식 정답표를 넣어두면 학생의 OMR 채점 및 메타인지 4대 매트릭스(확신정답, 불안정답, 오답, 찍음)가 자동 판정됩니다.")

                # ⭐️ 정답표 PDF 파일 업로드로 자동 채우기
                with st.container(border=True):
                    st.markdown("###### 📄 평가원 공식 정답표 PDF로 자동 채우기")
                    st.caption("평가원 정답표 PDF 파일을 올리고 [⚡ 정답 자동 추출] 버튼을 누르면 AI가 1~45번 정답 번호를 자동으로 판독해 채워줍니다.")
                    col_ap1, col_ap2 = st.columns([2.5, 1])
                    with col_ap1:
                        ans_pdf_file = st.file_uploader(
                            "공식 정답표 PDF 파일 선택",
                            type=["pdf"],
                            key=f"ans_pdf_upload_{selected_eid}"
                        )
                    with col_ap2:
                        st.write("")
                        st.write("")
                        if st.button("⚡ 정답 자동 추출", type="secondary", use_container_width=True, key=f"btn_extract_ans_{selected_eid}"):
                            if not ans_pdf_file:
                                st.warning("정답표 PDF 파일을 먼저 선택해 주세요.")
                            else:
                                with st.spinner("AI가 정답표 PDF를 분석하여 1~45번 정답을 판독 중입니다..."):
                                    pdf_bytes = ans_pdf_file.read()
                                    extracted_dict, msg = extract_answers_from_pdf(pdf_bytes, client=client)
                                    if extracted_dict:
                                        st.session_state[f"extracted_ans_{selected_eid}"] = extracted_dict
                                        st.toast(msg, icon="✅")
                                        st.rerun()
                                    else:
                                        st.error(msg)

                # 세션에 방금 추출된 정답이 있다면 그것을 우선 사용
                extracted_for_cur = st.session_state.get(f"extracted_ans_{selected_eid}")
                if extracted_for_cur:
                    cur_key_to_show = extracted_for_cur
                    st.info(f"💡 정답표 PDF에서 **총 {len(extracted_for_cur)}개 문항의 정답이 자동 추출**되었습니다! 아래 텍스트와 상세 확인 표를 검토하신 후 맨 아래 **[💾 이 시험지 설정 저장하기]**를 눌러 저장해 주세요.")
                else:
                    cur_key_to_show = cur_key

                cur_str_parts = []
                for i in range(1, edit_total_q + 1):
                    cur_str_parts.append(str(cur_key_to_show.get(i, "")))
                preview_raw_str = " ".join([
                    "".join(cur_str_parts[j:j+5]) for j in range(0, edit_total_q, 5)
                ]).strip()

                edit_raw_answers = st.text_area(
                    "1번~45번 정답 빠른 붙여넣기 (공백/줄바꿈 무관, 1부터 5까지 숫자)",
                    value=preview_raw_str,
                    placeholder="예: 11423 53423 25415 35413 24153 24253 41523 41523 41523",
                    key=f"ans_text_{selected_eid}",
                    help="평가원 정답표의 숫자들을 복사해 넣으면 공백이나 엔터를 자동 제거하고 1~45번 정답으로 저장합니다."
                )

                if cur_key_to_show:
                    with st.expander(f"👀 현재 등록(추출)된 1~{edit_total_q}번 정답표 상세 확인 ({len(cur_key_to_show)}문항 등록됨)"):
                        cols_grid = st.columns(5)
                        for col_idx in range(5):
                            with cols_grid[col_idx]:
                                start_q = col_idx * 9 + 1
                                end_q = min(start_q + 9, edit_total_q + 1)
                                grid_lines = []
                                for qn in range(start_q, end_q):
                                    ans_val = cur_key_to_show.get(qn, "-")
                                    grid_lines.append(f"**{qn}번:** `{ans_val}번`")
                                st.markdown("<br>".join(grid_lines), unsafe_allow_html=True)

                # 5. 원문 PDF 뷰어 미리보기 아코디언
                if has_pdf:
                    with st.expander("📄 [미리보기] 등록된 실물 시험지 PDF 원문 열람"):
                        render_pdf_viewer(base64_pdf=b64, pdf_url=url, pdf_path=path, initial_page=1, height=550)

                st.divider()

                # 6. 저장 및 삭제 버튼
                col_save, col_del = st.columns([3, 1])
                with col_save:
                    if st.button("💾 이 시험지 설정 저장하기", type="primary", use_container_width=True, key=f"btn_save_{selected_eid}"):
                        pdf_bytes = edit_pdf_file.read() if edit_pdf_file is not None else None
                        fname = edit_pdf_file.name if edit_pdf_file is not None else None

                        if edit_raw_answers.strip():
                            parsed_answers = parse_answer_string(edit_raw_answers)
                        else:
                            parsed_answers = cur_key_to_show

                        ok, msg = save_exam(
                            exam_id=selected_eid,
                            title=edit_title.strip() or cur_exam["title"],
                            total_questions=edit_total_q,
                            pdf_bytes=pdf_bytes,
                            filename=fname,
                            pdf_url=edit_pdf_url.strip(),
                            answer_key=parsed_answers
                        )
                        st.session_state.pop(f"extracted_ans_{selected_eid}", None)
                        st.success(f"✅ '{edit_title}' 시험지 설정(기본정보, PDF, 정답표)이 모두 성공적으로 저장되었습니다!")
                        st.rerun()

                with col_del:
                    if st.button("🗑️ 시험지 삭제", key=f"btn_del_{selected_eid}", use_container_width=True):
                        ok, msg = delete_exam(selected_eid)
                        st.success(msg)
                        st.rerun()

    # ---------------- 탭 3: 마스터 연동 및 시스템 설정 ----------------
    with tab3:
        st.subheader("⚙️ 마스터 연동 및 시스템 설정")
        st.markdown("""
        선생님의 **구글 드라이브 및 구글 스프레드시트(Google Apps Script)**와 연동하여 시험지 목록, 학생 계정, 관리자 설정, 진단 기록을 **클라우드에 영구 보존**합니다.  
        Streamlit Cloud 서버가 재시작되거나 새로고침되어도 구글 시트로부터 데이터가 100% 자동 복원됩니다.
        """)

        # 1. 클라우드 동기화 제어 패널
        st.markdown("##### ☁️ 구글 시트 실시간 클라우드 동기화")
        cfg = get_admin_config()
        gas_url = get_gas_api_url()
        last_sync = get_last_sync_time()

        col_sync1, col_sync2, col_sync3 = st.columns([1.5, 1.5, 2])
        with col_sync1:
            if st.button("🔄 구글 시트에서 최신 데이터 불러오기", use_container_width=True, type="primary"):
                with st.spinner("구글 스프레드시트와 동기화 중..."):
                    ok, msg = sync_from_google_sheets(force=True)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        with col_sync2:
            if st.button("☁️ 현재 로컬 데이터를 구글 시트로 백업", use_container_width=True):
                with st.spinner("구글 스프레드시트로 전체 백업 전송 중..."):
                    ok, msg = push_all_to_google_sheets()
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
        with col_sync3:
            if gas_url:
                sync_caption = f"🟢 **구글 시트 연동 활성화됨**"
                if last_sync:
                    sync_caption += f" (최근 동기화: {last_sync})"
                st.caption(sync_caption)
            else:
                st.caption("⚪ **구글 시트 미연동** (아래 폼에 GAS URL을 등록해 주세요)")

        st.divider()

        # 2. 마스터 설정 폼
        master_url = cfg.get("google_drive_folder_url", "")
        master_api_key = cfg.get("gemini_api_key", "")

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
            st.markdown("##### 🌐 교사용 구글 스프레드시트(GAS) 웹앱 URL (강력 권장 - 영구 보존용)")
            st.caption("시험지, 학생 계정, 제출 기록을 영구히 저장할 Google Apps Script 웹앱 URL입니다. (예: `https://script.google.com/macros/s/.../exec`)")
            new_gas_url = st.text_input(
                "GAS 웹앱 /exec URL",
                value=gas_url,
                placeholder="https://script.google.com/macros/s/.../exec"
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
                st.success("✅ 모든 설정이 저장되고 구글 시트와 동기화되었습니다!")
                st.rerun()

        st.divider()

        # 3. Google Apps Script 1분 설치 가이드 Expander
        with st.expander("📖 구글 스프레드시트 1분 연동 코드 및 설치 방법 (클릭하여 열기)"):
            st.markdown("""
            ### 🛠️ 1분 만에 내 구글 시트에 연동하는 법
            1. 새 [구글 스프레드시트](https://sheets.new)를 만듭니다. (이름: `수능 국어 사고 복원 클리닉 DB`)
            2. 상단 메뉴 **[확장 프로그램] ➔ [Apps Script]**를 클릭합니다.
            3. 열린 편집기의 `Code.gs` 내용을 모두 지우고, **아래 코드를 복사해서 붙여넣기**한 뒤 저장(`Ctrl + S`)합니다.
            4. 상단 실행 함수 드롭다운에서 **`setup`**을 선택하고 **[실행]**을 누릅니다. (첫 실행 시 계정 권한 승인 팝업 진행)
            5. 우측 상단 **[배포] ➔ [새 배포]**를 클릭합니다:
               - 종류: **웹 앱 (Web app)**
               - 다음 사용자 권한으로 실행: **나 (내 계정)**
               - 액세스 권한: **모든 사용자 (Anyone)** *(중요!)*
            6. 배포 완료 후 나타나는 **웹 앱 URL (`https://script.google.com/.../exec`)**을 복사하여 위 [GAS 웹앱 URL] 칸에 입력하고 저장하면 끝납니다!
            
            > **💡 Streamlit Cloud 영구 보존 팁:**  
            > Streamlit Cloud 대시보드 ➔ 해당 앱의 `Settings` ➔ `Secrets`에 아래와 같이 한 줄 넣어두시면, 서버가 재배포되어도 URL이 절대 초기화되지 않습니다:  
            > ```toml
            > GAS_API_URL = "https://script.google.com/macros/s/.../exec"
            > ```
            """)
            
            # Code.gs 코드 내용 읽어서 표시
            try:
                gas_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gas", "Code.gs")
                if os.path.exists(gas_file_path):
                    with open(gas_file_path, "r", encoding="utf-8") as gf:
                        code_content = gf.read()
                    st.code(code_content, language="javascript")
            except Exception:
                pass

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

            st.divider()
            st.markdown("##### 🎓 개별 학생 누적 취약점 및 행동 원칙 심층 조회")
            student_list = get_students()
            if student_list:
                sel_stu_label = st.selectbox(
                    "조회할 학생 선택",
                    options=[f"{s['student_id']} - {s['name']}" for s in student_list],
                    key="admin_sel_student_profile"
                )
                sel_sid = sel_stu_label.split(" - ")[0]
                prof = get_student_vulnerability_profile(sel_sid)

                if prof["has_history"]:
                    ap1, ap2, ap3 = st.columns(3)
                    with ap1:
                        st.metric("총 진단 시험", f"{prof['total_submissions']}회")
                    with ap2:
                        st.metric("분석된 취약 문항", f"{prof['total_questions']}개")
                    with ap3:
                        top_t = prof['top_vulnerabilities'][0][0] if prof['top_vulnerabilities'] else "없음"
                        top_c = prof['top_vulnerabilities'][0][1] if prof['top_vulnerabilities'] else 0
                        st.metric("주요 취약점 1위", top_t, f"{top_c}회")

                    st.markdown("**📌 이 학생의 취약점 분포:**")
                    top_tags_line = " | ".join([f"**{t[0]}** ({t[1]}회)" for t in prof["top_vulnerabilities"]])
                    st.write(top_tags_line)

                    with st.expander(f"📖 {sel_stu_label} 학생이 수립한 행동 원칙 ({len(prof['action_rules'])}개)"):
                        for r in prof["action_rules"]:
                            st.markdown(f"- **[{r['exam_title']} {r['q_num']}번 ({r['error_tag']})]:** *\"{r['action_rule']}\"*")
                else:
                    st.info(f"선택한 학생({sel_stu_label})의 제출된 진단 기록이 아직 없습니다.")

            st.divider()
            with st.expander("🔍 전체 제출 건별 상세 진단 결과 열람"):
                for idx, s in enumerate(reversed(subs)):
                    st.markdown(f"**[{s.get('timestamp')}] {s.get('student_name')}({s.get('student_id')}) - {s.get('exam_title')}**")
                    for d in s.get("diagnosed_items", []):
                        st.markdown(f"- **{d.get('q_num')}번 ({d.get('status')}):** 오류 태그: `{d.get('error_tag')}` | 행동 원칙: *{d.get('action_rule')}*")
                    st.divider()
        else:
            st.info("아직 제출된 학생 진단 기록이 없습니다.")
