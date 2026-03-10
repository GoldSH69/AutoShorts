#!/usr/bin/env python3
"""
텔레그램 알림
"""

import os
import sys
import json
import requests
from pathlib import Path
from utils import logger, get_env, get_today_str, get_weekday_name_ko

class TelegramNotifier:
    """텔레그램 봇 알림"""
    
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
        
        logger.info(f"TelegramNotifier 초기화 (활성화: {self.enabled})")
    
    def send_success(self, video_path=None, script_data=None, 
                     upload_result=None, video_duration=None,
                     language='ko', weekday=None):
        """성공 알림 전송"""
        if not self.enabled:
            return False
        
        emoji = self.config.get_category_emoji(weekday)
        category_name = self.config.get_category_name(weekday, language)
        title = script_data.get('title', '제목 없음') if script_data else '제목 없음'
        
        # 업로드 상태
        if upload_result:
            upload_status = f"✅ 완료 ({upload_result.get('privacy', '')})"
            video_url = upload_result.get('url', '')
            link_line = f"🔗 링크: {video_url}"
        else:
            upload_status = "⏭️ 수동 업로드 대기"
            link_line = "📱 텔레그램에서 영상 확인 후 수동 업로드하세요"
        
        duration_str = f"{video_duration:.1f}초" if video_duration else "확인 불가"
        
        message = f"""✅ [뇌를 깨우는 30초] 영상 생성 완료!

📅 {get_today_str()} ({get_weekday_name_ko()})
🌐 언어: {'🇰🇷 한국어' if language == 'ko' else '🇺🇸 영어'}
📂 카테고리: {emoji} {category_name}
📝 제목: {title}
⏱ 길이: {duration_str}
📤 업로드: {upload_status}
{link_line}
"""
        
        # 텍스트 메시지 전송
        self._send_message(message)
        
        # 영상 파일 전송 (옵션)
        if (video_path and Path(video_path).exists() 
            and self.tg_config.get('send_video', True)):
            self._send_video(video_path, title)
        
        return True
    
    def send_failure(self, error_message, language='ko', weekday=None):
        """실패 알림 전송"""
        if not self.enabled:
            return False
        
        category_name = self.config.get_category_name(weekday, language)
        
        # GitHub Actions 로그 링크
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
    
    def _send_message(self, text):
        """텍스트 메시지 전송"""
        try:
            max_len = self.tg_config.get('max_caption_length', 1024)
            if len(text) > max_len:
                text = text[:max_len-3] + "..."
            
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            }
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                logger.info("텔레그램 메시지 전송 성공")
                return True
            else:
                logger.error(f"텔레그램 메시지 전송 실패: {response.status_code}")
                logger.error(response.text)
                return False
                
        except Exception as e:
            logger.error(f"텔레그램 전송 오류: {e}")
            return False
    
    def _send_video(self, video_path, caption=""):
        """영상 파일 전송"""
        try:
            # 파일 크기 확인 (텔레그램 제한: 50MB)
            file_size = Path(video_path).stat().st_size / (1024 * 1024)
            
            if file_size > 50:
                logger.warning(f"영상 크기 초과 ({file_size:.1f}MB > 50MB), 파일 전송 건너뜀")
                return False
            
            url = f"{self.base_url}/sendVideo"
            
            caption_text = f"🎬 {caption}"[:1024]
            
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
                logger.error(f"텔레그램 영상 전송 실패: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"텔레그램 영상 전송 오류: {e}")
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
    args = parser.parse_args()
    
    config = Config(args.config)
    notifier = TelegramNotifier(config)
    
    if args.status == 'success':
        notifier.send_custom(f"✅ GitHub Actions 작업 완료 ({get_today_str()})")
    else:
        notifier.send_failure(
            args.error or "알 수 없는 오류",
            language=args.language,
        )
