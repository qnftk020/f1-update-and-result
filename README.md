# f1-update-and-result

공개 데이터와 FIA 공식 문서를 결합해 F1 팀별 업그레이드와 성능 추이를 보여 주는 비영리 오픈 웹사이트다. 비공식 팬 프로젝트이며 Formula 1, FIA, 각 팀과 관련이 없다.

현재 데이터 범위는 2025 시즌까지다. 진행 상황은 `docs/progress.md`, 데이터원과 라이선스는 `docs/sources.md`, 지표 정의는 `docs/methodology.md`에 있다.

## 실행

```sh
uv sync
uv run pytest                              # 품질 테스트
uv run python -m pipeline.build_site_data  # 사이트 빌드용 JSON 생성
cd site && npm ci && npm run build         # 정적 사이트 빌드
```

커밋 훅은 `uv run pre-commit install`로 설치한다.

## 라이선스

- 코드: MIT (`LICENSE`)
- 데이터: CC BY-NC-SA 4.0 (`DATA_LICENSE`). 비영리 목적으로만 쓸 수 있다.
- FIA 문서 원본은 재배포하지 않는다. 원문 링크와 추출한 구조화 정보만 싣는다.
