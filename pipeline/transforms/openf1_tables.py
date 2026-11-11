"""OpenF1 원문 캐시를 정제 테이블로 바꾸고 Jolpica와 연결한다. (T9)

- 물리적으로 불가능한 날씨 값은 결측으로 바꾼다(예: 노면 온도 0.0).
- 미팅은 시즌과 결승 날짜로 Jolpica 라운드에 맞추고, 서킷 대응의 일관성을 테스트로 본다.
- 드라이버는 대회별 차량 번호로 맞춘 뒤 시즌 단위 대응표로 요약한다. 대응표는 사람이 검수한다.

실행: uv run python -m pipeline.transforms.openf1_tables
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.config import CURATED_DIR, LAST_SEASON, OPENF1_FIRST_SEASON, RAW_DIR
from pipeline.sources.openf1 import ENDPOINTS, SESSION_NAMES

RAW = RAW_DIR / "openf1"
OUT = CURATED_DIR / "openf1"

KEEP = {
    "laps": [
        "session_key", "driver_number", "lap_number", "date_start", "lap_duration",
        "duration_sector_1", "duration_sector_2", "duration_sector_3", "is_pit_out_lap",
        "i1_speed", "i2_speed", "st_speed",
    ],
    "stints": [
        "session_key", "driver_number", "stint_number", "lap_start", "lap_end", "compound",
        "tyre_age_at_start",
    ],
    "pit": ["session_key", "driver_number", "lap_number", "date", "pit_duration"],
    "weather": [
        "session_key", "date", "air_temperature", "track_temperature", "humidity", "pressure",
        "rainfall", "wind_speed", "wind_direction",
    ],
    "race_control": [
        "session_key", "date", "lap_number", "category", "flag", "scope", "sector",
        "driver_number", "qualifying_phase", "message",
    ],
    "session_result": [
        "session_key", "driver_number", "position", "number_of_laps", "dnf", "dns", "dsq",
    ],
    "drivers": [
        "session_key", "driver_number", "name_acronym", "full_name", "team_name",
    ],
}  # fmt: skip
SORT = {
    "laps": ["session_key", "driver_number", "lap_number"],
    "stints": ["session_key", "driver_number", "stint_number"],
    "pit": ["session_key", "driver_number", "lap_number", "date"],
    "weather": ["session_key", "date"],
    "race_control": ["session_key", "date", "message"],
    "session_result": ["session_key", "position", "driver_number"],
    "drivers": ["session_key", "driver_number"],
}


def load_sessions(*, allow_partial: bool = False) -> pd.DataFrame:
    rows = []
    for year in range(OPENF1_FIRST_SEASON, LAST_SEASON + 1):
        path = RAW / str(year) / "sessions.json"
        if allow_partial and not path.exists():
            continue
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    df = pd.DataFrame(rows)
    df = df[df["session_name"].isin(SESSION_NAMES) & ~df["is_cancelled"].fillna(False)]
    if allow_partial:  # 수집이 끝나지 않았을 때 개발용으로만 쓴다
        done = [
            all((RAW / str(s.year) / str(s.session_key) / f"{e}.json").exists() for e in ENDPOINTS)
            for s in df.itertuples()
        ]
        df = df[done]
    cols = [
        "session_key", "meeting_key", "year", "session_name", "date_start", "date_end",
        "location", "country_name", "circuit_short_name", "circuit_key",
    ]  # fmt: skip
    return df[cols].sort_values(["date_start"]).reset_index(drop=True)


def load_endpoint(sessions: pd.DataFrame, endpoint: str) -> pd.DataFrame:
    frames = []
    for s in sessions.itertuples():
        path = RAW / str(s.year) / str(s.session_key) / f"{endpoint}.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        if rows:
            frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True)
    for col in KEEP[endpoint]:
        if col not in df.columns:
            df[col] = pd.NA
    return df[KEEP[endpoint]].sort_values(SORT[endpoint], kind="stable").reset_index(drop=True)


def clean_weather(df: pd.DataFrame) -> pd.DataFrame:
    """물리적으로 불가능한 값을 결측으로 바꾼다."""
    df = df.copy()
    df.loc[df["track_temperature"] <= 0, "track_temperature"] = pd.NA
    df.loc[df["humidity"] <= 0, "humidity"] = pd.NA
    df.loc[df["pressure"] <= 0, "pressure"] = pd.NA
    return df


def build_meeting_map(sessions: pd.DataFrame) -> pd.DataFrame:
    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    races = races[races["season"].between(OPENF1_FIRST_SEASON, LAST_SEASON)].copy()
    races["race_date_utc"] = pd.to_datetime(races["race_start_utc"], utc=True).dt.date
    of_race = sessions[sessions["session_name"] == "Race"].copy()
    of_race["race_date_utc"] = pd.to_datetime(of_race["date_start"], utc=True).dt.date
    of_quali = sessions[sessions["session_name"] == "Qualifying"][["meeting_key", "session_key"]]
    # 같은 UTC 날짜로 먼저 맞추고, 남은 대회는 하루 차이까지 허용한다.
    # (Jolpica의 날짜는 현지 날짜라 라스베이거스처럼 UTC 날짜와 하루 어긋나는 대회가 있다)
    exact = races.merge(
        of_race, how="left", left_on=["season", "race_date_utc"], right_on=["year", "race_date_utc"]
    )
    exact["match_rule"] = exact["meeting_key"].notna().map({True: "same_utc_date", False: ""})
    used = set(exact["meeting_key"].dropna())
    for idx in exact.index[exact["meeting_key"].isna()]:
        day = exact.at[idx, "race_date_utc"]
        near = of_race[
            (of_race["year"] == exact.at[idx, "season"])
            & ~of_race["meeting_key"].isin(used)
            & of_race["race_date_utc"].map(lambda d, day=day: abs((d - day).days) <= 1)
        ]
        if len(near) == 1:
            for col in of_race.columns:
                if col != "race_date_utc":
                    exact.at[idx, col] = near.iloc[0][col]
            exact.at[idx, "match_rule"] = "within_one_day"
            used.add(near.iloc[0]["meeting_key"])
    merged = exact.merge(of_quali, how="left", on="meeting_key", suffixes=("_race", "_qualifying"))
    out = merged[
        [
            "season", "round", "race_name", "date", "circuit_id", "meeting_key", "location",
            "circuit_short_name", "circuit_key", "session_key_qualifying", "session_key_race",
            "match_rule",
        ]
    ].rename(
        columns={
            "date": "jolpica_date",
            "location": "openf1_location",
            "circuit_short_name": "openf1_circuit",
            "circuit_key": "openf1_circuit_key",
            "session_key_qualifying": "qualifying_session_key",
            "session_key_race": "race_session_key",
        }
    )  # fmt: skip
    for col in ["meeting_key", "openf1_circuit_key", "qualifying_session_key", "race_session_key"]:
        out[col] = out[col].astype("Int64")
    return out.sort_values(["season", "round"]).reset_index(drop=True)


def build_driver_map(meeting_map: pd.DataFrame, drivers: pd.DataFrame) -> pd.DataFrame:
    """결승 세션의 차량 번호로 OpenF1 드라이버와 Jolpica 드라이버를 맞춘다."""
    results = pd.read_parquet(CURATED_DIR / "jolpica" / "results.parquet")
    results = results[results["session_type"] == "R"][
        ["season", "round", "driver_id", "constructor_id", "car_number"]
    ]
    names = pd.read_parquet(CURATED_DIR / "jolpica" / "drivers.parquet")[
        ["driver_id", "abbreviation", "forename", "surname"]
    ]
    covered = meeting_map.dropna(subset=["race_session_key"])[
        ["season", "round", "race_session_key"]
    ]
    results = results.merge(covered[["season", "round"]], on=["season", "round"])
    race_drivers = covered.merge(drivers, left_on="race_session_key", right_on="session_key")
    pairs = race_drivers.merge(
        results, how="outer", left_on=["season", "round", "driver_number"],
        right_on=["season", "round", "car_number"], indicator=True,
    ).merge(names, how="left", on="driver_id")  # fmt: skip
    pairs["driver_number"] = pairs["driver_number"].fillna(pairs["car_number"]).astype("Int64")
    grouped = (
        pairs.groupby(
            ["season", "driver_number", "driver_id", "name_acronym", "abbreviation", "full_name",
             "forename", "surname"],
            dropna=False,
        )
        .agg(first_round=("round", "min"), last_round=("round", "max"), rounds=("round", "count"),
             unmatched=("_merge", lambda s: int((s != "both").sum())))
        .reset_index()
    )  # fmt: skip
    grouped["jolpica_name"] = grouped["forename"].fillna("") + " " + grouped["surname"].fillna("")
    grouped["acronym_matches"] = grouped["name_acronym"] == grouped["abbreviation"]
    grouped["review"] = "auto"
    grouped.loc[(grouped["unmatched"] > 0) | ~grouped["acronym_matches"], "review"] = "check"
    cols = [
        "season", "driver_number", "driver_id", "name_acronym", "abbreviation", "full_name",
        "jolpica_name", "first_round", "last_round", "rounds", "unmatched", "review",
    ]  # fmt: skip
    return grouped[cols].sort_values(["season", "driver_number", "first_round"])


def write_parquet(df: pd.DataFrame, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.parquet"
    new = pa.Table.from_pandas(df, preserve_index=False)
    if path.exists():
        old = pq.read_table(path)
        # 내용이 같으면 쓰지 않는다. 증분 갱신에서 pandas 열 형식 메타데이터만 달라져도
        # 파일 바이트가 바뀌어, 자동 갱신이 내용 변화 없는 커밋을 만드는 일을 막는다.
        if old.schema.remove_metadata().equals(new.schema.remove_metadata()) and old.equals(
            new.replace_schema_metadata(old.schema.metadata)
        ):
            return path
    pq.write_table(new, path, compression="zstd")
    return path


def build(*, allow_partial: bool = False) -> dict[str, int]:
    sessions = load_sessions(allow_partial=allow_partial)
    counts = {"sessions": len(sessions)}
    write_parquet(sessions, "sessions")
    tables = {}
    for endpoint in ENDPOINTS:
        df = load_endpoint(sessions, endpoint)
        if endpoint == "weather":
            df = clean_weather(df)
        tables[endpoint] = df
        write_parquet(df, endpoint)
        counts[endpoint] = len(df)
    meeting_map = build_meeting_map(sessions)
    meeting_map.to_csv(OUT / "meeting_map.csv", index=False)
    counts["meeting_map"] = len(meeting_map)
    driver_map = build_driver_map(meeting_map, tables["drivers"])
    driver_map.to_csv(OUT / "driver_map.csv", index=False)
    counts["driver_map"] = len(driver_map)
    return counts


if __name__ == "__main__":
    import sys

    for name, n in build(allow_partial="--partial" in sys.argv).items():
        print(f"openf1/{name}: {n} rows")
