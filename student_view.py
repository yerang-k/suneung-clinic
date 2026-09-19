import streamlit as st
from datetime import datetime
import json
import re
import requests
import pandas as pd
from data_manager import (
    verify_student, get_exams, get_exam_pdf_base64,
    get_exam_pdf_source, get_admin_config, save_submission,
    get_student_submissions, get_student_vulnerability_profile,
    call_gemini_safe, save_student_progress, get_student_progress,
    clear_student_progress, get_effective_api_key,
    save_student_api_key, clear_student_api_key,
    grade_student_omr, get_exam_answer_key, get_sorted_exam_keys, exam_has_own_pdf,
    exam_is_elective, ELECTIVE_SUBJECTS
)
try:
    from pdf_viewer import render_pdf_viewer, render_csat_text_view
except Exception:
    def render_pdf_viewer(*args, **kwargs):
        st.info("📄 실물 시험지는 상단 원문 링크를 통해 새 창에서 확인하실 수 있습니다.")
    def render_csat_text_view(*args, **kwargs):
        pass
try:
    from pdf_viewer import (
        get_pdf_bytes_cached, get_pdf_total_pages_cached,
        get_page_for_question_cached, render_pdf_page_cached
    )
except Exception:
    get_pdf_bytes_cached = get_pdf_total_pages_cached = None
    get_page_for_question_cached = render_pdf_page_cached = None
from prescription_engine import (
    get_prescription_problems, evaluate_student_defense,
    find_indexed_problem, get_all_indexed_problems
)
from google.genai import types

# 6대 사고 오류 전 항목에 대한 기본 추천 기출 DB
RECOMMENDATION_DB = {
    "선지 임의 변형": [
        {"year": "2025학년도 9월", "q_num": 21, "mission": "선지의 서술어가 지문의 인과와 정확히 일치하는지 단어 단위로 끊어 검증할 것"},
        {"year": "2024학년도 수능", "q_num": 34, "mission": "내 상식으로 문맥을 보완하지 말고, 선지가 제시한 주어-목적어 관계만 확인할 것"}
    ],
    "선지 후반부 검증 생략": [
        {"year": "2024학년도 6월", "q_num": 15, "mission": "복합 선지의 앞부분(A)에 밑줄 긋고 참/거짓 판별 후, 뒷부분(B)을 독립적으로 검증할 것"},
        {"year": "2023학년도 수능", "q_num": 17, "mission": "전반부 수식어가 맞다고 해서 후반부 핵심 술어를 건너뛰지 말 것"}
    ],
    "기억 부재의 부재화": [
        {"year": "2024학년도 9월", "q_num": 8, "mission": "기억나지 않는다고 '틀린 선지'로 단정하지 말고, 반드시 지문 해당 단락으로 돌아가 눈으로 확인할 것"},
        {"year": "2025학년도 6월", "q_num": 12, "mission": "내 기억의 확신도와 실제 지문 텍스트는 다를 수 있음을 인정하고 근거 문장을 재탐색할 것"}
    ],
    "적용 조건 혼동": [
        {"year": "2025학년도 수능", "q_num": 10, "mission": "원리 지문에서 제시된 '전제 조건'과 '<보기>의 구체적 상황'을 1:1로 대응시킬 것"},
        {"year": "2024학년도 9월", "q_num": 14, "mission": "예외 조항과 기본 규칙의 적용 범위를 지문 기호로 명확히 분리할 것"}
    ],
    "관계어·논리 왜곡": [
        {"year": "2024학년도 수능", "q_num": 10, "mission": "지문의 'A일수록 B'라는 비례 관계를 'A이면 C'라는 인과 관계로 왜곡하지 말 것"},
        {"year": "2023학년도 9월", "q_num": 16, "mission": "필요조건과 충분조건, 주체와 대상의 전도 현상을 선지에서 역추적할 것"}
    ],
    "과잉 인과 생성": [
        {"year": "2025학년도 6월", "q_num": 31, "mission": "문학에서 시간적 인접성을 필연적 인과로 단정하지 말고, 선지의 연결 어미를 따져볼 것"},
        {"year": "2024학년도 6월", "q_num": 24, "mission": "작품 속 인물의 심리와 행동 사이에 지문에 없는 독자적 개연성을 부여하지 말 것"}
    ]
}

SAMPLE_QUESTIONS_TEXT = {
    4: {
        "q_num": 4,
        "genre": "독서 (독서론)",
        "topic": "초인지 독서 전략과 능동적 의미 구성",
        "passage": "독서는 글에 제시된 정보를 독자의 배경지식(스키마)과 결합하여 능동적으로 의미를 재구성하는 과정이다. 숙련된 독자는 글을 읽는 도중 자신의 이해 상태를 점검하는 상위인지(초인지) 전략을 유연하게 구사한다. 반면 초보 독자는 글의 표면적 어휘에만 집착하여 행간의 의미나 글쓴이의 숨겨진 집필 의도를 파악하는 데 어려움을 겪는다.",
        "question": "윗글을 바탕으로 할 때, 상위인지 독서 전략에 대한 설명으로 가장 적절하지 않은 것은?",
        "options": {
            1: "독자가 스스로 글에 대한 이해 여부를 평가하며 읽기 속도를 조절한다.",
            2: "배경지식만을 맹신하여 글쓴이가 전달하려는 새로운 사실을 무시한다.",
            3: "글의 표면적 진술 너머에 내재된 숨은 전제나 필자의 관점을 추론한다.",
            4: "이해되지 않는 단락을 만났을 때 앞 문맥으로 돌아가 재독하는 전략을 취한다.",
            5: "자신의 사전 지식과 텍스트의 정보를 상호 비교하며 능동적으로 의미를 형성한다."
        },
        "correct": 2,
        "trap_concept": "지문에서 긍정적으로 설명한 배경지식의 역할을 선지에서 '배경지식만 맹신하여 텍스트를 무시한다'는 극단적 왜곡으로 변조한 함정"
    },
    9: {
        "q_num": 9,
        "genre": "독서 (과학 물리)",
        "topic": "초전도 현상과 마이스너 효과",
        "passage": "초전도체는 임계 온도 이하로 냉각될 때 전기 저항이 완전히 0이 되는 '초전도 현상'과, 내부의 자기장을 밖으로 밀어내는 '마이스너 효과'를 동시에 나타낸다. 제1종 초전도체는 임계 자기장을 넘어서면 순식간에 초전도 상태를 상실하지만, 제2종 초전도체는 하부 임계 자기장과 상부 임계 자기장 사이에서 양자화된 소용돌이(보텍스) 형태로 자기장이 침투하는 혼합 상태를 유지하여 더 강한 자기장에서도 초전도성을 보존한다.",
        "question": "윗글의 초전도체에 대한 이해로 적절하지 않은 것은?",
        "options": {
            1: "제1종 초전도체는 임계 자기장보다 강한 자기장에서 즉시 상전도체로 전이된다.",
            2: "마이스너 효과는 초전도체 내부로 외부 자기선속이 자유롭게 통과하는 현상이다.",
            3: "제2종 초전도체는 혼합 상태에서 자기장의 일부 침투를 허용하면서도 초전도성을 유지한다.",
            4: "초전도 현상은 물질이 임계 온도보다 낮게 냉각될 때 전기 저항이 소멸하는 것을 의미한다.",
            5: "보텍스는 제2종 초전도체 내부를 관통하는 미세한 자기 소용돌이 구조이다."
        },
        "correct": 2,
        "trap_concept": "지문의 '자기장을 밖으로 밀어낸다'는 배척 특성을 선지에서 '자유롭게 통과한다'고 정반대로 서술한 함정"
    },
    14: {
        "q_num": 14,
        "genre": "독서 (기술)",
        "topic": "데이터 전송과 패리티 부호",
        "passage": "데이터 전송 과정에서 잡음으로 인한 비트 반전을 검출하기 위해 패리티 비트를 추가한다. 홀수 패리티 방식은 전체 비트 중 1의 개수가 홀수가 되도록 검사 비트를 할당하며, 전송 중 1비트의 오류가 발생하면 즉시 검출할 수 있으나 2비트 동시 반전 오류는 정상 데이터로 오인하는 한계를 지닌다.",
        "question": "윗글을 바탕으로 추론한 내용으로 가장 적절한 것은?",
        "options": {
            1: "홀수 패리티 방식은 2비트 오류가 발생했을 때 수신 측에서 재전송을 요청한다.",
            2: "패리티 비트는 데이터 비트의 위치 정보까지 파악하여 자체 교정을 수행한다.",
            3: "홀수 패리티를 적용한 8비트 데이터 프레임의 '1'의 총 개수는 항상 홀수여야 한다.",
            4: "잡음의 세기가 커질수록 패리티 비트의 검출 한계는 짝수 비트로 이동한다.",
            5: "비트 반전이 3번 일어난 경우 홀수 패리티 방식으로는 오류를 검출할 수 없다."
        },
        "correct": 3,
        "trap_concept": "2비트 동시 반전 시 검출 불가능한 한계를 무시하거나 자체 교정 능력이 없는 단순 패리티를 오류 정정 부호로 오해하도록 유도"
    },
    27: {
        "q_num": 27,
        "genre": "문학 (현대시)",
        "topic": "늦된 나무의 생태와 지연의 가치 성찰",
        "passage": "앞줄의 아름드리나무 그늘 속에 숨어 있는 늦된 나무는 햇빛을 받지 못해 꽃을 늦게 피운다. (중략) 나도 늦된 나무처럼 천천히, 그러나 단단하게 뿌리를 내리며 나만의 꽃을 준비하고 있다.",
        "question": "윗글에 대한 이해로 적절하지 않은 것은?",
        "options": {
            1: "그늘은 늦된 나무가 다른 나무들로부터 자신의 몸을 감추기 위해 선택한 공간이다.",
            2: "늦된 나무의 개화는 앞줄 나무들과의 생존 경쟁에서 비롯된 결과이다.",
            3: "화자는 늦된 나무의 생태를 관찰하며 자신의 삶에 대한 성찰을 이끌어내고 있다.",
            4: "아름드리나무는 늦된 나무와 대비되는 존재로, 외부적 환경의 한계를 상징한다.",
            5: "꽃을 늦게 피우는 현상을 통해 지연의 가치를 긍정적으로 인식하고 있다."
        },
        "correct": 1,
        "trap_concept": "지문에서 수동적 환경 조건(햇빛을 받지 못함)으로 제시된 '그늘'을, 늦된 나무가 능동적으로 '선택한 공간'인 것처럼 인과 주체를 왜곡함"
    }
}

def _load_exam_pdf_page(exam_id: str, q_num: int):
    """
    선생님이 연결한 실제 시험지 PDF에서 q_num번 문항이 있는 페이지를 찾아
    (페이지 번호, PDF 바이트, 페이지 이미지 JPEG 바이트)를 반환. 실패하면 None.
    """
    if not exam_id or not exam_has_own_pdf(exam_id) or get_pdf_bytes_cached is None:
        return None
    try:
        path, b64, url = get_exam_pdf_source(exam_id)
        pdf_bytes = get_pdf_bytes_cached(pdf_url=url, pdf_path=path, base64_pdf=b64)
        if not pdf_bytes:
            return None
        total = get_pdf_total_pages_cached(pdf_bytes)
        page = get_page_for_question_cached(pdf_bytes, q_num, total)
        img = render_pdf_page_cached(pdf_bytes, page - 1, scale=2.0)
        return page, pdf_bytes, img
    except Exception:
        return None

def extract_text_from_exam_pdf(exam_id: str, page_num: int):
    """로컬에 등록된 시험지 PDF가 있는 경우 해당 페이지 텍스트를 추출"""
    import os
    from data_manager import get_exam_pdf_path
    path = get_exam_pdf_path(exam_id)
    if not path or not os.path.exists(path):
        return None
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        if 1 <= page_num <= len(reader.pages):
            return reader.pages[page_num - 1].extract_text()
    except Exception:
        pass
    return None

def get_question_full_context(exam_info: dict, q_num: int):
    """
    해당 문항의 전체 지문, 발문, 선지, 정답, 함정 개념을 3중 체계로 조회합니다:
    1. prescription_engine의 6대 취약점 대표 기출 인덱스 (PAST_EXAM_QUESTION_INDEX)
    2. SAMPLE_QUESTIONS_TEXT (내장 수능 핵심 기출 DB)
    3. 로컬 PDF 파일 텍스트 추출 (있는 경우)
    """
    exam_id = exam_info.get("exam_id", "") if exam_info else ""
    # 선생님이 실제 시험지 PDF를 연결한 시험은, 문항 번호만 같은 '다른 시험'의 예시 문항을
    # 끌어다 쓰면 엉뚱한 내용이 되므로 내장 예시(2·번 조회)는 쓰지 않는다.
    # (이 경우 AI에는 실제 PDF 페이지 이미지를 함께 전달한다)
    has_real_pdf = exam_has_own_pdf(exam_id) if exam_id else False
    
    # 1. prescription_engine 기출 인덱스 검색
    prob = find_indexed_problem(exam_id, q_num)
    if prob and has_real_pdf and prob.get("exam_id") != exam_id:
        prob = None
    if prob and prob.get("passage"):
        opts = {}
        for k, v in prob.get("options", {}).items():
            try:
                opts[int(k)] = v
            except ValueError:
                opts[k] = v
        return {
            "q_num": q_num,
            "passage": prob["passage"],
            "question": prob.get("question", "윗글을 바탕으로 추론한 내용으로 가장 적절하지 않은 것은?"),
            "options": opts,
            "correct": prob.get("correct", 1),
            "trap_concept": prob.get("trap_concept", "지문 조건 왜곡 및 인과 전도"),
            "genre": prob.get("genre", "국어영역"),
            "topic": prob.get("topic", f"{q_num}번 문항 핵심 제재"),
            "mission": prob.get("mission", "선지의 서술어가 지문과 일치하는지 단어 단위로 검증할 것")
        }

    # 2. SAMPLE_QUESTIONS_TEXT 검색 (실제 PDF가 연결된 시험에서는 사용하지 않음)
    if q_num in SAMPLE_QUESTIONS_TEXT and not has_real_pdf:
        item = dict(SAMPLE_QUESTIONS_TEXT[q_num])
        if "genre" not in item:
            item["genre"] = "국어영역"
        if "topic" not in item:
            item["topic"] = f"{q_num}번 핵심 개념"
        if "trap_concept" not in item:
            item["trap_concept"] = "지문의 세부 서술어를 살짝 비틀어 오답을 유도한 평가원 함정"
        return item

    # 3. 로컬 PDF 텍스트 추출 (실제 PDF가 연결된 시험은 페이지 이미지를 AI에 직접 전달하므로 생략)
    approx_page = min(max(1, (q_num - 1) // 3 + 1), 16)
    pdf_text = None if has_real_pdf else extract_text_from_exam_pdf(exam_id, approx_page)
    if pdf_text and len(pdf_text.strip()) > 50:
        return {
            "q_num": q_num,
            "passage": pdf_text[:1200],
            "question": f"{exam_info.get('title', '국어')} {q_num}번 문항",
            "options": {},
            "correct": 1,
            "trap_concept": "지문 문맥과 선지 조건의 인과 전도 및 부분적 사실 왜곡",
            "genre": "국어영역",
            "topic": f"{q_num}번 문항",
            "mission": "지문 원문으로 돌아가 핵심 서술어를 1:1로 확인할 것"
        }

    return None

def build_initial_interview_question(exam_info, q_num, status_label, my_pick, correct_opt=None, matrix_type=None):
    """지문과 선지의 구체적 내용 및 공식 정답/메타인지 상태를 반영한 첫 질문 생성"""
    q_item = get_question_full_context(exam_info, q_num)
    
    # 텍스트 정보가 있는 경우
    if q_item and q_item.get("passage") and q_item.get("options"):
        opts = q_item.get("options", {})
        opt_text = opts.get(my_pick, opts.get(str(my_pick), ''))
        corr_n = correct_opt or q_item.get("correct")
        passage = q_item.get("passage", "")
        first_sentence = passage.split(".")[0].strip() if "." in passage else passage[:50].strip()
        
        if matrix_type == "CONFIDENT_WRONG":
            return f"**{q_num}번** 문항이야. 정답을 확신하고 **{my_pick}번 선지(「{opt_text}」)**를 골랐지만, 실제 공식 정답은 **{corr_n}번**이었어. 지문의 「*{first_sentence}*」 내용과 관련하여, 시험 당시 어떤 지문 내용이나 생각 때문에 {my_pick}번이 정답이라고 100% 확신했었는지 핵심만 솔직하게 말해줘."
        elif matrix_type == "UNSURE_CORRECT":
            return f"**{q_num}번** 문항이야. **{my_pick}번 선지(「{opt_text}」)**를 골라 **정답을 맞혔지만, 시험 당시 확신이 없었던 상태**였네! 지문의 「*{first_sentence}*」 내용과 관련하여, 시험 당시 몇 번 선지와 끝까지 망설였고 왜 헷갈렸는지 솔직하게 복기해 줘."
        elif matrix_type == "UNSURE_WRONG":
            return f"**{q_num}번** 문항이야. 시험 당시 확신이 없었고 결과도 오답(**{my_pick}번**, 정답: **{corr_n}번**)이었네. 지문의 「*{first_sentence}*」 내용과 관련하여, 어떤 부분이 명확히 이해되지 않았거나 선지 판단에 어려움이 있었는지 솔직하게 말해줘."
        elif matrix_type in ["TIMED_OUT_GUESS", "LUCKY_CORRECT"]:
            return f"**{q_num}번** 문항이야. **시간이 부족해서 찍었던 문항**이네! (선택: **{my_pick}번**, 공식 정답: **{corr_n}번**) 실전에서 이 문항을 다시 만났을 때 빠르고 정확하게 풀 수 있도록, 지문의 「*{first_sentence}*」 부근에서 이 선지의 진짜 근거가 되는 핵심 문장이 무엇인지 함께 찾아볼까?"
        else:
            if opt_text:
                return f"**{q_num}번** 문항이야. [{status_label}] 상태로 **{my_pick}번 선지(「{opt_text}」)**를 골랐네. 지문의 「*{first_sentence}*」 내용과 관련하여, 시험 당시 어떤 생각이나 근거로 이 선지를 답으로 판단했는지 핵심만 단도직입적으로 말해줘."
            else:
                return f"**{q_num}번** 문항이야. [{status_label}] 상태로 **{my_pick}번**을 골랐네. 지문의 「*{first_sentence}*」 내용과 관련하여, 시험 당시 어떤 근거로 {my_pick}번을 답으로 판단했는지 핵심만 말해줘."
    else:
        corr_n = correct_opt
        if matrix_type == "CONFIDENT_WRONG":
            corr_mention = f"실제 공식 정답은 **{corr_n}번**이었어." if corr_n else ""
            return f"**{q_num}번** 문항이야. 정답을 확신하고 **{my_pick}번**을 골랐지만 {corr_mention} 시험 당시 왼쪽 시험지 지문의 어느 문장이나 선지의 특정 어휘 때문에 {my_pick}번이 정답이라고 확신했었는지 그 사고 과정을 말해줘."
        elif matrix_type == "UNSURE_CORRECT":
            return f"**{q_num}번** 문항이야. **{my_pick}번**을 골라 정답을 맞혔지만 **확신이 부족했던 문항**이야. 당시 몇 번 선지와 마지막까지 고민했었고, 어떤 부분 때문에 망설여졌는지 솔직하게 짚어줘."
        elif matrix_type == "UNSURE_WRONG":
            corr_mention = f"공식 정답은 **{corr_n}번**이었어." if corr_n else ""
            return f"**{q_num}번** 문항이야. 확신이 없는 상태에서 **{my_pick}번**을 골라 오답이 되었네. {corr_mention} 지문의 어느 부분에서 해석이 막혔거나 혼란스러웠는지 편하게 말해줘."
        elif matrix_type in ["TIMED_OUT_GUESS", "LUCKY_CORRECT"]:
            return f"**{q_num}번** 문항이야. **시간이 부족해서 찍었던 문항**이네! 왼쪽 시험지 지문에서 이 선지의 참/거짓을 판별할 수 있는 진짜 근거 단어나 문장을 1개만 찾아볼까?"
        else:
            return f"**{q_num}번** 문항이야. [{status_label}] 상태로 **{my_pick}번**을 골랐네. 시험 당시 지문의 몇 문단, 어떤 핵심 문장이나 선지의 특정 어휘 때문에 {my_pick}번이 맞다고 판단했는지 지문 내용을 들어 핵심만 말해줘."

def get_exam_page_context_parts():
    """
    현재 인터뷰 중인 문항이 실린 '실제 시험지 PDF 페이지'를 이미지로 만들어 AI에 함께 전달할 Part 목록을 반환.
    (시험지 PDF가 연결되지 않았거나 페이지를 찾지 못하면 빈 목록)
    """
    try:
        exam_info = st.session_state.get("exam_info")
        queue = st.session_state.get("vulnerable_queue", [])
        idx = st.session_state.get("queue_index", 0)
        if not exam_info or not queue:
            return []
        q_num = queue[idx]["q_num"]
        loaded = _load_exam_pdf_page(exam_info.get("exam_id", ""), q_num)
        if not loaded or not loaded[2]:
            return []
        page, _, img = loaded
        return [
            types.Part.from_bytes(data=img, mime_type="image/jpeg"),
            types.Part.from_text(text=(
                f"[실제 시험지 이미지] 위 이미지는 '{exam_info.get('title', '')}' 시험지의 {page}페이지이며, "
                f"{q_num}번 문항의 지문·발문·선지가 여기에 실려 있습니다. "
                f"대화에서 지문이나 선지를 언급할 때는 반드시 이 이미지에 실제로 적힌 내용만 근거로 삼으십시오. "
                f"이미지에서 {q_num}번 문항을 직접 찾아 읽고, 이 이미지에 없는 내용은 지어내지 마십시오."
            ))
        ]
    except Exception:
        return []

def build_gemini_contents(chat_history):
    """
    대화 기록을 google-genai SDK의 표준 types.Content 구조로 변환합니다.
    실제 시험지 PDF가 연결된 경우 해당 문항 페이지 이미지를 첫 사용자 메시지에 함께 담습니다.
    """
    page_parts = get_exam_page_context_parts()
    contents = []
    attached = False
    for idx, msg in enumerate(chat_history):
        role = "model" if msg.get("role") == "assistant" else "user"
        text = str(msg.get("content", "")).strip()
        if not text:
            continue
        if idx == 0 and role == "model":
            first_parts = list(page_parts) + [types.Part.from_text(text="시험 당시 제 사고 과정을 복원하고 싶습니다. 인터뷰를 시작해 주세요.")]
            attached = bool(page_parts)
            contents.append(types.Content(role="user", parts=first_parts))
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=text)]
            )
        )
    if page_parts and not attached and contents:
        contents.insert(0, types.Content(role="user", parts=list(page_parts)))
    return contents

def safe_parse_json(text: str):
    cleaned = re.sub(r"^```(?:json)?\s*|```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("JSON 응답을 해석할 수 없습니다.")


def render_kakaotalk_chat(chat_history):
    """
    카카오톡 메신저 인터페이스:
    AI(어시스턴트)는 좌측 프로필 아바타와 함께, 학생(유저)은 우측 카카오 노란색 말풍선으로 배치.
    마크다운 4칸 들여쓰기로 인한 코드블록 오작동을 방지하기 위해 공백 없는 인라인 HTML로 조합.
    """
    if not chat_history:
        st.caption("대화가 시작되면 이곳에 질문과 답변이 표시됩니다.")
        return
    
    html_items = [
        '<div style="display: flex; flex-direction: column; gap: 14px; padding: 10px 4px;">'
    ]
    
    for msg in chat_history:
        role = msg.get("role")
        raw_text = str(msg.get("content", "")).strip()
        # HTML 특수문자 및 줄바꿈 처리
        safe_text = raw_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        # 볼드 마크다운 (**text**) 치환
        safe_text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", safe_text)
        
        if role == "assistant":
            item_html = (
                '<div style="display: flex; align-items: flex-start; gap: 8px; justify-content: flex-start; margin-right: 15%;">'
                '<div style="width: 34px; height: 34px; border-radius: 50%; background: #E3EAE2; border: 1px solid #C7D6CB; display: flex; align-items: center; justify-content: center; font-size: 1.05rem; flex-shrink: 0; box-shadow: 0 1px 2px rgba(14, 14, 41, 0.06);">'
                '🎯'
                '</div>'
                '<div style="display: flex; flex-direction: column; gap: 3px; max-width: 88%;">'
                '<span style="font-size: 0.78rem; color: #4B4640; font-weight: 600; margin-left: 2px;">AI 사고 복원 코치</span>'
                f'<div style="background: #ffffff; color: #2B2927; padding: 10px 14px; border-radius: 4px 12px 12px 12px; border: 1px solid #E6E1DA; font-size: 0.95rem; line-height: 1.55; box-shadow: 0 2px 8px -2px rgba(14, 14, 41, 0.05); word-break: break-word;">{safe_text}</div>'
                '</div>'
                '</div>'
            )
            html_items.append(item_html)
        else:
            item_html = (
                '<div style="display: flex; align-items: flex-end; justify-content: flex-end; margin-left: 15%;">'
                f'<div style="background: #fee500; color: #191600; padding: 10px 14px; border-radius: 12px 4px 12px 12px; font-size: 0.95rem; font-weight: 500; line-height: 1.55; box-shadow: 0 2px 8px -2px rgba(14, 14, 41, 0.07); word-break: break-word; border: 1px solid #fde047; max-width: 88%;">{safe_text}</div>'
                '</div>'
            )
            html_items.append(item_html)
            
    html_items.append("</div>")
    st.markdown("".join(html_items), unsafe_allow_html=True)
# ==========================================
def save_current_student_progress():
    """현재 세션의 모든 학습 상태를 디스크 및 구글 시트에 영구 보존"""
    student = st.session_state.get("auth_student")
    if not student:
        return
    sid = student.get("student_id")
    if not sid:
        return
    
    progress_data = {
        "student_stage": st.session_state.get("student_stage", "OMR"),
        "exam_info": st.session_state.get("exam_info"),
        "total_time": st.session_state.get("total_time", 80),
        "time_pressure": st.session_state.get("time_pressure", "보통"),
        "elective_subject": st.session_state.get("elective_subject"),
        "vulnerable_queue": st.session_state.get("vulnerable_queue", []),
        "queue_index": st.session_state.get("queue_index", 0),
        "interview_step": st.session_state.get("interview_step", "CHAT"),
        "chat_history": st.session_state.get("chat_history", []),
        "draft_summary": st.session_state.get("draft_summary", ""),
        "current_analysis": st.session_state.get("current_analysis"),
        "diagnosed_items": st.session_state.get("diagnosed_items", []),
        "active_training_problem": st.session_state.get("active_training_problem"),
        "training_feedback": st.session_state.get("training_feedback"),
        "defense_logs": st.session_state.get("defense_logs", [])
    }
    save_student_progress(sid, progress_data)

def load_student_progress_to_session(progress_data: dict):
    """저장된 학습 상태를 현재 Streamlit 세션으로 완벽 복원"""
    if not progress_data:
        return
    keys = [
        "student_stage", "exam_info", "total_time", "time_pressure", "elective_subject",
        "vulnerable_queue", "queue_index", "interview_step", "chat_history",
        "draft_summary", "current_analysis", "diagnosed_items",
        "active_training_problem", "training_feedback", "defense_logs"
    ]
    for k in keys:
        if k in progress_data and progress_data[k] is not None:
            st.session_state[k] = progress_data[k]

def render_student_welcome_header():
    """
    학생 진단실 최상단 고정 헤더:
    '반가워요, ~ 학생!' 환영 문구와 학생 상태를 가장 위에 크고 명확하게 표시
    """
    student = st.session_state.get("auth_student")
    if not student:
        return
    
    stage = st.session_state.get("student_stage", "OMR")
    exam_info = st.session_state.get("exam_info")
    exam_title = exam_info["title"] if exam_info else "시험지 선택 대기"
    
    stage_desc = {
        "OMR": "1단계: 시험지 선택 & OMR 마킹",
        "INTERVIEW": "2단계: 1:1 사고 복원 인터뷰 진행 중",
        "REPORT": "3단계: 종합 리포트 & AI 방어 훈련"
    }.get(stage, "진단 진행 중")

    st.markdown(f"""
    <div style="background:#EEF3EE; border:1px solid #C7D6CB; border-radius:10px; padding:0.45rem 1rem; margin-bottom:0.5rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <span style="color:#2B2927; font-size:1rem; font-weight:700;">👋 {student['name']} ({student['student_id']}) 학생</span>
            <span style="font-size:0.85rem; color:#4B4640;">🎯 {stage_desc}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_stage_navigation_bar():
    """
    학생 진단실 상단 단계 선택 네비게이터:
    1단계: OMR 마킹 및 선별
    2단계: 1:1 사고 복원 인터뷰
    3단계: 종합 리포트 & AI 기출 방어 훈련
    """
    cur_stage = st.session_state.get("student_stage", "OMR")
    queue = st.session_state.get("vulnerable_queue", [])
    diagnosed = st.session_state.get("diagnosed_items", [])
    total_vuln = len(queue)
    done_vuln = len(diagnosed)
    
    with st.container():
        col_nav1, col_nav2, col_nav3, col_save = st.columns([1.1, 1.4, 1.3, 0.9])
        
        with col_nav1:
            is_omr = (cur_stage == "OMR")
            omr_label = "1️⃣ OMR 마킹" + (" (현재)" if is_omr else "")
            if st.button(omr_label, type="primary" if is_omr else "secondary", use_container_width=True, help="1단계: 시험지 선택 및 OMR 상태 체크"):
                st.session_state.student_stage = "OMR"
                save_current_student_progress()
                st.rerun()

        with col_nav2:
            is_interview = (cur_stage == "INTERVIEW")
            stat_text = f" ({done_vuln}/{total_vuln} 완료)" if total_vuln > 0 else ""
            btn_label = f"2️⃣ 사고 복원{stat_text}" + (" (현재)" if is_interview else "")
            can_go_interview = (total_vuln > 0 or is_interview)
            if st.button(btn_label, type="primary" if is_interview else "secondary", disabled=not can_go_interview, use_container_width=True, help="2단계: 1:1 취약 문항 사고 복원 인터뷰"):
                st.session_state.student_stage = "INTERVIEW"
                save_current_student_progress()
                st.rerun()

        with col_nav3:
            is_report = (cur_stage == "REPORT")
            btn_label = "3️⃣ 리포트 & 방어훈련" + (" (현재)" if is_report else "")
            can_go_report = (done_vuln > 0 or cur_stage == "REPORT")
            if st.button(btn_label, type="primary" if is_report else "secondary", disabled=not can_go_report, use_container_width=True, help="3단계: 종합 진단 리포트 및 AI 맞춤 기출 방어 훈련"):
                st.session_state.student_stage = "REPORT"
                save_current_student_progress()
                st.rerun()

        with col_save:
            if st.button("💾 저장 후 멈춤", help="현재까지의 진행 상황을 저장해 두고, 나중에 이어서 풀 수 있습니다.", use_container_width=True):
                save_current_student_progress()
                st.toast("✅ 현재까지의 학습 진행 상태가 안전하게 저장되었습니다! 다음에 로그인 시 바로 이어서 하실 수 있습니다.", icon="💾")


# ==========================================
# 1. 학생 로그인 뷰
# ==========================================
def render_student_login():
    st.markdown("""
    <div style="text-align: center; margin-top: 0.5rem; margin-bottom: 1.25rem;">
        <h1 style="color: var(--color-text); font-weight: 800; letter-spacing: -0.5px;">🎯 수능 국어 사고 복원 클리닉</h1>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.container(border=True):
            st.subheader("🎓 학생 로그인")
            
            with st.form("student_login_form"):
                sid = st.text_input("학번 (예: 30101)", placeholder="30101", key="student_login_sid")
                name = st.text_input("이름", placeholder="김수험", key="student_login_name")
                pw = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력", key="student_login_pw")
                
                submitted = st.form_submit_button("로그인 및 진단 시작", type="primary", use_container_width=True)
                if submitted:
                    sid_clean = (sid or "").strip()
                    name_clean = (name or "").strip()
                    pw_clean = (pw or "").strip()
                    
                    if sid_clean and name_clean and pw_clean:
                        ok, res = verify_student(sid_clean, name_clean, pw_clean)
                        if ok:
                            st.session_state.auth_student = res
                            # 이전 저장된 진행 상태 확인 및 자동 복원
                            saved_prog = get_student_progress(sid_clean)
                            if saved_prog and (saved_prog.get("vulnerable_queue") or saved_prog.get("student_stage") in ["INTERVIEW", "REPORT"]):
                                load_student_progress_to_session(saved_prog)
                            else:
                                st.session_state.student_stage = "OMR"
                                st.session_state.chat_history = []
                                st.session_state.interview_step = "CHAT"
                                st.session_state.vulnerable_queue = []
                                st.session_state.queue_index = 0
                                st.session_state.diagnosed_items = []
                                if "omr_df" in st.session_state:
                                    del st.session_state["omr_df"]
                            st.rerun()
                        else:
                            st.error(f"❌ {res}")
                    else:
                        missing = []
                        if not sid_clean:
                            missing.append("학번")
                        if not name_clean:
                            missing.append("이름")
                        if not pw_clean:
                            missing.append("비밀번호")
                        st.warning(f"⚠️ {', '.join(missing)}을(를) 입력해 주세요.")
            
            # 학생 로그인 화면 내 Gemini API 키 직접 설정/확인 칸
            saved_key, key_source = get_effective_api_key()
            with st.expander("🔑 Gemini API Key 설정 (학생 개별 키)", expanded=(not bool(saved_key))):
                login_user_key = st.text_input(
                    "Gemini API Key",
                    value=saved_key,
                    type="password",
                    placeholder="AI Studio 키를 입력하세요",
                    key="login_user_api_key"
                )
                col_lk1, col_lk2 = st.columns([1.3, 1])
                with col_lk1:
                    if st.button("💾 이 기기에 저장", key="btn_save_login_user_key", use_container_width=True, type="primary"):
                        if login_user_key.strip():
                            save_student_api_key(login_user_key.strip())
                            st.success("API 키가 저장되었습니다!")
                            st.rerun()
                        else:
                            st.warning("API 키를 입력해 주세요.")
                with col_lk2:
                    if st.button("🗑️ 키 삭제", key="btn_clear_login_user_key", use_container_width=True):
                        clear_student_api_key()
                        st.info("저장된 API 키가 삭제되었습니다.")
                        st.rerun()

            st.write("")
            if st.button("🔒 선생님 관리자 페이지", key="btn_switch_admin", use_container_width=True):
                st.query_params["mode"] = "admin"
                st.session_state.app_mode = "ADMIN"
                st.rerun()

# ==========================================
# 1-1. 학생 개인 맞춤형 누적 성장 리포트 (마이페이지)
# ==========================================
def render_student_mypage():
    """
    학생 개인 맞춤형 누적 성장 리포트 (마이페이지)
    - 과거 진단 이력 및 누적 취약점 TOP 3
    - 나만의 실전 행동 원칙 (Action Rules) 아카이브
    - 과거 시험별 상세 오답 복원 기록 열람
    """
    student = st.session_state.get("auth_student")
    if not student:
        st.warning("로그인이 필요한 서비스입니다.")
        return

    profile = get_student_vulnerability_profile(student["student_id"])
    
    st.markdown(f"### 📊 **{student['name']}** ({student['student_id']}) 님의 사고 복원 성장 기록")

    if not profile["has_history"]:
        st.info("💡 아직 제출된 진단 기록이 없습니다. 상단 **[✏️ 시험 진단실]** 탭에서 첫 번째 시험지 진단을 완료해 보세요!")
        return

    # 1. 상단 핵심 메트릭 카드
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("총 진단 완료 시험", f"{profile['total_submissions']}회")
    with m2:
        st.metric("정밀 분석 문항 수", f"{profile['total_questions']}개")
    with m3:
        top1_tag = profile['top_vulnerabilities'][0][0] if profile['top_vulnerabilities'] else "없음"
        top1_cnt = profile['top_vulnerabilities'][0][1] if profile['top_vulnerabilities'] else 0
        st.metric("최대 빈출 취약점 (1위)", top1_tag, f"{top1_cnt}회 감지")
    with m4:
        st.metric("수립된 실전 행동 원칙", f"{len(profile['action_rules'])}개")

    st.write("")

    # 2. 탭 구성
    tab_summary, tab_rules, tab_history = st.tabs([
        "🚨 취약점 패턴 정밀 분석",
        "🎯 수능장 지참용 나만의 행동 원칙 요약집",
        "📜 시험별 오답 복원 상세 이력"
    ])

    with tab_summary:
        st.subheader("🚨 나의 6대 사고 오류 누적 분포")

        col_top, col_chart = st.columns([1.2, 1.8], gap="medium")
        with col_top:
            st.markdown("##### 📌 집중 극복 대상 TOP 3")
            for rank, (tag, count) in enumerate(profile["top_vulnerabilities"], start=1):
                badge_color = "#C86446" if rank == 1 else ("#B4552E" if rank == 2 else "#97731F")
                ratio = round(count / max(1, profile['total_questions']) * 100, 1)
                st.markdown(f"""
                <div style="background-color: #F5F2EB; border-left: 4px solid {badge_color}; border-top: 1px solid #E6E1DA; border-right: 1px solid #E6E1DA; border-bottom: 1px solid #E6E1DA; padding: 12px 14px; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 2px 8px -2px rgba(14, 14, 41, 0.05);">
                    <div style="font-weight: 700; color: #2B2927; font-size: 1.05rem;">{rank}위: {tag}</div>
                    <div style="color: #4B4640; font-size: 0.9rem; margin-top: 4px;">총 <b>{count}문항</b>에서 감지 (전체 분석의 {ratio}%)</div>
                </div>
                """, unsafe_allow_html=True)

        with col_chart:
            st.markdown("##### 📊 사고 왜곡 유형별 누적 빈도")
            if profile["tag_counts"]:
                df_tags = pd.DataFrame([
                    {"사고 오류 유형": k, "감지 횟수": v}
                    for k, v in profile["tag_counts"].items()
                ]).sort_values(by="감지 횟수", ascending=True)
                st.bar_chart(df_tags.set_index("사고 오류 유형"), horizontal=True, color="#2B2927")

    with tab_rules:
        st.subheader("🎯 수능장 지참용 나만의 행동 원칙 (Action Rules)")

        if profile["action_rules"]:
            for idx, r in enumerate(profile["action_rules"], start=1):
                with st.container(border=True):
                    col_r1, col_r2 = st.columns([3.2, 1])
                    with col_r1:
                        st.markdown(f"**📌 [{r['exam_title']}] {r['q_num']}번 문항** `오류: {r['error_tag']}`")
                        st.markdown(f"💡 **나의 행동 원칙:** <span style='color: #2B2927; font-weight: 700; font-size: 1.05rem;'>\"{r['action_rule']}\"</span>", unsafe_allow_html=True)
                    with col_r2:
                        st.caption(f"📅 진단일: {r['timestamp']}")
        else:
            st.info("아직 수립된 행동 원칙이 없습니다.")

    with tab_history:
        st.subheader("📜 시험별 진단 제출 상세 이력")
        subs = get_student_submissions(student["student_id"])
        for s in subs:
            with st.expander(f"📝 {s.get('exam_title')} (제출 일시: {s.get('timestamp')})"):
                st.markdown(f"- **소요 시간:** {s.get('total_time', 80)}분 | **체감 시간 압박:** {s.get('time_pressure', '보통')}")
                st.markdown(f"- **감지된 주요 오류 태그:** {', '.join(s.get('error_tags', []))}")
                st.markdown("---")
                st.markdown("##### 🔍 문항별 정밀 복원 기록:")
                for d in s.get("diagnosed_items", []):
                    st.markdown(f"**[{d.get('q_num')}번 문항]** (내 선택: {d.get('my_pick')}번 | 오류 태그: `{d.get('error_tag')}`)")
                    st.markdown(f"- 💭 **내 당시 사고 과정:** {d.get('student_thought')}")
                    st.markdown(f"- 😈 **평가원 함정 설계:** {d.get('evaluator_trap')}")
                    st.markdown(f"- 💡 **실전 행동 원칙:** *{d.get('action_rule')}*")
                    st.write("")
                
                st.markdown("---")
                if st.button(f"🎯 [{s.get('exam_title')}] AI 맞춤 기출 방어 훈련 바로 열기", key=f"reopen_report_{s.get('submission_id') or s.get('timestamp')}", use_container_width=True, type="primary"):
                    st.session_state.exam_info = {
                        "exam_id": s.get("exam_id"),
                        "title": s.get("exam_title"),
                        "total_questions": len(s.get("diagnosed_items", []))
                    }
                    st.session_state.total_time = s.get("total_time", 80)
                    st.session_state.time_pressure = s.get("time_pressure", "보통")
                    st.session_state.diagnosed_items = s.get("diagnosed_items", [])
                    st.session_state.student_stage = "REPORT"
                    st.session_state.active_training_problem = None
                    st.session_state.training_feedback = None
                    save_current_student_progress()
                    st.toast(f"'{s.get('exam_title')}'의 종합 진단 리포트 및 맞춤 처방 화면으로 이동합니다.")
                    st.rerun()

# ==========================================
# 2. OMR 일괄 상태 입력 뷰
# ==========================================
def render_omr_stage():
    student = st.session_state.auth_student
    
    # 이전 저장된 진행 상태가 있는 경우 알림 및 이어하기 배너 제공
    saved_prog = get_student_progress(student["student_id"])
    if saved_prog and saved_prog.get("exam_info"):
        prev_exam_title = saved_prog.get("exam_info", {}).get("title", "시험")
        prev_stage = saved_prog.get("student_stage", "INTERVIEW")
        prev_diagnosed = saved_prog.get("diagnosed_items", [])
        prev_queue = saved_prog.get("vulnerable_queue", [])
        stage_name = "2단계 사고 복원 인터뷰" if prev_stage == "INTERVIEW" else ("3단계 AI 맞춤 방어 훈련" if prev_stage == "REPORT" else "1단계 OMR")
        
        with st.container(border=True):
            st.markdown("#### 📌 이전에 진행 중이던 학습 기록이 있습니다!")
            st.write(f"📝 **{prev_exam_title}** | 진행 단계: **{stage_name}** | 복원 완료: **{len(prev_diagnosed)}/{len(prev_queue)} 문항**")
            col_res1, col_res2 = st.columns([1.5, 1])
            with col_res1:
                if st.button(f"▶️ [{stage_name}] 이어서 계속하기", type="primary", use_container_width=True, key="btn_resume_progress"):
                    load_student_progress_to_session(saved_prog)
                    st.rerun()
            with col_res2:
                if st.button("🔄 이전 기록 지우고 새로 시작", use_container_width=True, key="btn_clear_prev_progress"):
                    clear_student_progress(student["student_id"])
                    st.info("이전 학습 기록을 지우고 새로 시작합니다.")
                    st.rerun()
        st.write("")

    # 학생의 과거 누적 취약점 프로필 조회 및 경보 배너 표시
    profile = get_student_vulnerability_profile(student["student_id"])
    if profile.get("has_history") and profile.get("top_vulnerabilities"):
        top_tags_text = ", ".join([f"**{tag}**({cnt}회)" for tag, cnt in profile["top_vulnerabilities"][:2]])
        st.info(f"💡 **누적 취약점 경보**: 지난 진단에서 {top_tags_text} 패턴이 자주 감지되었습니다. 이번 시험지에서도 비슷한 사고 왜곡이 발생하지 않았는지 주의 깊게 복기해 보세요!")

    st.markdown("""
    <div style="background-color: #F5F2EB; border-left: 4px solid #2B2927; border-top: 1px solid #E6E1DA; border-right: 1px solid #E6E1DA; border-bottom: 1px solid #E6E1DA; padding: 12px 16px; border-radius: 8px; margin-bottom: 1.2rem; box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.04);">
        <b style="color: #2B2927; font-size: 1.05rem;">📝 1단계: 시험지 선택 및 OMR 풀이 상태 마킹</b>
    </div>
    """, unsafe_allow_html=True)

    exams = get_exams()
    # ⭐️ 시험지 목록을 최신순(최근 연도 및 시험 시기 우선)으로 정렬 후,
    # 선생님이 원문 PDF(파일 업로드 또는 구글 드라이브 링크)를 연동해 둔 시험지만 노출
    sorted_all_ids = get_sorted_exam_keys(exams, reverse=True)
    exam_options = [eid for eid in sorted_all_ids if exam_has_own_pdf(eid)]

    if not exam_options:
        st.info("💡 아직 선생님이 원문 PDF를 연결한 시험지가 없습니다. 등록될 때까지 잠시 기다려 주세요.")
        return

    col_meta1, col_meta2, col_meta3 = st.columns([2, 1, 1.2])
    with col_meta1:
        selected_exam_id = st.selectbox(
            "📝 진단할 시험지 선택",
            options=exam_options,
            format_func=lambda x: f"{exams[x]['title']} ({exams[x]['total_questions']}문항)"
        )
    with col_meta2:
        total_time = st.number_input("전체 풀이 소요 시간 (분)", min_value=10, max_value=120, value=78)
    with col_meta3:
        time_pressure = st.selectbox("시험 당시 시간 압박감", ["충분했음", "쫓기며 풀었음", "시간 부족으로 찍음/못풂"])

    cur_exam = exams[selected_exam_id]
    total_q = cur_exam["total_questions"]

    is_elective_exam = exam_is_elective(selected_exam_id)
    selected_subject = None
    if is_elective_exam:
        SUBJECT_PLACEHOLDER = "선택하세요"
        selected_subject = st.selectbox(
            "🔀 응시한 선택과목 (35~45번 채점 기준)",
            options=[SUBJECT_PLACEHOLDER] + ELECTIVE_SUBJECTS,
            help="이 시험지는 35~45번이 선택과목별로 나뉘어 있어, 실제로 응시한 과목을 선택해야 정확히 채점됩니다."
        )
        if selected_subject == SUBJECT_PLACEHOLDER:
            selected_subject = None
        else:
            st.session_state.elective_subject = selected_subject
        if not selected_subject:
            st.warning("⚠️ 35~45번을 정확히 채점하려면 먼저 응시한 선택과목을 선택해 주세요.")

    st.divider()
    st.subheader(f"📋 {cur_exam['title']} - 전체 문항 풀이 상태 기록")
    st.caption("기본값은 '확신'입니다. 틀렸거나 헷갈렸거나 찍었던 문제만 상태를 변경하세요.")

    # 시험지가 변경되었거나 OMR 데이터가 없는 경우 안전하게 초기화
    opt_chars = ["①", "②", "③", "④", "⑤"]
    if "current_exam_id" not in st.session_state or st.session_state.current_exam_id != selected_exam_id or "omr_df" not in st.session_state:
        st.session_state.current_exam_id = selected_exam_id
        init_rows = [
            {
                "문항": i,
                "🔴 오답": False,
                "🟡 확신 없음": False,
                "⏱️ 찍음": False,
                "①": True,
                "②": False,
                "③": False,
                "④": False,
                "⑤": False
            }
            for i in range(1, total_q + 1)
        ]
        st.session_state.omr_df = pd.DataFrame(init_rows)
        st.session_state.omr_editor_nonce = st.session_state.get("omr_editor_nonce", 0) + 1

    # 0. 시험지 원문 PDF 열람 (문항별 자동 이동 지원)
    pdf_path_omr, pdf_b64_omr, pdf_url_omr = get_exam_pdf_source(selected_exam_id)
    if pdf_path_omr or pdf_b64_omr or pdf_url_omr:
        with st.expander("📄 [시험지 원문 열기] 실물 시험지 PDF를 보면서 마킹하기 (문항별 이동 지원)", expanded=False):
            render_pdf_viewer(
                base64_pdf=pdf_b64_omr,
                pdf_url=pdf_url_omr,
                pdf_path=pdf_path_omr,
                height=560,
                viewer_id=f"omr_{selected_exam_id}"
            )

    # 1. 빠른 번호 일괄 지정 폼 (체크박스 자동 토글)
    with st.expander("⚡ 번호 직접 입력으로 빠르게 체크하기 (선택사항)", expanded=False):
        with st.form("quick_omr_form"):
            col_q1, col_q2, col_q3 = st.columns(3)
            with col_q1:
                wrong_input = st.text_input("🔴 오답 번호들", placeholder="예: 14, 27, 34")
            with col_q2:
                unsure_input = st.text_input("🟡 확신 없는 정답 번호들", placeholder="예: 8, 21")
            with col_q3:
                time_input = st.text_input("⏱️ 찍음 / 시간부족 번호들", placeholder="예: 44, 45")

            col_btn1, col_btn2 = st.columns([2, 1])
            with col_btn1:
                submit_quick = st.form_submit_button("⚡ 위 문항들 체크박스 자동 적용", type="primary", use_container_width=True)
            with col_btn2:
                reset_all = st.form_submit_button("🔄 전체 체크박스 해제 (초기화)", use_container_width=True)

            if submit_quick:
                def parse_q_numbers(text: str):
                    if not text:
                        return []
                    parts = re.split(r"[,/\\s]+", text.strip())
                    return [int(p) for p in parts if p.isdigit()]

                w_list = parse_q_numbers(wrong_input)
                u_list = parse_q_numbers(unsure_input)
                t_list = parse_q_numbers(time_input)

                applied_count = 0
                for q in w_list:
                    if 1 <= q <= total_q:
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🔴 오답"] = True
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🟡 확신 없음"] = False
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "⏱️ 찍음"] = False
                        applied_count += 1
                for q in u_list:
                    if 1 <= q <= total_q:
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🔴 오답"] = False
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🟡 확신 없음"] = True
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "⏱️ 찍음"] = False
                        applied_count += 1
                for q in t_list:
                    if 1 <= q <= total_q:
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🔴 오답"] = False
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "🟡 확신 없음"] = False
                        st.session_state.omr_df.loc[st.session_state.omr_df["문항"] == q, "⏱️ 찍음"] = True
                        applied_count += 1

                st.session_state.omr_editor_nonce = st.session_state.get("omr_editor_nonce", 0) + 1
                st.session_state.omr_grading_result = None
                st.success(f"총 {applied_count}개 문항의 체크박스가 자동 설정되었습니다.")
                st.rerun()

            if reset_all:
                init_rows = [
                    {
                        "문항": i,
                        "🔴 오답": False,
                        "🟡 확신 없음": False,
                        "⏱️ 찍음": False,
                        "①": True,
                        "②": False,
                        "③": False,
                        "④": False,
                        "⑤": False
                    }
                    for i in range(1, total_q + 1)
                ]
                st.session_state.omr_df = pd.DataFrame(init_rows)
                st.session_state.omr_editor_nonce = st.session_state.get("omr_editor_nonce", 0) + 1
                st.session_state.omr_grading_result = None
                st.info("전체 문항의 체크가 해제되었습니다. (모두 확신 상태)")
                st.rerun()

    # 2. 체크박스 OMR 마킹 시트 (선지도 ①~⑤ 체크박스 형태로 직관화)
    st.markdown("##### ☑️ OMR 체크박스 마킹 시트")

    # 상단 2단 그룹 헤더: [문항 풀이 상태] vs [내가 체크한 답]
    st.markdown("""
    <div style="display: flex; gap: 8px; margin-top: 8px; margin-bottom: 8px; font-weight: 700; font-size: 0.93rem;">
        <div style="flex: 4; background-color: #F5F2EB; color: #4B4640; padding: 9px 12px; border-radius: 8px; text-align: center; border: 1px solid #E6E1DA;">
            📋 문항 풀이 상태
        </div>
        <div style="flex: 5; background-color: #E3EAE2; color: #2B2927; padding: 9px 12px; border-radius: 8px; text-align: center; border: 1px solid #C7D6CB;">
            ✏️ 내가 체크한 답 (실제 선택한 선지)
        </div>
    </div>
    """, unsafe_allow_html=True)

    editor_key = f"omr_editor_{st.session_state.current_exam_id}_{st.session_state.get('omr_editor_nonce', 0)}"

    edited_df = st.data_editor(
        st.session_state.omr_df,
        key=editor_key,
        column_config={
            "문항": st.column_config.NumberColumn("문항", disabled=True, width="small"),
            "🔴 오답": st.column_config.CheckboxColumn("🔴 오답", default=False, width="small"),
            "🟡 확신 없음": st.column_config.CheckboxColumn("🟡 확신 없음", default=False, width="small"),
            "⏱️ 찍음": st.column_config.CheckboxColumn("⏱️ 찍음", default=False, width="small"),
            "①": st.column_config.CheckboxColumn("내 답 ①", default=True, help="내가 체크한 답 1번", width="small"),
            "②": st.column_config.CheckboxColumn("내 답 ②", default=False, help="내가 체크한 답 2번", width="small"),
            "③": st.column_config.CheckboxColumn("내 답 ③", default=False, help="내가 체크한 답 3번", width="small"),
            "④": st.column_config.CheckboxColumn("내 답 ④", default=False, help="내가 체크한 답 4번", width="small"),
            "⑤": st.column_config.CheckboxColumn("내 답 ⑤", default=False, help="내가 체크한 답 5번", width="small"),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        height=380
    )

    # ⭐️ 1) 선지 체크박스 단일 선택(라디오 동작) 자동 보정: 1번에서 3번으로 바꾸면 1번 자동 해제!
    needs_rerun = False
    for idx in range(len(edited_df)):
        row = edited_df.iloc[idx]
        checked = [c for c in opt_chars if row.get(c, False)]
        if len(checked) > 1:
            prev_row = st.session_state.omr_df.iloc[idx] if idx < len(st.session_state.omr_df) else None
            newly = [c for c in checked if prev_row is not None and not prev_row.get(c, False)]
            keep = newly[-1] if newly else checked[-1]
            for c in opt_chars:
                val = (c == keep)
                if edited_df.iat[idx, edited_df.columns.get_loc(c)] != val:
                    edited_df.iat[idx, edited_df.columns.get_loc(c)] = val
                    needs_rerun = True

    # ⭐️ 2) 문항 풀이 상태 체크박스("🔴 오답", "🟡 확신 없음", "⏱️ 찍음") 단일 선택(상호 배타) 자동 보정
    status_cols = ["🔴 오답", "🟡 확신 없음", "⏱️ 찍음"]
    for idx in range(len(edited_df)):
        row = edited_df.iloc[idx]
        checked_st = [s for s in status_cols if row.get(s, False)]
        if len(checked_st) > 1:
            prev_row = st.session_state.omr_df.iloc[idx] if idx < len(st.session_state.omr_df) else None
            newly_st = [s for s in checked_st if prev_row is not None and not prev_row.get(s, False)]
            keep_st = newly_st[-1] if newly_st else checked_st[-1]
            for s in status_cols:
                val = (s == keep_st)
                if edited_df.iat[idx, edited_df.columns.get_loc(s)] != val:
                    edited_df.iat[idx, edited_df.columns.get_loc(s)] = val
                    needs_rerun = True

    st.session_state.omr_df = edited_df

    if needs_rerun:
        st.session_state.omr_editor_nonce = st.session_state.get("omr_editor_nonce", 0) + 1
        st.session_state.omr_grading_result = None
        st.rerun()

    # 상태 판정 함수 (상호 배타 5개 영역 매핑)
    def resolve_status(row):
        if row.get("⏱️ 찍음", False):
            return "⏱️ 찍음"
        elif row.get("🟡 확신 없음", False):
            return "🟡 확신 없음"
        elif row.get("🔴 오답", False):
            return "🔴 오답"
        return "🟢 확신"

    def resolve_pick(row):
        for opt_num, opt_char in [(5, "⑤"), (4, "④"), (3, "③"), (2, "②"), (1, "①")]:
            if row.get(opt_char, False):
                return opt_num
        return 1

    # 전체 45문항 원본 마킹 데이터 추출
    raw_omr_records = []
    for _, row in edited_df.iterrows():
        raw_omr_records.append({
            "q_num": int(row["문항"]),
            "selected_opt": resolve_pick(row),
            "state": resolve_status(row)
        })

    # ==========================================
    # ⭐️ 2단계 검증: OMR 자동 정오 판정 및 마킹 확인 카드
    # ==========================================
    grading_res = st.session_state.get("omr_grading_result")

    if not grading_res:
        # 아직 채점하기 전 상태: [OMR 제출 및 자동 정오 판정하기] 버튼 노출
        st.markdown("""
        <div style="background-color: #F5F2EB; border: 1px solid #E6E1DA; border-left: 4px solid #2B2927; padding: 14px 18px; border-radius: 8px; margin: 16px 0; box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.04);">
            <span style="font-size: 1.05rem; font-weight: 700; color: #2B2927;">
                💡 OMR 마킹을 마쳤다면 아래 버튼을 눌러 공식 정답표와 자동 대조(채점)를 진행하세요.
            </span>
            <div style="margin-top: 6px; font-size: 0.92rem; color: #4B4640; line-height: 1.55;">
                앱이 실제 정답과 대조하여 마킹 실수나 착각을 바로잡고, <b>'확신 오답'</b>, <b>'찍어서 맞힌 문항'</b> 등 메타인지 매트릭스를 정밀 분석합니다.
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🎯 OMR 제출 및 자동 정오 판정(채점)하기", type="primary", use_container_width=True, key="btn_grade_omr", disabled=(is_elective_exam and not selected_subject)):
            res = grade_student_omr(cur_exam["exam_id"], raw_omr_records, subject=selected_subject)
            st.session_state.omr_grading_result = res
            st.rerun()

    else:
        # ⭐️ 자동 정오 판정 완료 상태: 결과 요약 및 마킹 확인 UI 노출
        correct_n = grading_res["correct_count"]
        wrong_n = grading_res["wrong_count"]
        clinic_n = grading_res["clinic_count"]
        acc_pct = int(correct_n / total_q * 100) if total_q else 0

        with st.container(border=True):
            st.markdown(f"### 📊 자동 채점 결과 및 메타인지 정오 분석")
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; background: #F1F5F0; border: 1px solid #C7D6CB; border-radius: 12px; padding: 12px 18px; margin-bottom: 14px; box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.04);">
                <div>
                    <span style="font-size: 1.25rem; font-weight: 800; color: #2B2927;">
                        🎯 정답률: {acc_pct}% ({correct_n} / {total_q} 문항)
                    </span>
                    <span style="margin-left: 14px; font-size: 0.98rem; color: #4B4640;">
                        (⭕ 정답: <b>{correct_n}개</b> | ❌ 오답: <b>{wrong_n}개</b>)
                    </span>
                </div>
                <div>
                    <span style="font-size: 1.05rem; font-weight: bold; background: #FBEEEA; color: #C86446; padding: 6px 14px; border-radius: 20px; border: 1px solid #E8C4B7;">
                        복원 대상: 총 {clinic_n}개 문항
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 5대 메타인지 정오 분석 카드 5열 표시 (5개 카드의 합 = 전체 문항 수 100% 일치)
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            
            n_conf_corr = len(grading_res.get('confident_correct', []))
            n_conf_wrong = len(grading_res.get('confident_wrong', []))
            n_unsure_corr = len(grading_res.get('unsure_correct', []))
            n_unsure_wrong = len(grading_res.get('unsure_wrong', []))
            n_timed_guess = len(grading_res.get('timed_out_guess', []))
            total_classified = n_conf_corr + n_conf_wrong + n_unsure_corr + n_unsure_wrong + n_timed_guess

            with col_m1:
                st.markdown(f"""
                <div style="background: #EEF3EC; border: 1px solid #C7D6CB; border-radius: 10px; padding: 10px 8px; text-align: center; box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.04);">
                    <b style="color: #3F5646; font-size: 0.94rem;">⭕ 확신했고 정답</b>
                    <h3 style="margin: 4px 0; color: #4A6452;">{n_conf_corr}개</h3>
                    <span style="font-size: 0.78rem; color: #5E7966;">안정적 득점<br>(클리닉 불필요)</span>
                </div>
                """, unsafe_allow_html=True)
            with col_m2:
                st.markdown(f"""
                <div style="background: #FBEEEA; border: 1px solid #E8C4B7; border-radius: 10px; padding: 10px 8px; text-align: center; box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.04);">
                    <b style="color: #8A3F28; font-size: 0.94rem;">🚨 확신했으나 오답</b>
                    <h3 style="margin: 4px 0; color: #C86446;">{n_conf_wrong}개</h3>
                    <span style="font-size: 0.78rem; color: #A8543A;">킬러 함정 낚임<br>(우선 복원 대상)</span>
                </div>
                """, unsafe_allow_html=True)
            with col_m3:
                st.markdown(f"""
                <div style="background: #FBF3E4; border: 1px solid #E8D5A8; border-radius: 10px; padding: 10px 8px; text-align: center; box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.04);">
                    <b style="color: #6B531C; font-size: 0.94rem;">⚠️ 확신 없으나 정답</b>
                    <h3 style="margin: 4px 0; color: #97731F;">{n_unsure_corr}개</h3>
                    <span style="font-size: 0.78rem; color: #7A5F22;">실전 불안 요소<br>(근거 재정립)</span>
                </div>
                """, unsafe_allow_html=True)
            with col_m4:
                st.markdown(f"""
                <div style="background: #FCEEE9; border: 1px solid #F0C9BC; border-radius: 10px; padding: 10px 8px; text-align: center; box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.04);">
                    <b style="color: #6B2A18; font-size: 0.94rem;">❌ 확신 없고 오답</b>
                    <h3 style="margin: 4px 0; color: #B4552E;">{n_unsure_wrong}개</h3>
                    <span style="font-size: 0.78rem; color: #96431F;">독해 사고 공백<br>(개념 보완)</span>
                </div>
                """, unsafe_allow_html=True)
            with col_m5:
                st.markdown(f"""
                <div style="background: #F2EDE6; border: 1px solid #CDC5BD; border-radius: 10px; padding: 10px 8px; text-align: center; box-shadow: 0 2px 6px -2px rgba(14, 14, 41, 0.04);">
                    <b style="color: #4B4640; font-size: 0.94rem;">⏱️ 시간이 없어서 찍음</b>
                    <h3 style="margin: 4px 0; color: #32302C;">{n_timed_guess}개</h3>
                    <span style="font-size: 0.78rem; color: #4B4640;">타임 어택 문항<br>(시간 관리 전략)</span>
                </div>
                """, unsafe_allow_html=True)

            # 5대 영역 합계 검증 배너
            match_color = "#2B2927" if total_classified == total_q else "#C86446"
            match_txt = f"✓ 전체 문항 완벽 일치 ({total_classified}/{total_q})" if total_classified == total_q else f"⚠️ 합계 불일치 ({total_classified}/{total_q})"
            st.markdown(f"""
            <div style="margin-top: 10px; padding: 8px 14px; background: #F5F2EB; border-radius: 8px; border: 1px dashed #CDC5BD; font-size: 0.88rem; color: #4B4640; display: flex; justify-content: space-between; align-items: center;">
                <span>
                    📌 <b>5대 영역 분류 합계 검증</b>: 
                    ⭕ {n_conf_corr} + 🚨 {n_conf_wrong} + ⚠️ {n_unsure_corr} + ❌ {n_unsure_wrong} + ⏱️ {n_timed_guess} = <b style="color: #1D1B17;">총 {total_classified}문항</b>
                </span>
                <span style="color: {match_color}; font-weight: 700;">
                    {match_txt}
                </span>
            </div>
            """, unsafe_allow_html=True)

            st.write("")
            
            # 상세 정오 대조 확인표 (아코디언)
            with st.expander("🔍 1~45번 전체 문항 정오 대조표 (마킹 번호 검증)", expanded=False):
                table_rows = []
                for item in grading_res["graded_items"]:
                    corr_txt = f"{item['correct_opt']}번" if item.get('correct_opt') else "-"
                    table_rows.append({
                        "문항": f"{item['q_num']}번",
                        "내가 체크한 답": f"{item['selected_opt']}번" if item.get('selected_opt') else "-",
                        "공식 정답": corr_txt,
                        "정오 결과": "⭕ 정답" if item["is_correct"] else "❌ 오답",
                        "풀이 당시 상태": item["user_state"],
                        "메타인지 정오 판정": item["matrix_badge"]
                    })
                st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

            st.write("")
            st.info("💡 **확인 안내**: 혹시 번호를 잘못 마킹했거나 답안을 수정해야 한다면 **[✏️ 마킹 답안 수정하기]**를 눌러 즉시 변경할 수 있습니다. 결과가 맞다면 아래 파란색 버튼을 눌러 인터뷰를 시작하세요.")

            col_fix, col_start = st.columns([1.2, 2])
            with col_fix:
                if st.button("✏️ 마킹 답안 수정하기 (채점 다시하기)", use_container_width=True):
                    st.session_state.omr_grading_result = None
                    st.rerun()

            with col_start:
                if clinic_n == 0:
                    btn_label = "🎉 완벽합니다! (복원할 취약 문항 없음)"
                else:
                    btn_label = f"🚀 정오 확인 완료! AI 사고 복원 인터뷰 시작하기 (총 {clinic_n}개 문항)"
                    
                if st.button(btn_label, type="primary", use_container_width=True, disabled=(clinic_n == 0)):
                    # 취약 문항 큐 생성 (정답 여부 및 메타인지 타입 완벽 반영)
                    clinic_queue = []
                    for item in grading_res["graded_items"]:
                        if item["needs_clinic"]:
                            clinic_queue.append({
                                "q_num": item["q_num"],
                                "status": item["matrix_badge"],
                                "my_pick": item["selected_opt"],
                                "correct_opt": item["correct_opt"],
                                "matrix_type": item["matrix_type"]
                            })

                    st.session_state.exam_info = cur_exam
                    st.session_state.total_time = total_time
                    st.session_state.time_pressure = time_pressure
                    st.session_state.vulnerable_queue = clinic_queue
                    st.session_state.queue_index = 0
                    st.session_state.diagnosed_items = []
                    st.session_state.student_stage = "INTERVIEW"

                    # 첫 번째 문항 인터뷰 세팅
                    first_q = clinic_queue[0]
                    st.session_state.interview_step = "CHAT"
                    first_q_msg = build_initial_interview_question(
                        cur_exam, 
                        first_q['q_num'], 
                        first_q['status'], 
                        first_q['my_pick'],
                        first_q.get('correct_opt'),
                        first_q.get('matrix_type')
                    )
                    st.session_state.chat_history = [{
                        "role": "assistant",
                        "content": first_q_msg
                    }]
                    st.session_state.draft_summary = ""
                    st.session_state.current_analysis = None
                    save_current_student_progress()
                    st.rerun()

def get_interview_system_prompt(student, exam_info, q_num, status_label, my_pick, correct_opt=None, matrix_type=None):
    """사고 복원 인터뷰어용 맞춤형 시스템 프롬프트 생성"""
    q_item = get_question_full_context(exam_info, q_num)

    q_context = ""
    corr_num = correct_opt or (q_item.get('correct') if q_item else '')
    if q_item and q_item.get("passage"):
        opts = q_item.get("options", {})
        opt_text = opts.get(my_pick, opts.get(str(my_pick), '선지 텍스트 미등록'))
        corr_text = opts.get(corr_num, opts.get(str(corr_num), '')) if corr_num else ''
        q_context = f"""
[문항 실제 지문 및 선지 정밀 텍스트]
- 제재 및 주제: {q_item.get('genre', '국어')} | {q_item.get('topic', '')}
- 지문 원문:
\"\"\"{q_item.get('passage', '')}\"\"\"
- 발문: {q_item.get('question', '')}
- 학생이 선택한 선지: {my_pick}번 (선지 내용: "{opt_text}")
- 실제 공식 정답: {corr_num}번 (선지 내용: "{corr_text}")
- 평가원의 함정 설계 원리: {q_item.get('trap_concept', '지문 조건 왜곡 및 인과 전도')}
"""
    else:
        q_context = f"""
[문항 기본 정보]
- 시험명: {exam_info.get('title', '')}
- 문항 번호: {q_num}번
- 학생이 고른 선지: {my_pick}번 (풀이 상태: {status_label})
- 공식 정답 선지: {corr_num}번
- 지침: 대화에 시험지 페이지 이미지가 첨부되어 있으면 그 이미지의 지문·선지를 직접 읽고 근거로 삼으십시오(이미지에 없는 내용은 절대 지어내지 말 것). 이미지가 없을 때만 학생에게 지문의 핵심 어휘와 문장을 직접 질문하여 끄집어내십시오.
"""

    past_profile = get_student_vulnerability_profile(student["student_id"])
    past_context = ""
    if past_profile.get("has_history") and past_profile.get("top_vulnerabilities"):
        top_str = ", ".join([f"'{t[0]}'({t[1]}회)" for t in past_profile["top_vulnerabilities"]])
        rules_sample = "; ".join([f"[{r['exam_title']} {r['q_num']}번: {r['action_rule']}]" for r in past_profile["action_rules"][-3:]]) if past_profile.get("action_rules") else "없음"
        past_context = f"""
[학생의 과거 누적 사고 오류 및 행동 원칙 기록]
- 이 학생({student['name']})의 고질적 취약 패턴: {top_str}
- 과거에 수립했던 행동 원칙: {rules_sample}
- 지도 지침: 이번 문항에서도 동일한 취약 패턴({top_str})을 되풀이했는지 점검하십시오.
"""

    meta_guide = ""
    if matrix_type == "CONFIDENT_WRONG":
        meta_guide = f"""
[🎯 메타인지 코칭 지침: 🚨 확신했으나 오답 (평가원 킬러 함정)]
- 학생은 정답을 완전히 확신하고 오답인 {my_pick}번을 골랐습니다. (공식 정답: {corr_num}번)
- 학생이 지문의 내용을 어떤 방식으로 자기 마음대로 왜곡(선지 임의 변형, 과잉 인과, 전제 조건 누락 등)하여 읽었는지 학생의 답변을 통해 스스로 실토하도록 유도하십시오.
"""
    elif matrix_type == "UNSURE_CORRECT":
        meta_guide = f"""
[🎯 메타인지 코칭 지침: ⚠️ 확신 없으나 정답 (실전 불안 요소)]
- 학생은 정답인 {my_pick}번을 맞히긴 했으나, 시험 당시 확신이 없어 다른 선지와 망설였던 상태입니다.
- 어떤 다른 오답 선지와 마지막까지 갈등했는지, 왜 그 선지가 매력적으로 느껴져 망설였는지 질문하여 다음에는 100% 확신을 갖고 고를 수 있는 판단 기준을 정립시키십시오.
"""
    elif matrix_type == "UNSURE_WRONG":
        meta_guide = f"""
[🎯 메타인지 코칭 지침: ❌ 확신 없고 오답 (독해 사고 공백)]
- 학생은 풀면서도 확신이 없었으며 결국 오답({my_pick}번)을 골랐습니다. (공식 정답: {corr_num}번)
- 개념이나 조건 이해에 공백이 있었거나, 지문의 핵심 문장을 제대로 파악하지 못했던 원인을 짚어 개념적 구멍을 메우도록 이끄십시오.
"""
    elif matrix_type in ["TIMED_OUT_GUESS", "LUCKY_CORRECT"]:
        meta_guide = f"""
[🎯 메타인지 코칭 지침: ⏱️ 시간이 없어서 찍음 (타임 어택 및 시간 관리)]
- 학생은 시험장 시간 부족 또는 직관으로 {my_pick}번을 찍은 상태입니다. (공식 정답: {corr_num}번)
- 시험 운영상 앞선 문항에서 시간이 지체된 원인을 짚어보고, 이 문항에서 선지의 참/거짓을 판별할 수 있는 진짜 '결정적 근거 문장'을 신속하게 발췌독하는 전략을 수립시키십시오.
"""

    return f"""
당신은 대한민국 최고 수준의 수능 국어 '사고 복원 전문 인터뷰어'입니다.
학생이 시험장에서 범한 독해 인지 왜곡과 추론의 오류를 학생 스스로 깨닫도록 이끕니다.

[현재 분석 문항]
- 시험: {exam_info.get('title', '')}
- 문항 번호: {q_num}번
- 학생 풀이 상태: {status_label}
- 학생이 고른 선지: {my_pick}번 (공식 정답: {corr_num}번)
{q_context}
{past_context}
{meta_guide}

[★ 최우선 핵심 행동 지침: 지문의 구체적 내용 인용 필수 (뜬구름 잡는 일반론 금지)]
1. [지문 내용 직접 인용]:
   - 학생의 답변에 반응하거나 질문할 때, **반드시 지문의 구체적 문장, 핵심 어휘, 조건절, 인과관계를 큰따옴표(\"...\")로 직접 인용**하십시오!
   - 절대 "왜 그렇게 생각했나요?" 같은 추상적 사고 질문만 던지지 마십시오.
   - 예시:
     - *"지문에서 '**A는 B와 비례하지 않고 C에 반비례한다**'고 명시했는데, 학생은 선지의 '**B가 커질수록 A도 증가한다**'는 해석을 왜 맞다고 보았나요?"*
     - *"지문에서는 '**충렬이 황성을 지키기 위해 출전했다**'고 했는데, {my_pick}번 선지의 '**가문의 복수를 위해 군사를 요청했다**'는 내용은 지문의 어디에 근거한 생각인가요?"*
     - *"지문 속 '**2비트 동시 반전 오류는 검출할 수 없다**'는 내용과, 학생이 고른 선지의 '**자체 교정을 수행한다**' 사이에 어떤 오해가 있었나요?"*

2. [정오 판별 일방적 누설 금지]:
   - "그건 틀렸습니다", "정답은 3번입니다" 같은 일방적 정답 누설이나 강의식 해설은 하지 마십시오.
   - 학생이 자신이 고른 선지와 지문의 실제 텍스트가 어떻게 어긋났는지 스스로 입으로 시인하도록 유도하십시오.

3. [지문 텍스트가 부분적인 문항일 때의 대응 요령]:
   - 학생에게 "지문의 어느 단락/어떤 핵심 어휘를 보고 그렇게 판단했나요? 지문의 실제 문장을 1개만 들어보세요."라고 지문 팩트 확인을 먼저 요구하고, 학생이 제시한 어휘를 바탕으로 지문과 선지의 괴리를 짚으십시오.

4. [⚡ 스피디 & 단도직입 원칙]:
   - 수험생은 마음이 급합니다. 불필요한 인사말, 칭찬, 위로, 서론은 일절 생략하고 곧바로 팩트 대조 질문으로 들어가십시오.
   - 질문은 1~2문장(공백 포함 150자 이내)으로 신속하고 명쾌하게 던지십시오.
"""

# ==========================================
# 3. 순차 사고 복원 인터뷰 뷰 (Queue Runner)
# ==========================================
def render_interview_stage(client):
    queue = st.session_state.vulnerable_queue
    q_idx = st.session_state.queue_index
    current_q_meta = queue[q_idx]
    q_num = current_q_meta["q_num"]
    my_pick = current_q_meta["my_pick"]
    status_label = current_q_meta["status"]
    correct_opt = current_q_meta.get("correct_opt")
    matrix_type = current_q_meta.get("matrix_type")
    exam_info = st.session_state.exam_info
    student = st.session_state.auth_student

    # 상단 진행 인디케이터
    total_in_queue = len(queue)
    st.progress((q_idx + 1) / total_in_queue)
    col_stat1, col_stat2 = st.columns([3, 1])
    with col_stat1:
        st.markdown(f"#### 🎯 취약 문항 복원 중: **{q_idx + 1} / {total_in_queue} 번째** (문항 번호: **{q_num}번**)")
        caption_base = f"학생: **{student['name']}** | 상태: `{status_label}` | 내가 고른 선지: **{my_pick}번**"
        if correct_opt:
            caption_base += f" | 공식 정답: **{correct_opt}번**"
        profile = get_student_vulnerability_profile(student["student_id"])
        if profile.get("has_history") and profile.get("top_vulnerabilities"):
            top_str = ", ".join([t[0] for t in profile["top_vulnerabilities"][:2]])
            caption_base += f" | 🔍 *과거 취약점 연동: {top_str}*"
        st.caption(caption_base)
    with col_stat2:
        if st.button("⏹️ OMR로 돌아가기", use_container_width=True):
            st.session_state.student_stage = "OMR"
            save_current_student_progress()
            st.rerun()

    # 취약 문항 빠른 점프 및 완료 현황 칩
    done_cnt = len({d.get("q_num") for d in st.session_state.get("diagnosed_items", [])})
    with st.expander(f"📋 문항 이동 (현재 {q_num}번 · 완료 {done_cnt}/{len(queue)}) — 눌러서 펼치기", expanded=False):
        chip_cols = st.columns(min(max(len(queue), 1), 8))
        for idx, item in enumerate(queue):
            col_target = chip_cols[idx % min(max(len(queue), 1), 8)]
            with col_target:
                is_cur = (idx == q_idx)
                is_done = any(d.get("q_num") == item["q_num"] for d in st.session_state.get("diagnosed_items", []))
                icon = "✅" if is_done else ("🎯" if is_cur else "⏳")
                lbl = f"{icon} {item['q_num']}번"
            
                if st.button(lbl, key=f"nav_chip_q_{idx}", use_container_width=True, help=f"{item['q_num']}번 ({item['status']}) - 클릭 시 이동"):
                    if idx != q_idx:
                        st.session_state.queue_index = idx
                        target_q = queue[idx]
                        done_item = next((d for d in st.session_state.get("diagnosed_items", []) if d.get("q_num") == target_q["q_num"]), None)
                        if done_item:
                            st.session_state.interview_step = "ITEM_COMPLETED"
                            st.session_state.current_analysis = done_item
                        else:
                            st.session_state.interview_step = "CHAT"
                            st.session_state.current_analysis = None
                            jump_msg = build_initial_interview_question(
                                exam_info, 
                                target_q['q_num'], 
                                target_q['status'], 
                                target_q['my_pick'],
                                target_q.get('correct_opt'),
                                target_q.get('matrix_type')
                            )
                            st.session_state.chat_history = [{
                                "role": "assistant",
                                "content": jump_msg
                            }]
                        save_current_student_progress()
                        st.rerun()

    # 좌측 PDF창과 우측 채팅창의 완벽한 분리 및 우측 고정 CSS
    st.markdown("""
    <style>
    /* 우측 채팅 열을 화면에 딱 고정 (Sticky) */
    div[data-testid="column"]:nth-of-type(2) {
        position: sticky !important;
        top: 1.5rem !important;
        align-self: flex-start !important;
        z-index: 10 !important;
    }
    /* 좌측 및 우측 스크롤 컨테이너 부드러운 스크롤 */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px;
        box-shadow: 0 4px 12px -2px rgba(14, 14, 41, 0.05);
        border: 1px solid #E6E1DA;
        transition: all 0.2s ease-in-out;
    }
    /* 우측 열 chat_input 한 줄 나란히 배치 강제 (줄바꿈 방지) */
    div[data-testid="stChatInput"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
    }
    div[data-testid="stChatInput"] [data-baseweb="textarea"] {
        flex: 1 1 auto !important;
        max-width: calc(100% - 44px) !important;
    }
    div[data-testid="stChatInput"] textarea {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    div[data-testid="stChatInput"] button {
        flex: 0 0 34px !important;
        margin-left: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

    col_paper, col_chat = st.columns([1.1, 1.1], gap="large")

    # [좌측 열] 시험지 원문 뷰어 (독립 스크롤)
    VIEWER_HEIGHT = 600

    with col_paper:
        pdf_path, pdf_b64, pdf_url = get_exam_pdf_source(exam_info["exam_id"])
        
        tab_pdf, tab_text = st.tabs(["📄 시험지 원문 (PDF)", "📝 문항 텍스트 집중 보기"])
        
        with tab_pdf:
            if pdf_path or pdf_b64 or pdf_url:
                render_pdf_viewer(
                    base64_pdf=pdf_b64, 
                    pdf_url=pdf_url, 
                    pdf_path=pdf_path, 
                    q_num=q_num, 
                    height=VIEWER_HEIGHT, 
                    viewer_id=f"interview_{exam_info['exam_id']}"
                )
            else:
                st.info(f"선생님이 아직 '{exam_info['title']}'의 원문 PDF를 등록하지 않았습니다. [문항 텍스트 집중 보기] 탭을 확인해 주세요.")
                with st.container(height=VIEWER_HEIGHT):
                    q_ctx_fallback = get_question_full_context(exam_info, q_num)
                    if q_ctx_fallback and q_ctx_fallback.get("passage"):
                        render_csat_text_view(q_ctx_fallback, my_pick, status_label)
                    else:
                        st.write(f"**{q_num}번 문항 원문을 책상 위 종이 시험지에서 확인해 주세요.**")

        with tab_text:
            with st.container(height=VIEWER_HEIGHT):
                q_ctx_full = get_question_full_context(exam_info, q_num)
                if q_ctx_full and q_ctx_full.get("passage"):
                    render_csat_text_view(q_ctx_full, my_pick, status_label)
                else:
                    st.write(f"현재 등록된 텍스트 지문이 없습니다. 오프라인 시험지의 **{q_num}번 문항**을 함께 보면서 진행해주세요.")

    # [우측 열] Gemini 소크라테스 인터뷰 (화면 고정)
    with col_chat:
        if st.session_state.interview_step == "CHAT":
            # 상단 헤더: 타이틀(좌측) + 대화 종료 및 요약안 작성하기 버튼(우측)
            col_chat_title, col_finish_btn = st.columns([1.05, 1.35], vertical_alignment="center")
            with col_chat_title:
                st.markdown("<h3 style='margin:0; padding: 2px 0; font-size: 1.22rem;'>💬 AI 사고 복원 인터뷰</h3>", unsafe_allow_html=True)
            with col_finish_btn:
                # 학생 답변 1회 이상(전체 2개 이상) 시 요약안 작성 버튼 활성화 (빠른 진행 지원)
                if len(st.session_state.chat_history) >= 2:
                    if st.button("📝 대화 종료 및 내 사고 요약안 작성하기", use_container_width=True, type="primary", key="btn_finish_interview_top"):
                        with chat_box if 'chat_box' in locals() else st.container():
                            with st.spinner("당시 사고 경로를 1인칭으로 요약 중입니다..."):
                                q_item_ctx = get_question_full_context(exam_info, q_num)
                                passage_ref = f"(지문 제재: {q_item_ctx.get('genre', '')} / 주제: {q_item_ctx.get('topic', '')})" if q_item_ctx else ""
                                summary_prompt = f"""
지금까지의 대화 전문과 지문 텍스트를 바탕으로, 학생이 시험장에서 해당 선지를 고르게 된 '인지 왜곡 및 사고 경로'를 1~2문장으로 명확히 요약해 주십시오. {passage_ref}
지문의 구체적 내용이나 오독한 핵심 어휘를 직접 언급하며, 1인칭('나는 지문의 ~라는 내용을 ~라고 잘못 생각하여 ~했다') 시점으로 작성하세요.
"""
                                contents_for_summary = build_gemini_contents(st.session_state.chat_history)
                                contents_for_summary.append(types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(text=summary_prompt)]
                                ))
                                try:
                                    summary_res = call_gemini_safe(
                                        client,
                                        contents=contents_for_summary
                                    )
                                    st.session_state.draft_summary = summary_res.text
                                    st.session_state.interview_step = "REVIEW"
                                    st.session_state["last_chat_error"] = None
                                    save_current_student_progress()
                                    st.rerun()
                                except Exception as e:
                                    st.session_state["last_chat_error"] = f"사고 요약 작성 실패: {e}"
                                    st.rerun()

            # 1. 고정 높이 스크롤 메시지 박스 (기존보다 길고 시원하게 확대)
            chat_box = st.container(height=VIEWER_HEIGHT - 20, key="chat_scroll_box")
            with chat_box:
                render_kakaotalk_chat(st.session_state.chat_history)
            # 새 메시지가 보이도록 채팅 박스를 항상 맨 아래로 스크롤 (메시지 수가 바뀔 때마다 실행)
            import streamlit.components.v1 as _components
            _components.html(
                f"""<script>/* {len(st.session_state.chat_history)} */
                const doc = window.parent.document;
                const go = () => {{
                  const box = doc.querySelector('.st-key-chat_scroll_box');
                  if (!box) return;
                  [box, ...box.querySelectorAll('*')].forEach(el => {{
                    if (el.scrollHeight > el.clientHeight + 5 && /auto|scroll/.test(getComputedStyle(el).overflowY)) el.scrollTop = el.scrollHeight;
                  }});
                }};
                go(); setTimeout(go, 150); setTimeout(go, 500);
                </script>""", height=0)

            # 2. 🚨 에러가 발생한 경우 고정 표시 (채팅창 바로 아래)
            if st.session_state.get("last_chat_error"):
                st.error("⚠️ **AI 인터뷰 질문 생성 중 오류가 발생했습니다.**")
                with st.expander("🔍 오류 상세 내역 확인하기 (클릭)", expanded=True):
                    st.code(st.session_state["last_chat_error"], language="text")
                
                col_retry, col_close = st.columns([1.5, 1])
                with col_retry:
                    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
                        if st.button("🔄 마지막 생각으로 AI 질문 다시 생성", key="retry_ai_chat_btn", type="primary", use_container_width=True):
                            system_prompt = get_interview_system_prompt(student, exam_info, q_num, status_label, my_pick, correct_opt, matrix_type)
                            gemini_contents = build_gemini_contents(st.session_state.chat_history)
                            with chat_box:
                                with st.spinner("생각의 경로를 분석 중입니다..."):
                                    try:
                                        response = call_gemini_safe(
                                            client,
                                            contents=gemini_contents,
                                            config=types.GenerateContentConfig(
                                                system_instruction=system_prompt,
                                                temperature=0.2,
                                                max_output_tokens=1024
                                            )
                                        )
                                        st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                                        st.session_state["last_chat_error"] = None
                                        save_current_student_progress()
                                        st.rerun()
                                    except Exception as e:
                                        st.session_state["last_chat_error"] = str(e)
                                        st.rerun()
                with col_close:
                    if st.button("✖️ 오류 메시지 닫기", key="close_chat_err_btn", use_container_width=True):
                        st.session_state["last_chat_error"] = None
                        st.rerun()

            # 4. 학생 입력창 (화면 하단에 항상 고정)
            if user_input := st.chat_input("당시 들었던 생각, 헷갈렸던 문장이나 단어를 솔직히 적어주세요..."):
                st.session_state["last_chat_error"] = None
                st.session_state.chat_history.append({"role": "user", "content": user_input})
                with chat_box:
                    with st.spinner("생각의 경로를 분석 중입니다..."):
                        system_prompt = get_interview_system_prompt(student, exam_info, q_num, status_label, my_pick, correct_opt, matrix_type)
                        gemini_contents = build_gemini_contents(st.session_state.chat_history)
                        try:
                            response = call_gemini_safe(
                                client,
                                contents=gemini_contents,
                                config=types.GenerateContentConfig(
                                    system_instruction=system_prompt,
                                    temperature=0.2,
                                    max_output_tokens=1024
                                )
                            )
                            st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                            st.session_state["last_chat_error"] = None
                            save_current_student_progress()
                            st.rerun()
                        except Exception as e:
                            st.session_state["last_chat_error"] = str(e)
                            st.rerun()

        elif st.session_state.interview_step == "REVIEW":
            st.subheader("🔍 사고 복원 내용 확인 및 수정")
            st.info("💡 AI가 대화를 바탕으로 복원한 사고 과정입니다. 실제 내 생각과 다른 부분이 있다면 직접 수정해 주세요.")
            
            # 🚨 확정 단계 에러 발생 시 고정 표시
            if st.session_state.get("last_review_error"):
                st.error("⚠️ **정밀 분석 생성 중 오류가 발생했습니다.**")
                with st.expander("🔍 오류 상세 내역 확인하기 (클릭)", expanded=True):
                    st.code(st.session_state["last_review_error"], language="text")
                if st.button("✖️ 오류 메시지 닫기", key="close_review_err_btn"):
                    st.session_state["last_review_error"] = None
                    st.rerun()

            edited_thought = st.text_area("시험 당시 나의 사고 흐름 (수정 가능)", value=st.session_state.draft_summary, height=130)

            if st.button("✅ 내 사고로 확정하고 정밀 분석 완료하기", type="primary", use_container_width=True):
                with st.spinner("사고 패턴 태깅 및 평가원 함정 구조 분석 중..."):
                    json_prompt = f"""
                    문항: {exam_info['title']} {q_num}번
                    학생의 확정된 사고 과정: "{edited_thought}"
                    학생 선택: {my_pick}번 선지
                    
                    이 사고 과정을 바탕으로 다음 3가지 항목을 JSON 형식으로 출력하십시오.
                    {{
                        "error_tag": "선지 임의 변형, 선지 후반부 검증 생략, 기억 부재의 부재화, 적용 조건 혼동, 관계어·논리 왜곡, 과잉 인과 생성 중 가장 적합한 1개",
                        "evaluator_trap": "학생의 인지 왜곡을 역이용하여 평가원이 이 오답 선지를 설계한 함정의 논리 구조 (1문장)",
                        "action_rule": "학생이 다음 시험장에서 이 오류를 반복하지 않기 위해 되뇌어야 할 단 한 문장의 구체적 행동 원칙"
                    }}
                    """
                    try:
                        json_res = call_gemini_safe(
                            client,
                            contents=json_prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                temperature=0.1
                            )
                        )
                        analysis_data = safe_parse_json(json_res.text)
                        analysis_data["q_num"] = q_num
                        analysis_data["status"] = status_label
                        analysis_data["my_pick"] = my_pick
                        analysis_data["student_thought"] = edited_thought

                        st.session_state.current_analysis = analysis_data
                        # 기존 복원 목록에 중복 문항이 있으면 갱신, 없으면 추가
                        existing_idx = next((i for i, d in enumerate(st.session_state.diagnosed_items) if d.get("q_num") == q_num), None)
                        if existing_idx is not None:
                            st.session_state.diagnosed_items[existing_idx] = analysis_data
                        else:
                            st.session_state.diagnosed_items.append(analysis_data)
                        
                        st.session_state.interview_step = "ITEM_COMPLETED"
                        st.session_state["last_review_error"] = None
                        save_current_student_progress()
                        st.rerun()  # ✅ 성공 시에만 리런
                    except Exception as e:
                        st.session_state["last_review_error"] = str(e)
                        st.error(f"분석 중 오류: {e}")

        elif st.session_state.interview_step == "ITEM_COMPLETED":
            res = st.session_state.current_analysis
            st.success(f"🎉 **{q_num}번 문항** 사고 복원 완료!")
            
            st.markdown(f"**💭 복원된 나의 사고**\n> *\"{res['student_thought']}\"*")
            st.markdown(f"**🚨 사고 오류 태그:** `{res['error_tag']}`")
            st.markdown(f"**😈 평가원의 함정 설계:** {res['evaluator_trap']}")
            st.markdown(f"**💡 나만의 행동 원칙:** *{res['action_rule']}*")

            st.divider()
            # 큐의 다음 문항으로 이동할지 여부 결정
            if q_idx + 1 < len(queue):
                next_q = queue[q_idx + 1]
                col_next_btn, col_skip_rep = st.columns([1.4, 1])
                with col_next_btn:
                    if st.button(f"➡️ 다음 취약 문항 복원하기 ({q_idx + 2} / {len(queue)} - {next_q['q_num']}번)", type="primary", use_container_width=True):
                        st.session_state.queue_index += 1
                        st.session_state.interview_step = "CHAT"
                        st.session_state.current_analysis = None
                        st.session_state.chat_history = [{
                            "role": "assistant",
                            "content": f"다음은 **{next_q['q_num']}번** 문항이야. [{next_q['status']}] 상태로 **{next_q['my_pick']}번**을 고른 당시 생각의 근거를 단도직입적으로 말해줘."
                        }]
                        save_current_student_progress()
                        st.rerun()
                with col_skip_rep:
                    if st.button("📊 3단계 방어 훈련 먼저 보기", use_container_width=True, help="남은 문항은 나중에 복원하고, 지금까지 완료한 문항들의 리포트와 AI 맞춤 훈련을 먼저 진행합니다."):
                        st.session_state.student_stage = "REPORT"
                        save_current_student_progress()
                        st.rerun()
            else:
                if st.button("🏁 모든 취약 문항 복원 완료! 종합 진단 보고서 및 맞춤 처방 보기", type="primary", use_container_width=True):
                    st.session_state.student_stage = "REPORT"
                    save_current_student_progress()
                    st.rerun()

# ==========================================
# 4. 종합 진단 보고서 & AI 기출 탐색 및 인앱 즉석 방어 훈련
# ==========================================
def render_report_stage(client):
    student = st.session_state.auth_student
    exam_info = st.session_state.get("exam_info")
    diagnosed = st.session_state.get("diagnosed_items", [])
    
    if not exam_info or not diagnosed:
        st.info("💡 아직 완료된 문항 복원 기록이 없습니다. 상단 **[1️⃣ OMR 마킹]** 또는 **[2️⃣ 사고 복원]** 단계를 먼저 진행해 주세요.")
        if st.button("⬅️ 1단계 OMR로 이동하기", type="primary"):
            st.session_state.student_stage = "OMR"
            st.rerun()
        return

    # 3단계 진입 상태 자동 저장 (백그라운드 영구 보존)
    save_current_student_progress()

    cfg = get_admin_config()
    master_drive_url = cfg.get("google_drive_folder_url", "")

    if "active_training_problem" not in st.session_state:
        st.session_state.active_training_problem = None
    if "training_feedback" not in st.session_state:
        st.session_state.training_feedback = None

    st.markdown("##### 🎉 종합 사고 복원 리포트 & AI 기출 맞춤 처방")

    # 시험지 공식 정답표 구글 드라이브 링크가 있는 경우 바로가기 제공
    ans_pdf_url = exam_info.get("answer_pdf_url", "")
    if not ans_pdf_url and "current_exam_id" in st.session_state:
        all_exams = get_exams()
        ans_pdf_url = all_exams.get(st.session_state.current_exam_id, {}).get("answer_pdf_url", "")

    if ans_pdf_url and ans_pdf_url.startswith("http"):
        st.markdown(f"""
        <div style="background-color: #FDFBF7; border: 1px solid #E6E1DA; border-left: 4px solid #2B2927; padding: 6px 12px; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem;">
            <span style="color: #2B2927; font-weight: 600;">
                📄 이번 시험({exam_info['title']})의 <b>평가원 공식 정답표 원문 PDF</b>가 연동되어 있습니다.
            </span>
            <a href="{ans_pdf_url}" target="_blank" style="text-decoration: none;">
                <button style="background-color: #2B2927; color: white; border: none; padding: 3px 10px; border-radius: 6px; font-weight: 600; font-size: 0.8rem; cursor: pointer;">
                    공식 정답표 원문 열기 ↗
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)

    st.caption(f"👤 **{student['name']}** ({student['student_id']})  |  📝 {exam_info['title']}  |  🚨 분석된 취약 문항 **{len(diagnosed)}개**")


    # 오류 태그 집계
    tag_counts = {}
    for item in diagnosed:
        t = item["error_tag"]
        tag_counts[t] = tag_counts.get(t, 0) + 1

    st.markdown("##### 📊 나의 인지 오류 패턴")
    _mx = max(tag_counts.values())
    _rows = "".join(
        f'<div style="display:flex;align-items:center;gap:10px;margin:4px 0;font-size:0.9rem;">'
        f'<span style="width:150px;flex:none;color:#2B2927;">{t}</span>'
        f'<div style="flex:1;background:#EEE9E0;border-radius:6px;height:12px;max-width:320px;">'
        f'<div style="width:{cnt/_mx*100:.0f}%;background:#5E7966;height:12px;border-radius:6px;"></div></div>'
        f'<b style="color:#2B2927;">{cnt}회</b></div>'
        for t, cnt in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    )
    st.markdown(_rows, unsafe_allow_html=True)

    st.divider()

    # ---------------- AI 맞춤 기출 탐색 및 즉석 방어 훈련 영역 ----------------
    st.subheader("🎯 AI 맞춤 기출 탐색 & 실전 방어 훈련")
    st.markdown("""
    AI가 최근 3개년 평가원 기출 모의고사 전체 시험지 속에서 **학생의 취약점과 동일한 평가원 함정 구조를 가진 문항**을 탐색했습니다.  
    문항 카드의 **[방어 훈련 시작]** 버튼을 누르면 목록 바로 아래에 시험지와 훈련 화면이 열립니다.
    """)

    # 오류 태그별 AI 탐색 기출 문항 카드 리스트
    for t, cnt in tag_counts.items():
        problems = get_prescription_problems(t)
        with st.container(border=True):
            st.markdown(f"#### 🚨 [{t}] 극복 솔루션 (이번 시험 {cnt}회 감지)")
            st.write(f"AI가 전체 모의고사 PDF 중에서 `{t}` 함정이 가장 날카롭게 설계된 **{len(problems)}개 기출 문제**를 선별했습니다:")
            
            p_cols = st.columns(len(problems))
            for idx, p in enumerate(problems):
                with p_cols[idx]:
                    with st.container(border=True):
                        st.markdown(f"📌 **{p['exam_title']} {p['q_num']}번**")
                        st.caption(f"**제재:** {p['genre']} ({p['page']}p)")
                        st.caption(f"**주제:** {p['topic']}")
                        st.markdown(f"**수행 미션:** *{p['mission']}*")
                        
                        _sel = bool(st.session_state.active_training_problem and st.session_state.active_training_problem.get("id") == p["id"])
                        if st.button("✅ 훈련 중 (아래 확인)" if _sel else f"🎯 방어 훈련 시작 ({p['q_num']}번)", key=f"btn_train_{p['id']}", type="primary" if _sel else "secondary", use_container_width=True):
                            st.session_state.active_training_problem = {**p, "error_tag": t}
                            st.session_state.training_feedback = None
                            save_current_student_progress()
                            st.rerun()

    # 현재 실전 방어 훈련 중인 문항이 있는 경우 상단에 인터랙티브 뷰 렌더링
    if st.session_state.active_training_problem:
        prob = st.session_state.active_training_problem
        with st.container(border=True, key="training_panel"):
            col_th1, col_th2 = st.columns([3, 1])
            with col_th1:
                st.markdown(f"### 🛡️ [실전 방어 훈련] {prob['exam_title']} **{prob['q_num']}번** ({prob['page']}페이지)")
                st.caption(f"제재: {prob['genre']} | 문항 주제: {prob['topic']}")
            with col_th2:
                if st.button("❌ 훈련 닫기", use_container_width=True):
                    st.session_state.active_training_problem = None
                    st.session_state.training_feedback = None
                    st.rerun()

            col_train_pdf, col_train_act = st.columns([1.1, 1.1], gap="large")

            # 좌측: 해당 시험지 PDF 원문 뷰어 (해당 문제 페이지로 자동 점프) 및 텍스트 탭 제공
            with col_train_pdf:
                target_path, target_b64, target_url = get_exam_pdf_source(prob["exam_id"])
                
                tab_tr_pdf, tab_tr_text = st.tabs(["📄 시험지 원문 (PDF)", "📝 문항 텍스트 집중 보기"])
                
                with tab_tr_pdf:
                    if target_path or target_b64 or target_url:
                        render_pdf_viewer(base64_pdf=target_b64, pdf_url=target_url, pdf_path=target_path, initial_page=prob["page"], height=580)
                    else:
                        st.info(f"선생님의 구글 드라이브 또는 기출 저장소에서 '{prob['exam_title']}' 원문을 연결할 수 있습니다.")
                        if master_drive_url:
                            st.markdown(f"""
                            <a href="{master_drive_url}" target="_blank">
                                <button style="background-color: #2B2927; color: white; border: none; padding: 8px 14px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: background 0.2s;">
                                    📂 구글 드라이브에서 '{prob['exam_title']}' 원문 파일 열기 ↗
                                </button>
                            </a>
                            """, unsafe_allow_html=True)

                with tab_tr_text:
                    with st.container(height=580):
                        render_csat_text_view(prob, my_pick=0, status_tag=f"{prob['year']} {prob['month']} | {prob['genre']}")

            # 우측: 방어 미션 수행 및 AI 피드백
            with col_train_act:
                st.markdown(f"""
                <div style="background-color: #FBEEEA; border: 1px solid #E8C4B7; padding: 12px 16px; border-radius: 8px; margin-bottom: 12px;">
                    <b style="color: #8A3F28;">😈 평가원의 함정 설계:</b><br>
                    <span style="color: #6B2A18; font-size: 0.95rem;">{prob['trap_concept']}</span>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                <div style="background-color: #F1F5F0; border: 1px solid #C7D6CB; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px;">
                    <b style="color: #2B2927;">💡 방어 훈련 미션:</b><br>
                    <span style="color: #2B2927; font-size: 0.95rem;">👉 <b>{prob['mission']}</b></span>
                </div>
                """, unsafe_allow_html=True)

                defense_input = st.text_area(
                    f"📝 위 시험지의 {prob['q_num']}번 문제를 보고, 방어 미션에 맞추어 선지를 검증한 생각이나 오답 판별 근거를 적어보세요:",
                    height=140,
                    placeholder="예: 선지의 '~하기 위하여'라는 목적 표현이 지문의 2문단 3번째 줄에 서술된 '결과'와 인과관계가 전도되어 있어 오답으로 판별했습니다."
                )

                if st.button("🚀 AI에게 방어 검증 받기", type="primary", use_container_width=True):
                    if not client:
                        st.error("Gemini API Key가 설정되지 않아 피드백을 생성할 수 없습니다.")
                    elif not defense_input.strip():
                        st.warning("선지를 검증한 생각을 먼저 적어주세요.")
                    else:
                        with st.spinner("방어 논리를 정밀 분석하고 있습니다..."):
                            try:
                                fb = evaluate_student_defense(client, prob, defense_input)
                                st.session_state.training_feedback = fb
                                st.session_state.setdefault("defense_logs", []).append({
                                    "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "exam_title": prob["exam_title"], "q_num": prob["q_num"],
                                    "error_tag": prob.get("error_tag") or prob.get("trap_type") or "",
                                    "trap": prob.get("trap_concept", ""), "mission": prob.get("mission", ""),
                                    "answer": defense_input.strip(), "feedback": fb,
                                })
                                st.session_state["training_feedback_error"] = None
                                save_current_student_progress()
                                st.rerun()  # ✅ 성공 시에만 리런
                            except Exception as e:
                                st.session_state["training_feedback_error"] = str(e)
                                st.error(f"피드백 생성 오류: {e}")

                if st.session_state.get("training_feedback_error"):
                    st.error(f"⚠️ **방어 코칭 피드백 생성 실패:**\n\n{st.session_state['training_feedback_error']}")

                if st.session_state.training_feedback:
                    import re as _re, html as _html
                    _fb_html = _re.sub(r"\*\*(.+?)\*\*", r"<b></b>", _html.escape(st.session_state.training_feedback)).replace(chr(10), "<br>")
                    st.divider()
                    st.markdown(f"""
                    <div style="background-color: #F5F2EB; border: 1px solid #E6E1DA; border-left: 4px solid #2B2927; padding: 14px 16px; border-radius: 10px; box-shadow: 0 2px 8px -2px rgba(14, 14, 41, 0.05);">
                        <b style="color: #2B2927; font-size: 1.02rem;">👨‍🏫 AI 1:1 방어 코칭:</b><br>
                        <div style="margin-top: 8px; color: #4B4640; line-height: 1.6;">
                            {_fb_html}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            st.divider()

    if st.session_state.active_training_problem:
        import streamlit.components.v1 as _c2
        _c2.html(f"""<script>/* {st.session_state.active_training_problem['id']} */
        setTimeout(()=>{{const e=window.parent.document.querySelector('.st-key-training_panel'); if(e) e.scrollIntoView({{behavior:'smooth',block:'start'}});}},250);
        </script>""", height=0)

    st.divider()
    st.subheader("📝 문항별 복원된 나의 사고 & 행동 원칙 총정리")
    for item in diagnosed:
        with st.expander(f"📌 {item['q_num']}번 문항 (선택: {item['my_pick']}번 | 태그: {item['error_tag']})"):
            st.markdown(f"**💭 나의 사고 과정:** {item['student_thought']}")
            st.markdown(f"**😈 평가원 함정 구조:** {item['evaluator_trap']}")
            st.info(f"**💡 행동 원칙:** {item['action_rule']}")

    st.divider()
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("💾 이 진단 결과를 교사 대시보드로 제출", type="primary", use_container_width=True):
            sub_data = {
                "student_id": student["student_id"],
                "student_name": student["name"],
                "exam_id": exam_info["exam_id"],
                "exam_title": exam_info["title"],
                "total_time": st.session_state.total_time,
                "time_pressure": st.session_state.time_pressure,
                "diagnosed_items": diagnosed,
                "error_tags": list(tag_counts.keys()),
                "defense_logs": st.session_state.get("defense_logs", [])
            }
            save_submission(sub_data)
            
            # 구글 시트 연동 전송
            gas_url = cfg.get("gas_api_url", "")
            if gas_url and gas_url.startswith("http"):
                try:
                    requests.post(gas_url, json=sub_data, timeout=5)
                except Exception:
                    pass
            st.toast("선생님께 진단 리포트가 성공적으로 제출되었습니다!", icon="✅")

    with col_b2:
        if st.button("🔄 새로운 시험 진단하기 (초기화)", use_container_width=True):
            clear_student_progress(student["student_id"])
            st.session_state.student_stage = "OMR"
            st.session_state.exam_info = None
            st.session_state.vulnerable_queue = []
            st.session_state.queue_index = 0
            st.session_state.diagnosed_items = []
            st.session_state.active_training_problem = None
            st.session_state.training_feedback = None
            if "omr_df" in st.session_state:
                del st.session_state["omr_df"]
            st.rerun()
