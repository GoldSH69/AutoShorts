#!/usr/bin/env python3
"""발행 후 성과 수집 (월간 롤링 배치).

- `history/generated_topics.json`에서 video_id가 기록된 영상을 찾는다.
  (video_id는 업로드 성공 시 main.py가 히스토리에 보충 기록한다.)
- 매주 토요일에 최근 30일치(롤링)를 YouTube Analytics API로 조회해
  `history/performance.json`에 누적(덮어쓰기)한다.
- 판단 기준(0920개선사항.md 기준선 5): 시청 vs 스와이프 70% 이상,
  평균 시청률 90% 이상. 스와이프율은 Data/Analytics API로 직접 제공되지
  않으므로 조회·참여·평균시청시간을 수집하고 목표치와 비교한다.
- 발행시각 추정: 히스토리 `date` 당일 `config.yml` 예약 시각(기본 17:55).
  자정 기준 24~48시간 창을 쓰면 예약분(공개 후 약 13~15시간)을
  미성숙 상태로 긁어 0으로 영구 동결하므로, 롤링 30일 + 항상 덮어쓰기로
  성숙치가 들어오면 자동 교정된다. 쇼츠는 수일 내 수치가 굳으므로
  첫7일/누적 구분 없이 공개일~현재 누적치로 단순 비교한다.

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

# 토요일 롤링 배치: 최근 30일치(공개일 기준)를 항상 덮어쓰기 수집.
WINDOW_DAYS = 30
# 예약 발행 시각 (config.yml scheduling.time과 동기화, 폴백값)
DEFAULT_SCHEDULING_TIME = "17:55"

# 0920개선사항.md 기준선 5의 24시간 점검 목표치
TARGET_AVG_VIEW_RATE = 0.90

METRICS = "views,likes,comments,shares,averageViewDuration,estimatedMinutesWatched"


def parse_history_date(date_str):
    """히스토리 날짜(YYYY-MM-DD, KST 자정 기준)를 aware datetime으로."""
    kst = timezone(timedelta(hours=9))
    return datetime.strptime(str(date_str), "%Y-%m-%d").replace(tzinfo=kst)


def get_publish_datetime(date_str, scheduling_time=DEFAULT_SCHEDULING_TIME):
    """히스토리 날짜의 실제 공개시각 추정 (당일 예약 시각, KST).

    업로드는 새벽에 끝나지만 공개는 당일 17:55(private 예약)이므로,
    자정 기준 나이 계산은 공개 후 나이를 약 18시간 부풀린다.
    """
    kst = timezone(timedelta(hours=9))
    try:
        hour, minute = map(int, str(scheduling_time).split(":"))
    except (ValueError, TypeError, AttributeError):
        hour, minute = 17, 55
    return datetime.strptime(str(date_str), "%Y-%m-%d").replace(
        tzinfo=kst, hour=hour, minute=minute, second=0, microsecond=0)


def get_scheduling_time(root):
    """config.yml의 예약 시각을 읽는다 (실패 시 기본값)."""
    try:
        from config_loader import Config
        cfg = Config(str(Path(root) / "config" / "config.yml"))
        return cfg.get("upload", "youtube", "scheduling", "time",
                       default=DEFAULT_SCHEDULING_TIME)
    except Exception:
        return DEFAULT_SCHEDULING_TIME


def select_targets(topics, performance=None, now=None, window_days=WINDOW_DAYS,
                   scheduling_time=DEFAULT_SCHEDULING_TIME):
    """수집 대상 선정 (순수 함수, 오프라인 테스트 가능).

    조건: video_id 있음 + 공개일이 최근 window_days 이내 + 이미 공개됨.
    performance(수집済み)여도 제외하지 않고 항상 포함한다 — 매주 토요일
    덮어쓰기로 성숙치가 들어오면 0이 자동 교정된다.
    performance 인자는 하위호환용으로만 유지한다.
    """
    now = now or get_korea_now()
    cutoff = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")
    targets = []
    for t in topics:
        video_id = (t.get("video_id") or "").strip()
        if not video_id:
            continue
        date_str = str(t.get("date", ""))
        if date_str < cutoff:
            continue
        try:
            publish_at = get_publish_datetime(date_str, scheduling_time)
        except (ValueError, TypeError):
            continue
        if publish_at > now:
            # 아직 공개 전(당일 예약 대기) → 차주에 수집
            continue
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
    """YouTube Analytics API 서비스 생성 (실수집 시에만 호출).

    업로드용 자격증명과 완전 분리한다: 성적 읽기 전용 클라이언트
    (`YOUTUBE_ANALYTICS_CLIENT_ID/SECRET/REFRESH_TOKEN`)가 있으면 그 조를 쓰고,
    없으면 기존 업로드용 조로 폴백한다. 한쪽 고장·만료가 다른 쪽에 번지지
    않게 하는 격리 목적이다.
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    client_id = (get_env("YOUTUBE_ANALYTICS_CLIENT_ID")
                 or get_env("YOUTUBE_CLIENT_ID"))
    client_secret = (get_env("YOUTUBE_ANALYTICS_CLIENT_SECRET")
                     or get_env("YOUTUBE_CLIENT_SECRET"))
    refresh_token = (get_env("YOUTUBE_ANALYTICS_REFRESH_TOKEN")
                     or get_env("YOUTUBE_REFRESH_TOKEN"))
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly"],
    )
    return build("youtubeAnalytics", "v2", credentials=creds)


def fetch_metrics(service, video_id, publish_date=None):
    """단일 영상 지표 조회 (실수집 시에만 호출).

    공개일~현재 누적치로 조회한다. 쇼츠는 수일 내 수치가 굳으므로
    첫7일/누적 구분 없이 단순 비교한다.
    """
    now = get_korea_now()
    start = publish_date or (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    res = service.reports().query(
        ids="channel==MINE",
        startDate=start,
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

    scheduling_time = get_scheduling_time(root)
    now = get_korea_now()
    targets = select_targets(topics, performance, now=now,
                             scheduling_time=scheduling_time)
    logger.info(f"수집 대상 {len(targets)}건 (최근 {WINDOW_DAYS}일 공개분, 항상 덮어쓰기)")
    for t in targets:
        pub = get_publish_datetime(t.get("date", ""), scheduling_time)
        age_days = (now - pub).total_seconds() / 86400
        logger.info(f"  - {t.get('date')} [{t.get('category')} no.{t.get('no')}]"
                    f" {t.get('video_id')} '{t.get('title', '')[:30]}'"
                    f" (공개 {age_days:.1f}일차)")

    if not args.collect:
        logger.info("드라이런 종료 (실수집은 --collect). API 호출 없음.")
        return 0

    service = build_analytics_service()
    entries = []
    for t in targets:
        try:
            e = fetch_metrics(service, t["video_id"],
                              publish_date=str(t.get("date", "")))
            e["publish_at"] = get_publish_datetime(
                t.get("date", ""), scheduling_time).strftime("%Y-%m-%d %H:%M")
            e["window_start"] = str(t.get("date", ""))
            e["window_end"] = now.strftime("%Y-%m-%d")
            entries.append(e)
        except Exception as e:
            logger.warning(f"  수집 실패 {t.get('video_id')}: {e}")
    perf = merge_performance(root / PERFORMANCE_FILE, entries)
    logger.info(f"수집 완료: {len(entries)}건 (누적 {len(perf.get('videos', {}))}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
