# 주제 고도화·개편 실행 계획 (2026-11)

> 2026-11-02 월간 성적표·성과 데이터·최신 Shorts 트렌드 조사 기반.
> 작업이 중단되어도 이 문서의 체크 상태로 남은 일을 이어갈 수 있게 기록한다.

## 결정 사항

- 영어 괄호는 **영어 검색 유입용**이므로 제거하지 않는다.
  - 제목: 한글 본문 15~30자 + 관련 영어 용어 괄호 1개, 전체 45자 이내.
  - `(Psychology)`, `(Self)`, `(Love)`, `(Brain)` 같은 범용어만 제거한다.
- 4주 실행안은 별도 대기 없이 즉시 적용한다.
- `config/topics.json`은 `no`와 리스트 인덱스가 연결되어 있으므로 순서를 바꾸지 않고, 기존 번호의 문구만 교체한다.
- 실제 Gemini/Pexels/YouTube API 호출 테스트는 하지 않는다. `py_compile`, JSON 검증, 오프라인 계산만 수행한다.

## 진행 상태

### 완료
- [x] 프롬프트 7종 제목 규칙: 한글 본문 30자·영어 괄호 1개·전체 45자, 영어 검색 유지
- [x] 프롬프트 7종 훅 규칙: 첫 2초·15자 이내·인물/행동 즉시 시작
- [x] 프롬프트 7종 고정댓글: 2지선다 질문 1문장
- [x] `config/topics.json` 즉시 사용 주제 relationship 29~35, love 27~29/38, dark 35 교체. relationship 50은 기존 문구가 적합해 유지.
- [x] `config/config.yml` 편성: relationship 3 / love 2 / dark 1 / brain 1
- [x] `config/config.yml` 해시태그: 손절·회피형·관계스트레스 중심 보강
- [x] `scripts/script_generator.py` 제목 길이 경고 + CTA 2지선다 지침
- [x] `scripts/topic_inventory.py` 실제 재고 계산 공통 모듈
- [x] `scripts/telegram_notifier.py` 하드코딩 `30 - no` 제거 → 실제 재고 사용
- [x] `scripts/script_generator.py` 주제 선택 로그에 실제 재고 표시
- [x] `scripts/analytics_collector.py` 성과 엔트리에 title/category/topic_no 저장
- [x] `scripts/monthly_report.py` 경고 문구 `노출 하락` → `조회수 하락` 정정
- [x] `WORK_LOG.md`, `ROADMAP.md` 갱신
- [x] `py_compile`·JSON·재고 계산 오프라인 검증
  - `py_compile` 5개 통과, JSON 7카테고리 개수·`no` 연속성 통과, YAML 편성/해시태그 확인.
  - 재고: relationship 59/87, love 61/87, dark 60/87, brain 30/51.
  - 월간 리포트·성과 수집 드라이런 통과(외부 API 호출 없음).

### 보류(의도적, 미완료)
- [ ] 시즌 주제(명절·부모-돈)는 시즌 전 재배치. 현재 발행 순번에서 억지로 당기지 않음.
- [ ] 실제 YouTube 리텐션·유지율 검증은 다음 성과 수집 이후. 현재 `videoDuration` 미수집.
- [ ] GitHub Actions 실제 run은 최신 main에서 새 `workflow_dispatch`로 실행 필요.

## 4주 실행안 (즉시 적용 버전)

| 주차 | 콘텐츠 | 핵심 |
|---|---|---|
| 1주 | 기존 다음 순번 7편 | 제목·첫 2초·영어 괄호 1개 규칙 적용 |
| 2주 | 손절/경계 3 + love 2 + dark 1 + brain 1 | 고정댓글 2지선다 운영 |
| 3주 | 애착/친밀감 5 + 상위작 리믹스 2 | 리믹스·CTA 실험 |
| 4주 | 말 한마디 5 + 편성 재배치 | 주제 재고·성과 재점검 |

## 측정 지표

- 7일 views/day, 28일 누적 조회수
- 완주율·평균 시청시간(수집 가능 시)
- 댓글/1,000회, 구독/1,000회
- 제목 길이, 영어 괄호 수, 첫 2초 훅 길이

## 롤백

- 문제 발생 시 `git revert <commit>`로 프롬프트·주제·편성 변경을 한 번에 되돌린다.
- `scripts/topic_inventory.py`는 읽기 전용 계산 모듈이라 롤백 영향이 없다.
