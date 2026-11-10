"""T3 계보 테이블 검증."""

import csv

import duckdb
import pytest

from pipeline.config import CURATED_DIR, LAST_SEASON
from pipeline.transforms.lineage import LINEAGES, LINKS

SEASONS = CURATED_DIR / "lineage" / "constructor_seasons.parquet"


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


def lineage_of(con, constructor_id: str, season: int) -> str | None:
    row = con.execute(
        f"select lineage_id from '{SEASONS}' where constructor_id = ? and season = ?",
        [constructor_id, season],
    ).fetchone()
    assert row is not None, (constructor_id, season)
    return row[0]


def read_csv(path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_every_last_season_team_has_a_lineage(con):
    rows = con.execute(
        f"select constructor_id, lineage_id from '{SEASONS}' where season = {LAST_SEASON}"
    ).fetchall()
    assert len(rows) == 10
    assert all(lineage for _, lineage in rows)
    assert len({lineage for _, lineage in rows}) == 10


def test_renault_id_is_split_by_organisation(con):
    """renault ID에는 1977-1985년 워크스와 2002년 이후 엔스톤 팀이 섞여 있다."""
    assert lineage_of(con, "renault", 1980) is None
    assert lineage_of(con, "renault", 1985) is None
    assert lineage_of(con, "renault", 2002) == "enstone"
    assert lineage_of(con, "renault", 2011) == "enstone"
    assert lineage_of(con, "renault", 2016) == "enstone"
    assert lineage_of(con, "lotus_f1", 2013) == "enstone"
    assert lineage_of(con, "alpine", 2025) == "enstone"


def test_mercedes_id_is_split_by_organisation(con):
    """mercedes ID에는 1954-1955년 워크스와 2010년 이후 브래클리 팀이 섞여 있다."""
    assert lineage_of(con, "mercedes", 1954) is None
    assert lineage_of(con, "mercedes", 1955) is None
    assert lineage_of(con, "mercedes", 2010) == "brackley"
    assert lineage_of(con, "brawn", 2009) == "brackley"
    assert lineage_of(con, "honda", 2007) == "brackley"
    assert lineage_of(con, "honda", 1965) is None


def test_other_shared_ids_are_split(con):
    assert lineage_of(con, "alfa", 1951) is None
    assert lineage_of(con, "alfa", 2020) == "hinwil"
    assert lineage_of(con, "aston_martin", 1959) is None
    assert lineage_of(con, "aston_martin", 2021) == "silverstone"
    assert lineage_of(con, "williams", 1975) is None
    assert lineage_of(con, "williams", 1980) == "grove"
    assert lineage_of(con, "sauber", 2010) == "hinwil"


def test_no_constructor_season_maps_to_two_lineages(con):
    dup = con.execute(f"""
        select season, constructor_id from '{SEASONS}' group by 1, 2 having count(*) > 1
    """).fetchall()
    assert dup == []


def test_links_are_well_formed():
    lineages = {r["lineage_id"] for r in read_csv(LINEAGES)}
    links = read_csv(LINKS)
    assert {r["lineage_id"] for r in links} == lineages
    for r in links:
        assert int(r["season_from"]) <= int(r["season_to"]) <= LAST_SEASON, r
        assert r["link_type"] in {"origin", "renamed", "acquired", "entry_purchase"}, r


def test_links_agree_with_f1db_chronology(con):
    """초안의 출발점인 F1DB chronology와 구간이 겹치는지 본다.

    F1DB에 없는 구분(같은 f1db ID 안에서 조직을 나눈 경우)은 우리 쪽이 더 좁을 뿐 어긋나지 않는다.
    """
    chrono = con.execute(f"""
        select f1db_constructor_id, year_from, coalesce(year_to, {LAST_SEASON})
        from '{CURATED_DIR}/f1db/constructors_chronology.parquet'
    """).fetchall()
    for r in read_csv(LINKS):
        if r["link_type"] == "origin" and r["lineage_id"] in {
            "maranello", "woking", "grove", "kannapolis",
        }:  # fmt: skip
            continue  # 이름이 바뀐 적 없는 팀은 chronology에 행이 없다
        lo, hi = int(r["season_from"]), int(r["season_to"])
        overlaps = [
            c for c in chrono if c[0] == r["f1db_constructor_id"] and c[1] <= hi and c[2] >= lo
        ]
        assert overlaps, r
