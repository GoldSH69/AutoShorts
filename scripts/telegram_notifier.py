#!/usr/bin/env python3
"""
텔레그램 알림 - v2 (SNS 캡션 지원)
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from utils import logger, get_env, get_today_str, get_weekday_name_ko

# ─── 블로그 홍보 문구 ───
BLOG_FOOTER_TELEGRAM = "\n🧠 Insight Retreat — 심리 · 운세 · 생활정보 · AI\n👉 https://mindground.org"

class TelegramNotifier:
    """텔레그램 봇 알림 v2 - SNS 캡션 지원"""
    
    def __init__(self, config):
        self.config = config
        self.enabled = config.is_telegram_enabled()
        
        self.bot_token = get_env('TELEGRAM_BOT_TOKEN')
        self.chat_id = get_env('TELEGRAM_CHAT_ID')
        
        if not self.bot_token or not self.chat_id:
            logger.warning("텔레그램 설정 부족, 알림 비활성화")
            self.enabled = False
        
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.tg_config = config.get_telegram_config()
        
        logger.info(f"TelegramNotifier v2 초기화 (활성화: {self.enabled})")
    
    def send_success(self, video_path=None, script_data=None, 
                     upload_result=None, video_duration=None,
                     language='ko', weekday=None, bgm_enabled=True,
                     youtube_metadata=None):
        """성공 알림 전송"""
        if not self.enabled:
            return False
        
        emoji = self.config.get_category_emoji(weekday)
        category_name = self.config.get_category_name(weekday, language)
        title = script_data.get('title', '제목 없음') if script_data else '제목 없음'
        # 개행 등 공백 정규화 (메시지 포맷 보호: \n이 제목/후킹에 섞이지 않도록)
        title = ' '.join(str(title).split())
        
        # 순차 정보 및 썸네일 훅 추출
        no = script_data.get('no', 1) if script_data else 1
        thumbnail_hook = script_data.get('thumbnail_hook', '설정 없음') if script_data else '설정 없음'
        thumbnail_hook = ' '.join(str(thumbnail_hook).split())
        
        # 남은 주제 개수 계산 및 경고 추가
        remaining = 30 - no
        warning_line = ""
        if remaining <= 3:
            warning_line = f"\n⚠️ 경고: [{category_name}] 남은 주제가 {remaining}개뿐입니다. (주제 충전 필요!)\n"
        
        # 업로드 상태
        if upload_result and upload_result.get('video_id'):
            upload_status = f"✅ 자동 업로드 완료 ({upload_result.get('privacy', 'public')})"
            video_url = upload_result.get('url', '')
            link_line = f"🔗 링크: {video_url}"
        elif self.config.is_youtube_upload_enabled():
            upload_status = "❌ 업로드 실패 (수동 업로드 필요)"
            link_line = "📱 Artifacts 또는 아래 영상 파일을 수동 업로드하세요"
        else:
            upload_status = "⏭️ 수동 업로드 모드"
            link_line = "📱 아래 영상 파일을 YouTube에 업로드하세요"
        
        duration_str = f"{video_duration:.1f}초" if video_duration else "확인 불가"
        bgm_str = "🎵 ON" if bgm_enabled else "🔇 OFF (틱톡 호환)"
        
        # 업로드 메타데이터 (수동 업로드용)
        meta_info = ""
        if not upload_result and script_data:
            suggested_title = ""
            suggested_desc = ""
            if youtube_metadata:
                suggested_title = youtube_metadata.get('title', '')
                suggested_desc = youtube_metadata.get('description', '')
            else:
                hashtags = self.config.get_category_hashtags(weekday, language)
                suggested_title = f"{emoji} {title} | {self.config.get_channel_name(language)}"
                suggested_desc = hashtags
                
            meta_info = f"""
📋 수동 업로드 시 사용:
제목: {suggested_title}

설명:
{suggested_desc}"""
        
        message = f"""✅ [뇌를 깨우는 30초] 영상 생성 완료!
 
📅 {get_today_str()} ({get_weekday_name_ko()})
🌐 언어: {'🇰🇷 한국어' if language == 'ko' else '🇺🇸 영어'}
📂 카테고리: {emoji} {category_name} (No. {no})
📝 제목: {title}
🖼️ 썸네일 후킹: {thumbnail_hook}
⏱ 길이: {duration_str}
🎵 BGM: {bgm_str}
📤 업로드: {upload_status}
{link_line}
{meta_info}{warning_line}
{BLOG_FOOTER_TELEGRAM}"""
        
        # ① 메인 상태 메시지 전송
        self._send_message(message)
        
        # ② SNS 캡션 전송 (인스타/틱톡 각각 별도 메시지)
        if script_data:
            self._send_sns_captions(script_data, title)
        
        # ③ 영상 파일 전송 (옵션)
        if (video_path and Path(video_path).exists() 
            and self.tg_config.get('send_video', True)):
            self._send_video(video_path, f"{emoji} {title}")
        
        return True
    
    def _send_sns_captions(self, script_data, title=''):
        """SNS 복사용 캡션을 별도 메시지로 전송"""
        
        ig_caption = script_data.get('instagram_caption', '')
        ig_hashtags = script_data.get('instagram_hashtags', '')
        tk_caption = script_data.get('tiktok_caption', '')
        tk_hashtags = script_data.get('tiktok_hashtags', '')
        
        if not ig_caption and not tk_caption:
            logger.info("SNS 캡션 없음, 건너뜀")
            return
        
        title_prefix = f"{title}\n\n" if title else ""
        
        # ── 인스타그램 메시지 ──
        if ig_caption:
            ig_message = (
                f"{title_prefix}"
                f"{ig_caption}\n\n"
                f"{ig_hashtags}"
            )
            self._send_message(ig_message, parse_mode=None)
            logger.info("인스타그램 캡션 전송 완료")
            time.sleep(0.5)
        
        # ── 틱톡 메시지 ──
        if tk_caption:
            tk_message = (
                f"{title_prefix}"
                f"{tk_caption}\n\n"
                f"{tk_hashtags}"
            )
            self._send_message(tk_message, parse_mode=None)
            logger.info("틱톡 캡션 전송 완료")
    
    def send_failure(self, error_message, language='ko', weekday=None):
        """실패 알림 전송"""
        if not self.enabled:
            return False
        
        category_name = self.config.get_category_name(weekday, language)
        
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        run_id = os.environ.get('GITHUB_RUN_ID', '')
        log_link = ""
        if repo and run_id:
            log_link = f"\n📋 로그: https://github.com/{repo}/actions/runs/{run_id}"
        
        message = f"""🚨 [뇌를 깨우는 30초] 영상 생성 실패!

📅 {get_today_str()} ({get_weekday_name_ko()})
🌐 언어: {'🇰🇷 한국어' if language == 'ko' else '🇺🇸 영어'}
📂 카테고리: {category_name}
❌ 오류: {str(error_message)[:500]}
{log_link}
"""
        
        self._send_message(message)
        return True
    
    def send_custom(self, message):
        """커스텀 메시지 전송"""
        if not self.enabled:
            return False
        return self._send_message(message)
    
    def _send_message(self, text, parse_mode='HTML'):
        """
        텍스트 메시지 전송
        
        Args:
            text: 메시지 텍스트
            parse_mode: 'HTML', 'Markdown', 또는 None (SNS 캡션은 None 권장)
        """
        try:
            max_len = 4096
            if len(text) > max_len:
                text = text[:max_len - 3] + "..."
            
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'disable_web_page_preview': True,
            }
            
            if parse_mode:
                payload['parse_mode'] = parse_mode
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                logger.info("텔레그램 메시지 전송 성공")
                return True
            else:
                if parse_mode == 'HTML' and response.status_code == 400:
                    logger.warning("HTML 파싱 실패, plain text로 재시도")
                    return self._send_message(text, parse_mode=None)
                
                logger.error(f"텔레그램 메시지 전송 실패: {response.status_code}")
                logger.error(response.text)
                return False
                
        except Exception as e:
            logger.error(f"텔레그램 전송 오류: {e}")
            return False
    
    def _send_video(self, video_path, caption=""):
        """영상 파일 전송 (1회 재시도 포함)"""
        try:
            file_size = Path(video_path).stat().st_size / (1024 * 1024)
            
            if file_size > 50:
                logger.warning(f"영상 크기 초과 ({file_size:.1f}MB > 50MB), 파일 전송 건너뜀")
                self._send_message(
                    f"⚠️ 영상 첨부 생략 안내\n"
                    f"영상이 {file_size:.1f}MB로 텔레그램 50MB 제한을 초과해 파일을 첨부하지 못했습니다.\n"
                    f"🔗 위의 YouTube 링크 또는 GitHub Actions Artifacts에서 확인해 주세요."
                )
                return False
            
            url = f"{self.base_url}/sendVideo"
            caption_text = f"🎬 {caption}"[:1024]
            
            max_attempts = 2  # 기본 1회 시도 + 재시도 1회
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.info(f"텔레그램 영상 전송 시도 ({attempt}/{max_attempts})...")
                    with open(video_path, 'rb') as video_file:
                        files = {'video': video_file}
                        data = {
                            'chat_id': self.chat_id,
                            'caption': caption_text,
                            'supports_streaming': True,
                        }
                        
                        response = requests.post(url, data=data, files=files, timeout=120)
                    
                    if response.status_code == 200:
                        logger.info("텔레그램 영상 전송 성공")
                        return True
                    else:
                        logger.warning(f"텔레그램 영상 전송 실패 ({attempt}/{max_attempts}): HTTP {response.status_code} - {response.text[:200]}")
                except requests.exceptions.RequestException as req_err:
                    logger.warning(f"텔레그램 영상 전송 네트워크 오류 ({attempt}/{max_attempts}): {req_err}")
                
                if attempt < max_attempts:
                    logger.info("3초 후 영상 전송을 1회 재시도합니다...")
                    time.sleep(3)
            
            # 2회 시도 모두 실패 시 사용자 안내 메시지 발송
            logger.error("텔레그램 영상 전송 최종 실패 (재시도 포함)")
            repo = os.environ.get('GITHUB_REPOSITORY', '')
            run_id = os.environ.get('GITHUB_RUN_ID', '')
            download_link = f"https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else "GitHub Actions Artifacts"
            
            self._send_message(
                f"⚠️ 영상 파일 첨부 실패 안내\n\n"
                f"텔레그램 서버 통신 지연(타임아웃)으로 영상 전송이 실패했습니다 (재시도 1회 완료).\n\n"
                f"📱 핸드폰 다운로드 링크:\n{download_link}\n\n"
                f"위 링크 하단 'Artifacts'에서 다운로드하시거나, Actions의 'Resend Video to Telegram' 워크플로를 수동 실행해 주세요."
            )
            return False
                
        except Exception as e:
            logger.error(f"텔레그램 영상 전송 처리 중 예외 발생: {e}")
            return False


# ─── CLI 모드 (GitHub Actions에서 직접 호출용) ───
if __name__ == '__main__':
    import argparse
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import Config
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', type=str, default='success')
    parser.add_argument('--config', type=str, default=None)
    parser.add_argument('--error', type=str, default='')
    parser.add_argument('--language', type=str, default='ko')
    parser.add_argument('--video-path', type=str, default=None)
    parser.add_argument('--caption', type=str, default='')
    args = parser.parse_args()
    
    config = Config(args.config)
    notifier = TelegramNotifier(config)
    
    if args.video_path:
        notifier._send_video(args.video_path, args.caption or "재전송 영상")
    elif args.status == 'success':
        notifier.send_custom(f"✅ GitHub Actions 작업 완료 ({get_today_str()})")
    else:
        notifier.send_failure(
            args.error or "알 수 없는 오류",
            language=args.language,
        )
