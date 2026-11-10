# 데이터원

이 문서는 사이트가 쓰는 모든 데이터원의 범위, 요청 제한, 라이선스, 이용 규칙을 적는다. 각 항목의 근거는 공식 문서 URL로 남기고, 공식 문서에서 확인하지 못한 내용은 "미검증"으로 표시한다.

- 확인일: 2026-11-11
- 현재 데이터 범위: 2025 시즌까지 (`CLAUDE.md`의 범위 조정 참고)

## 요약

| 데이터원 | 쓰는 범위 | 요청 제한 | 라이선스 | 이 프로젝트의 요청 규칙 |
|---|---|---|---|---|
| Jolpica-F1 | 결과·순위 1950–2025, 예선 기록 | 비인증 4회/초, 500회/시간 | CC BY-NC-SA 4.0, 비상업 | 초기 적재는 지연 덤프 1회, API는 0.5초 간격·시간당 450회 이하, 전 응답 캐시 |
| OpenF1 | 세션 상세 2023–2025 | 공식 문서에 수치 없음(미검증) | CC BY-NC-SA 4.0 | 요청 간 2초 이상, 429 응답 시 간격을 늘려 재시도 |
| F1DB | 캘린더 대조, 컨스트럭터 chronology, 엔트런트·엔진 제조사, 예선 기록 | 해당 없음(GitHub 릴리스 파일) | CC BY 4.0 | 릴리스 태그를 고정해 1회 내려받기 |
| Open-Meteo | 2023년 이전 날씨 보조 | 하루 1만 회, 시간당 5천 회, 분당 600회 미만 | CC BY 4.0, 무료 API는 비상업 | 요청 간 1초 이상 |
| FIA 문서 | 대회별 결정 문서, 규정 | 명시된 수치 없음 | FIA 저작물 | 요청 간 3초 이상, PDF 원본은 커밋·재게시 금지 |

## Jolpica-F1

- 주소: `https://api.jolpi.ca/ergast/f1/` (Ergast 호환 API), `https://api.jolpi.ca/data/dumps/download/` (덤프 목록)
- 범위: 결과·순위 1950–, 랩 1996–, 피트스톱 2011–. 덤프의 랩 테이블로 확인한 결과 레이스 랩은 1996년부터 있다.
- 요청 제한: 비인증 접근은 버스트 4회/초, 지속 500회/시간이다. 공식 문서는 이 수치가 앞으로 낮아질 것이라고 밝힌다.
  - 근거: https://github.com/jolpica/jolpica-f1/blob/main/docs/rate_limits.md
- 라이선스: 데이터는 CC BY-NC-SA 4.0이며 API는 비상업 용도로 무료다. 약관 최종 수정일은 2025-08-27이다.
  - 근거: https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md
- 덤프: 무료(비상업) 등급은 업로드 14일 뒤의 지연 덤프를 인증 없이 받을 수 있다. 최신 덤프는 후원자 등급 전용이다. CSV 열 순서는 보장되지 않으므로 열 이름으로 읽는다.
  - 근거: https://github.com/jolpica/jolpica-f1/blob/main/docs/database_dumps.md
- 이 프로젝트가 쓴 덤프: 2026-10-27 업로드분(sha256은 `data/manifests/datasets.csv`). 2025 시즌 24개 대회가 모두 들어 있다.
- 확인한 한계:
  - 예선 기록은 2003년부터 대부분의 대회에 있고 1996–2002년은 일부 대회만 있다(시즌별 수록 대회 수: 1996년 7, 1997년 10, 1998년 7, 1999년 3, 2000년 4, 2001년 1, 2002년 2).
  - 2025년 6라운드(마이애미) 예선은 순위만 있고 기록이 비어 있다. 덤프와 API(`2025/6/qualifying`) 모두 같다.
  - 대회 날짜는 현지 날짜다. 라스베이거스처럼 현지 토요일 밤에 열리는 대회는 UTC 날짜를 쓰는 F1DB와 하루 차이가 난다.
- User-Agent: `f1-update-and-result/<버전>`을 보낸다.

## OpenF1

- 주소: `https://api.openf1.org/v1/`
- 범위: 2023년 이후 세션 상세(랩, 스틴트, 날씨, 레이스 컨트롤, 세션 결과 등).
- 접근 조건: 공식 문서는 "2023년 이후 과거 데이터는 무료이며 인증이 필요 없다. 실시간 데이터는 유료 구독이 필요하다"고 밝힌다.
  - 근거: https://openf1.org/docs
- 요청 제한: 공식 문서에서 수치를 찾지 못했다. 작업서의 "무료 3회/초, 30회/분"은 제3자 사이트에만 나오는 수치라 미검증이다. 이 프로젝트는 그보다 느린 2초 간격을 쓰고, 429 응답을 받으면 간격을 늘려 재시도한다.
- "세션 종료 30분 이후 데이터만 사용" 규칙: 공식 문서에서 30분이라는 기준을 확인하지 못했다(미검증). 현재 범위는 2025 시즌까지의 과거 데이터라 이 규칙에 걸리는 요청이 없다. 2026 시즌으로 넓힐 때 다시 확인한다.
- 라이선스: 저장소의 LICENSE 파일은 CC BY-NC-SA 4.0 전문이다.
  - 근거: https://github.com/br-g/openf1/blob/main/LICENSE
- 비공식 프로젝트이며 F1 관련 상표는 Formula One Licensing B.V. 소유라고 명시한다.

## F1DB

- 주소: https://github.com/f1db/f1db (릴리스의 `f1db-csv.zip`)
- 범위: 1950년 이후 결과, 컨스트럭터 chronology, 시즌별 엔트런트와 엔진 제조사, 예선 기록(형식 구분 포함).
- 라이선스: CC BY 4.0.
  - 근거: https://github.com/f1db/f1db#license , https://creativecommons.org/licenses/by/4.0/
- 이 프로젝트가 쓴 릴리스: `v2026.20.0` (2026-11-09 게시).
- 쓰임: 계보 테이블 초안, 시즌별 레이스 수 대조, Jolpica 예선 기록 결측 보완.
- 주의: 식별자 체계가 Jolpica와 다르다(예: F1DB `red-bull`, Jolpica `red_bull`). 대응표로 연결하고 원자료는 바꾸지 않는다.

## Open-Meteo 과거 날씨

- 주소: https://open-meteo.com/en/docs/historical-weather-api
- 범위: ERA5 재분석(0.25도, 1940년 이후), ERA5-Land(0.1도, 1950년 이후).
- 요청 제한과 조건: 무료 API는 비상업 용도에 한해 하루 1만 회, 시간당 5천 회, 분당 600회 미만으로 쓸 수 있고, CC BY 4.0 표시 조건을 따른다.
  - 근거: https://open-meteo.com/en/terms
- 표기 규칙: 지역 기상 재분석 값이며 노면 온도가 아님을 화면에 적는다.
- 상태: 아직 수집하지 않았다. 2023년 이전 우천 플래그가 필요해질 때 쓴다.

## FIA 문서

- 주소: https://www.fia.com/documents (대회별 결정 문서), 규정 아카이브는 T8에서 정리한다.
- 요청 규칙: 요청 간 3초 이상. PDF 원본은 저장소에 커밋하거나 사이트에 재게시하지 않는다. 원문 링크와 추출한 구조화 정보만 싣고, 원문의 URL·수집 시각·sha256을 `data/manifests/`에 남긴다.
- FIA 사이트의 이용 약관 문구는 아직 확인하지 못했다(미검증). 위 규칙은 작업서의 보수적 기준을 따른 것이다.
- 2026-11-11에 실제 응답으로 확인한 구조:
  - 결정 문서 페이지의 시즌 선택 목록은 2019–2026년과 2015년이다.
  - 대회별 주소 형식: `https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-<연도>-<번호>/event/<대회명>`
  - 2025년 문서는 `/system/files/decision-document/` 아래에, 2024년 이전 문서는 `/sites/default/files/decision-document/` 아래에 있다.
- 문서별 공개 경로:

| 문서 | 확인한 범위 | 경로 |
|---|---|---|
| Car Presentation Submissions | 2025년 24개 대회 전부, 2024년 23개 대회 | 대회별 결정 문서 목록 |
| Car Presentation Submissions | 2023년 7개 대회(오스트리아, 벨기에, 네덜란드, 이탈리아, 싱가포르, 카타르, 멕시코시티) | FIA 뉴스 "F1 – Tech updates at the ... Grand Prix"의 첨부 PDF. 예: https://www.fia.com/news/f1-tech-updates-qatar-grand-prix |
| New PU elements for this Event/Competition | 2020–2025년 | 대회별 결정 문서 목록 |
| PU elements used per driver up to now | 2020–2025년(시즌 첫 대회에는 없는 해가 많다) | 대회별 결정 문서 목록 |
| Car Display Procedure | 2022–2025년(2022년 명칭은 Automobile Display Procedure) | 대회별 결정 문서 목록 |

- 문서 목록 전체는 `data/manifests/fia_documents.csv`에 있다(2020–2025년 135개 대회 페이지, 7,129건).
- Car Presentation을 찾지 못한 대회:
  - 2024년 바레인: 결정 문서 목록에 없고 뉴스 주소(`/news/f1-tech-updates-bahrain-grand-prix`)도 없다.
  - 2023년 15개 대회: 바레인부터 캐나다까지 여덟 대회와 일본, 라스베이거스, 상파울루, 아부다비는 뉴스 주소가 없다. 영국, 헝가리, 미국은 뉴스 글은 있으나 첨부 PDF가 없다. 첨부 파일명 규칙(`<번호>_<국가 코드>_car_presentation_submissions.pdf`)으로도 확인했지만 없었다.
  - 따라서 fia.com에서 받을 수 있는 업그레이드 목록은 2023년 오스트리아 대회부터이고, 2023년은 일부만 있다.
- 대회 페이지의 문서 행 마크업은 두 가지다(제목에 필드 래퍼가 있는 것과 없는 것). 인덱서는 둘 다 읽고, 문서 행이 있는데 하나도 읽지 못하면 실패로 처리한다.
- 2022년 업그레이드 목록은 결정 문서 목록에서 찾지 못했다. 경로 조사는 T18이다.

## 쓰지 않는 데이터

- FastF1: Formula 1이 라이브 타이밍 아카이브에 인증을 요구하기 시작했고, FastF1은 v3.9.0(2026-10-24)부터 F1TV Access 이상 계정 로그인을 지원한다. 개인 구독으로 받은 데이터를 재배포할 수 없으므로 FastF1 데이터는 공개 데이터셋과 사이트에 넣지 않는다.
  - 근거: https://github.com/theOehrly/Fast-F1/releases/tag/v3.9.0
- 언론 기사 본문, F1·FIA·팀의 로고와 공식 이미지.
