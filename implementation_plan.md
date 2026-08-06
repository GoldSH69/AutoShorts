# Implementation Plan — 자연스러운 AI CTA(댓글/저장 유도) 자동 생성 및 검증 강화

## 승인 사항 (2026-08-06)
- AI(Gemini)가 대본 작성 시 4단계 마무리에 자연스러운 댓글 유도/저장/공유 문구(CTA)를 직접 생성하고 `full_script` 맥락에 자연스럽게 포함하도록 프롬프트 지침 개선.
- 스크립트 검증(`_validate_script`) 시 AI가 생성한 CTA가 대본 마무리에 잘 녹아들어 있는지 확인하고, 보장 로직 강화.

---

## 1. 프롬프트 CTA 지침 강화 (`scripts/script_generator.py`)
- `comment_instruction` (프롬프트 추가 지침) 개편:
  - "굳이 넣지 않아도 됩니다"와 같은 소극적 지침 제거.
  - "AI가 대본 맥락에 맞춰 자연스럽게 이어지는 댓글 참여 유도(경험/의문) 또는 저장/공유 CTA 멘트 1문장을 대본 마무리에 필수로 직접 작성"하도록 명시.
  - 예시 제시:
    - *"여러분은 어느 쪽인가요? 댓글로 공유해 주세요!"*
    - *"나중에 충동구매 마려울 때 다시 보려면 저장해 두세요!"*
    - *"주변에 자꾸 미루는 친구가 있다면 이 영상을 공유해 보세요!"*

## 2. 스크립트 검증 및 CTA 보장 로직 (`scripts/script_generator.py`)
- `_validate_script()` 개선:
  - AI가 생성한 `cta` / `comment_cta`가 `full_script` 마지막에 자연스럽게 포함되어 있는지 검사.
  - 만약 AI가 `full_script` 끝에 CTA 문구를 생략하고 `cta` 필드에만 따로 적어둔 경우, `full_script` 끝에 문맥이 어색하지 않게 원활히 통합되도록 보장.
  - 매달린 접속사나 불완결 어미로 끝나지 않는지 검증과 조화롭게 동작하도록 처리.

---

## Verification Plan
1. `python -m py_compile scripts/script_generator.py` 문법 검증
2. 스크립트 생성 로직 드라이런/테스트 스크립트 실행하여 생성 결과의 `full_script` 마지막에 자연스러운 CTA가 포함되는지 확인

