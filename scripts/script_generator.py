#!/usr/bin/env python3
"""
Gemini API 스크립트 생성 - v6.3 (SNS 캡션 해시태그 완전 제거 강화)
변경: 캡션 본문 내 모든 #해시태그 패턴 제거 (줄 끝/본문 중간 모두 대응)
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


# ─── 상수 ───
# ─── 카테고리별 소재 목록 (프롬프트 소재와 동일) ───
CATEGORY_TOPICS = {
    'money': [
        '심적 회계(Mental Accounting)',
        '매몰비용 오류',
        '앵커링 효과와 세일 가격',
        '라떼 팩터와 복리',
        '카드 vs 현금 결제 심리',
        '손실회피 (카너먼-트버스키)',
        '파킨슨의 법칙 수입편',
        '현재편향과 저축',
        '사회적 비교와 소비',
        '무료의 심리학 (댄 애리얼리)',
        '선택 과부하와 투자',
        '72의 법칙',
    ],
    'success': [
        '의도적 연습(Deliberate Practice)',
        '성장 마인드셋 (캐롤 드웩)',
        '시각화의 뇌과학',
        '5초 법칙 (멜 로빈스)',
        '습관 루프 (찰스 두히그)',
        '파킨슨의 법칙',
        '지연된 보상 (마시멜로 실험)',
        '아침 루틴의 뇌과학',
        '실패 편향',
        '목표 설정 SMART vs 구현 의도',
        '환경 설계와 습관',
    ],
    'brain': [
        '도파민 디톡스',
        '포모도로 25분 전두엽',
        '아침 햇빛 세로토닌',
        '운동 20분 BDNF',
        '멀티태스킹 인지 비용',
        '90분 울트라디안 리듬',
        '낮잠 20분 NASA 연구',
        '냉수 샤워 노르에피네프린',
        '명상 8주 편도체 (하버드)',
        '씹는 행위 코르티솔',
        '2분 규칙 전두엽',
        '수면 글림프 시스템',
    ],
    'dark': [
        '상호성 원리 (치알디니)',
        '문간에 발 들이기(Foot-in-the-door)',
        '사회적 증거',
        '희소성 원리',
        '권위 편향 (밀그램)',
        '가스라이팅 3단계',
        '미러링 기법',
        '프레이밍 효과',
        '닻내리기(Anchoring)',
        '칵테일 파티 효과',
        '벤자민 프랭클린 효과',
    ],
    'hack': [
        '구현 의도(Implementation Intention)',
        '2분 규칙',
        '습관 스태킹 (제임스 클리어)',
        '자아 고갈(Ego Depletion)',
        '환경 설계 선택 설계',
        '작은 승리(Small Wins) 도파민',
        '자기 효능감 (반두라)',
        '세이렌 서버(Ulysses Contract)',
        '파킨슨의 법칙 데드라인',
        '시각화의 함정',
        '자기 자비(Self-Compassion)',
    ],
    'love': [
        '호감 무의식 신호 (미러링)',
        '밀당 희소성 원리 간헐적 강화',
        '첫인상 7초 후광효과',
        '연락 불확실성 집착 심리',
        '이별 후 손실회피 심리',
        '썸에서 관계로 결정적 행동',
        '질투 편도체 활성화',
        '커플 5:1 비율 (가트만)',
        '익숙함과 설렘의 심리학',
        '고백 타이밍 피크엔드 법칙',
        '눈 맞춤 3초 법칙',
        '공포 영화 데이트 오귀인 이론',
        '로미오와 줄리엣 효과',
    ],
    'relationship': [
        '가트만 4기수',
        '5:1 긍정적 상호작용 비율',
        '비폭력 대화(NVC)',
        '애착 이론 불안형 회피형',
        '경청 옥시토신',
        '초두효과 대화 3분',
        '자기 노출 법칙 47%',
        '감정 코칭 갈등 65% 감소',
        '심리적 안전감 (구글)',
        '투사(Projection)',
        '역설적 변화 이론',
        '메타 대화',
    ],
}

# thinking 모델 판별
THINKING_MODELS = {
    'gemini-2.5-flash',
    'gemini-2.5-pro',
}

# 인스타/틱톡에서 제거할 플랫폼/채널 전용 태그 (소문자 비교)
PLATFORM_TAGS_TO_REMOVE = {
    "#shorts", "#short", "#youtubeshorts", "#youtube",
    "#reels", "#reel", "#instagramreels",
    "#tiktok", "#fyp", "#foryou", "#foryoupage",
    "#쇼츠", "#유튜브쇼츠", "#유튜브", "#릴스", "#틱톡",
    "#뇌를깨우는30초",
}

# 틱톡에서는 허용할 태그
TIKTOK_ALLOWED_TAGS = {"#fyp", "#foryou", "#foryoupage"}

INSTAGRAM_HASHTAG_LIMIT = 5
TIKTOK_HASHTAG_LIMIT = 7

# 해시태그 최소 보장용 기본 풀
DEFAULT_HASHTAGS_KO = [
    "#심리학", "#자기계발", "#뇌과학", "#마인드셋", "#멘탈",
    "#psychology", "#mindset", "#selfimprovement",
]

TIKTOK_DEFAULT_HASHTAGS = [
    "#심리학", "#자기계발", "#뇌과학", "#fyp", "#psychology", "#mindset",
]


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
    """Gemini 스크립트 생성기 v6.3 - SNS 캡션 해시태그 완전 제거"""
    
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
        
        logger.info(f"ScriptGenerator v6.3 초기화 (캡션 해시태그 완전 제거)")
        logger.info(f"  주력 모델: {self.model_name} (thinking: {is_thinking_model(self.model_name)})")
        logger.info(f"  백업 모델: {self.fallback_models}")
        logger.info(f"  max_output_tokens: {self.max_tokens}")
        logger.info(f"  인스타 해시태그 제한: {INSTAGRAM_HASHTAG_LIMIT}개")
        logger.info(f"  틱톡 해시태그 제한: {TIKTOK_HASHTAG_LIMIT}개")
    
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
        """기본 프롬프트 (v6.3 - 캡션 본문 해시태그 금지 강화)"""
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

SNS 캡션 규칙:

⚠️ 중요: instagram_caption과 tiktok_caption 본문에는 #해시태그를 절대 넣지 마세요!
해시태그는 반드시 instagram_hashtags, tiktok_hashtags 필드에만 넣으세요.

인스타그램:
- instagram_caption: 3~5줄 본문 (이모지 포함, 마지막에 팔로우 유도 CTA)
  ⚠️ 본문에 #해시태그 넣지 말 것!
- instagram_hashtags: 콘텐츠 핵심 해시태그 정확히 5개만 배열로 생성
  - 콘텐츠 주제와 직접 관련된 구체적 키워드만 사용
  - 한국어+영어 혼합 가능 (예: "#심리학", "#뇌과학", "#psychology")
  - 아래 태그는 절대 넣지 말 것:
    → #shorts #reels #유튜브 #쇼츠 #릴스 #뇌를깨우는30초 (플랫폼/채널명 태그)
  - 너무 포괄적인 태그 금지 (예: #일상 #공부 #정보)

틱톡:
- tiktok_caption: 1~2줄 짧은 후킹 (이모지 포함)
  ⚠️ 본문에 #해시태그 넣지 말 것!
- tiktok_hashtags: 해시태그 5~7개 배열로 생성
  - #fyp는 틱톡 전용이므로 포함 가능
  - 아래 태그는 절대 넣지 말 것:
    → #shorts #유튜브 #쇼츠 #뇌를깨우는30초 (타 플랫폼/채널명 태그)

반드시 아래 JSON 형식으로만 출력하세요. 해시태그는 반드시 배열(리스트)로 출력하세요.

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
  "instagram_caption": "인스타그램 본문 3~5줄 (해시태그 넣지 말 것)",
  "instagram_hashtags": ["#주제태그1", "#주제태그2", "#주제태그3", "#영어태그1", "#영어태그2"],
  "tiktok_caption": "틱톡 후킹 1~2줄 (해시태그 넣지 말 것)",
  "tiktok_hashtags": ["#주제태그1", "#주제태그2", "#주제태그3", "#fyp", "#영어태그1"]
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

    def _select_forced_topic(self, category_id):
        """
        🆕 v6.5 소재 강제 선택
        - 이전에 다룬 주제와 겹치지 않는 소재를 랜덤 선택
        - 모든 소재를 다 사용했으면 가장 오래된 것부터 재사용
        """
        import random
        
        topics_pool = CATEGORY_TOPICS.get(category_id, [])
        if not topics_pool:
            logger.warning(f"  카테고리 '{category_id}'의 소재 목록 없음")
            return "자유 주제 선택"
        
        # 이전 주제 키워드 추출
        history = self._load_history()
        previous = history.get('topics', [])
        same_cat = [t for t in previous if t.get('category') == category_id]
        recent_titles = [t.get('title', '').lower() for t in same_cat[-30:]]
        
        # 사용 안 한 소재 필터링
        unused = []
        for topic in topics_pool:
            topic_keywords = topic.lower().split()
            # 이전 제목에 핵심 키워드가 포함되어 있는지 체크
            used = False
            for title in recent_titles:
                match_count = sum(1 for kw in topic_keywords if kw in title)
                if match_count >= 2:  # 키워드 2개 이상 겹치면 사용된 것으로 판단
                    used = True
                    break
            if not used:
                unused.append(topic)
        
        if unused:
            selected = random.choice(unused)
            logger.info(f"  🎯 소재 선택: '{selected}' (미사용 {len(unused)}개 중)")
        else:
            # 모든 소재 사용됨 → 가장 오래된 것부터 재사용
            selected = random.choice(topics_pool)
            logger.info(f"  🔄 소재 재사용: '{selected}' (모든 소재 사용됨, 랜덤 선택)")
        
        return selected
        
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
    
    # ─── 해시태그 정제 ───
    
    def _parse_hashtags_to_list(self, raw):
        """해시태그를 어떤 형태든 리스트로 변환"""
        if isinstance(raw, list):
            result = []
            for item in raw:
                if isinstance(item, str):
                    for tag in item.split():
                        tag = tag.strip().strip(',')
                        if tag:
                            result.append(tag)
            return result
        
        if isinstance(raw, str):
            tags = re.split(r'[\s,]+', raw)
            return [t.strip() for t in tags if t.strip()]
        
        return []
    
    def _sanitize_hashtags(self, raw, limit, platform='instagram'):
        """
        해시태그 정제
        - 어떤 형태든 리스트로 변환
        - # 접두사 보장
        - 플랫폼/채널 전용 태그 제거
        - 틱톡에서는 #fyp 허용
        - 개수 제한 + 중복 제거
        """
        tags = self._parse_hashtags_to_list(raw)
        
        cleaned = []
        seen_lower = set()
        
        for tag in tags:
            if not tag.startswith("#"):
                tag = f"#{tag}"
            
            if len(tag) <= 1:
                continue
            
            tag_lower = tag.lower()
            
            if tag_lower in seen_lower:
                continue
            
            if platform == 'instagram':
                if tag_lower in PLATFORM_TAGS_TO_REMOVE:
                    logger.debug(f"  인스타 태그 제거: {tag}")
                    continue
            elif platform == 'tiktok':
                if tag_lower in PLATFORM_TAGS_TO_REMOVE and tag_lower not in TIKTOK_ALLOWED_TAGS:
                    logger.debug(f"  틱톡 태그 제거: {tag}")
                    continue
            
            seen_lower.add(tag_lower)
            cleaned.append(tag)
        
        return cleaned[:limit]
    
    def _deduplicate_cross_platform(self, ig_tags: list, tt_tags: list, max_overlap: int = 2) -> tuple:
        """
        인스타/틱톡 간 교차 중복 최소화
        - 인스타 태그는 그대로 유지
        - 틱톡에서 인스타와 겹치는 태그를 max_overlap개까지만 허용
        """
        ig_lower_set = set(tag.lower() for tag in ig_tags)
        
        overlap_count = 0
        filtered_tt = []
        removed = []
        
        for tag in tt_tags:
            if tag.lower() in ig_lower_set:
                overlap_count += 1
                if overlap_count <= max_overlap:
                    filtered_tt.append(tag)
                else:
                    removed.append(tag)
            else:
                filtered_tt.append(tag)
        
        if removed:
            logger.info(f"  교차 중복 제거 (틱톡에서): {removed}")
        
        return ig_tags, filtered_tt
    
    def _strip_hashtags_from_caption(self, caption, platform_name):
        """
        🆕 v6.3 캡션 본문에서 모든 #해시태그 완전 제거
        - 줄 전체가 해시태그 → 줄 삭제
        - 줄 끝에 해시태그 → 해시태그만 제거
        - 본문 중간 해시태그 → 해시태그만 제거
        모든 패턴 대응!
        """
        if not caption:
            return caption
        
        original = caption
        
        # 모든 #해시태그 단어 제거 (유니코드 대응: 한글/영문/숫자/언더스코어)
        caption = re.sub(r'#[^\s#]+', '', caption)
        
        # 연속 공백 정리
        caption = re.sub(r'[ \t]{2,}', ' ', caption)
        
        # 각 줄 앞뒤 공백 정리 + 빈줄 제거
        lines = [line.strip() for line in caption.split('\n')]
        lines = [line for line in lines if line]
        
        caption = '\n'.join(lines)
        
        if caption != original:
            logger.info(f"  ✂️ {platform_name} 캡션에서 해시태그 제거 완료")
        
        return caption
    
    def _normalize_sns_captions(self, data):
        """
        SNS 캡션 + 해시태그 최종 정규화 (v6.3)
        - ★ 캡션 본문에서 모든 해시태그 완전 제거 (줄끝/중간/전체줄 모두)
        - 인스타 해시태그: 정확히 5개 (플랫폼/채널 태그 제거)
        - 틱톡 해시태그: 5~7개 (#fyp 허용)
        - 인스타/틱톡 교차 중복 최소화 (최대 2개 겹침)
        - 캡션 기본값 보장
        - 최종 출력: 문자열 (' '.join)
        """
        
        # ★ [1단계] 캡션 본문에서 해시태그 완전 제거 (v6.3 핵심 변경)
        data['instagram_caption'] = self._strip_hashtags_from_caption(
            data.get('instagram_caption', ''), 'instagram'
        )
        data['tiktok_caption'] = self._strip_hashtags_from_caption(
            data.get('tiktok_caption', ''), 'tiktok'
        )
        
        # === [2단계] 인스타그램 해시태그 ===
        ig_raw = data.get('instagram_hashtags', [])
        ig_tags = self._sanitize_hashtags(ig_raw, INSTAGRAM_HASHTAG_LIMIT, platform='instagram')
        
        if len(ig_tags) < INSTAGRAM_HASHTAG_LIMIT:
            for default_tag in DEFAULT_HASHTAGS_KO:
                if default_tag.lower() not in {t.lower() for t in ig_tags}:
                    ig_tags.append(default_tag)
                if len(ig_tags) >= INSTAGRAM_HASHTAG_LIMIT:
                    break
        ig_tags = ig_tags[:INSTAGRAM_HASHTAG_LIMIT]
        
        # === [3단계] 틱톡 해시태그 ===
        tt_raw = data.get('tiktok_hashtags', [])
        tt_tags = self._sanitize_hashtags(tt_raw, TIKTOK_HASHTAG_LIMIT, platform='tiktok')
        
        # ★ 교차 중복 제거
        ig_tags, tt_tags = self._deduplicate_cross_platform(ig_tags, tt_tags, max_overlap=2)
        
        # 틱톡 부족하면 기본값에서 채움
        if len(tt_tags) < 5:
            ig_lower_set = set(t.lower() for t in ig_tags)
            tt_lower_set = set(t.lower() for t in tt_tags)
            for default_tag in TIKTOK_DEFAULT_HASHTAGS:
                if default_tag.lower() not in tt_lower_set:
                    if default_tag.lower() not in ig_lower_set or len(tt_tags) < 3:
                        tt_tags.append(default_tag)
                        tt_lower_set.add(default_tag.lower())
                if len(tt_tags) >= TIKTOK_HASHTAG_LIMIT:
                    break
        tt_tags = tt_tags[:TIKTOK_HASHTAG_LIMIT]
        
        # 로그
        data['instagram_hashtags'] = ig_tags
        data['tiktok_hashtags'] = tt_tags
        logger.info(f"  인스타 해시태그 ({len(ig_tags)}개): {ig_tags}")
        logger.info(f"  틱톡 해시태그 ({len(tt_tags)}개): {tt_tags}")
        
        overlap = set(t.lower() for t in ig_tags) & set(t.lower() for t in tt_tags)
        if overlap:
            logger.info(f"  인스타/틱톡 겹침: {len(overlap)}개 {overlap}")
        
        # === [4단계] 캡션 기본값 ===
        if not data.get('instagram_caption'):
            data['instagram_caption'] = (
                f"{data.get('hook', '🧠 당신의 뇌를 깨워보세요')}\n\n"
                f"{data.get('description', data.get('title', ''))}\n\n"
                f"👉 팔로우하고 매일 심리학 지식 받아가세요!"
            )
            logger.info("  인스타 캡션: 기본값 생성")
        
        if not data.get('tiktok_caption'):
            data['tiktok_caption'] = f"{data.get('hook', '🧠 뇌를 깨우는 30초')} 😳🧠"
            logger.info("  틱톡 캡션: 기본값 생성")
        
        # ★ 최종: 리스트 → 문자열 변환
        data['instagram_hashtags'] = ' '.join(ig_tags)
        data['tiktok_hashtags'] = ' '.join(tt_tags)
        
        return data
    
    # ─── 메인 생성 ───
    
    def generate(self, category_id=None, weekday=None, language='ko', save_history=True):
        """스크립트 생성 (v6.5 - 소재 강제 지정 + 중복 체크)"""
        
        if category_id is None:
            category_id = self.config.get_category_id(weekday)
        
        logger.info(f"스크립트 생성 시작: 카테고리={category_id}, 언어={language}")
        
        template = self._load_prompt_template(category_id, language)
        previous_topics = self._get_previous_topics(category_id)
        
        # 🆕 v6.5: 소재 강제 선택
        forced_topic = self._select_forced_topic(category_id)
        
        # 프롬프트 변수 치환
        prompt = template.replace('{previous_topics}', previous_topics)
        prompt = prompt.replace('{forced_topic}', forced_topic)
        
        models = []
        seen = set()
        for m in [self.model_name] + self.fallback_models:
            if m not in seen:
                seen.add(m)
                models.append(m)
        
        logger.info(f"시도할 모델: {models}")
        
        result = None
        max_dedup_attempts = 3  # 🆕 중복 시 최대 재시도
        
        for dedup_attempt in range(max_dedup_attempts):
            if dedup_attempt > 0:
                # 재시도 시 다른 소재 선택
                forced_topic = self._select_forced_topic(category_id)
                prompt = template.replace('{previous_topics}', previous_topics)
                prompt = prompt.replace('{forced_topic}', forced_topic)
                logger.info(f"  🔄 중복 감지, 소재 변경: '{forced_topic}' (시도 {dedup_attempt+1})")
            
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
            
            if result:
                # 🆕 v6.5: 제목 중복 체크
                if self._is_duplicate_title(result, category_id):
                    logger.warning(f"  ⚠️ 제목 중복 감지: '{result.get('title', '')}'")
                    result = None  # 재생성
                    continue
                break  # 중복 아니면 완료
        
        if not result:
            logger.error("❌ 모든 모델에서 실패!")
            raise Exception("스크립트 생성 실패: 사용 가능한 모델 없음")
        
        logger.info(f"\n✅ 스크립트 생성 성공!")
        logger.info(f"  제목: {result.get('title', '')}")
        logger.info(f"  지정 소재: {forced_topic}")
        logger.info(f"  스크립트: {result.get('full_script', '')[:80]}...")
        logger.info(f"  검색 키워드: {result.get('search_keywords', [])}")
        logger.info(f"  인스타 캡션: {'있음' if result.get('instagram_caption') else '기본값'}")
        logger.info(f"  인스타 해시태그: {result.get('instagram_hashtags', '')} ")
        logger.info(f"  틱톡 캡션: {'있음' if result.get('tiktok_caption') else '기본값'}")
        logger.info(f"  틱톡 해시태그: {result.get('tiktok_hashtags', '')}")
        
        if save_history:
            self._save_history(category_id, result)
        else:
            logger.info("🚫 히스토리 저장 건너뜀 (--no-history)")
        return result
    
    # ─── 검증 ───
    
    def _validate_script(self, data):
        """스크립트 검증 (v6.3 - 캡션 해시태그 완전 제거)"""
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
        
        # 기본값 채우기
        if not data.get('hook'):
            data['hook'] = script[:50]
        if not data.get('body'):
            data['body'] = script
        if not data.get('cta'):
            data['cta'] = '구독과 좋아요 부탁드려요!'
        if not data.get('description'):
            data['description'] = title
        
        # ─── 검색 키워드 (다중) ───
        if not data.get('search_keywords'):
            single = data.get('search_keyword', '')
            if single:
                data['search_keywords'] = [
                    single,
                    'abstract dark background',
                    'cinematic light'
                ]
                logger.info(f"  search_keywords: search_keyword에서 변환 → {data['search_keywords']}")
            else:
                data['search_keywords'] = [
                    'psychology brain',
                    'abstract dark background',
                    'cinematic light'
                ]
                logger.info(f"  search_keywords: 기본값 생성")
        
        if isinstance(data['search_keywords'], str):
            data['search_keywords'] = [data['search_keywords'], 'abstract dark background', 'cinematic light']
            logger.info(f"  search_keywords: 문자열→리스트 변환")
        
        if not data['search_keywords']:
            data['search_keywords'] = ['psychology brain', 'abstract dark background', 'cinematic light']
        
        data['search_keyword'] = data['search_keywords'][0]
        
        # ─── ★ SNS 캡션 + 해시태그 정규화 (v6.3) ───
        data = self._normalize_sns_captions(data)
        
        ig_count = len(data['instagram_hashtags'].split()) if isinstance(data['instagram_hashtags'], str) else len(data['instagram_hashtags'])
        tt_count = len(data['tiktok_hashtags'].split()) if isinstance(data['tiktok_hashtags'], str) else len(data['tiktok_hashtags'])
        logger.info(f"검증 ✅: '{title}' ({len(data['full_script'])}자, "
                     f"{len(data['subtitle_segments'])}세그먼트, "
                     f"{len(data['search_keywords'])}키워드, "
                     f"IG#{ig_count} TT#{tt_count})")
        return True

    def _is_duplicate_title(self, result, category_id):
        """
        🆕 v6.5 제목 중복 체크
        - 최근 30개 제목과 핵심 키워드 비교
        - 3개 이상 겹치면 중복으로 판단
        """
        new_title = result.get('title', '').lower()
        new_script = result.get('full_script', '').lower()
        
        history = self._load_history()
        previous = history.get('topics', [])
        same_cat = [t for t in previous if t.get('category') == category_id]
        recent_titles = [t.get('title', '').lower() for t in same_cat[-30:]]
        
        # 새 제목의 핵심 단어 추출 (2글자 이상)
        import re
        new_words = set(w for w in re.findall(r'[가-힣a-z]{2,}', new_title))
        
        for old_title in recent_titles:
            old_words = set(w for w in re.findall(r'[가-힣a-z]{2,}', old_title))
            overlap = new_words & old_words
            if len(overlap) >= 3:
                logger.warning(f"  제목 겹침: {overlap} (기존: '{old_title}')")
                return True
        
        return False
        
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
