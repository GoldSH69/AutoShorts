#!/usr/bin/env python3
"""
FFmpeg 기반 영상 합성 - v3.2 (fps 통일 + 다중 배경 전환)

v3.1 대비 변경:
- 다중 배경 합성 전 normalize_video()로 fps/해상도/포맷 통일
- xfade timebase 불일치 문제 완전 해결
- offset 계산 로직 개선
"""

import os
import math
import subprocess
import json
import shutil
import tempfile
from pathlib import Path
from pydub import AudioSegment
from utils import logger, ensure_dir

class VideoComposer:
    """FFmpeg 영상 합성기 v3.2 - fps 통일 + 다중 배경 전환"""
    
    def __init__(self, config):
        self.config = config
        self.video_config = config.get_video_config()
        self.bgm_config = config.get_bgm_config()
        
        self.width = self.video_config.get('width', 1080)
        self.height = self.video_config.get('height', 1920)
        self.fps = self.video_config.get('fps', 30)
        self.bg_opacity = self.video_config.get('background_opacity', 0.4)
        self.fade_duration = self.video_config.get('fade_duration', 0.5)
        
        self.ffmpeg_path = shutil.which('ffmpeg') or 'ffmpeg'
        self.ffprobe_path = shutil.which('ffprobe') or 'ffprobe'
        
        logger.info(f"VideoComposer v3.2 초기화 (fps통일 + 다중배경)")
        logger.info(f"  해상도: {self.width}x{self.height}, fps: {self.fps}")
    
    # ─── 영상 정규화 (핵심!) ───
    
    def _normalize_video(self, input_path, output_path):
        """
        배경 영상을 동일 fps/해상도/포맷으로 정규화
        
        xfade timebase 불일치 문제의 근본 해결:
        - 모든 영상을 동일한 fps로 변환
        - 동일한 해상도 + 크롭
        - 동일한 픽셀 포맷 (yuv420p)
        - video_track_timescale 고정
        """
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', str(input_path),
            '-vf', (
                f'scale={self.width}:{self.height}:'
                f'force_original_aspect_ratio=increase,'
                f'crop={self.width}:{self.height},'
                f'fps={self.fps},'
                f'format=yuv420p,'
                f'drawbox=0:0:{self.width}:{self.height}:'
                f'color=black@{self.bg_opacity}:t=fill'
            ),
            '-an',  # 배경 영상 오디오 제거
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-r', str(self.fps),
            '-video_track_timescale', str(self.fps * 1000),
            str(output_path),
        ]
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            
            if result.returncode == 0 and Path(output_path).exists():
                size_mb = Path(output_path).stat().st_size / (1024 * 1024)
                logger.info(f"  ✅ 정규화: {Path(input_path).name} → {self.fps}fps ({size_mb:.1f}MB)")
                return True
            else:
                logger.warning(f"  ❌ 정규화 실패: {result.stderr[-300:]}")
                return False
                
        except Exception as e:
            logger.warning(f"  ❌ 정규화 예외: {e}")
            return False
    
    def _normalize_all(self, background_paths, tmp_dir, target_duration):
        """
        모든 배경 영상을 정규화 + 필요한 길이로 트림
        
        Returns:
            list: 정규화된 영상 경로 리스트
        """
        n = len(background_paths)
        segment_duration = target_duration / n + self.fade_duration  # 페이드 오버랩 여유
        
        normalized = []
        
        for i, bg_path in enumerate(background_paths):
            norm_path = os.path.join(tmp_dir, f"norm_{i:02d}.mp4")
            
            # 원본 영상 길이 확인
            bg_duration = self._get_duration(bg_path)
            
            # 원본이 짧으면 루프 입력
            input_args = []
            if bg_duration > 0 and bg_duration < segment_duration:
                loop_count = int(segment_duration / bg_duration) + 1
                input_args = ['-stream_loop', str(loop_count)]
            
            # 정규화 + 트림
            cmd = [
                self.ffmpeg_path, '-y',
            ] + input_args + [
                '-i', str(bg_path),
                '-vf', (
                    f'scale={self.width}:{self.height}:'
                    f'force_original_aspect_ratio=increase,'
                    f'crop={self.width}:{self.height},'
                    f'fps={self.fps},'
                    f'format=yuv420p,'
                    f'drawbox=0:0:{self.width}:{self.height}:'
                    f'color=black@{self.bg_opacity}:t=fill'
                ),
                '-t', str(segment_duration),
                '-an',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-r', str(self.fps),
                '-video_track_timescale', str(self.fps * 1000),
                norm_path,
            ]
            
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120
                )
                
                if result.returncode == 0 and Path(norm_path).exists():
                    norm_dur = self._get_duration(norm_path)
                    logger.info(f"  ✅ [{i+1}/{n}] 정규화: {Path(bg_path).name} → {norm_dur:.1f}초, {self.fps}fps")
                    normalized.append(norm_path)
                else:
                    logger.warning(f"  ❌ [{i+1}/{n}] 정규화 실패, 건너뜀")
                    logger.warning(f"     {result.stderr[-200:]}")
                    
            except Exception as e:
                logger.warning(f"  ❌ [{i+1}/{n}] 정규화 예외: {e}")
        
        return normalized
    
    # ─── 메인 합성 ───
    
    def compose(self, background_paths, narration_path, subtitle_path, 
                output_path, bgm_path=None, narration_duration=None):
        """
        영상 합성 (다중 배경 지원)
        
        Args:
            background_paths: 배경 영상 경로 (str 1개 또는 list 여러개)
            narration_path: 나레이션 오디오
            subtitle_path: ASS 자막 파일
            output_path: 출력 영상
            bgm_path: BGM 파일 (옵션)
            narration_duration: 나레이션 길이 (초)
        
        Returns:
            tuple: (output_path, video_duration)
        """
        ensure_dir(Path(output_path).parent)
        
        # 배경 경로 리스트로 통일
        if isinstance(background_paths, str):
            background_paths = [background_paths]
        
        # 존재하는 파일만 필터
        valid_paths = [p for p in background_paths if Path(p).exists()]
        if not valid_paths:
            raise Exception("유효한 배경 영상이 없습니다")
        
        logger.info(f"배경 영상: {len(valid_paths)}개")
        
        # 나레이션 길이 확인
        if narration_duration is None:
            narration_duration = self._get_duration(narration_path)
        
        max_duration = self.video_config.get('max_duration', 55)
        target_duration = min(narration_duration + 1.5, max_duration)
        
        if narration_duration > max_duration:
            logger.warning(f"⚠️ 나레이션({narration_duration:.1f}초) > max({max_duration}초)")
            target_duration = max_duration
        
        logger.info(f"영상 합성 시작")
        logger.info(f"  나레이션: {narration_duration:.1f}초")
        logger.info(f"  목표 영상: {target_duration:.1f}초")
        
        # 오디오 믹싱
        mixed_audio_path = str(Path(output_path).parent / "mixed_audio.mp3")
        self._mix_audio(narration_path, bgm_path, mixed_audio_path, target_duration)
        
        # 다중 배경 합성
        if len(valid_paths) >= 2:
            try:
                result = self._compose_multi(
                    valid_paths, mixed_audio_path, subtitle_path,
                    output_path, target_duration
                )
                if result:
                    self._cleanup([mixed_audio_path])
                    return result
            except Exception as e:
                logger.warning(f"다중 배경 실패: {e}")
            
            logger.warning("단일 배경으로 폴백...")
        
        # 단일 배경 (폴백 또는 영상 1개)
        result = self._compose_single(
            valid_paths[0], mixed_audio_path, subtitle_path,
            output_path, target_duration
        )
        
        self._cleanup([mixed_audio_path])
        return result
    
    def _compose_multi(self, background_paths, audio_path, subtitle_path,
                        output_path, target_duration):
        """
        다중 배경 합성 (fps 정규화 후 xfade)
        
        Returns:
            tuple: (output_path, duration) or None
        """
        n = len(background_paths)
        fade = self.fade_duration
        segment_duration = target_duration / n
        
        logger.info(f"  구간 분할: {n}개 × {segment_duration:.1f}초 (페이드: {fade}초)")
        
        # ★ 핵심: 임시 디렉토리에서 모든 영상을 정규화
        with tempfile.TemporaryDirectory() as tmp_dir:
            logger.info(f"  배경 영상 정규화 시작 (fps={self.fps})...")
            normalized = self._normalize_all(background_paths, tmp_dir, target_duration)
            
            if len(normalized) < 2:
                logger.warning(f"  정규화된 영상 {len(normalized)}개 < 2, 다중 합성 불가")
                return None
            
            n = len(normalized)
            segment_duration = target_duration / n
            
            # 자막 경로 이스케이프
            sub_path_escaped = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
            
            # ── FFmpeg 명령 구성 ──
            cmd = [self.ffmpeg_path, '-y']
            
            # 정규화된 영상 입력
            for norm_path in normalized:
                cmd.extend(['-i', norm_path])
            
            # 오디오 입력
            cmd.extend(['-i', str(audio_path)])
            audio_index = n
            
            # ── 필터 체인 ──
            filter_parts = []
            
            # 각 영상 트림 (정확한 세그먼트 길이)
            for i in range(n):
                trim_duration = segment_duration + fade  # 오버랩 여유
                filter_parts.append(
                    f"[{i}:v]trim=0:{trim_duration:.2f},setpts=PTS-STARTPTS[v{i}]"
                )
            
            # xfade 연결
            if n == 2:
                offset = max(0.1, segment_duration - fade)
                filter_parts.append(
                    f"[v0][v1]xfade=transition=fade:duration={fade}:offset={offset:.2f}[merged]"
                )
                last_label = "merged"
                
            elif n == 3:
                # 첫 두 개 합치기
                offset1 = max(0.1, segment_duration - fade)
                filter_parts.append(
                    f"[v0][v1]xfade=transition=fade:duration={fade}:offset={offset1:.2f}[xf01]"
                )
                # 세 번째 합치기
                offset2 = max(offset1 + 0.1, segment_duration * 2 - fade * 2)
                filter_parts.append(
                    f"[xf01][v2]xfade=transition=fade:duration={fade}:offset={offset2:.2f}[merged]"
                )
                last_label = "merged"
                
            elif n >= 4:
                # 첫 두 개
                offset = max(0.1, segment_duration - fade)
                filter_parts.append(
                    f"[v0][v1]xfade=transition=fade:duration={fade}:offset={offset:.2f}[xf0]"
                )
                
                # 나머지 순차 연결
                for i in range(2, n):
                    prev = f"xf{i-2}"
                    # xfade 후 결과의 길이 = 이전 결과 + segment - fade
                    accumulated = segment_duration * i - fade * (i - 1)
                    curr_offset = max(0.1, accumulated - fade)
                    
                    if i == n - 1:
                        curr_label = "merged"
                    else:
                        curr_label = f"xf{i-1}"
                    
                    filter_parts.append(
                        f"[{prev}][v{i}]xfade=transition=fade:duration={fade}:offset={curr_offset:.2f}[{curr_label}]"
                    )
                
                last_label = "merged"
            else:
                last_label = "v0"
            
            # 자막 합성
            filter_parts.append(
                f"[{last_label}]ass='{sub_path_escaped}'[final]"
            )
            
            filter_complex = ';'.join(filter_parts)
            
            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', '[final]',
                '-map', f'{audio_index}:a',
                '-t', str(target_duration),
                '-r', str(self.fps),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '44100',
                '-movflags', '+faststart',
                '-shortest',
                str(output_path),
            ])
            
            logger.info(f"  FFmpeg 다중 합성 실행...")
            
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            
            if result.returncode != 0:
                logger.error(f"  FFmpeg 다중 합성 오류:\n{result.stderr[-1000:]}")
                return None
            
            if not Path(output_path).exists():
                return None
            
            output_size = Path(output_path).stat().st_size / (1024 * 1024)
            output_duration = self._get_duration(output_path)
            
            logger.info(f"  ✅ 다중 배경 합성 완료: {output_size:.1f}MB, {output_duration:.1f}초")
            
            return output_path, output_duration
    
    def _compose_single(self, background_path, audio_path, subtitle_path,
                         output_path, target_duration):
        """단일 배경 합성 (폴백)"""
        
        logger.info(f"  단일 배경 합성 모드")
        
        bg_duration = self._get_duration(background_path)
        
        loop_count = 1
        if bg_duration > 0 and bg_duration < target_duration:
            loop_count = int(target_duration / bg_duration) + 1
        
        sub_path_escaped = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
        
        cmd = [self.ffmpeg_path, '-y']
        
        if loop_count > 1:
            cmd.extend(['-stream_loop', str(loop_count - 1)])
        cmd.extend(['-i', str(background_path)])
        cmd.extend(['-i', str(audio_path)])
        
        filter_parts = []
        
        filter_parts.append(
            f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
            f"fps={self.fps},"
            f"format=yuv420p,"
            f"setsar=1[scaled]"
        )
        
        filter_parts.append(
            f"[scaled]drawbox=0:0:{self.width}:{self.height}:"
            f"color=black@{self.bg_opacity}:t=fill[darkened]"
        )
        
        filter_parts.append(
            f"[darkened]ass='{sub_path_escaped}'[subbed]"
        )
        
        filter_complex = ';'.join(filter_parts)
        
        cmd.extend([
            '-filter_complex', filter_complex,
            '-map', '[subbed]',
            '-map', '1:a',
            '-t', str(target_duration),
            '-r', str(self.fps),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-movflags', '+faststart',
            '-shortest',
            str(output_path),
        ])
        
        logger.info(f"  FFmpeg 단일 합성 실행...")
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        
        if result.returncode != 0:
            logger.error(f"  FFmpeg 단일 합성 오류:\n{result.stderr[-500:]}")
            raise Exception(f"FFmpeg 실패: {result.returncode}")
        
        if not Path(output_path).exists():
            raise Exception("출력 파일이 생성되지 않았습니다")
        
        output_size = Path(output_path).stat().st_size / (1024 * 1024)
        output_duration = self._get_duration(output_path)
        
        logger.info(f"  ✅ 단일 배경 합성 완료: {output_size:.1f}MB, {output_duration:.1f}초")
        
        return output_path, output_duration
    
    # ─── 오디오 믹싱 ───
    
    def _mix_audio(self, narration_path, bgm_path, output_path, target_duration):
        """오디오 믹싱 (나레이션 + BGM)"""
        
        narration = AudioSegment.from_file(narration_path)
        
        if bgm_path and Path(bgm_path).exists() and self.bgm_config.get('enabled', True):
            try:
                bgm = AudioSegment.from_file(bgm_path)
                
                bgm_volume = self.bgm_config.get('volume', 0.08)
                if bgm_volume > 0:
                    volume_db = 20 * math.log10(bgm_volume)
                else:
                    volume_db = -40
                bgm = bgm + volume_db
                
                target_ms = int(target_duration * 1000)
                
                if len(bgm) < target_ms:
                    loops = (target_ms // len(bgm)) + 1
                    bgm = bgm * loops
                
                bgm = bgm[:target_ms]
                
                fade_in = self.bgm_config.get('fade_in_ms', 1000)
                fade_out = self.bgm_config.get('fade_out_ms', 2000)
                bgm = bgm.fade_in(fade_in).fade_out(fade_out)
                
                if len(bgm) >= len(narration):
                    mixed = bgm.overlay(narration)
                else:
                    silence_pad = AudioSegment.silent(duration=len(narration) - len(bgm))
                    bgm_padded = bgm + silence_pad
                    mixed = bgm_padded.overlay(narration)
                
                mixed.export(output_path, format='mp3', bitrate='192k')
                logger.info(f"오디오 믹싱 완료 (BGM 포함, {len(mixed)/1000:.1f}초)")
                return
                
            except Exception as e:
                logger.warning(f"BGM 믹싱 실패, 나레이션만 사용: {e}")
        
        narration.export(output_path, format='mp3', bitrate='192k')
        logger.info(f"오디오 준비 완료 (나레이션만, {len(narration)/1000:.1f}초)")
    
    # ─── 유틸리티 ───
    
    def _get_duration(self, file_path):
        """미디어 파일 길이 (초)"""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'json',
                str(file_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            return duration
        except Exception as e:
            logger.warning(f"길이 확인 실패: {e}, 기본값 30초 사용")
            return 30.0
    
    def _cleanup(self, files):
        """임시 파일 삭제"""
        for f in files:
            try:
                if Path(f).exists():
                    os.remove(f)
            except Exception:
                pass
