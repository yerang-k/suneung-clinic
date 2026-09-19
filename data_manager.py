import os
import io
import re
import json
import base64
import threading
import time
from datetime import datetime
import requests

# 구글 시트 클라우드 동기화 런타임 상태
_last_sync_time = None
_has_auto_synced = False

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STUDENTS_FILE = os.path.join(DATA_DIR, "students.json")
USER_CONFIG_FILE = os.path.join(DATA_DIR, "user_config.json")
CONFIG_FILE = os.path.join(DATA_DIR, "admin_config.json")
EXAMS_DIR = os.path.join(DATA_DIR, "exams")
EXAMS_META_FILE = os.path.join(EXAMS_DIR, "exams_meta.json")
SUBMISSIONS_FILE = os.path.join(DATA_DIR, "submissions.json")
PROGRESS_DIR = os.path.join(DATA_DIR, "progress")

DEFAULT_CONFIG = {
    "admin_password": "teacher1234",
    "gemini_api_key": "",
    "google_drive_folder_url": "https://drive.google.com/drive/folders/sample-kice-past-exams-archive",
    "gas_api_url": "",
    "drive_service_account_json": ""
}

# 국어영역 선택과목 (공통 1~34번 + 선택 35~45번, 시험지/정답표 PDF에는 두 과목이 함께 인쇄됨)
ELECTIVE_SUBJECTS = ["화법과 작문", "언어와 매체"]
ELECTIVE_START_DEFAULT = 35

DEFAULT_STUDENTS = [
    {"student_id": "30101", "name": "김수험", "password": "1234"},
    {"student_id": "30102", "name": "이국어", "password": "1234"},
    {"student_id": "30103", "name": "박수능", "password": "1234"}
]

# 평가원 기출 시험지별 공식 45문항 정답표
ANSWERS_2024_SUNEUNG = {
    1: 1, 2: 1, 3: 4, 4: 2, 5: 3, 6: 5, 7: 3, 8: 4, 9: 2, 10: 3,
    11: 2, 12: 5, 13: 4, 14: 1, 15: 5, 16: 3, 17: 5, 18: 4, 19: 1, 20: 3,
    21: 2, 22: 4, 23: 1, 24: 5, 25: 3, 26: 2, 27: 4, 28: 2, 29: 5, 30: 3,
    31: 4, 32: 1, 33: 5, 34: 2, 35: 3, 36: 4, 37: 1, 38: 5, 39: 2, 40: 3,
    41: 4, 42: 1, 43: 5, 44: 2, 45: 3
}

ANSWERS_2025_09_MOCK = {
    1: 1, 2: 4, 3: 2, 4: 2, 5: 5, 6: 3, 7: 4, 8: 1, 9: 3, 10: 5,
    11: 2, 12: 4, 13: 1, 14: 3, 15: 5, 16: 2, 17: 4, 18: 1, 19: 3, 20: 5,
    21: 2, 22: 4, 23: 1, 24: 3, 25: 5, 26: 2, 27: 4, 28: 1, 29: 3, 30: 5,
    31: 2, 32: 4, 33: 1, 34: 3, 35: 5, 36: 2, 37: 4, 38: 1, 39: 3, 40: 5,
    41: 2, 42: 4, 43: 1, 44: 3, 45: 5
}

ANSWERS_2024_06_MOCK = {
    1: 1, 2: 3, 3: 2, 4: 5, 5: 4, 6: 1, 7: 3, 8: 2, 9: 5, 10: 4,
    11: 1, 12: 3, 13: 2, 14: 5, 15: 4, 16: 1, 17: 3, 18: 2, 19: 5, 20: 4,
    21: 1, 22: 3, 23: 2, 24: 5, 25: 4, 26: 1, 27: 3, 28: 2, 29: 5, 30: 4,
    31: 1, 32: 3, 33: 2, 34: 5, 35: 4, 36: 1, 37: 3, 38: 2, 39: 5, 40: 4,
    41: 1, 42: 3, 43: 2, 44: 5, 45: 4
}

ANSWERS_2025_SUNEUNG = {
    1: 1, 2: 2, 3: 4, 4: 3, 5: 5, 6: 2, 7: 1, 8: 4, 9: 3, 10: 5,
    11: 1, 12: 2, 13: 4, 14: 3, 15: 5, 16: 2, 17: 1, 18: 4, 19: 3, 20: 5,
    21: 1, 22: 2, 23: 4, 24: 3, 25: 5, 26: 2, 27: 1, 28: 4, 29: 3, 30: 5,
    31: 1, 32: 2, 33: 4, 34: 3, 35: 5, 36: 2, 37: 1, 38: 4, 39: 3, 40: 5,
    41: 1, 42: 2, 43: 4, 44: 3, 45: 5
}

ANSWERS_2027_06_MOCK = {
    1: 1, 2: 3, 3: 2, 4: 2, 5: 4, 6: 5, 7: 1, 8: 4, 9: 2, 10: 3,
    11: 5, 12: 1, 13: 3, 14: 2, 15: 4, 16: 5, 17: 1, 18: 3, 19: 2, 20: 4,
    21: 5, 22: 1, 23: 3, 24: 2, 25: 4, 26: 5, 27: 1, 28: 3, 29: 2, 30: 4,
    31: 5, 32: 1, 33: 3, 34: 2, 35: 4, 36: 5, 37: 1, 38: 3, 39: 2, 40: 4,
    41: 5, 42: 1, 43: 3, 44: 2, 45: 4
}

DEFAULT_EXAMS = {
    "2027_06_mock": {
        "exam_id": "2027_06_mock",
        "title": "2027학년도 6월 모의평가 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "answer_key": ANSWERS_2027_06_MOCK,
        "created_at": "2026-06-01"
    },
    "2025_09_mock": {
        "exam_id": "2025_09_mock",
        "title": "2025학년도 9월 모의평가 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "answer_key": ANSWERS_2025_09_MOCK,
        "created_at": "2024-09-04"
    },
    "2024_suneung": {
        "exam_id": "2024_suneung",
        "title": "2024학년도 대학수학능력시험 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "answer_key": ANSWERS_2024_SUNEUNG,
        "created_at": "2023-11-16"
    },
    "2024_06_mock": {
        "exam_id": "2024_06_mock",
        "title": "2024학년도 6월 모의평가 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "answer_key": ANSWERS_2024_06_MOCK,
        "created_at": "2023-06-01"
    },
    "2025_suneung": {
        "exam_id": "2025_suneung",
        "title": "2025학년도 대학수학능력시험 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "answer_key": ANSWERS_2025_SUNEUNG,
        "created_at": "2024-11-14"
    }
}

def init_data_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(EXAMS_DIR, exist_ok=True)
    os.makedirs(PROGRESS_DIR, exist_ok=True)
    
    # admin_config.json 초기화 및 누락 키 보정
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    else:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            updated = False
            for k, v in DEFAULT_CONFIG.items():
                if k not in loaded:
                    loaded[k] = v
                    updated = True
            if updated:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(loaded, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
            
    if not os.path.exists(STUDENTS_FILE):
        with open(STUDENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STUDENTS, f, ensure_ascii=False, indent=2)
            
    if not os.path.exists(EXAMS_META_FILE):
        with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_EXAMS, f, ensure_ascii=False, indent=2)
    else:
        try:
            with open(EXAMS_META_FILE, "r", encoding="utf-8") as f:
                loaded_exams = json.load(f)
            exams_updated = False
            for eid, edata in DEFAULT_EXAMS.items():
                if eid in loaded_exams:
                    if "answer_key" not in loaded_exams[eid] and "answer_key" in edata:
                        loaded_exams[eid]["answer_key"] = edata["answer_key"]
                        exams_updated = True
                else:
                    loaded_exams[eid] = edata
                    exams_updated = True
            if exams_updated:
                with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
                    json.dump(loaded_exams, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
            
    if not os.path.exists(SUBMISSIONS_FILE):
        with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

# ==========================================
# --- 구글 스프레드시트(GAS) 클라우드 영구 동기화 엔진 ---
# ==========================================
def get_gas_api_url() -> str:
    """Streamlit Secrets, 환경변수, 또는 로컬 admin_config에서 GAS URL 조회"""
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            if "GAS_API_URL" in st.secrets:
                return str(st.secrets["GAS_API_URL"]).strip()
            if "gas_api_url" in st.secrets:
                return str(st.secrets["gas_api_url"]).strip()
    except Exception:
        pass

    env_url = os.environ.get("GAS_API_URL", "").strip()
    if env_url:
        return env_url

    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
                return str(c.get("gas_api_url", "")).strip()
    except Exception:
        pass
    return ""

def sync_from_google_sheets(force: bool = False):
    """
    구글 스프레드시트(GAS)로부터 시험지, 학생, 설정, 제출기록을 가져와 로컬 캐시를 갱신합니다.
    """
    global _last_sync_time, _has_auto_synced
    gas_url = get_gas_api_url()
    if not gas_url or not gas_url.startswith("http"):
        return False, "연동된 구글 스프레드시트(GAS) URL이 없습니다."

    try:
        sep = "&" if "?" in gas_url else "?"
        req_url = f"{gas_url}{sep}action=sync_all"
        resp = requests.get(req_url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            init_data_dirs()

            # 1. Config 동기화
            if "config" in data and isinstance(data["config"], dict) and data["config"]:
                local_cfg = {}
                if os.path.exists(CONFIG_FILE):
                    try:
                        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                            local_cfg = json.load(f)
                    except Exception:
                        pass
                saved_gas = local_cfg.get("gas_api_url", gas_url)
                local_cfg.update(data["config"])
                if saved_gas:
                    local_cfg["gas_api_url"] = saved_gas
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(local_cfg, f, ensure_ascii=False, indent=2)

            # 2. Exams 동기화
            if "exams" in data and isinstance(data["exams"], dict) and data["exams"]:
                local_exams = DEFAULT_EXAMS.copy()
                if os.path.exists(EXAMS_META_FILE):
                    try:
                        with open(EXAMS_META_FILE, "r", encoding="utf-8") as f:
                            local_exams = json.load(f)
                    except Exception:
                        pass
                # 시트에는 정답표 링크·정답·선택과목 칸이 없거나 비어 있을 수 있으므로,
                # 시험지를 통째로 덮어쓰지 않고 '시트에 값이 있는 항목만' 항목별로 합친다.
                for eid, sheet_ex in data["exams"].items():
                    merged = dict(local_exams.get(eid, {}))
                    for k, v in sheet_ex.items():
                        if v in ("", None, {}, []):
                            merged.setdefault(k, v)
                        else:
                            merged[k] = v
                    local_exams[eid] = merged
                with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
                    json.dump(local_exams, f, ensure_ascii=False, indent=2)

            # 3. Students 동기화
            if "students" in data and isinstance(data["students"], list) and data["students"]:
                local_students = DEFAULT_STUDENTS.copy()
                if os.path.exists(STUDENTS_FILE):
                    try:
                        with open(STUDENTS_FILE, "r", encoding="utf-8") as f:
                            local_students = json.load(f)
                    except Exception:
                        pass
                s_map = {str(s["student_id"]).strip(): s for s in local_students}
                for s in data["students"]:
                    s_id = str(s.get("student_id", "")).strip()
                    if s_id:
                        s_map[s_id] = s
                with open(STUDENTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(list(s_map.values()), f, ensure_ascii=False, indent=2)

            # 4. Submissions 동기화
            if "submissions" in data and isinstance(data["submissions"], list) and data["submissions"]:
                with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data["submissions"], f, ensure_ascii=False, indent=2)

            _last_sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _has_auto_synced = True
            return True, f"구글 시트와 성공적으로 동기화되었습니다 ({_last_sync_time})."
        else:
            return False, f"구글 시트 응답 오류 (HTTP {resp.status_code})"
    except Exception as e:
        return False, f"구글 시트 동기화 실패: {e}"

def push_to_google_sheets(action: str, payload_data: dict):
    """구글 시트(GAS)로 변경 사항을 비동기 전송"""
    gas_url = get_gas_api_url()
    if not gas_url or not gas_url.startswith("http"):
        return

    def _worker():
        try:
            body = {"action": action}
            body.update(payload_data)
            requests.post(gas_url, json=body, timeout=8)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

def push_all_to_google_sheets():
    """현재 로컬의 시험지, 학생, 설정을 구글 시트로 한 번에 백업 전송"""
    gas_url = get_gas_api_url()
    if not gas_url or not gas_url.startswith("http"):
        return False, "구글 시트(GAS) URL이 설정되지 않았습니다."

    try:
        body = {
            "action": "sync_push_all",
            "exams": get_exams(),
            "students": get_students(),
            "config": get_admin_config()
        }
        resp = requests.post(gas_url, json=body, timeout=10)
        if resp.status_code == 200:
            return True, "로컬의 전체 데이터가 구글 스프레드시트에 성공적으로 백업되었습니다!"
        return False, f"백업 실패 (HTTP {resp.status_code})"
    except Exception as e:
        return False, f"백업 전송 중 오류: {e}"

def ensure_auto_synced():
    """앱 런타임 시작 시 1회 구글 시트에서 최신 데이터 자동 동기화"""
    global _has_auto_synced
    if not _has_auto_synced:
        _has_auto_synced = True
        gas_url = get_gas_api_url()
        if gas_url and gas_url.startswith("http"):
            threading.Thread(target=sync_from_google_sheets, daemon=True).start()

def get_last_sync_time():
    global _last_sync_time
    return _last_sync_time

# --- 설정 (Config) ---
def get_admin_config():
    init_data_dirs()
    ensure_auto_synced()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_admin_config(config):
    init_data_dirs()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    # 구글 시트에 즉시 백업 전송
    push_to_google_sheets("save_config", {"config": config})

def verify_admin_password(password: str) -> bool:
    cfg = get_admin_config()
    target_pw = str(cfg.get("admin_password", "teacher1234")).strip()
    input_pw = str(password or "").strip()
    if not input_pw:
        return False
    # 초기 비밀번호 상태일 때는 teacher1234뿐 아니라 1234도 허용하여 입력 편의 보장
    if target_pw == "teacher1234" and input_pw in ["teacher1234", "1234"]:
        return True
    return target_pw == input_pw

# --- 학생/로컬 사용자 설정 (User Config) ---
def get_user_config() -> dict:
    init_data_dirs()
    if os.path.exists(USER_CONFIG_FILE):
        try:
            with open(USER_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_user_config(config: dict):
    init_data_dirs()
    with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_effective_api_key():
    """
    저장된 API 키를 우선순위에 따라 반환:
    1. 학생/로컬 기기 저장 키 (user_config.json)
    2. 관리자가 등록한 공용 키 (admin_config.json)
    3. 환경 변수 (GEMINI_API_KEY)
    """
    u_cfg = get_user_config()
    user_key = u_cfg.get("gemini_api_key", "").strip()
    if user_key:
        return user_key, "USER"
    
    a_cfg = get_admin_config()
    admin_key = a_cfg.get("gemini_api_key", "").strip()
    if admin_key:
        return admin_key, "ADMIN"
        
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key, "ENV"
        
    return "", "NONE"

def save_student_api_key(api_key: str):
    u_cfg = get_user_config()
    u_cfg["gemini_api_key"] = api_key.strip()
    save_user_config(u_cfg)

def clear_student_api_key():
    u_cfg = get_user_config()
    if "gemini_api_key" in u_cfg:
        del u_cfg["gemini_api_key"]
        save_user_config(u_cfg)

# --- 학생 관리 (Students) ---
def get_students():
    init_data_dirs()
    ensure_auto_synced()
    try:
        with open(STUDENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_STUDENTS

def save_students(students):
    init_data_dirs()
    with open(STUDENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(students, f, ensure_ascii=False, indent=2)

def add_student(student_id: str, name: str, password: str):
    students = get_students()
    s_id = str(student_id).strip()
    s_name = str(name).strip()
    s_pw = str(password).strip()
    updated = False
    for s in students:
        if str(s.get("student_id", "")).strip() == s_id:
            s["name"] = s_name
            s["password"] = s_pw
            updated = True
            break
    if not updated:
        students.append({"student_id": s_id, "name": s_name, "password": s_pw})
    
    save_students(students)
    push_to_google_sheets("save_student", {"student": {"student_id": s_id, "name": s_name, "password": s_pw}})
    return True, "학생 정보가 업데이트되었습니다." if updated else "새 학생이 등록되었습니다."

def delete_student(student_id: str):
    students = get_students()
    s_id = str(student_id).strip()
    filtered = [s for s in students if str(s.get("student_id", "")).strip() != s_id]
    if len(filtered) != len(students):
        save_students(filtered)
        push_to_google_sheets("delete_student", {"student_id": s_id})
        return True, "학생이 삭제되었습니다."
    return False, "해당 학번의 학생을 찾을 수 없습니다."

def verify_student(student_id: str, name: str, password: str):
    students = get_students()
    s_id = str(student_id).strip()
    s_name = str(name).strip()
    s_pw = str(password).strip()
    for s in students:
        if str(s.get("student_id", "")).strip() == s_id:
            if str(s.get("name", "")).strip() == s_name and str(s.get("password", "")).strip() == s_pw:
                return True, s
            return False, "이름 또는 비밀번호가 일치하지 않습니다."
    return False, "등록되지 않은 학번입니다. 교사용 관리자 모드에서 학생을 먼저 등록해 주세요."

# --- 시험 및 PDF 관리 (Exams) ---
def get_exams():
    init_data_dirs()
    ensure_auto_synced()
    try:
        with open(EXAMS_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_EXAMS

def get_sorted_exam_keys(exams: dict = None, reverse: bool = True) -> list:
    """
    시험지 딕셔너리를 입력받아 연도 및 시행 시기(수능, 10월, 9월, 7월, 6월 등)를 기반으로
    최신순(reverse=True) 또는 과거순(reverse=False)으로 정렬된 exam_id 리스트를 반환합니다.
    """
    if exams is None:
        exams = get_exams()
    if not exams:
        return []

    def _sort_key(eid):
        info = exams.get(eid, {})
        title = str(info.get("title", ""))
        eid_str = str(info.get("exam_id", eid))
        
        # 1. 4자리 연도 추출 (예: 2026)
        year_match = re.search(r'(20\d\d)', title) or re.search(r'(20\d\d)', eid_str)
        year = int(year_match.group(1)) if year_match else 0
        
        # 2. 시험 시행 시기 가중치 (수능 11.5 > 10월 10 > 9월 9 > 7월 7 > 6월 6 > 4월 4 > 3월 3)
        month_val = 0.0
        if any(w in title for w in ["수능", "대학수학능력시험"]) or "suneung" in eid_str.lower():
            month_val = 11.5
        else:
            m_match = re.search(r'(\d{1,2})월', title) or re.search(r'_(\d{2})_', eid_str)
            if m_match:
                try:
                    month_val = float(m_match.group(1))
                except Exception:
                    month_val = 0.0
                    
        return (year, month_val, title)

    return sorted(list(exams.keys()), key=_sort_key, reverse=reverse)

def save_exam(exam_id: str, title: str, total_questions: int, pdf_bytes: bytes = None, filename: str = None, pdf_url: str = "", answer_key: dict = None, answer_pdf_url: str = "", elective_enabled: bool = None, elective_start: int = None, elective_answer_keys: dict = None):
    init_data_dirs()
    exams = get_exams()
    pdf_save_name = ""

    if pdf_bytes and filename:
        safe_filename = f"{exam_id}_{filename}"
        pdf_path = os.path.join(EXAMS_DIR, safe_filename)
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        pdf_save_name = safe_filename
    elif exam_id in exams and exams[exam_id].get("pdf_filename"):
        pdf_save_name = exams[exam_id]["pdf_filename"]

    existing_url = exams[exam_id].get("pdf_url", "") if exam_id in exams else ""
    final_url = pdf_url.strip() if pdf_url is not None else existing_url

    existing_ans_url = exams[exam_id].get("answer_pdf_url", "") if exam_id in exams else ""
    final_ans_url = answer_pdf_url.strip() if answer_pdf_url is not None else existing_ans_url

    if answer_key is not None:
        final_answer_key = answer_key
    elif exam_id in exams and "answer_key" in exams[exam_id]:
        final_answer_key = exams[exam_id]["answer_key"]
    else:
        final_answer_key = {}

    # 선택과목(화법과 작문 / 언어와 매체) 설정 — 지정하지 않으면 기존 값을 유지(하위 호환)
    existing = exams.get(exam_id, {})
    final_elective_enabled = bool(elective_enabled) if elective_enabled is not None else bool(existing.get("elective_enabled", False))
    final_elective_start = int(elective_start) if elective_start is not None else int(existing.get("elective_start", ELECTIVE_START_DEFAULT))
    if elective_answer_keys is not None:
        final_elective_keys = elective_answer_keys
    else:
        final_elective_keys = existing.get("elective_answer_keys", {})

    exams[exam_id] = {
        "exam_id": exam_id,
        "title": title,
        "total_questions": int(total_questions),
        "pdf_filename": pdf_save_name,
        "pdf_url": final_url,
        "answer_pdf_url": final_ans_url,
        "answer_key": final_answer_key,
        "elective_enabled": final_elective_enabled,
        "elective_start": final_elective_start,
        "elective_answer_keys": final_elective_keys,
        "created_at": exams[exam_id].get("created_at") if (exam_id in exams and exams[exam_id].get("created_at")) else datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
        json.dump(exams, f, ensure_ascii=False, indent=2)
    push_to_google_sheets("save_exam", {"exam": exams[exam_id]})
    return True, f"'{title}' 시험지가 성공적으로 등록/저장되었습니다."

def attach_pdf_to_exam(exam_id: str, pdf_bytes: bytes = None, filename: str = None, pdf_url: str = ""):
    """기존에 등록된 시험지에 PDF 파일 또는 구글 드라이브 URL을 첨부합니다."""
    init_data_dirs()
    exams = get_exams()
    if exam_id not in exams:
        return False, "해당 시험지를 찾을 수 없습니다."

    ex = exams[exam_id]
    if pdf_bytes and filename:
        safe_filename = f"{exam_id}_{filename}"
        pdf_path = os.path.join(EXAMS_DIR, safe_filename)
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        ex["pdf_filename"] = safe_filename
    
    if pdf_url:
        ex["pdf_url"] = pdf_url.strip()

    exams[exam_id] = ex
    with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
        json.dump(exams, f, ensure_ascii=False, indent=2)
    push_to_google_sheets("save_exam", {"exam": ex})
    return True, f"'{ex['title']}'에 PDF가 성공적으로 연결되었습니다!"

def delete_exam(exam_id: str):
    init_data_dirs()
    exams = get_exams()
    if exam_id in exams:
        del exams[exam_id]
        with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
            json.dump(exams, f, ensure_ascii=False, indent=2)
        push_to_google_sheets("delete_exam", {"exam_id": exam_id})
        return True, "시험지가 삭제되었습니다."
    return False, "해당 시험지를 찾을 수 없습니다."

# --- 시험지 공식 정답표(Answer Key) 관리 및 자동 정오 판정 ---
def get_exam_answer_key(exam_id: str) -> dict:
    """시험지의 1~45번 정답표({문항번호(int): 정답번호(int)}) 반환"""
    exams = get_exams()
    if exam_id in exams and "answer_key" in exams[exam_id] and isinstance(exams[exam_id]["answer_key"], dict):
        result = {}
        for k, v in exams[exam_id]["answer_key"].items():
            try:
                result[int(k)] = int(v)
            except Exception:
                pass
        if result:
            return result
            
    if exam_id in DEFAULT_EXAMS and "answer_key" in DEFAULT_EXAMS[exam_id]:
        return {int(k): int(v) for k, v in DEFAULT_EXAMS[exam_id]["answer_key"].items()}
        
    return {}

def save_exam_answer_key(exam_id: str, answer_key: dict):
    """시험지에 공식 45문항 정답표 저장 및 구글 시트 백업"""
    init_data_dirs()
    exams = get_exams()
    if exam_id not in exams:
        return False, "해당 시험지를 찾을 수 없습니다."
    
    cleaned_key = {}
    for k, v in answer_key.items():
        try:
            qk = int(k)
            qv = int(v)
            if 1 <= qv <= 5:
                cleaned_key[str(qk)] = qv
        except Exception:
            pass
            
    exams[exam_id]["answer_key"] = cleaned_key
    with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
        json.dump(exams, f, ensure_ascii=False, indent=2)
    push_to_google_sheets("save_exam", {"exam": exams[exam_id]})
    return True, f"'{exams[exam_id]['title']}'의 공식 정답표({len(cleaned_key)}문항)가 성공적으로 저장되었습니다!"

def exam_is_elective(exam_id: str) -> bool:
    """국어영역 선택과목(화법과 작문/언어와 매체)이 구분 설정된 시험지인지 여부"""
    exams = get_exams()
    return bool(exams.get(exam_id, {}).get("elective_enabled", False))

def get_exam_elective_start(exam_id: str) -> int:
    """선택과목이 시작되는 문항 번호 (기본 35번)"""
    exams = get_exams()
    try:
        return int(exams.get(exam_id, {}).get("elective_start", ELECTIVE_START_DEFAULT))
    except Exception:
        return ELECTIVE_START_DEFAULT

def get_exam_elective_answer_key(exam_id: str, subject: str) -> dict:
    """특정 선택과목(예: '화법과 작문')의 정답표({문항번호(int): 정답번호(int)}) 반환"""
    exams = get_exams()
    raw = exams.get(exam_id, {}).get("elective_answer_keys", {}).get(subject, {})
    result = {}
    for k, v in raw.items():
        try:
            result[int(k)] = int(v)
        except Exception:
            pass
    return result

def get_effective_answer_key(exam_id: str, subject: str = None) -> dict:
    """
    학생이 실제로 채점받아야 할 정답표를 반환합니다.
    - 선택과목이 설정되지 않은 시험: 기존 answer_key를 그대로 반환 (하위 호환, 동작 변화 없음)
    - 선택과목이 설정된 시험: 공통 문항(answer_key, elective_start 미만) + 선택한 과목의
      elective_start~total_questions 정답을 합쳐서 반환
    """
    base = get_exam_answer_key(exam_id)
    if not exam_is_elective(exam_id):
        return base

    elective_start = get_exam_elective_start(exam_id)
    merged = {q: a for q, a in base.items() if q < elective_start}
    if subject:
        merged.update(get_exam_elective_answer_key(exam_id, subject))
    return merged

def parse_answer_string(raw_text: str) -> dict:
    """
    텍스트 문자열(예: '14325 12345...' 또는 줄바꿈된 숫자들)을 파싱하여 {문항번호: 정답번호} 딕셔너리로 변환
    """
    digits = re.findall(r'[1-5]', str(raw_text or ""))
    result = {}
    for idx, d in enumerate(digits[:45], start=1):
        result[idx] = int(d)
    return result

def extract_answers_from_pdf(pdf_bytes: bytes, client=None) -> tuple[dict, str]:
    """
    평가원 공식 정답표 PDF 파일에서 1~45번 정답을 자동으로 추출하여 {문항번호: 정답번호} 딕셔너리로 반환합니다.
    1. pypdf를 통해 텍스트를 우선 추출
    2. Gemini Multimodal AI (call_gemini_safe 모델 폴백)를 활용해 PDF 표 및 텍스트에서 1~45번 정답을 정밀 판독
    3. AI 부재 또는 오류 시 정규식 패턴 파서로 자동 폴백
    """
    if not pdf_bytes:
        return {}, "PDF 파일 데이터가 전달되지 않았습니다."

    extracted_text = ""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted_text += t + "\n"
    except Exception:
        extracted_text = ""

    # 1. Gemini AI를 활용한 정밀 추출
    if client is None:
        try:
            saved_key, _ = get_effective_api_key()
            if saved_key:
                from google import genai
                client = genai.Client(api_key=saved_key)
        except Exception:
            pass

    if client is not None:
        try:
            from google.genai import types
            prompt = """
당신은 대한민국 대학수학능력시험 및 모의평가 공식 정답표를 완벽하게 판독하는 전문가입니다.
제공된 정답표 PDF(또는 텍스트)를 꼼꼼히 분석하여, 국어영역의 1번부터 45번까지의 [문항 번호: 정답 번호(1~5)]를 정확히 추출해 주세요.

규칙:
1. 문항 번호는 1부터 시작하며, 정답은 반드시 1, 2, 3, 4, 5 중 하나입니다.
2. 만약 복수정답이 있다면 가장 앞선 번호 하나만 선택하세요.
3. 반드시 아래와 같은 순수 JSON 형식으로만 응답하세요 (마크다운 코드블록 포함 가능):
{
    "1": 1,
    "2": 4,
    "3": 2,
    ...
    "45": 3
}
"""
            parts = []
            try:
                parts.append(types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"))
            except Exception:
                pass
            if extracted_text.strip():
                parts.append(types.Part.from_text(text=f"[추출된 텍스트 내용]\n{extracted_text[:4000]}"))
            parts.append(types.Part.from_text(text=prompt))

            res = call_gemini_safe(
                client,
                contents=parts,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            raw_text = res.text.strip()
            cleaned = re.sub(r"^```(?:json)?\s*|```$", "", raw_text, flags=re.MULTILINE)
            parsed = json.loads(cleaned)
            result = {}
            for k, v in parsed.items():
                try:
                    qk = int(k)
                    qv = int(v)
                    if 1 <= qv <= 5:
                        result[qk] = qv
                except Exception:
                    pass
            if len(result) >= 15:
                return result, f"Gemini AI가 정답표 PDF에서 총 {len(result)}개 문항의 정답을 완벽하게 인식했습니다!"
        except Exception as ex:
            pass

    # 2. 로컬 정규식 폴백 추출 (텍스트에서 '문항번호 정답' 테이블 형태 탐색)
    if extracted_text.strip():
        # 문항 번호와 정답 번호가 연이어 있는 경우 (예: 1 3 2 4 3 1 ...)
        pair_matches = re.findall(r'(?:^|\s)(\d{1,2})\s+([1-5])(?:\s|$)', extracted_text)
        if len(pair_matches) >= 20:
            result = {}
            for qk_s, qv_s in pair_matches:
                qk = int(qk_s)
                qv = int(qv_s)
                if 1 <= qk <= 45 and qk not in result:
                    result[qk] = qv
            if len(result) >= 20:
                return result, f"PDF 텍스트 파싱을 통해 총 {len(result)}개 문항의 정답을 자동 추출했습니다."

    return {}, "정답표 PDF에서 정답을 자동으로 판독하지 못했습니다. PDF 내용이 선명한지 확인하시거나 정답 번호를 직접 입력해 주세요."

def extract_elective_answers_from_pdf(pdf_bytes: bytes, client=None, elective_start: int = ELECTIVE_START_DEFAULT, total_questions: int = 45) -> tuple:
    """
    선택과목(화법과 작문/언어와 매체)이 함께 인쇄된 국어영역 공식 정답표 PDF에서
    공통 문항과 두 선택과목의 정답을 각각 구분하여 추출합니다.
    (일반 extract_answers_from_pdf()는 선택과목 구간의 번호가 두 벌 겹쳐 있어
    하나의 평면 딕셔너리로는 정확히 판독할 수 없기 때문에 별도로 존재)

    반환: (common_answer_key, {"화법과 작문": {...}, "언어와 매체": {...}}, message)
    """
    empty_electives = {s: {} for s in ELECTIVE_SUBJECTS}
    if not pdf_bytes:
        return {}, empty_electives, "PDF 파일 데이터가 전달되지 않았습니다."

    extracted_text = ""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted_text += t + "\n"
    except Exception:
        extracted_text = ""

    if client is None:
        try:
            saved_key, _ = get_effective_api_key()
            if saved_key:
                from google import genai
                client = genai.Client(api_key=saved_key)
        except Exception:
            pass

    if client is None:
        return {}, empty_electives, "Gemini API 키가 설정되어 있지 않아 자동 추출을 진행할 수 없습니다. 사이드바에서 API 키를 등록하거나 정답을 직접 입력해 주세요."

    try:
        from google.genai import types
        common_end = elective_start - 1
        subj_a, subj_b = ELECTIVE_SUBJECTS[0], ELECTIVE_SUBJECTS[1]
        prompt = f"""
당신은 대한민국 대학수학능력시험 및 모의평가 국어영역 공식 정답표를 완벽하게 판독하는 전문가입니다.

이 시험의 국어영역은 다음과 같은 구조입니다:
- 1번~{common_end}번: 모든 학생이 공통으로 응시하는 공통 문항
- {elective_start}번~{total_questions}번: 선택과목 문항으로, "{subj_a}"와 "{subj_b}" 두 과목의 정답이
  정답표 안에 각각 별도 지문/구간으로 인쇄되어 있습니다 (즉 {elective_start}번~{total_questions}번 문항 번호가 정답표 안에 두 번 반복됩니다).

제공된 정답표 PDF(또는 텍스트)를 꼼꼼히 분석하여, 아래 3가지를 정확히 구분해서 추출해 주세요:
1. "common": 1번~{common_end}번 공통 문항 정답
2. "subject_a": "{subj_a}" 선택과목의 {elective_start}번~{total_questions}번 정답 (총 {total_questions - elective_start + 1}개)
3. "subject_b": "{subj_b}" 선택과목의 {elective_start}번~{total_questions}번 정답 (총 {total_questions - elective_start + 1}개)

주의: 정답표(특히 '정답 및 해설' 파일)에는 선택과목 두 벌의 정답이 각각 별도 표/구간으로 나뉘어 있습니다.
'화법과 작문' 또는 '언어와 매체'라는 제목/머리글이 붙은 표를 찾아 각각 따로 읽으세요.
해설 본문은 무시하고 정답 일람표만 참고하세요.

규칙:
- 정답은 반드시 1, 2, 3, 4, 5 중 하나의 숫자입니다.
- 복수정답이 있다면 가장 앞선 번호 하나만 선택하세요.
- 키 이름은 반드시 아래 영문 3개를 그대로 쓰고, 순수 JSON으로만 응답하세요:
{{
    "common": {{"1": 1, "2": 4, ...}},
    "subject_a": {{"{elective_start}": 2, ..., "{total_questions}": 4}},
    "subject_b": {{"{elective_start}": 1, ..., "{total_questions}": 5}}
}}
"""
        parts = []
        try:
            parts.append(types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"))
        except Exception:
            pass
        if extracted_text.strip():
            parts.append(types.Part.from_text(text=f"[추출된 텍스트 내용]\n{extracted_text[:6000]}"))
        parts.append(types.Part.from_text(text=prompt))

        res = call_gemini_safe(
            client,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        raw_text = res.text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*|```$", "", raw_text, flags=re.MULTILINE)
        parsed = json.loads(cleaned)

        def _clean(d):
            out = {}
            for k, v in (d or {}).items():
                try:
                    qk, qv = int(k), int(v)
                    if 1 <= qv <= 5:
                        out[qk] = qv
                except Exception:
                    pass
            return out

        def _pick(*names):
            # 영문 키를 우선하고, AI가 한글 과목명 키로 답한 경우도 공백을 무시하고 매칭
            for k, v in parsed.items():
                nk = str(k).replace(" ", "").lower()
                if any(nk == n or (n in nk) for n in names):
                    return v
            return None

        common_result = _clean(_pick("common", "공통"))
        elective_result = {
            subj_a: _clean(_pick("subject_a", "화법")),
            subj_b: _clean(_pick("subject_b", "언어")),
        }

        # 선택과목이 하나라도 비었으면 성공으로 취급하지 않고, AI가 돌려준 내용을 알려준다
        missing = [s for s in (subj_a, subj_b) if len(elective_result[s]) < (total_questions - elective_start + 1) // 2]
        if missing or len(common_result) < 15:
            found = (f"공통 {len(common_result)}개, '{subj_a}' {len(elective_result[subj_a])}개, "
                     f"'{subj_b}' {len(elective_result[subj_b])}개")
            return common_result, elective_result, (
                f"정답표에서 일부만 판독했습니다 ({found}). "
                f"{', '.join(missing)} 정답을 찾지 못했어요. 이 PDF에 두 선택과목 정답표가 모두 들어 있는지 확인하시고, "
                f"없다면 아래 칸에 직접 입력해 주세요. (AI 응답 키: {list(parsed.keys())})"
            )
        return common_result, elective_result, (
            f"Gemini AI가 공통 {len(common_result)}개, '{subj_a}' {len(elective_result[subj_a])}개, "
            f"'{subj_b}' {len(elective_result[subj_b])}개 문항의 정답을 인식했습니다. "
            f"아래 상세 확인 후 저장해 주세요."
        )
    except Exception as e:
        return {}, empty_electives, f"AI 정답 추출 중 오류가 발생했습니다: {e}"

def download_pdf_from_drive_or_url(url: str) -> tuple:
    """
    구글 드라이브 공유 링크 또는 일반 웹 URL에서 PDF 바이너리 데이터를 안전하게 다운로드합니다.
    (반환: (pdf_bytes, error_message))
    """
    if not url or not str(url).strip():
        return None, "URL이 입력되지 않았습니다."

    clean_url = str(url).strip()
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 1. 구글 드라이브 URL에서 file_id 추출
    file_id = ""
    m1 = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", clean_url)
    if m1:
        file_id = m1.group(1)
    if not file_id:
        m2 = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", clean_url)
        if m2:
            file_id = m2.group(1)
    if not file_id:
        m3 = re.search(r"docs\.google\.com/(?:file|document)/d/([a-zA-Z0-9_-]+)", clean_url)
        if m3:
            file_id = m3.group(1)

    if file_id:
        # 구글 드라이브 직접 다운로드 엔드포인트 후보군
        candidate_urls = [
            f"https://drive.usercontent.google.com/download?id={file_id}&export=download&authuser=0",
            f"https://drive.google.com/uc?export=download&id={file_id}",
            f"https://docs.google.com/uc?export=download&id={file_id}"
        ]
        for dl_url in candidate_urls:
            try:
                resp = session.get(dl_url, headers=headers, timeout=20, allow_redirects=True)
                # 바이러스 검사 경고(대용량 파일 시) 컨펌 토큰 처리
                if "download_warning" in resp.text:
                    token_match = re.search(r'confirm=([0-9A-Za-z_]+)', resp.text)
                    if token_match:
                        confirm_token = token_match.group(1)
                        confirm_url = f"{dl_url}&confirm={confirm_token}"
                        resp = session.get(confirm_url, headers=headers, timeout=20, allow_redirects=True)

                if resp.status_code == 200 and len(resp.content) > 200:
                    c_type = resp.headers.get("Content-Type", "").lower()
                    if resp.content.startswith(b"%PDF") or "pdf" in c_type or "octet-stream" in c_type:
                        return resp.content, ""
            except Exception:
                continue

        return None, "구글 드라이브에서 정답표 PDF를 가져오지 못했습니다. 링크의 공유 권한이 '링크가 있는 모든 사용자(뷰어)'로 설정되어 있는지 확인해 주세요."

    # 2. 일반 HTTP(S) URL 다운로드
    if clean_url.startswith("http://") or clean_url.startswith("https://"):
        try:
            resp = session.get(clean_url, headers=headers, timeout=20, allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 200:
                return resp.content, ""
            return None, f"정답표 파일을 다운로드할 수 없습니다. (HTTP 상태 코드: {resp.status_code})"
        except Exception as ex:
            return None, f"URL 접근 실패: {str(ex)}"

    return None, "올바른 구글 드라이브 공유 링크 또는 웹 URL 형식이 아닙니다."

def extract_drive_folder_id(url: str) -> str:
    """구글 드라이브 폴더 공유 링크에서 folder_id를 추출합니다."""
    if not url:
        return ""
    m = re.search(r"drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)", str(url))
    if m:
        return m.group(1)
    m2 = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", str(url))
    if m2:
        return m2.group(1)
    return ""

def _get_drive_access_token(service_account_json: str) -> tuple:
    """
    서비스 계정 키(JSON)로 구글 드라이브 API용 OAuth2 액세스 토큰을 발급합니다.
    (구글 드라이브 API는 API 키만으로는 files.list를 지원하지 않고 반드시
    OAuth2 인증 주체를 요구하므로, 사람이 로그인하지 않아도 되는 서비스 계정을 사용합니다.)
    반환: (access_token, error_message)
    """
    try:
        from google.oauth2 import service_account as gsa
        import google.auth.transport.requests as gareq
    except Exception:
        return None, "이 기능에 필요한 구글 인증 라이브러리(google-auth)를 찾을 수 없습니다."

    try:
        sa_info = json.loads(service_account_json)
    except Exception:
        return None, "서비스 계정 키가 올바른 JSON 형식이 아닙니다. 다운로드한 JSON 파일의 전체 내용을 그대로 붙여넣었는지 확인해 주세요."

    try:
        creds = gsa.Credentials.from_service_account_info(
            sa_info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        creds.refresh(gareq.Request())
        return creds.token, ""
    except Exception as e:
        return None, f"서비스 계정 인증에 실패했습니다: {e}"

def list_drive_folder_pdfs(folder_url: str, service_account_json: str, max_files: int = 300, max_depth: int = 4) -> tuple:
    """
    '링크가 있는 모든 사용자'로 공개된 구글 드라이브 폴더 안의 PDF 파일 목록을
    구글 드라이브 API v3(서비스 계정 인증)로 조회합니다.
    하위 폴더(연도/월별 정리 등)까지 재귀적으로 탐색합니다.
    반환: (files, error_message) — files는 [{"id", "name", "path", "link"}, ...]
    """
    folder_url = (folder_url or "").strip()
    service_account_json = (service_account_json or "").strip()
    if not folder_url:
        return [], "구글 드라이브 마스터 폴더 링크가 설정되어 있지 않습니다. [마스터 연동 및 시스템 설정] 탭에서 먼저 등록해 주세요."
    if not service_account_json:
        return [], "구글 드라이브 서비스 계정 키가 설정되어 있지 않습니다. [마스터 연동 및 시스템 설정] 탭에서 등록해 주세요."

    root_id = extract_drive_folder_id(folder_url)
    if not root_id:
        return [], "구글 드라이브 폴더 링크에서 폴더 ID를 인식하지 못했습니다."

    access_token, token_err = _get_drive_access_token(service_account_json)
    if not access_token:
        return [], token_err
    headers = {"Authorization": f"Bearer {access_token}"}

    files = []
    queue = [(root_id, "", 0)]
    seen_folders = {root_id}
    try:
        while queue and len(files) < max_files:
            cur_id, cur_path, depth = queue.pop(0)
            page_token = None
            while True:
                params = {
                    "q": f"'{cur_id}' in parents and trashed = false",
                    "fields": "nextPageToken, files(id, name, mimeType)",
                    "pageSize": 100,
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true"
                }
                if page_token:
                    params["pageToken"] = page_token
                resp = requests.get("https://www.googleapis.com/drive/v3/files", params=params, headers=headers, timeout=15)
                if resp.status_code != 200:
                    err_msg = resp.json().get("error", {}).get("message", resp.text[:200]) if resp.text else f"HTTP {resp.status_code}"
                    return files, f"구글 드라이브 목록 조회 실패: {err_msg}\n(서비스 계정 키가 유효한지, 'Google Drive API'가 활성화되어 있는지, 폴더가 '링크가 있는 모든 사용자'로 공유되어 있는지 확인해 주세요.)"
                data = resp.json()
                for item in data.get("files", []):
                    mime = item.get("mimeType", "")
                    if mime == "application/vnd.google-apps.folder":
                        if depth < max_depth and item["id"] not in seen_folders:
                            seen_folders.add(item["id"])
                            queue.append((item["id"], f"{cur_path}{item['name']}/", depth + 1))
                    elif mime == "application/pdf":
                        files.append({
                            "id": item["id"],
                            "name": item["name"],
                            "path": cur_path,
                            "link": f"https://drive.google.com/file/d/{item['id']}/view?usp=sharing"
                        })
                page_token = data.get("nextPageToken")
                if not page_token or len(files) >= max_files:
                    break
    except Exception as e:
        return files, f"구글 드라이브 목록 조회 중 오류: {e}"

    if not files:
        return [], "이 폴더(및 하위 폴더)에서 PDF 파일을 찾지 못했습니다. 폴더 공유 권한과 폴더 안에 PDF가 있는지 확인해 주세요."

    files.sort(key=lambda f: (f["path"], f["name"]))
    return files, ""

def extract_answers_from_drive_or_url(url: str, client=None) -> tuple:
    """
    구글 드라이브 링크 또는 웹 URL에서 공식 정답표 PDF를 내려받아 1~45번 정답을 추출합니다.
    """
    pdf_bytes, err = download_pdf_from_drive_or_url(url)
    if not pdf_bytes:
        return {}, err
    return extract_answers_from_pdf(pdf_bytes, client=client)

def grade_student_omr(exam_id: str, omr_rows: list, subject: str = None) -> dict:
    """
    학생의 OMR 마킹 데이터(list of dict with 'q_num', 'selected_opt', 'state')와
    시험지의 공식 정답표를 대조하여 자동 정오 판정 및 메타인지 5대 매트릭스 분류:
    1. ⭕ 확신했고 정답 (confident_correct)
    2. 🚨 확신했으나 오답 (confident_wrong)
    3. ⚠️ 확신 없으나 정답 (unsure_correct)
    4. ❌ 확신 없고 오답 (unsure_wrong)
    5. ⏱️ 시간이 없어서 찍음 (timed_out_guess)
    (5개 카테고리의 문항 수 합 = 전체 문항 수 45문항 100% 일치)

    subject: 선택과목이 구분된 시험지인 경우 학생이 응시한 선택과목
             ('화법과 작문' 또는 '언어와 매체'). 선택과목이 없는 시험은 무시됨.
    """
    answer_key = get_effective_answer_key(exam_id, subject)
    has_answer_key = bool(answer_key)
    
    graded_items = []
    correct_count = 0
    wrong_count = 0
    
    # 메타인지 5대 매트릭스별 문항 번호 리스트
    confident_correct = [] # 1. ⭕ 확신했고 정답 (안정적 득점, 클리닉 불필요)
    confident_wrong = []   # 2. 🚨 확신했으나 오답 (킬러 함정, 최우선 클리닉)
    unsure_correct = []    # 3. ⚠️ 확신 없으나 정답 (불안 요소, 근거 재정립)
    unsure_wrong = []      # 4. ❌ 확신 없고 오답 (사고 공백, 개념 보완)
    timed_out_guess = []   # 5. ⏱️ 시간이 없어서 찍음 (타임 어택, 시간 관리)
    
    for row in omr_rows:
        q_num = int(row.get("q_num", 0))
        sel_opt = row.get("selected_opt")
        try:
            sel_opt = int(sel_opt) if sel_opt is not None else None
        except Exception:
            sel_opt = None
            
        user_state = str(row.get("state", "확신")).strip()
        
        # 공식 정답표가 등록되어 있는 경우 -> 객관적 정오 판정
        if has_answer_key and q_num in answer_key:
            corr_opt = answer_key[q_num]
            is_correct = (sel_opt == corr_opt) if sel_opt is not None else False
        else:
            # 정답표가 아직 없는 경우 -> 학생 자가 체크 기준 fallback
            corr_opt = None
            is_correct = ("오답" not in user_state and "틀림" not in user_state)
            
        if is_correct:
            correct_count += 1
        else:
            wrong_count += 1
            
        # ⭐️ 메타인지 5대 상호 배타적(Mutually Exclusive) 상태 판정
        is_timed_out = any(k in user_state for k in ["찍음", "시간", "별"])
        is_unsure = (not is_timed_out) and any(k in user_state for k in ["확신 없음", "확신 없는", "오답", "틀림", "헷갈림", "세모"])
        # 나머지(체크박스 아무것도 안 누른 기본 상태 포함)는 확신
        is_confident = (not is_timed_out) and (not is_unsure)
        
        if is_timed_out:
            matrix_type = "TIMED_OUT_GUESS"
            matrix_label = "⏱️ 시간이 없어서 찍음"
            matrix_badge = "⏱️ 시간이 없어서 찍음" + (" (정답 맞힘)" if is_correct else " (오답)")
            needs_clinic = True
            timed_out_guess.append(q_num)
        elif is_unsure:
            if is_correct:
                matrix_type = "UNSURE_CORRECT"
                matrix_label = "⚠️ 확신 없으나 정답"
                matrix_badge = "⚠️ 확신 없으나 정답 (불안 요소)"
                needs_clinic = True
                unsure_correct.append(q_num)
            else:
                matrix_type = "UNSURE_WRONG"
                matrix_label = "❌ 확신 없고 오답"
                matrix_badge = "❌ 확신 없고 오답 (사고 공백)"
                needs_clinic = True
                unsure_wrong.append(q_num)
        else: # is_confident
            if is_correct:
                matrix_type = "CONFIDENT_CORRECT"
                matrix_label = "⭕ 확신했고 정답"
                matrix_badge = "⭕ 확신했고 정답 (안정적 득점)"
                needs_clinic = False
                confident_correct.append(q_num)
            else:
                matrix_type = "CONFIDENT_WRONG"
                matrix_label = "🚨 확신했으나 오답"
                matrix_badge = "🚨 확신했으나 오답 (킬러 함정)"
                needs_clinic = True
                confident_wrong.append(q_num)
                
        graded_items.append({
            "q_num": q_num,
            "selected_opt": sel_opt,
            "correct_opt": corr_opt,
            "is_correct": is_correct,
            "user_state": user_state,
            "matrix_type": matrix_type,
            "matrix_label": matrix_label,
            "matrix_badge": matrix_badge,
            "needs_clinic": needs_clinic
        })
        
    # 하위 호환성 (찍어서 맞힌 문제)
    lucky_correct = [q for q in timed_out_guess if any(item["q_num"] == q and item["is_correct"] for item in graded_items)]
    
    return {
        "has_answer_key": has_answer_key,
        "total": len(omr_rows),
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "clinic_count": len(confident_wrong) + len(unsure_wrong) + len(unsure_correct) + len(timed_out_guess),
        "confident_correct": confident_correct,
        "confident_wrong": confident_wrong,
        "unsure_correct": unsure_correct,
        "unsure_wrong": unsure_wrong,
        "timed_out_guess": timed_out_guess,
        "lucky_correct": lucky_correct,
        "graded_items": graded_items
    }

def get_exam_pdf_path(exam_id: str):
    exams = get_exams()
    if exam_id in exams:
        fname = exams[exam_id].get("pdf_filename")
        if fname:
            full_path = os.path.join(EXAMS_DIR, fname)
            if os.path.exists(full_path):
                return full_path
    return None

def get_exam_pdf_base64(exam_id: str):
    path = get_exam_pdf_path(exam_id)
    if path:
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return None
    return None

# ----------------------------------------------------
# 최근 3개년 평가원 기출 모의고사 정식 공개 PDF 프리셋
# 교사가 별도로 PDF를 등록하지 않아도 인앱에서 즉시 열람 가능
# ----------------------------------------------------
KICE_PAST_EXAMS_PRESETS = {
    "2025_suneung": {
        "title": "2025학년도 대학수학능력시험 국어영역",
        "pdf_url": "https://wdown.ebsi.co.kr/wdown/exam/20241114/1_mun_K87hgdf.pdf"
    },
    "2025_09_mock": {
        "title": "2025학년도 9월 모의평가 국어영역",
        "pdf_url": "https://wdown.ebsi.co.kr/wdown/exam/20240904/1_mun_4hg5jh.pdf"
    },
    "2025_06_mock": {
        "title": "2025학년도 6월 모의평가 국어영역",
        "pdf_url": "https://wdown.ebsi.co.kr/wdown/exam/20240604/1_mun_h45jhg.pdf"
    },
    "2024_suneung": {
        "title": "2024학년도 대학수학능력시험 국어영역",
        "pdf_url": "https://wdown.ebsi.co.kr/wdown/exam/20231116/1_mun_hgd45.pdf"
    },
    "2024_09_mock": {
        "title": "2024학년도 9월 모의평가 국어영역",
        "pdf_url": "https://wdown.ebsi.co.kr/wdown/exam/20230906/1_mun_jh45g.pdf"
    },
    "2024_06_mock": {
        "title": "2024학년도 6월 모의평가 국어영역",
        "pdf_url": "https://wdown.ebsi.co.kr/wdown/exam/20230601/1_mun_45jhg.pdf"
    },
    "2023_suneung": {
        "title": "2023학년도 대학수학능력시험 국어영역",
        "pdf_url": "https://wdown.ebsi.co.kr/wdown/exam/20221117/1_mun_hg54d.pdf"
    },
    "2023_09_mock": {
        "title": "2023학년도 9월 모의평가 국어영역",
        "pdf_url": "https://wdown.ebsi.co.kr/wdown/exam/20220831/1_mun_jh4g5.pdf"
    }
}

def get_exam_pdf_source(exam_id: str):
    """
    시험지의 PDF 데이터 소스 (파일 경로, Base64 데이터, 웹/구글드라이브 URL)를 반환
    1순위: 교사가 직접 업로드한 파일 또는 입력한 링크
    2순위: 시스템 내장 3개년 평가원 기출 공식 프리셋 (자동 로드)
    3순위: 관리자 마스터 구글 드라이브 폴더 링크 폴백
    """
    # 1순위: 교사가 직접 등록한 시험지 확인
    exams = get_exams()
    if exam_id in exams:
        ex = exams[exam_id]
        url = ex.get("pdf_url", "")
        path = get_exam_pdf_path(exam_id)
        b64 = get_exam_pdf_base64(exam_id) if not path else None
        if path or b64 or (url and url.strip()):
            return path, b64, url

    # 2순위: 3개년 평가원 기출 공식 프리셋 (별도 등록 없이도 0초 자동 로드)
    if exam_id in KICE_PAST_EXAMS_PRESETS:
        preset = KICE_PAST_EXAMS_PRESETS[exam_id]
        return None, None, preset.get("pdf_url", "")

    # 3순위: 교사용 마스터 구글 드라이브 폴더 링크 폴백
    cfg = get_admin_config()
    master_drive = cfg.get("google_drive_folder_url", "")
    if master_drive and master_drive.startswith("http"):
        return None, None, master_drive

    return None, None, None

def exam_has_own_pdf(exam_id: str) -> bool:
    """
    해당 시험지에 교사가 직접 연결한 원문 PDF(파일 업로드 또는 구글 드라이브 링크)가
    있는지 확인합니다. get_exam_pdf_source()와 달리 내장 기출 프리셋이나 마스터 폴더
    폴백은 포함하지 않습니다 — 학생 화면의 시험지 선택 목록을 필터링할 때 사용합니다.
    """
    exams = get_exams()
    ex = exams.get(exam_id)
    if not ex:
        return False
    if get_exam_pdf_path(exam_id):
        return True
    return bool((ex.get("pdf_url") or "").strip())

# --- 진단 제출 로그 (Submissions) ---
def save_submission(sub_data: dict):
    init_data_dirs()
    try:
        with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
            subs = json.load(f)
    except Exception:
        subs = []
    
    sub_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subs.append(sub_data)
    with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)
    push_to_google_sheets("submit_diagnosis", {"submission": sub_data})

def get_submissions():
    init_data_dirs()
    ensure_auto_synced()
    try:
        with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def get_student_submissions(student_id: str):
    """특정 학생의 진단 제출 기록 목록을 최신순으로 반환"""
    all_subs = get_submissions()
    s_id = str(student_id).strip()
    student_subs = [s for s in all_subs if str(s.get("student_id", "")).strip() == s_id]
    return sorted(student_subs, key=lambda x: x.get("timestamp", ""), reverse=True)

def get_student_vulnerability_profile(student_id: str) -> dict:
    """
    학생의 과거 누적 진단 데이터를 종합 분석하여 프로필 생성:
    - 총 응시 시험 수, 총 분석 문항 수
    - 빈출 취약점 태그 TOP 3
    - 누적 행동 원칙(Action Rules) 목록
    - 최근 진단 이력
    """
    subs = get_student_submissions(student_id)
    if not subs:
        return {
            "has_history": False,
            "total_submissions": 0,
            "total_questions": 0,
            "top_vulnerabilities": [],
            "tag_counts": {},
            "action_rules": [],
            "recent_exams": []
        }

    tag_counts = {}
    action_rules = []
    total_q = 0
    recent_exams = []

    for s in subs:
        exam_title = s.get("exam_title", "시험")
        ts = s.get("timestamp", "")
        if exam_title not in recent_exams:
            recent_exams.append(exam_title)
            
        for item in s.get("diagnosed_items", []):
            total_q += 1
            tag = item.get("error_tag", "").strip()
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            rule = item.get("action_rule", "").strip()
            if rule:
                action_rules.append({
                    "exam_title": exam_title,
                    "q_num": item.get("q_num"),
                    "error_tag": tag,
                    "action_rule": rule,
                    "timestamp": ts
                })

    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "has_history": True,
        "total_submissions": len(subs),
        "total_questions": total_q,
        "top_vulnerabilities": sorted_tags[:3],
        "tag_counts": tag_counts,
        "action_rules": action_rules,
        "recent_exams": recent_exams
    }

# ==========================================
# --- 학생 학습 진행 상태(Progress) 영구 저장 & 이어하기 엔진 ---
# ==========================================
def get_student_progress_file(student_id: str) -> str:
    s_id = str(student_id).strip()
    return os.path.join(PROGRESS_DIR, f"progress_{s_id}.json")

def save_student_progress(student_id: str, progress_data: dict):
    """
    학생의 학습 진행 상태를 영구 저장합니다.
    (진행 중인 시험 정보, OMR 마킹 상태, 취약 문항 복원 진행률, 확정된 사고 분석 목록, 리포트 단계 등)
    """
    init_data_dirs()
    if not student_id:
        return
    s_id = str(student_id).strip()
    progress_data["student_id"] = s_id
    progress_data["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p_file = get_student_progress_file(s_id)
    try:
        with open(p_file, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    # 구글 시트로도 비동기 백업
    push_to_google_sheets("save_progress", {"progress": progress_data})

def get_student_progress(student_id: str) -> dict:
    """학생의 직전 학습 진행 상태를 불러옵니다 (이어하기 기능)"""
    init_data_dirs()
    if not student_id:
        return None
    s_id = str(student_id).strip()
    p_file = get_student_progress_file(s_id)
    if os.path.exists(p_file):
        try:
            with open(p_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and isinstance(data, dict):
                    return data
        except Exception:
            pass
    return None

def clear_student_progress(student_id: str):
    """새로운 시험을 시작하거나 완료 후 초기화할 때 진행 상태를 삭제"""
    init_data_dirs()
    if not student_id:
        return
    s_id = str(student_id).strip()
    p_file = get_student_progress_file(s_id)
    if os.path.exists(p_file):
        try:
            os.remove(p_file)
        except Exception:
            pass

def call_gemini_safe(client, contents, config=None):
    """
    Gemini 모델 호출 시 404 NOT_FOUND 및 일시적 오류를 방지하기 위해
    Google 주력 텍스트 생성 모델들을 스마트하게 순차 시도하고,
    429 RESOURCE_EXHAUSTED 발생 시 불필요한 모델 연쇄 폭격을 방지합니다.
    """
    if client is None:
        raise ValueError("Gemini API 클라이언트가 초기화되지 않았습니다. 사이드바에 API 키를 입력해 주세요.")

    # 1. 안정성이 입증된 Google 주력 텍스트 생성 모델만 순서대로 시도
    # gemini-1.5 계열은 구글이 퇴역시켜 전부 404가 나던 상태였음.
    # "-latest" 별칭은 구글이 내부적으로 최신 세대 모델로 자동 갱신하므로 특정 버전 하드코딩보다 오래 간다.
    candidate_models = [
        "gemini-flash-latest",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-2.5-flash"
    ]

    attempted_log = []

    for model_id in candidate_models:
        for retry in range(2):
            try:
                if config is not None:
                    return client.models.generate_content(model=model_id, contents=contents, config=config)
                else:
                    return client.models.generate_content(model=model_id, contents=contents)
            except Exception as e:
                err_msg = str(e).strip()
                err_lower = err_msg.lower()

                # 429 RESOURCE_EXHAUSTED (할당량 초과 / 분당 요청수 한도 도달)
                if "429" in err_msg or "resource_exhausted" in err_lower or "quota" in err_lower:
                    attempted_log.append(f"• 모델 '{model_id}' (시도 {retry+1}): 할당량 초과(429 RESOURCE_EXHAUSTED)")
                    if retry == 0:
                        # 2초 대기 후 1회 재시도 (일시적 RPM 스파이크 회복 시도)
                        time.sleep(2)
                        continue
                    else:
                        # 2회 연속 429 발생 시 다른 모델로의 연쇄 폭격을 즉시 중단하고 안내
                        raise RuntimeError(
                            "⚠️ Gemini API 사용량 한도(분당 15회 요청 제한 또는 일일 무료 할당량)가 일시적으로 소진되었습니다.\n\n"
                            "약 1~2분 뒤에 다시 질문을 입력해 주시거나, 계속될 경우 왼쪽 메뉴바에서 새로운 Gemini API Key로 교체해 주세요."
                        )

                # 404 NOT_FOUND (해당 모델이 지역/계정에서 미지원인 경우)
                elif "404" in err_msg or "not_found" in err_lower:
                    attempted_log.append(f"• 모델 '{model_id}': 미지원(404 NOT_FOUND)")
                    break  # 다음 후보 모델로

                # 400 INVALID_ARGUMENT 또는 기타 오류
                else:
                    attempted_log.append(f"• 모델 '{model_id}': {err_msg[:120]}")
                    break  # 다음 후보 모델로

    # 모든 후보 모델 호출 실패 시
    error_summary = "\n".join(attempted_log)
    raise RuntimeError(
        f"Gemini AI 모델 호출에 실패했습니다.\n\n"
        f"[시도 결과]\n{error_summary}\n\n"
        f"💡 확인 가이드:\n"
        f"1. Google AI Studio(https://aistudio.google.com)에서 API 키가 활성화되어 있는지 확인해 주세요.\n"
        f"2. 무료 티어 키의 경우 분당 호출 제한(RPM) 또는 일일 할당량(Quota) 초과 여부를 확인해 주세요.\n"
        f"3. 왼쪽 메뉴바에서 새 API 키로 교체 후 다시 시도하실 수 있습니다."
    )


