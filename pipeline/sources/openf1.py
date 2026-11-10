"""OpenF1 수집기. (T9)

2023년 이후 그랑프리 본 예선과 결승의 세션 상세를 받는다. 과거 데이터만 쓴다.
요청 사이에 2초 이상 간격을 두고 모든 응답을 data/raw/openf1/ 에 캐시한다.

실행: uv run python -m pipeline.sources.openf1 2023 2024 2025
"""

from __future__ import annotations

import json
import sys

from pipeline.http import PoliteClient

API_BASE = "https://api.openf1.org/v1"
SESSION_NAMES = ("Qualifying", "Race")
ENDPOINTS = ("drivers", "laps", "stints", "pit", "weather", "race_control", "session_result")


def fetch_sessions(client: PoliteClient, year: int, *, force: bool = False) -> list[dict]:
    result = client.get(
        f"{API_BASE}/sessions", f"{year}/sessions.json", params={"year": year}, force=force
    )
    return json.loads(result.content.decode("utf-8"))


def collect(years: list[int], *, force: bool = False) -> int:
    """세션 목록과 세션별 엔드포인트를 받는다. 받은(또는 캐시된) 세션 수를 돌려준다."""
    n = 0
    with PoliteClient("openf1") as client:
        for year in years:
            sessions = [
                s
                for s in fetch_sessions(client, year, force=force)
                if s["session_name"] in SESSION_NAMES and not s.get("is_cancelled")
            ]
            for s in sessions:
                key = s["session_key"]
                for endpoint in ENDPOINTS:
                    client.get(
                        f"{API_BASE}/{endpoint}",
                        f"{year}/{key}/{endpoint}.json",
                        params={"session_key": key},
                        force=force,
                        empty_on_404=b"[]",
                    )
                n += 1
                print(f"{year} {s['location']} {s['session_name']} ({key})", flush=True)
    return n


if __name__ == "__main__":
    print(f"{collect([int(a) for a in sys.argv[1:]])} sessions")
