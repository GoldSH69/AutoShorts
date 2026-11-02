#!/usr/bin/env python3
"""주제 재고 계산 공통 모듈.

`config/topics.json`의 전체 주제 수와 `history/generated_topics.json`의
발행 번호를 대조해 실제 남은 주제 수를 계산한다.

기존 텔레그램 알림의 `remaining = 30 - no`처럼 카테고리 총량을 하드코딩하지
않고, 카테고리별 실제 재고를 사용하기 위한 읽기 전용 유틸리티다.
"""

import json
from pathlib import Path

from utils import get_project_root

TOPICS_FILE = "config/topics.json"
HISTORY_FILE = "history/generated_topics.json"


def _load_json(path):
    """JSON 파일을 읽고, 없거나 깨졌으면 빈 dict를 반환한다."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_topic_inventory(category_id, root=None):
    """카테고리의 (전체, 사용, 남음) 주제 수를 반환한다.

    Args:
        category_id: `relationship`, `love`, `dark`, `brain` 등 topics.json 키.
        root: 프로젝트 루트. 생략 시 `utils.get_project_root()` 사용.

    Returns:
        tuple[int, int, int]: (total, used, remaining)
    """
    root = Path(root) if root else get_project_root()
    topics = _load_json(root / TOPICS_FILE)
    history = _load_json(root / HISTORY_FILE)

    items = topics.get(category_id, []) or []
    total = len(items)

    used_numbers = set()
    for record in history.get("topics", []) or []:
        if record.get("category") != category_id:
            continue
        try:
            number = int(record.get("no"))
        except (TypeError, ValueError):
            continue
        if 1 <= number <= total:
            used_numbers.add(number)

    used = len(used_numbers)
    remaining = max(0, total - used)
    return total, used, remaining


def get_all_topic_inventory(root=None):
    """모든 카테고리의 재고를 dict로 반환한다."""
    root = Path(root) if root else get_project_root()
    topics = _load_json(root / TOPICS_FILE)
    return {
        category_id: get_topic_inventory(category_id, root=root)
        for category_id in topics.keys()
    }


if __name__ == "__main__":
    for category_id, (total, used, remaining) in get_all_topic_inventory().items():
        print(f"{category_id}: {remaining}/{total} 남음 (사용 {used})")
