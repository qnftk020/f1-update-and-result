"""T10 페이스 지수 검증."""

import duckdb
import pytest

from pipeline.config import CURATED_DIR

Q = CURATED_DIR / "pace" / "qualifying_index.parquet"
J = CURATED_DIR / "jolpica"


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


def test_qualifying_index_covers_every_race_since_1996(con):
    missing = con.execute(f"""
        select r.season, r.round from '{J}/races.parquet' r
        anti join '{Q}' q using (season, round) where r.season >= 1996
    """).fetchall()
    assert missing == []


def test_qualifying_index_is_zero_for_fastest_and_never_negative(con):
    lo, zero_rounds, rounds = con.execute(f"""
        select min(index_pct), count(distinct (season, round)) filter (where index_pct = 0),
               count(distinct (season, round)) from '{Q}'
    """).fetchone()
    assert lo == 0
    assert zero_rounds == rounds


def test_qualifying_index_matches_hand_calculation(con):
    """수기 계산(docs/methodology.md): 2025년 1라운드 레드불 = 75,481 / 75,096 - 1 = 0.513%."""
    team, best, index = con.execute(f"""
        select team_best_ms, session_best_ms, index_pct from '{Q}'
        where season = 2025 and round = 1 and constructor_id = 'red_bull'
    """).fetchone()
    assert (team, best) == (75481, 75096)
    assert index == pytest.approx(0.5127, abs=1e-4)


def test_qualifying_index_teams_exist_in_jolpica(con):
    """대응표를 거친 팀 ID가 Jolpica에 있는 ID인지 본다(예선 탈락 팀 포함)."""
    unknown = con.execute(f"""
        select distinct q.constructor_id from '{Q}' q
        anti join '{J}/constructors.parquet' c using (constructor_id)
    """).fetchall()
    assert unknown == []


def test_reference_formats_are_flagged(con):
    seasons = con.execute(
        f"select distinct season from '{Q}' where is_reference_format order by 1"
    ).fetchall()
    assert [s[0] for s in seasons] == [2003, 2004, 2005]


# --- 레이스 페이스 지수 ---------------------------------------------------------------

R = CURATED_DIR / "pace" / "race_index.parquet"


def test_qualifying_index_matches_api_hand_calculations(con):
    """Jolpica API 값으로 따로 계산한 세 대회 (docs/methodology.md)."""
    cases = [
        (2024, 8, "ferrari", 70270, 70270, 0.0),
        (2023, 1, "aston_martin", 90336, 89708, 0.7),
        (2010, 5, "mclaren", 80829, 79995, 1.0426),
    ]
    for season, rnd, team, team_best, session_best, index in cases:
        row = con.execute(
            f"select team_best_ms, session_best_ms, index_pct from '{Q}' "
            "where season = ? and round = ? and constructor_id = ?",
            [season, rnd, team],
        ).fetchone()
        assert row[:2] == (team_best, session_best)
        assert row[2] == pytest.approx(index, abs=1e-4)


def test_race_index_covers_every_race_2023_2025(con):
    rounds = con.execute(f"select count(distinct (season, round)) from '{R}'").fetchone()[0]
    assert rounds == 70


def test_race_index_is_centred_on_the_field_median(con):
    """필드 기준이 팀 값의 중앙값이므로 대회별 지수의 중앙값은 0이어야 한다."""
    worst = con.execute(f"""
        select max(abs(m)) from (
            select median(index_pct) as m from '{R}' where index_pct is not null
            group by season, round)
    """).fetchone()[0]
    assert worst < 1e-3


def test_race_index_interval_contains_the_estimate(con):
    bad = con.execute(f"""
        select count(*) from '{R}'
        where index_pct is not null and not (ci_low_pct <= index_pct and index_pct <= ci_high_pct)
    """).fetchone()[0]
    assert bad == 0


def test_race_index_needs_enough_clean_laps(con):
    bad = con.execute(f"""
        select count(*) from '{R}' where (clean_laps < 8) <> (index_pct is null)
    """).fetchone()[0]
    assert bad == 0


def test_race_index_matches_independent_recalculation(con):
    """원문 JSON으로 따로 계산한 세 대회의 값 (docs/methodology.md)."""
    cases = [
        (2023, 5, {"red_bull": -1.1776, "mercedes": -0.3631, "aston_martin": -0.2727}),
        (2024, 1, {"red_bull": -1.2566, "ferrari": -0.7356, "mclaren": -0.6082}),
        (2025, 2, {"mclaren": -0.8496, "ferrari": -0.5911, "red_bull": -0.4134}),
    ]
    for season, rnd, expected in cases:
        rows = dict(
            con.execute(
                f"select constructor_id, index_pct from '{R}' where season = ? and round = ?",
                [season, rnd],
            ).fetchall()
        )
        for team, value in expected.items():
            assert rows[team] == pytest.approx(value, abs=1e-4), (season, rnd, team)


def test_wet_flags(con):
    flags = dict(
        con.execute(f"""
            select wet_flag, count(distinct (season, round)) from '{Q}' group by 1
        """).fetchall()
    )
    assert flags["wet"] + flags["dry"] == 70
    assert flags["unclassified"] == 498
    seasons = con.execute(
        f"select min(season), max(season) from '{Q}' where wet_flag <> 'unclassified'"
    ).fetchone()
    assert seasons == (2023, 2025)
    # 2024년 상파울루 결승은 비로 클린 랩이 없었다
    wet, teams = con.execute(f"""
        select bool_and(is_wet), count(index_pct) from '{R}' where season = 2024 and round = 21
    """).fetchone()
    assert wet and teams == 0
