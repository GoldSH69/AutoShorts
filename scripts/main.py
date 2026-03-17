#!/usr/bin/env python3
"""
뇌를 깨우는 30초 - 메인 오케스트레이터 v3

1. 설정 로드
2. 스크립트 생성 (Gemini) → 키워드 3개
3. TTS 음성 생성 (gTTS) → 자동 배속 + 세그먼트 타이밍
4. 배경 영상 다운로드 (Pexels) → 3~4개
5. 자막 생성 (ASS) → TTS 타이밍 기반 싱크
6. 영상 합성 (FFmpeg) → 다중 배경 전환 + 페이드
7. YouTube 업로드 (옵션)
8. 텔레그램 알림
"""

import os
import sys
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils import (
    logger, setup_logging, get_project_root, get_output_dir,
    get_today_str, get_weekday, get_weekday_name_ko,
    select_bgm, ensure_dir
)
from config_loader import Config, parse_args
from script_generator import ScriptGenerator
from tts_generator import TTSGenerator
from video_downloader import VideoDownloader
from subtitle_generator import SubtitleGenerator
from video_composer import VideoComposer
from youtube_uploader import YouTubeUploader, generate_upload_metadata
from telegram_notifier import TelegramNotifier


def main():
    """메인 실행 함수"""
    
    # ─── Step 0: 초기화 ───
    args = parse_args()
    
    if args.debug:
        setup_logging(level=10)
    
    logger.info("=" * 60)
    logger.info("🧠 뇌를 깨우는 30초 - YouTube Shorts 자동화 v3")
    logger.info("=" * 60)
    
    config_path = args.config
    if config_path:
        config = Config(config_path)
    else:
        config = Config()
    
    language = args.language
    
    if not config.is_channel_enabled(language):
        logger.warning(f"채널이 비활성화 상태입니다: {language}")
        return
    
    if args.weekday is not None:
        weekday = args.weekday
    else:
        weekday = get_weekday()
    
    if args.category and args.category != 'auto':
        category_override = args.category
        for day_num in range(7):
            cat = config.get_today_category(day_num)
            if cat.get('id') == category_override:
                weekday = day_num
                break
    
    category_id = config.get_category_id(weekday)
    category_name = config.get_category_name(weekday, language)
    category_emoji = config.get_category_emoji(weekday)
    
    logger.info(f"📅 날짜: {get_today_str()} ({get_weekday_name_ko()})")
    logger.info(f"🌐 언어: {language}")
    logger.info(f"📂 카테고리: {category_emoji} {category_name} ({category_id})")
    
    output_dir = get_output_dir()
    date_str = get_today_str()
    base_name = f"{date_str}_{language}_{category_id}"
    
    narration_path = str(output_dir / f"{base_name}_narration.mp3")
    bg_dir = str(output_dir / "backgrounds")  # 다중 배경 저장 폴더
    subtitle_path = str(output_dir / f"{base_name}_subtitle.ass")
    output_video_path = str(output_dir / f"{base_name}_final.mp4")
    
    ensure_dir(Path(bg_dir))
    
    notifier = TelegramNotifier(config)
    
    script_data = None
    video_duration = None
    upload_result = None
    
    try:
        # ─── Step 1: 스크립트 생성 ───
        logger.info("")
        logger.info("📝 Step 1: 스크립트 생성 (Gemini)")
        logger.info("-" * 40)
        
        generator = ScriptGenerator(config)
        script_data = generator.generate(
            category_id=category_id,
            weekday=weekday,
            language=language,
        )
        
        logger.info(f"  제목: {script_data.get('title', '')}")
        logger.info(f"  스크립트: {script_data.get('full_script', '')[:80]}...")
        logger.info(f"  자막 세그먼트: {len(script_data.get('subtitle_segments', []))}개")
        
        # 키워드 확인
        search_keywords = script_data.get('search_keywords', [])
        search_keyword = script_data.get('search_keyword', 'abstract background')
        if not search_keywords:
            search_keywords = [search_keyword]
        logger.info(f"  검색 키워드: {search_keywords}")
        
        # ─── Step 2: TTS 음성 생성 ───
        logger.info("")
        logger.info("🔊 Step 2: TTS 음성 생성 (gTTS + 자동 배속)")
        logger.info("-" * 40)
        
        tts = TTSGenerator(config)
        
        tts_result = tts.generate(
            text=script_data['full_script'],
            output_path=narration_path,
            language=language,
            segments=script_data.get('subtitle_segments'),
        )
        
        narration_path = tts_result[0]
        narration_duration = tts_result[1]
        timed_segments = tts_result[2] if len(tts_result) > 2 else None
        
        logger.info(f"  나레이션 길이: {narration_duration:.1f}초")
        if timed_segments:
            logger.info(f"  실측 타이밍: {len(timed_segments)}개 세그먼트")
        
        # ─── Step 3: 배경 영상 다운로드 (다중) ───
        logger.info("")
        logger.info("🎥 Step 3: 배경 영상 다운로드 (Pexels × 3~4개)")
        logger.info("-" * 40)
        
        downloader = VideoDownloader(config)
        
        bg_count = config.get('background', 'count', default=3)
        
        try:
            background_paths = downloader.download_multiple(
                search_keywords=search_keywords,
                output_dir=bg_dir,
                category_id=category_id,
                count=bg_count,
            )
            logger.info(f"  배경 영상: {len(background_paths)}개 다운로드")
        except Exception as e:
            # 다중 다운로드 실패 시 단일 다운로드로 폴백
            logger.warning(f"  다중 다운로드 실패: {e}")
            logger.info("  단일 영상 다운로드로 폴백...")
            single_bg = str(output_dir / f"{base_name}_background.mp4")
            downloader.download(
                search_keyword=search_keywords[0] if search_keywords else 'abstract background',
                output_path=single_bg,
                category_id=category_id,
            )
            background_paths = [single_bg]
        
        # ─── Step 4: 자막 생성 (TTS 타이밍 기반) ───
        logger.info("")
        logger.info("📄 Step 4: 자막 생성 (음성 싱크)")
        logger.info("-" * 40)
        
        sub_gen = SubtitleGenerator(config)
        subtitle_path = sub_gen.generate(
            segments=script_data['subtitle_segments'],
            output_path=subtitle_path,
            language=language,
            total_duration=narration_duration,
            timed_segments=timed_segments,
        )
        
        # ─── Step 5: BGM 선택 ───
        logger.info("")
        logger.info("🎵 Step 5: BGM 선택")
        logger.info("-" * 40)
        
        bgm_config = config.get_bgm_config()
        bgm_dir_path = str(get_project_root() / bgm_config.get('directory', 'assets/music'))
        bgm_path = select_bgm(category_id, bgm_dir_path)
        
        if bgm_path:
            logger.info(f"  BGM: {Path(bgm_path).name}")
        else:
            logger.info("  BGM: 없음 (나레이션만 사용)")
        
        # ─── Step 6: 영상 합성 (다중 배경) ───
        logger.info("")
        logger.info("🎬 Step 6: 영상 합성 (다중 배경 전환)")
        logger.info("-" * 40)
        
        composer = VideoComposer(config)
        output_video_path, video_duration = composer.compose(
            background_paths=background_paths,  # ★ 리스트 전달
            narration_path=narration_path,
            subtitle_path=subtitle_path,
            output_path=output_video_path,
            bgm_path=bgm_path,
            narration_duration=narration_duration,
        )
        
        logger.info(f"  최종 영상: {output_video_path}")
        logger.info(f"  영상 길이: {video_duration:.1f}초")
        
        # ─── Step 7: YouTube 업로드 ───
        if not args.skip_upload and not args.dry_run:
            logger.info("")
            logger.info("📤 Step 7: YouTube 업로드")
            logger.info("-" * 40)
            
            if config.is_youtube_upload_enabled():
                try:
                    uploader = YouTubeUploader(config)
                    
                    if uploader.enabled:
                        metadata = generate_upload_metadata(
                            script_data=script_data,
                            config=config,
                            language=language,
                            weekday=weekday,
                        )
                        
                        logger.info(f"  제목: {metadata['title']}")
                        logger.info(f"  태그: {len(metadata['tags'])}개")
                        
                        upload_result = uploader.upload(
                            video_path=output_video_path,
                            title=metadata['title'],
                            description=metadata['description'],
                            tags=metadata['tags'],
                            language=language,
                        )
                        
                        if upload_result:
                            logger.info(f"  ✅ 업로드 성공: {upload_result['url']}")
                        else:
                            logger.warning("  ⚠️ 업로드 실패 (영상은 생성됨)")
                    else:
                        logger.warning("  ⚠️ YouTube 인증 실패, 업로드 건너뜀")
                        
                except Exception as e:
                    logger.error(f"  ❌ 업로드 오류: {e}")
                    logger.info("  영상은 정상 생성됨, 수동 업로드 가능")
            else:
                logger.info("  YouTube 업로드 비활성화 (수동 업로드 모드)")
        else:
            logger.info("")
            logger.info("⏭️ Step 7: YouTube 업로드 건너뜀")
        
        # ─── Step 8: 텔레그램 알림 ───
        if not args.skip_telegram:
            logger.info("")
            logger.info("📱 Step 8: 텔레그램 알림")
            logger.info("-" * 40)
            
            notifier.send_success(
                video_path=output_video_path,
                script_data=script_data,
                upload_result=upload_result,
                video_duration=video_duration,
                language=language,
                weekday=weekday,
            )
        
        # ─── 완료 ───
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ 모든 작업 완료!")
        logger.info(f"  📝 제목: {script_data.get('title', '')}")
        logger.info(f"  ⏱ 길이: {video_duration:.1f}초")
        logger.info(f"  🎥 배경: {len(background_paths)}개 영상 사용")
        logger.info(f"  📁 파일: {output_video_path}")
        if upload_result:
            logger.info(f"  🔗 URL: {upload_result['url']}")
        logger.info("=" * 60)
        
        # GitHub Actions 출력
        github_output = os.environ.get('GITHUB_OUTPUT')
        if github_output:
            with open(github_output, 'a') as f:
                f.write(f"video_path={output_video_path}\n")
                f.write(f"video_duration={video_duration}\n")
                f.write(f"title={script_data.get('title', '')}\n")
                if upload_result:
                    f.write(f"video_url={upload_result['url']}\n")
        
    except Exception as e:
        logger.error("")
        logger.error("=" * 60)
        logger.error(f"❌ 오류 발생: {e}")
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        
        if not args.skip_telegram:
            try:
                notifier.send_failure(
                    error_message=str(e),
                    language=language,
                    weekday=weekday,
                )
            except Exception:
                logger.error("텔레그램 알림도 실패")
        
        sys.exit(1)


if __name__ == '__main__':
    main()
