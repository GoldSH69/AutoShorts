#!/usr/bin/env python3
"""소재 중복 검수 스크립트 (E-2, U6).

- `config/topics.json` 210개 전량을 읽어 topic/thumbnail_hook 유사도를 계산한다.
- 카테고리 내부 + 카테고리 교차(D-3) 쌍을 모두 보고한다.
- `history/generated_topics.json` 발행 완료 제목과 대조해 D-1 유형(예정과 발행분 유사)도 잡는다.
- 오프라인 동작(표준 라이브러리만 사용). 외부 API 호출 없음.

사용법:
    python scripts/topic_audit.py [--json out.json] [--top-n 50]
종료 코드: 항상 0 (리포트 출력용. 게이트로 쓸 경우 --fail-on-hit 추가)
"""

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOPICS_FILE = PROJECT_ROOT / "config" / "topics.json"
HISTORY_FILE = PROJECT_ROOT / "history" / "generated_topics.json"

TOPIC_SIM_THRESHOLD = 0.55
HOOK_SIM_THRESHOLD = 0.60
TOKEN_OVERLAP_THRESHOLD = 3

# 흔한 조각(A-6 오탐 원인)은 토큰 겹침에서 제외한다.
STOPWORDS = {
    "이유", "방법", "사람", "사람들", "진짜", "정말", "심리", "심리학",
    "뇌", "뇌과학", "돈", "관계", "연애", "성공", "습관", "하루",
    "매달", "오늘", "당신", "것", "수", "때문", "위한", "대한",
    "대해", "하는", "되는", "된다", "있다", "없다", "같은", "다른",
    "자신", "마음", "법", "비밀", "이것", "그것",
}


def normalize(text):
    return re.sub(r"\s+", "", str(text).lower())


def tokens(text):
    return {
        w for w in re.findall(r"[가-힣a-z0-9]{2,}", str(text).lower())
        if w not in STOPWORDS
    }


def sim(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def load_topics():
    data = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    items = []
    for cat, entries in data.items():
        for e in entries:
            items.append({
                "category": cat,
                "no": e.get("no"),
                "topic": e.get("topic", ""),
                "thumbnail_hook": e.get("thumbnail_hook", ""),
            })
    return items


def load_history_titles():
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        {"category": t.get("category"), "no": t.get("no"), "title": t.get("title", "")}
        for t in data.get("topics", [])
        if t.get("title")
    ]


def audit_pairs(items):
    hits = []
    for a, b in combinations(items, 2):
        topic_s = sim(a["topic"], b["topic"])
        hook_s = sim(a["thumbnail_hook"], b["thumbnail_hook"])
        overlap = tokens(a["topic"]) & tokens(b["topic"])
        reasons = []
        if topic_s >= TOPIC_SIM_THRESHOLD:
            reasons.append(f"topic유사도={topic_s:.2f}")
        if hook_s >= HOOK_SIM_THRESHOLD:
            reasons.append(f"hook유사도={hook_s:.2f}")
        if len(overlap) >= TOKEN_OVERLAP_THRESHOLD:
            reasons.append(f"공통토큰={sorted(overlap)}")
        if reasons:
            hits.append({
                "a": f"{a['category']} no.{a['no']}",
                "b": f"{b['category']} no.{b['no']}",
                "cross_category": a["category"] != b["category"],
                "reasons": reasons,
                "topic_a": a["topic"],
                "topic_b": b["topic"],
            })
    return hits


def audit_history(items, history):
    hits = []
    for item in items:
        for h in history:
            s = sim(item["topic"], h["title"])
            hook_s = sim(item["thumbnail_hook"], h["title"])
            if s >= TOPIC_SIM_THRESHOLD or hook_s >= HOOK_SIM_THRESHOLD:
                hits.append({
                    "planned": f"{item['category']} no.{item['no']}",
                    "published": f"{h['category']} no.{h['no']}",
                    "topic_sim": round(s, 2),
                    "hook_sim": round(hook_s, 2),
                    "planned_topic": item["topic"],
                    "published_title": h["title"],
                })
    return hits


def main():
    parser = argparse.ArgumentParser(description="소재 중복 검수 (오프라인)")
    parser.add_argument("--json", default=None, help="결과 JSON 저장 경로")
    parser.add_argument("--top-n", type=int, default=50, help="출력할 쌍 상위 N개")
    parser.add_argument("--fail-on-hit", action="store_true",
                        help="히스토리 충돌이 있으면 종료 코드 1")
    args = parser.parse_args()

    items = load_topics()
    history = load_history_titles()
    pair_hits = audit_pairs(items)
    history_hits = audit_history(items, history)

    pair_hits.sort(key=lambda h: (not h["cross_category"], h["a"], h["b"]))
    cross = sum(1 for h in pair_hits if h["cross_category"])

    print(f"소재 {len(items)}개, 발행이력 {len(history)}건 대조")
    print(f"유사 쌍 {len(pair_hits)}건 (교차 카테고리 {cross}건)")
    for h in pair_hits[:args.top_n]:
        tag = "교차" if h["cross_category"] else "내부"
        print(f"  [{tag}] {h['a']} <-> {h['b']} : {'; '.join(h['reasons'])}")
    print(f"히스토리 충돌(D-1형) {len(history_hits)}건")
    for h in history_hits[:args.top_n]:
        print(f"  {h['planned']}('{h['planned_topic']}')"
              f" <-> 발행 {h['published']}('{h['published_title']}')"
              f" topic={h['topic_sim']} hook={h['hook_sim']}")

    if args.json:
        out = {"pairs": pair_hits, "history_hits": history_hits}
        Path(args.json).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.json}")

    if args.fail_on_hit and history_hits:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
