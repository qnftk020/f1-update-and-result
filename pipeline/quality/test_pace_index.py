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
