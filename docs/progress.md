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

## T3 계보 테이블

- 완료일: 2026-11-11
- 결과: `data/curated/lineage/`에 계보 10개(`lineages.csv`), 연결 39행(`lineage_links.csv`), 근거 45행(`lineage_evidence.csv`), 시즌별 연결 결과와 PU 공급사(`constructor_seasons.parquet`), F1DB와 Jolpica의 팀 ID 대응표(`constructor_crosswalk.csv`). 근거와 판단이 갈리는 지점은 `docs/lineage.md`에 적었다.
- 완료 기준 확인: 범위 조정에 따라 2025 그리드 10개 팀 모두 연결 행마다 근거 URL과 확인일이 있다. 근거 인용문 41건을 실제 페이지와 대조해 모두 통과했다. `renault`, `mercedes` ID 분리 테스트와 `honda`, `alfa`, `aston_martin`, `williams` 분리 테스트가 통과한다.
- 메모: 제외 구간(예: 1954–1955년 `mercedes`)의 근거는 간접 근거다. Tyrrell 포함 여부, 2018년 Force India 참가권 단절, Williams의 시작 연도는 판단이 갈릴 수 있어 문서에 따로 적었다.

## T5 Car Presentation 파서

- 작업일: 2026-11-11
- 결과: `pipeline/parsers/car_presentation.py`, `data/curated/fia/car_presentation.parquet`(855행), `car_presentation_teams.csv`(540행), `car_presentation_documents.csv`(54행), `data/manifests/parse_failures.csv`(1건).
- 완료 기준 확인: 2023–2025년 54개 문서 모두 팀 수 검증을 통과했다. 실패 문서 1건(2024년 라스베이거스, Williams 표가 그림)을 목록에 남겼다. 수동 대조 결과를 `docs/methodology.md`에 적었다.
- 완료 기준에 못 미친 부분: 수동 대조는 문서 10개에서 한 쪽씩만 했고 그중 무작위는 5건이다. 문서 단위 대조는 사람이 한 번 더 하는 편이 좋다.
- 메모: CI는 표본 문서 6건을 manifest에서 다시 받아 파싱 결과가 커밋된 데이터와 같은지 본다.

## T9 OpenF1 수집

- 작업일: 2026-11-11
- 결과: 2023–2025년 그랑프리 본 예선과 결승 140개 세션의 drivers, laps, stints, pit, weather, race_control, session_result를 `data/curated/openf1/`에 실었다(랩 99,523행). 미팅 대응표(`meeting_map.csv`, 70행)와 드라이버 대응표(`driver_map.csv`, 69행)를 만들었다.
- 완료 기준 확인:
  - 요청 제한: 983회를 32분 50초에 걸쳐 보냈다(평균 2.0초 간격, 분당 30회 이하). 429 응답은 없었다. 404 응답 13건은 자료가 없는 세션이다(예선의 pit 12건, 2025년 아제르바이잔 예선의 laps 1건). 로그는 `data/raw/_logs/requests-openf1.csv`에 있고 커밋하지 않는다.
  - 날씨 결측 규칙: 노면 온도, 습도, 기압이 0 이하면 결측으로 바꾼다. 이번 범위에는 해당 값이 없었다(노면 온도 12.0–54.6도).
  - 미팅 대응: 70개 대회 모두 맞췄다. 69개는 UTC 날짜가 같고, 2024년 라스베이거스만 하루 차이 규칙으로 맞췄다. 서킷 대응은 세 시즌에 걸쳐 일대일이다.
  - 드라이버 대응: 차량 번호로 맞춘 68건은 양쪽 약칭이 모두 같다. 1건(2023년 싱가포르의 Stroll)은 결승에 나오지 않아 OpenF1 결승 세션에 없다.
- 완료 기준에 못 미친 부분: 대응표를 사람이 검수하는 단계가 남았다. 자동 대조(약칭 일치)만 했다.
- 메모: 스프린트 예선과 스프린트는 받지 않았다. 지수 계산에 쓰지 않기 때문이다.

## T10 페이스 지수

- 작업일: 2026-11-11
- 결과: `data/curated/pace/qualifying_index.parquet`(1996–2025년 568개 대회, 5,991행), `race_index.parquet`(2023–2025년 70개 대회, 700행).
- 완료 기준 확인: 지표 정의와 계산 대조를 `docs/methodology.md`에 적었다. 퀄리파잉 지수는 API 값으로 손으로 계산한 네 대회와 일치한다. 레이스 지수는 원문 JSON으로 따로 계산한 세 대회와 소수 넷째 자리까지 일치한다.
- 완료 기준과 다른 점: 레이스 지수의 대조는 손 계산이 아니라 다른 코드로 한 재계산이다. 퀄리파잉 지수는 Jolpica만이 아니라 F1DB로 보완했다(1996–2005년과 2025년 마이애미).
- 사용자 결정 대기: 지표 정의 승인, 2022년 이전 우천 플래그 방법, 우천 판정 기준(강우 표본 하나로도 우천 표시).
