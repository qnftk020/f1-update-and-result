"""T9 OpenF1 정제 테이블과 대응표 검증."""

import pandas as pd
import pytest

from pipeline.config import CURATED_DIR, LAST_SEASON, OPENF1_FIRST_SEASON

OF = CURATED_DIR / "openf1"


@pytest.fixture(scope="module")
def meeting_map():
    return pd.read_csv(OF / "meeting_map.csv")


def test_every_race_is_matched_to_an_openf1_meeting(meeting_map):
    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    expected = races[races["season"].between(OPENF1_FIRST_SEASON, LAST_SEASON)]
    assert len(meeting_map) == len(expected) == 70
    for column in ["meeting_key", "qualifying_session_key", "race_session_key"]:
        assert meeting_map[column].notna().all(), column
        assert meeting_map[column].is_unique, column


def test_circuit_mapping_is_consistent_across_seasons(meeting_map):
    """같은 Jolpica 서킷은 늘 같은 OpenF1 서킷 키에 대응해야 한다(반대도 같다)."""
    assert (meeting_map.groupby("circuit_id")["openf1_circuit_key"].nunique() == 1).all()
    assert (meeting_map.groupby("openf1_circuit_key")["circuit_id"].nunique() == 1).all()


def test_driver_map_has_only_known_exceptions():
    """차량 번호로 맞춘 결과에서 한쪽에만 있는 드라이버는 알려진 예외뿐이어야 한다.

    예외: 2023년 15라운드(싱가포르)의 Stroll. 예선 사고 뒤 결승에 나오지 않아 Jolpica 결과에는
    있고 OpenF1 결승 세션에는 없다.
    """
    driver_map = pd.read_csv(OF / "driver_map.csv")
    # 자동 대응의 check 조건(한쪽에만 있거나 약어가 다르다). 검수 뒤에는 review가 human이라
    # 조건을 열 값으로 다시 본다.
    check = driver_map[
        (driver_map["unmatched"] > 0) | (driver_map["name_acronym"] != driver_map["abbreviation"])
    ]
    assert [(r.season, r.driver_number, r.driver_id) for r in check.itertuples()] == [
        (2023, 18, "stroll")
    ]
    assert not driver_map.duplicated(["season", "driver_number", "first_round"]).any()


def test_maps_carry_the_human_review():
    """두 대응표의 모든 행은 2026-11-13 사람 검수(human_review.csv m1, m2)를 거쳤다."""
    from pipeline import review

    approved = {
        r["id"]: r["target"]
        for doc_type in ("openf1_meeting_map", "openf1_driver_map")
        for r in review.decisions(doc_type)
        if r["decision"] == "approve"
    }
    for name, rid in (("meeting_map", "m1"), ("driver_map", "m2")):
        df = pd.read_csv(OF / f"{name}.csv", dtype=str, keep_default_na=False)
        assert list(df.columns[-2:]) == ["review", "review_id"], name
        assert (df["review"] == "human").all() and (df["review_id"] == rid).all(), name
        assert approved[rid] == f"{name}.csv"


def test_regenerated_maps_keep_human_review_only_for_unchanged_rows(tmp_path, monkeypatch):
    """다시 만든 대응표는 앞 파일에서 검수한 행과 내용이 같은 행만 human을 이어받는다."""
    from pipeline.transforms import openf1_tables as ot

    monkeypatch.setattr(ot, "OUT", tmp_path)
    monkeypatch.setattr(ot, "approved_reviews", lambda name: {"m9": {}})
    prev = pd.DataFrame(
        {"season": [2025, 2025], "driver_number": [1, 4], "review": ["human", "human"],
         "review_id": ["m9", "m9"]}
    )  # fmt: skip
    prev.to_csv(tmp_path / "driver_map.csv", index=False)
    new = pd.DataFrame(
        {"season": [2025, 2025, 2025], "driver_number": [1, 5, 4],
         "review": ["auto", "auto", "check"]}
    )  # fmt: skip
    new["driver_number"] = new["driver_number"].astype("Int64")
    out = ot.write_map(new, "driver_map")
    assert out["review"].tolist() == ["human", "auto", "human"]
    assert out["review_id"].tolist() == ["m9", "", "m9"]
    # 승인 행이 human_review.csv에서 사라지면 표시도 이어받지 않는다.
    monkeypatch.setattr(ot, "approved_reviews", lambda name: {})
    out = ot.write_map(new, "driver_map")
    assert out["review"].tolist() == ["auto", "auto", "check"]
    # 대응표에 review 열이 없으면(미팅 대응표) auto로 시작한다.
    meetings = ot.write_map(pd.DataFrame({"season": [2025], "round": [1]}), "meeting_map")
    assert meetings["review"].tolist() == ["auto"]


def test_weather_has_no_impossible_values():
    weather = pd.read_parquet(OF / "weather.parquet")
    assert not (weather["track_temperature"] <= 0).any()
    assert not (weather["humidity"] <= 0).any()
    assert not (weather["pressure"] <= 0).any()
    assert weather["track_temperature"].max() < 80


# OpenF1에 랩 자료가 없는 세션(2026-11-11에 두 번 요청해 모두 "No results found").
SESSIONS_WITHOUT_LAPS = {9900}  # 2025 아제르바이잔 예선


def test_every_session_has_laps_and_results(meeting_map):
    laps = pd.read_parquet(OF / "laps.parquet")
    results = pd.read_parquet(OF / "session_result.parquet")
    keys = set(meeting_map["qualifying_session_key"]) | set(meeting_map["race_session_key"])
    assert keys - set(laps["session_key"]) == SESSIONS_WITHOUT_LAPS
    assert set(meeting_map["race_session_key"]) <= set(laps["session_key"])
    assert set(meeting_map["race_session_key"]) <= set(results["session_key"])
