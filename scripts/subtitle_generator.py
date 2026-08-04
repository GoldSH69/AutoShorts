#!/usr/bin/env python3
"""
ASS 자막 파일 생성 - v2 (음성 기반 싱크)
"""

import re
from pathlib import Path
from utils import logger, ensure_dir, split_text_for_subtitle

class SubtitleGenerator:
    """ASS 자막 생성기 v2 - 음성 기반 싱크"""
    
    def __init__(self, config):
        self.config = config
        self.sub_config = config.get_subtitle_config()
        logger.info("SubtitleGenerator v2 초기화 (음성 기반 싱크)")
    
    def generate(self, output_path, language='ko', 
                 total_duration=30, timed_segments=None, thumbnail_hook=None):
        """
        ASS 자막 파일 생성 (TTS 실측 타이밍 기반)
        
        Args:
            output_path: 출력 파일 경로 (.ass)
            language: 언어
            total_duration: 전체 영상 길이
            timed_segments: TTS 실측 타이밍 [{"text": "...", "start": 0.0, "end": 3.2}, ...]
        
        Returns:
            str: ASS 파일 경로
        """
        ensure_dir(Path(output_path).parent)
        
        font_name = self.sub_config.get('font_name', 'NanumGothic')
        font_size = self.sub_config.get('font_size', 52)
        font_color = self.sub_config.get('font_color', '&H00FFFFFF')
        outline_color = self.sub_config.get('outline_color', '&H00000000')
        outline_width = self.sub_config.get('outline_width', 3)
        shadow_offset = self.sub_config.get('shadow_offset', 1)
        margin_v = self.sub_config.get('margin_v', 400)
        alignment = self.sub_config.get('alignment', 5)
        
        max_chars = (self.sub_config.get('max_chars_per_line_ko', 14) 
                    if language == 'ko' 
                    else self.sub_config.get('max_chars_per_line_en', 30))
        
        # ASS 헤더
        ass_content = f"""[Script Info]
Title: Brain 30sec Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{font_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_width},{shadow_offset},{alignment},50,50,{margin_v},1
Style: Highlight,{font_name},{int(font_size*1.1)},&H0000D4FF,&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{int(outline_width+1)},{shadow_offset},{alignment},50,50,{margin_v},1
Style: Hook,{font_name},{int(font_size*1.6)},&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{int(outline_width*1.5)},{int(shadow_offset*1.5)},{alignment},50,50,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # ── 타이밍 소스 결정 ──
        if timed_segments and len(timed_segments) > 0:
            logger.info(f"자막 타이밍: TTS 실측 기반 ({len(timed_segments)}개)")
            ass_content += self._build_events_from_timed(
                timed_segments, max_chars, language, thumbnail_hook
            )
        else:
            logger.error("❌ timed_segments가 없습니다! 자막 생성 불가")
            raise Exception("TTS timed_segments가 필요합니다")
        
        # 파일 저장
        with open(output_path, 'w', encoding='utf-8-sig') as f:
            f.write(ass_content)
        
        seg_count = len(timed_segments)
        logger.info(f"자막 생성 완료: {output_path} ({seg_count}개 세그먼트)")
        return output_path
    
    def _build_events_from_timed(self, timed_segments, max_chars, language, thumbnail_hook=None):
        """TTS 실측 타이밍 기반 자막 이벤트 생성"""
        events = ""
        
        # ── 썸네일 후킹 자막 추가 (영상 맨 앞 0.0 ~ 0.3초) ──
        if thumbnail_hook:
            # 썸네일 후킹 자막은 문맥 맞게 줄바꿈(\n)이 포함된 경우 개행 유지
            if '\n' in thumbnail_hook:
                lines = [line.strip() for line in thumbnail_hook.split('\n') if line.strip()]
            else:
                hook_max_chars = 9 if language == 'ko' else 15
                lines = split_text_for_subtitle(thumbnail_hook, language, hook_max_chars)
            display_text = '\\N'.join(lines)
            start_str = self._format_time(0.0)
            end_str = self._format_time(0.3)
            # 썸네일 후킹 자막은 썸네일 문구 재표시이므로 연출(효과) 없이 평문 유지
            events += f"Dialogue: 0,{start_str},{end_str},Hook,,0,0,0,,{display_text}\n"
        
        for i, seg in enumerate(timed_segments):
            text = seg.get('text', '')
            start = seg.get('start', 0)
            end = seg.get('end', start + 3)
            
            if not text:
                continue
            
            # 첫 번째 나레이션 자막은 썸네일 후킹 자막과 겹치지 않게 최소 0.3초 이후에 나오도록 설정
            if i == 0:
                start = max(start, 0.3)
                if end <= start:
                    end = start + 2.0
            
            # 자막 줄바꿈
            lines = split_text_for_subtitle(text, language, max_chars)
            display_text = '\\N'.join(lines)
            
            # 첫 세그먼트는 실제 후킹 문장 → Highlight 스타일 + 페이드인 + 미세 확대 + 반짝 효과
            if i == 0:
                style = "Highlight"
                hook_effect = "{\\fad(60,0)\\fscx115\\fscy115\\t(0,180,\\fscx100\\fscy100)}"
                effect = hook_effect
            else:
                style = "Default"
                effect = "{\\fad(150,100)}"
            
            start_str = self._format_time(start)
            end_str = self._format_time(end)
            
            events += f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{effect}{display_text}\n"
        
        return events
    
    def _format_time(self, seconds):
        """초를 ASS 시간 형식으로 변환 (H:MM:SS.CC)"""
        seconds = max(0, seconds)  # 음수 방지
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int(round((seconds % 1) * 100))
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
