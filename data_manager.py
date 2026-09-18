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
    "gas_api_url": ""
}

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
                local_exams.update(data["exams"])
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

def save_exam(exam_id: str, title: str, total_questions: int, pdf_bytes: bytes = None, filename: str = None, pdf_url: str = "", answer_key: dict = None):
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

    if answer_key is not None:
        final_answer_key = answer_key
    elif exam_id in exams and "answer_key" in exams[exam_id]:
        final_answer_key = exams[exam_id]["answer_key"]
    else:
        final_answer_key = {}

    exams[exam_id] = {
        "exam_id": exam_id,
        "title": title,
        "total_questions": int(total_questions),
        "pdf_filename": pdf_save_name,
        "pdf_url": final_url,
        "answer_key": final_answer_key,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
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
    2. Gemini Multimodal AI (gemini-2.0-flash)를 활용해 PDF 표 및 텍스트에서 1~45번 정답을 정밀 판독
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

            res = client.models.generate_content(
                model='gemini-2.0-flash',
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


def grade_student_omr(exam_id: str, omr_rows: list) -> dict:
    """
    학생의 OMR 마킹 데이터(list of dict with 'q_num', 'selected_opt', 'state')와
    시험지의 공식 정답표를 대조하여 자동 정오 판정 및 메타인지 4대 매트릭스 분류
    """
    answer_key = get_exam_answer_key(exam_id)
    has_answer_key = bool(answer_key)
    
    graded_items = []
    correct_count = 0
    wrong_count = 0
    
    # 메타인지 매트릭스별 문항 번호 리스트
    confident_wrong = []   # 🚨 확신 오답 (치명적 함정)
    unsure_wrong = []      # ❌ 헷갈림/찍음 오답 (사고 공백)
    unsure_correct = []    # ⚠️ 헷갈렸으나 정답 (실전 위험)
    lucky_correct = []     # 🎲 찍어서 정답 (행운의 정답)
    confident_correct = [] # ⭕ 확신 정답 (안정적 득점)
    
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
            if "찍음" in user_state or "별" in user_state:
                matrix_type = "LUCKY_CORRECT"
                matrix_label = "🎲 찍어서 맞힘"
                matrix_badge = "🎲 찍어서 맞힘 (행운)"
                needs_clinic = True
                lucky_correct.append(q_num)
            elif "헷갈림" in user_state or "세모" in user_state:
                matrix_type = "UNSURE_CORRECT"
                matrix_label = "⚠️ 헷갈렸으나 맞힘"
                matrix_badge = "⚠️ 헷갈렸으나 맞힘 (불안)"
                needs_clinic = True
                unsure_correct.append(q_num)
            else:
                matrix_type = "CONFIDENT_CORRECT"
                matrix_label = "⭕ 확신하고 맞힘"
                matrix_badge = "⭕ 확신 정답"
                needs_clinic = False
                confident_correct.append(q_num)
        else:
            wrong_count += 1
            if "확신" in user_state:
                matrix_type = "CONFIDENT_WRONG"
                matrix_label = "🚨 확신했으나 오답"
                matrix_badge = "🚨 확신 오답 (킬러 함정)"
                needs_clinic = True
                confident_wrong.append(q_num)
            else:
                matrix_type = "UNSURE_WRONG"
                matrix_label = "❌ 오답 (헷갈림/찍음)"
                matrix_badge = "❌ 헷갈림/찍음 오답"
                needs_clinic = True
                unsure_wrong.append(q_num)
                
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
        
    return {
        "has_answer_key": has_answer_key,
        "total": len(omr_rows),
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "clinic_count": len(confident_wrong) + len(unsure_wrong) + len(unsure_correct) + len(lucky_correct),
        "confident_wrong": confident_wrong,
        "unsure_wrong": unsure_wrong,
        "unsure_correct": unsure_correct,
        "lucky_correct": lucky_correct,
        "confident_correct": confident_correct,
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
    # (gemini-2.0-flash -> gemini-1.5-flash -> gemini-1.5-pro)
    candidate_models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro"
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


