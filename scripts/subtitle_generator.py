#!/usr/bin/env python3
"""
ASS 자막 파일 생성 - v2 (음성 기반 싱크)
"""

import re
from pathlib import Path
from utils import logger, ensure_dir, split_text_for_subtitle, smart_split_korean_hook

# ── U22 C-3 요약 카드 타이밍 상수 ──
SUMMARY_CARD_LEAD = 1.5      # 나레이션 종료 몇 초 전부터 카드를 띄울지
SUMMARY_CARD_GAP = 0.05      # 나레이션 자막 종료 ~ 카드 시작 사이 간격
SUMMARY_CARD_MIN_DUR = 1.2   # 카드 최소 노출 시간 (미달 시 카드 생략)
LAST_SUB_MIN_VISIBLE = 0.5   # 마지막 나레이션 자막이 보장받는 최소 노출 시간

# 하이라이트 대상 주요 심리/뇌과학/트렌드 키워드
HIGHLIGHT_KEYWORDS = [
    '전두엽', '도파민', '코르티솔', '해마', '가스라이팅', '나르시시스트',
    '브레인롯', '팝콘브레인', '회피형', '불안형', '지불의 고통', '인지부조화',
    '세로토닌', '글림프', '어장관리', '자존감', '생체시계', '서카디안',
    '마이크로습관', '2분 법칙', '5초 법칙', '손실회피', '확증편향', '소비 통증'
]


class SubtitleGenerator:
    """ASS 자막 생성기 v3 - Pretendard + 팝업 바운스 + 키워드 컬러 하이라이트"""
    
    def __init__(self, config):
        self.config = config
        self.sub_config = config.get_subtitle_config()
        logger.info("SubtitleGenerator v3 초기화 (Pretendard + 팝업 바운스 + 키워드 하이라이트)")
    
    def _highlight_keywords(self, line):
        """한 줄의 자막 텍스트 내 숫자 및 핵심 키워드를 노란색(&H0000FFFF)으로 강조"""
        if not line:
            return line

        # U18 A-9: 강조 복귀색을 font_color 설정값과 연동 (기본 흰색 폴백)
        base_color = str(self.sub_config.get('font_color', '&H00FFFFFF')).replace('&H', '')
        if not re.fullmatch(r'[0-9A-Fa-f]{8}', base_color):
            base_color = '00FFFFFF'
        close_tag = '{\\c&H' + base_color + '&}'

        count = 0
        max_highlights = 1  # 한 줄당 최대 1개 단어만 강조하여 시각적 피로도 방지

        # 1. 숫자+단위 패턴 매칭 (예: 91%, 3초, 24시간, 43만원, 10배, 1가지 등)
        def repl_num(match):
            nonlocal count
            if count >= max_highlights:
                return match.group(0)
            count += 1
            return f"{{\\c&H0000FFFF&}}{match.group(0)}{close_tag}"
        
        # 2자 이상 숫자 또는 숫자+단위 (예: 91%, 30초, 2분 등)
        highlighted = re.sub(r'(\b\d+(?:%|초|분|시간|명|원|배|단계|가지|개|\b))', repl_num, line)
        
        # 2. 핵심 키워드 매칭
        if count < max_highlights:
            for kw in HIGHLIGHT_KEYWORDS:
                if kw in highlighted and f"{{\\c&H0000FFFF&}}{kw}" not in highlighted:
                    highlighted = highlighted.replace(kw, f"{{\\c&H0000FFFF&}}{kw}{close_tag}", 1)
                    count += 1
                    break
                    
        return highlighted
    
    def generate(self, output_path, language='ko',
                 total_duration=30, timed_segments=None, thumbnail_hook=None,
                 summary_lines=None, video_duration=None):
        """
        ASS 자막 파일 생성 (TTS 실측 타이밍 기반)

        Args:
            output_path: 출력 파일 경로 (.ass)
            language: 언어
            total_duration: 나레이션 길이 (초)
            timed_segments: TTS 실측 타이밍 [{"text": "...", "start": 0.0, "end": 3.2}, ...]
            summary_lines: U22 C-3 요약 카드 3줄 [제목, CTA, 훅]. None이면 카드 생략.
            video_duration: 최종 영상 길이 (초). 요약 카드 종료 시점으로 사용.
                            None이면 total_duration을 사용한다.

        Returns:
            str: ASS 파일 경로
        """
        ensure_dir(Path(output_path).parent)
        
        font_name = self.sub_config.get('font_name', 'Pretendard')
        font_size = self.sub_config.get('font_size', 72)
        font_color = self.sub_config.get('font_color', '&H00FFFFFF')
        outline_color = self.sub_config.get('outline_color', '&H00000000')
        outline_width = self.sub_config.get('outline_width', 4)
        shadow_offset = self.sub_config.get('shadow_offset', 2)
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
Style: Hook,{font_name},{int(font_size*1.5)},&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{int(outline_width*1.5)},{int(shadow_offset*1.5)},{alignment},50,50,{margin_v},1
Style: Summary,{font_name},{int(font_size*0.65)},&H0000FFFF,&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_width},{shadow_offset},{alignment},50,50,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        if not timed_segments or len(timed_segments) == 0:
            logger.error("❌ timed_segments가 없습니다! 자막 생성 불가")
            raise Exception("TTS timed_segments가 필요합니다")

        # ── U22 C-3 요약 카드 구간 선계산 ──
        # 카드 구간을 먼저 확정한 뒤 나레이션 자막을 그 직전에서 끊는다.
        # (libass는 중앙 정렬(alignment 4~6) 이벤트에 충돌 회피를 적용하지 않아
        #  같은 시간에 두 이벤트가 있으면 화면에서 그대로 포개진다)
        card_lines = [str(ln).strip() for ln in (summary_lines or []) if str(ln).strip()][:3]
        video_end = float(video_duration) if video_duration else float(total_duration)
        # 나레이션이 영상 최대 길이를 넘는 예외 상황에서는 영상 끝을 기준으로 삼는다
        narration_end = min(float(total_duration), video_end)

        card_window = None
        if card_lines and video_end >= 8:
            card_window = self._plan_summary_card(timed_segments, narration_end, video_end)
            if card_window is None:
                logger.warning("요약 카드 생략: 나레이션 자막과 겹치지 않는 구간 확보 실패")

        narration_cutoff = (card_window[0] - SUMMARY_CARD_GAP) if card_window else None

        # ── 나레이션 자막 이벤트 ──
        logger.info(f"자막 타이밍: TTS 실측 기반 ({len(timed_segments)}개)")
        ass_content += self._build_events_from_timed(
            timed_segments, max_chars, language, thumbnail_hook,
            cutoff=narration_cutoff,
        )

        # ── 요약 카드 (저장 유도): 나레이션 종료 1.5초 전 ~ 영상 끝 ──
        if card_window:
            card_start_str = self._format_time(card_window[0])
            card_end_str = self._format_time(card_window[1])
            card_text = '\\N'.join(card_lines)
            ass_content += (
                f"Dialogue: 1,{card_start_str},{card_end_str},Summary,,0,0,0,,"
                f"{{\\fad(200,0)}}{card_text}\n"
            )
            logger.info(
                f"요약 카드 추가: {card_start_str}→{card_end_str} "
                f"({card_window[1] - card_window[0]:.1f}초, {len(card_lines)}줄)"
            )
        
        # 파일 저장
        with open(output_path, 'w', encoding='utf-8-sig') as f:
            f.write(ass_content)
        
        seg_count = len(timed_segments)
        logger.info(f"자막 생성 완료: {output_path} ({seg_count}개 세그먼트, 폰트: {font_name})")
        return output_path
    
    def _plan_summary_card(self, timed_segments, narration_duration, video_end):
        """
        요약 카드 구간 계산 → (start, end) 또는 None

        기준:
          1. 기본 시작점은 나레이션 종료 SUMMARY_CARD_LEAD초 전 (영상 끝까지 = 약 3초 노출)
          2. 마지막 나레이션 자막의 최소 노출(LAST_SUB_MIN_VISIBLE)을 침범하면 그만큼 뒤로 미룸
          3. 그래도 카드 노출이 SUMMARY_CARD_MIN_DUR 미만이면 카드 생략
        """
        try:
            last = timed_segments[-1]
            last_start = max(float(last.get('start', 0.0)), 0.3)
        except (IndexError, TypeError, ValueError):
            last_start = 0.3

        card_start = max(0.3, float(narration_duration) - SUMMARY_CARD_LEAD)

        # 마지막 나레이션 자막이 최소 노출 시간을 확보하도록 시작점 보정
        earliest = last_start + LAST_SUB_MIN_VISIBLE + SUMMARY_CARD_GAP
        if card_start < earliest:
            card_start = earliest

        if card_start > video_end - SUMMARY_CARD_MIN_DUR:
            return None

        return (card_start, float(video_end))

    def _build_events_from_timed(self, timed_segments, max_chars, language,
                                 thumbnail_hook=None, cutoff=None):
        """
        TTS 실측 타이밍 기반 자막 이벤트 생성

        cutoff: 나레이션 자막이 넘지 못하는 종료 시각(초). 요약 카드와의 겹침 방지용.
        """
        events = ""
        
        # ── 썸네일 후킹 자막 추가 (영상 맨 앞 0.0 ~ 0.3초) ──
        if thumbnail_hook:
            # 썸네일 후킹 자막: 한국어 문맥 단락 맞춤 스마트 분할 적용
            if language == 'ko':
                lines = smart_split_korean_hook(thumbnail_hook, max_line_chars=9)
            else:
                if '\n' in thumbnail_hook:
                    lines = [line.strip() for line in thumbnail_hook.split('\n') if line.strip()]
                else:
                    lines = split_text_for_subtitle(thumbnail_hook, language, 15)
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

            # 요약 카드 시작 직전에서 끊기 (중앙 정렬 이벤트 겹침 방지)
            if cutoff is not None and start < cutoff and end > cutoff:
                end = cutoff
            
            # 자막 줄바꿈
            lines = split_text_for_subtitle(text, language, max_chars)
            
            # 첫 세그먼트는 실제 후킹 문장 → Highlight 스타일 + 페이드인 + 미세 확대 + 반짝 효과
            if i == 0:
                style = "Highlight"
                hook_effect = "{\\fad(60,0)\\fscx115\\fscy115\\t(0,180,\\fscx100\\fscy100)}"
                effect = hook_effect
                display_text = '\\N'.join(lines)
            else:
                style = "Default"
                # 본문 자막: 등장 시 통통 튀는 팝업 바운스 모션 (108% -> 100%)
                bounce_effect = "{\\fad(100,80)\\fscx108\\fscy108\\t(0,120,\\fscx100\\fscy100)}"
                effect = bounce_effect
                # 핵심 키워드/숫자 컬러 하이라이트
                highlighted_lines = [self._highlight_keywords(line) for line in lines]
                display_text = '\\N'.join(highlighted_lines)
            
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

