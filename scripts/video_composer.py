#!/usr/bin/env python3
"""
FFmpeg 기반 영상 합성 - v3 (다중 배경 전환 + 페이드)
"""

import os
import math
import subprocess
import json
from pathlib import Path
from pydub import AudioSegment
from utils import logger, ensure_dir

class VideoComposer:
    """FFmpeg 영상 합성기 v3 - 다중 배경 전환"""
    
    def __init__(self, config):
        self.config = config
        self.video_config = config.get_video_config()
        self.bgm_config = config.get_bgm_config()
        
        self.width = self.video_config.get('width', 1080)
        self.height = self.video_config.get('height', 1920)
        self.fps = self.video_config.get('fps', 30)
        self.bg_opacity = self.video_config.get('background_opacity', 0.4)
        self.fade_duration = self.video_config.get('fade_duration', 0.5)
        
        logger.info("VideoComposer v3 초기화 (다중 배경 전환)")
    
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
        
        # FFmpeg 합성
        if len(valid_paths) >= 2:
            # ★ 다중 배경: 구간별 전환 + 페이드
            cmd = self._build_multi_bg_command(
                background_paths=valid_paths,
                audio_path=mixed_audio_path,
                subtitle_path=subtitle_path,
                output_path=output_path,
                target_duration=target_duration,
            )
        else:
            # 단일 배경 (폴백)
            cmd = self._build_single_bg_command(
                background_path=valid_paths[0],
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
                timeout=600,  # 다중 영상은 시간 더 필요
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg 오류:\n{result.stderr[-2000:]}")
                
                # 다중 배경 실패 시 단일 배경으로 폴백
                if len(valid_paths) >= 2:
                    logger.warning("다중 배경 실패, 단일 배경으로 재시도...")
                    return self._fallback_single(
                        valid_paths[0], mixed_audio_path, subtitle_path,
                        output_path, target_duration
                    )
                
                raise Exception(f"FFmpeg 실패: {result.returncode}")
            
            if not Path(output_path).exists():
                raise Exception("출력 파일이 생성되지 않았습니다")
            
            output_size = Path(output_path).stat().st_size / (1024 * 1024)
            output_duration = self._get_duration(output_path)
            
            logger.info(f"영상 합성 완료: {output_size:.1f}MB, {output_duration:.1f}초")
            
            self._cleanup([mixed_audio_path])
            
            return output_path, output_duration
            
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg 타임아웃 (600초)")
            raise
    
    def _build_multi_bg_command(self, background_paths, audio_path,
                                 subtitle_path, output_path, target_duration):
        """다중 배경 FFmpeg 명령 빌드"""
        
        n = len(background_paths)
        segment_duration = target_duration / n
        fade = self.fade_duration
        
        logger.info(f"  구간 분할: {n}개 × {segment_duration:.1f}초 (페이드: {fade}초)")
        
        sub_path_escaped = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
        
        cmd = ['ffmpeg', '-y']
        
        # ── 입력: 각 배경 영상 ──
        for i, bg_path in enumerate(background_paths):
            bg_duration = self._get_duration(bg_path)
            if bg_duration < segment_duration:
                loop_count = int(segment_duration / bg_duration) + 1
                cmd.extend(['-stream_loop', str(loop_count)])
            cmd.extend(['-i', str(bg_path)])
        
        # 오디오 입력
        cmd.extend(['-i', str(audio_path)])
        audio_index = n  # 오디오의 입력 인덱스
        
        # ── 필터 체인 ──
        filter_parts = []
        
        # 각 배경 스케일 + 크롭 + 어둡게 + 트림
        for i in range(n):
            start = i * segment_duration
            end = start + segment_duration + fade  # 페이드 오버랩용 여유
            
            filter_parts.append(
                f"[{i}:v]"
                f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                f"crop={self.width}:{self.height},setsar=1,"
                f"drawbox=0:0:{self.width}:{self.height}:color=black@{self.bg_opacity}:t=fill,"
                f"trim=0:{segment_duration + fade},setpts=PTS-STARTPTS"
                f"[bg{i}]"
            )
        
        # ── xfade로 영상 연결 (페이드 전환) ──
        if n == 1:
            # 1개면 그냥 사용
            last_label = "bg0"
        elif n == 2:
            offset = segment_duration - fade
            filter_parts.append(
                f"[bg0][bg1]xfade=transition=fade:duration={fade}:offset={offset:.2f}[merged]"
            )
            last_label = "merged"
        else:
            # 3개 이상: 순차적으로 xfade
            # 첫 두 개 합치기
            offset = segment_duration - fade
            filter_parts.append(
                f"[bg0][bg1]xfade=transition=fade:duration={fade}:offset={offset:.2f}[xf0]"
            )
            
            for i in range(2, n):
                prev_label = f"xf{i-2}"
                curr_label = f"xf{i-1}" if i < n - 1 else "merged"
                offset = segment_duration * i - fade * i
                # offset이 음수가 되지 않도록
                offset = max(offset, segment_duration * (i - 1))
                
                filter_parts.append(
                    f"[{prev_label}][bg{i}]xfade=transition=fade:duration={fade}:offset={offset:.2f}[{curr_label}]"
                )
            
            last_label = f"xf{n-2}" if n > 2 else "merged"
            # 마지막 라벨 보정
            if n == 3:
                last_label = "merged"
            elif n >= 4:
                last_label = f"xf{n-2}"
        
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
        
        return cmd
    
    def _build_single_bg_command(self, background_path, audio_path,
                                  subtitle_path, output_path, target_duration):
        """단일 배경 FFmpeg 명령 (기존 방식)"""
        
        bg_duration = self._get_duration(background_path)
        
        loop_count = 1
        if bg_duration < target_duration:
            loop_count = int(target_duration / bg_duration) + 1
        
        sub_path_escaped = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
        
        cmd = ['ffmpeg', '-y']
        
        if loop_count > 1:
            cmd.extend(['-stream_loop', str(loop_count - 1)])
        cmd.extend(['-i', str(background_path)])
        cmd.extend(['-i', str(audio_path)])
        
        filter_parts = []
        
        filter_parts.append(
            f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
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
        
        return cmd
    
    def _fallback_single(self, background_path, audio_path, subtitle_path,
                          output_path, target_duration):
        """다중 배경 실패 시 단일 배경 폴백"""
        logger.info("단일 배경 폴백 모드")
        
        cmd = self._build_single_bg_command(
            background_path, audio_path, subtitle_path,
            output_path, target_duration
        )
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            raise Exception(f"폴백도 실패: {result.stderr[-500:]}")
        
        output_duration = self._get_duration(output_path)
        return output_path, output_duration
    
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
    
    def _get_duration(self, file_path):
        """미디어 파일 길이 (초)"""
        try:
            cmd = [
                'ffprobe',
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
