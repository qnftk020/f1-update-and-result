"""T10 페이스 지수 검증."""

import duckdb
import pytest

from pipeline.config import CURATED_DIR

Q = CURATED_DIR / "pace" / "qualifying_index.parquet"
J = CURATED_DIR / "jolpica"


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


F = CURATED_DIR / "f1db"


def test_qualifying_index_covers_every_race_except_indianapolis(con):
    """1950년부터 모든 대회가 있다. 인디애나폴리스 500(4랩 합계 기록, 1950-1960)만 뺀다."""
    missing = con.execute(f"""
        select r.season, r.round, f.qualifying_format from '{J}/races.parquet' r
        join '{F}/races.parquet' f using (season, round)
        anti join '{Q}' q using (season, round)
    """).fetchall()
    assert len(missing) == 11
    assert {m[2] for m in missing} == {"FOUR_LAPS"}


def test_pre_1996_entries_map_to_jolpica_constructors(con):
    """1996년 이전 F1DB 예선 기록 14,391행 가운데 Jolpica 결승 결과의 차 번호, 같은 차체와 엔진,
    그 시즌 Jolpica 컨스트럭터 이름으로 맞지 않는 44행(예선 탈락, 1966-1969 독일 대회의 F2 차)만
    빠진다."""
    kept = con.execute(f"select sum(drivers_entered) from '{Q}' where season < 1996").fetchone()[0]
    assert kept == 14391 - 44


def test_qualifying_index_pre_1996_hand_calculations(con):
    """F1DB 예선 기록으로 따로 계산한 세 대회(docs/methodology.md).

    1950 영국: 알파 로메오 Farina 1:50.8, 마세라티 Bira 1:52.6 -> 112,600 / 110,800 - 1.
    1975 벨기에: 페라리 Lauda 1:25.43, 브라밤 Pace 1:25.47. 1988 브라질: 맥라렌 Senna 1:28.096,
    로터스 Piquet 1:30.087(Jolpica ID team_lotus).
    """
    cases = [
        (1950, 1, "alfa", 110800, 110800, 0.0),
        (1950, 1, "maserati", 112600, 110800, 1.6245),
        (1975, 6, "brabham", 85470, 85430, 0.0468),
        (1988, 1, "williams", 88632, 88096, 0.6084),
        (1988, 1, "team_lotus", 90087, 88096, 2.26),
    ]
    for season, rnd, team, team_best, session_best, index in cases:
        row = con.execute(
            f"select team_best_ms, session_best_ms, index_pct from '{Q}' "
            "where season = ? and round = ? and constructor_id = ?",
            [season, rnd, team],
        ).fetchone()
        assert row[:2] == (team_best, session_best), (season, rnd, team)
        assert row[2] == pytest.approx(index, abs=1e-4)


def test_qualifying_index_is_zero_for_fastest_and_never_negative(con):
    lo, zero_rounds, rounds = con.execute(f"""
        select min(index_pct), count(distinct (season, round)) filter (where index_pct = 0),
               count(distinct (season, round)) from '{Q}'
    """).fetchone()
    assert lo == 0
    assert zero_rounds == rounds


def test_qualifying_index_matches_hand_calculation(con):
    """수기 계산(docs/methodology.md): 2025년 1라운드 레드불 = 75,481 / 75,096 - 1 = 0.513%."""
    team, best, index = con.execute(f"""
        select team_best_ms, session_best_ms, index_pct from '{Q}'
        where season = 2025 and round = 1 and constructor_id = 'red_bull'
    """).fetchone()
    assert (team, best) == (75481, 75096)
    assert index == pytest.approx(0.5127, abs=1e-4)


def test_qualifying_index_teams_exist_in_jolpica(con):
    """대응표를 거친 팀 ID가 Jolpica에 있는 ID인지 본다(예선 탈락 팀 포함)."""
    unknown = con.execute(f"""
        select distinct q.constructor_id from '{Q}' q
        anti join '{J}/constructors.parquet' c using (constructor_id)
    """).fetchall()
    assert unknown == []


def test_reference_formats_are_flagged(con):
    seasons = con.execute(
        f"select distinct season from '{Q}' where is_reference_format order by 1"
    ).fetchall()
    assert [s[0] for s in seasons] == [2003, 2004, 2005]


# --- 레이스 페이스 지수 ---------------------------------------------------------------

R = CURATED_DIR / "pace" / "race_index.parquet"


def test_qualifying_index_matches_api_hand_calculations(con):
    """Jolpica API 값으로 따로 계산한 세 대회 (docs/methodology.md)."""
    cases = [
        (2024, 8, "ferrari", 70270, 70270, 0.0),
        (2023, 1, "aston_martin", 90336, 89708, 0.7),
        (2010, 5, "mclaren", 80829, 79995, 1.0426),
    ]
    for season, rnd, team, team_best, session_best, index in cases:
        row = con.execute(
            f"select team_best_ms, session_best_ms, index_pct from '{Q}' "
            "where season = ? and round = ? and constructor_id = ?",
            [season, rnd, team],
        ).fetchone()
        assert row[:2] == (team_best, session_best)
        assert row[2] == pytest.approx(index, abs=1e-4)


def test_race_index_covers_every_race_2014_2025(con):
    """2014-2022년은 Jolpica 계열, 2023-2025년은 OpenF1 계열이다. 두 계열이 시즌을 나눠 갖는다."""
    rows = dict(
        con.execute(f"""
            select method, count(distinct (season, round)) from '{R}' group by 1
        """).fetchall()
    )
    assert rows == {"jolpica": 182, "openf1": 70}
    mixed = con.execute(f"""
        select season from '{R}' group by 1
        having count(distinct method) > 1
            or min(method) <> case when season < 2023 then 'jolpica' else 'openf1' end
    """).fetchall()
    assert mixed == []
    missing = con.execute(f"""
        select r.season, r.round from '{J}/races.parquet' r
        anti join '{R}' x using (season, round) where r.season between 2014 and 2025
    """).fetchall()
    assert missing == []


def test_jolpica_race_index_matches_independent_recalculation(con):
    """Jolpica 덤프 CSV만으로 따로 계산한 두 대회(docs/methodology.md). 마른 대회이고 중립화 추정
    랩이 없다. 2015 바레인(100kg), 2019 중국(110kg)."""
    cases = [
        (2015, 4, {"mercedes": -1.3026, "ferrari": -1.2854, "lotus_f1": -0.3124}),
        (2019, 3, {"mercedes": -2.1954, "ferrari": -2.0918, "red_bull": -1.4311}),
    ]
    for season, rnd, expected in cases:
        rows = dict(
            con.execute(
                f"select constructor_id, index_pct from '{R}' where season = ? and round = ?",
                [season, rnd],
            ).fetchall()
        )
        for team, value in expected.items():
            assert rows[team] == pytest.approx(value, abs=1e-4), (season, rnd, team)


def test_jolpica_race_fuel_follows_regulations(con):
    """출발 연료량은 그 시즌 스포팅 규정의 경주 연료 상한이다(2014-2016 100kg, 2017-2018 105kg,
    2019-2021 110kg). 상한 조항이 없는 2022년은 OpenF1 계열과 같은 110kg이다."""
    fuel = dict(
        con.execute(
            f"select season, min(start_fuel_kg) from '{R}' group by 1"
            " having count(distinct start_fuel_kg) = 1"
        ).fetchall()
    )
    expected = {2014: 100, 2015: 100, 2016: 100, 2017: 105, 2018: 105, 2019: 110, 2020: 110,
                2021: 110, 2022: 110, 2023: 110, 2024: 110, 2025: 110}  # fmt: skip
    assert fuel == expected


def test_race_index_is_centred_on_the_field_median(con):
    """필드 기준이 팀 값의 중앙값이므로 대회별 지수의 중앙값은 0이어야 한다."""
    worst = con.execute(f"""
        select max(abs(m)) from (
            select median(index_pct) as m from '{R}' where index_pct is not null
            group by season, round)
    """).fetchone()[0]
    assert worst < 1e-3


def test_race_index_interval_contains_the_estimate(con):
    bad = con.execute(f"""
        select count(*) from '{R}'
        where index_pct is not null and not (ci_low_pct <= index_pct and index_pct <= ci_high_pct)
    """).fetchone()[0]
    assert bad == 0


def test_race_index_needs_enough_clean_laps(con):
    bad = con.execute(f"""
        select count(*) from '{R}'
        where (clean_laps < 8 or wet_flag = 'unclassified') <> (index_pct is null)
    """).fetchone()[0]
    assert bad == 0


def test_race_index_matches_independent_recalculation(con):
    """원문 JSON으로 따로 계산한 세 대회의 값 (docs/methodology.md)."""
    cases = [
        (2023, 5, {"red_bull": -1.1776, "mercedes": -0.3631, "aston_martin": -0.2727}),
        (2024, 1, {"red_bull": -1.2566, "ferrari": -0.7356, "mclaren": -0.6082}),
        (2025, 2, {"mclaren": -0.8496, "ferrari": -0.5911, "red_bull": -0.4134}),
    ]
    for season, rnd, expected in cases:
        rows = dict(
            con.execute(
                f"select constructor_id, index_pct from '{R}' where season = ? and round = ?",
                [season, rnd],
            ).fetchall()
        )
        for team, value in expected.items():
            assert rows[team] == pytest.approx(value, abs=1e-4), (season, rnd, team)


def test_wet_flags(con):
    flags = dict(
        con.execute(f"""
            select wet_flag, count(distinct (season, round)) from '{Q}' group by 1
        """).fetchall()
    )
    assert flags["wet"] + flags["dry"] == 70
    assert flags["unclassified"] == 1068
    seasons = con.execute(
        f"select min(season), max(season) from '{Q}' where wet_flag <> 'unclassified'"
    ).fetchone()
    assert seasons == (2023, 2025)
    # 2024년 상파울루 결승은 비로 클린 랩이 없었다
    wet, teams = con.execute(f"""
        select bool_and(is_wet), count(index_pct) from '{R}' where season = 2024 and round = 21
    """).fetchone()
    assert wet and teams == 0


def test_wet_rule_is_tyres_or_rain_share(con):
    """우천은 웨트 계열 타이어를 쓴 세션이거나 강우 표본이 10% 이상인 세션이다(OpenF1 계열).
    Jolpica 계열(2014-2022)은 결승 시간대 ERA5 강수량 1.0mm 이상이 wet, 0.2mm 미만이 dry다.

    강우 표본이 없는 세션은 우천이 확인되지 않는 한 dry가 아니라 unclassified다. 그래서 강우
    비율이 결측인 dry 행이 있는지 따로 본다.
    """
    bad = con.execute(f"""
        select count(*) from '{R}'
        where method = 'jolpica' and (
              (wet_flag = 'wet') <> coalesce(precip_mm >= 1.0, false)
           or (wet_flag = 'dry') <> coalesce(precip_mm < 0.2, false)
           or wet_tyres is not null or rain_sample_share is not null)
    """).fetchone()[0]
    assert bad == 0
    bad = con.execute(f"""
        select count(*) from '{R}'
        where (method = 'openf1' and (
                  (wet_flag = 'wet') <> (wet_tyres or coalesce(rain_sample_share >= 0.10, false))
               or (wet_flag = 'dry' and rain_sample_share is null)))
           or (is_wet is null) <> (wet_flag = 'unclassified')
           or is_wet <> (wet_flag = 'wet')
    """).fetchone()[0]
    assert bad == 0
    bad = con.execute(f"""
        select count(*) from '{Q}' where season >= 2023
          and ((wet_flag = 'wet') <> (wet_tyres or coalesce(rain_sample_share >= 0.10, false))
               or (wet_flag = 'dry' and rain_sample_share is null))
    """).fetchone()[0]
    assert bad == 0
    race = dict(
        con.execute(f"""
            select round, bool_or(is_wet) from '{R}' where season = 2024 and round in (10, 12)
            group by 1
        """).fetchall()
    )
    assert race == {10: False, 12: True}  # 스페인은 가랑비 표본 1%, 영국은 인터미디어트 사용
    quali = dict(
        con.execute(f"""
            select round, any_value(wet_flag) from '{Q}' where season = 2024 and round in (3, 13)
            group by 1
        """).fetchall()
    )
    assert quali == {3: "dry", 13: "wet"}  # 헝가리 예선은 슬릭이었지만 표본의 76%가 강우


# --- 판정 자료가 빠진 세션 ------------------------------------------------------------

OPENF1_TABLES = ["laps", "stints", "pit", "race_control", "session_result", "weather"]


def sandbox(tmp_path, monkeypatch, season, rnd, drop=()):
    """한 대회만 담은 임시 curated 폴더를 만들고 pace_index가 그 폴더를 읽게 한다.

    drop에는 (테이블, "Q" 또는 "R")을 넣어 그 세션의 행을 지운다. 원본 테이블은 건드리지 않는다.
    """
    import shutil

    import pandas as pd

    from pipeline.transforms import pace_index as pi

    root = tmp_path / "curated"
    (root / "openf1").mkdir(parents=True)
    (root / "pace").mkdir()
    (root / "jolpica").symlink_to(J)
    shutil.copy(Q, root / "pace" / "qualifying_index.parquet")
    src = CURATED_DIR / "openf1"
    mm = pd.read_csv(src / "meeting_map.csv")
    mm = mm[(mm["season"] == season) & (mm["round"] == rnd)]
    mm.to_csv(root / "openf1" / "meeting_map.csv", index=False)
    keys = {
        "Q": int(mm["qualifying_session_key"].iloc[0]),
        "R": int(mm["race_session_key"].iloc[0]),
    }
    for name in OPENF1_TABLES:
        df = pd.read_parquet(src / f"{name}.parquet")
        df = df[df["session_key"].isin(keys.values())]
        gone = [keys[kind] for table, kind in drop if table == name]
        df[~df["session_key"].isin(gone)].to_parquet(root / "openf1" / f"{name}.parquet")
    monkeypatch.setattr(pi, "CURATED_DIR", root)
    monkeypatch.setattr(pi, "J", root / "jolpica")
    monkeypatch.setattr(pi, "PACE", root / "pace")
    return pi, root


def quali_flag(pi, root, season, rnd):
    import pandas as pd

    pi.add_qualifying_wet_flags()
    q = pd.read_parquet(root / "pace" / "qualifying_index.parquet")
    return q[(q["season"] == season) & (q["round"] == rnd)]["wet_flag"].unique().tolist()


@pytest.mark.parametrize(
    ("season", "rnd", "drop", "expected"),
    [
        (2024, 21, [("weather", "Q"), ("stints", "Q")], "unclassified"),  # 상파울루, 실제는 wet
        (2024, 13, [("weather", "Q")], "unclassified"),  # 헝가리, 슬릭에 강우 76%
        (2024, 12, [("stints", "Q")], "unclassified"),  # 영국, 인터미디어트에 강우 7%
        (2024, 3, [], "dry"),  # 자료가 다 있으면 판정은 그대로다
        (2024, 13, [("stints", "Q")], "wet"),  # 강우 비율만으로 우천이 확인된다
    ],
)
def test_qualifying_without_rain_evidence_is_unclassified(
    tmp_path, monkeypatch, season, rnd, drop, expected
):
    pi, root = sandbox(tmp_path, monkeypatch, season, rnd, drop)
    assert quali_flag(pi, root, season, rnd) == [expected]


def test_qualifying_without_session_key_is_unclassified(tmp_path, monkeypatch):
    import pandas as pd

    pi, root = sandbox(tmp_path, monkeypatch, 2024, 21)
    path = root / "openf1" / "meeting_map.csv"
    mm = pd.read_csv(path)
    mm["qualifying_session_key"] = pd.NA
    mm.to_csv(path, index=False)
    assert quali_flag(pi, root, 2024, 21) == ["unclassified"]


@pytest.mark.parametrize(
    ("season", "rnd", "drop", "expected"),
    [
        (2024, 21, [("weather", "R"), ("stints", "R")], "unclassified"),  # 상파울루
        (2023, 12, [("weather", "R")], "unclassified"),  # 벨기에, 슬릭에 강우 11.9%
        (2025, 13, [("stints", "R")], "unclassified"),  # 벨기에, 인터미디어트에 강우 0%
        (2023, 12, [("stints", "R")], "wet"),  # 강우 비율만으로 우천이 확인된다
        (2024, 1, [], "dry"),
    ],
)
def test_race_without_rain_evidence_is_unclassified(
    tmp_path, monkeypatch, season, rnd, drop, expected
):
    """판정하지 못한 결승은 is_wet이 NULL이고 지수를 내지 않는다."""
    import pandas as pd

    pi, root = sandbox(tmp_path, monkeypatch, season, rnd, drop)
    pi.build_race(jolpica=False)
    r = pd.read_parquet(root / "pace" / "race_index.parquet")
    assert r["wet_flag"].unique().tolist() == [expected]
    if expected == "unclassified":
        assert r["is_wet"].isna().all()
        assert r["index_pct"].isna().all()
    else:
        assert r["is_wet"].tolist() == [expected == "wet"] * len(r)
    if expected == "dry":
        assert r["index_pct"].notna().all()


def test_race_rain_window_starts_at_session_start(con):
    """2025년 마이애미 결승은 OpenF1에 2-24랩이 없어 첫 랩 출발 시각을 알 수 없다.

    강우 표본은 레이스 컨트롤의 SESSION STARTED(20:03:42Z)부터 세므로 91개 중 5개, 0.0549다.
    첫 랩 기록(25랩 무렵)부터 세면 52개 중 5개, 0.0962가 된다.
    """
    share, wet = con.execute(f"""
        select any_value(rain_sample_share), bool_or(is_wet) from '{R}'
        where season = 2025 and round = 6
    """).fetchone()
    assert share == pytest.approx(0.0549, abs=1e-4)
    assert wet is False


def test_dry_sessions_have_rain_evidence(con):
    """dry로 판정한 2023년 이후 세션은 날씨 표본과 스틴트가 모두 있어야 한다."""
    stints = CURATED_DIR / "openf1" / "stints.parquet"
    mm = CURATED_DIR / "openf1" / "meeting_map.csv"
    bad = con.execute(f"""
        select count(*) from (select distinct season, round, rain_sample_share from '{Q}'
                              where season >= 2023 and wet_flag = 'dry') q
        join read_csv('{mm}') m using (season, round)
        where q.rain_sample_share is null or m.qualifying_session_key not in
              (select session_key from '{stints}')
    """).fetchone()[0]
    assert bad == 0
    bad = con.execute(f"""
        select count(*) from '{R}' where index_pct is not null
          and ((method = 'openf1' and rain_sample_share is null) or wet_flag = 'unclassified'
               or is_wet is null)
    """).fetchone()[0]
    assert bad == 0
