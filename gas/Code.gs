/**
 * 수능 국어 사고 복원 클리닉 - Google Sheets & Drive 클라우드 백엔드
 * 
 * [설치 방법]
 * 1. 새 구글 스프레드시트 생성 (이름: 수능 국어 사고 복원 클리닉 DB)
 * 2. 메뉴 [확장 프로그램] -> [Apps Script] 클릭
 * 3. 이 코드 전체를 Code.gs에 붙여넣기 후 상단 저장(Ctrl+S)
 * 4. 상단 함수 선택 드롭다운에서 'setup' 선택 후 [실행] 클릭 (권한 승인)
 * 5. 우측 상단 [배포] -> [새 배포] 클릭
 *    - 유형: 웹 앱
 *    - 설명: 1.0
 *    - 다음 사용자 권한으로 실행: 나(내 계정)
 *    - 액세스 권한: 모든 사용자 (Anyone)  <-- 중요!
 * 6. 생성된 '웹 앱 URL'(https://script.google.com/macros/s/.../exec)을 복사하여
 *    앱의 [교사용 관리자 모드] -> [마스터 연동] 또는 Streamlit Secrets에 등록하세요.
 */

function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  
  // 1. Config 시트
  let sCfg = ss.getSheetByName("Config");
  if (!sCfg) {
    sCfg = ss.insertSheet("Config");
    sCfg.appendRow(["key", "value"]);
    sCfg.appendRow(["admin_password", "teacher1234"]);
    sCfg.appendRow(["gemini_api_key", ""]);
    sCfg.appendRow(["google_drive_folder_url", ""]);
  }
  
  // 2. Exams 시트
  let sExams = ss.getSheetByName("Exams");
  if (!sExams) {
    sExams = ss.insertSheet("Exams");
    sExams.appendRow(["exam_id", "title", "total_questions", "pdf_url", "created_at"]);
    // 기본 시험지 샘플 행
    sExams.appendRow(["2027_06_mock", "2027학년도 6월 모의평가 국어영역", 45, "", "2026-06-01"]);
    sExams.appendRow(["2025_09_mock", "2025학년도 9월 모의평가 국어영역", 45, "", "2024-09-04"]);
    sExams.appendRow(["2024_suneung", "2024학년도 대학수학능력시험 국어영역", 45, "", "2023-11-16"]);
    sExams.appendRow(["2024_06_mock", "2024학년도 6월 모의평가 국어영역", 45, "", "2023-06-01"]);
    sExams.appendRow(["2025_suneung", "2025학년도 대학수학능력시험 국어영역", 45, "", "2024-11-14"]);
  }
  
  // 3. Students 시트
  let sStu = ss.getSheetByName("Students");
  if (!sStu) {
    sStu = ss.insertSheet("Students");
    sStu.appendRow(["student_id", "name", "password"]);
    sStu.appendRow(["30101", "김수험", "1234"]);
    sStu.appendRow(["30102", "이국어", "1234"]);
    sStu.appendRow(["30103", "박수능", "1234"]);
  }
  
  // 4. Submissions 시트
  let sSubs = ss.getSheetByName("Submissions");
  if (!sSubs) {
    sSubs = ss.insertSheet("Submissions");
    sSubs.appendRow(["timestamp", "student_id", "student_name", "exam_id", "exam_title", "total_time", "time_pressure", "error_tags", "diagnosed_items_json"]);
  }
  
  // 기본 '시트1' 삭제 (비어있을 경우)
  const defaultSheet = ss.getSheetByName("시트1") || ss.getSheetByName("Sheet1");
  if (defaultSheet && ss.getSheets().length > 1) {
    try { ss.deleteSheet(defaultSheet); } catch(e) {}
  }
}

function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) ? e.parameter.action : "sync_all";
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    
    if (action === "sync_all") {
      const data = {
        config: readConfig_(ss),
        exams: readExams_(ss),
        students: readStudents_(ss),
        submissions: readSubmissions_(ss)
      };
      return ContentService.createTextOutput(JSON.stringify(data))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    return ContentService.createTextOutput(JSON.stringify({ status: "ok", message: "GAS Clinic Server Running" }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({ status: "error", message: "No post data" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    const payload = JSON.parse(e.postData.contents);
    const action = payload.action;
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    
    if (action === "save_exam") {
      saveExam_(ss, payload.exam);
    } else if (action === "delete_exam") {
      deleteExam_(ss, payload.exam_id);
    } else if (action === "save_student") {
      saveStudent_(ss, payload.student);
    } else if (action === "delete_student") {
      deleteStudent_(ss, payload.student_id);
    } else if (action === "save_config") {
      saveConfig_(ss, payload.config);
    } else if (action === "submit_diagnosis") {
      appendSubmission_(ss, payload.submission);
    } else if (action === "sync_push_all") {
      if (payload.exams) {
        overwriteExams_(ss, payload.exams);
      }
      if (payload.students) {
        overwriteStudents_(ss, payload.students);
      }
      if (payload.config) {
        saveConfig_(ss, payload.config);
      }
    }
    
    return ContentService.createTextOutput(JSON.stringify({ status: "success", action: action }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// --- 내부 헬퍼 함수 ---
function readConfig_(ss) {
  const s = ss.getSheetByName("Config");
  if (!s) return {};
  const rows = s.getDataRange().getValues();
  const cfg = {};
  for (let i = 1; i < rows.length; i++) {
    const k = String(rows[i][0]).trim();
    if (k) cfg[k] = rows[i][1];
  }
  return cfg;
}

function saveConfig_(ss, cfg) {
  let s = ss.getSheetByName("Config");
  if (!s) { setup(); s = ss.getSheetByName("Config"); }
  const rows = s.getDataRange().getValues();
  const existingKeys = {};
  for (let i = 1; i < rows.length; i++) {
    existingKeys[String(rows[i][0]).trim()] = i + 1;
  }
  
  for (let k in cfg) {
    if (k === "gas_api_url") continue;
    const val = String(cfg[k] || "").trim();
    if (existingKeys[k]) {
      s.getRange(existingKeys[k], 2).setValue(val);
    } else {
      s.appendRow([k, val]);
    }
  }
}

function readExams_(ss) {
  const s = ss.getSheetByName("Exams");
  if (!s) return {};
  const rows = s.getDataRange().getValues();
  const exams = {};
  for (let i = 1; i < rows.length; i++) {
    const exam_id = String(rows[i][0]).trim();
    if (!exam_id) continue;
    exams[exam_id] = {
      exam_id: exam_id,
      title: String(rows[i][1] || ""),
      total_questions: Number(rows[i][2] || 45),
      pdf_url: String(rows[i][3] || ""),
      created_at: String(rows[i][4] || "")
    };
  }
  return exams;
}

function saveExam_(ss, ex) {
  let s = ss.getSheetByName("Exams");
  if (!s) { setup(); s = ss.getSheetByName("Exams"); }
  const rows = s.getDataRange().getValues();
  const targetId = String(ex.exam_id).trim();
  let foundRow = -1;
  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][0]).trim() === targetId) {
      foundRow = i + 1;
      break;
    }
  }
  
  const totalQ = Number(ex.total_questions) || 45;
  const pdfUrl = String(ex.pdf_url || "").trim();
  const title = String(ex.title || "").trim();
  const createdAt = String(ex.created_at || new Date().toISOString().split("T")[0]);
  
  if (foundRow > 0) {
    s.getRange(foundRow, 2).setValue(title);
    s.getRange(foundRow, 3).setValue(totalQ);
    s.getRange(foundRow, 4).setValue(pdfUrl);
  } else {
    s.appendRow([targetId, title, totalQ, pdfUrl, createdAt]);
  }
}

function deleteExam_(ss, examId) {
  const s = ss.getSheetByName("Exams");
  if (!s) return;
  const rows = s.getDataRange().getValues();
  const targetId = String(examId).trim();
  for (let i = rows.length - 1; i >= 1; i--) {
    if (String(rows[i][0]).trim() === targetId) {
      s.deleteRow(i + 1);
    }
  }
}

function readStudents_(ss) {
  const s = ss.getSheetByName("Students");
  if (!s) return [];
  const rows = s.getDataRange().getValues();
  const list = [];
  for (let i = 1; i < rows.length; i++) {
    const sid = String(rows[i][0]).trim();
    if (!sid) continue;
    list.push({
      student_id: sid,
      name: String(rows[i][1] || "").trim(),
      password: String(rows[i][2] || "").trim()
    });
  }
  return list;
}

function saveStudent_(ss, stu) {
  let s = ss.getSheetByName("Students");
  if (!s) { setup(); s = ss.getSheetByName("Students"); }
  const rows = s.getDataRange().getValues();
  const targetId = String(stu.student_id).trim();
  let foundRow = -1;
  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][0]).trim() === targetId) {
      foundRow = i + 1;
      break;
    }
  }
  
  const name = String(stu.name || "").trim();
  const pw = String(stu.password || "").trim();
  if (foundRow > 0) {
    s.getRange(foundRow, 2).setValue(name);
    s.getRange(foundRow, 3).setValue(pw);
  } else {
    s.appendRow([targetId, name, pw]);
  }
}

function deleteStudent_(ss, studentId) {
  const s = ss.getSheetByName("Students");
  if (!s) return;
  const rows = s.getDataRange().getValues();
  const targetId = String(studentId).trim();
  for (let i = rows.length - 1; i >= 1; i--) {
    if (String(rows[i][0]).trim() === targetId) {
      s.deleteRow(i + 1);
    }
  }
}

function readSubmissions_(ss) {
  const s = ss.getSheetByName("Submissions");
  if (!s) return [];
  const rows = s.getDataRange().getValues();
  const list = [];
  for (let i = 1; i < rows.length; i++) {
    const ts = String(rows[i][0]).trim();
    if (!ts) continue;
    let diag = [];
    try {
      diag = JSON.parse(rows[i][8]);
    } catch(e) {}
    list.push({
      timestamp: ts,
      student_id: String(rows[i][1]),
      student_name: String(rows[i][2]),
      exam_id: String(rows[i][3]),
      exam_title: String(rows[i][4]),
      total_time: Number(rows[i][5]),
      time_pressure: String(rows[i][6]),
      error_tags: String(rows[i][7]).split(",").map(t => t.trim()).filter(Boolean),
      diagnosed_items: diag
    });
  }
  return list;
}

function appendSubmission_(ss, sub) {
  let s = ss.getSheetByName("Submissions");
  if (!s) { setup(); s = ss.getSheetByName("Submissions"); }
  const ts = sub.timestamp || Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd HH:mm:ss");
  const tags = Array.isArray(sub.error_tags) ? sub.error_tags.join(", ") : String(sub.error_tags || "");
  const diagJson = JSON.stringify(sub.diagnosed_items || []);
  
  s.appendRow([
    ts,
    String(sub.student_id || ""),
    String(sub.student_name || ""),
    String(sub.exam_id || ""),
    String(sub.exam_title || ""),
    Number(sub.total_time || 80),
    String(sub.time_pressure || ""),
    tags,
    diagJson
  ]);
}
