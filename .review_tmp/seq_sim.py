# -*- coding: utf-8 -*-
"""오프라인 검증: U29 요일 재배치 후 순번 추적(_select_sequential_topic) 재생.

- 외부 API 호출 없음: google.generativeai 모듈을 스텁으로 대체하고
  read_json/write_json을 인메모리로 교체하므로 실제 히스토리 파일도 건드리지 않는다.
- 리뷰 후 삭제.
"""
import copy
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.environ.setdefault('GEMINI_API_KEY', 'offline-review-stub')

# ── google.generativeai 스텁 (네트워크/SDK 로드 차단) ──
stub = types.ModuleType('google.generativeai')
stub.configure = lambda **kw: None
stub.GenerativeModel = object
google_pkg = types.ModuleType('google')
google_pkg.generativeai = stub
sys.modules.setdefault('google', google_pkg)
sys.modules['google.generativeai'] = stub

import script_generator as sg  # noqa: E402
from config_loader import Config  # noqa: E402

cfg = Config(os.path.join(ROOT, 'config', 'config.yml'))

print('=== 요일 → 카테고리 매핑 (config.yml) ===')
dow = ['월', '화', '수', '목', '금', '토', '일']
mapping = {}
for wd in range(7):
    cid = cfg.get_category_id(wd)
    mapping[wd] = cid
    print(f'  {dow[wd]}({wd}) -> {cid}')
from collections import Counter  # noqa: E402
cnt = Counter(mapping.values())
print('  주간 배분:', dict(cnt), '| 총', sum(cnt.values()), '일')
all_cats = set(json.load(open(os.path.join(ROOT, 'config/topics.json'), encoding='utf-8')).keys())
print('  휴면(요일 미배정) 카테고리:', sorted(all_cats - set(mapping.values())))

# ── 인메모리 히스토리로 교체 ──
real_hist = json.load(open(os.path.join(ROOT, 'history/generated_topics.json'), encoding='utf-8'))
MEM = {'h': copy.deepcopy(real_hist)}
_real_read_json = sg.read_json


def fake_read(p, *a, **k):
    if 'generated_topics' in str(p):
        return MEM['h']
    return _real_read_json(p, *a, **k)


sg.read_json = fake_read
WRITES = []


def fake_write(p, data):
    WRITES.append(str(p))
    MEM['h'] = copy.deepcopy(data)
    return True


sg.write_json = fake_write
sg.get_today_str = lambda: 'SIM'

gen = sg.ScriptGenerator(cfg)

# 로그 소음 제거
sg.logger.info = lambda *a, **k: None
sg.logger.warning = lambda *a, **k: print('   [warn]', *a)

print('\n=== 시작 시점: 카테고리별 마지막 no (실제 히스토리) ===')
start = {}
for c in sorted(set(mapping.values())):
    same = [t for t in MEM['h']['topics'] if t.get('category') == c]
    start[c] = same[-1]['no'] if same else 0
    print(f'  {c}: last_no={start[c]}, 총소재={len(gen.topics_data.get(c, []))}개')

print('\n=== 12주(84일) 시뮬레이션: 요일 순서대로 생성→히스토리 저장 반복 ===')
seen = {}
wrap_events = []
repub = []
for day in range(84):
    wd = day % 7
    cid = mapping[wd]
    no, topic, hook = gen._select_sequential_topic(cid)
    week = day // 7 + 1
    prev = seen.setdefault(cid, [])
    if no in prev:
        repub.append((week, dow[wd], cid, no, topic))
    if prev and no < prev[-1]:
        wrap_events.append((week, dow[wd], cid, prev[-1], no))
    prev.append(no)
    gen._save_history(cid, {'title': f'sim-{cid}-{no}', 'full_script': 'x', 'no': no})

for c in sorted(seen):
    nos = seen[c]
    gaps = [b - a for a, b in zip(nos, nos[1:])]
    print(f'  {c}: {len(nos)}회 실행, no {nos[0]}→{nos[-1]}, '
          f'증가폭 집합={sorted(set(gaps))}, 리셋={ "있음" if any(g<0 for g in gaps) else "없음" }')

print('\n  순환(소진) 이벤트:', wrap_events if wrap_events else '없음')
print('  이미 이번 시뮬 내에서 재사용된 소재:', repub if repub else '없음')
print(f'\n  (히스토리 파일 실제 쓰기 0건 보장: write 호출 {len(WRITES)}건 모두 인메모리)')

print('\n=== 소진 시점 계산 (시작 last_no 기준, 30개 소재) ===')
for c in sorted(set(mapping.values())):
    per_week = cnt[c]
    remain = 30 - start[c]
    print(f'  {c}: 남은 {remain}개 / 주 {per_week}회 = {remain/per_week:.1f}주 후 1번으로 순환')
