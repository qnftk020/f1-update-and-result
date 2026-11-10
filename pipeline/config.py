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
    "fia": 3.0,
    "f1db": 1.0,
    "openmeteo": 1.0,
}
MAX_REQUESTS_PER_HOUR = {
    "jolpica": 450,  # 공식 500회/시간보다 낮게 잡는다.
}
