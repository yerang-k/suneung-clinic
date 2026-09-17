import os
import json
import base64
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STUDENTS_FILE = os.path.join(DATA_DIR, "students.json")
CONFIG_FILE = os.path.join(DATA_DIR, "admin_config.json")
EXAMS_DIR = os.path.join(DATA_DIR, "exams")
EXAMS_META_FILE = os.path.join(EXAMS_DIR, "exams_meta.json")
SUBMISSIONS_FILE = os.path.join(DATA_DIR, "submissions.json")

DEFAULT_CONFIG = {
    "admin_password": "teacher1234",
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
    
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            
    if not os.path.exists(STUDENTS_FILE):
        with open(STUDENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STUDENTS, f, ensure_ascii=False, indent=2)
            
    if not os.path.exists(EXAMS_META_FILE):
        with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_EXAMS, f, ensure_ascii=False, indent=2)
            
    if not os.path.exists(SUBMISSIONS_FILE):
        with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

# --- 설정 (Config) ---
def get_admin_config():
    init_data_dirs()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG

def save_admin_config(config):
    init_data_dirs()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def verify_admin_password(password: str) -> bool:
    cfg = get_admin_config()
    return cfg.get("admin_password") == password

# --- 학생 관리 (Students) ---
def get_students():
    init_data_dirs()
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
    for s in students:
        if s["student_id"] == student_id:
            s["name"] = name
            s["password"] = password
            save_students(students)
            return True, "학생 정보가 업데이트되었습니다."
    students.append({"student_id": student_id, "name": name, "password": password})
    save_students(students)
    return True, "새 학생이 등록되었습니다."

def delete_student(student_id: str):
    students = get_students()
    filtered = [s for s in students if s["student_id"] != student_id]
    if len(filtered) != len(students):
        save_students(filtered)
        return True, "학생이 삭제되었습니다."
    return False, "해당 학번의 학생을 찾을 수 없습니다."

def verify_student(student_id: str, name: str, password: str):
    students = get_students()
    for s in students:
        if s["student_id"].strip() == student_id.strip():
            if s["name"].strip() == name.strip() and s["password"].strip() == password.strip():
                return True, s
            return False, "이름 또는 비밀번호가 일치하지 않습니다."
    return False, "등록되지 않은 학번입니다. 교사에게 문의하세요."

# --- 시험 및 PDF 관리 (Exams) ---
def get_exams():
    init_data_dirs()
    try:
        with open(EXAMS_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_EXAMS

def save_exam(exam_id: str, title: str, total_questions: int, pdf_bytes: bytes = None, filename: str = None):
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

    exams[exam_id] = {
        "exam_id": exam_id,
        "title": title,
        "total_questions": int(total_questions),
        "pdf_filename": pdf_save_name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    with open(EXAMS_META_FILE, "w", encoding="utf-8") as f:
        json.dump(exams, f, ensure_ascii=False, indent=2)
    return True, "시험지가 성공적으로 등록되었습니다."

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

def get_submissions():
    init_data_dirs()
    try:
        with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
