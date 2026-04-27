#!/usr/bin/env python3
"""
Edge TTS 기반 음성 생성 - v4.0
(요일별 음성 매핑 + 스마트 배속 + gTTS 폴백)
"""
"""
Edge TTS 기반 음성 생성 - v4.2
(요일별 음성 매핑 + 스마트 배속 + 텍스트 정제 + per-sentence 재시도 + gTTS 폴백)
"""

import asyncio
import io
import os
import re
import shutil
import tempfile
import subprocess
import json
from pathlib import Path
from utils import logger, ensure_dir

# ─── 요일별 음성 매핑 (config 로드 실패 시 폴백) ───
DEFAULT_VOICES = {
    'money': 'ko-KR-InJoonNeural',
    'success': 'ko-KR-InJoonNeural',
    'brain': 'ko-KR-SunHiNeural',
    'dark': 'ko-KR-InJoonNeural',
    'hack': 'ko-KR-SunHiNeural',
    'love': 'ko-KR-SunHiNeural',
    'relationship': 'ko-KR-SunHiNeural',
}
DEFAULT_VOICE = 'ko-KR-InJoonNeural'

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
    """Edge TTS 음성 생성기 v4.0 - 요일별 음성 + 스마트 배속 + gTTS 폴백"""

    def __init__(self, config, category_id=None):
        self.config = config
        self.video_config = config.get_video_config()
        self.category_id = category_id
        self._voice = self._resolve_voice(category_id)
        logger.info(f"TTSGenerator v4.2 초기화 (engine: edge-tts, voice: {self._voice})")

    def _resolve_voice(self, category_id):
        """카테고리 ID로 음성 결정"""
        tts_config = self.config.get_tts_config()
        voices = tts_config.get('voices', {})

        if category_id and category_id in voices:
            voice = voices[category_id]
            logger.info(f"  카테고리 '{category_id}' → 음성: {voice}")
            return voice

        if category_id and category_id in DEFAULT_VOICES:
            voice = DEFAULT_VOICES[category_id]
            logger.info(f"  카테고리 '{category_id}' → 기본 음성: {voice}")
            return voice

        default = voices.get('default', DEFAULT_VOICE)
        logger.info(f"  카테고리 미지정 → 기본 음성: {default}")
        return default

    def generate(self, text, output_path, language='ko', segments=None):
        """
        텍스트를 음성으로 변환

        Returns:
            tuple: (output_path, duration_seconds, timed_segments)
        """
        tts_config = self.config.get_tts_config(language)

        logger.info(f"TTS 생성 시작 (엔진: edge-tts, 음성: {self._voice}, 길이: {len(text)}자)")
        ensure_dir(Path(output_path).parent)

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
            logger.error(f"Edge TTS 실패: {e}")
            logger.info("gTTS 폴백 시도...")
            return self._generate_gtts_fallback(
                text, output_path, language, tts_config,
                target_duration, max_duration
            )

    # ─── Edge TTS 코어 ───

    def _edge_tts_to_file(self, text, output_file, rate="+0%"):
        """Edge TTS로 단일 텍스트를 파일로 변환"""
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(
                text=text,
                voice=self._voice,
                rate=rate
            )
            await communicate.save(output_file)

        asyncio.run(_run())

    def _calculate_edge_rate(self, raw_duration, narration_target, tts_config):
        """
        스마트 배속 계산 → Edge TTS rate 문자열 반환
        예: "+15%", "+30%", "-5%"
        """
        max_speed_limit = tts_config.get('max_speed', 1.40)
        base_rate_str = tts_config.get('rate', '+0%')

        # base_rate 파싱 ("+5%" → 1.05)
        base_rate_num = self._parse_rate(base_rate_str)

        # 자동 배속 계산
        if raw_duration > narration_target:
            auto_speed = raw_duration / narration_target
        elif raw_duration < narration_target * 0.7:
            auto_speed = max(raw_duration / narration_target, 0.9)
        else:
            auto_speed = 1.0

        # 최종 배속: 큰 값 선택 + 상한선
        speed_factor = max(auto_speed, base_rate_num)
        speed_factor = min(speed_factor, max_speed_limit)

        # 배속 → rate 문자열 변환
        rate_percent = int((speed_factor - 1.0) * 100)
        rate_str = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"

        logger.info(f"  🎯 배속: auto={auto_speed:.2f}x, base={base_rate_num:.2f}x → {speed_factor:.2f}x (rate={rate_str})")

        return rate_str, speed_factor

    def _parse_rate(self, rate_str):
        """Edge TTS rate 문자열 → 배속 float 변환 ("+10%" → 1.10)"""
        try:
            clean = rate_str.replace('%', '').replace('+', '')
            return 1.0 + float(clean) / 100.0
        except:
            return 1.0

    # ─── 세그먼트 기반 생성 ───

    def _generate_with_segments(self, segments, output_path, language,
                                 tts_config, target_duration, max_duration):
        """세그먼트별 Edge TTS 생성 → 타이밍 측정 → 스마트 배속"""
        logger.info(f"세그먼트 기반 TTS 생성 ({len(segments)}개)")

        base_rate = tts_config.get('rate', '+0%')

        with tempfile.TemporaryDirectory() as tmp_dir:
            segment_audios = []
            silence_ms = tts_config.get('silence_ms', 250)
            silence = AudioSegment.silent(duration=silence_ms)

            # ① 각 세그먼트별 TTS 생성 (기본 rate)
            for i, seg in enumerate(segments):
                text = seg.get('text', '').strip()
                if not text:
                    continue

                logger.info(f"  세그먼트 {i+1}/{len(segments)}: {text[:30]}...")

                tmp_file = os.path.join(tmp_dir, f"seg_{i:03d}.mp3")
                self._edge_tts_to_file(text, tmp_file, rate=base_rate)

                audio = AudioSegment.from_file(tmp_file, format='mp3')
                segment_audios.append((audio, text))

            if not segment_audios:
                raise Exception("생성된 오디오 세그먼트가 없습니다")

            # ② 원본 길이 측정
            combined_raw = AudioSegment.empty()
            for i, (audio, text) in enumerate(segment_audios):
                combined_raw += audio
                if i < len(segment_audios) - 1:
                    combined_raw += silence

            raw_duration = len(combined_raw) / 1000.0
            logger.info(f"  원본 음성 길이: {raw_duration:.1f}초")

            # ③ 스마트 배속 계산
            narration_target = target_duration - 2.0
            rate_str, speed_factor = self._calculate_edge_rate(
                raw_duration, narration_target, tts_config
            )

            # ④ 배속 필요 시 재생성
            need_regen = abs(speed_factor - self._parse_rate(base_rate)) > 0.03

            if need_regen:
                logger.info(f"  🔄 배속 변경으로 재생성 (rate={rate_str})")
                segment_audios = []
                for i, seg in enumerate(segments):
                    text = seg.get('text', '').strip()
                    if not text:
                        continue

                    tmp_file = os.path.join(tmp_dir, f"seg_re_{i:03d}.mp3")
                    self._edge_tts_to_file(text, tmp_file, rate=rate_str)

                    audio = AudioSegment.from_file(tmp_file, format='mp3')
                    segment_audios.append((audio, text))

            # ⑤ 타이밍 측정 + 합치기
            timed_segments = []
            combined_final = AudioSegment.empty()
            current_time = 0.0

            for i, (audio, text) in enumerate(segment_audios):
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
                    adj_silence_ms = max(int(silence_ms / max(speed_factor, 1.0)), 100)
                    adj_silence = AudioSegment.silent(duration=adj_silence_ms)
                    combined_final += adj_silence
                    current_time += adj_silence_ms / 1000.0

            # ⑥ 최종 길이 확인
            final_duration = len(combined_final) / 1000.0

            if final_duration > max_duration - 2:
                extra_speed = min(final_duration / (max_duration - 3), 1.2)
                logger.warning(f"  ⚠️ 여전히 김 ({final_duration:.1f}초), pydub 추가 배속 {extra_speed:.2f}x")
                combined_final = self._change_speed(combined_final, extra_speed)

                for seg in timed_segments:
                    seg['start'] = round(seg['start'] / extra_speed, 2)
                    seg['end'] = round(seg['end'] / extra_speed, 2)
                    seg['duration'] = round(seg['duration'] / extra_speed, 2)

                final_duration = len(combined_final) / 1000.0

            # ⑦ 저장
            combined_final.export(output_path, format='mp3', bitrate='192k')

            logger.info(f"✅ TTS 생성 완료: {final_duration:.1f}초, {len(timed_segments)}개 세그먼트")
            for i, ts in enumerate(timed_segments):
                logger.info(f"  [{ts['start']:.1f}s ~ {ts['end']:.1f}s] {ts['text'][:25]}...")

            return output_path, final_duration, timed_segments

    # ─── 심플 생성 ───

    def _generate_simple(self, text, output_path, language, tts_config,
                          target_duration, max_duration):
        """전체 텍스트 → 문장 분리 → 세그먼트별 TTS + 타이밍 측정"""
        sentences = self._split_sentences(text, language)
        logger.info(f"문장 분할: {len(sentences)}개")

        base_rate = tts_config.get('rate', '+0%')

        with tempfile.TemporaryDirectory() as tmp_dir:
            segment_audios = []

            for i, sentence in enumerate(sentences):
                sentence = sentence.strip()
                if not sentence:
                    continue

                # TTS용 텍스트 정제 (이모지/특수문자 제거)
                tts_text = self._clean_tts_text(sentence)
                if not tts_text or len(tts_text) < 2:
                    logger.warning(f"  문장 {i+1} 건너뜀 (정제 후 빈 텍스트): {sentence[:30]}")
                    continue

                tmp_file = os.path.join(tmp_dir, f"sentence_{i:03d}.mp3")

                # per-sentence 재시도 (max 2회)
                success = False
                for attempt in range(2):
                    try:
                        self._edge_tts_to_file(tts_text, tmp_file, rate=base_rate)
                        audio = AudioSegment.from_file(tmp_file, format='mp3')
                        segment_audios.append((audio, sentence))  # 원문 텍스트 보존
                        success = True
                        break
                    except Exception as e:
                        logger.warning(f"  문장 {i+1} Edge TTS 실패 (시도 {attempt+1}/2): {e}")
                        if attempt == 0:
                            import time
                            time.sleep(1)

                if not success:
                    logger.warning(f"  문장 {i+1} 최종 실패, 건너뜀: {sentence[:30]}")

            if not segment_audios:
                raise Exception("생성된 오디오 파일이 없습니다")

            silence_ms = tts_config.get('silence_ms', 250)

            # 원본 길이 측정
            combined_raw = AudioSegment.empty()
            for i, (audio, text) in enumerate(segment_audios):
                combined_raw += audio
                if i < len(segment_audios) - 1:
                    combined_raw += AudioSegment.silent(duration=silence_ms)

            raw_duration = len(combined_raw) / 1000.0
            narration_target = target_duration - 2.0
            rate_str, speed_factor = self._calculate_edge_rate(
                raw_duration, narration_target, tts_config
            )

            # 배속 필요 시 재생성
            need_regen = abs(speed_factor - self._parse_rate(base_rate)) > 0.03

            if need_regen:
                logger.info(f"  🔄 배속 변경으로 재생성 (rate={rate_str})")
                segment_audios = []
                for i, sentence in enumerate(sentences):
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    tts_text = self._clean_tts_text(sentence)
                    if not tts_text or len(tts_text) < 2:
                        continue

                    tmp_file = os.path.join(tmp_dir, f"sentence_re_{i:03d}.mp3")
                    try:
                        self._edge_tts_to_file(tts_text, tmp_file, rate=rate_str)
                        audio = AudioSegment.from_file(tmp_file, format='mp3')
                        segment_audios.append((audio, sentence))
                    except Exception as e:
                        logger.warning(f"  재생성 문장 {i+1} 실패, 건너뜀: {e}")

            # 타이밍 측정 + 합치기
            timed_segments = []
            combined_final = AudioSegment.empty()
            current_time = 0.0

            for i, (audio, text) in enumerate(segment_audios):
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
                    adj_silence_ms = max(int(silence_ms / max(speed_factor, 1.0)), 100)
                    combined_final += AudioSegment.silent(duration=adj_silence_ms)
                    current_time += adj_silence_ms / 1000.0

            # 최종 길이 확인
            final_duration = len(combined_final) / 1000.0

            if final_duration > max_duration - 2:
                extra_speed = min(final_duration / (max_duration - 3), 1.2)
                logger.warning(f"  ⚠️ 여전히 김 ({final_duration:.1f}초), pydub 추가 배속 {extra_speed:.2f}x")
                combined_final = self._change_speed(combined_final, extra_speed)

                for seg in timed_segments:
                    seg['start'] = round(seg['start'] / extra_speed, 2)
                    seg['end'] = round(seg['end'] / extra_speed, 2)
                    seg['duration'] = round(seg['duration'] / extra_speed, 2)

                final_duration = len(combined_final) / 1000.0

            combined_final.export(output_path, format='mp3', bitrate='192k')

            logger.info(f"✅ TTS 생성 완료: {final_duration:.1f}초, {len(timed_segments)}개 세그먼트")
            for i, ts in enumerate(timed_segments):
                logger.info(f"  [{ts['start']:.1f}s ~ {ts['end']:.1f}s] {ts['text'][:25]}...")

            return output_path, final_duration, timed_segments

    # ─── gTTS 폴백 ───

    def _generate_gtts_fallback(self, text, output_path, language, tts_config,
                                 target_duration, max_duration, segments=None):
        """Edge TTS 실패 시 gTTS로 폴백 (timed_segments 포함)"""
        from gtts import gTTS

        logger.warning("⚠️ gTTS 폴백 모드 (품질 저하)")

        sentences = self._split_sentences(text, language)

        with tempfile.TemporaryDirectory() as tmp_dir:
            segment_audios = []

            for i, sentence in enumerate(sentences):
                sentence = sentence.strip()
                if not sentence:
                    continue

                # TTS용 텍스트 정제
                tts_text = self._clean_tts_text(sentence)
                if not tts_text or len(tts_text) < 2:
                    logger.warning(f"  gTTS 문장 {i+1} 건너뜀 (정제 후 빈 텍스트): {sentence[:30]}")
                    continue

                tmp_file = os.path.join(tmp_dir, f"fb_{i:03d}.mp3")
                try:
                    tts = gTTS(
                        text=tts_text,
                        lang=tts_config['lang'],
                        tld=tts_config.get('tld', 'com'),
                        slow=False
                    )
                    tts.save(tmp_file)

                    audio = AudioSegment.from_file(tmp_file, format='mp3')
                    segment_audios.append((audio, sentence))  # 원문 보존
                except Exception as e:
                    logger.warning(f"  gTTS 문장 {i+1} 실패, 건너뜀: {e}")

            if not segment_audios:
                raise Exception("gTTS 폴백도 실패")

            silence_ms = tts_config.get('silence_ms', 250)

            # 원본 길이 측정
            combined_raw = AudioSegment.empty()
            for i, (audio, text) in enumerate(segment_audios):
                combined_raw += audio
                if i < len(segment_audios) - 1:
                    combined_raw += AudioSegment.silent(duration=silence_ms)

            raw_duration = len(combined_raw) / 1000.0
            narration_target = target_duration - 2.0
            speed_factor = self._calculate_smart_speed_legacy(
                raw_duration, narration_target, tts_config
            )

            # 배속 적용
            if speed_factor != 1.0:
                new_audios = []
                for audio, sentence in segment_audios:
                    new_audios.append((self._change_speed(audio, speed_factor), sentence))
                segment_audios = new_audios

            # 타이밍 측정 + 합치기
            timed_segments = []
            combined_final = AudioSegment.empty()
            current_time = 0.0

            for i, (audio, text) in enumerate(segment_audios):
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
                    adj_silence_ms = max(int(silence_ms / max(speed_factor, 1.0)), 100)
                    combined_final += AudioSegment.silent(duration=adj_silence_ms)
                    current_time += adj_silence_ms / 1000.0

            # 최종 길이 확인 (안전장치)
            final_duration = len(combined_final) / 1000.0

            if final_duration > max_duration - 2:
                extra_speed = min(final_duration / (max_duration - 3), 1.2)
                logger.warning(f"  ⚠️ gTTS 여전히 김 ({final_duration:.1f}초), pydub 추가 배속 {extra_speed:.2f}x")
                combined_final = self._change_speed(combined_final, extra_speed)

                for seg in timed_segments:
                    seg['start'] = round(seg['start'] / extra_speed, 2)
                    seg['end'] = round(seg['end'] / extra_speed, 2)
                    seg['duration'] = round(seg['duration'] / extra_speed, 2)

                final_duration = len(combined_final) / 1000.0

            combined_final.export(output_path, format='mp3', bitrate='128k')

            final_duration = len(combined_final) / 1000.0

            logger.info(f"✅ gTTS 폴백 완료: {final_duration:.1f}초, {len(timed_segments)}개 세그먼트")
            for i, ts in enumerate(timed_segments):
                logger.info(f"  [{ts['start']:.1f}s ~ {ts['end']:.1f}s] {ts['text'][:25]}...")

            return output_path, final_duration, timed_segments

    def _calculate_smart_speed_legacy(self, raw_duration, narration_target, tts_config):
        """v3.1 레거시 스마트 배속 (gTTS 폴백용)"""
        max_speed_limit = tts_config.get('max_speed', 1.50)
        base_speed = tts_config.get('speed_factor', 1.0)

        if raw_duration > narration_target:
            auto_speed = raw_duration / narration_target
        elif raw_duration < narration_target * 0.7:
            auto_speed = max(raw_duration / narration_target, 0.9)
        else:
            auto_speed = 1.0

        speed_factor = max(auto_speed, base_speed)
        speed_factor = min(speed_factor, max_speed_limit)

        return speed_factor

    # ─── 유틸리티 ───

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

    def _clean_tts_text(self, text):
        """TTS용 텍스트 정제 - 이모지/특수문자 제거, 읽을 수 있는 텍스트만 남김"""
        import unicodedata
        cleaned = []
        for c in text:
            cat = unicodedata.category(c)
            cp = ord(c)
            # 이모지 범위 제거
            if 0x1F300 <= cp <= 0x1FAFF:
                continue
            if 0x2600 <= cp <= 0x27BF:
                continue
            if 0xFE00 <= cp <= 0xFE0F:
                continue
            if cp == 0x200D:
                continue
            # Symbol 카테고리 제거 (So=기타심볼, Sk=수식심볼)
            if cat in ('So', 'Sk'):
                continue
            cleaned.append(c)
        result = ''.join(cleaned).strip()
        # 연속 공백 정리
        result = re.sub(r'\s+', ' ', result)
        return result

    def _change_speed(self, audio, speed=1.0):
        """오디오 속도 변경 (pydub, 최후 수단)"""
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