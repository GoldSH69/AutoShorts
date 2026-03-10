#!/usr/bin/env python3
"""
gTTS 기반 음성 생성
"""

import io
import os
import tempfile
from pathlib import Path
from gtts import gTTS
from pydub import AudioSegment
from utils import logger, ensure_dir

class TTSGenerator:
    """gTTS 음성 생성기"""
    
    def __init__(self, config):
        self.config = config
        logger.info("TTSGenerator 초기화 (gTTS)")
    
    def generate(self, text, output_path, language='ko'):
        """
        텍스트를 음성으로 변환
        
        Args:
            text: 변환할 텍스트
            output_path: 출력 파일 경로 (.mp3)
            language: 언어 코드
        
        Returns:
            str: 출력 파일 경로
            float: 음성 길이 (초)
        """
        tts_config = self.config.get_tts_config(language)
        
        logger.info(f"TTS 생성 시작 (언어: {language}, 길이: {len(text)}자)")
        
        ensure_dir(Path(output_path).parent)
        
        try:
            # 문장 단위 분할
            sentences = self._split_sentences(text, language)
            logger.info(f"문장 분할: {len(sentences)}개")
            
            # 각 문장별 TTS 생성 후 합치기
            combined = AudioSegment.empty()
            silence = AudioSegment.silent(duration=tts_config['silence_ms'])
            
            for i, sentence in enumerate(sentences):
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                logger.info(f"  문장 {i+1}/{len(sentences)}: {sentence[:30]}...")
                
                # gTTS 생성
                tts = gTTS(
                    text=sentence,
                    lang=tts_config['lang'],
                    tld=tts_config['tld'],
                    slow=False
                )
                
                # 메모리에서 처리
                fp = io.BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                
                audio_segment = AudioSegment.from_mp3(fp)
                combined += audio_segment
                
                # 문장 사이 묵음 (마지막 제외)
                if i < len(sentences) - 1:
                    combined += silence
            
            # 속도 조절
            speed_factor = tts_config.get('speed_factor', 1.0)
            if speed_factor != 1.0:
                combined = self._change_speed(combined, speed_factor)
                logger.info(f"속도 조절: {speed_factor}x")
            
            # 저장
            combined.export(output_path, format='mp3', bitrate='128k')
            
            duration = len(combined) / 1000.0
            logger.info(f"TTS 생성 완료: {output_path} ({duration:.1f}초)")
            
            return output_path, duration
            
        except Exception as e:
            logger.error(f"TTS 생성 실패: {e}")
            raise
    
    def _split_sentences(self, text, language='ko'):
        """문장 분할"""
        import re
        
        if language == 'ko':
            # 한국어: . ? ! 기준
            sentences = re.split(r'(?<=[.?!。])\s*', text)
        else:
            # 영어: . ? ! 기준
            sentences = re.split(r'(?<=[.?!])\s+', text)
        
        # 빈 문장 제거
        return [s.strip() for s in sentences if s.strip()]
    
    def _change_speed(self, audio, speed=1.0):
        """오디오 속도 변경"""
        if speed == 1.0:
            return audio
        
        # frame_rate 변경으로 속도 조절
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
