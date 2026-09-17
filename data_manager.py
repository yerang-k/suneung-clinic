import os
import json
import base64
import threading
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

DEFAULT_EXAMS = {
    "2027_06_mock": {
        "exam_id": "2027_06_mock",
        "title": "2027학년도 6월 모의평가 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "created_at": "2026-06-01"
    },
    "2025_09_mock": {
        "exam_id": "2025_09_mock",
        "title": "2025학년도 9월 모의평가 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "created_at": "2024-09-04"
    },
    "2024_suneung": {
        "exam_id": "2024_suneung",
        "title": "2024학년도 대학수학능력시험 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "created_at": "2023-11-16"
    },
    "2024_06_mock": {
        "exam_id": "2024_06_mock",
        "title": "2024학년도 6월 모의평가 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "created_at": "2023-06-01"
    },
    "2025_suneung": {
        "exam_id": "2025_suneung",
        "title": "2025학년도 대학수학능력시험 국어영역",
        "total_questions": 45,
        "pdf_filename": "",
        "created_at": "2024-11-14"
    }
}

def init_data_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(EXAMS_DIR, exist_ok=True)
    
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
    return cfg.get("admin_password") == password

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

def save_exam(exam_id: str, title: str, total_questions: int, pdf_bytes: bytes = None, filename: str = None, pdf_url: str = ""):
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
    final_url = pdf_url.strip() if pdf_url else existing_url

    exams[exam_id] = {
        "exam_id": exam_id,
        "title": title,
        "total_questions": int(total_questions),
        "pdf_filename": pdf_save_name,
        "pdf_url": final_url,
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

def get_exam_pdf_source(exam_id: str):
    """시험지의 PDF 데이터 소스 (파일 경로, Base64 데이터, 웹/구글드라이브 URL)를 반환"""
    exams = get_exams()
    if exam_id in exams:
        ex = exams[exam_id]
        url = ex.get("pdf_url", "")
        path = get_exam_pdf_path(exam_id)
        b64 = get_exam_pdf_base64(exam_id) if not path else None
        return path, b64, url
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

def call_gemini_safe(client, contents, config=None):
    """
    Gemini 모델 호출 시 404 NOT_FOUND 및 일시적 오류를 방지하기 위해
    Google 주력 모델들을 스마트하게 순차 시도하고, 상세 진단 정보를 제공합니다.
    """
    if client is None:
        raise ValueError("Gemini API 클라이언트가 초기화되지 않았습니다. 사이드바에 API 키를 입력해 주세요.")

    # 1. 시도할 후보 모델 목록 (최신 2.5 및 2.0, 1.5 계열)
    default_candidates = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.0-flash-lite",
        "gemini-2.5-pro"
    ]

    candidate_models = list(default_candidates)

    # 2. 가능한 경우 API 키가 접근 가능한 실제 모델 목록을 동적으로 탐색
    try:
        available_models = []
        for m in client.models.list():
            m_name = getattr(m, "name", str(m)).replace("models/", "")
            if "gemini" in m_name.lower():
                available_models.append(m_name)
        if available_models:
            # 주력 모델 우선순위대로 정렬하여 재배치
            priority_order = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
            sorted_available = []
            for p in priority_order:
                if p in available_models:
                    sorted_available.append(p)
            for m_name in available_models:
                if m_name not in sorted_available:
                    sorted_available.append(m_name)
            if sorted_available:
                candidate_models = sorted_available
    except Exception:
        # models.list 권한이 없거나 제한된 키의 경우 기본 후보군 유지
        pass

    attempted_log = []
    
    for raw_m in candidate_models:
        model_id = raw_m.replace("models/", "").strip()
        try:
            if config is not None:
                return client.models.generate_content(model=model_id, contents=contents, config=config)
            else:
                return client.models.generate_content(model=model_id, contents=contents)
        except Exception as e:
            err_msg = str(e).strip()
            attempted_log.append(f"• 모델 '{model_id}': {err_msg}")
            # 404/NOT_FOUND/권한/일시적 오류 발생 시 다음 후보 모델 시도
            continue

    # 모든 후보 모델 호출 실패 시 상세한 원인 리포트 생성
    error_summary = "\n".join(attempted_log)
    raise RuntimeError(
        f"Gemini AI 모델 호출에 실패했습니다.\n\n"
        f"[시도한 모델 및 응답 결과]\n{error_summary}\n\n"
        f"💡 확인 가이드:\n"
        f"1. Google AI Studio(https://aistudio.google.com)에서 API 키가 활성화되어 있는지 확인해 주세요.\n"
        f"2. 무료 티어 키의 경우 분당 호출 제한(RPM) 또는 일일 할당량(Quota) 초과 여부를 확인해 주세요.\n"
        f"3. 왼쪽 사이드바에서 새 API 키로 교체 후 다시 시도하실 수 있습니다."
    )


