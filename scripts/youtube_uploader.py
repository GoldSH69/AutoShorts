#!/usr/bin/env python3
"""
YouTube 자동 업로드
"""

import os
import sys
import json
import time
import httplib2
from pathlib import Path

from utils import logger, get_env

# YouTube API imports
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
except ImportError:
    logger.warning("YouTube API 패키지가 설치되지 않았습니다")


class YouTubeUploader:
    """YouTube 업로드"""
    
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    API_SERVICE_NAME = 'youtube'
    API_VERSION = 'v3'
    
    # 재시도 가능한 HTTP 상태 코드
    RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
    MAX_RETRIES = 3
    
    def __init__(self, config):
        self.config = config
        self.yt_config = config.get_youtube_config()
        self.enabled = config.is_youtube_upload_enabled()
        
        if self.enabled:
            self._init_credentials()
        
        logger.info(f"YouTubeUploader 초기화 (활성화: {self.enabled})")
    
    def _init_credentials(self):
        """OAuth 인증 초기화"""
        client_id = get_env('YOUTUBE_CLIENT_ID')
        client_secret = get_env('YOUTUBE_CLIENT_SECRET')
        refresh_token = get_env('YOUTUBE_REFRESH_TOKEN')
        
        if not all([client_id, client_secret, refresh_token]):
            logger.warning("YouTube OAuth 정보 부족, 업로드 비활성화")
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
            self.credentials.refresh(Request())
            
            self.youtube = build(
                self.API_SERVICE_NAME,
                self.API_VERSION,
                credentials=self.credentials,
            )
            
            logger.info("YouTube API 인증 성공")
            
        except Exception as e:
            logger.error(f"YouTube API 인증 실패: {e}")
            self.enabled = False
    
    def upload(self, video_path, title, description, tags=None, 
               language='ko', category_id=None):
        """
        YouTube에 영상 업로드
        
        Args:
            video_path: 영상 파일 경로
            title: 제목
            description: 설명
            tags: 태그 리스트
            language: 언어
            category_id: YouTube 카테고리 ID
        
        Returns:
            dict: 업로드 결과 (video_id, url 등)
        """
        if not self.enabled:
            logger.warning("YouTube 업로드가 비활성화 상태입니다")
            return None
        
        if not Path(video_path).exists():
            logger.error(f"영상 파일 없음: {video_path}")
            return None
        
        # 메타데이터 준비
        privacy = self.yt_config.get('privacy', 'public')
        made_for_kids = self.yt_config.get('made_for_kids', False)
        yt_category_id = category_id or self.yt_config.get('category_id', '27')
        
        if tags is None:
            tags = []
        
        # 제목 길이 제한 (100자)
        if len(title) > 100:
            title = title[:97] + "..."
        
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags[:500],  # 태그 500개 제한
                'categoryId': yt_category_id,
                'defaultLanguage': language,
                'defaultAudioLanguage': language,
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': made_for_kids,
                'shorts': {
                    'allowRemix': True,
                }
            },
        }
        
        logger.info(f"YouTube 업로드 시작: '{title}' ({privacy})")
        
        try:
            media = MediaFileUpload(
                str(video_path),
                mimetype='video/mp4',
                resumable=True,
                chunksize=1024 * 1024,  # 1MB chunks
            )
            
            request = self.youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media,
            )
            
            response = self._resumable_upload(request)
            
            if response:
                video_id = response.get('id', '')
                video_url = f"https://youtube.com/shorts/{video_id}"
                
                logger.info(f"YouTube 업로드 성공: {video_url}")
                
                return {
                    'video_id': video_id,
                    'url': video_url,
                    'title': title,
                    'privacy': privacy,
                }
            
            return None
            
        except HttpError as e:
            logger.error(f"YouTube API 오류: {e}")
            return None
        except Exception as e:
            logger.error(f"YouTube 업로드 실패: {e}")
            return None
    
    def _resumable_upload(self, request):
        """Resumable 업로드 (재시도 포함)"""
        response = None
        retry = 0
        
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"업로드 진행: {progress}%")
                    
            except HttpError as e:
                if e.resp.status in self.RETRIABLE_STATUS_CODES:
                    retry += 1
                    if retry > self.MAX_RETRIES:
                        logger.error("최대 재시도 횟수 초과")
                        raise
                    
                    wait_time = 2 ** retry
                    logger.warning(f"재시도 {retry}/{self.MAX_RETRIES} ({wait_time}초 대기)")
                    time.sleep(wait_time)
                else:
                    raise
                    
            except Exception as e:
                retry += 1
                if retry > self.MAX_RETRIES:
                    raise
                
                wait_time = 2 ** retry
                logger.warning(f"오류 재시도 {retry}/{self.MAX_RETRIES}: {e}")
                time.sleep(wait_time)
        
        return response


def generate_upload_metadata(script_data, config, language='ko', weekday=None):
    """업로드용 메타데이터 생성"""
    
    emoji = config.get_category_emoji(weekday)
    channel_name = config.get_channel_name(language)
    hashtags = config.get_category_hashtags(weekday, language)
    footer = config.get_description_footer(language)
    
    title_raw = script_data.get('title', '뇌를 깨우는 30초')
    
    # 제목 형식
    title = f"{emoji} {title_raw} | {channel_name}"
    if len(title) > 100:
        title = f"{emoji} {title_raw}"[:100]
    
    # 설명
    desc_body = script_data.get('description', '')
    description = f"""{desc_body}

{footer}

{hashtags}"""
    
    # 태그
    tag_text = hashtags.replace('#', '')
    tags = [t.strip() for t in tag_text.split() if t.strip()]
    
    if language == 'ko':
        tags.extend(['심리학', '뇌과학', '자기계발', '뇌를깨우는30초', 'shorts'])
    else:
        tags.extend(['psychology', 'neuroscience', 'selfimprovement', '30SecondBrainHack', 'shorts'])
    
    # 중복 제거
    tags = list(dict.fromkeys(tags))
    
    return {
        'title': title,
        'description': description,
        'tags': tags,
    }
