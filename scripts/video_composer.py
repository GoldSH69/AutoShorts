#!/usr/bin/env python3
"""
FFmpeg 기반 영상 합성
"""

import os
import subprocess
import json
from pathlib import Path
from pydub import AudioSegment
from utils import logger, ensure_dir

class VideoComposer:
    """FFmpeg 영상 합성기"""
    
    def __init__(self, config):
        self.config = config
        self.video_config = config.get_video_config()
        self.bgm_config = config.get_bgm_config()
        
        self.width = self.video_config.get('width', 1080)
        self.height = self.video_config.get('height', 1920)
        self.fps = self.video_config.get('fps', 30)
        self.bg_opacity = self.video_config.get('background_opacity', 0.4)
        
        logger.info("VideoComposer 초기화")
    
    def compose(self, background_path, narration_path, subtitle_path, 
                output_path, bgm_path=None, narration_duration=None):
        """
        영상 합성
        
        Args:
            background_path: 배경 영상
            narration_path: 나레이션 오디오
            subtitle_path: ASS 자막 파일
            output_path: 출력 영상
            bgm_path: BGM 파일 (옵션)
            narration_duration: 나레이션 길이 (초)
        
        Returns:
            str: 출력 파일 경로
            float: 영상 길이
        """
        ensure_dir(Path(output_path).parent)
        
        # 나레이션 길이 확인
        if narration_duration is None:
            narration_duration = self._get_duration(narration_path)
        
        # 목표 영상 길이 = 나레이션 + 여유 (최대 58초)
        max_duration = self.video_config.get('max_duration', 58)
        target_duration = min(narration_duration + 1.5, max_duration)
        
        logger.info(f"영상 합성 시작 (목표: {target_duration:.1f}초)")
        
        # 오디오 믹싱 (나레이션 + BGM)
        mixed_audio_path = str(Path(output_path).parent / "mixed_audio.mp3")
        self._mix_audio(narration_path, bgm_path, mixed_audio_path, target_duration)
        
        # FFmpeg 명령 구성
        cmd = self._build_ffmpeg_command(
            background_path=background_path,
            audio_path=mixed_audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            target_duration=target_duration,
        )
        
        logger.info(f"FFmpeg 실행...")
        logger.debug(f"명령: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg 오류:\n{result.stderr[-1000:]}")
                raise Exception(f"FFmpeg 실패: {result.returncode}")
            
            # 결과 확인
            if not Path(output_path).exists():
                raise Exception("출력 파일이 생성되지 않았습니다")
            
            output_size = Path(output_path).stat().st_size / (1024 * 1024)
            output_duration = self._get_duration(output_path)
            
            logger.info(f"영상 합성 완료: {output_size:.1f}MB, {output_duration:.1f}초")
            
            # 임시 파일 정리
            self._cleanup([mixed_audio_path])
            
            return output_path, output_duration
            
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg 타임아웃 (300초)")
            raise
    
    def _mix_audio(self, narration_path, bgm_path, output_path, target_duration):
        """오디오 믹싱 (나레이션 + BGM)"""
        
        narration = AudioSegment.from_file(narration_path)
        
        if bgm_path and Path(bgm_path).exists() and self.bgm_config.get('enabled', True):
            try:
                bgm = AudioSegment.from_file(bgm_path)
                
                # BGM 볼륨 조절
                bgm_volume = self.bgm_config.get('volume', 0.08)
                # dB로 변환 (0.08 ≈ -22dB)
                import math
                if bgm_volume > 0:
                    volume_db = 20 * math.log10(bgm_volume)
                else:
                    volume_db = -40
                bgm = bgm + volume_db
                
                # BGM 길이 맞추기 (루프 또는 자르기)
                target_ms = int(target_duration * 1000)
                
                if len(bgm) < target_ms:
                    # 루프
                    loops = (target_ms // len(bgm)) + 1
                    bgm = bgm * loops
                
                bgm = bgm[:target_ms]
                
                # 페이드 인/아웃
                fade_in = self.bgm_config.get('fade_in_ms', 1000)
                fade_out = self.bgm_config.get('fade_out_ms', 2000)
                bgm = bgm.fade_in(fade_in).fade_out(fade_out)
                
                # BGM 길이에 맞게 나레이션 오버레이
                if len(bgm) > len(narration):
                    # 나레이션을 BGM 위에 오버레이
                    mixed = bgm.overlay(narration)
                else:
                    # 나레이션이 더 긴 경우
                    mixed = narration.overlay(bgm)
                
                mixed.export(output_path, format='mp3', bitrate='192k')
                logger.info(f"오디오 믹싱 완료 (BGM 포함, {len(mixed)/1000:.1
