"""체코지수 계산. (T19) 결승 한 경기를 항목별로 점수화한다.

DC인사이드 F1 갤러리 글의 제안을 이 저장소의 정제 데이터로 계산한다. 지수 이름과 처음 여섯 항목,
그 가중치와 환산표는 그 글에서 왔다(data/curated/score/formulas.json의 source_url). 공식은 판마다
따로 두며, v0.1과 v0.2는 여섯 항목, v0.3은 아홉 항목, v0.4는 열 항목이다.

    data/curated/score/race_inputs.parquet   대회별 항목 원값
    data/curated/score/race_score.parquet    공식 판별 항목 반영 점수와 합계
    data/curated/score/formulas.json         공식 판(가중치, 환산표, 기준 시즌)
    data/curated/score/method_comparison.json  2023-2025년 두 계열 대조(compare_methods)

항목 원값의 출처:
- 순위 변동, 선두 교체: OpenF1 랩의 결승선 통과 시각으로 랩마다 순서를 다시 세운다.
- 우승 격차와 자리 격차: Jolpica 결승 결과의 기록 차(1-2위, 3-4위, 10-11위).
- 세이프티 카, 가상 세이프티 카, 적기: OpenF1 레이스 컨트롤 메시지.
- DNF: OpenF1 세션 결과의 dnf 표시. 멈추기 전 순위는 랩 끝 순서에서 읽는다.
- 노면: OpenF1 스틴트의 타이어 종류.
- 순위 상승: Jolpica 결승 결과의 그리드와 순위.
- 피트 스톱: OpenF1 스틴트에서 센 타이어 교체 횟수.
- 타이틀 긴장도: Jolpica 드라이버 순위표와 시즌 일정.
- 이변: Jolpica 컨스트럭터 순위표와 계보 표로 정한 대회 직전 팀 순위.

2014-2022년 결승(Jolpica 계열): OpenF1 자료가 없어 Jolpica 랩별 순위, 랩 시간, 피트스톱,
결승 상태로 원값을 만든다(build_inputs_jolpica).
- 랩 끝 순서는 Jolpica 랩 순위를 그대로 쓴다.
- 세이프티 카 구간은 레이스 페이스 지수의 Jolpica 계열처럼 느려진 랩으로 추정해 세이프티 카로
  센다. 가상 세이프티 카와 가르지 못한다.
- 노면은 랩 시간의 폭(lap_time_spread)이 RAIN_SPREAD_MIN 이상이면 혼용으로 추정한다. 웨트
  타이어와 슬릭을 함께 쓴 결승은 같은 결승 안에서 랩 시간이 크게 갈린다. 처음부터 끝까지 웨트로
  달린 결승은 가르지 못한다.
두 계열의 차이는 2023-2025년 결승을 두 방식으로 함께 계산해 잰다(compare_methods).

제안 원문의 추월 횟수(The Field의 on-track passes)는 이 저장소의 데이터원이 아니다. 순위 변동은
결승선에서 본 순서가 랩 사이에 뒤바뀐 횟수라서, 한 랩 안에서 주고받은 추월은 세지 못한다.

실행: uv run python -m pipeline.transforms.race_score
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from pipeline.config import CURATED_DIR
from pipeline.transforms.pace_index import WET_COMPOUNDS, clean_laps_for_race

J = CURATED_DIR / "jolpica"
OF = CURATED_DIR / "openf1"
LINEAGE = CURATED_DIR / "lineage"
SCORE = CURATED_DIR / "score"
FORMULAS = SCORE / "formulas.json"

SLICK_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")
# 랩 끝 시각을 아는 차-랩의 비율이 이보다 낮은 결승은 순위 변동과 선두 교체를 내지 않는다.
# 2025년 6라운드 마이애미는 OpenF1 랩 자료에 2-24랩이 없어 이 기준에 걸린다.
ORDER_COVERAGE_MIN = 0.98
# 타이어 계열(웨트 계열, 슬릭)은 출전 차의 이 비율 이상이 쓴 경우에만 그 결승에서 쓰인 것으로 본다.
# 한두 대가 시험 삼아 끼운 타이어로 노면 분류가 바뀌지 않게 한다.
TYRE_FAMILY_MIN_SHARE = 0.5

# 순위대: 포디움권(1-3위), 포인트권(4-10위), 그 밖. 순위 변동과 DNF를 순위대별로 나눠 센다.
PODIUM_PLACES = 3
POINTS_PLACES = 10
TIERS = ("podium", "points", "rest")
# 한 랩에 한 차가 내준 자리는 이 수까지만 순위 변동으로 센다. 스핀이나 고장으로 한꺼번에 밀린 차를
# 추월 여러 번으로 세지 않기 위해서다. 2023-2025년에 한 차가 한 랩에 순서를 내준 2,300건 가운데
# 98%가 3자리 이하이고, 4자리 이상인 44건이 상한 없이 센 쌍의 9%를 차지한다.
MAX_PLACES_LOST_PER_LAP = 3
# 막판은 결승 랩 수의 마지막 10%다(58랩이면 53-58랩).
LATE_SHARE = 0.1
# 그리드 대비 순위 상승 구간(자리). 제안 글의 댓글에서 제안자가 든 구간이다.
GAIN_TIERS = (5, 10, 15)
# 한 대회에서 한 드라이버가 얻을 수 있는 최대 점수: 결승 우승 25점, 스프린트 우승 8점, 2019-2024년은
# 패스티스트 랩 1점. Jolpica 순위표에서 한 드라이버가 한 대회에 얻은 최대 점수(2023년 26점과 34점,
# 2024년 26점과 33점, 2025년 25점과 33점)와 맞는다. 규정 조항은 미검증이다.
RACE_WIN_POINTS = 25
SPRINT_WIN_POINTS = 8
FASTEST_LAP_POINT_SEASONS = range(2019, 2025)
# 2021년 스프린트(당시 이름은 스프린트 예선)는 우승 3점이었다.
# 2014년 최종전(아부다비)은 점수가 두 배였다.
# 둘 다 Jolpica 순위표의 대회별 최대 획득 점수와 맞춰 본 값이다(test_round_points_max_bounds_...).
SPRINT_WIN_POINTS_BY_SEASON = {2021: 3}
DOUBLE_POINTS_ROUNDS = {(2014, 19)}
# 이변: 대회 직전 컨스트럭터 순위가 TOP_TEAMS 밖인 팀의 포디움과, 맨 아래 BOTTOM_TEAMS개 팀이 얻은
# 포인트(10위 이내 완주)를 센다. "4강이 아닌 팀의 포디움"과 최하위권 두 팀의 포인트를 꼽은 의견에서
# 온 값이다.
TOP_TEAMS = 4
BOTTOM_TEAMS = 2
# Jolpica 계열로 계산하는 시즌. 2013년 이전은 정제 랩 자료가 없어(레이스 페이스 지수와 같이
# 2014년부터) 넣지 않는다. 2023년부터는 OpenF1 계열이다.
JOLPICA_SEASONS = (2014, 2022)
# 랩 시간의 폭(lap_time_spread)이 이 값 이상이면 노면을 혼용으로 추정한다. 2023-2025년 70개
# 결승에서 타이어로 판정한 혼용·웨트 8개는 모두 1.053 이상이고, 맑은 결승 62개는 하나(2024년
# 8라운드 모나코 1.057)를 빼고 1.046 이하다. 결승 시간대 ERA5 강수량은 맑은 결승 가운데 3mm가 넘는
# 곳(2025년 일본, 마이애미)이 있어 쓰지 않는다.
RAIN_SPREAD_MIN = 1.05
# 랩 시간의 폭을 잴 때 이보다 느린 랩(세이프티 카 추정 구간과 같은 기준)은 뺀다
SPREAD_NEUTRAL_RATIO = 1.15
# Jolpica 결승 상태 코드: 0 완주, 1 랩 뒤진 완주, 20 실격, 30 미출발·기권. 그 밖은 리타이어다.
FLAG_STATUS = (0, 1)
NOT_RETIRED_STATUS = (0, 1, 20, 30)

INPUT_COLUMNS = [
    "season", "round", "race_session_key", "race_laps", "order_coverage", "order_status",
    "position_changes", "lead_changes", "lead_changes_on_track", "win_gap_s",
    "finished_behind_safety_car", "sc_periods", "vsc_periods", "red_flags", "dnf", "wet_cars",
    "slick_cars", "track_condition",
    "pc_podium", "pc_points", "pc_rest", "pc_late_podium", "pc_late_points", "pc_late_rest",
    "dnf_podium", "dnf_points", "dnf_rest", "gap_p3_p4_s", "gap_p10_p11_s",
    "gain_5", "gain_10", "gain_15", "pit_stops_mean",
    "title_gap_points", "round_points_max", "remaining_points_max",
    "underdog_podiums", "bottom_team_points", "method", "lap_time_spread",
]  # fmt: skip
ITEM_IDS = [
    "position_changes", "lead_changes", "win_gap", "safety_car", "dnf", "rain",
    "grid_gains", "pit_stops", "title", "upset",
]  # fmt: skip
SCORE_COLUMNS = ["season", "round", "formula", "status", *[f"pt_{i}" for i in ITEM_IDS], "score"]


# --- 랩 끝 순서 ---------------------------------------------------------------------------


def crossing_times(lap_number, start_s, duration, shared) -> np.ndarray:
    """차 한 대의 랩 끝(결승선 통과) 시각을 초로 돌려준다. 입력은 랩 번호순 배열이다.

    OpenF1 랩의 출발 시각은 가끔 몇 초씩 틀린다(2025년 4라운드 바레인에서 트랜스폰더가 고장 난
    63번은 38랩부터 1-2초씩 어긋난다). 그래서 출발 시각을 그대로 쓰지 않고, 랩 타임을 이어 붙인
    누적 시간을 기록된 출발 시각들의 중앙값에 맞춘다.
    - 2랩부터 랩 타임이 끊기지 않는 구간을 한 묶음으로 본다. 1랩은 출발 신호부터 재는 값이고 적기로
      출발을 다시 한 결승에서는 출발 시각과 맞지 않으므로 묶음에 넣지 않는다.
    - 묶음 안에서 "기록된 출발 시각 - 그 랩 앞까지의 누적 랩 타임"의 중앙값을 묶음의 시작 시각으로
      삼고, 랩 끝 시각은 시작 시각에 누적 랩 타임을 더한 값이다.
    - 랩 타임이 없는 랩의 끝은 다음 랩의 시작 시각이다. 다음 랩도 없으면 끝 시각을 내지 않는다.
    shared는 여러 차가 똑같이 가진 출발 시각이다. 통과 시각이 아니라 세션이 시작하거나 끝날 때
    한꺼번에 찍힌 값이므로 쓰지 않는다(1랩의 출발 신호, 2023년 14라운드 이탈리아의 52번째 행).
    """
    n = len(lap_number)
    ends = np.full(n, np.nan)
    begins = np.full(n, np.nan)  # 묶음에 든 랩의 시작 시각
    observed = np.where(shared, np.nan, start_s)
    chained = (lap_number >= 2) & ~np.isnan(duration)
    follows = np.zeros(n, dtype=bool)  # 바로 앞 행이 한 랩 앞인지
    follows[1:] = lap_number[1:] == lap_number[:-1] + 1

    i = 0
    while i < n:
        if not chained[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and chained[j + 1] and follows[j + 1]:
            j += 1
        total = np.cumsum(duration[i : j + 1])
        before = total - duration[i : j + 1]
        anchors = list(observed[i : j + 1] - before)
        if j + 1 < n and follows[j + 1]:
            anchors.append(observed[j + 1] - total[-1])
        anchors = [a for a in anchors if not np.isnan(a)]
        if anchors:
            anchor = float(np.median(anchors))
            ends[i : j + 1] = anchor + total
            begins[i : j + 1] = anchor + before
        i = j + 1

    for i in range(n):  # 묶음 밖의 랩: 다음 랩의 시작 시각
        if np.isnan(ends[i]) and i + 1 < n and follows[i + 1]:
            ends[i] = begins[i + 1] if not np.isnan(begins[i + 1]) else observed[i + 1]
    return ends


def lap_table(laps, stints, pit, race_control, race_laps: int) -> pd.DataFrame:
    """결승 랩마다 끝 시각(crossing_times)과 피트 랩, 중립화 여부를 붙인다.

    피트 인 랩의 정의는 레이스 페이스 지수(pace_index.clean_laps_for_race)와 같다. 중립화 여부는
    그 랩이 세이프티 카, 가상 세이프티 카, 적기 구간(neutral_periods)과 겹치는지다. red_lap은 그
    가운데 적기 구간과 겹치는 랩이다.
    """
    df = clean_laps_for_race(laps, stints, pit, race_control, race_laps)
    origin = df["start"].min()
    df["start_s"] = (df["start"] - origin).dt.total_seconds()
    shared = df["start_s"].map(df["start_s"].value_counts()) > 1
    df["end_s"] = np.nan
    for _, rows in df.groupby("driver_number"):
        df.loc[rows.index, "end_s"] = crossing_times(
            rows["lap_number"].to_numpy(),
            rows["start_s"].to_numpy(dtype=float),
            rows["lap_duration"].to_numpy(dtype=float),
            shared.loc[rows.index].to_numpy(),
        )
    # 랩의 시작은 같은 차의 앞 랩 끝이다. 앞 랩이 없으면 기록된 출발 시각을 쓴다.
    previous_end = df.groupby("driver_number")["end_s"].shift(1)
    previous_lap = df.groupby("driver_number")["lap_number"].shift(1)
    df["begin_s"] = previous_end.where(previous_lap == df["lap_number"] - 1).fillna(df["start_s"])
    df["pit_lap"] = df["is_in_lap"] | df["is_pit_out_lap"].fillna(False).astype(bool)

    neutral = np.zeros(len(df), dtype=bool)
    red = np.zeros(len(df), dtype=bool)
    for p in neutral_periods(race_control):
        start_s = (p["start"] - origin).total_seconds()
        end_s = (p["end"] - origin).total_seconds()
        overlap = ((df["begin_s"] <= end_s) & (df["end_s"] >= start_s)).to_numpy()
        neutral |= overlap
        if p["kind"] == "red":
            red |= overlap
    df["neutral_lap"] = neutral
    df["red_lap"] = red
    df = df[df["lap_number"] <= race_laps]
    columns = [
        "driver_number",
        "lap_number",
        "begin_s",
        "end_s",
        "pit_lap",
        "neutral_lap",
        "red_lap",
    ]
    return df[columns]


def order_coverage(table: pd.DataFrame, session_result: pd.DataFrame) -> float:
    """세션 결과의 완주 랩 수만큼 랩 끝 시각을 아는 비율. 실격 등으로 랩 수가 없는 차는 뺀다."""
    done = session_result.dropna(subset=["number_of_laps"]).set_index("driver_number")
    expected = int(done["number_of_laps"].sum())
    if expected == 0:
        return 0.0
    known = table[table["end_s"].notna()]
    limit = known["driver_number"].map(done["number_of_laps"])
    return float((known["lap_number"] <= limit).sum() / expected)


def tier(place: float) -> str:
    """순위가 속한 순위대(podium, points, rest)."""
    if place <= PODIUM_PLACES:
        return "podium"
    return "points" if place <= POINTS_PLACES else "rest"


def lap_places(table: pd.DataFrame) -> pd.DataFrame:
    """랩(행)마다 차(열)의 순위. 그 랩을 끝낸 차들 가운데 끝 시각이 이른 순이다."""
    ends = table.pivot(index="lap_number", columns="driver_number", values="end_s")
    return ends.rank(axis=1, method="first")


def swaps(table: pd.DataFrame) -> pd.DataFrame:
    """랩 끝 순서가 앞 랩과 뒤바뀐 쌍을 2랩부터 찾아, 쌍마다 랩 번호와 내준 자리를 돌려준다.

    두 차 모두 앞 랩과 그 랩의 끝 시각이 있어야 한다. 그 랩이 피트 인 랩이나 아웃 랩인 차,
    세이프티 카, 가상 세이프티 카, 적기 구간에 걸친 차가 낀 쌍은 세지 않는다. 피트 스톱과 중립화
    구간에서 생긴 순서 변화를 빼기 위해서다. 출발(그리드에서 1랩 끝까지)의 변화도 세지 않는다.
    내준 자리(place)는 순서를 내준 차의 앞 랩 순위다. 2위였던 차가 추월당했으면 2다.
    한 랩에 한 차가 내준 자리는 MAX_PLACES_LOST_PER_LAP까지만 센다.
    """
    ends = table.pivot(index="lap_number", columns="driver_number", values="end_s")
    places = ends.rank(axis=1, method="first")
    skip = table.assign(skip=table["pit_lap"] | table["neutral_lap"]).pivot(
        index="lap_number", columns="driver_number", values="skip"
    )
    rows = []
    for lap in ends.index:
        if lap < 2 or lap - 1 not in ends.index:
            continue
        before, after = ends.loc[lap - 1], ends.loc[lap]
        ok = before.notna() & after.notna() & ~skip.loc[lap].fillna(True).astype(bool)
        x, y = before[ok].to_numpy(dtype=float), after[ok].to_numpy(dtype=float)
        # 행의 차가 앞 랩에는 열의 차보다 앞이었고 이 랩에는 뒤다
        lost = (x[:, None] < x[None, :]) & (y[:, None] > y[None, :])
        place = places.loc[lap - 1][ok].to_numpy()
        for i, count in enumerate(lost.sum(axis=1)):
            rows.extend([(int(lap), int(place[i]))] * min(int(count), MAX_PLACES_LOST_PER_LAP))
    return pd.DataFrame(rows, columns=["lap_number", "place"])


def position_changes(table: pd.DataFrame) -> int:
    """순위 변동 횟수(swaps의 쌍 수)."""
    return len(swaps(table))


def position_change_tiers(table: pd.DataFrame, race_laps: int) -> dict:
    """순위 변동을 내준 자리의 순위대별로 나눠 센다. pc_late_*는 그 가운데 막판 랩에서 나온 수다."""
    found = swaps(table)
    place_tier = found["place"].map(tier)
    late = found["lap_number"] > race_laps * (1 - LATE_SHARE)
    out = {}
    for name in TIERS:
        out[f"pc_{name}"] = int((place_tier == name).sum())
        out[f"pc_late_{name}"] = int(((place_tier == name) & late).sum())
    return out


def dnf_tiers(table: pd.DataFrame, session_result: pd.DataFrame, results: pd.DataFrame) -> dict:
    """리타이어한 차를 멈추기 전 순위의 순위대별로 센다.

    멈추기 전 순위는 그 차가 마지막으로 끝낸 랩의 순위다. 한 랩도 끝내지 못했으면 그리드 순위이고,
    피트 레인 출발(그리드 0)은 맨 뒤로 본다.
    """
    places = lap_places(table)
    grid = results.set_index("car_number")["grid"]
    out = {f"dnf_{name}": 0 for name in TIERS}
    for driver in session_result[session_result["dnf"].fillna(False)]["driver_number"]:
        done = places[driver].dropna() if driver in places.columns else pd.Series(dtype=float)
        on_grid = grid.get(driver, 0) or len(results)  # 피트 레인 출발은 맨 뒤
        place = done.iloc[-1] if len(done) else on_grid
        out[f"dnf_{tier(place)}"] += 1
    return out


def lap_leaders(table: pd.DataFrame) -> pd.Series:
    """랩마다 결승선을 가장 먼저 지난 차의 번호. 색인은 랩 번호다."""
    known = table.dropna(subset=["end_s"])
    first = known.loc[known.groupby("lap_number")["end_s"].idxmin()]
    return first.set_index("lap_number")["driver_number"].sort_index()


def lead_changes(table: pd.DataFrame) -> int:
    """랩 끝 선두가 앞 랩과 달라진 횟수. 피트 스톱으로 바뀐 것도 센다. 출발은 세지 않는다."""
    leaders = lap_leaders(table)
    return int((leaders != leaders.shift(1)).iloc[1:].sum())


def lead_changes_on_track(table: pd.DataFrame) -> int:
    """선두 교체 가운데 순위 변동으로도 세는 것만 센 횟수.

    앞 랩 선두와 새 선두가 둘 다 그 랩에 피트 인 랩이나 아웃 랩이 아니고 중립화 구간에 걸치지 않은
    경우다. 선두가 피트에 들어가 넘겨준 선두와 피트 순서 차이로 바뀐 선두가 빠진다. 지금 공식은
    쓰지 않고 원값만 남긴다.
    """
    leaders = lap_leaders(table)
    skipped = table[table["pit_lap"] | table["neutral_lap"] | table["end_s"].isna()]
    skipped = set(zip(skipped["lap_number"], skipped["driver_number"], strict=True))
    known = set(zip(table["lap_number"], table["driver_number"], strict=True))
    count = 0
    for lap, new in leaders.items():
        old = leaders.get(lap - 1)
        if old is None or old == new:
            continue
        both_ran = (lap, old) in known and (lap, new) in known
        if both_ran and (lap, old) not in skipped and (lap, new) not in skipped:
            count += 1
    return count


# --- 레이스 컨트롤 ------------------------------------------------------------------------


def neutral_periods(race_control: pd.DataFrame) -> list[dict]:
    """결승 중의 세이프티 카(sc), 가상 세이프티 카(vsc), 적기(red) 구간을 종류와 함께 돌려준다.

    읽는 메시지는 pace_index.neutralised_intervals와 같다. 다른 점은 세 가지다.
    - 가상 세이프티 카가 끝 메시지 없이 세이프티 카로 바뀌면 그 시각에 가상 세이프티 카 구간을 닫고
      upgraded로 표시한다. 같은 사고의 한 구간이므로 횟수는 세이프티 카로만 센다.
    - 첫 SESSION STARTED 앞이나 종료 뒤에 시작한 구간은 결승 중이 아니므로 뺀다(예: 2025년
      13라운드 벨기에의 출발 전 적기, 2023년 3라운드 호주의 체커 뒤 적기).
    - 적기 뒤 재출발 메시지의 랩 번호를 restart_lap으로 남긴다.
    """
    rc = race_control.copy()
    rc["date"] = pd.to_datetime(rc["date"], utc=True, format="ISO8601")
    rc = rc.sort_values("date", kind="stable")
    msg = rc["message"].fillna("").str.upper()
    started = rc.loc[msg == "SESSION STARTED", "date"]
    finished = rc.loc[(msg == "SESSION FINISHED") | (rc["flag"] == "CHEQUERED"), "date"]
    if started.empty:
        return []
    race_start = started.min()
    race_end = finished.min() if len(finished) else rc["date"].max()

    periods: list[dict] = []
    open_period: dict[str, dict | None] = {"sc": None, "vsc": None, "red": None}

    def begin(kind: str, when, lap) -> None:
        if open_period[kind] is None:
            open_period[kind] = {
                "kind": kind, "start": when, "lap": lap, "upgraded": False, "open_end": False,
                "restart_lap": None,
            }  # fmt: skip

    def close(kind: str, when, **extra) -> None:
        period = open_period[kind]
        if period is not None:
            periods.append(period | {"end": when} | extra)
            open_period[kind] = None

    for row, text in zip(rc.itertuples(), msg, strict=True):
        when = row.date
        if row.category == "SafetyCar":
            if "VIRTUAL SAFETY CAR DEPLOYED" in text:
                begin("vsc", when, row.lap_number)
            elif "VIRTUAL SAFETY CAR ENDING" in text:
                close("vsc", when)
            elif text.startswith("SAFETY CAR DEPLOYED"):
                close("vsc", when, upgraded=True)
                begin("sc", when, row.lap_number)
            elif "SAFETY CAR IN THIS LAP" in text:
                close("sc", when)
        elif row.category == "Flag" and row.flag == "RED":
            begin("red", when, row.lap_number)
        elif text == "SESSION STARTED" and open_period["red"] is not None:  # 적기 뒤 재출발
            close("red", when, restart_lap=row.lap_number)
            close("sc", when)
            close("vsc", when)
    for kind in open_period:  # 끝 메시지 없이 세션이 끝난 구간
        close(kind, max(race_end, rc["date"].max()), open_end=True)
    return [p for p in periods if race_start <= p["start"] <= race_end]


def control_summary(race_control: pd.DataFrame, race_laps: int) -> dict:
    """세이프티 카, 가상 세이프티 카, 적기 횟수와 세이프티 카 뒤에서 끝났는지를 돌려준다.

    세이프티 카 뒤에서 끝난 결승은 두 경우다. 세이프티 카 구간이 끝 메시지 없이 체커까지 이어진
    경우(2025년 10라운드 캐나다)와, 적기 뒤 재출발이 마지막 랩에 이뤄져 그 랩을 세이프티 카 뒤에서
    달리고 끝난 경우(2023년 3라운드 호주)다. 이런 결승의 1위와 2위 격차는 경쟁의 결과가 아니다.
    """
    periods = neutral_periods(race_control)
    sc = [p for p in periods if p["kind"] == "sc"]
    vsc = [p for p in periods if p["kind"] == "vsc" and not p["upgraded"]]
    red = [p for p in periods if p["kind"] == "red"]
    restarts = [p["restart_lap"] for p in red if pd.notna(p["restart_lap"])]
    behind = any(p["open_end"] for p in sc) or any(lap >= race_laps for lap in restarts)
    return {
        "sc_periods": len(sc),
        "vsc_periods": len(vsc),
        "red_flags": len(red),
        "finished_behind_safety_car": bool(behind),
    }


# --- 그 밖의 항목 -------------------------------------------------------------------------


def track_condition(stints: pd.DataFrame) -> dict:
    """스틴트의 타이어 종류로 노면을 dry, mixed, wet으로 나눈다.

    타이어 계열은 출전 차의 절반 이상이 쓴 경우에만 쓰인 것으로 본다(TYRE_FAMILY_MIN_SHARE).
    웨트 계열(인터미디어트, 웨트)이 쓰이지 않았으면 dry, 웨트 계열과 슬릭이 모두 쓰였으면 mixed,
    웨트 계열만 쓰였으면 wet이다. 랩 수 비율은 쓰지 않는다. OpenF1 스틴트의 타이어 종류가 틀린
    것으로 보이는 결승이 있어서다(2025년 13라운드 벨기에는 1랩만 인터미디어트이고 2랩부터 첫 피트
    스톱까지가 슬릭으로 적혀 있다).
    """
    cars = stints["driver_number"].nunique()
    if cars == 0:
        return {"wet_cars": pd.NA, "slick_cars": pd.NA, "track_condition": None}
    wet = stints[stints["compound"].isin(WET_COMPOUNDS)]["driver_number"].nunique()
    slick = stints[stints["compound"].isin(SLICK_COMPOUNDS)]["driver_number"].nunique()
    wet_used = wet >= TYRE_FAMILY_MIN_SHARE * cars
    slick_used = slick >= TYRE_FAMILY_MIN_SHARE * cars
    condition = "dry" if not wet_used else ("mixed" if slick_used else "wet")
    return {"wet_cars": wet, "slick_cars": slick, "track_condition": condition}


def gap_seconds(results: pd.DataFrame, ahead: int) -> float | None:
    """결승 ahead위와 그 다음 순위의 기록 차(초).

    두 차의 완주 랩 수가 다르면 None이다. Jolpica의 기록은 그 차가 달린 랩까지의 시간이라, 랩 수가
    다른 차끼리는 뺄 수 없다. 어느 한쪽 기록이 없어도 None이다.
    """
    rows = results.dropna(subset=["position"]).set_index("position")
    if ahead not in rows.index or ahead + 1 not in rows.index:
        return None
    first, second = rows.loc[ahead], rows.loc[ahead + 1]
    if pd.isna(first["time_ms"]) or pd.isna(second["time_ms"]):
        return None
    if first["laps_completed"] != second["laps_completed"]:
        return None
    return round(float(second["time_ms"] - first["time_ms"]) / 1000, 3)


def win_gap_seconds(results: pd.DataFrame) -> float | None:
    """결승 1위와 2위의 기록 차(초)."""
    return gap_seconds(results, 1)


def grid_gains(results: pd.DataFrame) -> dict:
    """그리드보다 5, 10, 15자리 이상 올라 완주한 차의 수. 구간은 겹치지 않는다(12자리는 gain_10).

    완주로 분류된 차만 센다. 실격은 뺀다. 피트 레인 출발(그리드 0)은 맨 뒤 그리드로 본다.
    """
    done = results[results["is_classified"] & (results["status_detail"] != "Disqualified")]
    grid = done["grid"].where(done["grid"] > 0, len(results))
    gain = grid - done["position"]
    low, mid, high = GAIN_TIERS
    return {
        f"gain_{low}": int(((gain >= low) & (gain < mid)).sum()),
        f"gain_{mid}": int(((gain >= mid) & (gain < high)).sum()),
        f"gain_{high}": int((gain >= high).sum()),
    }


def tyre_changes(stints: pd.DataFrame, table: pd.DataFrame) -> pd.Series:
    """차마다 결승 중 타이어를 바꾼 횟수. 색인은 차 번호다.

    OpenF1 스틴트는 타이어를 바꾸지 않아도 끊긴다. 세이프티 카를 따라 피트 레인을 지나기만 해도 새
    스틴트가 생긴다(2025년 10라운드 캐나다의 67-69랩). 그래서 앞 스틴트와 타이어 종류가 같고 시작
    마모 랩 수가 앞 스틴트를 이어 달린 만큼(두 랩까지 모자라도 된다) 늘어 있으면 같은 타이어로 본다.
    적기 구간에 걸친 랩에서 시작한 스틴트도 세지 않는다. 적기 중의 교체는 피트 스톱이 아니다.
    """
    red = table[table["red_lap"]]
    red = set(zip(red["driver_number"], red["lap_number"], strict=True))
    counts = {}
    for driver, rows in stints.sort_values("stint_number").groupby("driver_number"):
        count, previous = 0, None
        for stint in rows.itertuples():
            if previous is not None:
                ran = previous.lap_end - previous.lap_start + 1
                same_set = (
                    stint.compound == previous.compound
                    and stint.tyre_age_at_start >= previous.tyre_age_at_start + ran - 2
                )
                if not same_set and (driver, stint.lap_start) not in red:
                    count += 1
            previous = stint
        counts[driver] = count
    return pd.Series(counts, dtype=float)


def pit_stops_mean(stints, session_result, table) -> float | None:
    """완주한 차의 평균 타이어 교체 횟수(tyre_changes)."""
    out = session_result[["dnf", "dns", "dsq"]].fillna(False).any(axis=1)
    finishers = session_result[~out & session_result["position"].notna()]["driver_number"]
    counts = tyre_changes(stints, table)
    counts = counts[counts.index.isin(finishers)]
    if counts.empty:
        return None
    return round(float(counts.mean()), 3)


def round_points_max(season: int, has_sprint: bool, rnd: int | None = None) -> int:
    """그 대회에서 한 드라이버가 얻을 수 있는 최대 점수."""
    fastest_lap = 1 if season in FASTEST_LAP_POINT_SEASONS else 0
    race = RACE_WIN_POINTS * (2 if (season, rnd) in DOUBLE_POINTS_ROUNDS else 1)
    sprint = SPRINT_WIN_POINTS_BY_SEASON.get(season, SPRINT_WIN_POINTS) if has_sprint else 0
    return race + fastest_lap + sprint


def title_context(season: int, rnd: int, races: pd.DataFrame, standings: pd.DataFrame) -> dict:
    """그 대회를 앞둔 드라이버 타이틀 상황.

    title_gap_points는 앞 대회까지의 드라이버 순위표 1위와 2위의 점수 차다(개막전은 0).
    round_points_max는 이 대회의 최대 점수, remaining_points_max는 이 대회부터 최종전까지의 최대
    점수 합이다.
    """
    season_races = races[races["season"] == season]
    remaining = season_races[season_races["round"] >= rnd]
    this_round = remaining[remaining["round"] == rnd]["has_sprint"].iloc[0]
    before = standings[(standings["season"] == season) & (standings["round"] == rnd - 1)]
    top = before["points"].sort_values(ascending=False)
    return {
        "title_gap_points": float(top.iloc[0] - top.iloc[1]) if len(top) >= 2 else 0.0,
        "round_points_max": round_points_max(season, bool(this_round), rnd),
        "remaining_points_max": int(
            sum(
                round_points_max(season, bool(s), int(r))
                for s, r in zip(remaining["has_sprint"], remaining["round"], strict=True)
            )
        ),
    }


def team_ranks_before(
    season: int, rnd: int, teams, standings: pd.DataFrame, lineage: pd.DataFrame
) -> dict[str, int]:
    """그 대회 직전의 컨스트럭터 순위를 팀별로 돌려준다.

    2라운드부터는 앞 대회까지의 컨스트럭터 순위표다. 개막전은 순위표가 없으므로 앞 시즌 최종 순위를
    쓰고, 이름이 바뀐 팀은 계보(lineage/constructor_seasons)로 잇는다. 앞 시즌에 없던 팀은 맨 아래
    순위로 본다.
    """
    last = len(teams)
    if rnd > 1:
        before = standings[(standings["season"] == season) & (standings["round"] == rnd - 1)]
        position = before.set_index("constructor_id")["position"].dropna()
        # 순위가 비어 있는 행(2014-2020년 개막전 뒤 0점 팀 일부)은 맨 아래로 본다
        return {team: int(position.get(team, last)) for team in teams}
    previous = standings[standings["season"] == season - 1]
    previous = previous[previous["round"] == previous["round"].max()]
    by_season = lineage.set_index(["season", "constructor_id"])["lineage_id"]
    final = {
        by_season.get((season - 1, team)): int(position)
        for team, position in zip(previous["constructor_id"], previous["position"], strict=True)
    }
    return {team: final.get(by_season.get((season, team)), last) for team in teams}


def upsets(results: pd.DataFrame, ranks: dict[str, int]) -> dict:
    """이변 두 가지를 센다. 완주로 분류된 차만 세고 실격은 뺀다.

    underdog_podiums는 대회 직전 순위가 TOP_TEAMS 밖인 팀의 차가 3위 안에 든 수,
    bottom_team_points는 맨 아래 BOTTOM_TEAMS개 팀의 차가 10위 안에 든 수다. 최하위권 팀의 포디움은
    양쪽에 모두 들어간다.
    """
    done = results[results["is_classified"] & (results["status_detail"] != "Disqualified")]
    rank = done["constructor_id"].map(ranks)
    return {
        "underdog_podiums": int(((done["position"] <= PODIUM_PLACES) & (rank > TOP_TEAMS)).sum()),
        "bottom_team_points": int(
            ((done["position"] <= POINTS_PLACES) & (rank > len(ranks) - BOTTOM_TEAMS)).sum()
        ),
    }


def build_inputs_openf1() -> pd.DataFrame:
    """2023년부터의 결승: OpenF1 랩, 스틴트, 레이스 컨트롤로 만든 원값."""
    meeting_map = pd.read_csv(OF / "meeting_map.csv").dropna(subset=["race_session_key"])
    names = ["laps", "stints", "pit", "race_control", "session_result"]
    tables = {n: pd.read_parquet(OF / f"{n}.parquet") for n in names}
    results = pd.read_parquet(J / "results.parquet")
    results = results[results["session_type"] == "R"]
    races = pd.read_parquet(J / "races.parquet")
    standings = pd.read_parquet(J / "driver_standings.parquet")
    team_standings = pd.read_parquet(J / "constructor_standings.parquet")
    lineage = pd.read_parquet(LINEAGE / "constructor_seasons.parquet")

    rows = []
    for m in meeting_map.itertuples():
        key = int(m.race_session_key)
        part = {n: t[t["session_key"] == key] for n, t in tables.items()}
        if part["session_result"].empty:
            continue
        winner = part["session_result"][part["session_result"]["position"] == 1]
        race_laps = int(winner["number_of_laps"].iloc[0])
        row = {
            "season": m.season, "round": m.round, "race_session_key": key, "race_laps": race_laps,
        }  # fmt: skip

        table = lap_table(
            part["laps"], part["stints"], part["pit"], part["race_control"], race_laps
        )
        race_results = results[(results["season"] == m.season) & (results["round"] == m.round)]
        coverage = order_coverage(table, part["session_result"])
        row["order_coverage"] = round(coverage, 4)
        if coverage >= ORDER_COVERAGE_MIN:
            row |= {
                "order_status": "ok",
                "position_changes": position_changes(table),
                "lead_changes": lead_changes(table),
                "lead_changes_on_track": lead_changes_on_track(table),
            }
            row |= position_change_tiers(table, race_laps)
            row |= dnf_tiers(table, part["session_result"], race_results)
        else:
            row |= {"order_status": "laps_missing"}

        row["win_gap_s"] = win_gap_seconds(race_results)
        row["gap_p3_p4_s"] = gap_seconds(race_results, PODIUM_PLACES)
        row["gap_p10_p11_s"] = gap_seconds(race_results, POINTS_PLACES)
        row |= control_summary(part["race_control"], race_laps)
        row["dnf"] = int(part["session_result"]["dnf"].fillna(False).sum())
        row |= track_condition(part["stints"])
        row |= grid_gains(race_results)
        row["pit_stops_mean"] = pit_stops_mean(part["stints"], part["session_result"], table)
        row |= title_context(m.season, m.round, races, standings)
        teams = race_results["constructor_id"].unique()
        ranks = team_ranks_before(m.season, m.round, teams, team_standings, lineage)
        row |= upsets(race_results, ranks)
        row["method"] = "openf1"
        rows.append(row)
    return _finish_inputs(rows)


def _finish_inputs(rows: list[dict]) -> pd.DataFrame:
    out = pd.DataFrame(rows).reindex(columns=INPUT_COLUMNS).sort_values(["season", "round"])
    counts = ["position_changes", "lead_changes", "lead_changes_on_track", "wet_cars", "slick_cars"]
    counts += [f"pc_{t}" for t in TIERS] + [f"pc_late_{t}" for t in TIERS]
    counts += [f"dnf_{t}" for t in TIERS]
    for col in counts:
        out[col] = out[col].astype("Int64")  # 내지 못한 결승은 NULL
    return out.reset_index(drop=True)


# --- Jolpica 계열(2014-2022) -----------------------------------------------------------------


def jolpica_lap_table(laps: pd.DataFrame, pits: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    """Jolpica 랩으로 lap_table과 같은 꼴의 표를 만든다. 중립화로 추정한 랩 번호도 돌려준다.

    Jolpica 랩의 position은 그 랩 끝의 순위라 그대로 랩 끝 순서(end_s 자리)로 쓴다. 같은 랩 안의
    순서만 비교하므로 시각이 아니어도 된다. 피트 인 랩은 피트스톱이 기록된 랩, 아웃 랩은 그다음
    랩이다. 중립화 구간은 레이스 페이스 지수의 Jolpica 계열(race_index_jolpica.neutralised_laps)로
    추정하고, 그 다음 랩까지 중립화 랩으로 본다.
    """
    from pipeline.transforms.race_index_jolpica import neutralised_laps

    df = laps.copy()
    stops = {(int(c), int(n)) for c, n in zip(pits["car_number"], pits["lap"], strict=True)}
    df["is_in_lap"] = [
        (int(c), int(n)) in stops for c, n in zip(df["car_number"], df["lap"], strict=True)
    ]
    df["is_out_lap"] = [
        (int(c), int(n) - 1) in stops for c, n in zip(df["car_number"], df["lap"], strict=True)
    ]
    df["lap_s"] = df["time_ms"] / 1000
    neutral = sorted(neutralised_laps(df))
    extended = set(neutral) | {n + 1 for n in neutral}
    table = pd.DataFrame(
        {
            "driver_number": df["car_number"].astype(int),
            "lap_number": df["lap"].astype(int),
            "end_s": df["position"].astype(float),
            "pit_lap": df["is_in_lap"] | df["is_out_lap"],
            "neutral_lap": df["lap"].isin(extended),
            "red_lap": False,
        }
    )
    return table, neutral


def neutral_runs(laps: list[int]) -> int:
    """이어진 랩 번호 묶음의 수. 추정한 중립화 구간의 횟수다."""
    runs, previous = 0, None
    for lap in sorted(laps):
        if previous is None or lap != previous + 1:
            runs += 1
        previous = lap
    return runs


def jolpica_session_result(results: pd.DataFrame) -> pd.DataFrame:
    """dnf_tiers에 넘길 세션 결과 꼴. 리타이어는 완주, 실격, 미출발·기권이 아닌 차다."""
    return pd.DataFrame(
        {
            "driver_number": results["car_number"].astype(int),
            "dnf": ~results["status_code"].isin(NOT_RETIRED_STATUS),
        }
    )


def jolpica_order_coverage(table: pd.DataFrame, results: pd.DataFrame) -> float:
    """결과의 완주 랩 수만큼 랩 순위를 아는 비율."""
    done = results.set_index(results["car_number"].astype(int))["laps_completed"].dropna()
    expected = int(done.sum())
    if expected == 0:
        return 0.0
    limit = table["driver_number"].map(done)
    return float((table["lap_number"] <= limit).sum() / expected)


def jolpica_pit_stops_mean(results: pd.DataFrame, pits: pd.DataFrame) -> float | None:
    """체커를 받은 차의 평균 피트스톱 횟수(Jolpica 피트스톱 기록)."""
    finishers = results[results["status_code"].isin(FLAG_STATUS)]["car_number"].astype(int)
    if finishers.empty:
        return None
    counts = pits.groupby(pits["car_number"].astype(int)).size()
    return round(float(counts.reindex(finishers, fill_value=0).mean()), 3)


def lap_time_spread(laps: pd.DataFrame, pits: pd.DataFrame) -> float | None:
    """결승 안에서 랩 시간이 얼마나 갈렸는지.

    랩마다 필드 중앙 랩 시간(1랩, 피트 인·아웃 랩 제외)을 구하고, 그 가운데 빠른 쪽 10번째
    백분위수에 대한 비율을 낸다. 비율이 SPREAD_NEUTRAL_RATIO를 넘는 랩(세이프티 카로 추정하는 랩)을
    빼고, 남은 랩 비율의 90번째 백분위수를 돌려준다. 웨트 타이어 구간과 슬릭 구간이 함께 있으면 이
    값이 커진다.
    """
    stops = {(int(c), int(n)) for c, n in zip(pits["car_number"], pits["lap"], strict=True)}
    keys = list(zip(laps["car_number"].astype(int), laps["lap"].astype(int), strict=True))
    keep = [(c, n) not in stops and (c, n - 1) not in stops for c, n in keys]
    green = laps[keep & (laps["lap"] > 1).to_numpy() & laps["time_ms"].notna().to_numpy()]
    per_lap = green.groupby("lap")["time_ms"].median()
    if len(per_lap) < 5:
        return None
    ratio = per_lap / per_lap.quantile(0.1)
    ratio = ratio[ratio <= SPREAD_NEUTRAL_RATIO]
    return round(float(ratio.quantile(0.9)), 4)


def spread_condition(spread: float | None) -> str | None:
    """랩 시간의 폭으로 추정한 노면. 값이 없으면 None(노면 항목을 내지 않는다)."""
    if spread is None:
        return None
    return "mixed" if spread >= RAIN_SPREAD_MIN else "dry"


def jolpica_race_row(
    season: int,
    rnd: int,
    laps: pd.DataFrame,
    pits: pd.DataFrame,
    race_results: pd.DataFrame,
    races: pd.DataFrame,
    standings: pd.DataFrame,
    team_standings: pd.DataFrame,
    lineage: pd.DataFrame,
) -> dict:
    """Jolpica 계열로 결승 하나의 원값을 만든다.

    우승 격차, 순위 상승, 타이틀, 이변은 OpenF1 계열과 같은 함수로 계산한다.
    """
    winner = race_results[race_results["position"] == 1]
    race_laps = int(winner["laps_completed"].iloc[0])
    table, neutral = jolpica_lap_table(laps, pits)
    table = table[table["lap_number"] <= race_laps]
    row: dict = {"season": season, "round": rnd, "race_laps": race_laps, "method": "jolpica"}
    coverage = jolpica_order_coverage(table, race_results)
    row["order_coverage"] = round(coverage, 4)
    session_result = jolpica_session_result(race_results)
    if coverage >= ORDER_COVERAGE_MIN:
        row |= {
            "order_status": "ok",
            "position_changes": position_changes(table),
            "lead_changes": lead_changes(table),
            "lead_changes_on_track": lead_changes_on_track(table),
        }
        row |= position_change_tiers(table, race_laps)
        row |= dnf_tiers(table, session_result, race_results)
    else:
        row |= {"order_status": "laps_missing"}
    row["win_gap_s"] = win_gap_seconds(race_results)
    row["gap_p3_p4_s"] = gap_seconds(race_results, PODIUM_PLACES)
    row["gap_p10_p11_s"] = gap_seconds(race_results, POINTS_PLACES)
    # 마지막 랩이 중립화 랩으로 추정되면 세이프티 카 뒤에서 끝난 결승으로 본다.
    # 결승 기록이 한 랩뿐인 결승(2021년 12라운드 벨기에: 세이프티 카 뒤 세 바퀴 뒤 중단, 한 랩으로
    # 판정)은 랩 시간으로 추정할 기준이 없어 따로 세이프티 카 뒤에서 끝난 것으로 본다.
    row["finished_behind_safety_car"] = race_laps in neutral or race_laps < 2
    row |= {"sc_periods": neutral_runs(neutral), "vsc_periods": 0, "red_flags": pd.NA}
    row["dnf"] = int(session_result["dnf"].sum())
    spread = lap_time_spread(laps[laps["lap"] <= race_laps], pits)
    row |= {"lap_time_spread": spread, "track_condition": spread_condition(spread)}
    row |= grid_gains(race_results)
    row["pit_stops_mean"] = jolpica_pit_stops_mean(race_results, pits)
    row |= title_context(season, rnd, races, standings)
    teams = race_results["constructor_id"].unique()
    ranks = team_ranks_before(season, rnd, teams, team_standings, lineage)
    row |= upsets(race_results, ranks)
    return row


def build_inputs_jolpica(seasons: tuple[int, int] = JOLPICA_SEASONS) -> pd.DataFrame:
    """Jolpica 계열 원값. 랩 자료가 있는 결승만 계산한다."""
    first, last = seasons
    laps = pd.read_parquet(J / "race_laps.parquet")
    laps = laps[laps["season"].between(first, last)]
    pits = pd.read_parquet(J / "pitstops.parquet")
    results = pd.read_parquet(J / "results.parquet")
    results = results[(results["session_type"] == "R") & results["season"].between(first, last)]
    races = pd.read_parquet(J / "races.parquet")
    standings = pd.read_parquet(J / "driver_standings.parquet")
    team_standings = pd.read_parquet(J / "constructor_standings.parquet")
    lineage = pd.read_parquet(LINEAGE / "constructor_seasons.parquet")
    rows = []
    for (season, rnd), race_laps in laps.groupby(["season", "round"]):
        season, rnd = int(season), int(rnd)
        race_results = results[(results["season"] == season) & (results["round"] == rnd)]
        race_pits = pits[(pits["season"] == season) & (pits["round"] == rnd)]
        rows.append(
            jolpica_race_row(
                season,
                rnd,
                race_laps,
                race_pits,
                race_results,
                races,
                standings,
                team_standings,
                lineage,
            )  # fmt: skip
        )
    return _finish_inputs(rows)


def build_inputs() -> pd.DataFrame:
    """Jolpica 계열(2014-2022)과 OpenF1 계열(2023-)의 원값을 합친다."""
    both = pd.concat([build_inputs_jolpica(), build_inputs_openf1()], ignore_index=True)
    return both.sort_values(["season", "round"]).reset_index(drop=True)


def compare_methods(formula_name: str = "v0.4") -> dict:
    """2023-2025년 결승을 Jolpica 계열로도 계산해 OpenF1 계열 점수와 비교한다.

    백분위 기준 분포는 OpenF1 계열 그대로 두고(공개한 점수의 기준), 두 계열 모두 점수가 있는
    결승만 비교한다. 돌려주는 값: 비교한 결승 수, 점수 상관, 순위 상관, 점수 차의 중앙값과 90번째
    백분위수, 최댓값, 상위 10개 겹침, 원값별 상관과 일치율.
    """
    openf1 = pd.read_parquet(SCORE / "race_inputs.parquet")
    openf1 = openf1[openf1["method"] == "openf1"]
    jolpica = build_inputs_jolpica((2023, 2025))
    formula = load_formulas()[formula_name]
    reference = reference_values(openf1, formula)

    def scored(inputs: pd.DataFrame) -> pd.DataFrame:
        rows = [
            {"season": r.season, "round": r.round} | score_race(r, formula, reference)
            for r in inputs.itertuples()
        ]
        return pd.DataFrame(rows)

    m = scored(openf1).merge(scored(jolpica), on=["season", "round"], suffixes=("", "_j"))
    m = m.dropna(subset=["score", "score_j"])
    diff = (m["score_j"] - m["score"]).abs()
    top = set(m.nlargest(10, "score").index) & set(m.nlargest(10, "score_j").index)
    raw = openf1.merge(jolpica, on=["season", "round"], suffixes=("", "_j"))
    raw = raw[(raw["order_status"] == "ok") & (raw["order_status_j"] == "ok")]
    sc = raw["sc_periods"] + raw["vsc_periods"]
    # 혼용과 웨트를 가르지 못하므로 맑음과 그 밖으로만 비교한다
    rain = raw["track_condition"].ne("dry") == raw["track_condition_j"].ne("dry")
    return {
        "races": len(m),
        "score_corr": round(float(m["score"].corr(m["score_j"])), 3),
        "rank_corr": round(float(m["score"].rank().corr(m["score_j"].rank())), 3),
        "abs_diff_median": round(float(diff.median()), 2),
        "abs_diff_p90": round(float(diff.quantile(0.9)), 2),
        "abs_diff_max": round(float(diff.max()), 2),
        "top10_overlap": len(top),
        "position_changes_corr": round(
            float(
                raw["position_changes"].astype(float).corr(raw["position_changes_j"].astype(float))
            ),
            3,
        ),
        "lead_changes_equal": round(
            float((raw["lead_changes"] == raw["lead_changes_j"]).mean()), 3
        ),
        "neutral_runs_equal": round(float((sc == raw["sc_periods_j"]).mean()), 3),
        "rain_class_equal": round(float(rain.mean()), 3),
        "dnf_equal": round(float((raw["dnf"] == raw["dnf_j"]).mean()), 3),
        "pit_stops_corr": round(float(raw["pit_stops_mean"].corr(raw["pit_stops_mean_j"])), 3),
    }


# --- 공식 ---------------------------------------------------------------------------------


def load_formulas() -> dict:
    return json.loads(FORMULAS.read_text(encoding="utf-8"))


def gap_points(gap_s: float, table: list[list[float]], over: float) -> float:
    """우승 격차 환산표. 구간의 경곗값은 아래 구간에 넣는다(1.000초는 0-1초 구간)."""
    for upper, points in table:
        if gap_s <= upper:
            return float(points)
    return float(over)


def safety_car_points(sc: int, vsc: int, table: dict, cap: float | None) -> float:
    """세이프티 카와 가상 세이프티 카 환산 점수의 합. 표의 마지막 칸은 그 횟수 이상이다."""
    points = table["sc"][min(sc, len(table["sc"]) - 1)]
    points += table["vsc"][min(vsc, len(table["vsc"]) - 1)]
    return float(points if cap is None else min(points, cap))


def percentile_points(value: float, reference: np.ndarray) -> float:
    """기준 대회 가운데 이 값보다 작은 대회의 비율을 0-100점으로 돌려준다.

    기준 대회가 n개면 (작은 대회 수) / (n - 1) * 100이고 100을 넘지 않는다. 기준 대회 가운데 가장
    작은 값은 0점, 하나뿐인 가장 큰 값은 100점이다. 같은 값은 같은 점수를 받는다.
    """
    if len(reference) < 2:
        return 0.0
    return float(min(1.0, (reference < value).sum() / (len(reference) - 1)) * 100)


def upset_points(podiums: int, points_finishes: int, item: dict) -> float:
    """이변 점수(0-100점): 4강 밖 팀의 포디움과 최하위권 팀의 포인트에 건당 점수를 주고 더한다."""
    points = item["podium_points"] * podiums + item["bottom_points"] * points_finishes
    return float(min(points, item["cap"]))


def title_points(gap: float, round_max: float, remaining_max: float) -> float:
    """타이틀 긴장도(0-100점): 이 대회의 배점 비중 x 점수 차의 여유.

    배점 비중은 이 대회의 최대 점수를 이 대회부터 최종전까지의 최대 점수 합으로 나눈 값이다(최종전은
    1). 점수 차의 여유는 1 - (1위와 2위의 점수 차 / 남은 최대 점수 합)이고, 타이틀이 이미 정해져
    음수가 되면 0이다. 동점으로 맞는 최종전이 100점이다.
    """
    if remaining_max <= 0:
        return 0.0
    return float(100 * (round_max / remaining_max) * max(0.0, 1 - gap / remaining_max))


GAP_COLUMNS = {1: "win_gap_s", PODIUM_PLACES: "gap_p3_p4_s", POINTS_PLACES: "gap_p10_p11_s"}


def _weighted(row, prefix: str, weights: dict) -> float | None:
    """순위대별 횟수에 가중치를 곱해 더한다. 횟수가 없으면 None이다."""
    counts = [getattr(row, f"{prefix}_{name}") for name in TIERS]
    if any(pd.isna(c) for c in counts):
        return None
    return float(sum(weights[name] * c for name, c in zip(TIERS, counts, strict=True)))


def item_value(row, item: dict) -> float | None:
    """횟수나 백분위로 환산하는 항목의 환산 전 값. 내지 못하면 None이다."""
    item_id = item["id"]
    if item_id == "position_changes" and "place_weights" in item:
        # 순위대 가중치를 곱하고, 막판 랩의 순위 변동은 late_multiplier배로 센다
        base = _weighted(row, "pc", item["place_weights"])
        late = _weighted(row, "pc_late", item["place_weights"])
        if base is None or late is None:
            return None
        return base + (item["late_multiplier"] - 1) * late
    if item_id == "dnf" and "place_weights" in item:
        return _weighted(row, "dnf", item["place_weights"])
    if item_id == "grid_gains":
        counts = [getattr(row, f"gain_{t}") for t in GAIN_TIERS]
        return float(sum(p * c for p, c in zip(item["tier_points"], counts, strict=True)))
    column = {"pit_stops": "pit_stops_mean"}.get(item_id, item_id)
    value = getattr(row, column)
    return None if pd.isna(value) else float(value)


def score_race(row, formula: dict, reference: dict[str, np.ndarray]) -> dict:
    """대회 하나의 항목별 반영 점수(항목 점수 x 가중치)와 합계."""
    out: dict = {}
    missing: list[str] = []
    for item in formula["items"]:
        item_id, convert = item["id"], item["convert"]
        points: float | None = None
        if convert in ("count", "percentile"):
            value = item_value(row, item)
            if value is None:
                missing.append(item_id)
            elif convert == "count":
                points = value
            else:
                points = percentile_points(value, reference[item_id])
        elif convert == "gap_table":
            if pd.isna(row.win_gap_s):
                missing.append(item_id)
            elif formula["gap_zero_when_finished_behind_safety_car"] and bool(
                row.finished_behind_safety_car
            ):
                points = 0.0
            else:
                # 경계마다 환산한 점수의 평균. 한 바퀴 넘게 벌어진 경계(격차 없음)는 0점이다.
                gaps = [getattr(row, GAP_COLUMNS[b]) for b in item.get("boundaries", [1])]
                points = sum(
                    0.0 if pd.isna(g) else gap_points(g, formula["gap_table"], formula["gap_over"])
                    for g in gaps
                ) / len(gaps)
        elif convert == "safety_car_table":
            points = safety_car_points(
                int(row.sc_periods), int(row.vsc_periods), formula["safety_car_table"],
                formula["safety_car_cap"],
            )  # fmt: skip
        elif convert == "rain_table":
            if row.track_condition is None or pd.isna(row.track_condition):
                missing.append(item_id)
            else:
                points = float(formula["rain_table"][row.track_condition])
        elif convert == "title_tension":
            points = title_points(
                row.title_gap_points, row.round_points_max, row.remaining_points_max
            )
        elif convert == "upset_table":
            points = upset_points(int(row.underdog_podiums), int(row.bottom_team_points), item)
        else:
            raise ValueError(f"모르는 환산 방식: {convert}")
        out[f"pt_{item_id}"] = None if points is None else round(points * item["weight"], 2)
    if missing:
        # 항목 하나라도 내지 못하면 합계를 내지 않는다. 남은 항목만 더하면 다른 대회와 견줄 수 없다.
        out |= {"status": "missing:" + ",".join(missing), "score": None}
    else:
        out |= {"status": "ok", "score": round(sum(out.values()), 2)}
    return out


def reference_values(inputs: pd.DataFrame, formula: dict) -> dict[str, np.ndarray]:
    """백분위 환산의 기준 분포. 기준 시즌 가운데 순위 자료가 온전한 대회만 쓴다."""
    if "reference_seasons" not in formula:
        return {}
    first, last = formula["reference_seasons"]
    ref = inputs[inputs["season"].between(first, last) & (inputs["order_status"] == "ok")]
    out = {}
    for item in formula["items"]:
        if item["convert"] == "percentile":
            values = [item_value(row, item) for row in ref.itertuples()]
            out[item["id"]] = np.array([v for v in values if v is not None], dtype=float)
    return out


def build_scores(inputs: pd.DataFrame, formulas: dict | None = None) -> pd.DataFrame:
    formulas = formulas or load_formulas()
    rows = []
    for name, formula in formulas.items():
        reference = reference_values(inputs, formula)
        for row in inputs.itertuples():
            rows.append(
                {"season": row.season, "round": row.round, "formula": name}
                | score_race(row, formula, reference)
            )
    out = pd.DataFrame(rows).reindex(columns=SCORE_COLUMNS)
    return out.sort_values(["formula", "season", "round"]).reset_index(drop=True)


def build() -> dict[str, int]:
    SCORE.mkdir(parents=True, exist_ok=True)
    inputs = build_inputs()
    inputs.to_parquet(SCORE / "race_inputs.parquet", index=False, compression="zstd")
    scores = build_scores(inputs)
    scores.to_parquet(SCORE / "race_score.parquet", index=False, compression="zstd")
    # 두 계열 대조 결과(사이트 방법론 쪽에 싣는다)
    comparison = compare_methods()
    (SCORE / "method_comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"race_inputs": len(inputs), "race_score": len(scores), "compared": comparison["races"]}


if __name__ == "__main__":
    print(build())
