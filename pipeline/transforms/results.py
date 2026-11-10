"""Jolpica 덤프와 F1DB 릴리스에서 정제 테이블(Parquet)을 만든다. (T2)

원자료의 식별자와 값은 바꾸지 않는다. 팀 계보 연결은 lineage 테이블에서 따로 한다.

실행: uv run python -m pipeline.transforms.results
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from pipeline.config import CURATED_DIR, FIRST_SEASON, LAST_SEASON
from pipeline.sources import f1db, jolpica

JOLPICA_TABLES = [
    "season", "round", "session", "sessionentry", "roundentry", "team", "teamdriver",
    "driver", "circuit", "driverchampionship", "teamchampionship", "lap",
]  # fmt: skip

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
}

F1DB_FILES = {
    "f1db_races": "f1db-races.csv",
    "f1db_constructors": "f1db-constructors.csv",
    "f1db_constructors_chronology": "f1db-constructors-chronology.csv",
    "f1db_seasons_entrants_constructors": "f1db-seasons-entrants-constructors.csv",
    "f1db_entrants": "f1db-entrants.csv",
    "f1db_engine_manufacturers": "f1db-engine-manufacturers.csv",
    "f1db_qualifying": "f1db-races-qualifying-results.csv",
}


def connect(jolpica_dir: Path, f1db_dir: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
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
    con.execute(ENTRY_VIEW.format(first=FIRST_SEASON, last=LAST_SEASON))
    return con


def build(out_dir: Path = CURATED_DIR) -> dict[str, int]:
    con = connect(jolpica.download_dump(), f1db.download_release())
    counts: dict[str, int] = {}
    for name, sql in OUTPUTS.items():
        path = out_dir / f"{name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        query = sql.format(first=FIRST_SEASON, last=LAST_SEASON)
        con.execute(f"copy ({query}) to '{path}' (format parquet, compression zstd)")
        counts[name] = con.execute(f"select count(*) from '{path}'").fetchone()[0]
    return counts


if __name__ == "__main__":
    for name, n in build().items():
        print(f"{name}: {n} rows")
