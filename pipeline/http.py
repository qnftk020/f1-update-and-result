"""예의 있는 HTTP 클라이언트.

- 데이터원별 최소 요청 간격과 시간당 요청 수를 지킨다. 간격은 data/raw/_locks/ 의 잠금 파일로
  세므로 여러 프로세스가 같은 데이터원을 동시에 써도 지켜진다.
- 모든 응답을 data/raw/ 아래에 캐시한다. 캐시가 있으면 네트워크 요청을 하지 않는다. 캐시 파일은
  임시 파일에 다 쓴 뒤 이름을 바꿔 만들므로, 중간에 끊긴 쓰기가 캐시로 남지 않는다.
- 실제로 나간 요청은 data/raw/_logs/requests-<source>.csv 에 남긴다(요청 제한 준수 증빙). 응답을
  받지 못한 요청(시간 초과, 연결 끊김)도 상태 열에 error:<예외 이름>으로 남긴다.
"""

from __future__ import annotations

import contextlib
import csv
import fcntl
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pipeline.config import MAX_REQUESTS_PER_HOUR, MIN_INTERVAL_SECONDS, RAW_DIR, USER_AGENT

# 서버가 요청을 막았을 때(429, Cloudflare 확인 화면) 쉬는 시간(초). 우회하지 않고 기다린다.
# 환경 변수 PIPELINE_BLOCK_COOLDOWNS("600,1200" 꼴)로 바꿀 수 있다. 빈 값이면 기다리지 않고
# 바로 실패한다(CI처럼 오래 기다릴 수 없는 곳에서 쓴다).
BLOCK_COOLDOWNS = tuple(
    float(x)
    for x in os.environ.get("PIPELINE_BLOCK_COOLDOWNS", "1800,3600,7200").split(",")
    if x.strip()
)


class SourceBlocked(RuntimeError):
    """서버가 요청을 거부했다. 기다린 뒤에도 풀리지 않으면 사람에게 알린다."""


class SourceUnavailable(RuntimeError):
    """서버에 닿지 못했다(연결 실패, 시간 초과 같은 전송 오류). 서버가 거부한 것과는 다르다.

    재시도를 다 쓰고도 응답을 받지 못했거나, PIPELINE_OFFLINE=1이라 캐시에 없는 자료를 요청하지
    않았을 때 낸다. RuntimeError의 하위 클래스이므로 RuntimeError를 잡던 곳은 그대로 동작한다.
    """


def offline() -> bool:
    """PIPELINE_OFFLINE=1이면 캐시만 쓰고 실제 네트워크 요청을 보내지 않는다."""
    return os.environ.get("PIPELINE_OFFLINE") == "1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_atomic(path: Path, content: bytes) -> None:
    """content를 path에 원자적으로 쓴다.

    같은 폴더의 고유한 임시 파일에 다 쓰고 디스크에 내린 뒤 os.replace로 이름을 바꾼다. 그래서 다른
    프로세스는 파일이 없거나 완전한 파일만 보며, 쓰기가 중간에 실패하면 이전 파일이 그대로 남는다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FetchResult:
    url: str
    path: Path
    content: bytes
    sha256: str
    from_cache: bool
    fetched_at: str | None  # 캐시에서 읽었으면 None


class PoliteClient:
    """데이터원 하나에 대한 순차 요청 클라이언트."""

    def __init__(
        self,
        source: str,
        *,
        user_agent: str = USER_AGENT,
        raw_dir: Path | None = None,
        timeout: float = 60.0,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
        block_cooldowns: tuple[float, ...] = BLOCK_COOLDOWNS,
    ) -> None:
        self.source = source
        self.min_interval = MIN_INTERVAL_SECONDS[source]
        self.max_per_hour = MAX_REQUESTS_PER_HOUR.get(source)
        self.raw_dir = (raw_dir or RAW_DIR) / source
        self.log_path = (raw_dir or RAW_DIR) / "_logs" / f"requests-{source}.csv"
        self.lock_path = (raw_dir or RAW_DIR) / "_locks" / f"{source}.json"
        self.max_retries = max_retries
        self.block_cooldowns = block_cooldowns
        # 실제 네트워크로 나가는 클라이언트인가. 테스트처럼 transport를 주면 네트워크가 아니므로
        # PIPELINE_OFFLINE=1이어도 막지 않는다.
        self.uses_network = transport is None
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait_turn(self) -> None:
        """이 데이터원으로 나가는 다음 요청 차례를 기다린다.

        마지막 요청 시각을 잠금 파일에 적어 두고, 잠금을 쥔 채로 기다린다. 그래서 프로세스가
        여러 개여도 요청 시작 시각 사이가 최소 간격보다 좁아지지 않는다.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read().strip()
                state = json.loads(raw) if raw else {}
                last = float(state.get("last", 0.0))
                recent = [float(t) for t in state.get("recent", [])]
                blocked = float(state.get("blocked_until", 0.0)) - time.time()
                if blocked > 0:  # 다른 프로세스가 거부 응답을 받았다. 함께 쉰다.
                    if not self.block_cooldowns:
                        # 기다리지 않기로 한 곳(CI)에서는 요청을 보내지 않고 바로 실패한다.
                        raise SourceBlocked(
                            f"{self.source}: 앞선 거부 응답으로 {blocked:.0f}초 더 쉬어야 한다"
                        )
                    time.sleep(blocked)
                if self.max_per_hour is not None:
                    recent = [t for t in recent if time.time() - t < 3600]
                    if len(recent) >= self.max_per_hour:
                        # 상한을 낮춘 뒤처럼 창 안의 요청이 상한보다 많을 수 있다. 이번 요청까지
                        # 넣어도 상한을 넘지 않도록, 덜어 낼 요청 가운데 가장 늦은 것이 창을 벗어날
                        # 때까지 기다린다.
                        last_to_drop = recent[len(recent) - self.max_per_hour]
                        time.sleep(max(0.0, 3600 - (time.time() - last_to_drop)) + 1)
                        recent = [t for t in recent if time.time() - t < 3600]
                wait = self.min_interval - (time.time() - last)
                if wait > 0:
                    time.sleep(wait)
                started = time.time()
                state = {"last": started}
                if self.max_per_hour is not None:
                    state["recent"] = [*recent, started]
                f.seek(0)
                f.truncate()
                f.write(json.dumps(state))
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _mark_blocked(self, seconds: float) -> None:
        """거부 응답을 받았음을 잠금 파일에 적어 같은 데이터원을 쓰는 모든 프로세스를 쉬게 한다."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read().strip()
                state = json.loads(raw) if raw else {}
                state["blocked_until"] = max(
                    float(state.get("blocked_until", 0.0)), time.time() + seconds
                )
                f.seek(0)
                f.truncate()
                f.write(json.dumps(state))
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _log(self, url: str, status: int | str, size: int, started: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["requested_at", "url", "status", "bytes"])
            w.writerow([started, url, status, size])

    def get(
        self,
        url: str,
        cache_path: str,
        *,
        params: dict | None = None,
        force: bool = False,
        empty_on_404: bytes | None = None,
        refetch_empty: bool = False,
    ) -> FetchResult:
        """url을 받아 data/raw/<source>/<cache_path>에 저장한다. 캐시가 있으면 그대로 쓴다.

        empty_on_404를 주면 404를 "결과 없음"으로 보고 그 값을 캐시에 적어 돌려준다. 파일이 있어야
        읽는 쪽이 엔드포인트를 빠짐없이 다룰 수 있기 때문이다. 다만 아직 올라오지 않은 자료도 404로
        오므로, refetch_empty를 켜면 캐시 내용이 empty_on_404와 같을 때 캐시를 쓰지 않고 다시
        묻는다. 이미 받은 실제 자료가 있는데 다시 받다가 404가 오면 그 자료를 덮어쓰지 않고 남긴다.
        """
        path = self.raw_dir / cache_path
        if path.exists() and not force:
            content = path.read_bytes()
            stale = (
                refetch_empty
                and empty_on_404 is not None
                and content.strip() == empty_on_404.strip()
            )
            if not stale:
                return FetchResult(url, path, content, sha256_bytes(content), True, None)
        if offline() and self.uses_network:
            raise SourceUnavailable(f"{self.source}: PIPELINE_OFFLINE=1이라 요청하지 않는다: {url}")

        last_error: Exception | None = None
        blocks = 0
        attempt = 0
        while attempt < self.max_retries:
            self._wait_turn()
            started = utc_now_iso()  # 로그에는 요청을 보낸 시각을 남긴다
            try:
                resp = self._client.get(url, params=params)
            except httpx.HTTPError as exc:  # 네트워크 오류는 간격을 늘려 재시도
                # 서버에 닿았을 수 있는 요청이므로 응답이 없어도 기록한다.
                sent = str(self._client.build_request("GET", url, params=params).url)
                self._log(sent, f"error:{type(exc).__name__}", 0, started)
                last_error = exc
                time.sleep(self.min_interval * (2**attempt))
                attempt += 1
                continue
            self._log(str(resp.request.url), resp.status_code, len(resp.content), started)
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.0
            if resp.status_code == 429 or "cf-mitigated" in resp.headers:
                # 요청 제한이나 봇 확인 화면이다. 우회하지 않는다. 오래 쉬고 다시 묻는다.
                if blocks >= len(self.block_cooldowns):
                    # 멈추기 전에도 쉬는 시간을 적어 두어, 같은 데이터원을 쓰는 다른 프로세스가
                    # 서버가 요청한 시간(Retry-After)을 지키게 한다.
                    rest = max(delay, self.block_cooldowns[-1] if self.block_cooldowns else 0.0)
                    if rest > 0:
                        self._mark_blocked(rest)
                    raise SourceBlocked(
                        f"{self.source}: 서버가 요청을 계속 거부한다({resp.status_code}): {url}"
                    )
                self._mark_blocked(max(delay, self.block_cooldowns[blocks]))
                blocks += 1
                continue
            if resp.status_code in (500, 502, 503, 504):
                time.sleep(max(delay, self.min_interval * (2 ** (attempt + 1))))
                last_error = httpx.HTTPStatusError(
                    f"{resp.status_code} for {url}", request=resp.request, response=resp
                )
                attempt += 1
                continue
            if resp.status_code == 404 and empty_on_404 is not None:
                content = empty_on_404  # "결과 없음"을 404로 알리는 API용
                if path.exists():
                    kept = path.read_bytes()
                    if kept.strip() != empty_on_404.strip():  # 받은 실제 자료는 404로 지우지 않는다
                        return FetchResult(url, path, kept, sha256_bytes(kept), True, None)
            else:
                resp.raise_for_status()
                content = resp.content
            write_atomic(path, content)
            return FetchResult(url, path, content, sha256_bytes(content), False, utc_now_iso())
        if isinstance(last_error, httpx.TransportError):
            # 응답을 한 번도 받지 못했다. 네트워크가 막힌 환경과 서버 오류(5xx)를 구분한다.
            message = f"요청 실패({self.source}, 서버에 닿지 못함): {url}"
            raise SourceUnavailable(message) from last_error
        raise RuntimeError(f"요청 실패({self.source}): {url}") from last_error


def main(argv: list[str]) -> int:
    """명령줄에서 한 건을 예의 있게 받는다. 결과를 JSON 한 줄로 출력한다.

    uv run python -m pipeline.http get <source> <url> <cache_path> [--force]
    """
    if len(argv) < 4 or argv[0] != "get":
        print("usage: python -m pipeline.http get <source> <url> <cache_path> [--force]")
        return 64
    _, source, url, cache_path, *flags = argv
    out: dict[str, object] = {"source": source, "url": url}
    try:
        with PoliteClient(source) as client:
            result = client.get(url, cache_path, force="--force" in flags)
        out.update(
            ok=True,
            path=str(result.path),
            bytes=len(result.content),
            sha256=result.sha256,
            from_cache=result.from_cache,
            fetched_at=result.fetched_at,
            head=result.content[:8].decode("latin-1"),
        )
    except httpx.HTTPStatusError as exc:
        out.update(ok=False, status=exc.response.status_code)
    except SourceBlocked as exc:
        out.update(ok=False, blocked=True, error=str(exc))
    except SourceUnavailable as exc:
        out.update(ok=False, unavailable=True, error=str(exc))
    except RuntimeError as exc:
        out.update(ok=False, error=str(exc))
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
