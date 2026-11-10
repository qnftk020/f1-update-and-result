"""페이스 지수 계산. (T10) 정의는 docs/methodology.md 를 따른다.

실행: uv run python -m pipeline.transforms.pace_index
"""

from __future__ import annotations

import duckdb

from pipeline.config import CURATED_DIR, LAST_SEASON

J = CURATED_DIR / "jolpica"
F = CURATED_DIR / "f1db"
PACE = CURATED_DIR / "pace"
CROSSWALK = CURATED_DIR / "lineage" / "constructor_crosswalk.csv"

QUALIFYING_FIRST_SEASON = 1996
JOLPICA_FIRST_SEASON = 2006  # 이전 형식은 F1DB의 그리드 결정 기록을 쓴다
REFERENCE_FORMATS = ("ONE_LAP", "AGGREGATE")  # 결승 연료 원랩, 합산 기록: 참고용

QUALIFYING_SQL = f"""
with jq as (  -- Jolpica: 드라이버별 Q1-Q3 최솟값
    select season, round, constructor_id, driver_id, min(best_time_ms) as best_ms
    from '{J}/qualifying.parquet'
    where session_type in ('Q1', 'Q2', 'Q3') and season >= {JOLPICA_FIRST_SEASON}
    group by all
),
j_ok as (  -- 참가자의 80% 이상에 기록이 있는 대회만 Jolpica를 쓴다
    select season, round from jq group by 1, 2
    having count(best_ms) >= 0.8 * count(*)
),
fq as (  -- F1DB: 드라이버별 기록(그리드 결정 기록 또는 Q1-Q3 최솟값)
    select season, round, f1db_constructor_id, f1db_driver_id,
           least(time_ms, q1_ms, q2_ms, q3_ms) as best_ms
    from '{F}/qualifying.parquet' where season >= {QUALIFYING_FIRST_SEASON}
),
teams_in_round as (
    select distinct season, round, constructor_id from '{J}/results.parquet'
    where session_type = 'R'
),
xwalk as (
    select f1db_constructor_id, season_from::int as season_from, season_to::int as season_to,
           constructor_id
    from read_csv('{CROSSWALK}', header = true, all_varchar = true)
),
f_mapped as (  -- F1DB ID를 Jolpica ID로. 대응표에 후보가 여럿이면 그 대회 결과에 있는 것을 고른다
    select f.season, f.round, f.f1db_driver_id as driver_id, f.best_ms,
           coalesce(
               (select x.constructor_id from xwalk x
                 where x.f1db_constructor_id = f.f1db_constructor_id
                   and f.season between x.season_from and x.season_to
                 order by exists (select 1 from teams_in_round t
                                   where t.season = f.season and t.round = f.round
                                     and t.constructor_id = x.constructor_id) desc,
                          x.constructor_id
                 limit 1),
               replace(f.f1db_constructor_id, '-', '_')) as constructor_id
    from fq f
),
times as (
    select j.season, j.round, j.constructor_id, j.driver_id, j.best_ms, 'jolpica' as time_source
    from jq j semi join j_ok k on k.season = j.season and k.round = j.round
    union all
    select f.season, f.round, f.constructor_id, f.driver_id, f.best_ms, 'f1db'
    from f_mapped f anti join j_ok k on k.season = f.season and k.round = f.round
),
team as (
    select season, round, constructor_id, time_source, min(best_ms) as team_best_ms,
           count(best_ms) as drivers_with_time, count(*) as drivers_entered
    from times group by all
),
session as (
    select season, round, min(team_best_ms) as session_best_ms from team group by 1, 2
)
select t.season, t.round, t.constructor_id, t.team_best_ms, s.session_best_ms,
       round((t.team_best_ms / s.session_best_ms - 1) * 100, 4) as index_pct,
       t.drivers_with_time, t.drivers_entered, r.qualifying_format,
       r.qualifying_format in {REFERENCE_FORMATS} as is_reference_format, t.time_source
from team t
join session s using (season, round)
join '{F}/races.parquet' r using (season, round)
where t.season between {QUALIFYING_FIRST_SEASON} and {LAST_SEASON}
order by t.season, t.round, index_pct nulls last, t.constructor_id
"""


def build_qualifying() -> int:
    PACE.mkdir(parents=True, exist_ok=True)
    out = PACE / "qualifying_index.parquet"
    con = duckdb.connect()
    con.execute(f"copy ({QUALIFYING_SQL}) to '{out}' (format parquet, compression zstd)")
    return con.execute(f"select count(*) from '{out}'").fetchone()[0]


# --- 레이스 페이스 지수 -------------------------------------------------------------------

FUEL_EFFECT_S_PER_KG = 0.03
START_FUEL_KG = 110.0
OUTLIER_RATIO = 1.07
MIN_CLEAN_LAPS = 8
BOOTSTRAP_DRAWS = 1000
WET_COMPOUNDS = ("INTERMEDIATE", "WET")


def neutralised_intervals(race_control):
    """세이프티 카, 가상 세이프티 카, 적기 구간을 (시작, 끝) 시각 목록으로 돌려준다."""
    import pandas as pd

    rc = race_control.sort_values("date")
    intervals = []
    open_since = {"sc": None, "vsc": None, "red": None}
    for row in rc.itertuples():
        msg = (row.message or "").upper()
        when = row.date
        if row.category == "SafetyCar":
            if "VIRTUAL SAFETY CAR DEPLOYED" in msg:
                open_since["vsc"] = open_since["vsc"] or when
            elif "VIRTUAL SAFETY CAR ENDING" in msg and open_since["vsc"] is not None:
                intervals.append((open_since["vsc"], when))
                open_since["vsc"] = None
            elif msg.startswith("SAFETY CAR DEPLOYED"):
                open_since["sc"] = open_since["sc"] or when
            elif "SAFETY CAR IN THIS LAP" in msg and open_since["sc"] is not None:
                intervals.append((open_since["sc"], when))
                open_since["sc"] = None
        elif row.category == "Flag" and row.flag == "RED":
            open_since["red"] = open_since["red"] or when
        elif (
            row.category == "SessionStatus"
            and "SESSION STARTED" in msg
            and open_since["red"] is not None
        ):
            intervals.append((open_since["red"], when))
            open_since["red"] = None
            # 적기 뒤 재출발하면 진행 중이던 세이프티 카 구간도 끝난 것으로 본다
            for key in ("sc", "vsc"):
                if open_since[key] is not None:
                    intervals.append((open_since[key], when))
                    open_since[key] = None
    end = rc["date"].max() if len(rc) else pd.NaT
    for since in open_since.values():  # 끝 메시지 없이 세션이 끝난 구간
        if since is not None:
            intervals.append((since, end))
    return intervals


def clean_laps_for_race(laps, stints, pit, race_control, total_laps: int):
    """한 결승의 랩에 클린 랩 조건과 연료 보정을 적용한다. 제외 사유를 열로 남긴다."""
    import numpy as np
    import pandas as pd

    df = laps.sort_values(["driver_number", "lap_number"]).copy()
    df["start"] = pd.to_datetime(df["date_start"], utc=True, format="ISO8601")
    df["end"] = df["start"] + pd.to_timedelta(df["lap_duration"], unit="s")

    # 타이어 종류: 스틴트 구간으로 랩에 붙인다
    df["compound"] = None
    for s in stints.itertuples():
        if pd.isna(s.lap_start) or pd.isna(s.lap_end):
            continue
        mask = (df["driver_number"] == s.driver_number) & df["lap_number"].between(
            s.lap_start, s.lap_end
        )
        df.loc[mask, "compound"] = s.compound

    # 피트 인 랩: pit 기록의 랩과, 마지막이 아닌 스틴트의 끝 랩
    in_laps = {(p.driver_number, p.lap_number) for p in pit.itertuples()}
    last_stint = stints.groupby("driver_number")["stint_number"].transform("max")
    for s in stints[stints["stint_number"] < last_stint].itertuples():
        if not pd.isna(s.lap_end):
            in_laps.add((s.driver_number, int(s.lap_end)))
    df["is_in_lap"] = [
        (d, n) in in_laps for d, n in zip(df["driver_number"], df["lap_number"], strict=True)
    ]

    # 중립화 구간에 걸친 랩과 그 다음 랩
    rc = race_control.copy()
    rc["date"] = pd.to_datetime(rc["date"], utc=True, format="ISO8601")
    overlap = np.zeros(len(df), dtype=bool)
    for start, end in neutralised_intervals(rc):
        overlap |= ((df["start"] <= end) & (df["end"] >= start)).to_numpy()
    df["neutralised"] = overlap
    prev = df.groupby("driver_number")["neutralised"].shift(1, fill_value=False)
    df["neutralised"] = df["neutralised"] | prev.astype(bool)

    fuel_left = START_FUEL_KG * (1 - (df["lap_number"] - 1) / total_laps)
    df["corrected"] = df["lap_duration"] - FUEL_EFFECT_S_PER_KG * fuel_left

    reason = pd.Series("", index=df.index)
    for label, mask in [
        ("no_time", df["lap_duration"].isna()),
        ("no_timestamp", df["start"].isna()),
        ("lap_1", df["lap_number"] == 1),
        ("pit_out", df["is_pit_out_lap"].fillna(False).astype(bool)),
        ("pit_in", df["is_in_lap"]),
        ("neutralised", df["neutralised"]),
        ("wet_tyre", df["compound"].isin(WET_COMPOUNDS)),
    ]:
        reason = reason.mask((reason == "") & mask, label)
    candidate = reason == ""
    median = df[candidate].groupby("driver_number")["corrected"].transform("median")
    slow = candidate & (df["corrected"] > OUTLIER_RATIO * median.reindex(df.index))
    reason = reason.mask(slow, "over_107pct")
    df["exclude_reason"] = reason
    return df


def build_race() -> int:
    import numpy as np
    import pandas as pd

    of = CURATED_DIR / "openf1"
    meeting_map = pd.read_csv(of / "meeting_map.csv").dropna(subset=["race_session_key"])
    tables = {n: pd.read_parquet(of / f"{n}.parquet") for n in
              ["laps", "stints", "pit", "race_control", "session_result", "weather"]}  # fmt: skip
    results = pd.read_parquet(J / "results.parquet")
    results = results[results["session_type"] == "R"]

    rows = []
    for m in meeting_map.itertuples():
        key = int(m.race_session_key)
        part = {n: t[t["session_key"] == key] for n, t in tables.items()}
        if part["laps"].empty:
            continue
        winner = part["session_result"][part["session_result"]["position"] == 1]
        total_laps = (
            int(winner["number_of_laps"].iloc[0])
            if len(winner) and pd.notna(winner["number_of_laps"].iloc[0])
            else int(part["laps"]["lap_number"].max())
        )
        laps = clean_laps_for_race(
            part["laps"], part["stints"], part["pit"], part["race_control"], total_laps
        )
        teams = results[(results["season"] == m.season) & (results["round"] == m.round)][
            ["car_number", "constructor_id"]
        ]
        laps = laps.merge(teams, left_on="driver_number", right_on="car_number", how="left")
        clean = laps[laps["exclude_reason"] == ""]

        wet_stint = bool(part["stints"]["compound"].isin(WET_COMPOUNDS).any())
        weather = part["weather"].copy()
        weather["date"] = pd.to_datetime(weather["date"], utc=True, format="ISO8601")
        during = weather[weather["date"].between(laps["start"].min(), laps["end"].max())]
        rain_share = float((during["rainfall"] > 0).mean()) if len(during) else float("nan")

        team_values = {}
        for team, g in clean.groupby("constructor_id"):
            if len(g) >= MIN_CLEAN_LAPS:
                team_values[team] = g["corrected"].to_numpy()
        if not team_values:  # 클린 랩이 충분한 팀이 하나도 없는 대회
            field = float("nan")
        else:
            field = float(np.median([np.median(v) for v in team_values.values()]))
        rng = np.random.default_rng(m.season * 100 + m.round)
        all_teams = laps.groupby("constructor_id")["lap_number"].count()
        for team, total in all_teams.items():
            values = team_values.get(team)
            row = {
                "season": m.season, "round": m.round, "constructor_id": team,
                "total_laps": int(total),
                "clean_laps": int((clean["constructor_id"] == team).sum()),
                "is_wet": wet_stint or (rain_share > 0), "rain_sample_share": round(rain_share, 4),
                "race_laps": total_laps,
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
    out = pd.DataFrame(rows).sort_values(["season", "round", "index_pct", "constructor_id"])
    PACE.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PACE / "race_index.parquet", index=False, compression="zstd")
    return len(out)


if __name__ == "__main__":
    print(f"pace/qualifying_index: {build_qualifying()} rows")
    print(f"pace/race_index: {build_race()} rows")
