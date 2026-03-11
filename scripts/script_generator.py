#!/usr/bin/env python3
"""
Gemini API를 사용한 스크립트 생성 - v2 (강화 버전)
"""

import time
import random
import json
from pathlib import Path
from utils import (
    logger, get_project_root, get_env, safe_json_loads,
    read_file, read_json, write_json, get_today_str, generate_hash
)

# Gemini SDK import
try:
    import google.generativeai as genai
except ImportError:
    logger.error("google-generativeai 패키지를 설치하세요: pip install google-generativeai")
    raise


class ScriptGenerator:
    """Gemini 기반 스크립트 생성기 v2"""
    
    def __init__(self, config):
        self.config = config
        self.api_key = get_env('GEMINI_API_KEY', required=True)
        
        genai.configure(api_key=self.api_key)
        
        self.model_name = config.get_gemini_model()
        self.fallback_models = config.get_gemini_fallback_models()
        self.temperature = config.get_gemini_temperature()
        self.max_tokens = config.get_gemini_max_tokens()
        self.retry_count = config.get_gemini_retry_count()
        
        self.project_root = get_project_root()
        
        logger.info(f"ScriptGenerator 초기화 (모델: {self.model_name})")
    
    def _load_prompt_template(self, category_id, language='ko'):
        """프롬프트 템플릿 로드"""
        prompts_dir = self.project_root / "config" / "prompts"
        prompt_file = prompts_dir / f"{category_id}.txt"
        
        if prompt_file.exists():
            template = read_file(prompt_file)
            logger.info(f"프롬프트 로드: {prompt_file.name}")
            return template
        
        logger.warning(f"프롬프트 파일 없음: {prompt_file}, 기본 프롬프트 사용")
        return self._get_default_prompt(category_id, language)
    
    def _get_default_prompt(self, category_id, language='ko'):
        """기본 프롬프트 생성 (프롬프트 파일이 없을 때)"""
        category_name = self.config.get_category_name(language=language)
        
        # 주의: f-string이므로 JSON의 { } 는 {{ }} 로 이스케이프
        if language == 'ko':
            return f"""당신은 유튜브 쇼츠 "뇌를 깨우는 30초" 채널의 전문 작가입니다.
"{category_name}" 주제로 30초 분량의 쇼츠 스크립트를 작성하세요.

## 규칙
1. 총 나레이션은 80-120자 이내 (한국어 기준, 약 25-30초 분량)
2. 첫 문장은 반드시 강력한 후킹으로 시작 (질문 또는 충격적 사실)
3. 중간에 반전이나 놀라운 포인트 필수
4. 마지막은 구독/좋아요 유도 (간결하게 1문장)
5. 실제 심리학 연구/이론에 기반
6. 쉽고 대중적인 언어 사용
7. 이전에 다룬 주제와 겹치지 않게

## 이전 주제
{{previous_topics}}

## 출력 형식
반드시 아래와 같은 JSON 형식으로만 출력하세요. JSON 외에 다른 텍스트는 절대 포함하지 마세요.

{{
  "title": "영상 제목 (최대 30자, 호기심 자극)",
  "hook": "첫 3초 후킹 문장",
  "body": "본문 (핵심 정보)",
  "cta": "마무리 CTA",
  "full_script": "전체 나레이션 (hook+body+cta)",
  "description": "유튜브 설명 (50자 이내)",
  "search_keyword": "배경영상 검색용 영어 키워드 1개",
  "subtitle_segments": [
    {{"text": "자막1", "duration": 3}},
    {{"text": "자막2", "duration": 4}},
    {{"text": "자막3", "duration": 5}},
    {{"text": "자막4", "duration": 4}},
    {{"text": "자막5", "duration": 3}}
  ]
}}"""
        else:
            return f"""You are an expert scriptwriter for the YouTube Shorts channel "30-Second Brain Hack".
Write a 30-second script about "{category_name}".

## Rules
1. Total narration: 50-80 words (about 25-30 seconds)
2. Start with a powerful hook (question or shocking fact)
3. Include a twist or surprising point
4. End with a brief CTA (subscribe/like)
5. Based on real psychology research
6. Use simple, accessible language
7. Don't repeat previous topics

## Previous topics
{{previous_topics}}

## Output format
Output ONLY the JSON below. Do not include any other text.

{{
  "title": "Video title (max 60 chars)",
  "hook": "First 3-second hook",
  "body": "Main content",
  "cta": "Closing CTA",
  "full_script": "Full narration (hook+body+cta)",
  "description": "YouTube description (under 100 chars)",
  "search_keyword": "One English keyword for background video",
  "subtitle_segments": [
    {{"text": "subtitle1", "duration": 3}},
    {{"text": "subtitle2", "duration": 4}},
    {{"text": "subtitle3", "duration": 5}},
    {{"text": "subtitle4", "duration": 4}},
    {{"text": "subtitle5", "duration": 3}}
  ]
}}"""
    
    def _load_history(self):
        """히스토리 로드"""
        history_config = self.config.get_history_config()
        history_file = self.project_root / history_config.get('file', 'history/generated_topics.json')
        return read_json(history_file)
    
    def _save_history(self, category_id, topic_data):
        """히스토리 저장"""
        history_config = self.config.get_history_config()
        if not history_config.get('enabled', True):
            return
        
        history_file = self.project_root / history_config.get('file', 'history/generated_topics.json')
        max_records = history_config.get('max_records', 500)
        
        history = read_json(history_file)
        
        if 'topics' not in history:
            history['topics'] = []
        
        record = {
            'date': get_today_str(),
            'category': category_id,
            'title': topic_data.get('title', ''),
            'hash': generate_hash(topic_data.get('full_script', '')),
        }
        
        history['topics'].append(record)
        
        if len(history['topics']) > max_records:
            history['topics'] = history['topics'][-max_records:]
        
        history['last_updated'] = get_today_str()
        write_json(history_file, history)
        logger.info(f"히스토리 저장 완료 (총 {len(history['topics'])}개)")
    
    def _get_previous_topics(self, category_id):
        """이전 주제 목록"""
        history = self._load_history()
        topics = history.get('topics', [])
        
        same_category = [t for t in topics if t.get('category') == category_id]
        recent = same_category[-50:]
        
        if not recent:
            return "아직 없음"
        
        return '\n'.join([f"- {t.get('title', '')}" for t in recent])
    
    def _call_gemini(self, prompt, model_name=None):
        """Gemini API 호출 (향상된 에러 처리)"""
        if model_name is None:
            model_name = self.model_name
        
        try:
            model = genai.GenerativeModel(
                model_name,
                generation_config=genai.types.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    response_mime_type="application/json",  # JSON 모드 강제
                ),
            )
            
            response = model.generate_content(prompt)
            
            if response and response.text:
                logger.info(f"Gemini 응답 수신 ({model_name}, {len(response.text)}자)")
                # 디버그: 응답 앞부분 로깅
                logger.debug(f"응답 미리보기: {response.text[:200]}")
                return response.text
            else:
                # candidates 확인
                if response and response.candidates:
                    for candidate in response.candidates:
                        if candidate.content and candidate.content.parts:
                            text = candidate.content.parts[0].text
                            if text:
                                logger.info(f"Gemini 응답 (candidates에서 추출)")
                                return text
                
                logger.warning(f"Gemini 빈 응답 ({model_name})")
                if response:
                    logger.warning(f"  prompt_feedback: {getattr(response, 'prompt_feedback', 'N/A')}")
                return None
                
        except Exception as e:
            error_str = str(e)
            
            # 429 Rate Limit 감지
            if '429' in error_str:
                logger.error(f"⚠️ API 할당량 초과 ({model_name}): 잠시 후 재시도 필요")
            # 모델 없음 감지
            elif '404' in error_str or 'not found' in error_str.lower():
                logger.error(f"⚠️ 모델을 찾을 수 없음 ({model_name})")
            else:
                logger.error(f"Gemini API 오류 ({model_name}): {e}")
            
            return None
    
    def _call_gemini_without_json_mode(self, prompt, model_name=None):
        """JSON 모드 없이 호출 (폴백용)"""
        if model_name is None:
            model_name = self.model_name
        
        try:
            model = genai.GenerativeModel(
                model_name,
                generation_config=genai.types.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    # response_mime_type 없음 → 일반 텍스트 모드
                ),
            )
            
            response = model.generate_content(prompt)
            
            if response and response.text:
                logger.info(f"Gemini 응답 수신 - 텍스트 모드 ({model_name}, {len(response.text)}자)")
                return response.text
            
            return None
            
        except Exception as e:
            logger.error(f"Gemini API 오류 (텍스트 모드, {model_name}): {e}")
            return None
    
    def generate(self, category_id=None, weekday=None, language='ko'):
        """스크립트 생성 메인 함수"""
        
        if category_id is None:
            category_id = self.config.get_category_id(weekday)
        
        logger.info(f"스크립트 생성 시작: 카테고리={category_id}, 언어={language}")
        
        # 프롬프트 준비
        template = self._load_prompt_template(category_id, language)
        previous_topics = self._get_previous_topics(category_id)
        prompt = template.replace('{previous_topics}', previous_topics)
        
        # 모델 리스트 구성
        models_to_try = [self.model_name] + self.fallback_models
        # 중복 제거
        seen = set()
        unique_models = []
        for m in models_to_try:
            if m not in seen:
                seen.add(m)
                unique_models.append(m)
        models_to_try = unique_models
        
        result = None
        
        for model_name in models_to_try:
            # ─── 시도 1: JSON 모드로 호출 ───
            for attempt in range(self.retry_count):
                logger.info(f"시도 {attempt+1}/{self.retry_count} (모델: {model_name}, JSON모드)")
                
                raw_response = self._call_gemini(prompt, model_name)
                
                if raw_response:
                    parsed = safe_json_loads(raw_response)
                    
                    if parsed and self._validate_script(parsed):
                        result = parsed
                        logger.info(f"✅ 스크립트 생성 성공: {parsed.get('title', '')}")
                        break
                    else:
                        logger.warning(f"JSON 파싱/검증 실패 (시도 {attempt+1})")
                        # 디버그: 실패한 응답 출력
                        if raw_response:
                            logger.warning(f"  응답 앞부분: {raw_response[:300]}")
                
                if attempt < self.retry_count - 1:
                    delay = self.config.get('gemini', 'retry_delay', default=5)
                    logger.info(f"  {delay}초 대기...")
                    time.sleep(delay)
            
            if result:
                break
            
            # ─── 시도 2: 텍스트 모드로 재시도 ───
            logger.info(f"텍스트 모드로 재시도 (모델: {model_name})")
            raw_response = self._call_gemini_without_json_mode(prompt, model_name)
            
            if raw_response:
                parsed = safe_json_loads(raw_response)
                if parsed and self._validate_script(parsed):
                    result = parsed
                    logger.info(f"✅ 스크립트 생성 성공 (텍스트 모드): {parsed.get('title', '')}")
                    break
            
            logger.warning(f"모델 {model_name} 완전 실패, 다음 모델...")
            
            # 모델 전환 전 대기 (rate limit 방지)
            time.sleep(3)
        
        if not result:
            logger.error("❌ 모든 모델에서 스크립트 생성 실패!")
            raise Exception("스크립트 생성 실패: 모든 모델 및 모드에서 실패")
        
        # 히스토리 저장
        self._save_history(category_id, result)
        
        return result
    
    def _validate_script(self, data):
        """스크립트 데이터 검증 (완화된 버전)"""
        if not isinstance(data, dict):
            logger.warning("검증 실패: dict 아님")
            return False
        
        # full_script 필수
        script = data.get('full_script', '')
        if not script or len(script) < 10:
            logger.warning(f"검증 실패: full_script 부족 ({len(script)}자)")
            return False
        
        # title 필수
        title = data.get('title', '')
        if not title:
            logger.warning("검증 실패: title 없음")
            return False
        
        # subtitle_segments 있으면 좋고, 없으면 자동 생성
        segments = data.get('subtitle_segments', [])
        if not segments or len(segments) < 1:
            logger.warning("subtitle_segments 부족, 자동 생성")
            data['subtitle_segments'] = self._auto_generate_segments(script)
        
        # 누락 필드 기본값 채우기
        if 'hook' not in data:
            data['hook'] = script[:50]
        if 'body' not in data:
            data['body'] = script
        if 'cta' not in data:
            data['cta'] = "구독과 좋아요 부탁드려요!"
        if 'description' not in data:
            data['description'] = title
        if 'search_keyword' not in data:
            data['search_keyword'] = 'psychology brain'
        
        logger.info(f"검증 통과: title='{title}', script={len(script)}자, segments={len(data['subtitle_segments'])}개")
        return True
    
    def _auto_generate_segments(self, full_script):
        """full_script에서 자동으로 자막 세그먼트 생성"""
        import re
        
        # 문장 분할
        sentences = re.split(r'(?<=[.?!。])\s*', full_script)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return [{"text": full_script, "duration": 5}]
        
        # 각 문장을 세그먼트로
        total_duration = 28  # 목표 총 시간
        per_segment = total_duration / len(sentences)
        
        segments = []
        for sentence in sentences:
            # 글자 수 기반 시간 배분
            char_count = len(sentence)
            # 한글 기준 약 초당 4-5자
            estimated_duration = max(2, min(char_count / 4.5, 8))
            segments.append({
                "text": sentence,
                "duration": round(estimated_duration, 1)
            })
        
        logger.info(f"자막 세그먼트 자동 생성: {len(segments)}개")
        return segments
