#!/usr/bin/env python3
"""
Gemini API 스크립트 생성 - v6 (SNS 캡션 + 다중 키워드)
"""

import time
import re
import json
from pathlib import Path
from utils import (
    logger, get_project_root, get_env, safe_json_loads,
    read_file, read_json, write_json, get_today_str, generate_hash
)

try:
    import google.generativeai as genai
except ImportError:
    logger.error("google-generativeai 패키지를 설치하세요")
    raise


# thinking 모델 판별
THINKING_MODELS = {
    'gemini-2.5-flash',
    'gemini-2.5-pro',
}

def is_thinking_model(model_name):
    """thinking 모델인지 확인 (lite는 제외)"""
    name = model_name.lower().replace('models/', '')
    if 'lite' in name:
        return False
    for tm in THINKING_MODELS:
        if tm in name:
            return True
    return False


class ScriptGenerator:
    """Gemini 스크립트 생성기 v6 - SNS 캡션 + 다중 키워드"""
    
    def __init__(self, config):
        self.config = config
        self.api_key = get_env('GEMINI_API_KEY', required=True)
        
        genai.configure(api_key=self.api_key)
        
        self.model_name = config.get_gemini_model()
        self.fallback_models = config.get_gemini_fallback_models()
        self.temperature = config.get_gemini_temperature()
        self.max_tokens = config.get_gemini_max_tokens()
        self.retry_count = config.get_gemini_retry_count()
        self.thinking_budget = config.get('gemini', 'thinking_budget', default=2048)
        
        self.project_root = get_project_root()
        
        logger.info(f"ScriptGenerator v6 초기화 (SNS 캡션 + 다중 키워드)")
        logger.info(f"  주력 모델: {self.model_name} (thinking: {is_thinking_model(self.model_name)})")
        logger.info(f"  백업 모델: {self.fallback_models}")
        logger.info(f"  max_output_tokens: {self.max_tokens}")
    
    # ─── 프롬프트 ───
    
    def _load_prompt_template(self, category_id, language='ko'):
        """프롬프트 로드"""
        prompts_dir = self.project_root / "config" / "prompts"
        prompt_file = prompts_dir / f"{category_id}.txt"
        
        if prompt_file.exists():
            template = read_file(prompt_file)
            logger.info(f"프롬프트 로드: {prompt_file.name}")
            return template
        
        logger.warning(f"프롬프트 파일 없음, 기본 프롬프트 사용")
        return self._get_default_prompt(category_id, language)
    
    def _get_default_prompt(self, category_id, language='ko'):
        """기본 프롬프트 (SNS 캡션 + 다중 키워드 포함)"""
        category_name = self.config.get_category_name(language=language)
        
        return f"""유튜브 쇼츠 "뇌를 깨우는 30초" 채널의 "{category_name}" 스크립트를 작성하세요.

규칙:
- 한국어 나레이션 150-250자
- 첫 문장: 강력한 후킹 (질문 또는 충격적 사실)
- 중간: 반전/놀라운 사실
- 마지막: 구독 유도 1문장
- 실제 심리학 근거 기반

이전 주제: {{previous_topics}}

배경 영상 키워드 규칙:
search_keywords는 Pexels에서 검색할 영어 키워드 3개를 배열로 생성하세요:
- 각 키워드는 1~3단어의 영어 (예: "brain neuron", "thinking person", "dark abstract")
- 영상 내용의 분위기/주제와 맞는 키워드
- 사람 얼굴 정면보다는 추상적/분위기 있는 영상 키워드 선호
- 3개가 서로 다른 느낌이어야 함 (다양한 배경 전환을 위해)

SNS 캡션도 함께 생성하세요:
- instagram_caption: 3~5줄 본문 (이모지 포함, 마지막에 팔로우 유도 CTA)
- instagram_hashtags: 해시태그 10~15개 (#shorts #심리학 #뇌과학 #뇌를깨우는30초 필수)
- tiktok_caption: 1~2줄 짧은 후킹 (이모지 포함)
- tiktok_hashtags: 해시태그 8~10개 (#fyp #틱톡 #심리학 #뇌를깨우는30초 필수)

반드시 아래 JSON 형식으로만 출력하세요:

{{
  "title": "영상 제목 (최대 30자)",
  "hook": "첫 3초 후킹 문장",
  "body": "본문 내용",
  "cta": "마무리 CTA",
  "full_script": "전체 나레이션 (hook+body+cta를 자연스럽게 연결)",
  "description": "유튜브 설명 50자 이내",
  "search_keywords": ["영어키워드1", "영어키워드2", "영어키워드3"],
  "subtitle_segments": [
    {{"text": "자막1", "duration": 3}},
    {{"text": "자막2", "duration": 4}},
    {{"text": "자막3", "duration": 5}},
    {{"text": "자막4", "duration": 4}},
    {{"text": "자막5", "duration": 3}}
  ],
  "instagram_caption": "인스타그램 본문 3~5줄",
  "instagram_hashtags": "#심리학 #자기계발 #뇌과학 #shorts #뇌를깨우는30초 ...",
  "tiktok_caption": "틱톡 후킹 1~2줄",
  "tiktok_hashtags": "#심리학 #fyp #틱톡 #뇌를깨우는30초 ..."
}}"""
    
    # ─── 히스토리 ───
    
    def _load_history(self):
        history_config = self.config.get_history_config()
        history_file = self.project_root / history_config.get('file', 'history/generated_topics.json')
        return read_json(history_file)
    
    def _save_history(self, category_id, topic_data):
        history_config = self.config.get_history_config()
        if not history_config.get('enabled', True):
            return
        
        history_file = self.project_root / history_config.get('file', 'history/generated_topics.json')
        max_records = history_config.get('max_records', 500)
        
        history = read_json(history_file)
        if 'topics' not in history:
            history['topics'] = []
        
        history['topics'].append({
            'date': get_today_str(),
            'category': category_id,
            'title': topic_data.get('title', ''),
            'hash': generate_hash(topic_data.get('full_script', '')),
        })
        
        if len(history['topics']) > max_records:
            history['topics'] = history['topics'][-max_records:]
        
        history['last_updated'] = get_today_str()
        write_json(history_file, history)
        logger.info(f"히스토리 저장 (총 {len(history['topics'])}개)")
    
    def _get_previous_topics(self, category_id):
        history = self._load_history()
        topics = history.get('topics', [])
        same_cat = [t for t in topics if t.get('category') == category_id]
        recent = same_cat[-50:]
        if not recent:
            return "아직 없음"
        return '\n'.join([f"- {t.get('title', '')}" for t in recent])
    
    # ─── Gemini API 호출 ───
    
    def _call_gemini(self, prompt, model_name, use_json_mode=True):
        """Gemini API 호출 (모델에 따라 자동 최적화)"""
        thinking = is_thinking_model(model_name)
        
        try:
            gen_config = {
                'temperature': self.temperature,
                'max_output_tokens': self.max_tokens,
            }
            
            if use_json_mode:
                gen_config['response_mime_type'] = 'application/json'
            
            if thinking:
                try:
                    gen_config['thinking_config'] = {
                        'thinking_budget': self.thinking_budget
                    }
                    logger.info(f"  thinking 모델, budget={self.thinking_budget}")
                except Exception:
                    logger.warning(f"  thinking_config 미지원, 기본 설정 사용")
            
            mode_str = "JSON" if use_json_mode else "텍스트"
            think_str = "+thinking" if thinking else ""
            logger.info(f"  호출: {model_name} [{mode_str}{think_str}]")
            
            model = genai.GenerativeModel(
                model_name,
                generation_config=gen_config,
            )
            
            response = model.generate_content(prompt)
            
            text = None
            
            try:
                if response and response.text:
                    text = response.text
            except Exception:
                pass
            
            if not text:
                try:
                    if response and response.candidates:
                        for candidate in response.candidates:
                            if candidate.content and candidate.content.parts:
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        if hasattr(part, 'thought') and part.thought:
                                            continue
                                        text = part.text
                                        break
                            if text:
                                break
                except Exception as e:
                    logger.warning(f"  candidates 추출 실패: {e}")
            
            if text:
                logger.info(f"  ✅ 응답 수신: {len(text)}자")
                logger.info(f"  미리보기: {text[:150]}...")
                return text
            else:
                logger.warning(f"  ⚠️ 빈 응답")
                try:
                    if response:
                        feedback = getattr(response, 'prompt_feedback', None)
                        if feedback:
                            logger.warning(f"  prompt_feedback: {feedback}")
                except Exception:
                    pass
                return None
            
        except Exception as e:
            error_str = str(e)
            
            if '429' in error_str:
                logger.error(f"  ❌ 할당량 초과 ({model_name})")
            elif '404' in error_str or 'not found' in error_str.lower():
                logger.error(f"  ❌ 모델 없음 ({model_name})")
            elif 'response_mime_type' in error_str:
                logger.warning(f"  ⚠️ JSON 모드 미지원 ({model_name}), 텍스트 모드로 전환")
                if use_json_mode:
                    return self._call_gemini(prompt, model_name, use_json_mode=False)
            elif 'thinking_config' in error_str or 'thinking_budget' in error_str:
                logger.warning(f"  ⚠️ thinking_config 미지원, 제거 후 재시도")
                return self._call_gemini_simple(prompt, model_name, use_json_mode)
            else:
                logger.error(f"  ❌ API 오류 ({model_name}): {error_str[:200]}")
            
            return None
    
    def _call_gemini_simple(self, prompt, model_name, use_json_mode=True):
        """최소 설정으로 호출 (thinking_config 없이)"""
        try:
            gen_config = {
                'temperature': self.temperature,
                'max_output_tokens': self.max_tokens,
            }
            if use_json_mode:
                gen_config['response_mime_type'] = 'application/json'
            
            model = genai.GenerativeModel(model_name, generation_config=gen_config)
            response = model.generate_content(prompt)
            
            if response and response.text:
                logger.info(f"  ✅ 심플 모드 응답: {len(response.text)}자")
                return response.text
            return None
            
        except Exception as e:
            if 'response_mime_type' in str(e) and use_json_mode:
                return self._call_gemini_simple(prompt, model_name, use_json_mode=False)
            logger.error(f"  ❌ 심플 모드도 실패: {e}")
            return None
    
    # ─── 메인 생성 ───
    
    def generate(self, category_id=None, weekday=None, language='ko'):
        """스크립트 생성"""
        
        if category_id is None:
            category_id = self.config.get_category_id(weekday)
        
        logger.info(f"스크립트 생성 시작: 카테고리={category_id}, 언어={language}")
        
        template = self._load_prompt_template(category_id, language)
        previous_topics = self._get_previous_topics(category_id)
        prompt = template.replace('{previous_topics}', previous_topics)
        
        models = []
        seen = set()
        for m in [self.model_name] + self.fallback_models:
            if m not in seen:
                seen.add(m)
                models.append(m)
        
        logger.info(f"시도할 모델: {models}")
        
        result = None
        
        for model_name in models:
            logger.info(f"\n{'─'*50}")
            logger.info(f"📡 모델: {model_name}")
            logger.info(f"{'─'*50}")
            
            for attempt in range(self.retry_count):
                logger.info(f"[시도 {attempt+1}/{self.retry_count}] JSON 모드")
                
                raw = self._call_gemini(prompt, model_name, use_json_mode=True)
                
                if raw:
                    parsed = safe_json_loads(raw)
                    if parsed and self._validate_script(parsed):
                        result = parsed
                        break
                    else:
                        logger.warning(f"  파싱/검증 실패 (응답 {len(raw)}자)")
                
                if attempt < self.retry_count - 1:
                    delay = self.config.get('gemini', 'retry_delay', default=10)
                    logger.info(f"  {delay}초 대기...")
                    time.sleep(delay)
            
            if result:
                break
            
            logger.info(f"[텍스트 모드] 재시도")
            raw = self._call_gemini(prompt, model_name, use_json_mode=False)
            
            if raw:
                parsed = safe_json_loads(raw)
                if parsed and self._validate_script(parsed):
                    result = parsed
                    break
            
            logger.warning(f"  모델 {model_name} 실패, 다음 모델로...")
            time.sleep(3)
        
        if not result:
            logger.error("❌ 모든 모델에서 실패!")
            raise Exception("스크립트 생성 실패: 사용 가능한 모델 없음")
        
        logger.info(f"\n✅ 스크립트 생성 성공!")
        logger.info(f"  제목: {result.get('title', '')}")
        logger.info(f"  스크립트: {result.get('full_script', '')[:80]}...")
        logger.info(f"  검색 키워드: {result.get('search_keywords', [])}")
        logger.info(f"  인스타 캡션: {'있음' if result.get('instagram_caption') else '기본값'}")
        logger.info(f"  틱톡 캡션: {'있음' if result.get('tiktok_caption') else '기본값'}")
        
        self._save_history(category_id, result)
        return result
    
    # ─── 검증 ───
    
    def _validate_script(self, data):
        """스크립트 검증 (SNS 캡션 + 다중 키워드 포함)"""
        if not isinstance(data, dict):
            logger.warning("검증 실패: dict 아님")
            return False
        
        title = data.get('title', '')
        if not title or len(title) < 2:
            logger.warning(f"검증 실패: title 없음")
            return False
        
        # full_script 복구
        script = data.get('full_script', '')
        if not script or len(script) < 10:
            hook = data.get('hook', '')
            body = data.get('body', '')
            cta = data.get('cta', '')
            combined = f"{hook} {body} {cta}".strip()
            
            if len(combined) >= 10:
                data['full_script'] = combined
                script = combined
                logger.info(f"  full_script 복구: {len(script)}자")
            else:
                logger.warning(f"검증 실패: 스크립트 부족")
                return False
        
        # 자막 자동 생성
        segments = data.get('subtitle_segments', [])
        if not segments or not isinstance(segments, list) or len(segments) < 1:
            data['subtitle_segments'] = self._auto_segments(script)
        else:
            valid_segments = []
            for seg in segments:
                if isinstance(seg, dict) and seg.get('text'):
                    if 'duration' not in seg:
                        seg['duration'] = 3
                    valid_segments.append(seg)
            
            if valid_segments:
                data['subtitle_segments'] = valid_segments
            else:
                data['subtitle_segments'] = self._auto_segments(script)
        
        # 기본값 채우기 (기존 필드)
        if not data.get('hook'):
            data['hook'] = script[:50]
        if not data.get('body'):
            data['body'] = script
        if not data.get('cta'):
            data['cta'] = '구독과 좋아요 부탁드려요!'
        if not data.get('description'):
            data['description'] = title
        
        # ─── 검색 키워드 (다중) ───
        # search_keywords가 없으면 search_keyword에서 변환
        if not data.get('search_keywords'):
            single = data.get('search_keyword', '')
            if single:
                # 단일 키워드가 있으면 그걸 첫번째로 + 기본 2개 추가
                data['search_keywords'] = [
                    single,
                    'abstract dark background',
                    'cinematic light'
                ]
                logger.info(f"  search_keywords: search_keyword에서 변환 → {data['search_keywords']}")
            else:
                # 둘 다 없으면 완전 기본값
                data['search_keywords'] = [
                    'psychology brain',
                    'abstract dark background',
                    'cinematic light'
                ]
                logger.info(f"  search_keywords: 기본값 생성")
        
        # search_keywords가 리스트가 아닌 경우 (문자열 등)
        if isinstance(data['search_keywords'], str):
            data['search_keywords'] = [data['search_keywords'], 'abstract dark background', 'cinematic light']
            logger.info(f"  search_keywords: 문자열→리스트 변환")
        
        # 최소 1개는 있어야 함
        if not data['search_keywords']:
            data['search_keywords'] = ['psychology brain', 'abstract dark background', 'cinematic light']
        
        # 하위 호환: search_keyword도 유지 (첫번째 값)
        data['search_keyword'] = data['search_keywords'][0]
        
        # ─── SNS 캡션 기본값 ───
        if not data.get('instagram_caption'):
            data['instagram_caption'] = (
                f"{data['hook']} 🧠\n\n"
                f"{data.get('description', title)}\n\n"
                f"👉 팔로우하고 매일 심리학 지식 받아가세요!"
            )
            logger.info("  인스타 캡션: 기본값 생성")
        
        if not data.get('instagram_hashtags'):
            data['instagram_hashtags'] = (
                "#심리학 #뇌과학 #자기계발 #심리해킹 #인간관계 "
                "#shorts #뇌를깨우는30초 #심리학퀴즈 #멘탈 #마인드셋"
            )
            logger.info("  인스타 해시태그: 기본값 생성")
        
        if not data.get('tiktok_caption'):
            data['tiktok_caption'] = f"{data['hook']} 😳🧠"
            logger.info("  틱톡 캡션: 기본값 생성")
        
        if not data.get('tiktok_hashtags'):
            data['tiktok_hashtags'] = (
                "#심리학 #뇌과학 #자기계발 #fyp #틱톡 "
                "#뇌를깨우는30초 #심리해킹 #shorts"
            )
            logger.info("  틱톡 해시태그: 기본값 생성")
        
        logger.info(f"검증 ✅: '{title}' ({len(data['full_script'])}자, "
                     f"{len(data['subtitle_segments'])}세그먼트, "
                     f"{len(data['search_keywords'])}키워드)")
        return True
    
    def _auto_segments(self, text):
        """자막 세그먼트 자동 생성"""
        sentences = re.split(r'(?<=[.?!。])\s*', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return [{"text": text, "duration": 5}]
        
        segments = []
        for s in sentences:
            duration = max(2, min(len(s) / 4.5, 8))
            segments.append({"text": s, "duration": round(duration, 1)})
        
        return segments
