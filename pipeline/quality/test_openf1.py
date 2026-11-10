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
    check = driver_map[driver_map["review"] == "check"]
    assert [(r.season, r.driver_number, r.driver_id) for r in check.itertuples()] == [
        (2023, 18, "stroll")
    ]
    matched = driver_map[driver_map["review"] == "auto"]
    assert (matched["name_acronym"] == matched["abbreviation"]).all()
    assert not matched.duplicated(["season", "driver_number", "first_round"]).any()


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
