"""HTTP 클라이언트의 요청 간격 규칙 테스트."""

from __future__ import annotations

import time

import httpx

from pipeline import http


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
    import json

    state = json.loads((tmp_path / "_locks" / "testsrc.json").read_text())
    assert len(state["recent"]) == 4


def test_block_response_waits_and_is_not_bypassed(tmp_path, monkeypatch):
    """429나 Cloudflare 확인 화면을 받으면 정해진 시간만큼 쉬고, 계속 막히면 멈춘다."""
    monkeypatch.setitem(http.MIN_INTERVAL_SECONDS, "testsrc", 0.0)
    calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(time.time())
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
    assert not (tmp_path / "testsrc" / "wait.txt").exists()

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
