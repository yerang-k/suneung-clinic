# suneung-clinic/ — 수능 국어 사고 복원 클리닉 2.0 (Streamlit)

원본은 GitHub `yerang-k/suneung-clinic`. **Antigravity(다른 AI 코딩 도구)에서 작업하던 프로젝트라 이 저장소에는 CLAUDE.md가 없었음** — 이 파일은 클론 후 Claude Code용으로 새로 작성한 것.

## 개요
모의고사 오답을 AI 소크라테스 인터뷰로 복원시키는 학생/교사용 Streamlit 웹앱. 학생은 OMR 형태로 1~45번 상태(확신/오답/찍음 등)를 입력하면 취약 문항만 골라 실제 시험지 PDF와 함께 Gemini AI 인터뷰 큐로 들어간다.

## 기술 스택 & 실행
- Python + Streamlit (`app.py`가 엔트리포인트), Gemini API(`google-genai`), PDF 처리는 `pypdfium2`/`pypdf`.
- 로컬 실행: `pip install -r requirements.txt` → `streamlit run app.py`
- Streamlit Cloud 배포 시 Secrets에 `GEMINI_API_KEY` 등록.

## 파일 구성
- `app.py`: 라우팅/진입점
- `student_view.py`: 학생 플로우 (가장 큰 파일, OMR 입력 → 인터뷰 → 방어 훈련)
- `admin_view.py`: 교사 관리자 모드 (학생/시험지 등록, 로그 열람)
- `data_manager.py`: 데이터 읽기/쓰기, 구글 드라이브 PDF 다운로드·정답표 추출 로직
- `prescription_engine.py`: AI 인터뷰/함정 분석 프롬프트·로직
- `pdf_viewer.py`: PDF 뷰어 컴포넌트
- `gas/Code.gs`: 구글 스프레드시트를 클라우드 DB로 쓰기 위한 백엔드. **재배포 시 "새 배포"가 아니라 기존 배포 수정으로 URL 유지할 것** (다른 GAS 프로젝트와 동일한 원칙, 최상위 CLAUDE.md 참고).
- `data/`: 로컬 데이터 (exams, students.json, submissions.json, admin_config.json). `data/user_config.json`은 gitignore됨 — 개인 설정이라 커밋 금지.

## 함정 포인트
- 구글 드라이브 폴더 연동(`google_drive_folder_url`)과 Gemini API 키는 교사용 관리자 모드 또는 Streamlit Secrets에서 설정하는 값이라 코드에 하드코딩된 게 없음. 로컬 테스트 시 `data/admin_config.json` 값을 확인할 것.
- 학생 개인정보(제출 로그 등)가 `data/submissions.json`에 로컬 저장됨 — 최상위 CLAUDE.md 원칙대로 제3자 서버 저장 금지, 구글 워크스페이스 연동만 예외.
