"""레이스 페이스 지수의 Jolpica 계열(2014-2022). (T10) 정의는 docs/methodology.md 를 따른다.

OpenF1 자료는 2023년부터라 그 이전 결승은 Jolpica 덤프의 랩 시간과 피트스톱으로 계산한다.
Jolpica에는 랩 시작 시각, 타이어, 레이스 컨트롤 메시지가 없어
OpenF1 계열(pace_index.build_race)과 클린 랩 규칙이
다르다.

- 피트 인 랩은 피트스톱이 기록된 랩, 아웃 랩은 그다음 랩이다.
- 세이프티 카, 가상 세이프티 카, 적기 구간은 랩마다 필드 중앙 랩 시간이 그 결승의 중앙값보다
  NEUTRAL_RATIO배 넘게 느린 랩으로 추정하고, 그다음 랩도 뺀다.
- 우천은 Open-Meteo ERA5 시간별 강수량으로 판정한다(wet_flag_from_precip).
- 출발 연료량은 그 시즌 스포팅 규정의 경주 연료 상한(regulations/fuel_rules.csv)이다. 상한 조항이
  없는 시즌(2022년)은 OpenF1 계열과 같은 110kg을 쓴다.

두 계열의 규칙 차이가 지수에 주는 영향은 2023-2025년 결승을 두 방식으로 함께 계산해 잰다
(compare_with_openf1). 그 대조로 NEUTRAL_RATIO와 강수 기준을 정했다.

실행: uv run python -m pipeline.transforms.pace_index (레이스 지수 전체를 다시 만든다)
"""

from __future__ import annotations

import json

from pipeline.config import CURATED_DIR, RAW_DIR

J = CURATED_DIR / "jolpica"
FIRST_SEASON = 2014  # 2013년 이전 규정에는 경주 연료 상한이 없다(2026-11-25 사용자 결정)
LAST_SEASON = 2022  # 2023년부터는 OpenF1 계열
VALIDATION_SEASONS = range(2023, 2026)

NEUTRAL_RATIO = 1.15
# 결승 시간대의 ERA5 강수량(mm, 시간별 값의 합). WET 이상이면 wet, DRY 미만이면 dry, 그 사이는
# unclassified로 두어 지수를 내지 않는다.
PRECIP_WET_MM = 1.0
PRECIP_DRY_MM = 0.2


def start_fuel_by_season() -> dict[int, float]:
    """시즌별 경주 연료 상한(kg). 스포팅 규정 조항에서 읽은 값만 있다."""
    import pandas as pd

    path = CURATED_DIR / "regulations" / "fuel_rules.csv"
    fuel = pd.read_csv(path)
    fuel = fuel[fuel["rule"] == "race_fuel_mass"]
    return {int(r.season): float(str(r.value).split()[0]) for r in fuel.itertuples()}


def neutralised_laps(df, ratio: float = NEUTRAL_RATIO) -> set[int]:
    """필드 중앙 랩 시간이 결승 중앙값의 ratio배를 넘는 랩 번호.

    1랩, 피트 인·아웃 랩은 셈에서 뺀다."""
    base = df[(df["lap"] > 1) & ~df["is_in_lap"] & ~df["is_out_lap"] & df["lap_s"].notna()]
    per_lap = base.groupby("lap")["lap_s"].median()
    if per_lap.empty:
        return set()
    reference = per_lap.median()
    return {int(lap) for lap, value in per_lap.items() if value > ratio * reference}


def clean_laps_for_race(
    laps, pits, total_laps: int, start_fuel: float, ratio: float = NEUTRAL_RATIO
):
    """한 결승의 Jolpica 랩에 클린 랩 조건과 연료 보정을 적용한다. 제외 사유를 열로 남긴다."""
    import pandas as pd

    from pipeline.transforms.pace_index import FUEL_EFFECT_S_PER_KG, OUTLIER_RATIO

    df = laps.sort_values(["car_number", "lap"]).copy()
    df["lap_s"] = df["time_ms"] / 1000
    stops = {(int(p.car_number), int(p.lap)) for p in pits.itertuples()}
    keys = list(zip(df["car_number"].astype(int), df["lap"].astype(int), strict=True))
    df["is_in_lap"] = [k in stops for k in keys]
    df["is_out_lap"] = [(c, n - 1) in stops for c, n in keys]
    neutral = neutralised_laps(df, ratio)
    neutral |= {n + 1 for n in neutral}
    df["neutralised"] = df["lap"].isin(neutral)

    fuel_left = start_fuel * (1 - (df["lap"] - 1) / total_laps)
    df["corrected"] = df["lap_s"] - FUEL_EFFECT_S_PER_KG * fuel_left

    reason = pd.Series("", index=df.index)
    for label, mask in [
        ("no_time", df["lap_s"].isna()),
        ("lap_1", df["lap"] == 1),
        ("pit_out", df["is_out_lap"]),
        ("pit_in", df["is_in_lap"]),
        ("neutralised", df["neutralised"]),
    ]:
        reason = reason.mask((reason == "") & mask, label)
    candidate = reason == ""
    median = df[candidate].groupby("car_number")["corrected"].transform("median")
    slow = candidate & (df["corrected"] > OUTLIER_RATIO * median.reindex(df.index))
    df["exclude_reason"] = reason.mask(slow, "over_107pct")
    return df


def race_precip(season: int, round_: int, start, duration_ms: float | None) -> float | None:
    """결승 시간대(출발 시각부터 우승자 기록까지)의 ERA5 강수량 합(mm). 자료가 없으면 None.

    ERA5 시간별 값은 그 시각까지 한 시간 동안의 양이므로 출발 시각 다음 정시부터 끝난 시각 다음
    정시까지를 더한다.
    """
    import math

    import pandas as pd

    path = RAW_DIR / "openmeteo" / "archive" / str(season) / f"{round_:02d}.json"
    if not path.exists() or pd.isna(start) or duration_ms is None or math.isnan(duration_ms):
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    hourly = pd.DataFrame(data["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"], utc=True)
    start = pd.Timestamp(start).tz_convert("UTC")
    end = start + pd.Timedelta(milliseconds=duration_ms)
    window = hourly[(hourly["time"] > start) & (hourly["time"] <= end.ceil("h"))]
    if window.empty or window["precipitation"].isna().all():
        return None
    return round(float(window["precipitation"].sum()), 2)


def wet_flag_from_precip(precip: float | None) -> str:
    if precip is None:
        return "unclassified"
    if precip >= PRECIP_WET_MM:
        return "wet"
    return "dry" if precip < PRECIP_DRY_MM else "unclassified"


def race_inputs(seasons):
    import pandas as pd

    laps = pd.read_parquet(J / "race_laps.parquet")
    pits = pd.read_parquet(J / "pitstops.parquet")
    results = pd.read_parquet(J / "results.parquet")
    results = results[results["session_type"] == "R"]
    races = pd.read_parquet(J / "races.parquet")
    laps, pits = laps[laps["season"].isin(seasons)], pits[pits["season"].isin(seasons)]
    races = races[races["season"].isin(seasons)]
    return laps, pits, results, races


def build_rows(
    seasons=range(FIRST_SEASON, LAST_SEASON + 1), ratio: float = NEUTRAL_RATIO
) -> list[dict]:
    """시즌 범위의 결승마다 팀별 레이스 지수 행을 만든다(pace_index.RACE_COLUMNS와 method 열)."""
    import numpy as np
    import pandas as pd

    from pipeline.transforms.pace_index import BOOTSTRAP_DRAWS, MIN_CLEAN_LAPS, START_FUEL_KG

    laps, pits, results, races = race_inputs(seasons)
    fuel = start_fuel_by_season()
    rows = []
    for race in races.itertuples():
        key = (laps["season"] == race.season) & (laps["round"] == race.round)
        part = laps[key]
        if part.empty:
            continue
        stops = pits[(pits["season"] == race.season) & (pits["round"] == race.round)]
        res = results[(results["season"] == race.season) & (results["round"] == race.round)]
        winner = res[res["position"] == 1]
        total_laps = (
            int(winner["laps_completed"].iloc[0])
            if len(winner) and pd.notna(winner["laps_completed"].iloc[0])
            else int(part["lap"].max())
        )
        start_fuel = fuel.get(int(race.season), START_FUEL_KG)
        df = clean_laps_for_race(part, stops, total_laps, start_fuel, ratio)
        clean = df[df["exclude_reason"] == ""]
        win_ms = (
            float(winner["time_ms"].iloc[0])
            if len(winner) and pd.notna(winner["time_ms"].iloc[0])
            else None
        )
        precip = race_precip(int(race.season), int(race.round), race.race_start_utc, win_ms)
        flag = wet_flag_from_precip(precip)

        team_values = {}
        for team, g in clean.groupby("constructor_id"):
            if flag != "unclassified" and len(g) >= MIN_CLEAN_LAPS:
                team_values[team] = g["corrected"].to_numpy()
        field = (
            float(np.median([np.median(v) for v in team_values.values()]))
            if team_values
            else float("nan")
        )
        rng = np.random.default_rng(race.season * 100 + race.round)
        for team, total in df.groupby("constructor_id")["lap"].count().items():
            values = team_values.get(team)
            row = {
                "season": int(race.season), "round": int(race.round), "constructor_id": team,
                "total_laps": int(total),
                "clean_laps": int((clean["constructor_id"] == team).sum()),
                "wet_flag": flag, "is_wet": pd.NA if flag == "unclassified" else flag == "wet",
                "wet_tyres": pd.NA, "rain_sample_share": float("nan"), "race_laps": total_laps,
                "method": "jolpica", "precip_mm": precip, "start_fuel_kg": start_fuel,
                "neutralised_laps": int(df.loc[df["neutralised"], "lap"].nunique()),
            }  # fmt: skip
            if values is not None:
                team_median = float(np.median(values))
                draws = np.median(
                    rng.choice(values, size=(BOOTSTRAP_DRAWS, len(values)), replace=True), axis=1
                )
                low, high = np.percentile(draws, [2.5, 97.5])
                row |= {
                    "team_median_s": round(team_median, 4),
                    "field_median_s": round(field, 4),
                    "index_pct": round((team_median / field - 1) * 100, 4),
                    "ci_low_pct": round((low / field - 1) * 100, 4),
                    "ci_high_pct": round((high / field - 1) * 100, 4),
                }
            rows.append(row)
    return rows


def compare_with_openf1(ratio: float = NEUTRAL_RATIO) -> dict:
    """2023-2025년 결승을 Jolpica 방식으로 계산해 OpenF1 계열과 견준다.

    - 중립화 랩: OpenF1 계열에서 절반 넘는 차의 랩이 neutralised로 빠진 랩 번호와, Jolpica 방식의
      추정 랩 번호의 일치(정밀도, 재현율).
    - 지수: 두 계열 모두 지수가 있는 팀의 차이(중앙값, 90번째 백분위수)와 대회 안 순위 상관.
    - 우천: Open-Meteo 판정과 OpenF1 판정의 교차표.
    """
    import numpy as np
    import pandas as pd

    from pipeline.transforms import pace_index as p

    jolpica = pd.DataFrame(build_rows(VALIDATION_SEASONS, ratio))
    openf1 = pd.read_parquet(p.PACE / "race_index.parquet")
    openf1 = openf1[
        openf1["season"].isin(VALIDATION_SEASONS) & (openf1.get("method", "openf1") == "openf1")
    ]
    # 중립화 랩 대조
    of = CURATED_DIR / "openf1"
    meeting_map = pd.read_csv(of / "meeting_map.csv").dropna(subset=["race_session_key"])
    tables = {n: pd.read_parquet(of / f"{n}.parquet") for n in
              ["laps", "stints", "pit", "race_control", "session_result"]}  # fmt: skip
    laps, pits, results, races = race_inputs(VALIDATION_SEASONS)
    tp = fp = fn = 0
    for m in meeting_map.itertuples():
        k = int(m.race_session_key)
        part = {n: t[t["session_key"] == k] for n, t in tables.items()}
        if part["laps"].empty:
            continue
        o = p.clean_laps_for_race(
            part["laps"], part["stints"], part["pit"], part["race_control"], 1
        )
        share = o.groupby("lap_number")["neutralised"].mean()
        truth = {int(n) for n, v in share.items() if v > 0.5 and n > 1}
        jl = laps[(laps["season"] == m.season) & (laps["round"] == m.round)]
        if jl.empty:
            continue
        st = pits[(pits["season"] == m.season) & (pits["round"] == m.round)]
        d = clean_laps_for_race(jl, st, int(jl["lap"].max()), 110.0, ratio)
        est = {int(n) for n in d.loc[d["neutralised"], "lap"].unique() if n > 1}
        tp += len(truth & est)
        fp += len(est - truth)
        fn += len(truth - est)
    both = jolpica.merge(
        openf1, on=["season", "round", "constructor_id"], suffixes=("_j", "_o")
    ).dropna(subset=["index_pct_j", "index_pct_o"])
    diff = (both["index_pct_j"] - both["index_pct_o"]).abs()
    rho = []
    for _, g in both.groupby(["season", "round"]):
        if len(g) >= 5:
            rho.append(g["index_pct_j"].rank().corr(g["index_pct_o"].rank()))
    races_j = jolpica.drop_duplicates(["season", "round"])[
        ["season", "round", "wet_flag", "precip_mm"]
    ]
    races_o = openf1.drop_duplicates(["season", "round"])[["season", "round", "wet_flag"]]
    flags = races_j.merge(races_o, on=["season", "round"], suffixes=("_j", "_o"))
    return {
        "ratio": ratio,
        "neutral_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "neutral_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "neutral_laps_openf1": tp + fn,
        "teams_compared": len(both),
        "abs_diff_median_pct": round(float(diff.median()), 4),
        "abs_diff_p90_pct": round(float(diff.quantile(0.9)), 4),
        "rank_corr_median": round(float(np.median(rho)), 3) if rho else None,
        "races_compared": len(rho),
        "wet_crosstab": pd.crosstab(flags["wet_flag_j"], flags["wet_flag_o"]).to_dict(),
        "wet_disagreements": flags[
            (flags["wet_flag_j"] != flags["wet_flag_o"]) & (flags["wet_flag_j"] != "unclassified")
        ][["season", "round", "wet_flag_j", "wet_flag_o", "precip_mm"]].to_dict("records"),
    }
