#!/usr/bin/env python3
"""
Gemini API 키로 사용 가능한 모델 목록을 조회하는 터미널 도구.

- 목록/가용 여부: 키에 실제로 열려 있는 모델을 API에서 직접 조회한다.
- 무료 여부: models.list 응답에는 티어 정보가 없으므로, 공식 가격 문서
  (2026-11-16 기준) 의 무료 티어 표를 병기한다. 표에 없는 모델은 "?"로 표시.
- API 키는 헤더(x-goog-api-key)로만 전달하며 화면/로그에는 마스킹해서 출력한다.

사용 예:
  python scripts/list_gemini_models.py                  # 실행하면 키를 직접 입력받음
  python scripts/list_gemini_models.py --all            # 이미지/TTS/Live 등도 포함
  python scripts/list_gemini_models.py --json           # JSON 출력
  python scripts/list_gemini_models.py --verify         # 모델별 접근 가능 여부 실제 확인
  python scripts/list_gemini_models.py --key AIza...    # 키를 인자로 바로 전달
  python scripts/list_gemini_models.py --env            # GEMINI_API_KEY 환경변수 사용
"""

import argparse
import getpass
import json
import os
import re
import sys
import time
import unicodedata

try:
    import requests
except ImportError:
    print("[ERROR] requests 패키지가 필요합니다: pip install requests", file=sys.stderr)
    raise SystemExit(1)


DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
PAGE_SIZE = 1000
TIMEOUT = 30

# ─── 무료 티어 여부 (출처: ai.google.dev/gemini-api/docs/pricing, 2026-11-16 확인) ───
# True=무료 제공, False=유료 전용, "limited"=기존 사용자 제한, None=문서에서 미확인
FREE_TIER = {
    # Gemini 4
    "gemini-4-hydrogen": True,
    "gemini-4-carbon": False,
    "gemini-4-argon": False,
    # Gemini 3 Flash 계열
    "gemini-3.8-flash": True,
    "gemini-3.6-flash": True,
    "gemini-3.5-flash-lite": True,
    "gemini-3.1-flash-lite": True,
    "gemini-3.1-pro-preview": None,
    # Live / Transcribe 계열
    "gemini-3.8-live": True,
    "gemini-3.8-live-extended-thinking": True,
    "gemini-3.1-flash-live-preview": True,
    "gemini-3.5-live-translate-preview": True,
    "gemini-3.5-transcribe": True,
    "gemini-3.5-transcribe-live": True,
    # 생성 미디어
    "gemini-omni-1.2-flash": False,
    "gemini-omni-1.1-flash": False,
    # 2.5 계열 (신규 프로젝트 제한)
    "gemini-2.5-flash": "limited",
    "gemini-2.5-pro": "limited",
    "gemini-2.5-flash-lite": "limited",
}

# 텍스트 생성이 아닌 모델을 걸러내는 키워드 (소문자 기준)
NON_TEXT_KEYWORDS = (
    "-image", "nano-banana", "-tts", "-live", "transcribe",
    "embedding", "robotics", "-audio", "computer-use",
    "deep-research", "antigravity", "imagen", "veo", "lyria",
    "omni", "decision",
)

FREE_LABEL = {True: "O", False: "X", "limited": "제한", None: "?"}


# ─── 유틸 ───

def mask_key(key):
    """API 키 마스킹 (앞 4자 + 뒤 4자만 노출)"""
    if not key:
        return "(없음)"
    if len(key) <= 12:
        return key[:2] + "*" * (len(key) - 2)
    return f"{key[:4]}...{key[-4:]} (len={len(key)})"


def disp_width(text):
    """한글/CJK 폭을 2로 계산한 표시 폭"""
    width = 0
    for ch in str(text):
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def pad(text, width):
    """표시 폭 기준 좌측 정렬 패딩"""
    text = str(text)
    return text + " " * max(0, width - disp_width(text))


def model_id(name):
    """'models/gemini-4-hydrogen' -> 'gemini-4-hydrogen'"""
    return str(name).split("/", 1)[-1]


def is_text_model(model):
    """generateContent를 지원하는 텍스트 생성 모델인지 판별"""
    methods = model.get("supportedGenerationMethods") or []
    if "generateContent" not in methods:
        return False
    name = model_id(model.get("name", "")).lower()
    return not any(k in name for k in NON_TEXT_KEYWORDS)


def free_status(model):
    """무료 티어 상태 조회"""
    return FREE_TIER.get(model_id(model.get("name", "")))


def thinking_support(model):
    """thinking 지원 방식 표기"""
    name = model_id(model.get("name", "")).lower()
    if "2.5-flash" in name or "2.5-pro" in name:
        return "budget"
    if name.startswith("gemini-4") or re.match(r"gemini-3(\.\d+)?-", name):
        return "level"
    return "-"


def version_key(model):
    """최신 버전 우선 정렬용 키"""
    name = model_id(model.get("name", ""))
    match = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    version = float(match.group(1)) if match else 0.0
    order = 0 if free_status(model) is True else 1
    return (order, -version, name)


# ─── API ───

def fetch_models(api_key, base_url=DEFAULT_BASE_URL, session=None, timeout=TIMEOUT):
    """키에 열려 있는 전체 모델 목록 조회 (페이지네이션 처리)"""
    session = session or requests.Session()
    models = []
    page_token = None
    pages = 0

    while True:
        params = {"pageSize": PAGE_SIZE}
        if page_token:
            params["pageToken"] = page_token

        resp = session.get(
            f"{base_url}/models",
            params=params,
            headers={"x-goog-api-key": api_key},
            timeout=timeout,
        )
        pages += 1

        if resp.status_code != 200:
            raise RuntimeError(explain_http_error(resp))

        data = resp.json()
        models.extend(data.get("models") or [])

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        if pages >= 20:  # 무한 루프 방지
            break

    return models


def verify_access(api_key, model_name, base_url=DEFAULT_BASE_URL, session=None, timeout=TIMEOUT):
    """countTokens로 실제 접근 가능 여부 확인 (생성 토큰 미소모)"""
    session = session or requests.Session()
    try:
        resp = session.post(
            f"{base_url}/{model_name}:countTokens",
            headers={"x-goog-api-key": api_key},
            json={"contents": [{"parts": [{"text": "ok"}]}]},
            timeout=timeout,
        )
    except Exception as e:  # 네트워크 오류
        return f"ERR({type(e).__name__})"

    if resp.status_code == 200:
        return "OK"
    if resp.status_code == 404:
        return "NO_MODEL"
    if resp.status_code == 403:
        return "NO_ACCESS"
    if resp.status_code == 429:
        return "RATE_LIMIT"
    if resp.status_code == 400:
        return "BAD_REQUEST"
    return f"HTTP{resp.status_code}"


def explain_http_error(resp):
    """HTTP 오류를 사람이 읽을 수 있는 메시지로 변환"""
    detail = ""
    try:
        payload = resp.json()
        detail = (payload.get("error") or {}).get("message", "")
    except Exception:
        detail = (resp.text or "")[:200]

    hints = {
        400: "요청 형식 또는 API 키 형식이 올바르지 않습니다.",
        401: "API 키 인증에 실패했습니다.",
        403: "이 키로 Gemini API를 사용할 권한이 없습니다 (API 활성화/키 확인).",
        404: "엔드포인트를 찾을 수 없습니다 (base URL 확인).",
        429: "할당량 초과입니다. 잠시 후 다시 시도하세요.",
    }
    code = resp.status_code
    return f"HTTP {code} - {hints.get(code, '알 수 없는 오류')} {detail}".strip()


# ─── 출력 ───

def build_rows(models, include_all=False):
    """출력용 행 구성: (모델ID, 무료, thinking, 입력한도, 출력한도, 표시명)"""
    selected = [m for m in models if include_all or is_text_model(m)]
    selected.sort(key=version_key)

    rows = []
    for m in selected:
        rows.append({
            "model": model_id(m.get("name", "")),
            "free": FREE_LABEL.get(free_status(m), "?"),
            "free_bool": free_status(m),
            "thinking": thinking_support(m),
            "input_limit": m.get("inputTokenLimit"),
            "output_limit": m.get("outputTokenLimit"),
            "display": m.get("displayName", ""),
            "methods": m.get("supportedGenerationMethods") or [],
        })
    return rows


def render_table(rows, verify_results=None):
    """터미널 표 출력"""
    headers = ["모델 ID", "무료", "thinking", "입력", "출력", "표시명"]
    if verify_results is not None:
        headers.append("접근확인")

    body = []
    for r in rows:
        line = [
            r["model"],
            r["free"],
            r["thinking"],
            f"{r['input_limit']:,}" if r["input_limit"] else "-",
            f"{r['output_limit']:,}" if r["output_limit"] else "-",
            r["display"],
        ]
        if verify_results is not None:
            line.append(verify_results.get(r["model"], "-"))
        body.append(line)

    widths = [disp_width(h) for h in headers]
    for line in body:
        for i, cell in enumerate(line):
            widths[i] = max(widths[i], disp_width(cell))

    out = []
    out.append("  ".join(pad(h, widths[i]) for i, h in enumerate(headers)).rstrip())
    out.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for line in body:
        out.append("  ".join(pad(cell, widths[i]) for i, cell in enumerate(line)).rstrip())
    return "\n".join(out)


def summarize(rows):
    """요약 문구"""
    text_total = len(rows)
    free_yes = sum(1 for r in rows if r["free_bool"] is True)
    free_no = sum(1 for r in rows if r["free_bool"] is False)
    free_unknown = sum(1 for r in rows if r["free_bool"] is None)
    return (
        f"총 {text_total}개 (무료 O={free_yes}, 유료 X={free_no}, 미확인 ?={free_unknown})"
    )


# ─── main ───

def resolve_key(cli_key, use_env=False):
    """키 우선순위: --key > 직접 입력(기본) > --env 사용 시 환경변수

    기본 동작은 실행 시 키를 직접 입력받는 것이다.
    비대화형(파이프/CI) 실행에서는 입력이 불가능하므로 환경변수로 대체한다.
    """
    if cli_key:
        return cli_key.strip()

    env_key = (os.environ.get("GEMINI_API_KEY") or "").strip()

    if use_env:
        if env_key:
            print("GEMINI_API_KEY 환경변수를 사용합니다.")
            return env_key
        print("[WARN] GEMINI_API_KEY가 비어 있습니다. 직접 입력으로 전환합니다.", file=sys.stderr)

    if not sys.stdin.isatty():
        # 파이프/CI 환경: 입력 프롬프트를 띄울 수 없음
        if env_key:
            print("비대화형 실행: GEMINI_API_KEY 환경변수를 사용합니다.")
            return env_key
        print(
            "[ERROR] 비대화형 실행에서는 키를 입력받을 수 없습니다.\n"
            "        --key AIza... 또는 GEMINI_API_KEY 환경변수를 사용하세요.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    for attempt in range(1, 4):
        try:
            key = getpass.getpass(
                f"Gemini API 키 입력 (입력값은 화면에 표시되지 않음){'' if attempt == 1 else f' [{attempt}/3]'}: "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n취소되었습니다.", file=sys.stderr)
            raise SystemExit(1)
        except Exception:
            # getpass 미지원 콘솔(일부 IDE)에서는 일반 입력으로 대체
            try:
                key = input("Gemini API 키 입력: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n취소되었습니다.", file=sys.stderr)
                raise SystemExit(1)

        if key:
            return key
        print("[WARN] 키가 비어 있습니다. 다시 입력하세요.", file=sys.stderr)

    print("[ERROR] 키가 입력되지 않았습니다.", file=sys.stderr)
    raise SystemExit(1)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Gemini API 키로 사용 가능한 모델과 무료 티어 여부를 조회합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  python scripts/list_gemini_models.py\n"
            "  python scripts/list_gemini_models.py --all\n"
            "  python scripts/list_gemini_models.py --json > models.json\n"
            "  python scripts/list_gemini_models.py --verify\n"
        ),
    )
    parser.add_argument("--key", help="Gemini API 키 (미지정 시 실행 중 직접 입력)")
    parser.add_argument("--env", action="store_true", help="입력 대신 GEMINI_API_KEY 환경변수 사용")
    parser.add_argument("--all", action="store_true", help="이미지/TTS/Live/Embedding 등도 포함")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="모델별 countTokens 호출로 실제 접근 가능 여부 확인 (호출 수만큼 지연 발생)",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (기본 v1beta)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    api_key = resolve_key(args.key, use_env=args.env)

    if not api_key:
        print("[ERROR] API 키가 비어 있습니다.", file=sys.stderr)
        return 1

    print(f"키: {mask_key(api_key)}")
    print(f"조회: {args.base_url}/models")
    print()

    session = requests.Session()
    try:
        models = fetch_models(api_key, args.base_url, session=session)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except requests.exceptions.Timeout:
        print("[ERROR] 요청 시간이 초과되었습니다. 네트워크를 확인하세요.", file=sys.stderr)
        return 1

    rows = build_rows(models, include_all=args.all)

    verify_results = None
    if args.verify:
        print(f"접근 확인 중... ({len(rows)}개 모델, countTokens 사용)")
        verify_results = {}
        for i, r in enumerate(rows, 1):
            verify_results[r["model"]] = verify_access(
                api_key, f"models/{r['model']}", args.base_url, session=session
            )
            print(f"  [{i}/{len(rows)}] {r['model']}: {verify_results[r['model']]}")
            time.sleep(0.3)  # 연속 호출 완화
        print()

    if args.json:
        payload = []
        for r in rows:
            item = {k: v for k, v in r.items() if k != "free_bool"}
            if verify_results is not None:
                item["access"] = verify_results.get(r["model"])
            payload.append(item)
        print(json.dumps({"key": mask_key(api_key), "models": payload},
                         ensure_ascii=False, indent=2))
        return 0

    print(render_table(rows, verify_results))
    print()
    print(summarize(rows))
    print("무료: O=무료 티어 제공, X=유료 전용, 제한=기존 사용자만, ?=공식 문서 미확인")
    print("참고: models.list 응답에는 티어 정보가 없어 무료 표기는 가격 문서 기준입니다.")
    if verify_results is not None:
        print("접근확인: OK=사용 가능, NO_ACCESS=권한 없음, RATE_LIMIT=할당량 초과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
