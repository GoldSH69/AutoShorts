#!/usr/bin/env python3
"""
유틸리티 함수 모듈
"""

import os
import sys
import json
import hashlib
import logging
import random
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── 로깅 설정 ───
def setup_logging(level=logging.INFO):
    """로깅 설정"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger('brain30sec')

logger = setup_logging()

# ─── 경로 관련 ───
def get_project_root():
    """프로젝트 루트 경로 반환"""
    return Path(__file__).parent.parent

def ensure_dir(path):
    """디렉토리가 없으면 생성"""
    Path(path).mkdir(parents=True, exist_ok=True)
    return path

def get_output_dir():
    """출력 디렉토리 반환"""
    output = get_project_root() / "output"
    ensure_dir(output)
    return output

# ─── 날짜/시간 ───
def get_korea_now():
    """한국 시간 반환"""
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst)

def get_weekday():
    """오늘 요일 반환 (0=월, 6=일)"""
    return get_korea_now().weekday()

def get_today_str():
    """오늘 날짜 문자열"""
    return get_korea_now().strftime('%Y-%m-%d')

def get_weekday_name_ko():
    """한국어 요일명"""
    names = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
    return names[get_weekday()]

def get_weekday_name_en():
    """영어 요일명"""
    names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return names[get_weekday()]

# ─── 텍스트 처리 ───
def clean_text(text):
    """텍스트 정리"""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    return text

def split_korean_text(text, max_chars=14):
    """한국어 텍스트를 자막용으로 분할"""
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word
        if len(test_line) <= max_chars:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines

def split_english_text(text, max_chars=30):
    """영어 텍스트를 자막용으로 분할"""
    return split_korean_text(text, max_chars)

def split_text_for_subtitle(text, language='ko', max_chars=None):
    """언어별 자막 분할"""
    if language == 'ko':
        mc = max_chars or 14
        return split_korean_text(text, mc)
    else:
        mc = max_chars or 30
        return split_english_text(text, mc)

# ─── JSON 처리 ───
def safe_json_loads(text):
    """안전한 JSON 파싱 (Gemini 응답에서 JSON 추출) - 강화 버전"""
    if not text:
        logger.warning("JSON 파싱: 빈 텍스트")
        return None
    
    original_text = text
    text = text.strip()
    
    # ─── 1단계: 마크다운 코드블록 제거 ───
    # ```json ... ``` 패턴
    code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?\s*```'
    code_matches = re.findall(code_block_pattern, text, re.DOTALL)
    if code_matches:
        text = code_matches[0].strip()
        logger.info("JSON 파싱: 코드블록에서 추출")
    
    # ─── 2단계: 직접 파싱 시도 ───
    try:
        result = json.loads(text)
        logger.info("JSON 파싱: 직접 파싱 성공")
        return result
    except json.JSONDecodeError:
        pass
    
    # ─── 3단계: { } 블록 추출 시도 ───
    # 가장 바깥쪽 { } 찾기
    brace_depth = 0
    start_idx = -1
    end_idx = -1
    
    for i, char in enumerate(text):
        if char == '{':
            if brace_depth == 0:
                start_idx = i
            brace_depth += 1
        elif char == '}':
            brace_depth -= 1
            if brace_depth == 0 and start_idx >= 0:
                end_idx = i + 1
                break
    
    if start_idx >= 0 and end_idx > start_idx:
        json_candidate = text[start_idx:end_idx]
        try:
            result = json.loads(json_candidate)
            logger.info("JSON 파싱: 중괄호 추출 성공")
            return result
        except json.JSONDecodeError:
            # ─── 4단계: 이중 중괄호 수정 시도 ───
            # {{ → { , }} → } 치환
            fixed = json_candidate
            fixed = re.sub(r'\{\{', '{', fixed)
            fixed = re.sub(r'\}\}', '}', fixed)
            try:
                result = json.loads(fixed)
                logger.info("JSON 파싱: 이중 중괄호 수정 후 성공")
                return result
            except json.JSONDecodeError:
                pass
    
    # ─── 5단계: 줄바꿈/특수문자 정리 후 재시도 ───
    cleaned = text
    # 제어 문자 제거
    cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', cleaned)
    # 연속 공백 정리
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # { } 재추출
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            logger.info("JSON 파싱: 정리 후 추출 성공")
            return result
        except json.JSONDecodeError:
            pass
    
    # ─── 6단계: Gemini thinking 모드 응답 처리 ───
    # <think>...</think> 블록 제거
    thinking_removed = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    if thinking_removed != text:
        logger.info("JSON 파싱: thinking 블록 제거 시도")
        return safe_json_loads(thinking_removed)
    
    # ─── 실패 ───
    # 디버그용: 원본 응답 앞부분 출력
    preview = original_text[:500]
    logger.error(f"JSON 파싱 최종 실패. 응답 미리보기:\n{preview}")
    
    return None

# ─── 파일 처리 ───
def read_file(path):
    """파일 읽기"""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    """파일 쓰기"""
    ensure_dir(Path(path).parent)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def read_json(path):
    """JSON 파일 읽기"""
    if not Path(path).exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json(path, data):
    """JSON 파일 쓰기"""
    ensure_dir(Path(path).parent)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── BGM 선택 ───
def select_bgm(category_id, bgm_dir):
    """카테고리에 맞는 BGM 랜덤 선택"""
    bgm_path = Path(bgm_dir) / category_id
    
    if not bgm_path.exists():
        # 카테고리 폴더가 없으면 전체에서 검색
        bgm_path = Path(bgm_dir)
    
    bgm_files = list(bgm_path.glob('*.mp3')) + list(bgm_path.glob('*.wav'))
    
    if not bgm_files:
        # 전체 디렉토리에서 재검색
        bgm_files = list(Path(bgm_dir).rglob('*.mp3')) + list(Path(bgm_dir).rglob('*.wav'))
    
    if not bgm_files:
        logger.warning(f"BGM 파일을 찾을 수 없습니다: {bgm_dir}")
        return None
    
    selected = random.choice(bgm_files)
    logger.info(f"선택된 BGM: {selected.name}")
    return str(selected)

# ─── 해시 생성 ───
def generate_hash(text):
    """텍스트 해시 생성 (중복 체크용)"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

# ─── 환경변수 ───
def get_env(key, default=None, required=False):
    """환경변수 가져오기"""
    value = os.environ.get(key, default)
    if required and not value:
        raise ValueError(f"필수 환경변수가 설정되지 않았습니다: {key}")
    return value
