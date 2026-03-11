#!/usr/bin/env python3
"""
gTTS 기반 음성 생성 - v2 (ffprobe 경로 문제 해결)
"""

import io
import os
import re
import shutil
import tempfile
from pathlib import Path
from gtts import gTTS
from utils import logger, ensure_dir

# ─── pydub ffmpeg 경로 설정 (반드시 import 전에) ───
def _setup_ffmpeg_path():
    """ffmpeg/ffprobe 경로를 pydub에 설정"""
    
    # 방법 1: which 명령으로 경로 찾기
    ffmpeg_path = shutil.which('ffmpeg')
    ffprobe_path = shutil.which('ffprobe')
    
    # 방법 2: 일반적인 설치 경로 확인
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
    else:
        logger.warning("⚠️ ffmpeg을 찾을 수 없습니다!")
    
    if ffprobe_path:
        logger.info(f"ffprobe 경로: {ffprobe_path}")
    else:
        logger.warning("⚠️ ffprobe를 찾을 수 없습니다!")
    
    return ffmpeg_path, ffprobe_path

# ffmpeg 경로 찾기
_ffmpeg_path, _ffprobe_path = _setup_ffmpeg_path()

# pydub import 및 경로 설정
from pydub import AudioSegment

if _ffmpeg_path:
    AudioSegment.converter = _ffmpeg_path
if _ffprobe_path:
    AudioSegment.ffprobe = _ffprobe_path


class TTSGenerator:
    """gTTS 음성 생성기 v2"""
    
    def __init__(self, config):
        self.config = config
        logger.info("TTSGenerator v2 초기화 (gTTS)")
    
    def generate(self, text, output_path, language='ko'):
        """
        텍스트를 음성으로 변환
        
        Returns:
            tuple: (output_path, duration_seconds)
        """
        tts_config = self.config.get_tts_config(language)
        
        logger.info(f"TTS 생성 시작 (언어: {language}, 길이: {len(text)}자)")
        ensure_dir(Path(output_path).parent)
        
        try:
            # 문장 분할
            sentences = self._split_sentences(text, language)
            logger.info(f"문장 분할: {len(sentences)}개")
            
            # 임시 디렉토리 사용
            with tempfile.TemporaryDirectory() as tmp_dir:
                audio_files = []
                
                for i, sentence in enumerate(sentences):
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    logger.info(f"  문장 {i+1}/{len(sentences)}: {sentence[:40]}...")
                    
                    # gTTS로 각 문장 생성 → 임시 파일 저장
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
                
                # 오디오 합치기
                combined = self._combine_audio_files(
                    audio_files, 
                    silence_ms=tts_config.get('silence_ms', 300)
                )
                
                # 속도 조절
                speed_factor = tts_config.get('speed_factor', 1.0)
                if speed_factor != 1.0 and speed_factor > 0:
                    combined = self._change_speed(combined, speed_factor)
                    logger.info(f"속도 조절: {speed_factor}x")
                
                # 최종 저장
                combined.export(output_path, format='mp3', bitrate='128k')
                
                duration = len(combined) / 1000.0
                logger.info(f"TTS 생성 완료: {output_path} ({duration:.1f}초)")
                
                return output_path, duration
            
        except Exception as e:
            logger.error(f"TTS 생성 실패: {e}")
            raise
    
    def _combine_audio_files(self, file_paths, silence_ms=300):
        """여러 오디오 파일을 하나로 합치기 (파일 기반, BytesIO 미사용)"""
        combined = AudioSegment.empty()
        silence = AudioSegment.silent(duration=silence_ms)
        
        for i, fp in enumerate(file_paths):
            try:
                segment = AudioSegment.from_file(fp, format='mp3')
                combined += segment
                
                # 마지막 아닌 경우 묵음 추가
                if i < len(file_paths) - 1:
                    combined += silence
                    
            except Exception as e:
                logger.warning(f"  오디오 파일 로드 실패 ({fp}): {e}")
                # 실패한 파일은 건너뛰기
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
        
        # 문장이 너무 적으면 쉼표로도 분할
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
