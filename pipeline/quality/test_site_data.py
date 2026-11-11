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
        "select round, constructor_id, index_pct, team_best_ms, session_best_ms"
        f" from '{CURATED_DIR}/pace/qualifying_index.parquet' where season = 2025"
    ).fetchall()
    assert len(quali) == 240
    for rnd, cid, value, team_ms, session_ms in quali:
        exported = teams[cid]["quali_index"][rnd - 1]
        if value is None:
            assert exported is None, (rnd, cid)
            continue
        # 화면 값은 ms 기록에서 다시 계산한 지수다. 정제 테이블의 넷째 자리 값과 반올림 차이만 난다.
        assert exported == round((team_ms / session_ms - 1) * 100, 9), (rnd, cid)
        assert abs(exported - value) <= 0.00005 + 1e-12, (rnd, cid)
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
                "v": round(value, 6),
                "lo": round(low, 6),
                "hi": round(high, 6),
                "n": laps,
            }, (rnd, cid)


def test_quali_index_keeps_the_third_decimal(site):
    """2025 R24 McLaren: 82408 / 82207 - 1 = 0.24450...%. 넷째 자리 저장값(0.2445)을 셋째 자리로
    한 번 더 반올림하면 0.244가 되어 화면 문장(0.245%)과 어긋난다."""
    home = site("home.json")
    mclaren = next(q for q in home["quali"] if q["constructor_id"] == "mclaren")
    assert mclaren["team_best_ms"] == 82408
    assert mclaren["gap_s"] == 0.201
    assert 0.2445 < mclaren["v"] < 0.24451
    assert [q["constructor_id"] for q in home["quali"]][:2] == ["red_bull", "mclaren"]
    assert home["quali_meta"]["session_best"] == "1:22.207"
    assert [r["constructor_id"] for r in home["race_index"]][0] == "mclaren"


def test_round_fields_match_the_teams_of_that_round(site):
    season = site("season/2025.json")
    for i, rnd in enumerate(season["rounds"]):
        values = sorted(
            c["quali_index"][i]
            for c in season["constructors"]
            if c["quali_index"] and c["quali_index"][i] is not None
        )
        field = rnd["quali"]["field"]
        assert rnd["quali"]["teams"] == len(values) == 10
        assert abs(field["med"] - statistics.median(values)) < 1e-8
        assert field["q1"] <= field["med"] <= field["q3"]


def test_season_facts(site):
    facts = site("season/2025.json")["facts"]
    assert facts["races"] == 24
    assert facts["winners"] == 4
    assert facts["sprints"] == [2, 6, 13, 19, 21, 23]
    assert facts["quali_wet"] == [17, 22]
    assert facts["race_wet"] == [1, 12, 13]
    assert facts["driver_lead"]["leader_id"] == "norris"
    old = site("season/2004.json")["facts"]
    assert old["quali_reference"] == list(range(1, 19))
    assert old["quali_unclassified"] == list(range(1, 19))
    assert old["quali_reference_formats"] == ["원랩"]
    assert old["race_index_rounds"] == 0
    assert site("season/1957.json")["facts"]["constructor_lead"] is None


def test_team_page_fields(site):
    """팀 페이지 리드와 계보 수치: 엔스톤 2025는 10위 22점, 마른 예선 22개 평균 1.337%로 8번째다."""
    enstone = site("team/enstone.json")
    last = enstone["seasons"][-1]
    assert (last["position"], last["points"], last["quali_rounds"]) == (10, 22, 22)
    assert round(last["quali_index_mean"], 3) == 1.337
    assert (last["quali_rank"], last["quali_teams"]) == (8, 10)
    assert enstone["totals"] == {
        "seasons": 45,
        "races": 786,
        "wins": 50,
        "podiums": enstone["totals"]["podiums"],
        "best_position": 1,
        "titles": [1995, 2005, 2006],
    }
    assert enstone["current_from"] == 2021
    assert enstone["totals_current"]["seasons"] == 5
    assert [d["id"] for d in enstone["drivers_last"]] == ["gasly", "doohan", "colapinto"]
    timeline = enstone["upgrades"]["timeline"]
    assert sorted(timeline) == ["2023", "2024", "2025"]
    assert sum(r["n"] for rows in timeline.values() for r in rows) == enstone["upgrades"]["items"]
    assert enstone["upgrades"]["items"] == 62
    bahrain_2024 = next(r for r in timeline["2024"] if r["round"] == 1)
    assert bahrain_2024["status"] == "nodoc"
    vegas = next(
        r for r in site("team/grove.json")["upgrades"]["timeline"]["2024"] if r["round"] == 22
    )
    assert vegas["status"] == "needs_review" and vegas["doc_review"]


def test_home_tiles_and_round_counts(site):
    home = site("home.json")
    assert home["pole"]["id"] == "max_verstappen" and home["pole"]["time"] == "1:22.207"
    assert home["fastest_lap"]["id"] == "leclerc"
    assert (home["fastest_lap"]["lap"], home["fastest_lap"]["time"]) == (45, "1:26.725")
    counts = home["round_counts"]
    assert len(counts) == 24
    assert max(counts, key=lambda c: c["n"])["round"] == 1
    assert sum(c["n"] for c in counts) == sum(
        1 for i in site("upgrades.json")["items"] if i["season"] == 2025
    )
    assert [d["position"] for d in home["drivers"]] == list(range(1, len(home["drivers"]) + 1))
    assert home["drivers"][0]["team"] == "McLaren"
    assert len(home["constructors"]) == 10


def test_meta_has_as_of_dates_per_source(site):
    meta = site("meta.json")
    jolpica = meta["sources"]["jolpica"]
    assert jolpica["dump"] == "2026-10-27"
    assert set(meta["sources"]) == {"jolpica", "f1db", "openf1", "fia", "pace"}
    assert all(len(s["as_of"]) == 10 for s in meta["sources"].values())
    assert [(d["season"], d["round"]) for d in meta["review_documents"]] == [(2024, 22)]


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


def test_no_html_entities_in_generated_text(site):
    # 원자료의 "Lotus-Pratt &amp; Whitney"는 build_site_data가 글자로 푼다.
    for path in site.root.rglob("*.json"):
        assert "&amp;" not in path.read_text(encoding="utf-8"), path.name


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

    # 실제 post-race를 한 번 돌린 저장소에는 api-rounds 행이 이미 있다. 그 행을 빼고 시험 행만 둔다.
    rows = [r for r in manifest.read_rows("datasets.csv") if r["name"] != "api-rounds"]
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


def test_engines_export_follows_pu_tables(site):
    usage_path = CURATED_DIR / "fia" / "pu_usage.parquet"
    if not usage_path.exists():  # PU 파서(T6) 결과가 커밋되기 전에는 engines.json을 만들지 않는다
        pytest.skip("PU 정제 테이블이 아직 없다")
    engines = site("engines.json")
    usage = pd.read_parquet(usage_path)
    assert sorted(engines["seasons"]) == [str(s) for s in range(2020, LAST_SEASON + 1)]
    for key, s in engines["seasons"].items():
        season = int(key)
        assert s["rounds"] == len(s["round_labels"])
        for team in s["teams"]:
            for d in team["drivers"]:
                for el, series in d["by"].items():
                    assert len(series) == s["rounds"]
                    known = [v for v in series if v is not None]
                    assert d["final"][el] == (known[-1] if known else None)
        # 누적 값은 원자료의 used_after_event, 비어 있으면 used_before_event다.
        rows = usage[(usage["season"] == season) & (usage["element"] == "ICE")]
        for r in rows.head(30).itertuples():
            team = next(t for t in s["teams"] if t["constructor_id"] == r.constructor_id)
            d = next(x for x in team["drivers"] if x["driver_id"] == r.driver_id)
            expected = r.used_before_event if pd.isna(r.used_after_event) else r.used_after_event
            assert d["by"]["ICE"][int(r.round) - 1] == int(expected)
        for d in (d for t in s["teams"] for d in t["drivers"]):
            for el in d["exceed"]:
                assert d["final"][el] > s["allocation"][el]["allowed"]


def test_regulations_matrix_covers_every_year(site):
    reg = site("regulations.json")
    years = [y["year"] for y in reg["years"]]
    assert years == list(range(1982, LAST_SEASON + 1))
    for y in reg["years"]:
        expected = "A" if y["year"] >= 2008 else "B" if y["year"] >= 2001 else "C"
        assert y["grade"] == expected
        for section in ("technical", "sporting"):
            cell = y[section]
            assert cell["found"] == (cell["count"] > 0)
            assert (cell["url"] is not None) == cell["found"]
    for c in reg["comparisons"]:
        assert len(c["changes"]) == c["added"] + c["removed"] + c["modified"]
        # 조항 비교에는 본문을 싣지 않는다(번호, 제목, 변경 유형, 쪽만).
        for ch in c["changes"]:
            assert set(ch) == {
                "clause_no", "top_article", "top_title", "heading", "change", "renumbered",
                "from_clause_no", "page_from", "page_to",
            }  # fmt: skip
    # 등급 C 문서의 설명(스캔 내용을 옮긴 문장)은 싣지 않는다.
    for docs in reg["documents"].values():
        for d in docs:
            if d["grade"] == "C":
                assert d["note_ko"] is None


def _reg_documents():
    return pd.read_csv(CURATED_DIR / "regulations" / "documents.csv", dtype={"issue": str})


def test_comparisons_name_the_versions_they_skip(site):
    """건너뛴 판이 있는 비교는 review가 참이고, 건너뛴 판을 순서대로 판 정보와 함께 적는다."""
    reg = site("regulations.json")
    curated = pd.read_csv(CURATED_DIR / "regulations" / "comparisons.csv", dtype=str)
    docs = _reg_documents()
    key = ["kind", "section", "from_season", "from_version", "to_season", "to_version"]
    exported = {tuple(str(c[k]) for k in key): c for c in reg["comparisons"]}
    assert len(exported) == len(curated)
    reviewed = 0
    for row in curated.itertuples():
        c = exported[tuple(getattr(row, k) for k in key)]
        tokens = [t for t in str(row.skipped_versions or "").split(";") if t and t != "nan"]
        assert [f"{k['season']}:{k['version']}" for k in c["skipped_versions"]] == tokens
        assert c["review"] == bool(tokens)
        reviewed += c["review"]
        for k in c["skipped_versions"]:
            hit = docs[
                (docs["season"] == k["season"])
                & (docs["section"] == c["section"])
                & (docs["version_key"] == k["version"])
            ].iloc[0]
            assert k["url"] == hit["url"]
            if hit["status"] == "needs_review":
                assert k["status"] == "needs_review" and k["review_reasons"]
    assert reviewed == 7
    # 2025 스포팅 규정 시즌 비교는 검수 대기인 Issue 5(2025-04-30)를 건너뛴다.
    c = next(
        c
        for c in reg["comparisons"]
        if c["kind"] == "season" and c["section"] == "sporting" and c["to_season"] == 2025
    )
    assert c["review"] and [(k["issue"], k["version"]) for k in c["skipped_versions"]] == [
        ("5", "2025-04-30")
    ]


def test_needs_review_versions_say_why_in_korean(site):
    reg = site("regulations.json")
    docs = _reg_documents()
    review = docs[docs["status"] == "needs_review"]
    exported = [d for ds in reg["documents"].values() for d in ds if d["status"] == "needs_review"]
    assert len(exported) == len(review) == 12
    for d in exported:
        assert d["problems"] and d["review_reasons"]
        assert all(not r.endswith("..") and "\u2014" not in r for r in d["review_reasons"])
    for ds in reg["documents"].values():
        for d in ds:
            if d["status"] != "needs_review":
                assert d["problems"] == [] and d["review_reasons"] == []
    by = {
        (int(y), d["section"], d["version_key"]): d
        for y, ds in reg["documents"].items()
        for d in ds
    }
    # 렌더링한 쪽에서 확인한 원문 오류는 원문 오류라고 적는다.
    issue5 = by[(2025, "sporting", "2025-04-30")]["review_reasons"]
    assert issue5[0].startswith("FIA 원문에 같은 조항 번호가 두 번 인쇄되어 있다(25쪽 23.6)")
    # 확인하지 않은 문제는 아직 확인하지 않았다고 적는다.
    unverified = by[(2022, "technical", "2021-12-15")]["review_reasons"]
    assert unverified[-1] == "원문의 오류인지 파싱의 오류인지 아직 사람이 확인하지 않았다."
    assert "14.3.3" in unverified[0]


def test_review_reasons_group_parser_problems():
    from pipeline import site_data_extra as extra

    reasons = extra.review_reasons(
        "8쪽: 들여 쓴 줄이 다음 조항 번호로 시작한다(2.9.2) / 54쪽: 조항 번호 순서가 어긋난다"
        "(8.2.5 다음 8.2.5) / 조항 번호 8.2.5가 2번 나온다 / 9쪽: 조항 번호가 건너뛴다(2.9.1 다음 "
        "2.9.3) / 외 3건"
    )
    assert reasons == [
        "자동 파싱에서 같은 조항 번호가 두 번 읽혔다(8.2.5).",
        "조항 번호가 건너뛰는 곳이 있다(9쪽 2.9.1 다음 2.9.3).",
        "본문 줄이 다음 조항 번호로 시작해 조항 경계를 자동으로 정하지 못했다(8쪽 2.9.2).",
        "그 밖에 3건이 더 있다.",
        "원문의 오류인지 파싱의 오류인지 아직 사람이 확인하지 않았다.",
    ]
    assert extra.review_reasons("") == []


def test_regulation_facts_carry_their_issue(site):
    """규정에서 읽은 수치는 읽은 판과 시즌 마지막 판인지를 함께 싣고, 인용문은 싣지 않는다."""
    reg = site("regulations.json")
    pu = pd.read_csv(CURATED_DIR / "regulations" / "pu_allocation_rules.csv", dtype=str)
    fuel = pd.read_csv(CURATED_DIR / "regulations" / "fuel_rules.csv", dtype=str)
    facts = [f for fs in reg["facts"].values() for f in fs]
    assert len(facts) == len(pu) + len(fuel)
    for f in facts:
        assert "quote" not in f and "quote_start" not in f
        assert f["version_key"] and f["clause_no"] and f["url"]
        assert (f["final_issue"] is None) == bool(f["is_final_issue"])
    non_final = [f for f in facts if f["is_final_issue"] is False]
    assert {f["element"] for f in non_final} == set(
        pu.loc[pu["is_final_issue"] == "False", "element"]
    )
    for f in non_final:
        assert (f["issue"], f["version_key"]) == ("4", "2025-02-26")
        fin = f["final_issue"]
        assert (fin["issue"], fin["version"], fin["status"]) == ("5", "2025-04-30", "needs_review")
        assert fin["review_reasons"]


def test_engine_allocation_says_where_values_come_from(site):
    engines = site("engines.json")
    s = engines["seasons"]["2025"]
    ice = s["allocation"]["ICE"]
    assert (ice["basis"], ice["clause_no"], ice["issue"], ice["is_final_issue"]) == (
        "regulation", "28.2", "4", False,
    )  # fmt: skip
    assert ice["final_issue"]["issue"] == "5" and ice["final_issue"]["status"] == "needs_review"
    # FIA 선언 문서의 배정 문장(pu_allocations.csv)도 함께 싣는다.
    statements = pd.read_csv(CURATED_DIR / "fia" / "pu_allocations.csv")
    for el, rows in s["allocation_statements"].items():
        want = statements[(statements["season"] == 2025) & (statements["element"] == el)]
        assert sorted((r["allowed"], r["first_round"], r["documents"]) for r in rows) == sorted(
            zip(want["allowed"], want["first_round"], want["documents"], strict=True)
        )
    assert s["allocation_statements"]["ICE"] == [
        {
            "allowed": 4,
            "first_round": 1,
            "documents": 19,
            "url": statements.loc[
                (statements["season"] == 2025) & (statements["element"] == "ICE"), "source_url"
            ].iloc[0],
        }
    ]
    for key, season in engines["seasons"].items():
        for el, a in season["allocation"].items():
            if a and a["basis"] == "regulation" and int(key) < 2025:
                assert a["is_final_issue"] is True and a["final_issue"] is None, (key, el)


def test_ice_events_without_ordinal_explain_the_conflict(site):
    engines = site("engines.json")
    events = pd.read_csv(CURATED_DIR / "fia" / "pu_ice_events.csv")
    exported = [e for s in engines["seasons"].values() for e in s["ice_events"]]
    assert len(exported) == len(events)
    unsure = [e for e in exported if e["ice_number"] is None]
    assert len(unsure) == int(events["ice_number"].isna().sum()) == 2
    for e in exported:
        assert {"printed_previously_used", "stated_ordinal", "conflict", "conflict_ko"} <= set(e)
        if e["ice_number"] is None:
            assert e["conflict"] and e["conflict_ko"]
            assert e["conflict_ko"].endswith("어느 쪽도 고르지 않고 순번을 비워 둔다.")
        else:
            assert e["conflict"] is None and e["conflict_ko"] is None
    leclerc = next(e for e in unsure if e["driver_id"] == "leclerc")
    assert (leclerc["printed_previously_used"], leclerc["stated_ordinal"]) == (3, 4)
    assert leclerc["conflict_ko"].startswith(
        "선언 문서는 이전 사용 개수를 3개로 적었으나 같은 대회 누적 문서로 센 값은 2개다."
    )
    coverage = {c["season"]: c["ice_unsure"] for c in engines["coverage"]}
    assert coverage[2022] == 2 and sum(coverage.values()) == 2
