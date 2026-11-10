"""페이스 지수 계산. (T10) 정의는 docs/methodology.md 를 따른다.

실행: uv run python -m pipeline.transforms.pace_index
"""

from __future__ import annotations

import duckdb

from pipeline.config import CURATED_DIR, LAST_SEASON

J = CURATED_DIR / "jolpica"
F = CURATED_DIR / "f1db"
PACE = CURATED_DIR / "pace"
CROSSWALK = CURATED_DIR / "lineage" / "constructor_crosswalk.csv"

QUALIFYING_FIRST_SEASON = 1996
JOLPICA_FIRST_SEASON = 2006  # 이전 형식은 F1DB의 그리드 결정 기록을 쓴다
REFERENCE_FORMATS = ("ONE_LAP", "AGGREGATE")  # 결승 연료 원랩, 합산 기록: 참고용

QUALIFYING_SQL = f"""
with jq as (  -- Jolpica: 드라이버별 Q1-Q3 최솟값
    select season, round, constructor_id, driver_id, min(best_time_ms) as best_ms
    from '{J}/qualifying.parquet'
    where session_type in ('Q1', 'Q2', 'Q3') and season >= {JOLPICA_FIRST_SEASON}
    group by all
),
j_ok as (  -- 참가자의 80% 이상에 기록이 있는 대회만 Jolpica를 쓴다
    select season, round from jq group by 1, 2
    having count(best_ms) >= 0.8 * count(*)
),
fq as (  -- F1DB: 드라이버별 기록(그리드 결정 기록 또는 Q1-Q3 최솟값)
    select season, round, f1db_constructor_id, f1db_driver_id,
           least(time_ms, q1_ms, q2_ms, q3_ms) as best_ms
    from '{F}/qualifying.parquet' where season >= {QUALIFYING_FIRST_SEASON}
),
teams_in_round as (
    select distinct season, round, constructor_id from '{J}/results.parquet'
    where session_type = 'R'
),
xwalk as (
    select f1db_constructor_id, season_from::int as season_from, season_to::int as season_to,
           constructor_id
    from read_csv('{CROSSWALK}', header = true, all_varchar = true)
),
f_mapped as (  -- F1DB ID를 Jolpica ID로. 대응표에 후보가 여럿이면 그 대회 결과에 있는 것을 고른다
    select f.season, f.round, f.f1db_driver_id as driver_id, f.best_ms,
           coalesce(
               (select x.constructor_id from xwalk x
                 where x.f1db_constructor_id = f.f1db_constructor_id
                   and f.season between x.season_from and x.season_to
                 order by exists (select 1 from teams_in_round t
                                   where t.season = f.season and t.round = f.round
                                     and t.constructor_id = x.constructor_id) desc,
                          x.constructor_id
                 limit 1),
               replace(f.f1db_constructor_id, '-', '_')) as constructor_id
    from fq f
),
times as (
    select j.season, j.round, j.constructor_id, j.driver_id, j.best_ms, 'jolpica' as time_source
    from jq j semi join j_ok k on k.season = j.season and k.round = j.round
    union all
    select f.season, f.round, f.constructor_id, f.driver_id, f.best_ms, 'f1db'
    from f_mapped f anti join j_ok k on k.season = f.season and k.round = f.round
),
team as (
    select season, round, constructor_id, time_source, min(best_ms) as team_best_ms,
           count(best_ms) as drivers_with_time, count(*) as drivers_entered
    from times group by all
),
session as (
    select season, round, min(team_best_ms) as session_best_ms from team group by 1, 2
)
select t.season, t.round, t.constructor_id, t.team_best_ms, s.session_best_ms,
       round((t.team_best_ms / s.session_best_ms - 1) * 100, 4) as index_pct,
       t.drivers_with_time, t.drivers_entered, r.qualifying_format,
       r.qualifying_format in {REFERENCE_FORMATS} as is_reference_format, t.time_source
from team t
join session s using (season, round)
join '{F}/races.parquet' r using (season, round)
where t.season between {QUALIFYING_FIRST_SEASON} and {LAST_SEASON}
order by t.season, t.round, index_pct nulls last, t.constructor_id
"""


def build_qualifying() -> int:
    PACE.mkdir(parents=True, exist_ok=True)
    out = PACE / "qualifying_index.parquet"
    con = duckdb.connect()
    con.execute(f"copy ({QUALIFYING_SQL}) to '{out}' (format parquet, compression zstd)")
    return con.execute(f"select count(*) from '{out}'").fetchone()[0]


if __name__ == "__main__":
    print(f"pace/qualifying_index: {build_qualifying()} rows")
