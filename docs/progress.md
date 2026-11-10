# 진행 기록

태스크를 끝낼 때마다 완료일과 결과를 적는다. 태스크 정의와 완료 기준은 `CLAUDE.md`에 있다.

## T0 저장소 초기화

- 완료일: 2026-11-11
- 결과: uv 프로젝트(Python 3.12), Astro 7 스캐폴드(`site/`), pre-commit 로컬 훅, `LICENSE`(MIT), `DATA_LICENSE`(CC BY-NC-SA 4.0), `.gitignore`에 `data/raw/`, CI 워크플로(`.github/workflows/ci.yml`).
- 완료 기준 확인: `uv run pytest` 3개 통과, `npm run build` 통과.
- 메모: 문구 규칙(em dash 금지)과 PDF·`data/raw/` 커밋 금지를 훅과 테스트로 강제한다. 개발 도구로 `pytest`, `ruff`, `pre-commit`을 추가했다.
