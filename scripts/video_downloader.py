#!/usr/bin/env python3
"""
Pexels/Pixabay 배경 영상 다운로드
"""

import os
import random
import requests
import time
from pathlib import Path
from utils import logger, ensure_dir, get_env

class VideoDownloader:
    """배경 영상 다운로드"""
    
    def __init__(self, config):
        self.config = config
        self.bg_config = config.get('background', default={})
        
        self.pexels_key = get_env('PEXELS_API_KEY')
        self.pixabay_key = get_env('PIXABAY_API_KEY', default=None)
        
        logger.info("VideoDownloader 초기화")
    
    def download(self, search_keyword, output_path, category_id=None):
        """
        배경 영상 다운로드
        
        Args:
            search_keyword: 검색 키워드
            output_path: 저장 경로
            category_id: 카테고리 ID (검색어 보충용)
        
        Returns:
            str: 다운로드된 파일 경로
        """
        ensure_dir(Path(output_path).parent)
        
        # 검색어 준비
        search_terms = [search_keyword]
        if category_id:
            config_terms = self.config.get_search_terms()
            search_terms.extend(config_terms)
        
        # Pexels 시도
        for term in search_terms:
            result = self._download_from_pexels(term, output_path)
            if result:
                return result
            time.sleep(1)
        
        # Pixabay 백업
        if self.pixabay_key:
            for term in search_terms:
                result = self._download_from_pixabay(term, output_path)
                if result:
                    return result
                time.sleep(1)
        
        logger.error("모든 소스에서 영상 다운로드 실패!")
        raise Exception("배경 영상 다운로드 실패")
    
    def _download_from_pexels(self, query, output_path):
        """Pexels에서 영상 다운로드"""
        if not self.pexels_key:
            logger.warning("Pexels API 키 없음")
            return None
        
        try:
            headers = {'Authorization': self.pexels_key}
            params = {
                'query': query,
                'orientation': self.bg_config.get('orientation', 'portrait'),
                'per_page': self.bg_config.get('per_page', 15),
                'size': 'medium',
            }
            
            base_url = self.bg_config.get('pexels', {}).get(
                'base_url', 'https://api.pexels.com/videos/search'
            )
            
            logger.info(f"Pexels 검색: '{query}'")
            response = requests.get(base_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            videos = data.get('videos', [])
            
            if not videos:
                logger.warning(f"Pexels 검색 결과 없음: '{query}'")
                return None
            
            # 필터링: 최소 길이, 세로 영상 우선
            min_duration = self.bg_config.get('min_duration', 10)
            suitable = []
            
            for video in videos:
                duration = video.get('duration', 0)
                width = video.get('width', 0)
                height = video.get('height', 0)
                
                if duration >= min_duration:
                    # 세로 영상 우선
                    is_portrait = height > width
                    suitable.append({
                        'video': video,
                        'portrait': is_portrait,
                        'duration': duration,
                    })
            
            if not suitable:
                # 길이 제한 완화
                suitable = [{'video': v, 'portrait': True, 'duration': v.get('duration', 0)} 
                           for v in videos]
            
            # 세로 영상 우선 정렬
            suitable.sort(key=lambda x: (x['portrait'], x['duration']), reverse=True)
            
            # 상위 5개 중 랜덤 선택
            top = suitable[:min(5, len(suitable))]
            selected = random.choice(top)['video']
            
            # 다운로드 URL 선택 (HD 품질)
            video_files = selected.get('video_files', [])
            download_url = self._select_best_quality(video_files)
            
            if not download_url:
                logger.warning("다운로드 가능한 파일 없음")
                return None
            
            # 다운로드
            logger.info(f"다운로드 중: {download_url[:80]}...")
            video_response = requests.get(download_url, timeout=120, stream=True)
            video_response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = Path(output_path).stat().st_size / (1024 * 1024)
            logger.info(f"Pexels 다운로드 완료: {file_size:.1f}MB")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Pexels 다운로드 오류: {e}")
            return None
    
    def _download_from_pixabay(self, query, output_path):
        """Pixabay에서 영상 다운로드"""
        if not self.pixabay_key:
            return None
        
        try:
            params = {
                'key': self.pixabay_key,
                'q': query,
                'video_type': 'film',
                'orientation': 'vertical',
                'per_page': 10,
                'safesearch': 'true',
            }
            
            base_url = self.bg_config.get('pixabay', {}).get(
                'base_url', 'https://pixabay.com/api/videos/'
            )
            
            logger.info(f"Pixabay 검색: '{query}'")
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            hits = data.get('hits', [])
            
            if not hits:
                logger.warning(f"Pixabay 검색 결과 없음: '{query}'")
                return None
            
            selected = random.choice(hits[:5])
            
            # medium 품질 URL
            videos = selected.get('videos', {})
            medium = videos.get('medium', {})
            download_url = medium.get('url', '')
            
            if not download_url:
                small = videos.get('small', {})
                download_url = small.get('url', '')
            
            if not download_url:
                return None
            
            video_response = requests.get(download_url, timeout=120, stream=True)
            video_response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info("Pixabay 다운로드 완료")
            return output_path
            
        except Exception as e:
            logger.error(f"Pixabay 다운로드 오류: {e}")
            return None
    
    def _select_best_quality(self, video_files):
        """최적 품질 영상 URL 선택"""
        if not video_files:
            return None
        
        # HD (720p~1080p) 우선
        preferred = []
        for vf in video_files:
            width = vf.get('width', 0)
            height = vf.get('height', 0)
            quality = vf.get('quality', '')
            link = vf.get('link', '')
            
            if not link:
                continue
            
            # 세로 영상: height > width
            if height >= 1080 and quality in ['hd', 'sd']:
                preferred.append(vf)
            elif height >= 720:
                preferred.append(vf)
        
        if preferred:
            # 해상도 순 정렬
            preferred.sort(key=lambda x: x.get('height', 0), reverse=True)
            return preferred[0].get('link')
        
        # 아무거나
        for vf in video_files:
            link = vf.get('link', '')
            if link:
                return link
        
        return None
