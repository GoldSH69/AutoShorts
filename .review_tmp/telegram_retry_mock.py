# -*- coding: utf-8 -*-
"""오프라인 mock 검증: 텔레그램 첫댓글 문구 전송 재시도/정확 로깅/연타 방지.
외부 API 호출 없음(requests.post·time.sleep 스텁). 리뷰 후 삭제."""
import os
import sys
import logging
import requests

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'offline-stub')
os.environ.setdefault('TELEGRAM_CHAT_ID', 'offline-stub')

import telegram_notifier as tn  # noqa: E402

FAILURES = []


def check(name, cond, detail=''):
    status = 'PASS' if cond else 'FAIL'
    print(f'  [{status}] {name}{(" — " + detail) if detail and not cond else ""}')
    if not cond:
        FAILURES.append(name)


class FakeConfig:
    def is_telegram_enabled(self): return True
    def get_telegram_config(self): return {'send_video': False}
    def get_category_emoji(self, weekday=None): return '🧠'
    def get_category_name(self, weekday=None, language='ko'): return '테스트'
    def is_youtube_upload_enabled(self): return True


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())

    def contains(self, needle):
        return any(needle in m for m in self.messages)


class FakeResponse:
    def __init__(self, status_code=200, text='ok'):
        self.status_code = status_code
        self.text = text


class NetErr(requests.exceptions.ConnectionError):
    pass


posts = []
sleeps = []
net_err = NetErr("('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))")


def fake_post(url, json=None, timeout=None):
    posts.append(json)
    behavior = BEHAVIOR[len(posts) - 1]
    if isinstance(behavior, Exception):
        raise behavior
    return behavior


def fake_sleep(sec):
    sleeps.append(sec)


BEHAVIOR = []
tn.requests.post = fake_post
tn.time.sleep = fake_sleep

capture = LogCapture()
tn.logger.addHandler(capture)

notifier = tn.TelegramNotifier(FakeConfig())

SCRIPT = {
    'title': '테스트 제목',
    'no': 1,
    'thumbnail_hook': '테스트 후킹',
    'comment_cta': '댓글용 질문 문장인가요?',
    'instagram_caption': '', 'instagram_hashtags': '',
    'tiktok_caption': '', 'tiktok_hashtags': '',
}
UPLOAD = {'video_id': 'vid123', 'url': 'https://youtube.com/shorts/vid123', 'privacy': 'private'}


def reset():
    posts.clear()
    sleeps.clear()
    capture.messages.clear()


print('\n① 댓글 1차 실패 → 재시도 성공 (send_success 경로)')
reset()
BEHAVIOR[:] = [FakeResponse(200), net_err, FakeResponse(200)]  # 메인 / 댓글1차 / 댓글재시도
result = notifier.send_success(script_data=SCRIPT, upload_result=UPLOAD)
check('메시지 3회 호출 (메인+댓글2회)', len(posts) == 3, f'실제 {len(posts)}회')
check('재시도 전 3초 대기 1회', sleeps == [1, 3], f'실제 {sleeps}')
check('댓글 문구가 최종 전송됨', len(posts) == 3 and posts[2].get('text') == SCRIPT['comment_cta'])
check('재시도 경고 로그', capture.contains('네트워크 오류 (1/2)'))
check('"첫 댓글용 문구 전송 완료" 로그', capture.contains('첫 댓글용 문구 전송 완료'))
check('send_success 정상 반환', result is True)

print('\n② 댓글 2회 모두 실패 → 실패 로그 정확성')
reset()
BEHAVIOR[:] = [FakeResponse(200), net_err, net_err]
result = notifier.send_success(script_data=SCRIPT, upload_result=UPLOAD)
check('메시지 3회 호출 (메인+댓글2회)', len(posts) == 3, f'실제 {len(posts)}회')
check('재시도 전 3초 대기 1회', sleeps == [1, 3], f'실제 {sleeps}')
check('"첫 댓글용 문구 전송 실패" 로그', capture.contains('첫 댓글용 문구 전송 실패'))
check('거짓 "전송 완료" 로그 없음', not capture.contains('첫 댓글용 문구 전송 완료'))
check('최종 오류 로그 형식 유지', capture.contains('텔레그램 전송 오류:'))

print('\n③ 기본값(max_attempts=1)은 재시도하지 않음 (회귀 방지)')
reset()
BEHAVIOR[:] = [net_err]
ok = notifier._send_message('일반 텍스트', parse_mode=None)
check('호출 1회만 수행', len(posts) == 1, f'실제 {len(posts)}회')
check('대기 없음', sleeps == [], f'실제 {sleeps}')
check('False 반환', ok is False)

print('\n④ HTML 400 → plain text 폴백 유지')
reset()
BEHAVIOR[:] = [FakeResponse(400, 'parse error'), FakeResponse(200)]
ok = notifier._send_message('폴백 텍스트', parse_mode='HTML')
check('호출 2회 (HTML 실패 후 plain)', len(posts) == 2, f'실제 {len(posts)}회')
check('2차 호출에 parse_mode 없음', len(posts) == 2 and 'parse_mode' not in posts[1])
check('True 반환', ok is True)

print('\n⑤ comment_cta 빈값 → 조용한 누락 대신 경고 로그')
reset()
BEHAVIOR[:] = [FakeResponse(200)]
empty_script = dict(SCRIPT, comment_cta='')
notifier.send_success(script_data=empty_script, upload_result=UPLOAD)
check('메인만 전송 (1회)', len(posts) == 1, f'실제 {len(posts)}회')
check('"첫 댓글용 문구 없음" 경고 로그', capture.contains('첫 댓글용 문구 없음'))

print()
if FAILURES:
    print(f'❌ 실패 {len(FAILURES)}건: {FAILURES}')
    sys.exit(1)
print('✅ 전 케이스 통과 (외부 API 호출 없음)')
