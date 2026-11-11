"""HTTP 클라이언트의 요청 간격, 캐시, 거부 응답 처리 규칙 테스트."""

from __future__ import annotations

import csv
import errno
import io
import json
import re
import time
from pathlib import Path

import httpx
import pytest

from pipeline import http
from pipeline.sources import openf1

pytest_plugins = ["pytester"]

REPO = Path(__file__).resolve().parents[2]


def make_client(tmp_path, calls: list[float]) -> http.PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(time.time())
        return httpx.Response(200, content=b"ok")

    return http.PoliteClient("testsrc", raw_dir=tmp_path, transport=httpx.MockTransport(handler))


def test_interval_holds_across_clients(tmp_path, monkeypatch):
    """클라이언트(프로세스)가 달라도 같은 데이터원의 요청 간격은 잠금 파일로 지켜진다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.3)
    calls: list[float] = []
    a = make_client(tmp_path, calls)
    b = make_client(tmp_path, calls)
    a.get("https://example.invalid/1", "1.txt")
    b.get("https://example.invalid/2", "2.txt")
    a.get("https://example.invalid/3", "3.txt")
    gaps = [later - earlier for earlier, later in zip(calls, calls[1:], strict=False)]
    assert len(calls) == 3
    assert all(gap >= 0.29 for gap in gaps), gaps


def test_cache_hit_sends_no_request(tmp_path, monkeypatch):
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    calls: list[float] = []
    client = make_client(tmp_path, calls)
    first = client.get("https://example.invalid/a", "a.txt")
    second = client.get("https://example.invalid/a", "a.txt")
    assert len(calls) == 1
    assert not first.from_cache and second.from_cache
    assert first.sha256 == second.sha256


def test_hourly_quota_is_shared_through_lock_file(tmp_path, monkeypatch):
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    monkeypatch.setitem(http.MAX_REQUESTS_PER_HOUR, "testsrc", 5)
    calls: list[float] = []
    a = make_client(tmp_path, calls)
    b = make_client(tmp_path, calls)
    for i in range(2):
        a.get(f"https://example.invalid/{i}", f"a{i}.txt")
        b.get(f"https://example.invalid/{i}", f"b{i}.txt")
    state = json.loads((tmp_path / "_locks" / "testsrc.json").read_text())
    assert len(state["recent"]) == 4


def test_block_response_waits_and_is_not_bypassed(tmp_path, monkeypatch):
    """429나 Cloudflare 확인 화면을 받으면 정해진 시간만큼 쉬고, 계속 막히면 멈춘다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    calls: list[float] = []
    cached_before: list[bool] = []
    x_path = tmp_path / "testsrc" / "x.txt"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(time.time())
        cached_before.append(x_path.exists())  # 거부 응답 본문이 캐시로 남았는지 요청마다 본다
        if len(calls) <= 2:
            return httpx.Response(429, headers={"cf-mitigated": "challenge"}, content=b"wait")
        return httpx.Response(200, content=b"ok")

    client = http.PoliteClient(
        "testsrc",
        raw_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        block_cooldowns=(0.2, 0.2),
    )
    result = client.get("https://example.invalid/x", "x.txt")
    assert result.content == b"ok"
    assert len(calls) == 3
    assert calls[1] - calls[0] >= 0.19 and calls[2] - calls[1] >= 0.19
    assert cached_before == [False, False, False]
    assert x_path.read_bytes() == b"ok"
    assert sorted(p.name for p in x_path.parent.iterdir()) == ["x.txt"]

    blocked = http.PoliteClient(
        "testsrc",
        raw_dir=tmp_path,
        transport=httpx.MockTransport(lambda request: httpx.Response(429, content=b"no")),
        block_cooldowns=(0.05,),
    )
    try:
        blocked.get("https://example.invalid/y", "y.txt")
    except http.SourceBlocked:
        pass
    else:
        raise AssertionError("SourceBlocked 예외가 나와야 한다")
    assert not (tmp_path / "testsrc" / "y.txt").exists()


def test_404_placeholder_is_refetched_only_when_asked(tmp_path, monkeypatch):
    """404 자리표시("[]")는 refetch_empty를 켠 호출에서 다시 묻고, 자료가 올라오면 받는다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    state = {"ready": False, "calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if not state["ready"]:
            return httpx.Response(404, json={"detail": "No results found."})
        return httpx.Response(200, content=b'[{"lap":1}]')

    client = http.PoliteClient("testsrc", raw_dir=tmp_path, transport=httpx.MockTransport(handler))
    first = client.get("https://example.invalid/laps", "laps.json", empty_on_404=b"[]")
    assert first.content == b"[]" and not first.from_cache
    assert (tmp_path / "testsrc" / "laps.json").read_bytes() == b"[]"

    state["ready"] = True
    # 일괄 수집처럼 refetch_empty를 끄면 캐시된 자리표시를 그대로 쓴다.
    bulk = client.get("https://example.invalid/laps", "laps.json", empty_on_404=b"[]")
    assert bulk.content == b"[]" and bulk.from_cache and state["calls"] == 1

    later = client.get(
        "https://example.invalid/laps", "laps.json", empty_on_404=b"[]", refetch_empty=True
    )
    assert later.content == b'[{"lap":1}]' and not later.from_cache
    assert (tmp_path / "testsrc" / "laps.json").read_bytes() == b'[{"lap":1}]'

    # 실제 자료가 캐시되면 refetch_empty를 켜도 다시 묻지 않는다.
    again = client.get(
        "https://example.invalid/laps", "laps.json", empty_on_404=b"[]", refetch_empty=True
    )
    assert again.from_cache and state["calls"] == 2


def test_forced_refetch_that_gets_404_keeps_real_data(tmp_path, monkeypatch):
    """이미 받은 실제 자료는 강제로 다시 받다가 404가 와도 "[]"로 덮어쓰지 않는다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    path = tmp_path / "testsrc" / "laps.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'[{"lap":1}]')
    client = http.PoliteClient(
        "testsrc",
        raw_dir=tmp_path,
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
    )
    result = client.get("https://example.invalid/laps", "laps.json", force=True, empty_on_404=b"[]")
    assert result.content == b'[{"lap":1}]'
    assert path.read_bytes() == b'[{"lap":1}]'


def test_collect_round_refetches_endpoints_cached_as_empty(tmp_path, monkeypatch):
    """대회 주간에 자료가 올라오기 전 실행이 남긴 "[]"는 다음 실행에서 다시 받는다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "openf1", 0.0)
    published = {"ready": False}
    requested: list[str] = []
    sessions = [
        {
            "session_key": 9001,
            "meeting_key": 1,
            "session_name": "Qualifying",
            "date_start": "2025-12-06T14:00:00+00:00",
        },
        {
            "session_key": 9002,
            "meeting_key": 1,
            "session_name": "Race",
            "date_start": "2025-12-07T13:00:00+00:00",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        requested.append(endpoint)
        if endpoint == "sessions":
            return httpx.Response(200, json=sessions)
        if not published["ready"]:
            return httpx.Response(404, json={"detail": "No results found."})
        return httpx.Response(200, json=[{"endpoint": endpoint}])

    def make(source: str) -> http.PoliteClient:
        return http.PoliteClient(source, raw_dir=tmp_path, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(openf1, "PoliteClient", make)
    assert openf1.collect_round(2025, "2025-12-07") == [9001, 9002]
    laps = tmp_path / "openf1" / "2025" / "9002" / "laps.json"
    assert laps.read_bytes() == b"[]"

    published["ready"] = True
    requested.clear()
    assert openf1.collect_round(2025, "2025-12-07") == [9001, 9002]
    assert requested.count("laps") == 2 and requested.count("weather") == 2
    assert json.loads(laps.read_bytes()) == [{"endpoint": "laps"}]


def test_interrupted_cache_write_leaves_no_cache_file(tmp_path, monkeypatch):
    """캐시 쓰기가 중간에 실패하면 잘린 파일이 캐시로 남지 않고, 다음 호출이 다시 받는다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    body = b"%PDF-" + b"x" * 100_000
    client = http.PoliteClient(
        "testsrc",
        raw_dir=tmp_path,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)),
    )
    real_open = io.open

    class DiskFull:
        """바이너리 쓰기 파일을 감싸 3분의 1만 쓰고 디스크가 찼다고 알린다."""

        def __init__(self, f) -> None:
            self._f = f

        def write(self, data) -> int:
            self._f.write(bytes(data)[: len(data) // 3])
            self._f.flush()
            raise OSError(errno.ENOSPC, "No space left on device")

        def __getattr__(self, name):
            return getattr(self._f, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            self._f.close()

    def failing_open(file, mode="r", *args, **kwargs):
        f = real_open(file, mode, *args, **kwargs)
        return DiskFull(f) if "w" in mode and "b" in mode else f

    monkeypatch.setattr(io, "open", failing_open)
    with pytest.raises(OSError):
        client.get("https://example.invalid/doc.pdf", "doc.pdf")
    monkeypatch.setattr(io, "open", real_open)

    folder = tmp_path / "testsrc"
    assert not (folder / "doc.pdf").exists()
    assert [p.name for p in folder.iterdir()] == []  # 임시 파일도 남지 않는다
    again = client.get("https://example.invalid/doc.pdf", "doc.pdf")
    assert not again.from_cache
    assert again.sha256 == http.sha256_bytes(body)


def test_last_block_is_recorded_for_other_processes(tmp_path, monkeypatch):
    """마지막 거부 응답의 Retry-After도 잠금 파일에 적어, 다른 프로세스가 그만큼 쉬게 한다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    calls: list[float] = []

    def blocked(request: httpx.Request) -> httpx.Response:
        calls.append(time.time())
        return httpx.Response(429, headers={"cf-mitigated": "x", "Retry-After": "1"})

    def ok(request: httpx.Request) -> httpx.Response:
        calls.append(time.time())
        return httpx.Response(200, content=b"ok")

    a = http.PoliteClient(
        "testsrc", raw_dir=tmp_path, transport=httpx.MockTransport(blocked), block_cooldowns=()
    )
    with pytest.raises(http.SourceBlocked):
        a.get("https://example.invalid/a", "a.txt")
    state = json.loads((tmp_path / "_locks" / "testsrc.json").read_text())
    assert state["blocked_until"] >= calls[0] + 0.9

    # 기다리지 않기로 한 프로세스(CI)는 요청을 보내지 않고 바로 SourceBlocked로 끝난다.
    fast = http.PoliteClient(
        "testsrc", raw_dir=tmp_path, transport=httpx.MockTransport(ok), block_cooldowns=()
    )
    with pytest.raises(http.SourceBlocked):
        fast.get("https://example.invalid/b", "b.txt")
    assert len(calls) == 1

    # 기다리는 프로세스는 서버가 말한 시간이 지난 뒤에 보낸다.
    patient = http.PoliteClient(
        "testsrc", raw_dir=tmp_path, transport=httpx.MockTransport(ok), block_cooldowns=(0.01,)
    )
    assert patient.get("https://example.invalid/b", "b.txt").content == b"ok"
    assert calls[1] - calls[0] >= 0.9


def test_transport_error_is_logged(tmp_path, monkeypatch):
    """응답을 받지 못한 요청도 서버에 닿았을 수 있으므로 요청 기록에 남긴다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"ok")

    client = http.PoliteClient("testsrc", raw_dir=tmp_path, transport=httpx.MockTransport(handler))
    client.get("https://example.invalid/q", "q.txt", params={"session_key": 1})
    with (tmp_path / "_logs" / "requests-testsrc.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(calls) == 2
    assert rows[0]["status"] == "error:ReadTimeout"
    assert rows[0]["url"] == "https://example.invalid/q?session_key=1"
    assert rows[1]["status"] == "200"


def test_unreachable_source_raises_source_unavailable(tmp_path, monkeypatch):
    """재시도를 다 써도 서버에 닿지 못하면 SourceUnavailable이다. 5xx는 전과 같이 RuntimeError다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    down = http.PoliteClient(
        "testsrc", raw_dir=tmp_path, transport=httpx.MockTransport(refused), max_retries=2
    )
    with pytest.raises(http.SourceUnavailable) as caught:
        down.get("https://example.invalid/x", "x.txt")
    assert isinstance(caught.value, RuntimeError)  # RuntimeError를 잡던 곳은 그대로 잡는다
    assert isinstance(caught.value.__cause__, httpx.ConnectError)

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"")

    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)
    erroring = http.PoliteClient(
        "testsrc", raw_dir=tmp_path, transport=httpx.MockTransport(broken), max_retries=2
    )
    with pytest.raises(RuntimeError) as caught:
        erroring.get("https://example.invalid/y", "y.txt")
    assert not isinstance(caught.value, http.SourceUnavailable)


def test_offline_mode_uses_cache_and_sends_nothing(tmp_path, monkeypatch):
    """PIPELINE_OFFLINE=1이면 캐시는 그대로 쓰고, 캐시에 없는 자료는 요청하지 않고 멈춘다.

    transport를 준 클라이언트(테스트의 가짜 서버)는 네트워크가 아니므로 막지 않는다.
    """
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    monkeypatch.delenv("PIPELINE_OFFLINE", raising=False)
    calls: list[float] = []
    client = make_client(tmp_path, calls)
    client.get("https://example.invalid/a", "a.txt")
    real = http.PoliteClient("testsrc", raw_dir=tmp_path)
    monkeypatch.setattr(
        real._client, "get", lambda *a, **k: pytest.fail("PIPELINE_OFFLINE=1인데 요청을 보냈다")
    )
    monkeypatch.setenv("PIPELINE_OFFLINE", "1")
    assert real.get("https://example.invalid/a", "a.txt").from_cache
    with pytest.raises(http.SourceUnavailable):
        real.get("https://example.invalid/b", "b.txt")
    assert not (tmp_path / "testsrc" / "b.txt").exists()
    assert client.get("https://example.invalid/c", "c.txt").content == b"ok"  # 가짜 서버
    assert len(calls) == 2


class FakeClock:
    """time 모듈 대신 쓰는 가짜 시계. sleep은 시각만 앞으로 옮긴다."""

    def __init__(self, now: float) -> None:
        self.now = now

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


def test_hourly_cap_holds_when_window_is_overfull(tmp_path, monkeypatch):
    """상한을 낮춘 뒤처럼 창 안의 요청이 상한보다 많아도, 기다린 뒤에는 상한을 넘지 않는다."""
    clock = FakeClock(1_000_000.0)
    monkeypatch.setattr(http, "time", clock)
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    monkeypatch.setitem(http.MAX_REQUESTS_PER_HOUR, "testsrc", 5)
    lock = tmp_path / "_locks" / "testsrc.json"
    lock.parent.mkdir(parents=True)
    recent = [clock.now - 3000 + 10 * i for i in range(8)]
    lock.write_text(json.dumps({"last": clock.now - 100, "recent": recent}))

    client = http.PoliteClient("testsrc", raw_dir=tmp_path)
    for _ in range(3):
        client._wait_turn()
        state = json.loads(lock.read_text())
        in_window = [t for t in state["recent"] if clock.now - t < 3600]
        assert len(in_window) <= 5, in_window


def test_blocked_source_in_fixture_is_skipped(pytester):
    """픽스처에서 원문 서버가 요청을 막아도 network 테스트는 오류가 아니라 건너뜀이다."""
    pytester.makeini(
        """
        [pytest]
        markers =
            network: 원문을 내려받아야 하는 테스트
        """
    )
    pytester.makeconftest("from pipeline.quality.conftest import *  # noqa: F403")
    pytester.makepyfile(
        """
        import pytest

        from pipeline.http import SourceBlocked

        pytestmark = pytest.mark.network


        @pytest.fixture(scope="module")
        def replayed():
            raise SourceBlocked("jolpica: 429")


        def test_fixture_one(replayed):
            pass


        def test_fixture_two(replayed):
            pass


        def test_body():
            raise SourceBlocked("jolpica: 429")


        @pytest.mark.parametrize("n", [1])
        def test_other_error_still_fails(n):
            raise ValueError("데이터가 틀렸다")
        """
    )
    result = pytester.runpytest("-p", "no:cacheprovider")
    result.assert_outcomes(skipped=3, failed=1)


def test_unreachable_source_is_skipped(pytester):
    """네트워크가 막혀 서버에 닿지 못한 network 테스트도 건너뜀이다. 감싼 예외도 알아본다."""
    pytester.makeini(
        """
        [pytest]
        markers =
            network: 원문을 내려받아야 하는 테스트
        """
    )
    pytester.makeconftest("from pipeline.quality.conftest import *  # noqa: F403")
    pytester.makepyfile(
        """
        import httpx
        import pytest

        from pipeline.http import SourceUnavailable


        @pytest.fixture(scope="module")
        def downloaded():
            raise SourceUnavailable("fia: 서버에 닿지 못함")


        @pytest.mark.network
        def test_fixture(downloaded):
            pass


        @pytest.mark.network
        def test_raw_transport_error():
            raise httpx.ConnectError("connection refused")


        @pytest.mark.network
        def test_wrapped():
            try:
                raise SourceUnavailable("jolpica: 서버에 닿지 못함")
            except SourceUnavailable as exc:
                raise RuntimeError("적재 실패") from exc


        def test_not_network_still_fails():
            raise SourceUnavailable("network 표시가 없는 테스트는 실패다")
        """
    )
    result = pytester.runpytest("-p", "no:cacheprovider")
    result.assert_outcomes(skipped=3, failed=1)


def test_ci_network_tests_do_not_wait_out_blocks():
    """ci.yml의 테스트 단계는 거부 응답에 몇 시간씩 쉬지 않고 바로 실패하게 설정한다."""
    text = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    step = re.search(r"- run: uv run pytest\n((?:\s{8,}.*\n)*)", text)
    assert step, "ci.yml에 uv run pytest 단계가 없다"
    assert re.search(r"env:\s*\n\s+PIPELINE_BLOCK_COOLDOWNS: ''", step.group(1)), step.group(1)
