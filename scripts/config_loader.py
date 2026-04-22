#!/usr/bin/env python3
"""
설정 파일 로더
"""

import yaml
import argparse
from pathlib import Path
from utils import logger, get_project_root, get_weekday

class Config:
    """설정 관리 클래스"""
    
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = get_project_root() / "config" / "config.yml"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self._data = yaml.safe_load(f)
        
        logger.info(f"설정 로드 완료: {config_path}")
    
    def get(self, *keys, default=None):
        """중첩 키로 값 가져오기"""
        data = self._data
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return default
        return data
    
    @property
    def raw(self):
        return self._data
    
    # ─── 채널 설정 ───
    def get_channel(self, language='ko'):
        return self.get('channel', language, default={})
    
    def is_channel_enabled(self, language='ko'):
        return self.get('channel', language, 'enabled', default=False)
    
    def get_channel_name(self, language='ko'):
        return self.get('channel', language, 'name', default='')
    
    # ─── 카테고리 ───
    def get_today_category(self, weekday=None):
        if weekday is None:
            weekday = get_weekday()
        return self.get('categories', weekday, default={})
    
    def get_category_id(self, weekday=None):
        cat = self.get_today_category(weekday)
        return cat.get('id', 'quiz')
    
    def get_category_name(self, weekday=None, language='ko'):
        cat = self.get_today_category(weekday)
        key = f'name_{language}'
        return cat.get(key, cat.get('name_ko', ''))
    
    def get_category_emoji(self, weekday=None):
        cat = self.get_today_category(weekday)
        return cat.get('emoji', '🧠')
    
    def get_category_hashtags(self, weekday=None, language='ko'):
        cat = self.get_today_category(weekday)
        key = f'hashtags_{language}'
        return cat.get(key, '')
    
    def get_search_terms(self, weekday=None):
        cat = self.get_today_category(weekday)
        return cat.get('search_terms', ['abstract background'])
    
    # ─── Gemini ───
    def get_gemini_model(self):
        return self.get('gemini', 'model', default='gemini-2.5-flash')
    
    def get_gemini_fallback_models(self):
        return self.get('gemini', 'fallback_models', default=['gemini-2.0-flash'])
    
    def get_gemini_temperature(self):
        return self.get('gemini', 'temperature', default=0.9)
    
    def get_gemini_max_tokens(self):
        return self.get('gemini', 'max_output_tokens', default=2048)
    
    def get_gemini_retry_count(self):
        return self.get('gemini', 'retry_count', default=3)
    
        # ─── TTS ───
    def get_tts_config(self, language='ko'):
        base = self.get('tts', default={})
        lang_config = self.get('tts', language, default={})
        return {
            'engine': base.get('engine', 'edge-tts'),
            'speed_factor': base.get('speed_factor', 1.0),
            'max_speed': base.get('max_speed', 1.40),
            'silence_ms': base.get('silence_between_sentences_ms', 300),
            'rate': base.get('rate', '+0%'),
            'voices': base.get('voices', {}),
            'lang': lang_config.get('lang', language),
            'tld': lang_config.get('tld', 'com'),       # gTTS 폴백용 유지
            'voice': lang_config.get('voice', ''),       # 영어용
        }
    
    # ─── 영상 ───
    def get_video_config(self):
        return self.get('video', default={})
    
    # ─── BGM ───
    def get_bgm_config(self):
        return self.get('bgm', default={})
    
    # ─── 자막 ───
    def get_subtitle_config(self):
        return self.get('subtitle', default={})
    
    # ─── 업로드 ───
    def is_youtube_upload_enabled(self):
        return self.get('upload', 'youtube', 'enabled', default=False)
    
    def get_youtube_config(self):
        return self.get('upload', 'youtube', default={})
    
    def is_telegram_enabled(self):
        return self.get('upload', 'telegram', 'enabled', default=True)
    
    def get_telegram_config(self):
        return self.get('upload', 'telegram', default={})
    
    # ─── 히스토리 ───
    def get_history_config(self):
        return self.get('history', default={})
    
    def get_description_footer(self, language='ko'):
        return self.get('channel', language, 'description_footer', default='')


def parse_args():
    """커맨드라인 인자 파싱"""
    parser = argparse.ArgumentParser(description='뇌를 깨우는 30초 - YouTube Shorts 자동화')
    
    parser.add_argument('--language', '-l',
                       type=str, default='ko',
                       choices=['ko', 'en'],
                       help='생성 언어 (ko/en)')
    
    parser.add_argument('--category', '-c',
                       type=str, default='auto',
                       help='카테고리 강제 지정 (auto=요일 자동)')
    
    parser.add_argument('--config', '-f',
                       type=str, default=None,
                       help='설정 파일 경로')
    
    parser.add_argument('--weekday', '-w',
                       type=int, default=None,
                       choices=range(7),
                       help='요일 강제 지정 (0=월, 6=일)')
    
    parser.add_argument('--skip-upload',
                       action='store_true',
                       help='업로드 건너뛰기')
    
    parser.add_argument('--skip-telegram',
                       action='store_true',
                       help='텔레그램 알림 건너뛰기')
    
    parser.add_argument('--dry-run',
                       action='store_true',
                       help='테스트 모드 (영상 생성만, 업로드 안함)')
    
    parser.add_argument('--no-history',
                       action='store_true',
                       help='히스토리 저장 안함 (테스트 시 오염 방지)')
    
    parser.add_argument('--debug',
                       action='store_true',
                       help='디버그 모드')
    
    return parser.parse_args()
