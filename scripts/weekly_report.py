#!/usr/bin/env python3
"""주간 성적표 (P0 성과 루프의 사람-facing 출력).

- `history/generated_topics.json` + `history/performance.json`을 읽어
  주간 TOP3·카테고리 평균·경고·리믹스 후보를 계산한다 (고정 규칙, 판단 없음).
- 기본은 화면 출력(드라이런). `--send`를 붙이면 텔레그램으로 전송한다.
- 수집 데이터가 없으면 "수집 데이터 없음" 안내만 낸다 (리턴 0).
- 외부 API 호출 없음 (읽는 건 로컬 JSON, 보내는 건 텔레그램뿐).
"""

import argparse
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import logger, get_project_root, get_korea_now  # noqa: E402

HISTORY_FILE = "history/generated_topics.json"
PERFORMANCE_FILE = "history/performance.json"
TOPICS_FILE = "config/topics.json"

# 제목 겹침 계산에서 제외할 흔한 단어
TITLE_STOPWORDS = frozenset({
    "이유", "방법", "사람", "진짜", "심리", "것", "수", "오늘", "당신",
    "영상", "이야기", "때문",
})


def load_json(path):
    try:
        import json
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def title_tokens(text):
    """제목 핵심어 (2자 이상 한글·영문, 불용어 제외)."""
    return {w for w in re.findall(r'[가-힣a-z]{2,}', str(text).lower())} - TITLE_STOPWORDS


def build_report(history_path, performance_path, topics_path, now=None):
    """성적표 텍스트 생성 (순수 계산, 입출력 없음)."""
    now = now or get_korea_now()
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    history = load_json(history_path)
    performance = load_json(performance_path)
    videos = (performance or {}).get("videos", {})

    by_id = {}
    for t in (history or {}).get("topics", []):
        vid = (t.get("video_id") or "").strip()
        if vid:
            by_id[vid] = t

    if not videos or not by_id:
        return ("📊 주간 성적표\n"
                "수집 데이터 없음 (토큰 재동의 후 기록 시작).\n"
                "재동의 전에도 리포트는 매주 오되 내용 없이 끝남.")

    # 이번 주(최근 7일) 수집분만 집계
    rows = []
    for vid, e in videos.items():
        t = by_id.get(vid)
        if not t or str(t.get("date", "")) < week_ago:
            continue
        views = int(e.get("views") or 0)
        likes = int(e.get("likes") or 0)
        comments = int(e.get("comments") or 0)
        avg_sec = float(e.get("averageViewDuration") or 0)
        eng = (likes + comments) / views if views > 0 else 0.0
        rows.append({
            "video_id": vid, "views": views, "likes": likes,
            "comments": comments, "avg_sec": avg_sec, "eng": eng,
            "date": t.get("date", ""), "category": t.get("category", ""),
            "no": t.get("no", ""), "title": t.get("title", ""),
        })
    rows.sort(key=lambda r: r["views"], reverse=True)

    if not rows:
        return ("📊 주간 성적표\n"
                "최근 7일 수집분 없음 (발행 후 24~48시간 뒤부터 쌓임).")

    lines = [f"📊 주간 성적표 ({week_ago}~{now.strftime('%Y-%m-%d')})"]
    for i, r in enumerate(rows[:3], 1):
        medal = ["🥇", "🥈", "🥉"][i - 1]
        lines.append(
            f"{medal} {r['category']} no.{r['no']} — "
            f"{r['views']:,}회 / 평균 {r['avg_sec']:.1f}초 / 댓글 {r['comments']}")

    # 카테고리 평균 (조회수)
    cats = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r["views"])
    cat_line = " / ".join(
        f"{c} 평균 {sum(v) // len(v):,}회" for c, v in sorted(cats.items()))
    lines.append(f"📂 {cat_line}")

    # 경고: 최근 3편 평균이 직전 3편 절반 이하 → 노출 하락
    by_date = sorted(rows, key=lambda r: r["date"], reverse=True)
    if len(by_date) >= 4:
        recent = sum(r["views"] for r in by_date[:3]) / 3
        prev = sum(r["views"] for r in by_date[3:6]) / max(1, len(by_date[3:6]))
        if prev > 0 and recent < prev / 2:
            lines.append("⚠️ 노출 하락 (최근 3편 평균이 직전 절반 이하)")
    # 경고: 댓글 0이 3편 연속 → 참여 저조
    if len(by_date) >= 3 and all(r["comments"] == 0 for r in by_date[:3]):
        lines.append("⚠️ 참여 저조 (댓글 0이 3편 연속)")

    # 리믹스 후보: 주간 1등과 같은 카테고리 미발행분 중 제목 겹침 상위 3개
    winner = rows[0]
    w_tokens = title_tokens(winner["title"])
    published_nos = {str(t.get("no")) for t in (history or {}).get("topics", [])
                     if t.get("category") == winner["category"]}
    topics = load_json(topics_path)
    cands = []
    for it in (topics or {}).get(winner["category"], []):
        if str(it.get("no")) in published_nos:
            continue
        overlap = w_tokens & title_tokens(it.get("topic", ""))
        cands.append((len(overlap), it.get("no"), it.get("topic", "")))
    cands.sort(key=lambda c: (-c[0], c[1]))
    if cands:
        picks = " / ".join(f"{winner['category']} no.{no}" for _, no, _ in cands[:3])
        lines.append(f"🔁 리믹스 후보(1등과 같은 뼈대): {picks}")
        lines.append("   → 번호 하나만 고르면 다음 발행順에 반영")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="주간 성적표 (P0)")
    parser.add_argument("--send", action="store_true",
                        help="텔레그램으로 실제 전송 (기본: 화면 출력만)")
    parser.add_argument("--history-file", default=None)
    parser.add_argument("--performance-file", default=None)
    parser.add_argument("--topics-file", default=None)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    root = get_project_root()
    report = build_report(
        args.history_file or str(root / HISTORY_FILE),
        args.performance_file or str(root / PERFORMANCE_FILE),
        args.topics_file or str(root / TOPICS_FILE),
    )
    print(report)

    if not args.send:
        logger.info("드라이런 종료 (전송은 --send).")
        return 0

    from config_loader import Config
    from telegram_notifier import TelegramNotifier
    config = Config(args.config)
    notifier = TelegramNotifier(config)
    if notifier.send_custom(f"📊 [뇌를 깨우는 30초] 주간 성적표\n\n{report}"):
        logger.info("주간 성적표 전송 완료")
    else:
        logger.warning("주간 성적표 전송 실패/비활성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
