"""사이트용 JSON 내보내기 테스트.

정제 테이블에서 만든 JSON이 원자료의 값과 같고, 화면이 기대하는 모양을 지키는지 본다.
"""

from __future__ import annotations

import copy
import csv
import json
import statistics
from types import SimpleNamespace

import duckdb
import pandas as pd
import pytest

from pipeline import build_site_data
from pipeline.config import CURATED_DIR, LAST_SEASON


@pytest.fixture(scope="module")
def tables():
    return build_site_data.Tables()


def _cut_after(t, season: int, last_round: int):
    """일정은 그대로 두고 결과, 예선, 순위, 지수만 last_round까지 남긴 진행 중 시즌을 만든다."""
    cut = copy.copy(t)
    for name in (
        "results",
        "qualifying",
        "driver_standings",
        "constructor_standings",
        "quali_index",
        "race_index",
    ):
        frame = getattr(t, name)
        keep = ~((frame["season"] == season) & (frame["round"] > last_round))
        setattr(cut, name, frame[keep])
    return cut


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


def test_home_tolerates_missing_fastest_lap_rank(tables):
    """2025년부터 랩 기록이 없는 차는 fastest_lap_rank가 NULL이다(22라운드의 bortoleto, stroll)."""
    data = build_site_data.build_season(tables, LAST_SEASON)
    data["rounds"] = data["rounds"][:22]
    home = build_site_data.build_home(tables, {LAST_SEASON: data}, {"documents": [], "items": []})
    assert home["race"]["round"] == 22
    flags = [r["fastest_lap"] for r in home["classification"]]
    assert all(isinstance(f, bool) for f in flags)
    assert sum(flags) == 1


def test_in_progress_season_uses_the_last_completed_round(tables):
    cut = _cut_after(tables, LAST_SEASON, 22)
    data = build_site_data.build_season(cut, LAST_SEASON)
    assert len(data["rounds"]) == 24  # 일정은 남아 있다
    home = build_site_data.build_home(cut, {LAST_SEASON: data}, build_site_data.build_upgrades(cut))
    assert home["race"]["round"] == 22
    assert len(home["classification"]) == 20
    assert home["session_best"] is not None
    assert any(p["quali"] is not None for p in home["pace"])
    assert build_site_data.build_meta(cut)["last_race"]["round"] == 22
    summary = build_site_data.season_summary(data)
    assert summary["champion_driver"] is None
    assert summary["champion_constructor"] is None


def test_every_completed_season_has_a_champion(site):
    seasons = site("seasons.json")
    assert all(s["champion_driver"] is not None for s in seasons)
    assert all(s["champion_constructor"] is not None for s in seasons if s["season"] >= 1958)


def test_pole_is_a_single_driver(site):
    for path in sorted((site.root / "season").glob("*.json")):
        for rnd in json.loads(path.read_text(encoding="utf-8"))["rounds"]:
            assert len(rnd["pole"]) <= 1, (path.name, rnd["round"], rnd["pole"])

    def pole(season: int, rnd: int) -> str:
        rounds = {r["round"]: r for r in site(f"season/{season}.json")["rounds"]}
        return rounds[rnd]["pole"][0]["id"]

    assert pole(2022, 21) == "kevin_magnussen"  # 결승 1번 그리드는 스프린트 우승자 russell
    # 2021년은 스프린트 우승자가 폴 기록을 받았으므로 결승 1번 그리드를 그대로 쓴다.
    con = duckdb.connect()
    for rnd in (10, 14, 19):
        grid = con.execute(
            f"select driver_id from '{CURATED_DIR}/jolpica/results.parquet'"
            " where season = 2021 and round = ? and session_type = 'R' and grid = 1",
            [rnd],
        ).fetchall()
        assert [pole(2021, rnd)] == [d for (d,) in grid], rnd
    assert pole(1951, 4) == "fangio"
    assert pole(1955, 1) == "gonzalez"
    assert pole(1964, 9) == "clark"


def test_shared_car_poles_match_f1db_qualifying():
    con = duckdb.connect()
    path = CURATED_DIR / "labels" / "pole_shared_cars.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert rows
    for row in rows:
        season, rnd = int(row["season"]), int(row["round"])
        first = con.execute(
            "select f1db_driver_id"
            f" from '{CURATED_DIR}/f1db/qualifying.parquet'"
            " where season = ? and round = ? and position = 1",
            [season, rnd],
        ).fetchall()
        assert first == [(row["f1db_driver_id"],)], (season, rnd)
        grid = con.execute(
            "select distinct driver_id, constructor_id"
            f" from '{CURATED_DIR}/jolpica/results.parquet'"
            " where season = ? and round = ? and session_type = 'R' and grid = 1",
            [season, rnd],
        ).fetchall()
        assert (row["driver_id"], row["constructor_id"]) in grid, (season, rnd)
        assert len({d for d, _ in grid}) > 1, (season, rnd)


def test_unlisted_shared_pole_fails_the_build():
    res = pd.DataFrame({"driver_id": ["a", "b"], "constructor_id": ["x", "x"], "grid": [1, 1]})
    t = SimpleNamespace(shared_poles={})
    with pytest.raises(ValueError, match="pole_shared_cars"):
        build_site_data.pole_sitter(t, 1960, 1, res, "ONE_SESSION")
    same = pd.DataFrame({"driver_id": ["a", "a"], "constructor_id": ["x", "x"], "grid": [1, 1]})
    assert build_site_data.pole_sitter(t, 1960, 1, same, "ONE_SESSION") == ("a", "x")


def test_pu_names_join_every_manufacturer(site):
    for path in [*(site.root / "season").glob("*.json"), *(site.root / "team").glob("*.json")]:
        data = json.loads(path.read_text(encoding="utf-8"))
        refs = [c["pu"] for c in data.get("constructors", [])] + [
            s["pu"] for s in data.get("seasons", [])
        ]
        for pu in refs:
            assert pu is None or "|" not in pu["name"], (path.name, pu)
    season = {c["id"]: c for c in site("season/1983.json")["constructors"]}
    assert season["mclaren"]["pu"] == {"id": "ford|tag", "name": "Ford, TAG"}


def test_every_link_type_has_a_korean_label(site):
    labels = site("labels.json")["link_types"]
    path = CURATED_DIR / "lineage" / "lineage_links.csv"
    used = {r["link_type"] for r in csv.DictReader(path.open(encoding="utf-8"))}
    assert used <= set(labels)
    bar = next(s for s in site("team/brackley.json")["segments"] if s["constructor_id"] == "bar")
    assert bar["link_type_ko"] == "참가권 인수"


def test_team_medians_use_unrounded_values(site):
    con = duckdb.connect()
    quali, race = {}, {}
    for season, cid, value in con.execute(
        "select season, constructor_id, index_pct"
        f" from '{CURATED_DIR}/pace/qualifying_index.parquet'"
        " where wet_flag <> 'wet' and index_pct is not null and not isnan(index_pct)"
    ).fetchall():
        quali.setdefault((season, cid), []).append(value)
    for season, cid, value in con.execute(
        "select season, constructor_id, index_pct"
        f" from '{CURATED_DIR}/pace/race_index.parquet'"
        " where not is_wet and index_pct is not null and not isnan(index_pct)"
    ).fetchall():
        race.setdefault((season, cid), []).append(value)
    checked = 0
    for path in (site.root / "team").glob("*.json"):
        for row in json.loads(path.read_text(encoding="utf-8"))["seasons"]:
            key = (row["season"], row["constructor_id"])
            expected_q = round(statistics.median(quali[key]), 3) if key in quali else None
            expected_r = round(statistics.median(race[key]), 3) if key in race else None
            assert row["quali_index_median"] == expected_q, (path.name, key)
            assert row["race_index_median"] == expected_r, (path.name, key)
            checked += expected_q is not None
    assert checked >= 280
    red_bull = next(s for s in site("team/milton_keynes.json")["seasons"] if s["season"] == 2025)
    assert red_bull["quali_index_median"] == 0.279


def test_team_name_history_has_no_repeats(site):
    teams = {t["lineage_id"]: t for t in site("teams.json")}
    for team in teams.values():
        names = team["names"]
        assert all(a != b for a, b in zip(names, names[1:], strict=False)), team["lineage_id"]
    assert teams["woking"]["names"] == ["McLaren"]
    assert teams["enstone"]["names"] == [
        "Toleman",
        "Benetton",
        "Renault",
        "Lotus F1",
        "Renault",
        "Alpine",
    ]


def test_meta_follows_api_round_updates(tmp_path, monkeypatch):
    """post-race로 API 대회를 반영하면 Jolpica 기준일과 버전이 그 시각을 따른다."""
    from pipeline import manifest

    rows = manifest.read_rows("datasets.csv")
    extra = {
        "source": "jolpica", "name": "api-rounds", "version": "2025 R24", "url": "", "sha256": "",
        "bytes": "", "upstream_published_at": "", "fetched_at": "2026-12-08T03:00:00Z",
    }  # fmt: skip
    monkeypatch.setattr(
        manifest, "read_rows",
        lambda name: [*rows, extra] if name == "datasets.csv" else manifest_rows(name),
    )  # fmt: skip
    meta = build_site_data.build_meta(build_site_data.Tables())
    assert meta["sources"]["jolpica"]["as_of"] == "2026-12-08"
    assert meta["sources"]["jolpica"]["version"] == "2026-10-27 + API 2025 R24"


def manifest_rows(name):
    import csv

    from pipeline.config import MANIFEST_DIR

    with (MANIFEST_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
