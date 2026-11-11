"""드라이버 페이지와 챔피언십 분석 JSON(drivers.json, driver/<id>.json, history.json) 테스트.

정제 테이블에서 바로 만든 산출물을 본다. 기대값은 Jolpica 정제 테이블에서 센 값이고, 가능한 것은
F1DB(v2026.20.0, 2025 시즌까지 걸러서)와 대조해 같은 값임을 확인했다. F1DB 원본 CSV가 로컬에
있으면(data/raw/f1db, 커밋하지 않음) 시즌 챔피언 점수와 주요 드라이버 통산을 직접 대조하고,
없으면 그 테스트만 건너뛴다.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from pathlib import Path

import pytest

from pipeline import build_site_data, site_drivers
from pipeline.config import LAST_SEASON, RAW_DIR

F1DB_CSV = RAW_DIR / "f1db" / "v2026.20.0" / "csv"


@pytest.fixture(scope="module")
def out():
    t = build_site_data.Tables()
    first = int(t.races["season"].min())
    seasons = {s: build_site_data.build_season(t, s) for s in range(first, LAST_SEASON + 1)}
    files: dict[str, object] = {}

    def write(name: str, payload: object) -> None:
        # build_site_data.write_json과 같은 규칙으로 직렬화해 NaN이 섞이면 실패하게 한다.
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        files[name] = json.loads(text)
        files.setdefault("_text", []).append(text)

    site_drivers.build_all(t, seasons, write)
    files["_tables"] = t
    files["_seasons"] = seasons
    return files


@pytest.fixture(scope="module")
def drivers(out):
    return {d["id"]: d for d in out["drivers.json"]}


def season_row(out, driver_id: str, season: int) -> dict:
    rows = out[f"driver/{driver_id}.json"]["season_rows"]
    return next(r for r in rows if r["s"] == season)


def test_one_file_per_driver_with_a_race_result(out, drivers):
    t = out["_tables"]
    race = t.results[t.results["session_type"] == "R"]
    assert set(drivers) == set(race["driver_id"])
    assert len(drivers) == 817
    for driver_id in drivers:
        assert f"driver/{driver_id}.json" in out
    assert sum(d["in_2025"] for d in drivers.values()) == 21  # 2025 결승 출전 21명(Doohan 포함)


def test_title_counts(drivers):
    # F1DB seasons-driver-standings의 championshipWon과 같다.
    assert drivers["michael_schumacher"]["title_seasons"] == [
        1994,
        1995,
        2000,
        2001,
        2002,
        2003,
        2004,
    ]
    assert drivers["hamilton"]["title_seasons"] == [2008, 2014, 2015, 2017, 2018, 2019, 2020]
    assert drivers["fangio"]["title_seasons"] == [1951, 1954, 1955, 1956, 1957]
    assert drivers["max_verstappen"]["title_seasons"] == [2021, 2022, 2023, 2024]
    assert drivers["norris"]["title_seasons"] == [2025]
    assert drivers["prost"]["titles"] == 4 and drivers["senna"]["titles"] == 3
    assert sum(d["titles"] for d in drivers.values()) == LAST_SEASON - 1950 + 1


def test_hamilton_career(drivers):
    ham = drivers["hamilton"]
    # F1DB: 380 출발, 105 우승, 202 포디움, 104 폴, 통산 5018.5점(결승 4955.5 + 스프린트 63).
    assert (ham["entries"], ham["starts"], ham["wins"], ham["podiums"]) == (380, 380, 105, 202)
    assert ham["poles"] == 104 and ham["grid_one"] == 104
    assert ham["points"] == 4955.5 and ham["sprint_points"] == 63
    assert ham["lineages"] == ["woking", "brackley", "maranello"]
    assert ham["last_team"] == {"id": "ferrari", "name": "Ferrari"}


def test_schumacher_1997_exclusion(out, drivers):
    row = season_row(out, "michael_schumacher", 1997)
    # Jolpica는 점수(78)를 남기고 순위를 비운 채 adjustment_type 101로 적는다.
    assert row["pos"] is None and row["excluded"] is True and row["pts"] == 78
    assert row["champ_id"] == "villeneuve" and row["champ_pts"] == 81
    assert 1997 not in drivers["michael_schumacher"]["title_seasons"]
    h = next(s for s in out["history.json"]["seasons"] if s["season"] == 1997)
    assert h["d1"]["id"] == "villeneuve" and h["d2"]["id"] == "frentzen"
    assert (h["margin"], h["margin_pct"]) == (39, 48.15)
    assert h["excluded"] == [{"id": "michael_schumacher", "name": "Michael Schumacher", "pts": 78}]
    excluded = [s for s in out["history.json"]["seasons"] if s["excluded"]]
    assert [s["season"] for s in excluded] == [1997]
    # 선두 라운드는 제외된 Schumacher의 그 시점 점수를 넣어 센다. Schumacher는 R5, R7-R14, R16 뒤
    # 점수 선두였고(R5 24점 대 Villeneuve 20점, R16 78점 대 77점) 선두는 R17에 마지막으로 바뀌었다.
    assert h["d1"]["led"] == 5 and h["lead_change"] == 17
    lead = out["_seasons"][1997]["facts"]["driver_lead"]
    assert lead["round"] == 17 and lead["excluded_leader"] == ["michael_schumacher"]


def test_mclaren_2007_lead_is_unavailable(out):
    # 2007 McLaren은 모든 라운드 점수까지 0으로 지워져 그 시점의 컨스트럭터 선두를 알 수 없다.
    h = next(s for s in out["history.json"]["seasons"] if s["season"] == 2007)
    assert h["c_lead_change"] is None
    assert out["_seasons"][2007]["facts"]["constructor_lead"] is None


def test_no_html_entities_or_float_noise(out):
    # 원자료의 "Lotus-Pratt &amp; Whitney"는 글자로 풀고, 점수는 소수 둘째 자리로 맞춘다.
    for text in out["_text"]:
        assert "&amp;" not in text
        assert "0000000001" not in text and "9999999" not in text
    row = season_row(out, "ascari", 1954)
    assert row["pts"] == 1.14 and row["round_pts"][-1] == 1.14


def test_unranked_rows_are_not_exclusions(out, drivers):
    # is_eligible 거짓인 행은 순위가 비어 있을 뿐 제외가 아니다(2002 Davidson은 완주 기록 없음).
    row = season_row(out, "davidson", 2002)
    assert row["pos"] is None and row["excluded"] is False and row["pts"] == 0
    # 1950년대 인디애나폴리스 500만 나온 드라이버. 우승자 Parsons는 순위가 있다.
    parsons = drivers["parsons"]
    assert parsons["indy_only"] and parsons["wins"] == 1
    assert season_row(out, "parsons", 1950)["pos"] == 6
    zero = [d for d in drivers.values() if d["points"] == 0 and d["sprint_points"] == 0]
    assert len(zero) > 400
    for d in zero:
        assert d["titles"] == 0


def test_final_positions_are_unique_even_on_equal_points(out):
    t = out["_tables"]
    by_season: dict[int, list[int]] = {}
    for d in out["drivers.json"]:
        for row in out[f"driver/{d['id']}.json"]["season_rows"]:
            if row["pos"] is not None:
                by_season.setdefault(row["s"], []).append(row["pos"])
    for season, positions in by_season.items():
        assert len(positions) == len(set(positions)), season
    assert len(by_season) == len(t.races["season"].unique())
    # 2025 Hulkenberg와 Hadjar는 51점 동점이고 Jolpica 순위(11, 12)를 따른다.
    assert season_row(out, "hulkenberg", 2025)["pts"] == season_row(out, "hadjar", 2025)["pts"]
    assert (season_row(out, "hulkenberg", 2025)["pos"], season_row(out, "hadjar", 2025)["pos"]) == (
        11,
        12,
    )


def test_norris_2025(out):
    row = season_row(out, "norris", 2025)
    assert (row["pos"], row["pts"], row["wins"]) == (1, 423, 7)
    assert row["rpts"] + row["spts"] == row["pts"]
    assert row["round_pts"][-1] == 423 and len(row["round_pos"]) == row["rounds"] == 24
    h = next(s for s in out["history.json"]["seasons"] if s["season"] == 2025)
    assert h["d1"]["id"] == "norris" and h["d2"] == {
        "id": "max_verstappen",
        "name": "Max Verstappen",
        "pts": 421,
    }
    assert (h["margin"], h["margin_pct"], h["lead_change"]) == (2, 0.47, 20)
    assert h["c1"]["id"] == "mclaren" and h["winners"] == 4


def test_shared_drives_and_fractional_points(out, drivers):
    # 1951 프랑스: Fagioli가 출발한 차를 Fangio가 넘겨받아 우승했다. Jolpica는 둘 다 1위로 적는다.
    fagioli = out["driver/fagioli.json"]["races"]
    assert any(r["s"] == 1951 and r["r"] == 4 and r["p"] == 1 for r in fagioli)
    assert drivers["fagioli"]["wins"] == 1
    fangio_rows = [r for r in out["driver/fangio.json"]["races"] if r["s"] == 1951 and r["r"] == 4]
    assert len(fangio_rows) == 2 and all(r.get("x") == 1 for r in fangio_rows)
    # 결승 득점 합은 공유 점수(1/7 = 0.14 등)를 소수 둘째 자리로 맞춘 값이다.
    assert drivers["fangio"]["points"] == 279.14
    # 유효 득점 규정: 1956 Fangio의 결승 득점 34.5점 가운데 챔피언십 점수는 30점이다.
    row = season_row(out, "fangio", 1956)
    assert (row["rpts"], row["pts"], row["pos"]) == (34.5, 30, 1)
    # 공유 우승은 계산하지 않고 차량 공유 동료와는 비교하지 않는다(같은 position).
    mates = season_row(out, "fagioli", 1951)["mates"]
    fangio = next(m for m in mates if m["id"] == "fangio")
    assert fangio["n"] == 1 and fangio["rc"] == 0


def test_teammate_counts_are_symmetric(out):
    pairs: dict[tuple, dict] = {}
    for d in out["drivers.json"]:
        for row in out[f"driver/{d['id']}.json"]["season_rows"]:
            for m in row["mates"]:
                pairs[(row["s"], m["c"], d["id"], m["id"])] = m
                assert 0 <= m["ra"] <= m["rc"] <= m["n"]
                assert 0 <= m["qa"] <= m["qc"] <= m["n"]
                if row["s"] < site_drivers.QUALI_FIRST_SEASON:
                    assert m["qc"] == 0
    for (season, cid, a, b), m in pairs.items():
        other = pairs[(season, cid, b, a)]
        assert m["n"] == other["n"] and m["rc"] == other["rc"] and m["qc"] == other["qc"]
        assert m["ra"] + other["ra"] == m["rc"], (season, cid, a, b)
        assert m["qa"] + other["qa"] == m["qc"], (season, cid, a, b)
    # 인디애나폴리스 500은 비교에서 빠진다. Indy만 나온 드라이버에게는 동료가 없다.
    assert season_row(out, "parsons", 1950)["mates"] == []
    piastri = season_row(out, "piastri", 2025)["mates"]
    assert [(m["id"], m["n"], m["rc"], m["qc"]) for m in piastri] == [("norris", 24, 23, 24)]


def test_ferrari_and_lineage_titles(out):
    history = out["history.json"]
    ferrari = next(c for c in history["constructor_titles"] if c["id"] == "ferrari")
    assert ferrari["titles"] == 16 and ferrari["seasons"][-1] == 2008
    by_id = {c["id"]: c["titles"] for c in history["constructor_titles"]}
    assert (by_id["mclaren"], by_id["williams"], by_id["mercedes"], by_id["red_bull"]) == (
        10,
        9,
        8,
        6,
    )
    lineages = {lin["lineage_id"]: lin for lin in history["lineages"]}
    assert len(lineages) == 10
    assert lineages["maranello"]["wins"] == 248 and lineages["maranello"]["titles"] == 16
    # 브래클리 계보: Tyrrell 1971, Brawn 2009, Mercedes 2014-2021.
    assert lineages["brackley"]["title_seasons"] == [1971, 2009, *range(2014, 2022)]
    assert lineages["enstone"]["title_seasons"] == [1995, 2005, 2006]
    assert lineages["kannapolis"]["wins"] == 0
    # 1954-1955 Mercedes 워크스는 브래클리 계보가 아니다.
    assert all(r["s"] >= 1970 for r in lineages["brackley"]["seasons"])


def test_constructor_adjustments(out):
    seasons = {s["season"]: s for s in out["history.json"]["seasons"]}
    assert all(seasons[y]["c1"] is None for y in range(1950, 1958))
    assert seasons[1958]["c1"]["id"] == "vanwall"
    assert seasons[2007]["c2"]["id"] == "bmw_sauber"
    assert seasons[2007]["c_adjusted"] == [
        {"id": "mclaren", "name": "McLaren", "kind": "excluded", "pts": 0, "pos": None}
    ]
    assert seasons[2020]["c_adjusted"][0]["kind"] == "deducted"


def test_f1db_point_differences_are_marked(out):
    seasons = {s["season"]: s for s in out["history.json"]["seasons"]}
    assert (seasons[1977]["d1"]["id"], seasons[1977]["d1"]["pts"]) == ("lauda", 70)
    assert seasons[1977]["d1"]["f1db_pts"] == 72
    assert seasons[1995]["c1"]["f1db_pts"] == 137 and seasons[1995]["c1"]["pts"] == 147
    marked = sorted(s["season"] for s in seasons.values() if s["c1"] and "f1db_pts" in s["c1"])
    assert marked == sorted(site_drivers.F1DB_CONSTRUCTOR_CHAMPION_POINTS)


def test_history_matches_season_json(out):
    for s in out["history.json"]["seasons"]:
        data = out["_seasons"][s["season"]]
        assert s["winners"] == data["facts"]["winners"]
        assert s["rounds"] == len(data["rounds"])
        assert [r["round"] for r in data["rounds"]] == list(range(1, s["rounds"] + 1))
        champ = next(d for d in data["drivers"] if d["id"] == s["d1"]["id"])
        assert champ["points"][-1] == s["d1"]["pts"]
        assert s["d1"]["led"] <= s["rounds"]
        if s["margin"] is not None:
            assert s["margin"] >= 0


def test_wins_ranking_keeps_ties(out, drivers):
    ranking = out["history.json"]["wins"]
    assert len(ranking) >= site_drivers.WINS_TOP
    assert ranking[0]["id"] == "hamilton" and ranking[0]["wins"] == 105
    cutoff = ranking[site_drivers.WINS_TOP - 1]["wins"]
    assert all(r["wins"] >= cutoff for r in ranking)
    assert sum(1 for d in drivers.values() if d["wins"] >= cutoff) == len(ranking)
    titles = out["history.json"]["driver_titles"]
    assert [t["id"] for t in titles[:2]] == ["michael_schumacher", "hamilton"]


def test_start_definition(out, drivers):
    # 1996 프랑스 Schumacher는 포메이션 랩에서 엔진이 멈춰 출발하지 않았다(status_code 30, 0랩).
    rows = out["driver/michael_schumacher.json"]["races"]
    france = next(r for r in rows if r["s"] == 1996 and r["r"] == 9)
    assert france["o"] == "N"
    assert drivers["michael_schumacher"]["entries"] == 308
    assert drivers["michael_schumacher"]["starts"] == 307
    # 랩을 돈 뒤 기권한 행은 출발로 센다(1976 후지 Lauda, 2랩).
    lauda = next(r for r in out["driver/lauda.json"]["races"] if r["s"] == 1976 and r["r"] == 16)
    assert lauda["st"] == "Withdrew" and lauda["o"] == "R"
    # 2025 라스베이거스 실격.
    norris = next(r for r in out["driver/norris.json"]["races"] if r["s"] == 2025 and r["r"] == 22)
    assert norris["o"] == "D" and norris["pts"] == 0


def test_sprints_are_separate(out, drivers):
    t = out["_tables"]
    total = sum(len(out[f"driver/{d}.json"]["sprints"]) for d in drivers)
    assert total == int((t.results["session_type"] == "SR").sum())
    for d in drivers.values():
        rows = out[f"driver/{d['id']}.json"]["races"]
        assert len({(r["s"], r["r"]) for r in rows}) == d["entries"]


def test_every_nationality_has_a_korean_label(drivers):
    assert all(d["nationality_ko"] for d in drivers.values())


def test_no_em_dash(out):
    dash = chr(0x2014)
    assert not any(dash in text for text in out["_text"])


def _f1db(name: str) -> list[dict]:
    path = F1DB_CSV / name
    if not path.exists():
        pytest.skip(f"F1DB 원본 CSV가 없다: {path}")
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if int(r["year"]) <= LAST_SEASON]


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def test_champions_match_f1db(out):
    rows = _f1db("f1db-seasons-driver-standings.csv")
    f1db = {int(r["year"]): r for r in rows if r["championshipWon"] == "true"}
    history = {s["season"]: s for s in out["history.json"]["seasons"]}
    assert set(f1db) == set(history)
    t = out["_tables"]
    surnames = {r.driver_id: _fold(r.surname) for r in t.drivers.itertuples()}
    for season, row in f1db.items():
        mine = history[season]["d1"]
        # F1DB ID는 이름-성 꼴이다(niki-lauda). 성으로 같은 사람인지 본다.
        assert surnames[mine["id"]].replace(" ", "-") in row["driverId"], season
        expected = float(row["points"])
        if season in site_drivers.F1DB_DRIVER_CHAMPION_POINTS:
            assert mine["f1db_pts"] == expected != mine["pts"], season
        else:
            assert "f1db_pts" not in mine, season
            assert mine["pts"] == pytest.approx(expected), season
    rows = _f1db("f1db-seasons-constructor-standings.csv")
    f1db_c = {int(r["year"]): float(r["points"]) for r in rows if r["positionNumber"] == "1"}
    assert set(f1db_c) == {s for s in history if s >= 1958}
    for season, points in f1db_c.items():
        mine = history[season]["c1"]
        if season in site_drivers.F1DB_CONSTRUCTOR_CHAMPION_POINTS:
            assert mine["f1db_pts"] == points != mine["pts"], season
        else:
            assert "f1db_pts" not in mine, season
            assert mine["pts"] == pytest.approx(points), season


def test_career_totals_match_f1db(drivers):
    rows = _f1db("f1db-races-race-results.csv")
    pairs = {
        "lewis-hamilton": "hamilton",
        "michael-schumacher": "michael_schumacher",
        "ayrton-senna": "senna",
        "max-verstappen": "max_verstappen",
        "lando-norris": "norris",
        "juan-manuel-fangio": "fangio",
        "sebastian-vettel": "vettel",
        "fernando-alonso": "alonso",
        "alain-prost": "prost",
    }
    not_entered = {"DNQ", "DNPQ"}  # F1DB 결승 결과에는 예선 탈락 행이 있고 Jolpica에는 없다.
    for f1db_id, driver_id in pairs.items():
        mine = [
            r for r in rows if r["driverId"] == f1db_id and r["positionText"] not in not_entered
        ]
        races = {(r["year"], r["round"]) for r in mine}
        wins = {(r["year"], r["round"]) for r in mine if r["positionNumber"] == "1"}
        poles = {(r["year"], r["round"]) for r in mine if r["polePosition"] == "true"}
        podiums = {
            (r["year"], r["round"])
            for r in mine
            if r["positionNumber"] and int(r["positionNumber"]) <= 3
        }
        d = drivers[driver_id]
        assert d["entries"] == len(races), driver_id
        assert d["wins"] == len(wins), driver_id
        assert d["poles"] == len(poles), driver_id
        assert d["podiums"] == len(podiums), driver_id
