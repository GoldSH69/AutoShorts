# WORK_LOG (작업 기록)

최신 작업 내역이 위에 기록됩니다. 대화 시작 시 가장 최근 항목부터 확인하세요.

---

## 2026-08-07 — GitHub Actions 장애 복구 중복 실행 히스토리 롤백 정리

> 원인 해결: GitHub Actions 장애 복구 과정에서 10시 경 중복 실행되어 작성된 10번 토픽(`no: 10`) 이력을 삭제하여, 차주 금요일(2026-08-14)에 10번 토픽이 순서대로 자동 실행되도록 정돈.

### 승인 범위
- `history/generated_topics.json`: 중복 등록된 `no: 10` 항목(`"당신이 미루기를 끊지 못하는 진짜 이유"`) 삭제.

### 상세
1. `history/generated_topics.json`:
   - 2026-08-07 장애 복구 실행분(`no: 10`) 이력 제거.
   - `hack` 카테고리 최종 기록을 `no: 9` (`"아침 결심이 매일 깨진다면? 성공률 91% 심리 해킹법"`)로 유지.
2. 검증:
   - `python -c "import json; json.load(open('history/generated_topics.json', encoding='utf-8'))"` 유효성 검증 PASS.

---

## 2026-08-06 — 자연스러운 AI CTA(댓글/저장/공유 유도) 생성 및 검증 강화

> 원인 해결: 스크립트 작성 시 AI가 댓글 유도/저장 문구(CTA)를 생략하는 현상 개선

### 승인 범위
- 프롬프트 지침: `scripts/script_generator.py` 내 `comment_instruction` 지침 개편 (AI가 4단계 대본 마무리에 자연스러운 댓글/저장/공유 CTA 문구 1문장을 필수로 작성하도록 지정)
- 대본 검증: `_validate_script()`에서 AI가 생성한 CTA가 `full_script` 마무리에 잘 녹아들어 있는지 확인하고, 누락 시 문맥 어색함 없이 덧붙임 보장.

### 상세
1. `scripts/script_generator.py`:
   - `comment_instruction` 지침 수정: "굳이 넣지 않아도 됩니다" 문구 제거 및 자연스러운 CTA 작성 필수 안내.
   - `_validate_script()`: `full_script` 마무리 키워드 검사 및 CTA 반영 보장 로직 강화.
2. 검증:
   - `python -m py_compile scripts/script_generator.py` 문법 통과.
   - 오프라인 단위 테스트(Mock Data) 실행: AI 자연스러운 생성 포함 케이스 및 누락 시 자동 덧붙임 보장 케이스 모두 PASS.

---

## 2026-08-03 — 영상 길이·대본 구조·토픽 전면 최적화 (v6.7)

> 트렌드 리서치 기반: 완시청률 우선, 나레이션 38~50초가 최적, 4단계 공감 서사 구조.

### 승인 범위
- 길이: `video.duration` 50→45, `max_duration` 55→50초
- 프롬프트 7종: 정보 나열 5단계 → **해결책 중심 4단계(Hook→공감→원리·해결→반전/CTA)** + 2차 마이크로훅 + 루프 대본
- 토픽: 발행분(1~8번, 총 56개) 보존, **비발행분(9~30번) 154개 트렌드/해결형 교체**

### 상세
1. **길이** (`config/config.yml`): 50→45초, 최대 55→50초 (국내 2026 Q1 완시청률 최적 구간 38~50초)
2. **프롬프트 7종 재작성** (`config/prompts/*.txt`): 4단계 구조 공통 적용, 각 카테고리 테마 유지
   - 0~3초 자기대입/역설 후킹 / 3~15초 일상 문제 재현 / 15~40초 원리+구체 해결책 / 40~45초 반전+참여 CTA
   - 약 10초 지점 2차 마이크로훅, 마지막=첫 문장 루프 대본
3. **토픽 154개 교체** (`config/topics.json`): 다크 관계·자기대입·반전·해결형 후킹(6~18자)으로 통일, 1~8번 발행분 보존(각 8개 총 56개)
4. **검증**: `scripts/*.py` 문법 OK, 훅 길이/종결/이모지 154개 전수 PASS

### 보류
- `main.py` 풀 드라이런 미실행 (선택)

---

## 2026-08-02 — 후킹 개선 + 토픽 교체 + 영상 효과 고도화 (v6.6)

> 구현 계획: `implementation_plan.md` (승인 확정 2026-08-02)

### 승인 범위
- 포함: 1-A(프롬프트 후킹), 1-B(script_generator 검증), 1-C(자막 효과), 토픽 비발행분 전면 교체, 3-C(xfade/비네트/그레인), 3-D(제목 SEO)
- 제외: 3-A(썸네일 이미지), 3-B(성과 트래킹)

### 완료 내역
1. **1-A 프롬프트 후킹 지침** (`config/prompts/*.txt` 7개)
   - 후킹 3공식: ① 숫자+충격 ② 당신은 X하는 사람 ③ 절대 하지 않는 X
   - 길이 6~15자, 2인칭 가산점, 금지(서술형/마침표/5자 이하/이모지), `\n` 첫 줄 임팩트

2. **1-B 스크립트 후킹 검증** (`scripts/script_generator.py`)
   - `_validate_thumbnail_hook()` 신규: 템플릿 잔여물 제거, 이모지/특수문자 제거, 6~18자, 종결형 거부, 정적 hook 단순 복붙 거부
   - `generate()` / `_validate_script()` 폴백을 검증 메서드로 교체
   - 단위 테스트 10케이스 PASS

3. **1-C Hook 자막 효과** (`scripts/subtitle_generator.py`)
   - `{\fad(60,0)\fscx115\fscy115\t(0,180,\fscx100\fscy100)}` 페이드+확대+반짝 (ASS 내장 태그, 무료)
   - 실제 FFmpeg 렌더링 검증 완료

4. **② 토픽 전면 교체** (`config/topics.json`)
   - 비발행분 164개를 트렌드 주제로 교체 (발행분 46개 원본 보존 검증)
   - 파일 유실 사고 → `git checkout`으로 복구 후 재실행 (재생성 스크립트: `C:\Users\Saturn\AppData\Local\Temp\opencode\rebuild_topics.py`)

5. **3-C 영상 효과** (`scripts/video_composer.py`)
   - `XFADE_TRANSITIONS` 16종 + fade, `_get_random_xfade_transition()` (50% fade / 50% 랜덤)
   - `_get_vignette_grain_filter()` 비네트+그레인, 단일/멀티 합성 모두 적용
   - FFmpeg 18종 transition + 비네트/그레인 실렌더 검증 PASS

6. **3-D 제목 SEO** (`scripts/youtube_uploader.py`)
   - `generate_upload_metadata()`: hook 키워드 앞배치 (80자 이내 시 `{hook} | {title}`)
   - httplib2 미설치로 함수만 exec 추출해 테스트 통과

### 검증 요약
- `scripts/*.py` 10개 문법 OK
- 신규 hook 164개 모두 6~18자 + 종결형 없음
- FFmpeg 필터 18종 + ASS 렌더링 실동작 확인
- 상세 결과: `C:\Users\Saturn\AppData\Local\Temp\opencode\` (remaining_topics.txt, topic_report.txt)

### 보류 / 참고
- `main.py` 드라이런은 아직 미실행 (선택적)
- Hook 자막 폰트는 108pt 유지 결정 (9자/줄 분할 시 폭 상한에 근접한 값, 사용자 승인)
