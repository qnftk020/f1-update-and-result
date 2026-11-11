"""사이트용 JSON 내보내기 테스트.

정제 테이블에서 만든 JSON이 원자료의 값과 같고, 화면이 기대하는 모양을 지키는지 본다.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from pipeline import build_site_data
from pipeline.config import CURATED_DIR


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("generated")
    original = build_site_data.SITE_DATA_DIR
    build_site_data.SITE_DATA_DIR = out
    try:
        build_site_data.main()
    finally:
        build_site_data.SITE_DATA_DIR = original

    def load(name: str):
        return json.loads((out / name).read_text(encoding="utf-8"))

    load.root = out
    return load


def test_every_season_is_exported(site):
    seasons = site("seasons.json")
    assert [s["season"] for s in seasons] == list(range(2025, 1949, -1))
    assert len(list((site.root / "season").glob("*.json"))) == 76
    assert seasons[0]["champion_driver"]["id"] == "norris"
    assert seasons[0]["champion_driver"]["final_points"] == 423
    assert seasons[0]["champion_constructor"]["id"] == "mclaren"
    by_year = {s["season"]: s for s in seasons}
    assert by_year[1957]["champion_constructor"] is None  # 컨스트럭터 순위는 1958년부터다
    assert by_year[1958]["champion_constructor"]["id"] == "vanwall"


def test_season_series_have_one_value_per_round(site):
    season = site("season/2025.json")
    n = len(season["rounds"])
    assert n == 24
    for driver in season["drivers"]:
        assert len(driver["positions"]) == n and len(driver["points"]) == n
    for team in season["constructors"]:
        assert len(team["points"]) == n
        assert len(team["quali_index"]) == n and len(team["race_index"]) == n
    assert [r["date"] for r in season["rounds"]] == sorted(r["date"] for r in season["rounds"])
    assert all(len(r["date"]) == 10 for r in season["rounds"])


def test_index_values_match_curated_tables(site):
    con = duckdb.connect()
    season = site("season/2025.json")
    teams = {c["id"]: c for c in season["constructors"]}
    quali = con.execute(
        "select round, constructor_id, index_pct"
        f" from '{CURATED_DIR}/pace/qualifying_index.parquet' where season = 2025"
    ).fetchall()
    assert len(quali) == 240
    for rnd, cid, value in quali:
        exported = teams[cid]["quali_index"][rnd - 1]
        assert exported == (None if value is None else round(value, 3)), (rnd, cid)
    race = con.execute(
        "select round, constructor_id, index_pct, ci_low_pct, ci_high_pct, clean_laps"
        f" from '{CURATED_DIR}/pace/race_index.parquet' where season = 2025"
    ).fetchall()
    for rnd, cid, value, low, high, laps in race:
        exported = teams[cid]["race_index"][rnd - 1]
        if value is None or value != value:
            assert exported is None, (rnd, cid)
        else:
            assert exported == {
                "v": round(value, 3),
                "lo": round(low, 3),
                "hi": round(high, 3),
                "n": laps,
            }, (rnd, cid)


def test_flags_are_exported(site):
    season_2025 = site("season/2025.json")
    wet_quali = [r["round"] for r in season_2025["rounds"] if r["quali"]["wet"] == "wet"]
    wet_race = [r["round"] for r in season_2025["rounds"] if r["race"]["wet"]]
    assert wet_quali and wet_race
    season_2004 = site("season/2004.json")
    assert all(r["quali"]["reference"] for r in season_2004["rounds"])
    assert all(r["quali"]["wet"] == "unclassified" for r in season_2004["rounds"])
    assert all(r["race"] is None for r in season_2004["rounds"])
    season_1990 = site("season/1990.json")
    assert all(r["quali"] is None for r in season_1990["rounds"])


def test_shared_wins_are_kept(site):
    """1951년 프랑스 그랑프리는 차량 공유로 우승자가 두 명이다."""
    season = site("season/1951.json")
    shared = [r for r in season["rounds"] if len(r["winners"]) > 1]
    assert [(r["round"], sorted(w["id"] for w in r["winners"])) for r in shared] == [
        (4, ["fagioli", "fangio"])
    ]


def test_home_summarises_the_last_race(site):
    home = site("home.json")
    assert home["race"]["name"] == "Abu Dhabi Grand Prix"
    assert home["race"]["name_ko"] == "아부다비 그랑프리"
    rows = home["classification"]
    assert len(rows) == 20
    assert [r["code"] for r in rows[:3]] == ["VER", "PIA", "NOR"]
    assert rows[0]["time"] == "1:26:07.469"
    assert rows[1]["time"] == "+12.594"
    assert rows[-1]["time"] == "+1랩"
    assert sum(1 for r in rows if r["fastest_lap"]) == 1
    assert home["upgrades_this_weekend"]["items"] == 0
    assert all(t["status"] == "no_updates" for t in home["upgrades_this_weekend"]["teams"])
    assert home["upgrades_latest"]["event"] == "Qatar Grand Prix"
    assert len(home["upgrades_latest"]["list"]) == home["upgrades_latest"]["items"] == 1
    assert len(home["pace"]) == 10


def test_upgrades_export_is_complete(site):
    upgrades = site("upgrades.json")
    assert len(upgrades["items"]) == 855
    assert len(upgrades["documents"]) == 54
    assert all(len(d["teams"]) == 10 for d in upgrades["documents"])
    missing = {(m["season"], m["event"]) for m in upgrades["missing_events"]}
    assert (2024, "Bahrain Grand Prix") in missing
    assert sum(1 for season, _ in missing if season == 2023) == 15
    assert not any(season == 2025 for season, _ in missing)
    review = {(i["season"], i["event"]) for i in upgrades["items"] if i["review"]}
    assert review == {(2024, "Las Vegas Grand Prix")}
    labels = site("labels.json")
    assert {i["area"] for i in upgrades["items"]} <= set(labels["component_areas"])
    assert {i["category"] for i in upgrades["items"]} <= set(labels["reason_categories"])


def test_teams_follow_the_lineage_table(site):
    teams = site("teams.json")
    assert len(teams) == 10
    enstone = site("team/enstone.json")
    assert [(s["constructor_id"], s["from"], s["to"]) for s in enstone["segments"]] == [
        ("toleman", 1981, 1985),
        ("benetton", 1986, 2001),
        ("renault", 2002, 2011),
        ("lotus_f1", 2012, 2015),
        ("renault", 2016, 2020),
        ("alpine", 2021, 2025),
    ]
    seasons = [s["season"] for s in enstone["seasons"]]
    assert seasons == list(range(1981, 2026))
    assert not any(
        s["constructor_id"] == "renault" and s["season"] < 2002 for s in enstone["seasons"]
    )
    brackley = site("team/brackley.json")
    assert not any(s["season"] in (1954, 1955) for s in brackley["seasons"])
    assert all(e["url"].startswith("http") for e in enstone["evidence"])


def test_every_race_has_a_korean_name(site):
    labels = site("labels.json")
    con = duckdb.connect()
    names = {
        r[0]
        for r in con.execute(
            f"select distinct race_name from '{CURATED_DIR}/jolpica/races.parquet'"
        ).fetchall()
    }
    assert names == set(labels["grand_prix"])


def test_no_em_dash_in_generated_text(site):
    em_dash = chr(0x2014)
    for path in site.root.rglob("*.json"):
        assert em_dash not in path.read_text(encoding="utf-8"), path.name
