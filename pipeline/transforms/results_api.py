"""Jolpica API로 대회 한 건의 결과와 순위를 정제 테이블에 반영한다. (T2 증분 갱신, T13)

초기 적재는 덤프로 하고(pipeline/transforms/results.py), 그 뒤에 열린 대회는 이 모듈로 한 라운드씩
더한다. 같은 라운드를 다시 돌리면 그 라운드의 행을 새 응답으로 갈아 끼운다.

API가 주지 않는 값은 비워 둔다.
- results.status_code: 덤프 내부 분류라 API에 없다. 덤프에 이미 있는 행은 기존 값을 두고,
  새 라운드는 다음 덤프 적재 때 채워진다.
- races.scheduled_laps: API 일정에 없다. 이미 있는 라운드를 갈아 끼울 때는 기존 값을 둔다.
- races.date: API는 결승 시작 시각의 UTC 날짜를 준다. 덤프는 대회의 현지 날짜라 밤 경기(2025
  라스베이거스)에서 하루 다르다. 이미 있는 라운드는 기존 날짜를 두고, 새 라운드만 API 날짜를 쓴다.
- results.time_ms: API는 완주로 분류된 차의 기록만 준다. 리타이어한 차는 비워 둔다.
- 순위표의 adjustment_type: 기본값 0을 넣는다. is_eligible은 순위가 매겨졌는지로 정한다.
- qualifying.position: API는 예선 최종 순위만 준다. 세션별 순위는 그 세션 기록 순으로 매기고,
  기록이 없는 드라이버는 비워 둔다. 스프린트 예선은 API에 없어 손대지 않는다.

실행: uv run python -m pipeline.transforms.results_api 2025 24
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

from pipeline.config import CURATED_DIR
from pipeline.sources import jolpica

ORDER_BY = {
    "races": "season, round",
    "results": "season, round, session_type, position nulls last, driver_id, constructor_id",
    "qualifying": "season, round, session_type, position nulls last, driver_id, constructor_id",
    "driver_standings": "season, round, position nulls last, driver_id",
    "constructor_standings": "season, round, position nulls last, constructor_id",
    "drivers": "driver_id",
    "constructors": "constructor_id",
}
# 갈아 끼울 때 기존 행을 찾는 열
REPLACE_KEY = {
    "races": ["season", "round"],
    "results": ["season", "round"],
    "qualifying": ["season", "round", "session_type"],  # 스프린트 예선(SQ) 행은 건드리지 않는다
    "driver_standings": ["season", "round"],
    "constructor_standings": ["season", "round"],
    "drivers": ["driver_id"],
    "constructors": ["constructor_id"],
}

# 이미 덤프로 적재된 라운드를 API로 다시 반영할 때, API에 없는 값은 같은 행의 기존 값을 둔다.
# (열 목록, 행 키). 기록 없는 Q3 드라이버의 세션 순위는 덤프만 준다.
KEEP_IF_NULL = {
    "results": (["status_code"], ["season", "round", "session_type", "driver_id"]),
    "qualifying": (["position"], ["season", "round", "session_type", "driver_id"]),
}


def lap_ms(text: str | None) -> int | None:
    """'1:22.207' 이나 '58.079' 를 밀리초로 바꾼다."""
    if not text:
        return None
    minutes, _, seconds = text.rpartition(":")
    return round((int(minutes or 0) * 60 + float(seconds)) * 1000)


def to_int(text: str | None) -> int | None:
    return int(text) if text not in (None, "") and str(text).lstrip("-").isdigit() else None


def result_rows(season: int, rnd: int, session_type: str, results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        rows.append(
            {
                "season": season,
                "round": rnd,
                "session_type": session_type,
                "driver_id": r["Driver"]["driverId"],
                "constructor_id": r["Constructor"]["constructorId"],
                "car_number": to_int(r.get("number")),
                "grid": to_int(r.get("grid")),
                "position": to_int(r.get("position")),
                "is_classified": str(r.get("positionText", "")).isdigit(),
                "status_code": None,
                "status_detail": r.get("status"),
                "laps_completed": to_int(r.get("laps")),
                "points": float(r["points"]) if r.get("points") not in (None, "") else None,
                "time_ms": to_int(r.get("Time", {}).get("millis")),
                "fastest_lap_rank": to_int(r.get("FastestLap", {}).get("rank")),
            }
        )
    return rows


def qualifying_rows(season: int, rnd: int, results: list[dict]) -> list[dict]:
    rows = []
    for session in ("Q1", "Q2", "Q3"):
        timed = []
        for r in results:
            if session not in r:
                continue
            timed.append((lap_ms(r[session]), r))
        ranked = sorted((x for x in timed if x[0] is not None), key=lambda x: x[0])
        order = {id(r): n for n, (_, r) in enumerate(ranked, 1)}
        for best, r in timed:
            rows.append(
                {
                    "season": season,
                    "round": rnd,
                    "session_type": session,
                    "driver_id": r["Driver"]["driverId"],
                    "constructor_id": r["Constructor"]["constructorId"],
                    "car_number": to_int(r.get("number")),
                    "position": order.get(id(r)),
                    "best_time_ms": best,
                }
            )
    return rows


def standings_rows(season: int, rnd: int, key: str, items: list[dict]) -> list[dict]:
    id_field = "driver_id" if key == "Driver" else "constructor_id"
    id_key = "driverId" if key == "Driver" else "constructorId"
    return [
        {
            "season": season,
            "round": rnd,
            id_field: item[key][id_key],
            "position": to_int(item.get("position")),
            "points": float(item["points"]),
            "wins": int(item["wins"]),
            "is_eligible": str(item.get("positionText", "")).isdigit(),
            "adjustment_type": 0,
        }
        for item in items
    ]


def race_row(race: dict, has_sprint: bool) -> dict:
    circuit = race["Circuit"]
    start = f"{race['date']} {race['time'].rstrip('Z')}+00:00" if race.get("time") else None
    return {
        "season": int(race["season"]),
        "round": int(race["round"]),
        "race_name": race["raceName"],
        "date": race["date"],
        "circuit_id": circuit["circuitId"],
        "circuit_name": circuit["circuitName"],
        "locality": circuit["Location"]["locality"],
        "country": circuit["Location"]["country"],
        "latitude": float(circuit["Location"]["lat"]),
        "longitude": float(circuit["Location"]["long"]),
        "race_start_utc": start,
        "scheduled_laps": None,
        "has_sprint": has_sprint,
        "wikipedia_url": race.get("url"),
    }


def people_rows(results: list[dict]) -> tuple[list[dict], list[dict]]:
    drivers, constructors = {}, {}
    for r in results:
        d, c = r["Driver"], r["Constructor"]
        drivers[d["driverId"]] = {
            "driver_id": d["driverId"],
            "forename": d.get("givenName"),
            "surname": d.get("familyName"),
            "abbreviation": d.get("code"),
            "permanent_number": to_int(d.get("permanentNumber")),
            "nationality": d.get("nationality"),
            "country_code": None,
            "date_of_birth": d.get("dateOfBirth"),
            "wikipedia_url": d.get("url"),
        }
        constructors[c["constructorId"]] = {
            "constructor_id": c["constructorId"],
            "name": c.get("name"),
            "nationality": c.get("nationality"),
            "country_code": None,
            "wikipedia_url": c.get("url"),
        }
    return list(drivers.values()), list(constructors.values())


def fetch_round(season: int, rnd: int, *, force: bool = False) -> dict[str, list[dict]]:
    """API에서 한 라운드의 표를 모두 받아 정제 테이블의 열 이름으로 맞춘다."""
    schedule = jolpica.fetch_api(f"{season}", force=force)["RaceTable"]["Races"]
    race = next((r for r in schedule if int(r["round"]) == rnd), None)
    if race is None:
        raise RuntimeError(f"{season}년 일정에 {rnd}라운드가 없다")
    has_sprint = "Sprint" in race

    def table(path: str, key: str) -> list[dict]:
        races = jolpica.fetch_api(f"{season}/{rnd}/{path}", force=force)["RaceTable"]["Races"]
        return races[0][key] if races else []

    race_results = table("results", "Results")
    if not race_results:
        raise RuntimeError(f"{season}년 {rnd}라운드 결승 결과가 아직 없다")
    sprint_results = table("sprint", "SprintResults") if has_sprint else []
    quali = table("qualifying", "QualifyingResults")

    def standings(path: str, key: str) -> list[dict]:
        lists = jolpica.fetch_api(f"{season}/{rnd}/{path}", force=force)["StandingsTable"][
            "StandingsLists"
        ]
        return lists[0][f"{key}Standings"] if lists else []

    drivers, constructors = people_rows([*race_results, *sprint_results, *quali])
    return {
        "races": [race_row(race, has_sprint)],
        "results": result_rows(season, rnd, "R", race_results)
        + result_rows(season, rnd, "SR", sprint_results),
        "qualifying": qualifying_rows(season, rnd, quali),
        "driver_standings": standings_rows(
            season, rnd, "Driver", standings("driverstandings", "Driver")
        ),
        "constructor_standings": standings_rows(
            season, rnd, "Constructor", standings("constructorstandings", "Constructor")
        ),
        "drivers": drivers,
        "constructors": constructors,
    }


def upsert(path: Path, name: str, rows: list[dict], *, keep_existing: bool = False) -> int:
    """정제 테이블에서 같은 키의 행을 빼고 새 행을 넣어 다시 쓴다. 열 형식은 기존 파일을 따른다.

    keep_existing이 참이면 이미 있는 키는 건드리지 않고 없는 키만 더한다(드라이버, 팀 목록용).
    돌려주는 값은 실제로 반영한 행 수다. 더할 행이 없으면 파일을 다시 쓰지 않는다.
    """
    if not rows:
        return 0
    con = duckdb.connect()
    schema = con.execute(f"describe select * from '{path}'").fetchall()
    frame = pd.DataFrame(rows)  # noqa: F841  (DuckDB가 변수 이름으로 읽는다)
    casts = ", ".join(f'cast("{col}" as {dtype}) as "{col}"' for col, dtype, *_ in schema)
    keys = REPLACE_KEY[name]
    match = " and ".join(f'old."{k}" = new."{k}"' for k in keys)
    con.execute(f"create temp table new as select {casts} from frame")
    if name in KEEP_IF_NULL:
        # API가 비워 두는 열은 같은 행의 기존 값(덤프)을 둔다. 다시 돌려도 값이 사라지지 않는다.
        cols, row_keys = KEEP_IF_NULL[name]
        same_row = " and ".join(f'old."{k}" = new."{k}"' for k in row_keys)
        for col in cols:
            con.execute(
                f'update new set "{col}" = (select old."{col}" from \'{path}\' old '
                f'where {same_row}) where "{col}" is null'
            )
    if keep_existing:
        con.execute(f"delete from new where exists (select 1 from '{path}' old where {match})")
        applied = con.execute("select count(*) from new").fetchone()[0]
        if not applied:
            return 0
        query = f"select * from '{path}' union all select * from new"
    else:
        applied = len(rows)
        query = (
            f"select * from '{path}' old where not exists (select 1 from new where {match}) "
            "union all select * from new"
        )
    con.execute(f"create temp table merged as select * from ({query}) order by {ORDER_BY[name]}")
    added = f"select count(*) from (select * from merged except all select * from '{path}')"
    dropped = f"select count(*) from (select * from '{path}' except all select * from merged)"
    if con.execute(added).fetchone()[0] == 0 and con.execute(dropped).fetchone()[0] == 0:
        # 같은 라운드를 다시 돌려 내용이 그대로면 파일을 쓰지 않는다(자동 갱신의 빈 커밋 방지).
        return applied
    con.execute(f"copy merged to '{path}' (format parquet, compression zstd)")
    return applied


def keep_race_fields(path: Path, rows: list[dict]) -> list[dict]:
    """이미 있는 라운드는 API가 덤프와 같게 내지 못하는 date, scheduled_laps를 기존 값으로 둔다."""
    con = duckdb.connect()
    kept = []
    for row in rows:
        old = con.execute(
            f"select date, scheduled_laps from '{path}' where season = ? and round = ?",
            [row["season"], row["round"]],
        ).fetchone()
        if old:
            row = {**row, "date": str(old[0]) if old[0] is not None else None,
                   "scheduled_laps": old[1]}  # fmt: skip
        kept.append(row)
    return kept


def apply_tables(tables: dict[str, list[dict]], out_dir: Path = CURATED_DIR) -> dict[str, int]:
    """정제 테이블 열 이름으로 맞춘 행을 테이블별로 반영하고, 반영한 행 수를 돌려준다."""
    counts = {}
    for name, rows in tables.items():
        path = out_dir / "jolpica" / f"{name}.parquet"
        if name == "races":
            rows = keep_race_fields(path, rows)
        counts[name] = upsert(path, name, rows, keep_existing=name in ("drivers", "constructors"))
    return counts


def apply_round(
    season: int, rnd: int, *, out_dir: Path = CURATED_DIR, force: bool = False
) -> dict[str, int]:
    """한 라운드를 API에서 받아 정제 테이블에 반영한다. 테이블별로 반영한 행 수를 돌려준다."""
    return apply_tables(fetch_round(season, rnd, force=force), out_dir)


def completed_rounds(season: int, *, force: bool = False) -> list[int]:
    """API 일정에서 결승 날짜가 지난 라운드 번호."""
    today = pd.Timestamp.now(tz="UTC").date().isoformat()
    schedule = jolpica.fetch_api(f"{season}", force=force)["RaceTable"]["Races"]
    return [int(r["round"]) for r in schedule if r["date"] < today]


if __name__ == "__main__":
    season_arg, round_arg = int(sys.argv[1]), int(sys.argv[2])
    for table_name, n in apply_round(season_arg, round_arg, force="--force" in sys.argv).items():
        print(f"{table_name}: {n} rows")
