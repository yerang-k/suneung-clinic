import os
import streamlit as st
import pandas as pd
from data_manager import (
    get_students, add_student, delete_student, save_students,
    get_admin_config, save_admin_config,
    get_exams, save_exam, get_exam_pdf_base64, get_sorted_exam_keys,
    attach_pdf_to_exam, get_exam_pdf_source, delete_exam,
    get_exam_answer_key, save_exam_answer_key, parse_answer_string, extract_answers_from_pdf,
    download_pdf_from_drive_or_url, extract_answers_from_drive_or_url,
    get_submissions, get_student_vulnerability_profile, get_student_submissions,
    sync_from_google_sheets, push_all_to_google_sheets, get_last_sync_time, get_gas_api_url,
    list_drive_folder_pdfs, extract_elective_answers_from_pdf, ELECTIVE_SUBJECTS, ELECTIVE_START_DEFAULT
)
try:
    from pdf_viewer import render_pdf_viewer
except Exception:
    def render_pdf_viewer(*args, **kwargs):
        st.info("📄 실물 시험지는 상단 원문 링크를 통해 새 창에서 확인하실 수 있습니다.")

def render_drive_folder_pdf_picker(target_session_key: str, picker_id: str, master_folder_url: str, drive_sa_json: str):
    """
    구글 드라이브 마스터 폴더 안의 PDF 목록을 불러와 선택하면,
    target_session_key(해당 링크 입력창의 key)에 선택한 파일의 공유 링크를 자동으로 채워 넣습니다.
    매번 드라이브에서 링크를 복사해 붙여넣는 수고를 없애기 위한 기능입니다.
    """
    cache_key = f"_drive_pdf_cache_{picker_id}"

    col_load, col_refresh = st.columns([3, 1])
    with col_load:
        do_load = st.button("📂 마스터 폴더에서 PDF 목록 불러오기", key=f"btn_load_{picker_id}", use_container_width=True)
    with col_refresh:
        do_refresh = st.button("🔄 새로고침", key=f"btn_refresh_{picker_id}", use_container_width=True)

    if do_load or do_refresh:
        if not master_folder_url or not drive_sa_json:
            st.warning("먼저 [⚙️ 마스터 연동 및 시스템 설정] 탭에서 '구글 드라이브 마스터 폴더 URL'과 '구글 드라이브 서비스 계정 키'를 등록해 주세요.")
        else:
            with st.spinner("구글 드라이브 폴더(하위 폴더 포함)를 탐색하는 중..."):
                files, err = list_drive_folder_pdfs(master_folder_url, drive_sa_json)
                st.session_state[cache_key] = files
                if err and not files:
                    st.error(err)
                elif err:
                    st.warning(err)
                elif files:
                    st.success(f"PDF {len(files)}개를 찾았습니다. 아래에서 선택해 주세요.")

    files = st.session_state.get(cache_key)
    if files:
        options = [f"{f['path']}{f['name']}" for f in files]
        sel_key = f"sel_{picker_id}"
        st.selectbox(f"불러온 PDF 중 선택 ({len(files)}개)", options=options, key=sel_key)

        msg_key = f"_picked_msg_{picker_id}"

        def _apply_drive_pick(target_key=target_session_key, cache_k=cache_key, sk=sel_key, mk=msg_key):
            # ⭐️ target_key로 지정된 위젯(예: pdf_url_xxx)이 이미 이번 스크립트 실행에서
            # 인스턴스화된 뒤에는 session_state[target_key]를 직접 대입할 수 없다
            # (StreamlitWidgetAlreadyInstantiatedError). 버튼의 on_click 콜백은 다음 스크립트
            # 실행이 시작되기 전에 먼저 실행되므로, 여기서 대입해야 안전하다.
            cur_files = st.session_state.get(cache_k) or []
            cur_opts = [f"{f['path']}{f['name']}" for f in cur_files]
            cur_sel = st.session_state.get(sk)
            if cur_sel in cur_opts:
                chosen = cur_files[cur_opts.index(cur_sel)]
                st.session_state[target_key] = chosen["link"]
                st.session_state[mk] = f"'{chosen['name']}' 파일 링크가 채워졌습니다. 아래 저장 버튼을 눌러 반영하세요."

        st.button(
            "✅ 이 파일로 연결하기",
            key=f"btn_pick_{picker_id}",
            type="primary",
            use_container_width=True,
            on_click=_apply_drive_pick
        )

    msg_key = f"_picked_msg_{picker_id}"
    if st.session_state.get(msg_key):
        st.success(f"✅ {st.session_state.pop(msg_key)}")

def _format_answers(answer_dict: dict, start: int, end: int) -> str:
    """{문항번호: 정답}을 start~end번 순서의 '11423 53423' 형태(5개씩 공백 구분) 문자열로 변환"""
    digits = [str(answer_dict.get(q, "")) for q in range(start, end + 1)]
    return " ".join("".join(digits[i:i + 5]) for i in range(0, len(digits), 5)).strip()

def render_answer_key_editor(prefix: str, total_q: int, cur_common_key: dict, cur_elective_enabled: bool,
                              cur_elective_keys: dict, cur_ans_pdf_url: str, master_folder_url: str,
                              drive_sa_json: str, client):
    """
    공식 정답표 입력 UI(선택과목 구분 포함)를 렌더링합니다.
    국어영역은 1~34번 공통 + 35~45번 선택과목(화법과 작문/언어와 매체)으로 나뉘는데,
    정답표 PDF에는 두 선택과목의 35~45번이 함께 두 벌 인쇄되어 있어 AI가 하나의
    평면 정답표로는 정확히 구분하지 못하므로, 체크박스로 켜면 세 칸(공통/화작/언매)으로 나눠 입력한다.

    반환: (ans_pdf_file, ans_pdf_url, elective_enabled, common_answer_key, elective_answer_keys)
    """
    st.markdown("###### 📄 평가원 공식 정답표 PDF 연동 및 자동 채우기")
    col_ap1, col_ap2 = st.columns(2)
    with col_ap1:
        st.markdown("**방법 A: 내 컴퓨터에서 정답표 PDF 업로드**")
        ans_pdf_file = st.file_uploader("정답표 PDF 파일 선택", type=["pdf"], key=f"{prefix}_ans_pdf_uploader")
    with col_ap2:
        st.markdown("**방법 B: 구글 드라이브 정답표 PDF 공유 링크 (강력 추천)**")
        st.caption("💡 구글 드라이브 링크를 연결해두면 배포 서버가 재시작되어도 정답표가 영구 보존됩니다.")
        ans_pdf_url_key = f"{prefix}_ans_pdf_url_input"
        ans_pdf_url = st.text_input(
            "정답표 구글 드라이브 링크",
            value=cur_ans_pdf_url,
            placeholder="https://drive.google.com/file/d/.../view?usp=sharing",
            key=ans_pdf_url_key
        )

    with st.expander("**방법 C: 마스터 폴더에서 바로 선택**"):
        render_drive_folder_pdf_picker(ans_pdf_url_key, f"{prefix}_ans", master_folder_url, drive_sa_json)
    ans_pdf_url = st.session_state.get(ans_pdf_url_key, ans_pdf_url)

    st.divider()
    elective_enabled = st.checkbox(
        "🔀 선택과목 있음 (35~45번이 화법과 작문 / 언어와 매체로 나뉨)",
        value=cur_elective_enabled,
        key=f"{prefix}_elective_enabled",
        help="정답표 안에 35~45번 정답이 화법과 작문 / 언어와 매체 두 벌로 함께 인쇄되어 있는 국어영역 시험이면 체크하세요."
    )

    elective_start = ELECTIVE_START_DEFAULT
    common_end = elective_start - 1
    subj_a, subj_b = ELECTIVE_SUBJECTS

    extracted_common_key = f"{prefix}_extracted_common"
    extracted_a_key = f"{prefix}_extracted_subj_a"
    extracted_b_key = f"{prefix}_extracted_subj_b"

    col_abtn1, col_abtn2 = st.columns([2, 1])
    with col_abtn1:
        if st.button("⚡ 정답 자동 추출 (AI 판독)", type="secondary", use_container_width=True, key=f"{prefix}_btn_extract_ans"):
            target_bytes = None
            if ans_pdf_file is not None:
                target_bytes = ans_pdf_file.read()
            elif ans_pdf_url.strip():
                with st.spinner("구글 드라이브에서 정답표 PDF를 내려받는 중입니다..."):
                    target_bytes, dl_err = download_pdf_from_drive_or_url(ans_pdf_url.strip())
                    if not target_bytes:
                        st.error(dl_err)
            else:
                st.warning("정답표 PDF 파일을 올리거나 구글 드라이브 링크를 입력해 주세요.")

            if target_bytes:
                if elective_enabled:
                    with st.spinner("AI가 공통·선택과목 정답을 구분하여 분석 중입니다..."):
                        common_dict, elective_dict, msg = extract_elective_answers_from_pdf(
                            target_bytes, client=client, elective_start=elective_start, total_questions=total_q
                        )
                        if common_dict or elective_dict[subj_a] or elective_dict[subj_b]:
                            st.session_state[extracted_common_key] = common_dict
                            st.session_state[extracted_a_key] = elective_dict[subj_a]
                            st.session_state[extracted_b_key] = elective_dict[subj_b]
                            st.session_state[f"{prefix}_extract_msg"] = msg
                            # 텍스트 칸은 이전 입력값을 기억하므로, 추출값을 직접 채워 넣는다
                            # (아직 이번 실행에서 렌더링되기 전이라 대입 가능)
                            st.session_state[f"{prefix}_common_ans_str_True"] = _format_answers(common_dict, 1, common_end)
                            st.session_state[f"{prefix}_elective_ans_str_{subj_a}"] = _format_answers(elective_dict[subj_a], elective_start, total_q)
                            st.session_state[f"{prefix}_elective_ans_str_{subj_b}"] = _format_answers(elective_dict[subj_b], elective_start, total_q)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    with st.spinner("AI가 정답표 PDF를 분석 중입니다..."):
                        extracted_dict, msg = extract_answers_from_pdf(target_bytes, client=client)
                        if extracted_dict:
                            st.session_state[extracted_common_key] = extracted_dict
                            st.session_state[f"{prefix}_common_ans_str_False"] = _format_answers(extracted_dict, 1, total_q)
                            st.toast(msg, icon="✅")
                            st.rerun()
                        else:
                            st.error(msg)
    with col_abtn2:
        if ans_pdf_url.strip():
            st.link_button("🔗 정답표 열기 ↗", ans_pdf_url.strip(), use_container_width=True)

    extract_msg = st.session_state.get(f"{prefix}_extract_msg")
    if extract_msg:
        if "일부만" in extract_msg:
            st.warning(extract_msg)
        else:
            st.success(extract_msg)

    extracted_common = st.session_state.get(extracted_common_key) or cur_common_key or {}
    common_upper = common_end if elective_enabled else total_q
    if extracted_common:
        common_parts = [str(extracted_common.get(i, "")) for i in range(1, common_upper + 1)]
        common_preview = " ".join(["".join(common_parts[j:j + 5]) for j in range(0, common_upper, 5)]).strip()
    else:
        common_preview = ""

    common_label = f"1번~{common_end}번 공통 정답 빠른 붙여넣기" if elective_enabled else "1번~45번 정답 빠른 붙여넣기 (1부터 5까지 숫자)"
    # 선택과목 on/off를 전환하면 위젯 key를 바꿔, 이전 모드에서 남은 미리보기 값이
    # 새 문항 범위에 안 맞게 그대로 유지되는 것을 방지한다.
    common_key = f"{prefix}_common_ans_str_{elective_enabled}"
    common_str = st.text_area(
        common_label,
        **({} if common_key in st.session_state else {"value": common_preview}),
        placeholder="예: 11423 53423 25415 35413 24153",
        key=common_key
    )
    common_answer_key = parse_answer_string(common_str) if common_str.strip() else extracted_common
    if elective_enabled:
        common_answer_key = {q: a for q, a in common_answer_key.items() if q <= common_end}

    elective_answer_keys = {}
    if elective_enabled:
        if extracted_common or common_str.strip():
            with st.expander(f"👀 공통 1~{common_end}번 정답표 확인"):
                st.write(", ".join(f"{q}번:{a}" for q, a in sorted(common_answer_key.items())) or "등록된 정답 없음")

        col_e1, col_e2 = st.columns(2)
        for subj, col, ex_key in [(subj_a, col_e1, extracted_a_key), (subj_b, col_e2, extracted_b_key)]:
            with col:
                extracted_subj = st.session_state.get(ex_key) or cur_elective_keys.get(subj) or {}
                if extracted_subj:
                    subj_parts = [str(extracted_subj.get(i, "")) for i in range(elective_start, total_q + 1)]
                    subj_preview = " ".join(["".join(subj_parts[j:j + 5]) for j in range(0, len(subj_parts), 5)]).strip()
                else:
                    subj_preview = ""
                subj_key = f"{prefix}_elective_ans_str_{subj}"
                subj_str = st.text_area(
                    f"{elective_start}번~{total_q}번 '{subj}' 정답",
                    **({} if subj_key in st.session_state else {"value": subj_preview}),
                    placeholder="예: 24153",
                    key=subj_key
                )
                if subj_str.strip():
                    raw = parse_answer_string(subj_str)
                    # parse_answer_string은 1번부터 채번하므로 elective_start만큼 보정
                    elective_answer_keys[subj] = {elective_start + (q - 1): a for q, a in raw.items()}
                else:
                    elective_answer_keys[subj] = extracted_subj

    return ans_pdf_file, ans_pdf_url, elective_enabled, common_answer_key, elective_answer_keys

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

        tab2_cfg = get_admin_config()
        master_folder_url = tab2_cfg.get("google_drive_folder_url", "")
        drive_sa_json = tab2_cfg.get("drive_service_account_json", "")

        exams = get_exams()
        NEW_EXAM_OPT = "➕ [새로운 시험지 추가 등록하기]"
        # ⭐️ 시험지 목록을 최신순(최근 연도 및 시험 시기 우선)으로 정렬
        sorted_exam_keys = get_sorted_exam_keys(exams, reverse=True)
        exam_options = sorted_exam_keys + [NEW_EXAM_OPT]

        if not exams:
            # 등록된 시험지가 하나도 없을 때
            selected_eid = NEW_EXAM_OPT
        else:
            selected_eid = st.selectbox(
                "📋 관리할 시험지를 선택하세요",
                options=exam_options,
                format_func=lambda x: NEW_EXAM_OPT if x == NEW_EXAM_OPT else f"{exams[x]['title']} ({exams[x].get('total_questions', 45)}문항) - {'✅ PDF 연결됨' if (exams[x].get('pdf_filename') or exams[x].get('pdf_url')) else '❌ PDF 없음'}{' | 🔗 정답표 연동' if exams[x].get('answer_pdf_url') else ''}",
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

                with st.expander("**방법 C: 마스터 폴더에서 바로 선택 (링크 복사·붙여넣기 없이)**"):
                    render_drive_folder_pdf_picker("new_pdf_url_input", "new_exam_main", master_folder_url, drive_sa_json)

                st.markdown("##### 🎯 공식 정답표 (선택 사항)")
                st.caption("평가원 정답표 PDF(파일 업로드 또는 구글 드라이브 링크)를 제공하면 AI가 정답을 자동으로 판독해 채워줍니다.")

                # 새 시험지 정답표 PDF 업로드 및 구글 드라이브 연동 컨테이너
                with st.container(border=True):
                    new_ans_pdf_file, new_ans_pdf_url, new_elective_enabled, new_common_answer, new_elective_answers = render_answer_key_editor(
                        prefix="new",
                        total_q=new_total_q,
                        cur_common_key={},
                        cur_elective_enabled=False,
                        cur_elective_keys={},
                        cur_ans_pdf_url="",
                        master_folder_url=master_folder_url,
                        drive_sa_json=drive_sa_json,
                        client=client
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

                        ok, msg = save_exam(
                            exam_id=eid_c,
                            title=title_c,
                            total_questions=new_total_q,
                            pdf_bytes=pdf_bytes,
                            filename=fname,
                            pdf_url=new_pdf_url.strip(),
                            answer_pdf_url=new_ans_pdf_url.strip(),
                            answer_key=new_common_answer,
                            elective_enabled=new_elective_enabled,
                            elective_answer_keys=new_elective_answers
                        )
                        for k in ["new_extracted_common", "new_extracted_subj_a", "new_extracted_subj_b"]:
                            st.session_state.pop(k, None)
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
                    has_ans_drive = bool(cur_exam.get("answer_pdf_url"))
                    ans_drive_badge = " (🔗 드라이브)" if has_ans_drive else ""
                    ans_badge = f"🟢 정답표 ({ans_count}/{total_q}){ans_drive_badge}" if ans_count >= total_q else (f"🟡 정답표 일부 ({ans_count}/{total_q}){ans_drive_badge}" if ans_count > 0 else f"🔴 정답표 미등록{ans_drive_badge}")
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

                with st.expander("**방법 C: 마스터 폴더에서 바로 선택 (링크 복사·붙여넣기 없이)**"):
                    render_drive_folder_pdf_picker(f"pdf_url_{selected_eid}", f"exist_main_{selected_eid}", master_folder_url, drive_sa_json)

                st.divider()

                # 4. 공식 정답표 (Answer Key) 설정
                st.markdown("##### 3️⃣ 공식 정답표 (Answer Key)")
                st.caption("공식 정답표를 넣어두면 학생의 OMR 채점 및 메타인지 5대 매트릭스가 자동 판정됩니다.")

                # ⭐️ 정답표 PDF 파일 업로드 및 구글 드라이브 연동으로 자동 채우기
                with st.container(border=True):
                    (edit_ans_pdf_file, edit_ans_pdf_url, edit_elective_enabled,
                     edit_common_answer, edit_elective_answers) = render_answer_key_editor(
                        prefix=f"exist_{selected_eid}",
                        total_q=edit_total_q,
                        cur_common_key=cur_key,
                        cur_elective_enabled=cur_exam.get("elective_enabled", False),
                        cur_elective_keys=cur_exam.get("elective_answer_keys", {}),
                        cur_ans_pdf_url=cur_exam.get("answer_pdf_url", ""),
                        master_folder_url=master_folder_url,
                        drive_sa_json=drive_sa_json,
                        client=client
                    )

                if edit_common_answer or (edit_elective_enabled and any(edit_elective_answers.values())):
                    common_upper = (ELECTIVE_START_DEFAULT - 1) if edit_elective_enabled else edit_total_q
                    with st.expander(f"👀 현재 등록(추출)된 정답표 상세 확인"):
                        st.markdown(f"**공통 1~{common_upper}번**" if edit_elective_enabled else "**전체 문항**")
                        cols_grid = st.columns(5)
                        q_list = list(range(1, common_upper + 1))
                        per_col = max(1, -(-len(q_list) // 5))
                        for col_idx in range(5):
                            with cols_grid[col_idx]:
                                chunk = q_list[col_idx * per_col: (col_idx + 1) * per_col]
                                grid_lines = [f"**{qn}번:** `{edit_common_answer.get(qn, '-')}번`" for qn in chunk]
                                st.markdown("<br>".join(grid_lines), unsafe_allow_html=True)
                        if edit_elective_enabled:
                            for subj in ELECTIVE_SUBJECTS:
                                subj_key = edit_elective_answers.get(subj, {})
                                st.markdown(f"**{subj} ({ELECTIVE_START_DEFAULT}~{edit_total_q}번)**")
                                st.write(", ".join(f"{q}번:{a}" for q, a in sorted(subj_key.items())) or "등록된 정답 없음")

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

                        ok, msg = save_exam(
                            exam_id=selected_eid,
                            title=edit_title.strip() or cur_exam["title"],
                            total_questions=edit_total_q,
                            pdf_bytes=pdf_bytes,
                            filename=fname,
                            pdf_url=edit_pdf_url.strip(),
                            answer_pdf_url=edit_ans_pdf_url.strip(),
                            answer_key=edit_common_answer,
                            elective_enabled=edit_elective_enabled,
                            elective_answer_keys=edit_elective_answers
                        )
                        for k in [f"exist_{selected_eid}_extracted_common", f"exist_{selected_eid}_extracted_subj_a", f"exist_{selected_eid}_extracted_subj_b"]:
                            st.session_state.pop(k, None)
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
        master_drive_sa_json = cfg.get("drive_service_account_json", "")

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
            st.caption("💡 이 폴더가 '링크가 있는 모든 사용자'로 공유되어 있고 아래 '구글 드라이브 서비스 계정 키'도 등록하면, [📄 시험지 및 PDF 업로드] 탭에서 링크를 복사·붙여넣기 하지 않고 폴더 안 PDF 목록에서 바로 선택할 수 있습니다.")
            new_drive_sa_json = st.text_input(
                "구글 드라이브 서비스 계정 키 (마스터 폴더에서 바로 선택하기 기능용)",
                value=master_drive_sa_json,
                type="password",
                placeholder='다운로드한 JSON 키 파일의 전체 내용을 그대로 붙여넣으세요 (예: {"type": "service_account", ...})',
                help="구글 드라이브 API는 API 키만으로는 목록 조회가 안 되고 이 서비스 계정 키가 있어야 동작합니다. 아래 [구글 드라이브 서비스 계정 키 발급 방법] 안내를 참고하세요."
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
                cfg["drive_service_account_json"] = new_drive_sa_json.strip()
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

        # 3-1. 구글 드라이브 서비스 계정 키 발급 가이드 Expander
        with st.expander("📖 구글 드라이브 서비스 계정 키 발급 방법 (마스터 폴더에서 바로 선택하기용, 클릭하여 열기)"):
            st.markdown("""
            ### 🛠️ 구글 드라이브 서비스 계정 키 발급받는 법
            이 키가 있으면 [📄 시험지 및 PDF 업로드] 탭에서 매번 드라이브 링크를 복사해 붙여넣지 않고, 마스터 폴더 안 PDF 목록에서 바로 골라 연결할 수 있습니다.
            (구글 드라이브 API는 단순 API 키만으로는 목록 조회가 안 되고, 아래처럼 "서비스 계정"이라는 로그인 없는 전용 계정의 키가 필요합니다. 선생님이 직접 로그인하는 절차는 없습니다.)

            1. [Google Cloud Console 사용자 인증 정보 페이지](https://console.cloud.google.com/apis/credentials)에 접속합니다. (처음이면 프로젝트를 새로 만들라는 안내가 뜨는데, 이름은 자유롭게 정해도 됩니다.)
            2. 좌측 메뉴에서 **[API 및 서비스] ➔ [라이브러리]**로 이동해 **"Google Drive API"**를 검색하고 **[사용 설정]**을 눌러 켭니다. (이 단계를 빠뜨리면 목록 조회가 실패합니다.)
            3. 다시 **[사용자 인증 정보]** 화면으로 돌아가 상단 **[+ 사용자 인증 정보 만들기] ➔ [서비스 계정]**을 클릭합니다.
            4. 서비스 계정 이름을 자유롭게 입력하고(예: `suneung-clinic-drive`) **[만들기 및 계속하기] ➔ [완료]**를 누릅니다. (역할 부여 단계는 건너뛰어도 됩니다.)
            5. 생성된 서비스 계정 목록에서 방금 만든 계정을 클릭 ➔ 상단 **[키]** 탭 ➔ **[키 추가] ➔ [새 키 만들기] ➔ JSON** 선택 ➔ **[만들기]**를 누르면 `.json` 파일이 컴퓨터에 다운로드됩니다.
            6. 다운로드된 `.json` 파일을 메모장 등으로 열어 **전체 내용을 그대로 복사**해서 위 [구글 드라이브 서비스 계정 키] 칸에 붙여넣고 저장합니다.

            > **주의**: 이 기능은 마스터 폴더가 **'링크가 있는 모든 사용자'로 공유**되어 있어야 동작합니다. 비공개 폴더는 이 방식으로 접근할 수 없습니다. `.json` 키 파일은 다른 사람과 공유하지 마세요.
            """)

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
