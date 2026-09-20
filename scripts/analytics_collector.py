#!/usr/bin/env python3
"""발행 후 성과 수집 스켈레톤 (E-1, U9).

- `history/generated_topics.json`에서 video_id가 기록된 영상을 찾는다.
  (video_id는 업로드 성공 시 main.py가 히스토리에 보충 기록한다. U9 이전
  발행분에는 video_id가 없어 수집 대상에서 제외된다.)
- 발행 후 24~48시간 경과분을 YouTube Analytics API로 조회해
  `history/performance.json`에 누적한다.
- 판단 기준(0920개선사항.md 기준선 5): 시청 vs 스와이프 70% 이상,
  평균 시청률 90% 이상. 스와이프율은 Data/Analytics API로 직접 제공되지
  않으므로 조회·참여·평균시청시간을 수집하고 목표치와 비교한다.

사용법:
    python scripts/analytics_collector.py            # 드라이런 (대상 목록만)
    python scripts/analytics_collector.py --collect  # 실제 수집 (API 호출)

주의: 실제 수집은 YouTube Analytics API(`youtubeAnalytics.reports.query`)를
호출한다. OAuth 범위에 `yt-analytics.readonly`가 필요하므로 기존 토큰은
재동의가 필요하다. 할당량 보호를 위해 기본값은 드라이런이다.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils import logger, get_project_root, get_korea_now, get_env

HISTORY_FILE = "history/generated_topics.json"
PERFORMANCE_FILE = "history/performance.json"

MIN_AGE_HOURS = 24
MAX_AGE_HOURS = 48

# 0920개선사항.md 기준선 5의 24시간 점검 목표치
TARGET_AVG_VIEW_RATE = 0.90

METRICS = "views,likes,comments,shares,averageViewDuration,estimatedMinutesWatched"


def parse_history_date(date_str):
    """히스토리 날짜(YYYY-MM-DD, KST 자정 기준)를 aware datetime으로."""
    kst = timezone(timedelta(hours=9))
    return datetime.strptime(str(date_str), "%Y-%m-%d").replace(tzinfo=kst)


def select_targets(topics, performance, now=None):
    """수집 대상 선정 (순수 함수, 오프라인 테스트 가능).

    조건: video_id 있음 + 발행 후 24~48시간 + 아직 미수집.
    """
    now = now or get_korea_now()
    collected = set((performance or {}).get("videos", {}).keys())
    targets = []
    for t in topics:
        video_id = (t.get("video_id") or "").strip()
        if not video_id or video_id in collected:
            continue
        try:
            age = now - parse_history_date(t.get("date", ""))
        except (ValueError, TypeError):
            continue
        if timedelta(hours=MIN_AGE_HOURS) <= age <= timedelta(hours=MAX_AGE_HOURS):
            targets.append(t)
    return targets


def summarize(entry):
    """단일 수집 결과를 목표치와 비교한 요약 (순수 함수)."""
    avg_dur = float(entry.get("averageViewDuration") or 0)
    duration = float(entry.get("videoDuration") or 0)
    rate = (avg_dur / duration) if duration > 0 else None
    return {
        "video_id": entry.get("video_id"),
        "views": entry.get("views"),
        "avg_view_duration": avg_dur,
        "avg_view_rate": round(rate, 3) if rate is not None else None,
        "meets_avg_view_rate": (rate >= TARGET_AVG_VIEW_RATE) if rate is not None else None,
    }


def merge_performance(performance_path, entries, fetched_at=None):
    """수집 결과를 performance.json에 병합 (API 호출 없음)."""
    path = Path(performance_path)
    try:
        perf = json_load(path)
    except (OSError, ValueError):
        perf = {}
    perf.setdefault("videos", {})
    fetched_at = fetched_at or get_korea_now().strftime("%Y-%m-%d %H:%M")
    for e in entries:
        vid = e.get("video_id")
        if not vid:
            continue
        record = dict(e)
        record["fetched_at"] = fetched_at
        record["summary"] = summarize(e)
        perf["videos"][vid] = record
    perf["last_updated"] = fetched_at
    json_dump(path, perf)
    return perf


def json_load(path):
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_dump(path, data):
    import json
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_analytics_service():
    """YouTube Analytics API 서비스 생성 (실수집 시에만 호출)."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=get_env("YOUTUBE_REFRESH_TOKEN"),
        client_id=get_env("YOUTUBE_CLIENT_ID"),
        client_secret=get_env("YOUTUBE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly"],
    )
    return build("youtubeAnalytics", "v2", credentials=creds)


def fetch_metrics(service, video_id):
    """단일 영상 지표 조회 (실수집 시에만 호출)."""
    now = get_korea_now()
    res = service.reports().query(
        ids="channel==MINE",
        startDate=(now - timedelta(days=7)).strftime("%Y-%m-%d"),
        endDate=now.strftime("%Y-%m-%d"),
        metrics=METRICS,
        filters=f"video=={video_id}",
    ).execute()
    rows = res.get("rows") or []
    if not rows:
        return {"video_id": video_id}
    headers = [h["name"] for h in res.get("columnHeaders", [])]
    entry = dict(zip(headers, rows[0]))
    entry["video_id"] = video_id
    return entry


def main():
    parser = argparse.ArgumentParser(description="발행 후 성과 수집 (E-1)")
    parser.add_argument("--collect", action="store_true",
                        help="실제 API 수집 수행 (기본: 드라이런)")
    args = parser.parse_args()

    root = get_project_root()
    history = json_load(root / HISTORY_FILE)
    try:
        performance = json_load(root / PERFORMANCE_FILE)
    except (OSError, ValueError):
        performance = {}

    topics = history.get("topics", [])
    with_id = sum(1 for t in topics if (t.get("video_id") or "").strip())
    logger.info(f"히스토리 {len(topics)}건 중 video_id 기록 {with_id}건")

    targets = select_targets(topics, performance)
    logger.info(f"수집 대상 {len(targets)}건 (발행 후 {MIN_AGE_HOURS}~{MAX_AGE_HOURS}시간, 미수집)")
    for t in targets:
        logger.info(f"  - {t.get('date')} [{t.get('category')} no.{t.get('no')}]"
                    f" {t.get('video_id')} '{t.get('title', '')[:30]}'")

    if not args.collect:
        logger.info("드라이런 종료 (실수집은 --collect). API 호출 없음.")
        return 0

    service = build_analytics_service()
    entries = []
    for t in targets:
        try:
            entries.append(fetch_metrics(service, t["video_id"]))
        except Exception as e:
            logger.warning(f"  수집 실패 {t.get('video_id')}: {e}")
    perf = merge_performance(root / PERFORMANCE_FILE, entries)
    logger.info(f"수집 완료: {len(entries)}건 (누적 {len(perf.get('videos', {}))}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
