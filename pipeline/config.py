"""파이프라인 공통 설정: 경로, 범위, 데이터원별 요청 규칙."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # gitignore, 커밋 금지
CURATED_DIR = DATA_DIR / "curated"
MANIFEST_DIR = DATA_DIR / "manifests"
SITE_DATA_DIR = REPO_ROOT / "site" / "src" / "data" / "generated"

APP_NAME = "f1-update-and-result"
APP_VERSION = "0.1.0"
USER_AGENT = f"{APP_NAME}/{APP_VERSION}"

# 데이터 범위. 2026-11-11 결정: 우선 2025 시즌까지만 다룬다 (CLAUDE.md "범위 조정" 참고).
FIRST_SEASON = 1950
LAST_SEASON = 2025
OPENF1_FIRST_SEASON = 2023
CAR_PRESENTATION_FIRST_SEASON = 2023
PU_ELEMENTS_FIRST_SEASON = 2020

# 요청 간 최소 간격(초). 근거는 docs/sources.md.
MIN_INTERVAL_SECONDS = {
    "jolpica": 0.5,  # 공식 제한 4회/초, 500회/시간. 시간당 제한은 클라이언트에서 따로 센다.
    "openf1": 2.0,
    # 작업서 기준은 3초 이상이다. 2026-11-11에 3초 간격으로 100여 건을 잇달아 받은 뒤
    # Cloudflare 확인 화면(429)을 받아 8초로 늘렸다(docs/sources.md).
    "fia": 8.0,  # www.fia.com
    "fia_argent": 8.0,  # argent.fia.com (구 서버)
    "fia_historic": 8.0,  # historicdb.fia.com
    "web": 3.0,  # 그 밖의 제3자 페이지(링크 확인용)
    "f1db": 1.0,
    "openmeteo": 1.0,
}
MAX_REQUESTS_PER_HOUR = {
    "jolpica": 450,  # 공식 500회/시간보다 낮게 잡는다.
    # www.fia.com은 파일 요청이 한 시간에 100건을 넘으면 확인 화면(429)을 띄운다(2026-11-11 관찰,
    # 공식 문서에 없는 수치라 미검증). 그보다 낮게 잡는다.
    "fia": 80,
}
