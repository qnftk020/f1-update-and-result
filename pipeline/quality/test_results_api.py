"""API 증분 갱신 테스트. (T2, T13)

덤프로 적재한 2025 시즌 대회를 API 응답만으로 다시 넣어 보고, 사이트가 쓰는 값이 덤프 기반
테이블과 같은지 본다. 자동 갱신 워크플로가 쓰는 경로를 2025 대회로 재현하는 검증이다.

비교 기준은 data/curated가 아니라 캐시된 덤프로 새로 만든 테이블이다. post-race 재현은
data/curated/jolpica를 API 행으로 갈아 끼우므로, 그 파일과 비교하면 API 행끼리 비교하게 된다.
재현 픽스처는 기준 테이블에서 대상 라운드 행과 일부 드라이버, 팀을 뺀 뒤 API로 다시 넣는다.
그래야 새 라운드를 넣는 경로(다음 시즌 증분 갱신의 실제 경로)를 검사할 수 있다.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import duckdb
import pandas as pd
import pytest

from pipeline import manifest
from pipeline.config import CURATED_DIR, FIRST_SEASON, LAST_SEASON, RAW_DIR
from pipeline.sources import f1db, jolpica
from pipeline.transforms import results, results_api

# 일반 주말, 스프린트 주말, 순위가 매겨지지 않은 드라이버가 있는 개막전
ROUNDS = [(2025, 24), (2025, 23), (2025, 1)]
ROUND_SQL = "season = 2025 and round in ({})".format(", ".join(str(r) for _, r in ROUNDS))
REMOVED = {"drivers": ("norris", "colapinto"), "constructors": ("mclaren",)}
ID_COLUMN = {"drivers": "driver_id", "constructors": "constructor_id"}
TABLES = list(results_api.ORDER_BY)


def removed_sql(name: str) -> str:
    """재현 픽스처를 만들 때 기준 테이블에서 뺄 행의 조건."""
    if name in REMOVED:
        ids = ", ".join(f"'{x}'" for x in REMOVED[name])
        return f"{ID_COLUMN[name]} in ({ids})"
    if name == "qualifying":  # 스프린트 예선은 API에 없어 남긴다
        return f"{ROUND_SQL} and session_type in ('Q1', 'Q2', 'Q3')"
    return ROUND_SQL


def test_lap_ms():
    assert results_api.lap_ms("1:22.207") == 82207
    assert results_api.lap_ms("58.079") == 58079
    assert results_api.lap_ms("") is None
    assert results_api.lap_ms(None) is None


def test_qualifying_rows_rank_by_session_time():
    def entry(driver: str, **times: str) -> dict:
        return {"number": "1", "Driver": {"driverId": driver},
                "Constructor": {"constructorId": "x"}, **times}  # fmt: skip

    rows = results_api.qualifying_rows(
        2025, 1, [entry("a", Q1="1:10.500", Q2="1:10.000"), entry("b", Q1="1:10.200"),
                  entry("c", Q1="")],
    )  # fmt: skip
    got = {(r["session_type"], r["driver_id"]): (r["position"], r["best_time_ms"]) for r in rows}
    assert got == {
        ("Q1", "a"): (2, 70500),
        ("Q1", "b"): (1, 70200),
        ("Q1", "c"): (None, None),
        ("Q2", "a"): (1, 70000),
    }


def file_sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_upsert_keep_existing_counts_only_added_rows(tmp_path):
    path = tmp_path / "drivers.parquet"
    pd.DataFrame([{"driver_id": "a", "forename": "A"}]).to_parquet(path)
    before = file_sha(path)
    assert results_api.upsert(path, "drivers", [{"driver_id": "a", "forename": "B"}],
                              keep_existing=True) == 0  # fmt: skip
    assert file_sha(path) == before  # 더할 행이 없으면 파일을 다시 쓰지 않는다
    rows = [{"driver_id": "a", "forename": "B"}, {"driver_id": "b", "forename": "C"}]
    assert results_api.upsert(path, "drivers", rows, keep_existing=True) == 1
    got = duckdb.connect().execute(f"select * from '{path}' order by driver_id").fetchall()
    assert got == [("a", "A"), ("b", "C")]


def test_existing_races_keep_dump_date_and_laps(tmp_path):
    """API 일정 전체를 이미 있는 라운드에 반영해도 races.date와 scheduled_laps는 그대로다.

    API의 date는 결승 시작의 UTC 날짜라 2025 라스베이거스(R22)에서 덤프보다 하루 늦다.
    """
    cache = RAW_DIR / "jolpica" / "api" / "2025" / "limit100-offset0.json"
    if not cache.exists():
        pytest.skip("캐시된 2025 일정 응답이 없다")
    schedule = json.loads(cache.read_text())["MRData"]["RaceTable"]["Races"]
    (tmp_path / "jolpica").mkdir()
    shutil.copy(CURATED_DIR / "jolpica" / "races.parquet", tmp_path / "jolpica")
    rows = [results_api.race_row(r, "Sprint" in r) for r in schedule]
    assert results_api.apply_tables({"races": rows}, out_dir=tmp_path) == {"races": len(rows)}
    con = duckdb.connect()
    columns = "round, race_name, date, scheduled_laps, race_start_utc, has_sprint"
    query = f"select {columns} from '{{}}/jolpica/races.parquet' where season = 2025"
    a = set(con.execute(query.format(CURATED_DIR)).fetchall())
    b = set(con.execute(query.format(tmp_path)).fetchall())
    assert a == b and len(a) == len(rows)


def cached_dump_dirs():
    """정제 테이블을 만든 덤프와 F1DB 릴리스의 캐시 폴더. 캐시가 없을 때만 내려받는다."""
    dump = next(
        (r for r in manifest.read_rows(jolpica.DATASET_MANIFEST)
         if r["source"] == "jolpica" and r["name"] == "delayed-dump-csv"),
        None,
    )  # fmt: skip
    dump_dir = RAW_DIR / "jolpica" / "dump" / dump["sha256"] if dump else None
    if dump_dir is None or not dump_dir.exists():
        dump_dir = jolpica.download_dump()
    f1db_dir = RAW_DIR / "f1db" / f1db.RELEASE_TAG / "csv"
    if not f1db_dir.exists():
        f1db_dir = f1db.download_release()
    return dump_dir, f1db_dir


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    """캐시된 덤프로 만든 결과 테이블. data/curated와 달리 post-race가 덮어쓰지 않는다."""
    out = tmp_path_factory.mktemp("dump")
    con = results.connect(*cached_dump_dirs())
    for name in TABLES:
        path = out / "jolpica" / f"{name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        query = results.OUTPUTS[f"jolpica/{name}"].format(first=FIRST_SEASON, last=LAST_SEASON)
        con.execute(f"copy ({query}) to '{path}' (format parquet, compression zstd)")
    return out


@pytest.fixture(scope="module")
def replayed(baseline, tmp_path_factory):
    """기준 테이블에서 대상 라운드와 일부 드라이버, 팀을 뺀 뒤 API로 다시 넣은 테이블."""
    out = tmp_path_factory.mktemp("curated")
    (out / "jolpica").mkdir()
    con = duckdb.connect()
    for name in TABLES:
        con.execute(
            f"copy (select * from '{baseline}/jolpica/{name}.parquet' "
            f"where not ({removed_sql(name)}) order by {results_api.ORDER_BY[name]}) "
            f"to '{out}/jolpica/{name}.parquet' (format parquet, compression zstd)"
        )
    counts = {(s, r): results_api.apply_round(s, r, out_dir=out) for s, r in ROUNDS}
    return out, counts


def compare(name: str, old, new, columns: str, where: str) -> tuple[set, set]:
    con = duckdb.connect()
    query = f"select {columns} from '{{}}/jolpica/{name}.parquet' where {where}"
    a = set(con.execute(query.format(old)).fetchall())
    b = set(con.execute(query.format(new)).fetchall())
    return a, b


def assert_round_matches(old, new, season: int, rnd: int, race_columns: str = "") -> None:
    where = f"season = {season} and round = {rnd}"
    a, b = compare(
        "results", old, new,
        "session_type, driver_id, constructor_id, car_number, grid, position, is_classified,"
        " status_detail, laps_completed, points, fastest_lap_rank,"
        " case when is_classified then time_ms end",
        where,
    )  # fmt: skip
    assert a == b and len(a) >= 20
    a, b = compare(
        "qualifying", old, new,
        "session_type, driver_id, constructor_id, car_number, best_time_ms", where,
    )  # fmt: skip
    assert a == b and len(a) >= 45
    for name, key in [
        ("driver_standings", "driver_id"),
        ("constructor_standings", "constructor_id"),
    ]:
        a, b = compare(name, old, new, f"{key}, position, points, wins, is_eligible", where)
        assert a == b and a
    a, b = compare(
        "races", old, new,
        "race_name, date, circuit_id, circuit_name, locality, country, latitude, longitude,"
        f" race_start_utc, has_sprint, wikipedia_url{race_columns}",
        where,
    )  # fmt: skip
    assert a == b and len(a) == 1


@pytest.mark.network
@pytest.mark.parametrize(("season", "rnd"), ROUNDS)
def test_api_round_matches_dump(baseline, replayed, season, rnd):
    assert_round_matches(baseline, replayed[0], season, rnd)


@pytest.mark.network
def test_round_one_has_unranked_drivers(baseline):
    """개막전 비교가 is_eligible이 거짓인 행을 실제로 포함하는지 확인한다."""
    con = duckdb.connect()
    n = con.execute(
        f"select count(*) from '{baseline}/jolpica/driver_standings.parquet' "
        "where season = 2025 and round = 1 and not is_eligible and position is null"
    ).fetchone()[0]
    assert n > 0


@pytest.mark.network
@pytest.mark.parametrize("name", list(REMOVED))
def test_api_people_match_dump(baseline, replayed, name):
    """API로 새로 넣은 드라이버와 팀이 덤프 값과 같다. country_code는 API에 없다."""
    columns = {
        "drivers": "driver_id, forename, surname, abbreviation, permanent_number, nationality,"
        " date_of_birth, wikipedia_url",
        "constructors": "constructor_id, name, nationality, wikipedia_url",
    }[name]
    a, b = compare(name, baseline, replayed[0], columns, removed_sql(name))
    assert a == b and len(a) == len(REMOVED[name])


@pytest.mark.network
def test_apply_round_counts_added_people(replayed):
    counts = replayed[1]
    first, *rest = ROUNDS  # 빠진 드라이버와 팀은 모두 첫 라운드에서 다시 들어간다
    assert counts[first]["drivers"] == len(REMOVED["drivers"])
    assert counts[first]["constructors"] == len(REMOVED["constructors"])
    for key in rest:
        assert counts[key]["drivers"] == 0 and counts[key]["constructors"] == 0


@pytest.mark.network
def test_other_rounds_and_schemas_are_untouched(baseline, replayed):
    con = duckdb.connect()
    for name in TABLES:
        old = f"'{baseline}/jolpica/{name}.parquet'"
        new = f"'{replayed[0]}/jolpica/{name}.parquet'"
        assert (
            con.execute(f"describe select * from {old}").fetchall()
            == con.execute(f"describe select * from {new}").fetchall()
        ), name
        assert (
            con.execute(f"select count(*) from {old}").fetchone()
            == con.execute(f"select count(*) from {new}").fetchone()
        ), name
        where = f"not ({removed_sql(name)})"
        for x, y in [(old, new), (new, old)]:
            n = con.execute(f"select count(*) from (select * from {x} where {where} except"
                            f" select * from {y} where {where})").fetchone()[0]  # fmt: skip
            assert n == 0, name


@pytest.mark.network
def test_apply_round_replaces_existing_round(baseline, tmp_path):
    """이미 있는 라운드를 다시 적용하면 그 라운드 행을 API 값으로 갈아 끼운다.

    드라이버와 팀 목록은 이미 있는 키를 건드리지 않고 파일도 다시 쓰지 않는다. scheduled_laps는
    API에 없으므로 기존 값을 둔다.
    """
    season, rnd = ROUNDS[0]
    shutil.copytree(baseline / "jolpica", tmp_path / "jolpica")
    where = f"season = {season} and round = {rnd}"
    con = duckdb.connect()
    for name, change in [
        ("results", "points = points + 100"),
        ("qualifying", "best_time_ms = best_time_ms + 1"),
        ("driver_standings", "wins = wins + 1"),
        ("constructor_standings", "wins = wins + 1"),
        ("races", "race_name = 'X'"),
        ("drivers", "forename = 'X'"),
    ]:
        path = tmp_path / "jolpica" / f"{name}.parquet"
        cond = "driver_id = 'norris'" if name == "drivers" else where
        con.execute(f"create or replace table t as select * from '{path}'")
        con.execute(f"update t set {change} where {cond}")
        con.execute(f"copy t to '{path}' (format parquet, compression zstd)")
    drivers = tmp_path / "jolpica" / "drivers.parquet"
    before = file_sha(drivers)
    counts = results_api.apply_round(season, rnd, out_dir=tmp_path)
    assert_round_matches(baseline, tmp_path, season, rnd, race_columns=", scheduled_laps")
    assert counts["drivers"] == 0 and counts["constructors"] == 0
    assert file_sha(drivers) == before
    assert con.execute(
        f"select forename from '{drivers}' where driver_id = 'norris'"
    ).fetchone() == ("X",)


@pytest.mark.network
def test_replaying_a_dump_round_changes_nothing(baseline, tmp_path):
    """덤프로 적재된 라운드를 API로 다시 반영해도 파일이 그대로다(T13 수동 재현).

    API에 없는 status_code와 기록 없는 Q3 드라이버의 세션 순위는 덤프 값을 두고,
    내용이 같으면 파일을 다시 쓰지 않는다.
    """
    season, rnd = ROUNDS[0]
    shutil.copytree(baseline / "jolpica", tmp_path / "jolpica")
    before = {name: file_sha(tmp_path / "jolpica" / f"{name}.parquet") for name in TABLES}
    results_api.apply_round(season, rnd, out_dir=tmp_path)
    after = {name: file_sha(tmp_path / "jolpica" / f"{name}.parquet") for name in TABLES}
    assert after == before
