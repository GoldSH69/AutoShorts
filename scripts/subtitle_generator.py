#!/usr/bin/env python3
"""
ASS 자막 파일 생성
"""

import re
from pathlib import Path
from utils import logger, ensure_dir, split_text_for_subtitle

class SubtitleGenerator:
    """ASS 자막 생성기"""
    
    def __init__(self, config):
        self.config = config
        self.sub_config = config.get_subtitle_config()
        logger.info("SubtitleGenerator 초기화")
    
    def generate(self, segments, output_path, language='ko', total_duration=30):
        """
        ASS 자막 파일 생성
        
        Args:
            segments: [{"text": "...", "duration": 3}, ...]
            output_path: 출력 파일 경로 (.ass)
            language: 언어
            total_duration: 전체 영상 길이
        
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
        alignment = self.sub_config.get('alignment', 5)  # 5 = 중앙
        
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
        
        # 타이밍 계산
        current_time = 0.0
        total_segment_duration = sum(s.get('duration', 3) for s in segments)
        
        # 세그먼트 시간을 전체 시간에 맞게 스케일링
        if total_segment_duration > 0:
            scale = min(total_duration / total_segment_duration, 1.5)
        else:
            scale = 1.0
        
        for i, segment in enumerate(segments):
            text = segment.get('text', '')
            duration = segment.get('duration', 3) * scale
            
            if not text:
                continue
            
            # 자막 줄바꿴
            lines = split_text_for_subtitle(text, language, max_chars)
            display_text = '\\N'.join(lines)
            
            # 첫 세그먼트는 Highlight 스타일
            style = "Highlight" if i == 0 else "Default"
            
            start = self._format_time(current_time)
            end = self._format_time(current_time + duration)
            
            # 페이드 효과 (fad: fade-in, fade-out)
            fade = "{\\fad(200,150)}"
            
            ass_content += f"Dialogue: 0,{start},{end},{style},,0,0,0,,{fade}{display_text}\n"
            
            current_time += duration
        
        # 파일 저장
        with open(output_path, 'w', encoding='utf-8-sig') as f:
            f.write(ass_content)
        
        logger.info(f"자막 생성 완료: {output_path} ({len(segments)}개 세그먼트)")
        return output_path
    
    def _format_time(self, seconds):
        """초를 ASS 시간 형식으로 변환 (H:MM:SS.CC)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
