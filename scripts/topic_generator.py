#!/usr/bin/env python3
"""소재 생성 배치 스캐폴드 (11.6, U28).

- 필러 정의 + 10.4 경계 규칙 + 기존 소재 210개 전량 + 발행 이력 104건을
  한 컨텍스트에 넣어 중복을 생성 시점에 차단한다.
- 후처리는 E-2(topic_audit) 유사도 재확인 → 통과분만 반영한다.
- 기본값은 드라이런(프롬프트 조립·검증만). 실제 Gemini 호출은 사용자 승인 후
  별도 실행한다. 이 파일의 테스트는 오프라인만 수행한다. (AGENTS.md 2항)

사용법:
    python scripts/topic_generator.py --pillar P1 --need 10        # 드라이런
    python scripts/topic_generator.py --pillar P1 --need 10 --execute  # 승인 후 실실행
"""

import argparse
import json
import re
import sys
from pathlib import Path

from utils import logger, get_project_root

try:
    from topic_audit import sim, tokens as audit_tokens
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False

# ─── 필러 정의 (0920개선사항.md 10.3/11.3) ───
PILLARS = {
    "P1": {
        "name": "다크심리·심리 방어",
        "categories": ["dark"],
        "rule": "타인이 나에게 가하는 심리적 공격과 그 방어만 다룬다. "
                "내가 나를 다루는 문제는 제외한다.",
    },
    "P2": {
        "name": "관계 심리",
        "categories": ["love", "relationship"],
        "rule": "특정 상대와의 관계 안에서 벌어지는 일만 다룬다. "
                "상대가 가해자로 규정되면 P1으로 보낸다.",
    },
    "P3": {
        "name": "자기 조종 (뇌·실행력)",
        "categories": ["success", "brain", "hack"],
        "rule": "나 혼자 있을 때의 뇌·습관·실행력 문제만 다룬다. "
                "타인이 등장하면 P1 또는 P2로 보낸다.",
    },
}

# 미개척 소재 방향 (10.5 P1 확장용)
P1_DIRECTIONS = [
    "협상·거래에서의 심리 우위 (앵커링, 침묵, 양보 설계)",
    "직장 내 권력 관계 (공로 가로채기, 책임 전가, 은근한 배제)",
    "설득 기법의 방어 (문간에 발 들여놓기, 낮은 공 던지기, 희소성 조작)",
    "집단 심리 (동조 압력, 방관자 효과, 집단사고)",
    "온라인·디지털 조작 (가짜 리뷰, 사회적 증거 조작, 다크 패턴)",
    "거짓 탐지의 과학과 그 한계",
]

TOPIC_SIM_LIMIT = 0.55
HOOK_SIM_LIMIT = 0.60


def load_all(topics_path, history_path):
    topics = json.loads(Path(topics_path).read_text(encoding="utf-8"))
    try:
        history = json.loads(Path(history_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history = {}
    return topics, history


def build_context(pillar, topics, history, need):
    """생성 프롬프트 조립 (순수, 오프라인 테스트 가능)."""
    if pillar not in PILLARS:
        raise ValueError(f"unknown pillar: {pillar}")
    p = PILLARS[pillar]
    existing_lines = []
    for cat, entries in topics.items():
        for e in entries:
            existing_lines.append(
                f"- [{cat} no.{e.get('no')}] {e.get('topic')} / {e.get('thumbnail_hook')}")
    published = [t.get("title", "") for t in history.get("topics", [])]
    directions = ""
    if pillar == "P1":
        directions = "\n미개척 방향:\n" + "\n".join(f"- {d}" for d in P1_DIRECTIONS) + "\n"
    prompt = f"""심리학 유튜브 쇼츠 채널의 신규 소재 {need}개를 생성하세요.

필러: {pillar} ({p['name']})
경계 규칙: {p['rule']}
{directions}
금지:
- 기존 소재 210개 및 발행 완료 제목과 소재·숫자·훅이 겹치지 말 것
- 출처가 불확실한 법칙명·효과명을 만들어내지 말 것 (예: 존재하지 않는 "~법칙")
- 한 카테고리 안에서 같은 테마를 쪼개지 말 것

기존 소재 전량:
{chr(10).join(existing_lines)}

발행 완료 제목:
{chr(10).join('- ' + t for t in published)}

출력 (JSON 배열, 항목별 topic/thumbnail_hook/소속필러/판정근거):
"""
    return {
        "pillar": pillar,
        "need": need,
        "existing_count": len(existing_lines),
        "published_count": len(published),
        "prompt_chars": len(prompt),
        "prompt": prompt,
    }


def hook_valid(hook):
    """썸네일 훅 규칙 (6~18자, 서술형 종결 금지)."""
    if not hook or not isinstance(hook, str):
        return False
    flat = hook.replace("\n", "").replace(" ", "")
    if not (6 <= len(flat) <= 18):
        return False
    if flat.rstrip().endswith((".", "!", "~")):
        return False
    return True


def validate_candidates(candidates, topics, history):
    """생성 후보 2차 검수 (E-2 재확인). (accepted, rejected) 반환."""
    existing = [(e.get("topic", ""), e.get("thumbnail_hook", ""))
                for entries in topics.values() for e in entries]
    published = [t.get("title", "") for t in history.get("topics", [])]
    accepted, rejected = [], []
    for c in candidates:
        topic, hook = (c.get("topic") or "").strip(), (c.get("thumbnail_hook") or "").strip()
        reasons = []
        if not topic or not hook_valid(hook):
            reasons.append("형식(빈 주제/훅 규칙 위반)")
        if AUDIT_AVAILABLE and not reasons:
            for et, eh in existing:
                if sim(topic, et) >= TOPIC_SIM_LIMIT or sim(hook, eh) >= HOOK_SIM_LIMIT:
                    reasons.append(f"기존 소재와 유사: '{et[:20]}'")
                    break
            if not reasons:
                for pt in published:
                    if pt and (sim(topic, pt) >= TOPIC_SIM_LIMIT or sim(hook, pt) >= HOOK_SIM_LIMIT):
                        reasons.append(f"발행 제목과 유사: '{pt[:20]}'")
                        break
        if reasons:
            rejected.append({"candidate": c, "reasons": reasons})
        else:
            accepted.append(c)
    return accepted, rejected


def apply_accepted(topics_path, category, accepted):
    """통과분을 topics.json에 반영 (다음 no부터 순번 부여)."""
    path = Path(topics_path)
    topics = json.loads(path.read_text(encoding="utf-8"))
    entries = topics.get(category, [])
    start_no = max([e.get("no", 0) for e in entries] + [0]) + 1
    for i, c in enumerate(accepted):
        entries.append({
            "no": start_no + i,
            "topic": c["topic"],
            "thumbnail_hook": c["thumbnail_hook"],
        })
    topics[category] = entries
    path.write_text(json.dumps(topics, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return start_no


def main():
    parser = argparse.ArgumentParser(description="소재 생성 배치 (11.6)")
    parser.add_argument("--pillar", default="P1", choices=list(PILLARS))
    parser.add_argument("--need", type=int, default=10)
    parser.add_argument("--category", default=None,
                        help="반영 대상 카테고리 (기본: 필러 첫 카테고리)")
    parser.add_argument("--execute", action="store_true",
                        help="실제 Gemini 호출 (사용자 승인 후에만)")
    args = parser.parse_args()

    root = get_project_root()
    topics, history = load_all(root / "config" / "topics.json",
                               root / "history" / "generated_topics.json")
    ctx = build_context(args.pillar, topics, history, args.need)
    logger.info(f"필러 {ctx['pillar']}: 기존 {ctx['existing_count']}개, "
                f"발행 {ctx['published_count']}건, 프롬프트 {ctx['prompt_chars']}자")

    if not args.execute:
        logger.info("드라이런 종료 (실생성은 --execute, 승인 후). API 호출 없음.")
        return 0

    raise SystemExit(
        "실생성은 사용자 승인 후 수행하세요. "
        "Gemini 호출·비용이 발생하므로 AGENTS.md 2항에 따라 별도 승인 필요.")


if __name__ == "__main__":
    sys.exit(main())
