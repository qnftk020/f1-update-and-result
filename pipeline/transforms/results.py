"""Jolpica 덤프와 F1DB 릴리스에서 정제 테이블(Parquet)을 만든다. (T2)

원자료의 식별자와 값은 바꾸지 않는다. 팀 계보 연결은 lineage 테이블에서 따로 한다.

실행: uv run python -m pipeline.transforms.results [표 이름 ...]
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from pipeline.config import CURATED_DIR, FIRST_SEASON, LAST_SEASON
from pipeline.sources import f1db, jolpica

JOLPICA_TABLES = [
    "season", "round", "session", "sessionentry", "roundentry", "team", "teamdriver",
    "driver", "circuit", "driverchampionship", "teamchampionship", "lap", "pitstop",
]  # fmt: skip
# 결승 랩과 피트스톱을 싣는 첫 시즌. 2014-2022년 레이스 페이스 지수(Jolpica 계열)와 2023-2025년
# 대조에 쓴다(pipeline/transforms/race_index_jolpica.py). 2013년 이전은 규정에 경주 연료 상한이
# 없어 연료 보정 근거가 없다.
RACE_LAPS_FIRST_SEASON = 2014

# "HH:MM:SS.fff" 문자열을 밀리초 정수로 바꾼다.
TO_MS = """
create or replace macro to_ms(t) as case when t is null then null else cast(round((
    cast(split_part(t, ':', 1) as double) * 3600
  + cast(split_part(t, ':', 2) as double) * 60
  + cast(split_part(t, ':', 3) as double)) * 1000) as bigint) end
"""

ENTRY_VIEW = """
create or replace view entry as
select s.year::int as season, r.number::int as round, se.type as session_type,
       se.number::int as session_number, e.id as entry_id,
       d.reference as driver_id, t.reference as constructor_id,
       try_cast(re.car_number as int) as car_number,
       try_cast(e.position as int) as position, try_cast(e.grid as int) as grid,
       e.is_classified = 't' as is_classified, try_cast(e.status as int) as status_code,
       e.detail as status_detail, try_cast(e.laps_completed as int) as laps_completed,
       try_cast(e.points as double) as points, to_ms(e.time) as time_ms,
       try_cast(e.fastest_lap_rank as int) as fastest_lap_rank
from sessionentry e
join session se on se.id = e.session_id
join round r on r.id = se.round_id
join season s on s.id = r.season_id
join roundentry re on re.id = e.round_entry_id
join teamdriver td on td.id = re.team_driver_id
join driver d on d.id = td.driver_id
join team t on t.id = td.team_id
where r.is_cancelled = 'f' and s.year::int between {first} and {last}
"""

OUTPUTS: dict[str, str] = {
    "jolpica/races": """
        select s.year::int as season, r.number::int as round, r.name as race_name,
               r.date::date as date, c.reference as circuit_id, c.name as circuit_name,
               c.locality, c.country, c.latitude::double as latitude,
               c.longitude::double as longitude,
               (select min(se.timestamp) from session se
                 where se.round_id = r.id and se.type = 'R') as race_start_utc,
               (select max(try_cast(se.scheduled_laps as int)) from session se
                 where se.round_id = r.id and se.type = 'R') as scheduled_laps,
               exists (select 1 from session se
                        where se.round_id = r.id and se.type = 'SR') as has_sprint,
               r.wikipedia as wikipedia_url
        from round r join season s on s.id = r.season_id join circuit c on c.id = r.circuit_id
        where r.is_cancelled = 'f' and s.year::int between {first} and {last}
        order by season, round
    """,
    "jolpica/results": """
        select season, round, session_type, driver_id, constructor_id, car_number, grid,
               position, is_classified, status_code, status_detail, laps_completed, points,
               time_ms, fastest_lap_rank
        from entry where session_type in ('R', 'SR')
        order by season, round, session_type, position nulls last, driver_id, constructor_id
    """,
    "jolpica/qualifying": """
        select e.season, e.round, e.session_type, e.driver_id, e.constructor_id, e.car_number,
               e.position, min(to_ms(l.time)) as best_time_ms
        from entry e
        left join lap l on l.session_entry_id = e.entry_id
                       and l.is_entry_fastest_lap = 't' and l.is_deleted = 'f'
        where e.session_type in ('QB', 'QO', 'QA', 'Q1', 'Q2', 'Q3', 'SQ1', 'SQ2', 'SQ3')
        group by all
        order by e.season, e.round, e.session_type, e.position nulls last, e.driver_id,
                 e.constructor_id
    """,
    "jolpica/race_laps": """
        select e.season, e.round, e.driver_id, e.constructor_id, e.car_number,
               l.number::int as lap, to_ms(l.time) as time_ms,
               try_cast(l.position as int) as position
        from entry e join lap l on l.session_entry_id = e.entry_id
        where e.session_type = 'R' and e.season >= {race_laps_first} and l.is_deleted = 'f'
          and l.number is not null
        order by e.season, e.round, e.car_number, lap
    """,
    "jolpica/pitstops": """
        select e.season, e.round, e.driver_id, e.constructor_id, e.car_number,
               p.number::int as stop, l.number::int as lap, to_ms(p.duration) as duration_ms
        from pitstop p join lap l on l.id = p.lap_id
        join entry e on e.entry_id = p.session_entry_id
        where e.session_type = 'R' and e.season >= {race_laps_first}
        order by e.season, e.round, e.car_number, stop
    """,
    "jolpica/driver_standings": """
        with ranked as (
            select dc.*, row_number() over (
                partition by dc.year, dc.round_number, dc.driver_id
                order by dc.session_number::int desc) as rn
            from driverchampionship dc)
        select k.year::int as season, k.round_number::int as round, d.reference as driver_id,
               try_cast(k.position as int) as position, k.points::double as points,
               k.win_count::int as wins, k.is_eligible = 't' as is_eligible,
               k.adjustment_type::int as adjustment_type
        from ranked k join driver d on d.id = k.driver_id
        where k.rn = 1 and k.year::int between {first} and {last}
        order by season, round, position nulls last, driver_id
    """,
    "jolpica/constructor_standings": """
        with ranked as (
            select tc.*, row_number() over (
                partition by tc.year, tc.round_number, tc.team_id
                order by tc.session_number::int desc) as rn
            from teamchampionship tc)
        select k.year::int as season, k.round_number::int as round,
               t.reference as constructor_id, try_cast(k.position as int) as position,
               k.points::double as points, k.win_count::int as wins,
               k.is_eligible = 't' as is_eligible, k.adjustment_type::int as adjustment_type
        from ranked k join team t on t.id = k.team_id
        where k.rn = 1 and k.year::int between {first} and {last}
        order by season, round, position nulls last, constructor_id
    """,
    "jolpica/drivers": """
        select reference as driver_id, forename, surname, abbreviation,
               try_cast(permanent_car_number as int) as permanent_number, nationality,
               country_code, try_cast(date_of_birth as date) as date_of_birth,
               wikipedia as wikipedia_url
        from driver order by driver_id
    """,
    "jolpica/constructors": """
        select reference as constructor_id, name, nationality, country_code,
               wikipedia as wikipedia_url
        from team order by constructor_id
    """,
    "f1db/races": """
        select year::int as season, round::int as round, date::date as date,
               grandPrixId as grand_prix_id, officialName as official_name,
               qualifyingFormat as qualifying_format, circuitId as circuit_id,
               try_cast(laps as int) as laps
        from f1db_races where year::int between {first} and {last} order by season, round
    """,
    "f1db/constructors": """
        select id as f1db_constructor_id, name, fullName as full_name, countryId as country_id
        from f1db_constructors order by id
    """,
    "f1db/constructors_chronology": """
        select parentConstructorId as parent_constructor_id,
               positionDisplayOrder::int as position_display_order,
               constructorId as f1db_constructor_id, yearFrom::int as year_from,
               try_cast(yearTo as int) as year_to
        from f1db_constructors_chronology order by 1, 2
    """,
    "f1db/season_entrants": """
        select sec.year::int as season, sec.entrantId as entrant_id, en.name as entrant_name,
               sec.constructorId as f1db_constructor_id,
               sec.engineManufacturerId as engine_manufacturer_id
        from f1db_seasons_entrants_constructors sec
        left join f1db_entrants en on en.id = sec.entrantId
        where sec.year::int between {first} and {last}
        order by season, entrant_id, f1db_constructor_id, engine_manufacturer_id
    """,
    "f1db/qualifying": """
        select year::int as season, round::int as round, driverId as f1db_driver_id,
               constructorId as f1db_constructor_id,
               engineManufacturerId as engine_manufacturer_id,
               try_cast(positionNumber as int) as position,
               try_cast(timeMillis as bigint) as time_ms, try_cast(q1Millis as bigint) as q1_ms,
               try_cast(q2Millis as bigint) as q2_ms, try_cast(q3Millis as bigint) as q3_ms
        from f1db_qualifying where year::int between {first} and {last}
        order by season, round, positionDisplayOrder::int
    """,
    "f1db/engine_manufacturers": """
        select id as engine_manufacturer_id, name, countryId as country_id
        from f1db_engine_manufacturers order by id
    """,
    # 참가 팀(entrant)별로 시즌에 등록한 섀시와 엔진. 몇 라운드부터 썼는지는 F1DB에 없다.
    "f1db/season_entrant_chassis": """
        select sec.year::int as season, sec.entrantId as entrant_id, en.name as entrant_name,
               sec.constructorId as f1db_constructor_id,
               sec.engineManufacturerId as engine_manufacturer_id,
               sec.chassisId as chassis_id, ch.name as chassis_name,
               ch.fullName as chassis_full_name
        from f1db_seasons_entrants_chassis sec
        left join f1db_entrants en on en.id = sec.entrantId
        left join f1db_chassis ch on ch.id = sec.chassisId
        where sec.year::int between {first} and {last}
        order by season, entrant_id, f1db_constructor_id, engine_manufacturer_id, chassis_id
    """,
    "f1db/season_entrant_engines": """
        select see.year::int as season, see.entrantId as entrant_id, en.name as entrant_name,
               see.constructorId as f1db_constructor_id,
               see.engineManufacturerId as engine_manufacturer_id,
               see.engineId as engine_id, eg.name as engine_name,
               eg.fullName as engine_full_name, try_cast(eg.capacity as double) as capacity,
               eg.configuration, eg.aspiration
        from f1db_seasons_entrants_engines see
        left join f1db_entrants en on en.id = see.entrantId
        left join f1db_engines eg on eg.id = see.engineId
        where see.year::int between {first} and {last}
        order by season, entrant_id, f1db_constructor_id, engine_manufacturer_id, engine_id
    """,
    # 결승 결과 행의 차 번호와 컨스트럭터·엔진 제조사. Jolpica 컨스트럭터 ID와 F1DB ID를
    # 대회와 차 번호로 맞추는 데 쓴다(pipeline/site_constructors.py).
    "f1db/race_entries": """
        select year::int as season, round::int as round,
               try_cast(driverNumber as int) as car_number, driverId as f1db_driver_id,
               constructorId as f1db_constructor_id,
               engineManufacturerId as engine_manufacturer_id
        from f1db_race_results where year::int between {first} and {last}
        order by season, round, positionDisplayOrder::int
    """,
}

F1DB_FILES = {
    "f1db_races": "f1db-races.csv",
    "f1db_constructors": "f1db-constructors.csv",
    "f1db_constructors_chronology": "f1db-constructors-chronology.csv",
    "f1db_seasons_entrants_constructors": "f1db-seasons-entrants-constructors.csv",
    "f1db_entrants": "f1db-entrants.csv",
    "f1db_engine_manufacturers": "f1db-engine-manufacturers.csv",
    "f1db_qualifying": "f1db-races-qualifying-results.csv",
    "f1db_seasons_entrants_chassis": "f1db-seasons-entrants-chassis.csv",
    "f1db_seasons_entrants_engines": "f1db-seasons-entrants-engines.csv",
    "f1db_chassis": "f1db-chassis.csv",
    "f1db_engines": "f1db-engines.csv",
    "f1db_race_results": "f1db-races-race-results.csv",
}


def connect(jolpica_dir: Path | None, f1db_dir: Path) -> duckdb.DuckDBPyConnection:
    """jolpica_dir가 None이면 F1DB 뷰만 만든다(F1DB 표만 다시 만들 때)."""
    con = duckdb.connect()
    if jolpica_dir is not None:
        for t in JOLPICA_TABLES:
            con.execute(
                f"create view {t} as select * from "
                f"read_csv('{jolpica_dir}/formula_one_{t}.csv', all_varchar=true, header=true)"
            )
    for view, filename in F1DB_FILES.items():
        con.execute(
            f"create view {view} as select * from "
            f"read_csv('{f1db_dir}/{filename}', all_varchar=true, header=true)"
        )
    con.execute(TO_MS)
    if jolpica_dir is not None:
        con.execute(ENTRY_VIEW.format(first=FIRST_SEASON, last=LAST_SEASON))
    return con


def build(
    out_dir: Path = CURATED_DIR, only: list[str] | None = None, recorded_dump: bool = False
) -> dict[str, int]:
    """정제 테이블을 만든다. only를 주면 그 이름의 표만 만든다.

    only가 모두 f1db/ 표면 Jolpica 덤프를 다시 확인하지 않는다(덤프 목록 요청과 manifest 갱신 없음).
    recorded_dump가 참이면 덤프 목록을 요청하지 않고 manifest에 적힌 덤프(로컬)를 쓴다. 새 덤프로
    다른 표가 바뀌지 않게 표 몇 개만 더할 때 쓴다.
    """
    names = only or list(OUTPUTS)
    unknown = [n for n in names if n not in OUTPUTS]
    if unknown:
        raise KeyError(f"없는 표: {unknown}")
    f1db_only = all(n.startswith("f1db/") for n in names)
    if f1db_only:
        dump = None
    elif recorded_dump:
        dump = jolpica.recorded_dump_dir()
    else:
        dump = jolpica.download_dump()
    con = connect(dump, f1db.download_release())
    counts: dict[str, int] = {}
    for name in names:
        sql = OUTPUTS[name]
        path = out_dir / f"{name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        query = sql.format(
            first=FIRST_SEASON, last=LAST_SEASON, race_laps_first=RACE_LAPS_FIRST_SEASON
        )
        con.execute(f"copy ({query}) to '{path}' (format parquet, compression zstd)")
        counts[name] = con.execute(f"select count(*) from '{path}'").fetchone()[0]
    return counts


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    names = [a for a in args if not a.startswith("--")] or None
    for name, n in build(only=names, recorded_dump="--recorded-dump" in args).items():
        print(f"{name}: {n} rows")
