#!/usr/bin/env python3
"""
YouTube 자동 업로드 - v2 (안정화 버전)
"""

import os
import sys
import time
import json
import httplib2
from pathlib import Path

from utils import logger, get_env

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False
    logger.warning("YouTube API 패키지 미설치 - 업로드 불가")


class YouTubeUploader:
    """YouTube 업로드 v2"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/youtube.upload',
    ]
    
    RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
    MAX_RETRIES = 3
    
    def __init__(self, config):
        self.config = config
        self.yt_config = config.get_youtube_config()
        self.enabled = config.is_youtube_upload_enabled()
        self.youtube = None
        
        if not YOUTUBE_API_AVAILABLE:
            logger.warning("YouTube API 패키지 없음, 업로드 비활성화")
            self.enabled = False
            return
        
        if self.enabled:
            self._authenticate()
        
        logger.info(f"YouTubeUploader v2 (활성화: {self.enabled})")
    
    def _authenticate(self):
        """OAuth 인증"""
        client_id = get_env('YOUTUBE_CLIENT_ID')
        client_secret = get_env('YOUTUBE_CLIENT_SECRET')
        refresh_token = get_env('YOUTUBE_REFRESH_TOKEN')
        
        if not all([client_id, client_secret, refresh_token]):
            missing = []
            if not client_id: missing.append('YOUTUBE_CLIENT_ID')
            if not client_secret: missing.append('YOUTUBE_CLIENT_SECRET')
            if not refresh_token: missing.append('YOUTUBE_REFRESH_TOKEN')
            logger.error(f"❌ YouTube 인증 정보 누락: {', '.join(missing)}")
            self.enabled = False
            return
        
        try:
            self.credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                token_uri='https://oauth2.googleapis.com/token',
                scopes=self.SCOPES,
            )
            
            # 토큰 갱신
            logger.info("YouTube OAuth 토큰 갱신 중...")
            self.credentials.refresh(Request())
            
            if not self.credentials.valid:
                raise Exception("토큰 갱신 실패")
            
            # YouTube API 클라이언트 빌드
            self.youtube = build(
                'youtube', 'v3',
                credentials=self.credentials,
                cache_discovery=False,
            )
            
            logger.info("✅ YouTube API 인증 성공")
            
        except Exception as e:
            logger.error(f"❌ YouTube API 인증 실패: {e}")
            logger.error("   → Refresh Token이 만료되었을 수 있습니다.")
            logger.error("   → get_token.py를 다시 실행하세요.")
            self.enabled = False
    
    def upload(self, video_path, title, description, tags=None, 
               language='ko', category_id=None, privacy=None):
        """
        YouTube에 영상 업로드
        
        Returns:
            dict: {'video_id': str, 'url': str, 'title': str, 'privacy': str}
            None: 실패 시
        """
        if not self.enabled or not self.youtube:
            logger.warning("YouTube 업로드 비활성화 상태")
            return None
        
        if not Path(video_path).exists():
            logger.error(f"영상 파일 없음: {video_path}")
            return None
        
        file_size = Path(video_path).stat().st_size / (1024 * 1024)
        logger.info(f"📤 YouTube 업로드 시작")
        logger.info(f"  파일: {Path(video_path).name} ({file_size:.1f}MB)")
        logger.info(f"  제목: {title}")
        
        # 설정
        if privacy is None:
            privacy = self.yt_config.get('privacy', 'public')
        if category_id is None:
            category_id = self.yt_config.get('category_id', '27')
        if tags is None:
            tags = []
        
        made_for_kids = self.yt_config.get('made_for_kids', False)
        notify = self.yt_config.get('notify_subscribers', True)
        
        # 제목 길이 제한 (YouTube: 100자)
        if len(title) > 100:
            title = title[:97] + "..."
        
        # 설명 길이 제한 (YouTube: 5000자)
        if len(description) > 5000:
            description = description[:4997] + "..."
        
        # 태그 정리 (각 태그 500바이트 이하, 총 500개 이하)
        clean_tags = []
        for tag in tags[:500]:
            tag = str(tag).strip()
            if tag and len(tag.encode('utf-8')) <= 500:
                clean_tags.append(tag)
        
        # 요청 본문
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': clean_tags,
                'categoryId': str(category_id),
                'defaultLanguage': language,
                'defaultAudioLanguage': language,
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': made_for_kids,
                'notifySubscribers': notify,
            },
        }
        
        try:
            # 미디어 파일 준비
            media = MediaFileUpload(
                str(video_path),
                mimetype='video/mp4',
                resumable=True,
                chunksize=5 * 1024 * 1024,  # 5MB 청크
            )
            
            # 업로드 요청
            request = self.youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media,
            )
            
            # Resumable 업로드 실행
            response = self._execute_upload(request)
            
            if response:
                video_id = response.get('id', '')
                video_url = f"https://youtube.com/shorts/{video_id}"
                
                result = {
                    'video_id': video_id,
                    'url': video_url,
                    'title': title,
                    'privacy': privacy,
                    'status': 'uploaded',
                }
                
                logger.info(f"✅ YouTube 업로드 성공!")
                logger.info(f"  🔗 {video_url}")
                logger.info(f"  🔒 공개 설정: {privacy}")
                
                return result
            
            logger.error("업로드 응답이 비어있습니다")
            return None
            
        except HttpError as e:
            status = e.resp.status if e.resp else 'unknown'
            logger.error(f"❌ YouTube API 오류 (HTTP {status}): {e}")
            
            if status == 403:
                logger.error("   → 권한 부족: YouTube Data API가 활성화되어 있는지 확인")
                logger.error("   → 또는 일일 업로드 할당량 초과")
            elif status == 401:
                logger.error("   → 인증 만료: Refresh Token을 재발급하세요")
            elif status == 400:
                logger.error(f"   → 잘못된 요청: 제목/설명/태그를 확인하세요")
                logger.error(f"   → 상세: {e.content.decode('utf-8', errors='ignore')[:500]}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 업로드 실패: {e}")
            return None
    
    def _execute_upload(self, request):
        """Resumable 업로드 실행 (재시도 포함)"""
        response = None
        retry = 0
        
        while response is None:
            try:
                status, response = request.next_chunk()
                
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"  📊 업로드 진행: {progress}%")
                    
            except HttpError as e:
                if e.resp and e.resp.status in self.RETRIABLE_STATUS_CODES:
                    retry += 1
                    if retry > self.MAX_RETRIES:
                        logger.error(f"  최대 재시도 횟수 초과 ({self.MAX_RETRIES})")
                        raise
                    
                    wait = min(2 ** retry, 30)
                    logger.warning(f"  재시도 {retry}/{self.MAX_RETRIES} ({wait}초 대기)")
                    time.sleep(wait)
                else:
                    raise
                    
            except (httplib2.HttpLib2Error, IOError) as e:
                retry += 1
                if retry > self.MAX_RETRIES:
                    raise
                
                wait = min(2 ** retry, 30)
                logger.warning(f"  네트워크 오류, 재시도 {retry}/{self.MAX_RETRIES}: {e}")
                time.sleep(wait)
        
        return response


# ─── 메타데이터 생성 함수 ───

def generate_upload_metadata(script_data, config, language='ko', weekday=None):
    """업로드용 메타데이터 생성"""
    
    emoji = config.get_category_emoji(weekday)
    channel_name = config.get_channel_name(language)
    hashtags = config.get_category_hashtags(weekday, language)
    footer = config.get_description_footer(language)
    category_name = config.get_category_name(weekday, language)
    
    title_raw = script_data.get('title', '뇌를 깨우는 30초')
    
    # ─── 제목 ───
    title = f"{emoji} {title_raw} | {channel_name}"
    if len(title) > 100:
        title = f"{emoji} {title_raw}"
    if len(title) > 100:
        title = title[:97] + "..."
    
    # ─── 설명 ───
    desc_body = script_data.get('description', '')
    hook = script_data.get('hook', '')
    
    description = f"""{hook}

{desc_body}

📂 카테고리: {emoji} {category_name}

{footer}

{hashtags}"""
    
    # ─── 태그 ───
    tag_text = hashtags.replace('#', '')
    tags = [t.strip() for t in tag_text.split() if t.strip()]
    
    if language == 'ko':
        base_tags = [
            '심리학', '뇌과학', '자기계발', '뇌를깨우는30초',
            'shorts', '심리', '다크심리학', 'MBTI',
            '동기부여', '성공', '심리테스트', '뇌',
        ]
    else:
        base_tags = [
            'psychology', 'neuroscience', 'selfimprovement',
            '30SecondBrainHack', 'shorts', 'darkpsychology',
            'MBTI', 'motivation', 'brain', 'mindset',
        ]
    
    tags.extend(base_tags)
    
    # 중복 제거 (순서 유지)
    seen = set()
    unique_tags = []
    for tag in tags:
        low = tag.lower()
        if low not in seen:
            seen.add(low)
            unique_tags.append(tag)
    
    return {
        'title': title,
        'description': description,
        'tags': unique_tags,
    }


# ─── CLI 모드 (워크플로우에서 독립 실행용) ───

if __name__ == '__main__':
    import argparse
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import Config
    
    parser = argparse.ArgumentParser(description='YouTube 업로드')
    parser.add_argument('--config', type=str, default=None)
    parser.add_argument('--language', type=str, default='ko')
    parser.add_argument('--video', type=str, help='영상 파일 경로')
    parser.add_argument('--title', type=str, help='제목')
    parser.add_argument('--description', type=str, default='', help='설명')
    parser.add_argument('--privacy', type=str, default=None,
                       choices=['public', 'private', 'unlisted'])
    args = parser.parse_args()
    
    if not args.video:
        print("❌ --video 인자가 필요합니다")
        sys.exit(1)
    
    config = Config(args.config)
    uploader = YouTubeUploader(config)
    
    result = uploader.upload(
        video_path=args.video,
        title=args.title or '뇌를 깨우는 30초',
        description=args.description,
        language=args.language,
        privacy=args.privacy,
    )
    
    if result:
        print(f"✅ 업로드 성공: {result['url']}")
    else:
        print("❌ 업로드 실패")
        sys.exit(1)
