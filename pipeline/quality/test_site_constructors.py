"""컨스트럭터 페이지 JSON과 드라이버 대회 행의 새 필드 테스트.

constructors.json, constructor/<id>.json, driver/<id>.json의 q, rc, m을 본다. 정제 테이블에서
바로 만든 산출물이고, 기대값은 Jolpica 정제 테이블에서 센 값과 드라이버 쪽과 챔피언십
분석(history.json)이 이미 검증한 값이다. 두 쪽은 같은 결과 행 문맥(site_drivers._Context)을 쓴다.
"""

from __future__ import annotations

import json

import pytest

from pipeline import build_site_data, site_constructors, site_drivers
from pipeline.config import LAST_SEASON


@pytest.fixture(scope="module")
def out():
    t = build_site_data.Tables()
    first = int(t.races["season"].min())
    seasons = {s: build_site_data.build_season(t, s) for s in range(first, LAST_SEASON + 1)}
    files: dict[str, object] = {}

    def write(name: str, payload: object) -> None:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        files[name] = json.loads(text)
        files.setdefault("_text", []).append(text)

    ctx = site_drivers.make_context(t, seasons)
    site_drivers.build_all(t, seasons, write, ctx)
    site_constructors.build_all(ctx, write)
    files["_tables"] = t
    return files


@pytest.fixture(scope="module")
def ctrs(out):
    return {c["id"]: c for c in out["constructors.json"]}


def race_rows(out):
    t = out["_tables"]
    return t.results[t.results["session_type"] == "R"]


def test_one_file_per_constructor_with_a_race_result(out, ctrs):
    race = race_rows(out)
    assert set(ctrs) == set(race["constructor_id"])
    assert len(ctrs) == 203
    for cid, c in ctrs.items():
        assert f"constructor/{cid}.json" in out
        assert c["years"] == sorted(set(race[race["constructor_id"] == cid]["season"]))
    assert sum(c["in_2025"] for c in ctrs.values()) == 10


def test_every_result_row_is_on_one_constructor_page(out, ctrs):
    rows = sum(len(out[f"constructor/{cid}.json"]["races"]) for cid in ctrs)
    assert rows == len(race_rows(out))
    assert sum(c["cars"] for c in ctrs.values()) == rows


def test_titles_match_history(out, ctrs):
    history = {r["id"]: r for r in out["history.json"]["constructor_titles"]}
    titled = {cid: c for cid, c in ctrs.items() if c["titles"]}
    assert set(titled) == set(history)
    for cid, c in titled.items():
        assert c["title_seasons"] == history[cid]["seasons"]
    assert ctrs["ferrari"]["titles"] == 16
    assert ctrs["mclaren"]["title_seasons"][-2:] == [2024, 2025]


def test_driver_titles_follow_the_champion(out, ctrs):
    # 그 시즌 드라이버 챔피언이 나선 컨스트럭터. 1954 Fangio는 Maserati와 Mercedes 둘 다다.
    assert 1954 in ctrs["maserati"]["driver_title_seasons"]
    assert 1954 in ctrs["mercedes"]["driver_title_seasons"]
    assert ctrs["mclaren"]["driver_title_seasons"][-1] == 2025
    total = sum(c["driver_titles"] for c in ctrs.values())
    seasons = len(out["history.json"]["seasons"])
    assert seasons <= total <= seasons + 5


def test_wins_and_podiums_match_race_tally(out, ctrs):
    t = out["_tables"]
    race = race_rows(out)
    winners = race[race["position"] == 1][["season", "round", "constructor_id"]].drop_duplicates()
    assert sum(c["wins"] for c in ctrs.values()) == len(winners)
    for cid in ("ferrari", "mclaren", "williams", "cooper-climax"):
        rows = out[f"constructor/{cid}.json"]["season_rows"]
        for r in rows:
            tally = t.race_tally[(r["s"], cid)]
            assert r["entries"] == tally["entered"]
            assert r["wins"] == tally["wins"]
            assert r["podiums"] == tally["podiums"]


def test_outcome_parts_add_up(out, ctrs):
    for cid in ctrs:
        for r in out[f"constructor/{cid}.json"]["season_rows"]:
            parts = r["classified"] + r["dsq"] + r["dns"] + sum(r["causes"].values())
            assert parts == r["cars"], (cid, r["s"])
            assert sum(d["n"] for d in r["drivers"]) >= r["entries"]


def test_mclaren_2025(out):
    c = out["constructor/mclaren.json"]
    row = next(r for r in c["season_rows"] if r["s"] == 2025)
    assert row["pos"] == 1 and row["pts"] == 833
    assert row["wins"] == 14 and row["entries"] == 24 and row["cars"] == 48
    assert row["dsq"] == 2  # 라스베이거스 두 차 실격
    assert row["driver_champ"] == "norris"
    assert [d["id"] for d in row["drivers"]] == ["norris", "piastri"] or [
        d["id"] for d in row["drivers"]
    ] == ["piastri", "norris"]
    assert len(row["round_pos"]) == row["rounds"] == 24
    assert row["engine"] == "Mercedes"


def test_retire_causes():
    def row(code, detail, classified=False, laps=10):
        return site_drivers.Row(2000, 1, "x", "y", 1, 10, classified, code, detail, laps, 0.0)

    assert site_drivers.retire_cause(row(10, "Collision")) == "acc"
    assert site_drivers.retire_cause(row(11, "Engine")) == "mech"
    assert site_drivers.retire_cause(row(11, "Retired")) == "unk"
    assert site_drivers.retire_cause(row(11, "Physical")) == "oth"
    assert site_drivers.retire_cause(row(1, "Not classified")) == "nc"
    assert site_drivers.retire_cause(row(1, "Finished", classified=True)) is None
    assert site_drivers.retire_cause(row(20, "Disqualified")) is None
    assert site_drivers.retire_cause(row(30, "Did not start", laps=0)) is None


def test_quali_rank_and_mates_on_driver_rows(out):
    races = {(r["s"], r["r"]): r for r in out["driver/norris.json"]["races"]}
    aus = races[(2025, 1)]
    assert aus["q"] == 1  # 2025 호주 폴
    assert aus["m"] == [["piastri", "F", 9]]
    vegas = races[(2025, 22)]
    assert vegas["o"] == "D" and vegas["m"][0][:2] == ["piastri", "D"]
    # 예선 순위는 대회마다 1부터 빈틈없이 매긴다(같은 키는 같은 순위)
    t = out["_tables"]
    ctx_ranks = site_drivers.quali_ranks(site_drivers._quali_keys(t.qualifying))
    by_race: dict[tuple[int, int], list[int]] = {}
    for (s, r, _), q in ctx_ranks.items():
        by_race.setdefault((s, r), []).append(q)
    for ranks in by_race.values():
        assert min(ranks) == 1
    # 인디애나폴리스 500과 동료가 넷 이상인 대회는 동료 결과를 싣지 않는다
    for r in out["driver/parsons.json"]["races"]:
        assert "m" not in r


def test_no_em_dash_or_nan(out):
    for text in out["_text"]:
        assert chr(0x2014) not in text
        assert "NaN" not in text


def kit_of(out, cid, season):
    return next(r for r in out[f"constructor/{cid}.json"]["season_rows"] if r["s"] == season)["kit"]


def test_kit_chassis_examples(out):
    # 한 시즌에 섀시를 둘 이상 등록한 대표 사례(F1DB 시즌별 참가 팀 섀시 표)
    ferrari = kit_of(out, "ferrari", 2003)
    assert [k["c"] for k in ferrari] == [["Ferrari F2002B", "Ferrari F2003-GA"]]
    brabham = kit_of(out, "brabham", 1978)
    assert "Brabham BT46B" in brabham[0]["c"]
    assert kit_of(out, "mclaren", 2025) == [
        {"e": "McLaren F1 Team", "c": ["McLaren MCL39"], "g": ["Mercedes-AMG F1 M16 1.6 V6 T H"]}
    ]
    # 섀시와 엔진 조합 ID에는 그 엔진을 쓴 참가 팀만 들어간다
    climax = kit_of(out, "cooper-climax", 1960)
    assert climax and all(g.startswith("Climax") for k in climax for g in k["g"])
    assert not any("Maserati" in g for k in climax for g in k["g"])
    # 이름이 다른 Jolpica ID도 결승 결과 대조로 맞춘다(team_lotus, alfa)
    assert any("Lotus 79" in c for k in kit_of(out, "team_lotus", 1978) for c in k["c"])
    assert kit_of(out, "alfa", 1950)[0]["c"] == ["Alfa Romeo 158"]


def test_kit_scope_and_coverage(out, ctrs):
    unmatched = []
    for cid in ctrs:
        for r in out[f"constructor/{cid}.json"]["season_rows"]:
            if 2010 <= r["s"] <= 2021:
                assert r["kit"] is None, (cid, r["s"])  # 2026-11-18 결정: 싣지 않는다
                continue
            assert r["kit"] is not None
            if not r["kit"]:
                unmatched.append((r["s"], cid))
            for k in r["kit"]:
                assert k["e"] and k["c"] and k["c"] == sorted(set(k["c"]))
    # F1DB 결승 결과에 차가 없는(출발하지 않은 기록만 있는) 5개 시즌만 맞추지 못한다
    assert sorted(unmatched) == [
        (1961, "mbm"), (1962, "team_lotus"), (1963, "team_lotus"), (1963, "tomaso"), (1965, "re"),
    ]  # fmt: skip
    t = out["_tables"]
    race = race_rows(out)
    for season, cid in unmatched:
        rows = race[(race["season"] == season) & (race["constructor_id"] == cid)]
        assert set(rows["status_detail"]) == {"Withdrew"}
    assert t.entrant_chassis["chassis_full_name"].notna().all()


def test_engine_fact_for_combo_ids(out, ctrs):
    # 섀시와 엔진 조합 ID도 결승 결과 대조로 엔진 제조사를 채운다.
    # 비는 것은 맞추지 못한 5개 시즌뿐이다.
    row = next(r for r in out["constructor/cooper-climax.json"]["season_rows"] if r["s"] == 1960)
    assert row["engine"] == "Climax"
    empty = sorted(
        (r["s"], cid)
        for cid in ctrs
        for r in out[f"constructor/{cid}.json"]["season_rows"]
        if not r["engine"]
    )
    assert empty == [
        (1961, "mbm"), (1962, "team_lotus"), (1963, "team_lotus"), (1963, "tomaso"), (1965, "re"),
    ]  # fmt: skip
