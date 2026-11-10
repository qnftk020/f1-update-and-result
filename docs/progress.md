# 진행 기록

태스크를 끝낼 때마다 완료일과 결과를 적는다. 태스크 정의와 완료 기준은 `CLAUDE.md`에 있다.

## T0 저장소 초기화

- 완료일: 2026-11-11
- 결과: uv 프로젝트(Python 3.12), Astro 7 스캐폴드(`site/`), pre-commit 로컬 훅, `LICENSE`(MIT), `DATA_LICENSE`(CC BY-NC-SA 4.0), `.gitignore`에 `data/raw/`, CI 워크플로(`.github/workflows/ci.yml`).
- 완료 기준 확인: `uv run pytest` 3개 통과, `npm run build` 통과.
- 메모: 문구 규칙(em dash 금지)과 PDF·`data/raw/` 커밋 금지를 훅과 테스트로 강제한다. 개발 도구로 `pytest`, `ruff`, `pre-commit`을 추가했다.

## T1 데이터원 문서

- 완료일: 2026-11-11
- 결과: `docs/sources.md`. 다섯 데이터원의 범위, 제한, 라이선스, 요청 규칙을 공식 문서 URL과 함께 적었다.
- 확인한 사실: Jolpica 요청 제한과 라이선스, 지연 덤프 조건, F1DB 라이선스, Open-Meteo 무료 조건, FastF1 v3.9.0의 F1TV 로그인 요구, 2023년 Car Presentation의 FIA 뉴스 첨부 경로.
- 미검증으로 남긴 항목: OpenF1 요청 제한 수치와 "세션 종료 30분" 기준(공식 문서에 없음), fia.com 이용 약관 문구.

## T2 결과·순위 적재

- 완료일: 2026-11-11
- 결과: Jolpica 지연 덤프(2026-10-27 업로드분)에서 1950–2025년 races 1,149건, results 26,353행, qualifying 21,729행, 드라이버 순위 34,620행, 컨스트럭터 순위 13,481행을 `data/curated/jolpica/`에 적재했다. F1DB `v2026.20.0`에서 캘린더, 컨스트럭터, chronology, 시즌 엔트런트, 예선 기록을 `data/curated/f1db/`에 적재했다.
- 완료 기준 확인: 범위 조정에 따라 2025년 24라운드(최종전)까지 적재했다. 시즌별 레이스 수는 독립 출처인 F1DB 캘린더와 76개 시즌 모두 일치한다. 2025 최종전 결과는 API 응답과 일치한다.
- 발견한 문제: Jolpica 예선 기록은 1996–2002년에 일부 대회만 있고 2025년 6라운드(마이애미)는 기록이 비어 있다. 퀄리파잉 지수는 F1DB로 보완한다(`docs/methodology.md`).
- 남은 일: API 증분 갱신을 정제 테이블에 반영하는 경로는 T13에서 만든다. 지금은 API 수집 함수와 대조 테스트만 있다.

## 페이스 지수 정의 초안

- 작성일: 2026-11-11
- 결과: `docs/methodology.md`에 퀄리파잉·레이스 페이스 지수의 계산식, 형식별 처리, 클린 랩 조건, 연료 보정 가정, 한계를 적었다. 사용자 검토 대기 상태다.

## T4 FIA 문서 인덱서

- 완료일: 2026-11-11
- 결과: `pipeline/sources/fia_docs.py`, `data/manifests/fia_documents.csv`. 2020–2025년 135개 대회 페이지에서 문서 7,129건의 제목, URL, 게시 시각을 모으고 Car Presentation, PU elements(신규·누적), Car Display Procedure로 분류했다. Car Presentation PDF 54건은 로컬 캐시에 받고 sha256을 manifest에 적었다.
- 완료 기준 확인: 범위 조정에 따라 2024–2025년을 확인했다. 2025년은 24개 대회 전부, 2024년은 바레인을 뺀 23개 대회의 Car Presentation URL을 확보했다.
- 완료 기준에 못 미친 부분: 2024년 바레인 문서는 fia.com에서 찾지 못했다. 2023년은 뉴스 첨부 경로로 7개 대회만 확인됐다(`docs/sources.md`).

## T3 계보 테이블 (진행 중)

- 상태: 초안과 테스트까지 끝났고 근거 URL 검증이 남았다.
- 결과: `data/curated/lineage/`에 계보 10개(`lineages.csv`), 연결 39행(`lineage_links.csv`), 시즌별 연결 결과(`constructor_seasons.parquet`), F1DB와 Jolpica의 팀 ID 대응표(`constructor_crosswalk.csv`). `renault`, `mercedes`, `honda`, `alfa`, `aston_martin`, `williams` ID 분리 사례 테스트가 통과한다.
- 남은 일: 연결 행마다 근거 URL과 확인일을 붙이고 `docs/lineage.md`를 쓴다.

## T9 OpenF1 수집 (진행 중)

- 상태: 수집기와 변환 코드는 끝났고 2023–2025년 본 예선·결승 140개 세션을 2초 간격으로 받는 중이다.
- 남은 일: 수집이 끝나면 정제 테이블과 미팅·드라이버 대응표를 만들고 대응표를 사람이 검수한다.

## T10 페이스 지수 (진행 중)

- 상태: 퀄리파잉 지수는 1996–2025년 568개 대회, 5,991행을 계산해 `data/curated/pace/qualifying_index.parquet`에 실었다. 수기 계산 1건(2025년 1라운드 레드불 0.513%)과 일치한다. 레이스 지수는 코드를 쓰고 2023년 초반 13개 대회로 동작을 확인했다.
- 발견한 문제: 2022년 이전 우천 예선(예: 2016년 헝가리, 2020년 튀르키예)은 지수가 15–34%까지 벌어진다. 우천 플래그 자료가 없어 아직 걸러 내지 못한다.
- 남은 일: OpenF1 수집이 끝나면 레이스 지수 전체 계산, 우천 플래그, 수기 계산 3건 대조.
