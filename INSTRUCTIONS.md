# Project Instructions (프로젝트 진행 지침)

이 파일은 프로젝트 진행 시 AI 에이전트가 반드시 참조하고 준수해야 하는 지침을 담고 있습니다.

## 핵심 지침 (Core Instructions)

1. **대화 및 작업 시작 전 원격 최신화 (Git Pull before work)**
   - 작업 착수 전 반드시 `git fetch origin main && git pull --rebase origin main`을 실행하여 원격의 최신 커밋을 로컬에 반영합니다.

2. **소스 수정은 승인 후 진행 (Source modification only after approval)**
   - 코드를 수정하기 전에 반드시 구현 계획(Implementation Plan)을 작성하고 사용자의 명시적인 승인을 받아야 합니다.
   - 승인되지 않은 소스 코드 수정은 허용되지 않습니다.

3. **모든 기획이 확인 된 후 진행할 것 (Proceed after all plans/requirements are confirmed)**
   - 기획 및 요구사항이 명확하게 확인되고 합의된 후에만 구현 및 수정 작업을 진행합니다.
   - 모호한 부분이 있을 경우 임의로 판단하지 않고 질문을 통해 확인합니다.

4. **API 호출 테스트 금지 (No External API Test Calls)**
   - 로컬 검증이나 테스트 시 Gemini API, Pexels/Pixabay, YouTube API 등 실제 외부 API를 호출하는 코드를 직접 실행하지 마십시오.
   - 문법 컴파일(`py_compile`) 및 오프라인 단위 검증(Mock 데이터 기반)으로만 테스트를 수행합니다.

5. **푸시 전 프로젝트 문서 최신화 (Update docs before push)**
   - 작업 완료 후 커밋/푸시 전 `WORK_LOG.md`, `ROADMAP.md` 등 프로젝트 문서를 반드시 최신화합니다.

---

*주의: 이 지침은 프로젝트 내의 모든 코드 변경, 추가, 삭제 작업에 상시 적용됩니다.*
