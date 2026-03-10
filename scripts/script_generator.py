#!/usr/bin/env python3
"""
Gemini API를 사용한 스크립트 생성
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
    """Gemini 기반 스크립트 생성기"""
    
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
        
        # 카테고리별 프롬프트 파일
        prompt_file = prompts_dir / f"{category_id}.txt"
        
        if prompt_file.exists():
            template = read_file(prompt_file)
            logger.info(f"프롬프트 로드: {prompt_file.name}")
            return template
        
        # 기본 프롬프트
        logger.warning(f"프롬프트 파일 없음: {prompt_file}, 기본 프롬프트 사용")
        return self._get_default_prompt(category_id, language)
    
    def _get_default_prompt(self, category_id, language='ko'):
        """기본 프롬프트 생성"""
        category_name = self.config.get_category_name(language=language)
        
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

## 출력 형식 (반드시 JSON)
{{{{
  "title": "영상 제목 (최대 30자, 호기심 자극)",
  "hook": "첫 3초 후킹 문장",
  "body": "본문 (핵심 정보)",
  "cta": "마무리 CTA",
  "full_script": "전체 나레이션 (hook+body+cta)",
  "description": "유튜브 설명 (50자 이내)",
  "search_keyword": "배경영상 검색용 영어 키워드 1개",
  "subtitle_segments": [
    {{{{"text": "자막1", "duration": 3}}}},
    {{{{"text": "자막2", "duration": 4}}}}
  ]
}}}}"""
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

## Output format (must be JSON)
{{{{
  "title": "Video title (max 60 chars, curiosity-inducing)",
  "hook": "First 3-second hook",
  "body": "Main content",
  "cta": "Closing CTA",
  "full_script": "Full narration (hook+body+cta)",
  "description": "YouTube description (under 100 chars)",
  "search_keyword": "One English keyword for background video",
  "subtitle_segments": [
    {{{{"text": "subtitle1", "duration": 3}}}},
    {{{{"text": "subtitle2", "duration": 4}}}}
  ]
}}}}"""
    
    def _load_history(self):
        """히스토리 로드 (중복 방지)"""
        history_config = self.config.get_history_config()
        history_file = self.project_root / history_config.get('file', 'history/generated_topics.json')
        
        history = read_json(history_file)
        return history
    
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
        
        # 최대 기록 수 제한
        if len(history['topics']) > max_records:
            history['topics'] = history['topics'][-max_records:]
        
        history['last_updated'] = get_today_str()
        
        write_json(history_file, history)
        logger.info(f"히스토리 저장 완료 (총 {len(history['topics'])}개)")
    
    def _get_previous_topics(self, category_id):
        """이전 주제 목록 (중복 방지용)"""
        history = self._load_history()
        topics = history.get('topics', [])
        
        # 같은 카테고리의 최근 50개
        same_category = [t for t in topics if t.get('category') == category_id]
        recent = same_category[-50:]
        
        if not recent:
            return "아직 없음"
        
        return '\n'.join([f"- {t.get('title', '')}" for t in recent])
    
    def _call_gemini(self, prompt, model_name=None):
        """Gemini API 호출"""
        if model_name is None:
            model_name = self.model_name
        
        try:
            model = genai.GenerativeModel(model_name)
            
            generation_config = genai.types.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )
            
            response = model.generate_content(
                prompt,
                generation_config=generation_config,
            )
            
            if response and response.text:
                logger.info(f"Gemini 응답 수신 ({model_name})")
                return response.text
            else:
                logger.warning(f"Gemini 빈 응답 ({model_name})")
                return None
                
        except Exception as e:
            logger.error(f"Gemini API 오류 ({model_name}): {e}")
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
        
        # Gemini 호출 (재시도 로직)
        models_to_try = [self.model_name] + self.fallback_models
        result = None
        
        for model_name in models_to_try:
            for attempt in range(self.retry_count):
                logger.info(f"시도 {attempt+1}/{self.retry_count} (모델: {model_name})")
                
                raw_response = self._call_gemini(prompt, model_name)
                
                if raw_response:
                    parsed = safe_json_loads(raw_response)
                    
                    if parsed and self._validate_script(parsed):
                        result = parsed
                        logger.info(f"스크립트 생성 성공: {parsed.get('title', '')}")
                        break
                    else:
                        logger.warning(f"JSON 파싱/검증 실패, 재시도...")
                
                if attempt < self.retry_count - 1:
                    delay = self.config.get('gemini', 'retry_delay', default=5)
                    time.sleep(delay)
            
            if result:
                break
            logger.warning(f"모델 {model_name} 실패, 다음 모델 시도...")
        
        if not result:
            logger.error("모든 모델에서 스크립트 생성 실패!")
            raise Exception("스크립트 생성 실패")
        
        # 히스토리 저장
        self._save_history(category_id, result)
        
        return result
    
    def _validate_script(self, data):
        """스크립트 데이터 검증"""
        required_fields = ['title', 'full_script', 'subtitle_segments']
        
        for field in required_fields:
            if field not in data:
                logger.warning(f"필수 필드 누락: {field}")
                return False
        
        # full_script 길이 체크
        script = data.get('full_script', '')
        if len(script) < 20:
            logger.warning(f"스크립트가 너무 짧음: {len(script)}자")
            return False
        
        # subtitle_segments 체크
        segments = data.get('subtitle_segments', [])
        if not segments or len(segments) < 2:
            logger.warning(f"자막 세그먼트 부족: {len(segments)}개")
            return False
        
        return True
