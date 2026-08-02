# Implementation Plan — 후킹 개선 + 트렌드 토픽 전면 교체 + 영상 효과 고도화

## 승인 확정 사항 (2026-08-02)
- 포함: 1-A(프롬프트 후킹 개선), 1-B(script_generator 검증), 1-C(자막 효과, 무료 ASS/FFmpeg)
- 토픽: 비발행분(164개) 전체를 최신 트렌드 주제로 교체
- 3-C: xfade 전환 무작위화 + 비네트/그레인
- 3-D: 제목 SEO (hook 단어 앞배치)
- 제외: 3-A(썸네일 이미지), 3-B(성과 트래킹)

---

## 1. 후킹 문장 개선

### 1-A. 프롬프트 7개 파일 thumbnail_hook 지침 업그레이드
파일: `config/prompts/{money,success,brain,dark,hack,love,relationship}.txt`

공통으로 `thumbnail_hook` JSON 가이드 문구를 아래로 교체:
- 검증된 후킹 3공식 안내:
  - `숫자+충격`: "월 43만원이 그냥 사라지는 이유"
  - `당신은 X하는 사람`: "당신도 모르게 X하는 사람"
  - `절대 하지 않는 X`: "부자는 절대 하지 않는 지출"
- 감정 트리거: 호기심 갭, 손실 회피, 반전/대비
- 금지 패턴: 평범한 서술형("~입니다"), 마침표로 끝맺음, 5자 이하 너무 짧음
- `\n` 배치: 첫 줄에 최대 임팩트 단어 배치

### 1-B. script_generator.py 후킹 검증 로직 강화
- `_validate_thumbnail_hook()` 신규 추가
  - 길이 6~18자 (줄바꿈 제외)
  - 이모지/특수문자 제거
  - 마침표로 끝나는 문장 재생성
  - 정적 hook과 동일(단순 복붙) 시 재생성
- `generate()`와 `_validate_script()`의 hook 폴백 조건을 검증 로직으로 교체

### 1-C. subtitle_generator.py 후킹 자막 효과 (무료)
- Hook 스타일 자막에 페이드인(`{\fad}`) + 확대(`{\fscx}\fscy`) + 반짝 효과 추가
- 0.0~0.3초 구간에 적용 (모두 ASS 내장 태그 + FFmpeg 렌더링 = 무료)

## 2. 토픽 전면 교체
- `config/topics.json` 비발행분(각 카테고리 남은 번호)을 최신 트렌드 주제로 교체
- 기존 발행 기록(history)과 번호 충돌 없음 (마지막 no+1부터 새 번호 사용)
- money의 과도한 "부자 패턴" 줄이고 자존감/번아웃/외로움/나르시시스트/비교심리 등 트렌드 주제 반영

## 3. 영상 효과 고도화 (3-C)
- `video_composer.py`:
  - xfade transition을 fade 외 `wipeleft/wiperight/slideup/slidedown/circleopen/radial` 등에서 무작위 선택
  - 최종 합성 후 미세 비네트 + 필름 그레인 노이즈 필터 추가

## 4. 제목 SEO (3-D)
- `youtube_uploader.py` `generate_upload_metadata()`:
  - 제목 포맷에서 hook 단어를 앞에 배치 (예: `{thumbnail_hook 핵심 키워드} {emoji} {title}`)

---

## Verification
1. `python -c "import ast; ast.parse(...)"` 로 모든 .py 문법 검증
2. `topics.json` JSON 유효성 + 번호 연속성 검증 스크립트
3. `python scripts/main.py --no-history --skip-upload --skip-telegram --category money` 드라이런으로 스크립트 생성 확인 (선택)
