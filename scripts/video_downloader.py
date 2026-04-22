#!/usr/bin/env python3
"""
Pexels/Pixabay 배경 영상 다운로드 - v2 (다중 영상 지원)
"""

import os
import random
import requests
import time
from pathlib import Path
from utils import logger, ensure_dir, get_env

# 카테고리별 기본 키워드 풀 (Gemini 키워드 실패 시 백업)
CATEGORY_KEYWORDS = {
    'money': [
        'money coins close up', 'credit card payment', 'shopping mall crowd',
        'wallet cash', 'stock market graph', 'piggy bank saving',
        'luxury store window', 'receipt bill', 'gold bars wealth'
    ],
    'success': [
        'business success', 'city skyline night', 'mountain top',
        'morning routine', 'running motivation', 'sunrise horizon',
        'chess strategy', 'trophy award', 'confident walk'
    ],
    'brain': [
        'brain scan', 'productivity workspace', 'clock time',
        'focus concentration', 'coffee morning', 'typing keyboard',
        'neuroscience', 'meditation calm', 'light bulb idea'
    ],
    'dark': [
        'dark shadow', 'chess pieces', 'mysterious fog',
        'persuasion handshake', 'mirror reflection', 'crowd people',
        'dark corridor', 'smoke abstract', 'eye shadow'
    ],
    'hack': [
        'self improvement', 'workout exercise', 'journal writing',
        'sunrise motivation', 'running shoes', 'meditation nature',
        'goal planning', 'book reading', 'morning alarm'
    ],
    'love': [
        'couple silhouette sunset', 'romantic city lights', 'coffee date aesthetic',
        'holding hands close up', 'candlelight dinner', 'walking together evening',
        'heart bokeh lights', 'love letter vintage', 'sunset beach couple'
    ],
    'relationship': [
        'couple silhouette', 'conversation cafe', 'holding hands',
        'social connection', 'family together', 'friends laughing',
        'heart love', 'communication talk', 'trust handshake'
    ],
}

# 공통 백업 키워드 (모든 카테고리에서 사용 가능)
UNIVERSAL_KEYWORDS = [
    'abstract dark background', 'cinematic light', 'bokeh lights night',
    'slow motion abstract', 'dark particles', 'neon light abstract',
    'ocean waves calm', 'stars universe', 'rain window'
]


class VideoDownloader:
    """배경 영상 다운로드 v2 - 다중 영상 지원"""
    
    def __init__(self, config):
        self.config = config
        self.bg_config = config.get('background', default={})
        
        self.pexels_key = get_env('PEXELS_API_KEY')
        self.pixabay_key = get_env('PIXABAY_API_KEY', default=None)
        
        logger.info("VideoDownloader v2 초기화 (다중 영상 지원)")
    
    def download_multiple(self, search_keywords, output_dir, category_id=None, count=4):
        """
        여러 배경 영상 다운로드
        
        Args:
            search_keywords: 검색 키워드 리스트 (Gemini 생성)
            output_dir: 저장 디렉토리
            category_id: 카테고리 ID
            count: 목표 다운로드 수
        
        Returns:
            list: 다운로드된 파일 경로 리스트
        """
        ensure_dir(Path(output_dir))
        
        # 키워드 리스트 준비 (Gemini + 카테고리 + 공통)
        all_keywords = self._prepare_keywords(search_keywords, category_id)
        
        logger.info(f"배경 영상 다운로드 시작 (목표: {count}개)")
        logger.info(f"  키워드 풀: {len(all_keywords)}개")
        
        downloaded = []
        used_video_ids = set()  # 중복 방지
        
        for keyword in all_keywords:
            if len(downloaded) >= count:
                break
            
            result = self._download_one(
                keyword, output_dir, len(downloaded),
                used_video_ids=used_video_ids
            )
            
            if result:
                downloaded.append(result['path'])
                used_video_ids.add(result['video_id'])
                logger.info(f"  ✅ [{len(downloaded)}/{count}] '{keyword}' → {Path(result['path']).name}")
            
            time.sleep(0.5)  # API rate limit 방지
        
        # 최소 1개는 있어야 함
        if not downloaded:
            logger.error("배경 영상 다운로드 완전 실패!")
            raise Exception("배경 영상 다운로드 실패: 사용 가능한 영상 없음")
        
        # 부족하면 기존 영상 복사해서 채우기
        while len(downloaded) < 2:
            downloaded.append(downloaded[0])
            logger.info(f"  ♻️ 영상 부족, 첫 번째 영상 재사용")
        
        logger.info(f"배경 영상 다운로드 완료: {len(downloaded)}개")
        return downloaded
    
    def download(self, search_keyword, output_path, category_id=None):
        """
        기존 호환용: 영상 1개 다운로드
        
        Returns:
            str: 다운로드된 파일 경로
        """
        ensure_dir(Path(output_path).parent)
        
        search_terms = self._prepare_keywords([search_keyword], category_id)
        
        for term in search_terms:
            result = self._download_from_pexels(term, output_path)
            if result:
                return result
            time.sleep(1)
        
        if self.pixabay_key:
            for term in search_terms[:3]:
                result = self._download_from_pixabay(term, output_path)
                if result:
                    return result
                time.sleep(1)
        
        logger.error("모든 소스에서 영상 다운로드 실패!")
        raise Exception("배경 영상 다운로드 실패")
    
    def _prepare_keywords(self, search_keywords, category_id=None):
        """검색 키워드 리스트 준비 (중복 제거, 우선순위 정렬)"""
        keywords = []
        seen = set()
        
        # 1순위: Gemini 생성 키워드
        if search_keywords:
            if isinstance(search_keywords, str):
                search_keywords = [search_keywords]
            for kw in search_keywords:
                kw = kw.strip()
                if kw and kw.lower() not in seen:
                    keywords.append(kw)
                    seen.add(kw.lower())
        
        # 2순위: 카테고리별 키워드
        if category_id:
            cat_keywords = CATEGORY_KEYWORDS.get(category_id, [])
            random.shuffle(cat_keywords)
            for kw in cat_keywords:
                if kw.lower() not in seen:
                    keywords.append(kw)
                    seen.add(kw.lower())
        
        # 3순위: config 키워드
        config_terms = self.config.get_search_terms()
        for kw in config_terms:
            if kw.lower() not in seen:
                keywords.append(kw)
                seen.add(kw.lower())
        
        # 4순위: 공통 백업 키워드
        shuffled_universal = UNIVERSAL_KEYWORDS.copy()
        random.shuffle(shuffled_universal)
        for kw in shuffled_universal:
            if kw.lower() not in seen:
                keywords.append(kw)
                seen.add(kw.lower())
        
        return keywords
    
    def _download_one(self, keyword, output_dir, index, used_video_ids=None):
        """
        영상 1개 다운로드 (중복 방지)
        
        Returns:
            dict: {'path': '...', 'video_id': 123} or None
        """
        output_path = str(Path(output_dir) / f"bg_{index:02d}.mp4")
        
        # Pexels
        result = self._download_from_pexels(
            keyword, output_path, 
            exclude_ids=used_video_ids
        )
        if result:
            return result
        
        # Pixabay 백업
        if self.pixabay_key:
            path = self._download_from_pixabay(keyword, output_path)
            if path:
                return {'path': path, 'video_id': f'pixabay_{index}'}
        
        return None
    
    def _download_from_pexels(self, query, output_path, exclude_ids=None):
        """
        Pexels에서 영상 다운로드
        
        Returns:
            dict: {'path': '...', 'video_id': 123} or None
        """
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
            
            logger.info(f"  Pexels 검색: '{query}'")
            response = requests.get(base_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            videos = data.get('videos', [])
            
            if not videos:
                logger.warning(f"  Pexels 검색 결과 없음: '{query}'")
                return None
            
            # 필터링
            min_duration = self.bg_config.get('min_duration', 10)
            suitable = []
            
            for video in videos:
                video_id = video.get('id', 0)
                duration = video.get('duration', 0)
                width = video.get('width', 0)
                height = video.get('height', 0)
                
                # 이미 사용한 영상 제외
                if exclude_ids and video_id in exclude_ids:
                    continue
                
                if duration >= min_duration:
                    is_portrait = height > width
                    suitable.append({
                        'video': video,
                        'video_id': video_id,
                        'portrait': is_portrait,
                        'duration': duration,
                    })
            
            if not suitable:
                suitable = [
                    {
                        'video': v,
                        'video_id': v.get('id', 0),
                        'portrait': True,
                        'duration': v.get('duration', 0),
                    }
                    for v in videos
                    if not (exclude_ids and v.get('id', 0) in exclude_ids)
                ]
            
            if not suitable:
                return None
            
            # 세로 영상 우선 정렬
            suitable.sort(key=lambda x: (x['portrait'], x['duration']), reverse=True)
            
            # 상위 5개 중 랜덤 선택
            top = suitable[:min(5, len(suitable))]
            selected = random.choice(top)
            video_data = selected['video']
            video_id = selected['video_id']
            
            # 다운로드 URL 선택
            video_files = video_data.get('video_files', [])
            download_url = self._select_best_quality(video_files)
            
            if not download_url:
                return None
            
            # 다운로드
            video_response = requests.get(download_url, timeout=120, stream=True)
            video_response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = Path(output_path).stat().st_size / (1024 * 1024)
            logger.info(f"  다운로드 완료: {file_size:.1f}MB (ID: {video_id})")
            
            return {'path': output_path, 'video_id': video_id}
            
        except Exception as e:
            logger.error(f"  Pexels 다운로드 오류: {e}")
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
            
            logger.info(f"  Pixabay 검색: '{query}'")
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            hits = data.get('hits', [])
            
            if not hits:
                return None
            
            selected = random.choice(hits[:5])
            
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
            
            logger.info("  Pixabay 다운로드 완료")
            return output_path
            
        except Exception as e:
            logger.error(f"  Pixabay 다운로드 오류: {e}")
            return None
    
    def _select_best_quality(self, video_files):
        """최적 품질 영상 URL 선택"""
        if not video_files:
            return None
        
        preferred = []
        for vf in video_files:
            height = vf.get('height', 0)
            quality = vf.get('quality', '')
            link = vf.get('link', '')
            
            if not link:
                continue
            
            if height >= 1080 and quality in ['hd', 'sd']:
                preferred.append(vf)
            elif height >= 720:
                preferred.append(vf)
        
        if preferred:
            preferred.sort(key=lambda x: x.get('height', 0), reverse=True)
            return preferred[0].get('link')
        
        for vf in video_files:
            link = vf.get('link', '')
            if link:
                return link
        
        return None
