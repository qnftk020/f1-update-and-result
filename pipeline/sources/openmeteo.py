"""Open-Meteo 과거 날씨 수집기. (T9 보조, T10)

2014-2022년 결승의 우천 여부를 판정하는 데 쓴다(OpenF1 날씨 자료는 2023년부터다). ERA5 재분석의
시간별 강수량이며 지역 기상이지 노면 상태가 아니다(docs/sources.md, docs/methodology.md).

- 주소: https://archive-api.open-meteo.com/v1/archive
- 이용 조건: 비상업 무료, CC BY 4.0 표시. https://open-meteo.com/en/terms
- 요청 간 1초 이상(pipeline/config.py). 모든 응답을 data/raw/openmeteo/ 에 캐시한다.

실행: uv run python -m pipeline.sources.openmeteo 2014 2022
"""

from __future__ import annotations

import json
import sys

from pipeline.http import PoliteClient

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
MODEL = "era5"  # 0.25도 ERA5. 모델을 고정해 다시 받아도 같은 값이 나오게 한다
HOURLY = "precipitation,rain"


def race_hourly(season: int, round_: int, latitude: float, longitude: float, date: str) -> dict:
    """결승 날(UTC 기준 그날과 다음 날)의 시간별 강수량 응답(JSON)을 돌려준다."""
    from datetime import date as Date
    from datetime import timedelta

    end = (Date.fromisoformat(date) + timedelta(days=1)).isoformat()
    params = {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "start_date": date,
        "end_date": end,
        "hourly": HOURLY,
        "models": MODEL,
        "timezone": "GMT",
    }
    with PoliteClient("openmeteo") as client:
        result = client.get(ARCHIVE_URL, f"archive/{season}/{round_:02d}.json", params=params)
    return json.loads(result.content.decode("utf-8"))


def race_day(race_start_utc: object, date: object) -> str:
    """결승 날짜(UTC). 결승 시각이 없으면 대회 날짜를 쓴다."""
    import pandas as pd

    if pd.notna(race_start_utc) and str(race_start_utc):
        return pd.Timestamp(race_start_utc).tz_convert("UTC").date().isoformat()
    return pd.Timestamp(date).date().isoformat()


def fetch_seasons(first: int, last: int) -> int:
    """Jolpica 대회 목록(서킷 좌표, 결승 날짜)으로 시즌 범위의 결승 날씨를 받는다."""
    import pandas as pd

    from pipeline.config import CURATED_DIR

    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    races = races[races["season"].between(first, last)]
    n = 0
    for r in races.itertuples():
        day = race_day(r.race_start_utc, r.date)
        race_hourly(int(r.season), int(r.round), float(r.latitude), float(r.longitude), day)
        n += 1
    return n


if __name__ == "__main__":
    first, last = (int(a) for a in sys.argv[1:3])
    print(f"openmeteo: {fetch_seasons(first, last)} races")
