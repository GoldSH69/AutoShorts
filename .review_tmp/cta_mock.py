# -*- coding: utf-8 -*-
"""오프라인 mock 검증: U2(A-2/A-7) CTA 판정 로직 실제 코드 경로 재생.
외부 API 호출 없음(SDK 스텁). 리뷰 후 삭제."""
import os
import sys
import types

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.environ.setdefault('GEMINI_API_KEY', 'offline-review-stub')

stub = types.ModuleType('google.generativeai')
stub.configure = lambda **kw: None
stub.GenerativeModel = object
gp = types.ModuleType('google')
gp.generativeai = stub
sys.modules.setdefault('google', gp)
sys.modules['google.generativeai'] = stub

import script_generator as sg  # noqa: E402
from config_loader import Config  # noqa: E402

cfg = Config(os.path.join(ROOT, 'config', 'config.yml'))
sg.write_json = lambda *a, **k: True          # 히스토리 파일 보호
gen = sg.ScriptGenerator(cfg)
gen.selected_no = 7
gen.selected_thumbnail_hook = '테스트 후킹 문구'
sg.logger.info = lambda *a, **k: None
sg.logger.warning = lambda *a, **k: print('     [warn]', *a)

FILLER = ('밤 11시에 배달앱을 켰다가 장바구니에 3만 원을 담고 결제 직전에 멈춘 적이 있으신가요. '
          '뇌는 지불의 고통을 느끼면 소비를 미룹니다. 카드 결제는 그 고통 신호를 흐리게 만듭니다. '
          '그래서 결제 버튼을 누르기 전에 딱 10초만 눈을 감고 내일 아침에도 이게 필요할지 물어보세요. '
          '이 10초가 한 달 지출을 눈에 보이게 줄여줍니다. 작은 멈춤이 소비 습관을 바꿉니다. ')

CASES = [
    ('① 정상: 나레이션 CTA 1문장 + comment_cta 분리',
     FILLER + '여러분은 어느 쪽인가요? 그렇게 생각한 이유를 댓글로 남겨주세요.',
     '여러분은 어느 쪽인가요? 그렇게 생각한 이유를 댓글로 남겨주세요.',
     '당신은 어느 쪽인가요? 이유도 한 줄로 남겨주세요.'),
    ('② 더블CTA(저장+댓글 2연타) → 거부 기대',
     FILLER + '나중에 다시 보려면 지금 저장해두세요. 여러분 경험도 댓글로 남겨주세요.',
     '나중에 다시 보려면 지금 저장해두세요.',
     '여러분 경험도 댓글로 남겨주세요.'),
    ('③ 본문에 정보성 "저장" 단어 + 정상 CTA 1개 → 통과 기대(오탐 확인)',
     '뇌는 잠자는 동안 기억을 장기 기억으로 저장합니다. ' + FILLER
     + '수면 전 복습이 기억 저장 효율을 높입니다. 여러분은 어떤 방법을 쓰나요? 댓글로 남겨주세요.',
     '여러분은 어떤 방법을 쓰나요? 댓글로 남겨주세요.',
     '당신의 방법을 댓글로 알려주세요.'),
    ('④ cta/comment_cta 둘 다 누락 → 하드코딩 폴백 확인',
     FILLER + '오늘부터 결제 전 10초 멈춤을 실천해보세요.',
     '', ''),
    ('⑤ cta 누락 + comment_cta만 있음 → comment_cta 채택 여부 확인',
     FILLER + '오늘부터 결제 전 10초 멈춤을 실천해보세요.',
     '', '당신은 어느 쪽인가요? 댓글로 남겨주세요.'),
]

for name, script, cta, ccta in CASES:
    data = {
        'title': '결제 전 10초 멈춤의 힘',
        'hook': '당신이 매달 모르게 날리는 돈',
        'body': script,
        'full_script': script,
        'cta': cta,
        'comment_cta': ccta,
        'description': '소비 심리 원리와 방어법',
        'search_keywords': ['a', 'b', 'c', 'd'],
        'thumbnail_hook': '결제 전 10초 멈춤',
    }
    ok = gen._validate_script(data)
    print(f'\n{name}')
    print(f'   결과: {"통과" if ok else "거부(재생성)"}')
    if ok:
        print(f'   cta         = {data.get("cta")!r}')
        print(f'   comment_cta = {data.get("comment_cta")!r}')
        print(f'   full_script 끝 = ...{data["full_script"][-70:]!r}')
