"""T19 체코지수 검증."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from pipeline.config import CURATED_DIR
from pipeline.transforms import race_score as rs

OF = CURATED_DIR / "openf1"
J = CURATED_DIR / "jolpica"
SCORE = CURATED_DIR / "score"


@pytest.fixture(scope="module")
def all_inputs():
    return pd.read_parquet(SCORE / "race_inputs.parquet")


@pytest.fixture(scope="module")
def all_scores():
    return pd.read_parquet(SCORE / "race_score.parquet")


@pytest.fixture(scope="module")
def inputs(all_inputs):
    """OpenF1 계열(2023-2025). 아래 대부분의 검증은 이 계열의 정의를 본다."""
    return all_inputs[all_inputs["method"] == "openf1"].reset_index(drop=True)


@pytest.fixture(scope="module")
def scores(all_scores):
    return all_scores[all_scores["season"] >= 2023].reset_index(drop=True)


@pytest.fixture(scope="module")
def jolpica_inputs(all_inputs):
    """Jolpica 계열(2014-2022)."""
    return all_inputs[all_inputs["method"] == "jolpica"].reset_index(drop=True)


@pytest.fixture(scope="module")
def formulas():
    return rs.load_formulas()


@pytest.fixture(scope="module")
def openf1():
    names = ["laps", "stints", "pit", "race_control", "session_result"]
    return {n: pd.read_parquet(OF / f"{n}.parquet") for n in names}


@pytest.fixture(scope="module")
def race_results():
    results = pd.read_parquet(J / "results.parquet")
    return results[results["session_type"] == "R"]


def session_key(season: int, rnd: int) -> int:
    mm = pd.read_csv(OF / "meeting_map.csv")
    return int(mm[(mm["season"] == season) & (mm["round"] == rnd)]["race_session_key"].iloc[0])


def race_part(openf1: dict, season: int, rnd: int) -> dict:
    key = session_key(season, rnd)
    return {n: t[t["session_key"] == key] for n, t in openf1.items()}


def race_lap_table(openf1: dict, season: int, rnd: int) -> pd.DataFrame:
    part = race_part(openf1, season, rnd)
    winner = part["session_result"][part["session_result"]["position"] == 1]
    race_laps = int(winner["number_of_laps"].iloc[0])
    return rs.lap_table(part["laps"], part["stints"], part["pit"], part["race_control"], race_laps)


# --- 공식 ---------------------------------------------------------------------------------


def example(changes, leads, gap, sc, vsc, dnf, condition):
    return SimpleNamespace(
        position_changes=changes, lead_changes=leads, win_gap_s=gap, sc_periods=sc,
        vsc_periods=vsc, dnf=dnf, track_condition=condition, finished_behind_safety_car=False,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (example(176, 35, 0.639, 1, 0, 3, "dry"), 87.9),
        (example(17, 2, 4.351, 0, 1, 4, "dry"), 17.75),
        (example(55, 5, 2.307, 2, 1, 3, "mixed"), 46.55),
        (example(147, 6, 2.754, 2, 0, 6, "mixed"), 77.25),
        (example(36, 3, 2.256, 1, 1, 5, "dry"), 31.7),
    ],
)
def test_v0_1_reproduces_the_worked_examples_of_the_proposal(formulas, row, expected):
    """제안 원문의 계산 예 다섯 건. 원문의 추월 횟수를 순위 변동 자리에 넣으면 합계가 같다."""
    assert rs.score_race(row, formulas["v0.1"], {})["score"] == pytest.approx(expected, abs=0.005)


def test_weights_sum_to_one_and_items_are_known(formulas):
    """v0.1과 v0.2는 제안 원문의 여섯 항목이다. v0.3은 세 항목을, v0.4는 이변 항목을 더 넣었다.
    v0.5는 v0.4와 항목이 같고 비중만 다르다."""
    expected = {
        "v0.1": rs.ITEM_IDS[:6], "v0.2": rs.ITEM_IDS[:6], "v0.3": rs.ITEM_IDS[:9],
        "v0.4": rs.ITEM_IDS, "v0.5": rs.ITEM_IDS,
    }  # fmt: skip
    assert set(formulas) == set(expected)
    for name, formula in formulas.items():
        assert [i["id"] for i in formula["items"]] == expected[name]
        assert sum(i["weight"] for i in formula["items"]) == pytest.approx(1.0)


def test_gap_table_boundaries(formulas):
    table, over = formulas["v0.2"]["gap_table"], formulas["v0.2"]["gap_over"]
    gaps = [0.0, 1.0, 1.001, 3.0, 5.0, 10.0, 20.0, 20.001]
    assert [rs.gap_points(g, table, over) for g in gaps] == [100, 100, 80, 80, 60, 40, 20, 0]


def test_safety_car_table_and_cap(formulas):
    table = formulas["v0.2"]["safety_car_table"]
    assert rs.safety_car_points(1, 1, table, None) == 60
    assert rs.safety_car_points(5, 0, table, None) == 100
    assert rs.safety_car_points(3, 1, table, None) == 110
    assert rs.safety_car_points(3, 1, table, 100) == 100


def test_percentile_points():
    reference = np.array([0, 0, 1, 2, 2, 5], dtype=float)
    assert rs.percentile_points(0, reference) == 0
    assert rs.percentile_points(2, reference) == pytest.approx(60)
    assert rs.percentile_points(5, reference) == 100
    assert rs.percentile_points(9, reference) == 100  # 기준 대회에 없던 큰 값


# --- 랩 끝 순서 ---------------------------------------------------------------------------


def test_crossing_times_ignore_a_wrong_start_time():
    """출발 시각 하나가 2초 틀려도 랩 타임을 이어 붙인 끝 시각은 그대로다."""
    laps = np.arange(1, 8)
    duration = np.array([np.nan, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0])
    start = np.array([0.0, 95.0, 185.0, 275.0, 367.0, 455.0, 545.0])  # 5랩 출발이 2초 늦게 적힘
    shared = np.array([True, False, False, False, False, False, False])
    ends = rs.crossing_times(laps, start, duration, shared)
    assert ends == pytest.approx([95.0, 185.0, 275.0, 365.0, 455.0, 545.0, 635.0])


def test_crossing_times_skip_shared_placeholder_rows():
    """랩 타임이 없는 마지막 랩은 다음 행의 출발 시각이 자리표시면 끝 시각을 내지 않는다."""
    laps = np.array([1, 2, 3, 4])
    duration = np.array([np.nan, 90.0, np.nan, np.nan])
    start = np.array([0.0, 95.0, 185.0, 999.0])
    shared = np.array([True, False, False, True])
    ends = rs.crossing_times(laps, start, duration, shared)
    assert ends[:2] == pytest.approx([95.0, 185.0])
    assert np.isnan(ends[2]) and np.isnan(ends[3])


def synthetic_table(ends: dict[int, list[float]], pit=(), neutral=()) -> pd.DataFrame:
    rows = []
    for driver, values in ends.items():
        for lap, end in enumerate(values, start=1):
            rows.append(
                {
                    "driver_number": driver,
                    "lap_number": lap,
                    "begin_s": end - 90,
                    "end_s": end,
                    "pit_lap": (driver, lap) in pit,
                    "neutral_lap": (driver, lap) in neutral,
                }  # fmt: skip
            )
    return pd.DataFrame(rows)


def test_position_changes_count_swaps_but_not_pit_or_neutral_laps():
    ends = {1: [90, 180, 272, 360], 2: [91, 181, 271, 361], 3: [95, 185, 275, 365]}
    # 3랩에 2번이 1번을 앞서고 4랩에 1번이 되찾는다
    assert rs.position_changes(synthetic_table(ends)) == 2
    assert rs.lead_changes(synthetic_table(ends)) == 2
    assert rs.position_changes(synthetic_table(ends, pit={(1, 3)})) == 1
    assert rs.position_changes(synthetic_table(ends, neutral={(2, 4)})) == 1
    assert rs.lead_changes_on_track(synthetic_table(ends, pit={(1, 3)})) == 1


def test_places_lost_in_one_lap_are_capped():
    """한 랩에 다섯 자리를 내준 차는 세 자리까지만 센다. 내준 자리는 그 차의 앞 랩 순위다."""
    ends = {n: [90 + n, 180 + n] for n in range(1, 7)}
    ends[1] = [91, 250]  # 선두가 2랩에 다섯 대에게 순서를 내준다
    found = rs.swaps(synthetic_table(ends))
    assert len(found) == rs.MAX_PLACES_LOST_PER_LAP == 3
    assert set(found["place"]) == {1} and set(found["lap_number"]) == {2}


def test_position_change_tiers_split_by_place_and_late_laps():
    """20랩 결승의 막판은 19-20랩이다. 2위 자리는 포디움권, 5위 자리는 포인트권이다."""
    ends = {n: [90 * lap + n for lap in range(1, 21)] for n in range(1, 13)}
    ends[2][9] -= 1.5  # 10랩: 2번이 1번 앞으로 (1위 자리)
    for lap in range(10, 20):
        ends[2][lap] -= 1.5
    ends[6][19] -= 1.5  # 20랩: 6번이 5번 앞으로 (5위 자리, 막판)
    ends[12][18] -= 1.5  # 19랩: 12번이 11번 앞으로 (11위 자리, 막판)
    ends[12][19] -= 1.5
    tiers = rs.position_change_tiers(synthetic_table(ends), 20)
    assert tiers == {
        "pc_podium": 1, "pc_late_podium": 0, "pc_points": 1, "pc_late_points": 1,
        "pc_rest": 1, "pc_late_rest": 1,
    }  # fmt: skip


def test_lapped_cars_do_not_count_as_position_changes():
    """한 바퀴 뒤진 차가 선두에게 추월당해도 같은 랩의 통과 순서는 바뀌지 않는다."""
    ends = {1: [90, 180, 270, 360], 2: [130, 270.5, 411, 551.5]}
    assert rs.position_changes(synthetic_table(ends)) == 0


def test_lap_order_matches_the_jolpica_lap_chart(openf1, race_results):
    """2023년 21라운드 라스베이거스 16랩의 순서.

    기댓값은 Jolpica 랩 차트다(https://api.jolpi.ca/ergast/f1/2023/21/laps/16/, 2026-11-25 확인).
    """
    expected = [
        "leclerc", "max_verstappen", "gasly", "ocon", "hamilton", "perez", "albon", "stroll",
        "piastri", "sainz", "zhou", "alonso", "russell", "ricciardo", "bottas", "sargeant",
        "kevin_magnussen", "hulkenberg", "tsunoda",
    ]  # fmt: skip
    table = race_lap_table(openf1, 2023, 21)
    lap = table[(table["lap_number"] == 16) & table["end_s"].notna()].sort_values("end_s")
    results = race_results[(race_results["season"] == 2023) & (race_results["round"] == 21)]
    ids = results.set_index("car_number")["driver_id"]
    assert [ids[n] for n in lap["driver_number"]] == expected


def test_last_lap_leader_is_the_winner(openf1, race_results, inputs):
    """마지막 랩을 가장 먼저 끝낸 차가 결승 1위다. 도로 위 1위가 실격된 대회만 다르다."""
    disqualified_winner = {(2024, 14)}  # Russell이 먼저 들어온 뒤 실격됐다
    for row in inputs[inputs["order_status"] == "ok"].itertuples():
        leaders = rs.lap_leaders(race_lap_table(openf1, row.season, row.round))
        results = race_results[
            (race_results["season"] == row.season) & (race_results["round"] == row.round)
        ]
        winner = int(results[results["position"] == 1]["car_number"].iloc[0])
        assert list(leaders.index) == list(range(1, row.race_laps + 1)), (row.season, row.round)
        same = int(leaders.iloc[-1]) == winner
        assert same != ((row.season, row.round) in disqualified_winner), (row.season, row.round)


def test_transponder_failure_does_not_inflate_position_changes(openf1):
    """2025년 4라운드 바레인: 63번의 출발 시각이 38랩부터 틀려도 한 랩에 수십 번 뒤바뀌지 않는다."""
    table = race_lap_table(openf1, 2025, 4)
    ends = table.pivot(index="lap_number", columns="driver_number", values="end_s")
    ahead_38 = (ends.loc[38] < ends.loc[38, 63]).sum()
    ahead_39 = (ends.loc[39] < ends.loc[39, 63]).sum()
    assert abs(int(ahead_38) - int(ahead_39)) <= 1


# --- 레이스 컨트롤 ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("race", "expected"),
    [
        # 가상 세이프티 카가 세이프티 카로 바뀐 대회는 세이프티 카로만 센다
        ((2023, 10), {"sc_periods": 1, "vsc_periods": 0, "red_flags": 0}),
        ((2024, 5), {"sc_periods": 2, "vsc_periods": 0, "red_flags": 0}),
        # 적기 세 번. 체커 뒤의 적기는 세지 않는다
        ((2023, 3), {"sc_periods": 3, "vsc_periods": 1, "red_flags": 3}),
        # 출발 전 적기는 결승 중의 적기가 아니다
        ((2025, 13), {"sc_periods": 0, "vsc_periods": 0, "red_flags": 0}),
    ],
)
def test_neutral_period_counts(inputs, race, expected):
    row = inputs[(inputs["season"] == race[0]) & (inputs["round"] == race[1])].iloc[0]
    assert {k: int(row[k]) for k in expected} == expected


def test_races_that_finished_behind_the_safety_car(inputs):
    behind = inputs[inputs["finished_behind_safety_car"]]
    assert sorted(zip(behind["season"], behind["round"], strict=True)) == [(2023, 3), (2025, 10)]


# --- 정제 테이블 --------------------------------------------------------------------------


def test_inputs_cover_every_race_2023_2025(inputs):
    races = pd.read_parquet(J / "races.parquet")
    races = races[races["season"].between(2023, 2025)]
    assert len(inputs) == len(races) == 70
    assert not inputs.duplicated(["season", "round"]).any()


def test_only_miami_2025_lacks_lap_data(inputs, scores):
    missing = inputs[inputs["order_status"] != "ok"]
    assert list(zip(missing["season"], missing["round"], strict=True)) == [(2025, 6)]
    assert missing["position_changes"].isna().all() and missing["lead_changes"].isna().all()
    miami = scores[(scores["season"] == 2025) & (scores["round"] == 6)]
    assert miami["score"].isna().all()
    assert miami.set_index("formula")["status"].to_dict() == {
        "v0.1": "missing:position_changes,lead_changes",
        "v0.2": "missing:position_changes,lead_changes",
        "v0.3": "missing:position_changes,lead_changes,dnf",
        "v0.4": "missing:position_changes,lead_changes,dnf",
        "v0.5": "missing:position_changes,lead_changes,dnf",
    }


def test_win_gap_matches_the_records_in_the_proposal(race_results):
    """제안 원문이 적은 격차: 2012년 브라질 2.754초, 2021년 아부다비 2.256초."""
    for (season, rnd), gap in {(2012, 20): 2.754, (2021, 22): 2.256}.items():
        results = race_results[(race_results["season"] == season) & (race_results["round"] == rnd)]
        assert rs.win_gap_seconds(results) == gap


def test_dnf_agrees_with_jolpica_status(openf1, race_results, inputs):
    """OpenF1의 dnf 표시와 Jolpica의 상태가 같은 차를 가리킨다.

    Jolpica 쪽은 완주, 실격, 미출발이 아닌 차에서 OpenF1이 미출발로 적었거나 싣지 않은 차를 뺀다.
    Jolpica 상태만으로는 포메이션 랩 사고(2025년 1라운드 Hadjar)와 1랩 사고를 가를 수 없어서다.
    """
    not_retired = {"Finished", "Lapped", "Disqualified", "Did not start"}
    for row in inputs.itertuples():
        result = race_part(openf1, row.season, row.round)["session_result"]
        listed = set(result["driver_number"])
        not_started = set(result[result["dns"].fillna(False)]["driver_number"])
        jolpica = race_results[
            (race_results["season"] == row.season) & (race_results["round"] == row.round)
        ]
        retired = {int(n) for n in jolpica[~jolpica["status_detail"].isin(not_retired)].car_number}
        retired = {n for n in retired if n in listed and n not in not_started}
        assert retired == set(result[result["dnf"].fillna(False)]["driver_number"])
        assert row.dnf == len(retired)


def test_track_condition_classes(inputs):
    def races(condition: str) -> list[tuple[int, int]]:
        rows = inputs[inputs["track_condition"] == condition]
        return list(zip(rows["season"], rows["round"], strict=True))

    assert races("wet") == [(2024, 21)]  # 상파울루: 슬릭을 쓴 차가 없다
    mixed = [(2023, 6), (2023, 13), (2024, 9), (2024, 12), (2025, 1), (2025, 12), (2025, 13)]
    assert races("mixed") == mixed
    assert len(races("dry")) == 62


def test_v0_2_scores_stay_within_0_and_100(scores, formulas):
    v2 = scores[(scores["formula"] == "v0.2") & (scores["status"] == "ok")]
    assert len(v2) == 69
    assert v2["score"].between(0, 100).all()
    for item in formulas["v0.2"]["items"]:
        points = v2[f"pt_{item['id']}"]
        assert points.between(0, item["weight"] * 100 + 1e-9).all(), item["id"]
    # 백분위 항목: 기준 대회에서 가장 작은 값은 0점, 하나뿐인 가장 큰 값은 만점
    assert v2["pt_position_changes"].min() == 0
    assert v2["pt_position_changes"].max() == pytest.approx(35)


# --- 댓글 의견으로 더한 원값 (v0.3) -------------------------------------------------------


def test_tier_counts_add_up(inputs):
    ok = inputs[inputs["order_status"] == "ok"]
    changes = ok[["pc_podium", "pc_points", "pc_rest"]].sum(axis=1)
    assert (changes == ok["position_changes"]).all()
    for name in rs.TIERS:
        assert (ok[f"pc_late_{name}"] <= ok[f"pc_{name}"]).all()
    assert (ok[["dnf_podium", "dnf_points", "dnf_rest"]].sum(axis=1) == ok["dnf"]).all()


def test_dnf_from_a_podium_place(inputs):
    """2025년 15라운드 네덜란드: 리타이어 세 대 가운데 한 대는 2위로 달리다 64랩을 끝으로 멈췄다.

    나머지 두 대는 포인트권(4-10위)에서 멈췄다.
    """
    row = inputs[(inputs["season"] == 2025) & (inputs["round"] == 15)].iloc[0]
    assert (row["dnf_podium"], row["dnf_points"], row["dnf_rest"]) == (1, 2, 0)


def test_boundary_gaps_need_the_same_lap_count(race_results, inputs):
    """2024년 8라운드 모나코: 10위는 77랩, 11위는 76랩이라 격차를 내지 않는다."""
    monaco = race_results[(race_results["season"] == 2024) & (race_results["round"] == 8)]
    assert rs.gap_seconds(monaco, 10) is None
    assert rs.gap_seconds(monaco, 3) == 1.065
    assert inputs["gap_p3_p4_s"].notna().all()
    assert inputs["gap_p10_p11_s"].isna().sum() == 4


def test_grid_gains(race_results, inputs):
    """2025년 12라운드 영국: 19번 그리드에서 3위(16자리), 17번에서 7위(10자리), 5-9자리가 둘."""
    row = inputs[(inputs["season"] == 2025) & (inputs["round"] == 12)].iloc[0]
    assert (row["gain_5"], row["gain_10"], row["gain_15"]) == (2, 1, 1)
    britain = race_results[(race_results["season"] == 2025) & (race_results["round"] == 12)]
    assert rs.grid_gains(britain) == {"gain_5": 2, "gain_10": 1, "gain_15": 1}


def test_tyre_changes_ignore_pit_lane_drive_throughs_and_red_flags(openf1, inputs):
    """스틴트가 끊겨도 같은 타이어면 세지 않는다. 적기 중의 교체도 세지 않는다."""
    part = race_part(openf1, 2025, 10)  # 캐나다: 67-69랩에 세이프티 카를 따라 피트 레인을 지남
    changes = rs.tyre_changes(part["stints"], race_lap_table(openf1, 2025, 10))
    assert len(part["stints"][part["stints"]["driver_number"] == 1]) == 6
    assert changes[1] == 2
    part = race_part(openf1, 2023, 3)  # 호주: 1번은 적기 중에만 타이어를 바꿨다
    assert rs.tyre_changes(part["stints"], race_lap_table(openf1, 2023, 3))[1] == 0
    qatar = inputs[(inputs["season"] == 2023) & (inputs["round"] == 17)].iloc[0]
    assert qatar["pit_stops_mean"] == 3.0  # 2023년 17라운드 카타르: 완주차 평균 세 번


def test_round_points_max_bounds_every_gain_in_the_standings(inputs):
    """한 드라이버가 한 대회에 얻은 점수는 그 대회의 최대 점수를 넘지 않는다."""
    standings = pd.read_parquet(J / "driver_standings.parquet")
    standings = standings[standings["season"].between(2014, 2025)]
    standings = standings.sort_values(["season", "driver_id", "round"])
    gain = standings.groupby(["season", "driver_id"])["points"].diff().fillna(standings["points"])
    races = pd.read_parquet(J / "races.parquet").set_index(["season", "round"])["has_sprint"]
    limit = pd.Series(
        [
            rs.round_points_max(s, bool(races[(s, r)]), r)
            for s, r in zip(standings["season"], standings["round"], strict=True)
        ],
        index=standings.index,
    )
    assert (gain <= limit).all()
    assert (gain == limit).sum() >= 100  # 최대 점수를 실제로 얻은 대회가 있어야 상한이 헐겁지 않다
    # 2014년 최종전은 두 배 점수(50점)를 실제로 얻었다.
    # 2021년 스프린트 대회는 상한이 29점(25+1+3)이다. 결승 점수만으로는 나올 수 없는
    # 27점(2021년 10라운드)이 있어 스프린트 점수가 들어간다.
    assert gain[(standings["season"] == 2014) & (standings["round"] == 19)].max() == 50
    sprint_2021 = (standings["season"] == 2021) & standings["round"].isin([10, 14, 19])
    assert set(limit[sprint_2021]) == {29} and gain[sprint_2021].max() == 27


def test_title_context_before_the_2025_finale(inputs):
    """2025년 최종전: 앞 대회까지 1위 408점, 2위 396점. 남은 점수는 이 대회의 25점뿐이다."""
    row = inputs[(inputs["season"] == 2025) & (inputs["round"] == 24)].iloc[0]
    context = (row["title_gap_points"], row["round_points_max"], row["remaining_points_max"])
    assert context == (12, 25, 25)
    assert rs.title_points(*context) == pytest.approx(52)


def test_title_points_range():
    assert rs.title_points(0, 25, 25) == 100  # 동점으로 맞는 최종전
    assert rs.title_points(26, 25, 25) == 0  # 이미 정해진 타이틀
    assert rs.title_points(0, 25, 600) == pytest.approx(100 * 25 / 600)  # 시즌 초


def test_v0_3_scores_stay_within_0_and_100(scores, formulas):
    v3 = scores[(scores["formula"] == "v0.3") & (scores["status"] == "ok")]
    assert len(v3) == 69
    assert v3["score"].between(0, 100).all()
    for item in formulas["v0.3"]["items"]:
        points = v3[f"pt_{item['id']}"]
        assert points.between(0, item["weight"] * 100 + 1e-9).all(), item["id"]
    older = scores[scores["formula"].isin(["v0.1", "v0.2"])]
    assert older[["pt_grid_gains", "pt_pit_stops", "pt_title", "pt_upset"]].isna().all().all()
    assert v3["pt_upset"].isna().all()


# --- 이변 항목 (v0.4) ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def team_tables():
    standings = pd.read_parquet(J / "constructor_standings.parquet")
    lineage = pd.read_parquet(CURATED_DIR / "lineage" / "constructor_seasons.parquet")
    return standings, lineage


def test_team_ranks_before_the_opening_round_follow_the_lineage(race_results, team_tables):
    """개막전은 앞 시즌 최종 순위를 쓴다. 2024년 sauber와 rb는 2023년의 alfa와 alphatauri다."""
    opener = race_results[(race_results["season"] == 2024) & (race_results["round"] == 1)]
    ranks = rs.team_ranks_before(2024, 1, opener["constructor_id"].unique(), *team_tables)
    assert sorted(ranks.values()) == list(range(1, 11))
    assert (ranks["red_bull"], ranks["sauber"], ranks["rb"], ranks["haas"]) == (1, 9, 8, 10)


def test_team_ranks_before_a_later_round_are_the_standings(race_results, team_tables):
    """2025년 12라운드 영국 직전: sauber는 9위, alpine은 10위였다."""
    race = race_results[(race_results["season"] == 2025) & (race_results["round"] == 12)]
    ranks = rs.team_ranks_before(2025, 12, race["constructor_id"].unique(), *team_tables)
    assert (ranks["sauber"], ranks["alpine"]) == (9, 10)


@pytest.mark.parametrize(
    ("race", "expected"),
    [
        ((2025, 12), (1, 2)),  # 영국: 9위 팀의 3위. 맨 아래 두 팀의 포인트가 그 차를 포함해 둘
        ((2024, 21), (2, 2)),  # 상파울루: 9위 팀의 2위와 3위
        ((2023, 21), (0, 0)),  # 라스베이거스: 해당 없음
    ],
)
def test_upset_counts(inputs, race, expected):
    row = inputs[(inputs["season"] == race[0]) & (inputs["round"] == race[1])].iloc[0]
    assert (row["underdog_podiums"], row["bottom_team_points"]) == expected


def test_upset_totals(inputs):
    assert inputs["underdog_podiums"].sum() == 18
    assert (inputs["underdog_podiums"] > 0).sum() == 15
    assert inputs["bottom_team_points"].sum() == 52
    assert (inputs["bottom_team_points"] > 0).sum() == 38


def test_upset_points_are_capped(formulas):
    item = next(i for i in formulas["v0.4"]["items"] if i["id"] == "upset")
    assert rs.upset_points(0, 0, item) == 0
    assert rs.upset_points(1, 1, item) == 60
    assert rs.upset_points(2, 2, item) == 100


def test_v0_4_scores_stay_within_0_and_100(scores, formulas):
    v4 = scores[(scores["formula"] == "v0.4") & (scores["status"] == "ok")]
    assert len(v4) == 69
    assert v4["score"].between(0, 100).all()
    for item in formulas["v0.4"]["items"]:
        points = v4[f"pt_{item['id']}"]
        assert points.between(0, item["weight"] * 100 + 1e-9).all(), item["id"]


def test_scores_match_recalculation_from_inputs(all_inputs, all_scores):
    again = rs.build_scores(all_inputs)
    pd.testing.assert_frame_equal(again, all_scores, check_dtype=False)


# --- Jolpica 계열 (2014-2022) -------------------------------------------------------------


def test_jolpica_inputs_cover_every_race_2014_2022(jolpica_inputs):
    races = pd.read_parquet(J / "races.parquet")
    races = races[races["season"].between(*rs.JOLPICA_SEASONS)]
    assert len(jolpica_inputs) == len(races) == 182
    assert (jolpica_inputs["order_status"] == "ok").all()
    assert jolpica_inputs["race_session_key"].isna().all()
    # 노면을 추정하지 못한 결승은 한 랩으로 판정된 2021년 벨기에뿐이다
    no_spread = jolpica_inputs[jolpica_inputs["lap_time_spread"].isna()]
    assert list(zip(no_spread["season"], no_spread["round"], strict=True)) == [(2021, 12)]


def test_jolpica_estimates_only_safety_cars_and_dry_or_mixed(jolpica_inputs):
    """가상 세이프티 카와 웨트를 가르지 못하므로 그 두 값은 쓰지 않는다."""
    assert (jolpica_inputs["vsc_periods"] == 0).all()
    known = jolpica_inputs.dropna(subset=["lap_time_spread"])
    assert set(known["track_condition"]) == {"dry", "mixed"}
    mixed = known["track_condition"] == "mixed"
    assert (mixed == (known["lap_time_spread"] >= rs.RAIN_SPREAD_MIN)).all()


def test_lap_time_spread_separates_tyre_based_conditions(inputs):
    """2023-2025년에 같은 규칙을 적용하면 타이어로 판정한 혼용·웨트 8개를 모두 찾고, 맑은 결승
    62개 가운데 하나(2024년 8라운드 모나코)만 혼용으로 판정한다."""
    laps = pd.read_parquet(J / "race_laps.parquet")
    pits = pd.read_parquet(J / "pitstops.parquet")
    wrong = []
    for row in inputs.itertuples():
        lap = laps[(laps["season"] == row.season) & (laps["round"] == row.round)]
        pit = pits[(pits["season"] == row.season) & (pits["round"] == row.round)]
        guess = rs.spread_condition(rs.lap_time_spread(lap[lap["lap"] <= row.race_laps], pit))
        if (guess != "dry") != (row.track_condition != "dry"):
            wrong.append((row.season, row.round))
    assert wrong == [(2024, 8)]


def test_jolpica_races_that_finished_behind_the_safety_car(jolpica_inputs):
    """2014 캐나다·일본, 2015 중국, 2019·2020 바레인, 2022 이탈리아, 한 랩 판정의 2021 벨기에."""
    behind = jolpica_inputs[jolpica_inputs["finished_behind_safety_car"]]
    assert sorted(zip(behind["season"], behind["round"], strict=True)) == [
        (2014, 7), (2014, 15), (2015, 3), (2019, 2), (2020, 15), (2021, 12), (2022, 16),
    ]  # fmt: skip


def test_jolpica_lap_order_uses_the_lap_chart():
    """Jolpica 랩 순위는 그대로 랩 끝 순서다(2023년 21라운드 16랩)."""
    laps = pd.read_parquet(J / "race_laps.parquet")
    laps = laps[(laps["season"] == 2023) & (laps["round"] == 21)]
    pits = pd.read_parquet(J / "pitstops.parquet")
    pits = pits[(pits["season"] == 2023) & (pits["round"] == 21)]
    table, _ = rs.jolpica_lap_table(laps, pits)
    lap16 = table[table["lap_number"] == 16].sort_values("end_s")
    assert lap16["end_s"].tolist() == list(range(1, len(lap16) + 1))


def test_neutral_runs():
    assert rs.neutral_runs([]) == 0
    assert rs.neutral_runs([5, 6, 7, 20, 21, 40]) == 3


def test_methods_agree_on_2023_2025():
    """두 계열을 2023-2025년에 함께 계산한 결과. docs/methodology.md에 적은 값과 같아야 한다."""
    c = rs.compare_methods()
    assert c["races"] == 69
    assert c["score_corr"] >= 0.9 and c["rank_corr"] >= 0.9
    assert c["top10_overlap"] >= 8
    assert c["lead_changes_equal"] >= 0.95 and c["dnf_equal"] >= 0.95
    assert c["rain_class_equal"] >= 0.9


def test_v0_4_scores_2014_2022_stay_within_0_and_100(all_scores, formulas):
    v4 = all_scores[(all_scores["formula"] == "v0.4") & all_scores["season"].between(2014, 2022)]
    assert len(v4) == 182
    missing = v4[v4["status"] != "ok"]
    assert list(zip(missing["season"], missing["round"], missing["status"], strict=True)) == [
        (2021, 12, "missing:rain")
    ]
    ok = v4[v4["status"] == "ok"]
    assert ok["score"].between(0, 100).all()
    for item in formulas["v0.4"]["items"]:
        assert ok[f"pt_{item['id']}"].between(0, item["weight"] * 100 + 1e-9).all(), item["id"]


def test_reference_distribution_stays_2023_2025(all_inputs, inputs, formulas):
    """기준 시즌은 2023-2025 그대로라 Jolpica 계열을 더해도 공개한 점수의 기준 분포가 같다."""
    for formula in formulas.values():
        a, b = rs.reference_values(all_inputs, formula), rs.reference_values(inputs, formula)
        assert a.keys() == b.keys()
        for k in a:
            np.testing.assert_array_equal(a[k], b[k])


def test_v0_5_only_moves_weights(formulas, all_scores):
    """v0.5는 v0.4의 환산을 그대로 두고 비중만 옮긴다.

    타이틀 10->5, 피트 스톱 5->3, 순위 변동 20->24, 자리 격차 15->18.
    """
    v4, v5 = formulas["v0.4"], formulas["v0.5"]
    w4 = {i["id"]: i["weight"] for i in v4["items"]}
    w5 = {i["id"]: i["weight"] for i in v5["items"]}
    changed = {k: (w4[k], w5[k]) for k in w4 if w4[k] != w5[k]}
    assert changed == {
        "position_changes": (0.2, 0.24), "win_gap": (0.15, 0.18),
        "pit_stops": (0.05, 0.03), "title": (0.1, 0.05),
    }  # fmt: skip
    strip = ("weight", "basis")
    same = [{k: v for k, v in i.items() if k not in strip} for i in v4["items"]]
    assert same == [{k: v for k, v in i.items() if k not in strip} for i in v5["items"]]
    v5s = all_scores[(all_scores["formula"] == "v0.5") & (all_scores["status"] == "ok")]
    assert len(v5s) == 250 and v5s["score"].between(0, 100).all()
    for item in v5["items"]:
        assert v5s[f"pt_{item['id']}"].between(0, item["weight"] * 100 + 1e-9).all(), item["id"]
