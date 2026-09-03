# WORK_LOG (작업 기록)

최신 작업 내역이 위에 기록됩니다. 대화 시작 시 가장 최근 항목부터 확인하세요.

---

## 2026-09-03 — 영상 및 대본 퀄리티 전면 업그레이드 (v7.0)

> 구현 계획: `implementation_plan.md` (사용자 승인 완료)
> 목표: 시청자 클릭률(CTR)과 완시청률(AVD) 극대화 (트렌디한 비주얼 + 역동적 템포 + 효과음 디자인 + 최신 숏폼 트렌드 토픽 전면 리터칭)

### 승인 범위 및 구현 내역
1. **자막 비주얼 고도화 (`Pretendard` + 팝업 바운스 + 키워드 하이라이트)**
   - `assets/fonts/Pretendard-Bold.ttf` 적용 및 `config.yml` 폰트명 반영.
   - `scripts/video_composer.py`: FFmpeg `ass` 필터에 `:fontsdir` 옵션 지정으로 시스템 폰트 설치 여부와 무관하게 100% 로드 보장.
   - `scripts/subtitle_generator.py`:
     - 본문 자막 등장 시 통통 튀는 팝업 바운스 효과(`{\fad(100,80)\fscx108\fscy108\t(0,120,\fscx100\fscy100)}`) 적용.
     - `_highlight_keywords()`: 숫자/통계 및 핵심 심리/뇌과학 용어(도파민, 전두엽, 가스라이팅, 회피형 등)를 네온 옐로우(`{\c&H0000FFFF&}`)로 자동 하이라이트.
2. **배경 영상 템포 단축 (3개 → 4개 클립)**
   - `config/config.yml` 및 `scripts/video_downloader.py`, `scripts/main.py`: `background.count`를 4개로 조정 (컷당 약 11초 템포로 역동성 확보).
   - `download_multiple()`: 클립 수 부족 시 4개 목표 개수 보장 로직 강화.
3. **화면 전환 효과음(Whoosh SFX) 자동 믹싱**
   - `assets/sfx/whoosh.wav`: 0.4초 무손실 스위프 Whoosh 오디오 생성 및 배치.
   - `scripts/config_loader.py` & `config/config.yml`: `sfx` 설정 섹션 추가 (`enabled: true`, `volume: 0.20`).
   - `scripts/video_composer.py`: 4개 배경 전환 시점(`_calculate_transition_offsets`)마다 은은한 볼륨으로 Whoosh 사운드를 오디오 트랙에 자동 믹싱.
4. **대본 프롬프트 7종 고도화**
   - `config/prompts/*.txt` (7개 카테고리 전체):
     - 2단계(공감): 두루뭉술한 설명 금지, '하이퍼 리얼리즘 공감 1문장(시간/장소/행동)' 필수 재현 지침.
     - 3단계(원리/해결): 시청자가 오늘 당장 3초 만에 행동할 수 있는 'One-Action Rule(단 1가지 실천법)' 명령형 제시.
     - 검색 키워드: 4단계 씬 흐름에 맞추어 4개의 영어 키워드 생성 지침 및 스키마 반영.
   - `scripts/script_generator.py`: 기본 프롬프트 키워드 4개 반영.
5. **비발행 토픽 전면 리터칭 & 트렌드 교체**
   - `history/generated_topics.json` 기준 기발행된 토픽 100% 원본 보존 검증 완료.
   - 비발행분의 비문, 오타("명애", "거리가 닫지 않는" 등), 문장잘림 전수 교정.
   - `brain`의 15개 이상 중복되던 "집중력" 테마를 최신 숏폼 트렌드(팝콘브레인, 90분 커피, 글림프 뇌청소, 도파민 단식 등)로 다변화.
   - 교과서식 밋밋한 썸네일 훅을 숏폼 3대 공식(손실회피, 역설, 숫자) 기반의 강력한 6~18자 훅으로 전면 업그레이드.

### 검증 내역
- `scripts/*.py` 10개 전체 파일 Python 컴파일 문법 검사 PASS.
- `config/topics.json` 및 `config/config.yml` 파싱 및 유효성 전수 검사 PASS.
- `topics.json` 210개 전체 항목 훅 길이(6~18자), 마침표 배제, 완결형 문장 검사 PASS.
- 자막 ASS Pretendard 및 하이라이트/바운스 태그 생성 단위 테스트 PASS.
- 오디오 믹싱 및 Whoosh SFX 오버레이 Pydub 단위 테스트 PASS.

---

## 2026-08-30 — 텔레그램 영상 전송 1회 재시도(Retry), 실패 시 다운로드 링크 안내 및 모바일 재전송 워크플로 구축

> 사용자 이슈 및 요청: 
> 1. 오늘 영상이 텔레그램 메시지로 정상 발송되지 않은 원인 파악 및 보고 요청.
> 2. 영상만 텔레그램으로 발송하는 전용 트리거 구축 요청 (../AShorts 참조).

### 원인 분석 결과
- **정상 생성 및 히스토리 반영**: 2026-08-30 06:53 KST 실행된 Daily Korean Short(`daily-short-ko.yml`)에서 오늘의 주제("아무리 친해도 절대 하면 안 되는 말 3가지", 카테고리: relationship, no: 12) 영상이 정상 생성되어 `history/generated_topics.json`에 커밋(1232901) 및 아티팩트(`korean-short-...`)로 업로드 완료.
- **텔레그램 sendVideo 타임아웃/통신 지연 누락**: 영상 파일(약 7~15MB) 전송 시 텔레그램 API 서버 일시 지연 또는 120초 타임아웃 발생 시, 기존 코드는 단 1회만 시도하고 재시도 없이 예외를 흡수(로그 출력 후 종료)하여 워크플로는 성공했으나 영상 파일이 누락됨.
- **수동 재발송 수단 부재**: 기존에는 영상을 다시 받으려면 Gemini API와 2~3분 렌더링을 처음부터 다시 실행해야 했음.

### 구현 내역
1. **텔레그램 영상 전송 1회 자동 재시도 구현 (`scripts/telegram_notifier.py`)**:
   - `_send_video()` 메서드에 최대 2회 시도(초기 1회 + 1회 재시도, 3초 대기) 로직 적용.
   - 2회 모두 실패 시 "⚠️ 영상 파일 첨부 실패 안내"와 함께 **핸드폰에서 바로 영상을 다운로드할 수 있는 GitHub Actions Artifact 링크**를 자동 발송.
   - CLI 인자로 `--video-path` 및 `--caption`을 추가하여 외부 워크플로에서 직접 영상 전송 가능하도록 확장.
2. **모바일 원클릭 영상 재전송 워크플로 구축 (`.github/workflows/resend-video.yml`)**:
   - 핸드폰 GitHub 웹/앱에서 `Actions` -> `📲 Resend Video to Telegram` -> `Run workflow` 클릭 시, 직전 생성된 Artifact 영상을 다운로드하여 10~15초 만에 텔레그램으로 전송하는 전용 워크플로 구축.
   - Run ID 미입력 시 `daily-short-ko.yml` 최근 런 자동 탐색(영어 쇼츠/테스트 런도 선택 가능).
   - Gemini API 호출 및 FFmpeg 렌더링 없이 이미 완성된 오늘자 영상을 즉시 재발송.

### 검증 결과
- `python -m py_compile scripts/telegram_notifier.py` 100% PASS.
- `.github/workflows/resend-video.yml` YAML 유효성 검사 100% PASS.
- 오프라인 Mock 단위 테스트:
  - 1차 Timeout 실패 시 3초 후 2차 재시도 성공 검증 PASS.
  - 2회 연속 실패 시 Artifact 링크 포함 실패 안내 메시지 발송 검증 PASS.
  - CLI `--video-path` 및 `--caption` 인자 파싱 및 영상 전송 호출 검증 PASS.

---

## 2026-08-17 — 지침 개편, 비발행분 140개 바이럴 토픽/후킹 최적화 및 로드맵 현행화

> 사용자 승인: 작업 시작 전 Git Pull & 푸시 전 프로젝트 문서 갱신 지침 추가, 2026 트렌드 기반 비발행분(11~30번, 140개) 바이럴 토픽/썸네일 훅 전면 개편, 영상 용량(≤20MB) 보장 원칙 및 로드맵 현행화.

### 승인 범위
1. **지침 파일 3종 업데이트**:
   - `AGENTS.md`, `.agents/AGENTS.md`, `INSTRUCTIONS.md`: "작업 전 Git Pull 동기화", "푸시 전 프로젝트 문서(WORK_LOG/ROADMAP) 갱신", "로컬 API 호출 테스트 절대 금지 (할당량/비용 보호)" 명시.
2. **비발행분 140개 바이럴 토픽/후킹 전면 개편**:
   - `config/topics.json`: 7개 카테고리 11~30번 토픽 140개를 손실회피/도파민디톡스/가스라이팅파훼/2인칭자기대입 등 2026 최신 숏폼 트렌드 토픽으로 전면 업그레이드 (1~10번 70개 발행 기록은 완벽 보존).
3. **영상 용량 불변 보장 및 로드맵 현행화**:
   - `ROADMAP.md`: xfade 16종 전환, 정적 비네트 필터 완료 처리 및 `CRF 24 + maxrate 3M` 인코딩 기반 영상 파일 크기 20MB 이하 엄격 보장 원칙 반영.
4. **배경 영상 차단 필터(BLOCKED_TERMS) 강화**:
   - `scripts/video_downloader.py`: Pexels/Pixabay에서 부적절한 인물 및 임산부/만삭(`pregnant`, `pregnancy`, `maternity`, `baby bump`, `black female` 등) 스톡 영상이 다운로드되지 않도록 URL/태그 차단 키워드 리스트 전면 강화.
   - `scripts/script_generator.py`: LLM 검색 키워드 생성 시 배제 지침 명시.
5. **0.3초 썸네일 후킹 자막 한국어 문맥 단락 맞춤 스마트 줄바꿈 알고리즘 적용**:
   - `scripts/utils.py` & `scripts/subtitle_generator.py`: 조사/어미/수식관계/길이균형 기반 `smart_split_korean_hook` 구현 적용. 어색한 1글자 고립 없이 2줄 균형 배치 완성.

### 상세 내역 및 검증
1. **지침 문서**:
   - `AGENTS.md`, `.agents/AGENTS.md`, `INSTRUCTIONS.md` 동기화 및 푸시 전 체크리스트 정비.
2. **토픽 검증**:
   - `config/topics.json` 7개 카테고리 총 210개(각 30개씩) 항목 전수 유효성 검증 완료 (`python verify_topics.py` PASS).
3. **코드 컴파일 검증**:
   - `python -m py_compile scripts/*.py` 전체 통과.

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
