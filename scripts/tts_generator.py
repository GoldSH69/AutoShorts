#!/usr/bin/env python3
"""
gTTS 기반 음성 생성 - v3.1 (스마트 배속 + 상한선 + 세그먼트별 길이 측정)
"""

import io
import os
import re
import shutil
import tempfile
import subprocess
import json
from pathlib import Path
from gtts import gTTS
from utils import logger, ensure_dir

# ─── pydub ffmpeg 경로 설정 ───
def _setup_ffmpeg_path():
    """ffmpeg/ffprobe 경로를 pydub에 설정"""
    ffmpeg_path = shutil.which('ffmpeg')
    ffprobe_path = shutil.which('ffprobe')
    
    if not ffmpeg_path:
        for path in ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg']:
            if os.path.exists(path):
                ffmpeg_path = path
                break
    
    if not ffprobe_path:
        for path in ['/usr/bin/ffprobe', '/usr/local/bin/ffprobe']:
            if os.path.exists(path):
                ffprobe_path = path
                break
    
    if ffmpeg_path:
        logger.info(f"ffmpeg 경로: {ffmpeg_path}")
    if ffprobe_path:
        logger.info(f"ffprobe 경로: {ffprobe_path}")
    
    return ffmpeg_path, ffprobe_path

_ffmpeg_path, _ffprobe_path = _setup_ffmpeg_path()

from pydub import AudioSegment

if _ffmpeg_path:
    AudioSegment.converter = _ffmpeg_path
if _ffprobe_path:
    AudioSegment.ffprobe = _ffprobe_path


class TTSGenerator:
    """gTTS 음성 생성기 v3.1 - 스마트 배속 + 상한선 + 세그먼트별 타이밍"""
    
    def __init__(self, config):
        self.config = config
        self.video_config = config.get_video_config()
        logger.info("TTSGenerator v3.1 초기화 (스마트 배속 + 상한선)")
    
    def generate(self, text, output_path, language='ko', segments=None):
        """
        텍스트를 음성으로 변환
        
        Args:
            text: 전체 나레이션 텍스트
            output_path: 출력 파일 경로
            language: 언어
            segments: subtitle_segments (각 세그먼트별 타이밍 측정용)
        
        Returns:
            tuple: (output_path, duration_seconds, timed_segments)
            - timed_segments: [{"text": "...", "start": 0.0, "end": 3.2}, ...]
        """
        tts_config = self.config.get_tts_config(language)
        
        logger.info(f"TTS 생성 시작 (언어: {language}, 길이: {len(text)}자)")
        ensure_dir(Path(output_path).parent)
        
        # 목표 시간 설정
        target_duration = self.video_config.get('duration', 50)
        max_duration = self.video_config.get('max_duration', 55)
        
        logger.info(f"  목표: {target_duration}초, 최대: {max_duration}초")
        
        try:
            if segments and len(segments) > 0:
                return self._generate_with_segments(
                    segments, output_path, language, tts_config,
                    target_duration, max_duration
                )
            
            return self._generate_simple(
                text, output_path, language, tts_config,
                target_duration, max_duration
            )
            
        except Exception as e:
            logger.error(f"TTS 생성 실패: {e}")
            raise
    
    def _calculate_smart_speed(self, raw_duration, narration_target, tts_config):
        """
        🆕 v3.1 스마트 배속 계산
        - 자동배속(시간맞춤)과 기본배속(gTTS보정) 중 큰 값 선택
        - 상한선 적용으로 과배속 방지
        
        Returns:
            float: 최종 배속 값
        """
        max_speed_limit = tts_config.get('max_speed', 1.50)
        base_speed = tts_config.get('speed_factor', 1.0)
        
        # ① 자동 배속 계산 (목표 시간 맞추기)
        if raw_duration > narration_target:
            auto_speed = raw_duration / narration_target
            logger.info(f"  ⏩ 자동 배속 필요: {auto_speed:.2f}x ({raw_duration:.1f}초 → {narration_target:.1f}초)")
        elif raw_duration < narration_target * 0.7:
            auto_speed = max(raw_duration / narration_target, 0.9)
            logger.info(f"  ⏪ 속도 감소 필요: {auto_speed:.2f}x (너무 짧음)")
        else:
            auto_speed = 1.0
            logger.info(f"  ⏸️ 자동 배속 불필요 ({raw_duration:.1f}초)")
        
        # ② 최종 배속: 자동 배속 vs 기본 배속 중 큰 값 (곱하기 ❌)
        speed_factor = max(auto_speed, base_speed)
        
        # ③ 상한선 적용
        speed_factor = min(speed_factor, max_speed_limit)
        
        logger.info(f"  🎯 배속 결정: auto={auto_speed:.2f}x, base={base_speed:.2f}x, max={max_speed_limit:.2f}x → 최종 {speed_factor:.2f}x")
        
        return speed_factor
    
    def _generate_with_segments(self, segments, output_path, language,
                                 tts_config, target_duration, max_duration):
        """
        세그먼트별 TTS 생성 → 실제 타이밍 측정 → 스마트 배속
        """
        logger.info(f"세그먼트 기반 TTS 생성 ({len(segments)}개)")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            segment_audios = []
            silence_ms = tts_config.get('silence_ms', 250)
            silence = AudioSegment.silent(duration=silence_ms)
            
            # ① 각 세그먼트별 TTS 생성
            for i, seg in enumerate(segments):
                text = seg.get('text', '').strip()
                if not text:
                    continue
                
                logger.info(f"  세그먼트 {i+1}/{len(segments)}: {text[:30]}...")
                
                tmp_file = os.path.join(tmp_dir, f"seg_{i:03d}.mp3")
                
                tts = gTTS(
                    text=text,
                    lang=tts_config['lang'],
                    tld=tts_config['tld'],
                    slow=False
                )
                tts.save(tmp_file)
                
                audio = AudioSegment.from_file(tmp_file, format='mp3')
                segment_audios.append((audio, text))
            
            if not segment_audios:
                raise Exception("생성된 오디오 세그먼트가 없습니다")
            
            # ② 원본 합치기 (배속 전 길이 측정)
            combined_raw = AudioSegment.empty()
            for i, (audio, text) in enumerate(segment_audios):
                combined_raw += audio
                if i < len(segment_audios) - 1:
                    combined_raw += silence
            
            raw_duration = len(combined_raw) / 1000.0
            logger.info(f"  원본 음성 길이: {raw_duration:.1f}초")
            
            # ③ 🆕 스마트 배속 계산
            narration_target = target_duration - 2.0
            speed_factor = self._calculate_smart_speed(
                raw_duration, narration_target, tts_config
            )
            
            # ④ 각 세그먼트에 배속 적용 + 타이밍 측정
            timed_segments = []
            combined_final = AudioSegment.empty()
            current_time = 0.0
            
            for i, (audio, text) in enumerate(segment_audios):
                if speed_factor != 1.0:
                    audio = self._change_speed(audio, speed_factor)
                
                seg_duration = len(audio) / 1000.0
                
                timed_segments.append({
                    'text': text,
                    'start': round(current_time, 2),
                    'end': round(current_time + seg_duration, 2),
                    'duration': round(seg_duration, 2),
                })
                
                combined_final += audio
                current_time += seg_duration
                
                if i < len(segment_audios) - 1:
                    adjusted_silence_ms = int(silence_ms / max(speed_factor, 1.0))
                    adjusted_silence_ms = max(adjusted_silence_ms, 100)
                    adj_silence = AudioSegment.silent(duration=adjusted_silence_ms)
                    combined_final += adj_silence
                    current_time += adjusted_silence_ms / 1000.0
            
            # ⑤ 최종 길이 확인 (여전히 길면 추가 배속)
            final_duration = len(combined_final) / 1000.0
            max_speed_limit = tts_config.get('max_speed', 1.50)
            
            if final_duration > max_duration - 2:
                extra_speed = final_duration / (max_duration - 3)
                extra_speed = min(extra_speed, 1.2)
                logger.warning(f"  ⚠️ 여전히 김 ({final_duration:.1f}초), 추가 배속 {extra_speed:.2f}x")
                combined_final = self._change_speed(combined_final, extra_speed)
                
                for seg in timed_segments:
                    seg['start'] = round(seg['start'] / extra_speed, 2)
                    seg['end'] = round(seg['end'] / extra_speed, 2)
                    seg['duration'] = round(seg['duration'] / extra_speed, 2)
                
                final_duration = len(combined_final) / 1000.0
            
            # ⑥ 저장
            combined_final.export(output_path, format='mp3', bitrate='128k')
            
            logger.info(f"✅ TTS 생성 완료: {final_duration:.1f}초, {len(timed_segments)}개 세그먼트")
            for i, ts in enumerate(timed_segments):
                logger.info(f"  [{ts['start']:.1f}s ~ {ts['end']:.1f}s] {ts['text'][:25]}...")
            
            return output_path, final_duration, timed_segments
    
    def _generate_simple(self, text, output_path, language, tts_config,
                          target_duration, max_duration):
        """세그먼트 없이 전체 텍스트 기반 생성 (폴백)"""
        
        sentences = self._split_sentences(text, language)
        logger.info(f"문장 분할: {len(sentences)}개")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_files = []
            
            for i, sentence in enumerate(sentences):
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                tmp_file = os.path.join(tmp_dir, f"sentence_{i:03d}.mp3")
                
                tts = gTTS(
                    text=sentence,
                    lang=tts_config['lang'],
                    tld=tts_config['tld'],
                    slow=False
                )
                tts.save(tmp_file)
                audio_files.append(tmp_file)
            
            if not audio_files:
                raise Exception("생성된 오디오 파일이 없습니다")
            
            combined = self._combine_audio_files(
                audio_files,
                silence_ms=tts_config.get('silence_ms', 250)
            )
            
            # 🆕 스마트 배속 계산
            raw_duration = len(combined) / 1000.0
            narration_target = target_duration - 2.0
            speed_factor = self._calculate_smart_speed(
                raw_duration, narration_target, tts_config
            )
            
            if speed_factor != 1.0:
                combined = self._change_speed(combined, speed_factor)
            
            combined.export(output_path, format='mp3', bitrate='128k')
            
            duration = len(combined) / 1000.0
            logger.info(f"✅ TTS 생성 완료: {output_path} ({duration:.1f}초)")
            
            return output_path, duration, None
    
    def _combine_audio_files(self, file_paths, silence_ms=250):
        """여러 오디오 파일을 하나로 합치기"""
        combined = AudioSegment.empty()
        silence = AudioSegment.silent(duration=silence_ms)
        
        for i, fp in enumerate(file_paths):
            try:
                segment = AudioSegment.from_file(fp, format='mp3')
                combined += segment
                if i < len(file_paths) - 1:
                    combined += silence
            except Exception as e:
                logger.warning(f"  오디오 파일 로드 실패 ({fp}): {e}")
                continue
        
        if len(combined) == 0:
            raise Exception("합친 오디오가 비어있습니다")
        
        return combined
    
    def _split_sentences(self, text, language='ko'):
        """문장 분할"""
        if language == 'ko':
            sentences = re.split(r'(?<=[.?!。])\s*', text)
        else:
            sentences = re.split(r'(?<=[.?!])\s+', text)
        
        result = [s.strip() for s in sentences if s.strip()]
        
        if len(result) <= 1 and len(text) > 60:
            sentences = re.split(r'[,，]\s*', text)
            result = [s.strip() for s in sentences if s.strip()]
        
        return result if result else [text]
    
    def _change_speed(self, audio, speed=1.0):
        """오디오 속도 변경"""
        if speed == 1.0:
            return audio
        
        sound_with_altered_frame_rate = audio._spawn(
            audio.raw_data,
            overrides={
                "frame_rate": int(audio.frame_rate * speed)
            }
        )
        return sound_with_altered_frame_rate.set_frame_rate(audio.frame_rate)
    
    def get_audio_duration(self, audio_path):
        """오디오 파일 길이 반환 (초)"""
        audio = AudioSegment.from_file(audio_path)
        return len(audio) / 1000.0
