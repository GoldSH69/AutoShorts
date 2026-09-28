# -*- coding: utf-8 -*-
"""오프라인 검증: U20 A-6 제목 중복 규칙을 실제 히스토리 제목으로 재생(replay).
외부 API 호출 없음. 리뷰 후 삭제."""
import json, re, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

STOP = frozenset({"이유", "방법", "사람", "진짜", "심리", "것", "수", "오늘", "당신"})
try:
    from topic_audit import STOPWORDS as S2
    STOP = S2
    print('topic_audit.STOPWORDS =', sorted(STOP))
except Exception as e:
    print('topic_audit import 실패 -> 폴백 집합 사용:', e)

h = json.load(open(os.path.join(ROOT, 'history/generated_topics.json'), encoding='utf-8'))


def content_tokens(t):
    return {w for w in re.findall(r'[가-힣a-z]{2,}', t)} - STOP


def number_tokens(t):
    return set(re.findall(
        r'\d+\s*(?:만|시간|초|분|일|주|월|년|%|배|가지|개|명|원|시)|\b\d{2,}\b', t))


def flat(t):
    return re.sub(r'\s+', '', t)


bycat = {}
for r in h['topics']:
    bycat.setdefault(r['category'], []).append(r.get('title', '').lower())


def old_dup(new, olds):
    nw = set(re.findall(r'[가-힣a-z]{2,}', new))
    for o in olds:
        if len(nw & set(re.findall(r'[가-힣a-z]{2,}', o))) >= 3:
            return ('tok3-old', o)
    return None


def new_dup(new, olds):
    nw, nn = content_tokens(new), number_tokens(new)
    for o in olds:
        if flat(o) == flat(new):
            return ('exact', o)
        ov = nw & content_tokens(o)
        if len(ov) >= 3:
            return ('tok3', o, ov)
        if (nn & number_tokens(o)) and len(ov) >= 1:
            return ('num+1tok', o, ov, nn & number_tokens(o))
    return None


tot = old_f = new_f = 0
print('\n--- 같은 카테고리 선행 제목들과 비교 (발행 순서대로 replay) ---')
for c, titles in bycat.items():
    for i, t in enumerate(titles):
        olds = titles[:i]
        if not olds:
            continue
        tot += 1
        o, n = old_dup(t, olds), new_dup(t, olds)
        old_f += bool(o)
        new_f += bool(n)
        if n and not o:
            print(f'  [신규 오탐 후보] {c}: "{t}"\n      -> {n}')
print(f'\n비교 대상 {tot}건: 기존 규칙 {old_f}건 차단, 신규 규칙 {new_f}건 차단')

print('\n--- 숫자 토큰을 가진 발행 제목 분포 ---')
for c, titles in bycat.items():
    withnum = [(t, number_tokens(t)) for t in titles if number_tokens(t)]
    print(f'  {c}: {len(withnum)}/{len(titles)}', [list(x[1]) for x in withnum])
