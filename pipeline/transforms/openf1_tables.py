"""OpenF1 원문 캐시를 정제 테이블로 바꾸고 Jolpica와 연결한다. (T9)

- 물리적으로 불가능한 날씨 값은 결측으로 바꾼다(예: 노면 온도 0.0).
- 미팅은 시즌과 결승 날짜로 Jolpica 라운드에 맞추고, 서킷 대응의 일관성을 테스트로 본다.
- 드라이버는 대회별 차량 번호로 맞춘 뒤 시즌 단위 대응표로 요약한다. 대응표는 사람이 검수한다.

대응표의 review 열: auto(자동 대응), check(자동 대응에서 한쪽에만 있거나 약어가 다른 행, 드라이버
대응표만), human(사람이 검수한 행). human 행은 review_id에 data/curated/review/human_review.csv의
검수 id를 적는다. 다시 만들 때(write_map) 앞 파일에서 human이던 행과 내용이 모두 같은 행만 human을
이어받는다. 내용이 바뀌거나 새로 생긴 행은 auto나 check로 돌아가 다시 검수를 기다린다.

실행: uv run python -m pipeline.transforms.openf1_tables
"""

from __future__ import annotations

import io
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


REVIEW_COLUMNS = ["review", "review_id"]
MAP_DOC_TYPES = {"meeting_map": "openf1_meeting_map", "driver_map": "openf1_driver_map"}
APPROVE = "approve"


def approved_reviews(name: str) -> dict[str, dict[str, str]]:
    """대응표 name("meeting_map", "driver_map")을 승인한 사람 검수 행(id -> 행)."""
    from pipeline import review

    return {
        r["id"]: r
        for r in review.decisions(MAP_DOC_TYPES[name])
        if r["decision"] == APPROVE and r["target"] == f"{name}.csv"
    }


def _as_text(df: pd.DataFrame) -> pd.DataFrame:
    """CSV로 쓴 모양 그대로의 글 값(정수 열의 결측, 소수점 표기까지 파일과 같게 비교한다)."""
    return pd.read_csv(io.StringIO(df.to_csv(index=False)), dtype=str, keep_default_na=False)


def keep_human_review(
    new: pd.DataFrame, previous: pd.DataFrame | None, approved: set[str]
) -> pd.DataFrame:
    """앞 파일에서 사람이 검수한(human) 행과 내용이 같은 새 행에 검수 표시를 이어 준다.

    내용은 review, review_id를 뺀 모든 열의 CSV 값으로 비교한다. 앞 행의 review_id가 지금
    human_review.csv에서 승인(approve)으로 남아 있어야 이어받는다. 나머지 행은 자동 표시(auto,
    check)를 그대로 두고 review_id를 비운다.
    """
    out = new.copy()
    if "review" not in out.columns:
        out["review"] = "auto"
    out["review_id"] = ""
    data = [c for c in out.columns if c not in REVIEW_COLUMNS]
    if previous is None or not set(data + REVIEW_COLUMNS) <= set(previous.columns):
        return out
    prev = _as_text(previous)
    prev = prev[(prev["review"] == "human") & prev["review_id"].isin(approved)]
    reviewed = {tuple(r): rid for r, rid in zip(prev[data].values, prev["review_id"], strict=True)}
    for i, row in zip(out.index, _as_text(out[data]).values, strict=True):
        rid = reviewed.get(tuple(row))
        if rid:
            out.at[i, "review"] = "human"
            out.at[i, "review_id"] = rid
    return out


def write_map(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """대응표를 OUT/name.csv로 쓴다. 사람 검수 표시는 keep_human_review로 이어받는다."""
    path = OUT / f"{name}.csv"
    previous = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else None
    out = keep_human_review(df, previous, set(approved_reviews(name)))
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def mark_reviewed(name: str, review_id: str) -> int:
    """지금 OUT/name.csv의 모든 행을 사람 검수 행으로 표시한다. 표시한 행 수를 돌려준다.

    사이트 운영자가 이 파일 그대로를 검수해 human_review.csv에 승인 행을 남긴 직후에만 쓴다.
    그 뒤로는 write_map이 내용이 같은 행의 표시를 이어 간다. 2026-11-13 검수(m1, m2)를 이것으로
    적었다.
    """
    if review_id not in approved_reviews(name):
        raise ValueError(f"human_review.csv에 {name}.csv를 승인한 {review_id} 행이 없다")
    path = OUT / f"{name}.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "review" not in df.columns:
        df["review"] = ""
    df["review"] = "human"
    df["review_id"] = review_id
    df.to_csv(path, index=False)
    return len(df)


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
    write_map(meeting_map, "meeting_map")
    counts["meeting_map"] = len(meeting_map)
    driver_map = build_driver_map(meeting_map, tables["drivers"])
    write_map(driver_map, "driver_map")
    counts["driver_map"] = len(driver_map)
    return counts


if __name__ == "__main__":
    import sys

    for name, n in build(allow_partial="--partial" in sys.argv).items():
        print(f"openf1/{name}: {n} rows")
