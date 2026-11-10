"""T2 결과·순위 적재 검증. 커밋된 정제 데이터만 읽는다."""

import duckdb
import pytest

from pipeline.config import CURATED_DIR, FIRST_SEASON, LAST_SEASON

J = CURATED_DIR / "jolpica"
F = CURATED_DIR / "f1db"


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


def test_all_seasons_present(con):
    seasons = [
        r[0] for r in con.execute(f"select distinct season from '{J}/races.parquet'").fetchall()
    ]
    assert sorted(seasons) == list(range(FIRST_SEASON, LAST_SEASON + 1))


def test_race_count_per_season_matches_f1db(con):
    """시즌별 레이스 수를 독립 출처(F1DB)의 캘린더와 대조한다."""
    diff = con.execute(f"""
        select coalesce(j.season, f.season) as season, j.n as jolpica, f.n as f1db
        from (select season, count(*) n from '{J}/races.parquet' group by 1) j
        full join (select season, count(*) n from '{F}/races.parquet' group by 1) f using (season)
        where j.n is distinct from f.n
    """).fetchall()
    assert diff == []


def test_race_dates_match_f1db_within_one_day(con):
    """현지 날짜와 UTC 날짜 차이(예: 라스베이거스)는 하루까지 허용한다."""
    diff = con.execute(f"""
        select season, round, j.date, f.date
        from '{J}/races.parquet' j full join '{F}/races.parquet' f using (season, round)
        where j.date is null or f.date is null or abs(date_diff('day', j.date, f.date)) > 1
    """).fetchall()
    assert diff == []


def test_last_season_calendar(con):
    n, first, last = con.execute(
        f"select count(*), min(date), max(date) from '{J}/races.parquet' where season = 2025"
    ).fetchone()
    assert n == 24
    assert str(first) == "2025-03-16"
    assert str(last) == "2025-12-07"


def test_every_race_has_a_winner_and_results(con):
    bad = con.execute(f"""
        select r.season, r.round
        from '{J}/races.parquet' r
        left join '{J}/results.parquet' x
          on x.season = r.season and x.round = r.round and x.session_type = 'R'
        group by 1, 2
        having count(*) filter (where x.position = 1) < 1
    """).fetchall()
    assert bad == []


def test_final_standings_exist_for_every_season(con):
    missing = con.execute(f"""
        with last_round as (select season, max(round) as round from '{J}/races.parquet' group by 1)
        select l.season from last_round l
        left join '{J}/driver_standings.parquet' s on s.season = l.season and s.round = l.round
        group by 1 having count(s.driver_id) = 0
    """).fetchall()
    assert missing == []


def test_2025_champions(con):
    """출처: Jolpica 2025 최종 순위. 두 테이블이 같은 결과를 내는지 본다."""
    driver = con.execute(f"""
        select driver_id, points from '{J}/driver_standings.parquet'
        where season = 2025 and round = 24 and position = 1
    """).fetchone()
    team = con.execute(f"""
        select constructor_id, points from '{J}/constructor_standings.parquet'
        where season = 2025 and round = 24 and position = 1
    """).fetchone()
    assert driver == ("norris", 423.0)
    assert team == ("mclaren", 833.0)
    race_points = con.execute(f"""
        select sum(points) from '{J}/results.parquet'
        where season = 2025 and driver_id = 'norris'
    """).fetchone()[0]
    assert race_points == 423.0


def test_qualifying_times_are_plausible(con):
    lo, hi = con.execute(f"""
        select min(best_time_ms), max(best_time_ms) from '{J}/qualifying.parquet'
        where season >= 2006
    """).fetchone()
    assert lo > 50_000 and hi < 180_000


def test_jolpica_and_f1db_qualifying_agree_where_both_exist(con):
    """2006년 이후 Q1 최고 기록의 세션 최솟값이 두 출처에서 같은지 본다.

    드라이버 ID 체계가 달라 세션 단위 최솟값으로 대조한다.
    """
    diff = con.execute(f"""
        with j as (select season, round, min(best_time_ms) t from '{J}/qualifying.parquet'
                   where session_type = 'Q1' group by 1, 2),
             f as (select season, round, min(q1_ms) t from '{F}/qualifying.parquet' group by 1, 2)
        select season, round, j.t, f.t from j join f using (season, round)
        where j.t is not null and f.t is not null and j.t <> f.t
    """).fetchall()
    assert len(diff) <= 3, diff


@pytest.mark.network
def test_dump_matches_api_for_last_race(con):
    """덤프로 적재한 2025 최종전 결과가 API 응답과 같은지 본다(요청 1회, 캐시)."""
    from pipeline.sources import jolpica

    data = jolpica.fetch_api("2025/24/results")
    api = [
        (int(r["position"]), r["Driver"]["driverId"], r["Constructor"]["constructorId"])
        for r in data["RaceTable"]["Races"][0]["Results"]
    ]
    curated = con.execute(f"""
        select position, driver_id, constructor_id from '{J}/results.parquet'
        where season = 2025 and round = 24 and session_type = 'R' order by position
    """).fetchall()
    assert curated == api
