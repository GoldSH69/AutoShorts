#!/usr/bin/env python3
"""
video_composer.py v3.1 - FFmpeg 영상 합성 (다중 배경 전환 + fps 통일)
- 다중 배경: xfade 페이드 전환
- fps 통일: 모든 입력 영상을 동일 fps로 사전 변환 (timebase 불일치 해결)
- 단일 배경 폴백
- 음성 기준 영상 길이
"""

import subprocess
import os
import json
import logging
import shutil
import tempfile

logger = logging.getLogger("brain30sec")


class VideoComposer:
    """FFmpeg 기반 영상 합성기 v3.1"""

    def __init__(self, config):
        self.config = config
        self.video_config = config.get('video', {})
        self.width = self.video_config.get('width', 1080)
        self.height = self.video_config.get('height', 1920)
        self.target_fps = self.video_config.get('fps', 25)
        self.fade_duration = self.video_config.get('fade_duration', 0.5)
        self.ffmpeg_path = shutil.which('ffmpeg') or 'ffmpeg'
        self.ffprobe_path = shutil.which('ffprobe') or 'ffprobe'
        logger.info("VideoComposer v3.1 초기화 (다중 배경 전환 + fps 통일)")

    def get_duration(self, filepath):
        """미디어 파일 길이 반환"""
        try:
            cmd = [
                self.ffprobe_path, '-v', 'quiet',
                '-print_format', 'json',
                '-show_format', filepath
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            info = json.loads(result.stdout)
            return float(info['format']['duration'])
        except Exception as e:
            logger.warning(f"duration 측정 실패: {e}")
            return 0

    def normalize_video(self, input_path, output_path):
        """
        영상을 동일 fps, 해상도, 픽셀포맷으로 정규화
        xfade timebase 불일치 문제 해결의 핵심
        """
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', input_path,
            '-vf', f'scale={self.width}:{self.height}:force_original_aspect_ratio=increase,'
                   f'crop={self.width}:{self.height},'
                   f'fps={self.target_fps},'
                   f'format=yuv420p',
            '-an',  # 오디오 제거 (배경영상 오디오 불필요)
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-r', str(self.target_fps),
            '-video_track_timescale', str(self.target_fps),
            output_path
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"  정규화 완료: {os.path.basename(input_path)} → {self.target_fps}fps")
                return True
            else:
                logger.warning(f"  정규화 실패: {result.stderr[-300:]}")
                return False
        except Exception as e:
            logger.warning(f"  정규화 예외: {e}")
            return False

    def mix_audio(self, narration_path, bgm_path, output_path, duration):
        """나레이션 + BGM 믹싱"""
        if bgm_path and os.path.exists(bgm_path):
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', narration_path,
                '-stream_loop', '-1', '-i', bgm_path,
                '-filter_complex',
                f'[0:a]volume=1.0[nar];'
                f'[1:a]volume=0.08,afade=t=in:d=1,afade=t=out:st={duration - 2}:d=2[bgm];'
                f'[nar][bgm]amix=inputs=2:duration=first[out]',
                '-map', '[out]',
                '-t', str(duration),
                '-ac', '2', '-ar', '44100',
                output_path
            ]
        else:
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', narration_path,
                '-t', str(duration),
                '-ac', '2', '-ar', '44100',
                '-c:a', 'aac',
                output_path
            ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                actual_dur = self.get_duration(output_path)
                logger.info(f"오디오 믹싱 완료 (BGM {'포함' if bgm_path else '없음'}, {actual_dur:.1f}초)")
                return True
        except Exception as e:
            logger.error(f"오디오 믹싱 실패: {e}")
        return False

    def compose_multi_background(self, background_paths, audio_path, subtitle_path, output_path, total_duration):
        """다중 배경 영상 합성 <span class="ml-2" /><span class="inline-block w-3 h-3 rounded-full bg-neutral-a12 align-middle mb-[0.1rem]" />
