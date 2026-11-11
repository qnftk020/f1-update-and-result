"""API 증분 갱신 테스트. (T2, T13)

덤프로 적재한 2025 시즌 대회를 API 응답만으로 다시 넣어 보고, 사이트가 쓰는 값이 덤프 기반
테이블과 같은지 본다. 자동 갱신 워크플로가 쓰는 경로를 2025 대회로 재현하는 검증이다.
"""

from __future__ import annotations

import shutil

import duckdb
import pytest

from pipeline.config import CURATED_DIR
from pipeline.transforms import results_api

ROUNDS = [(2025, 24), (2025, 23)]  # 일반 주말, 스프린트 주말


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


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    out = tmp_path_factory.mktemp("curated")
    shutil.copytree(CURATED_DIR / "jolpica", out / "jolpica")
    for season, rnd in ROUNDS:
        results_api.apply_round(season, rnd, out_dir=out)
    return out


def compare(name: str, replayed, columns: str, where: str) -> tuple[set, set]:
    con = duckdb.connect()
    old = f"'{CURATED_DIR}/jolpica/{name}.parquet'"
    new = f"'{replayed}/jolpica/{name}.parquet'"
    a = set(con.execute(f"select {columns} from {old} where {where}").fetchall())
    b = set(con.execute(f"select {columns} from {new} where {where}").fetchall())
    return a, b


@pytest.mark.network
@pytest.mark.parametrize(("season", "rnd"), ROUNDS)
def test_api_round_matches_dump(replayed, season, rnd):
    where = f"season = {season} and round = {rnd}"
    a, b = compare(
        "results", replayed,
        "session_type, driver_id, constructor_id, car_number, grid, position, is_classified,"
        " status_detail, laps_completed, points, fastest_lap_rank,"
        " case when is_classified then time_ms end",
        where,
    )  # fmt: skip
    assert a == b and len(a) >= 20
    a, b = compare(
        "qualifying", replayed,
        "session_type, driver_id, constructor_id, car_number, best_time_ms", where,
    )  # fmt: skip
    assert a == b and len(a) >= 45
    for name, key in [
        ("driver_standings", "driver_id"),
        ("constructor_standings", "constructor_id"),
    ]:
        a, b = compare(name, replayed, f"{key}, position, points, wins, is_eligible", where)
        assert a == b and a
    a, b = compare(
        "races", replayed,
        "race_name, date, circuit_id, circuit_name, locality, country, latitude, longitude,"
        " race_start_utc, has_sprint, wikipedia_url",
        where,
    )  # fmt: skip
    assert a == b and len(a) == 1


@pytest.mark.network
def test_other_rounds_and_schemas_are_untouched(replayed):
    con = duckdb.connect()
    for name in results_api.ORDER_BY:
        old = f"'{CURATED_DIR}/jolpica/{name}.parquet'"
        new = f"'{replayed}/jolpica/{name}.parquet'"
        assert (
            con.execute(f"describe select * from {old}").fetchall()
            == con.execute(f"describe select * from {new}").fetchall()
        ), name
        assert (
            con.execute(f"select count(*) from {old}").fetchone()
            == con.execute(f"select count(*) from {new}").fetchone()
        ), name
        if name in ("drivers", "constructors"):
            where = "true"
        else:
            where = "not (season = 2025 and round in (23, 24))"
        a = con.execute(f"select count(*) from (select * from {old} where {where} except"
                        f" select * from {new} where {where})").fetchone()[0]  # fmt: skip
        assert a == 0, name
