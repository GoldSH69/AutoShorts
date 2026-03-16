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
    
    def generate(self, segments, output_path, language='ko', 
                 total_duration=30, timed_segments=None):
        """
        ASS 자막 파일 생성
        
        Args:
            segments: Gemini 원본 [{"text": "...", "duration": 3}, ...]
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

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # ── 타이밍 소스 결정 ──
        if timed_segments and len(timed_segments) > 0:
            # ✅ TTS 실측 타이밍 사용 (완벽한 싱크)
            logger.info(f"자막 타이밍: TTS 실측 기반 ({len(timed_segments)}개)")
            ass_content += self._build_events_from_timed(
                timed_segments, max_chars, language
            )
        else:
            # ⚠️ 폴백: Gemini duration 기반 (비례 스케일링)
            logger.warning("자막 타이밍: Gemini duration 기반 (폴백)")
            ass_content += self._build_events_from_gemini(
                segments, total_duration, max_chars, language
            )
        
        # 파일 저장
        with open(output_path, 'w', encoding='utf-8-sig') as f:
            f.write(ass_content)
        
        seg_count = len(timed_segments) if timed_segments else len(segments)
        logger.info(f"자막 생성 완료: {output_path} ({seg_count}개 세그먼트)")
        return output_path
    
    def _build_events_from_timed(self, timed_segments, max_chars, language):
        """TTS 실측 타이밍 기반 자막 이벤트 생성"""
        events = ""
        
        for i, seg in enumerate(timed_segments):
            text = seg.get('text', '')
            start = seg.get('start', 0)
            end = seg.get('end', start + 3)
            
            if not text:
                continue
            
            # 자막 줄바꿈
            lines = split_text_for_subtitle(text, language, max_chars)
            display_text = '\\N'.join(lines)
            
            # 첫 세그먼트는 Highlight
            style = "Highlight" if i == 0 else "Default"
            
            start_str = self._format_time(start)
            end_str = self._format_time(end)
            
            # 페이드 효과
            fade = "{\\fad(150,100)}"
            
            events += f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{fade}{display_text}\n"
        
        return events
    
    def _build_events_from_gemini(self, segments, total_duration, max_chars, language):
        """Gemini duration 기반 자막 이벤트 (폴백)"""
        events = ""
        current_time = 0.0
        total_segment_duration = sum(s.get('duration', 3) for s in segments)
        
        if total_segment_duration > 0:
            scale = total_duration / total_segment_duration
            # 스케일링 범위 제한
            scale = max(0.5, min(scale, 2.0))
        else:
            scale = 1.0
        
        for i, segment in enumerate(segments):
            text = segment.get('text', '')
            duration = segment.get('duration', 3) * scale
            
            if not text:
                continue
            
            lines = split_text_for_subtitle(text, language, max_chars)
            display_text = '\\N'.join(lines)
            
            style = "Highlight" if i == 0 else "Default"
            
            start = self._format_time(current_time)
            end = self._format_time(current_time + duration)
            
            fade = "{\\fad(200,150)}"
            
            events += f"Dialogue: 0,{start},{end},{style},,0,0,0,,{fade}{display_text}\n"
            
            current_time += duration
        
        return events
    
    def _format_time(self, seconds):
        """초를 ASS 시간 형식으로 변환 (H:MM:SS.CC)"""
        seconds = max(0, seconds)  # 음수 방지
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
