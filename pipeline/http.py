"""예의 있는 HTTP 클라이언트.

- 데이터원별 최소 요청 간격과 시간당 요청 수를 지킨다.
- 모든 응답을 data/raw/ 아래에 캐시한다. 캐시가 있으면 네트워크 요청을 하지 않는다.
- 실제로 나간 요청은 data/raw/_logs/requests-<source>.csv 에 남긴다(요청 제한 준수 증빙).
"""

from __future__ import annotations

import csv
import hashlib
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pipeline.config import MAX_REQUESTS_PER_HOUR, MIN_INTERVAL_SECONDS, RAW_DIR, USER_AGENT


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    ) -> None:
        self.source = source
        self.min_interval = MIN_INTERVAL_SECONDS[source]
        self.max_per_hour = MAX_REQUESTS_PER_HOUR.get(source)
        self.raw_dir = (raw_dir or RAW_DIR) / source
        self.log_path = (raw_dir or RAW_DIR) / "_logs" / f"requests-{source}.csv"
        self.max_retries = max_retries
        self._last_request = 0.0
        self._recent: deque[float] = deque()
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait_turn(self) -> None:
        now = time.monotonic()
        if self.max_per_hour is not None:
            while self._recent and now - self._recent[0] > 3600:
                self._recent.popleft()
            if len(self._recent) >= self.max_per_hour:
                time.sleep(3600 - (now - self._recent[0]) + 1)
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def _log(self, url: str, status: int, size: int) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["requested_at", "url", "status", "bytes"])
            w.writerow([utc_now_iso(), url, status, size])

    def get(
        self,
        url: str,
        cache_path: str,
        *,
        params: dict | None = None,
        force: bool = False,
        empty_on_404: bytes | None = None,
    ) -> FetchResult:
        """url을 받아 data/raw/<source>/<cache_path>에 저장한다. 캐시가 있으면 그대로 쓴다."""
        path = self.raw_dir / cache_path
        if path.exists() and not force:
            content = path.read_bytes()
            return FetchResult(url, path, content, sha256_bytes(content), True, None)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._wait_turn()
            self._last_request = time.monotonic()
            self._recent.append(self._last_request)
            try:
                resp = self._client.get(url, params=params)
            except httpx.HTTPError as exc:  # 네트워크 오류는 간격을 늘려 재시도
                last_error = exc
                time.sleep(self.min_interval * (2**attempt))
                continue
            self._log(str(resp.request.url), resp.status_code, len(resp.content))
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.0
                time.sleep(max(delay, self.min_interval * (2 ** (attempt + 1))))
                last_error = httpx.HTTPStatusError(
                    f"{resp.status_code} for {url}", request=resp.request, response=resp
                )
                continue
            if resp.status_code == 404 and empty_on_404 is not None:
                content = empty_on_404  # "결과 없음"을 404로 알리는 API용
            else:
                resp.raise_for_status()
                content = resp.content
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return FetchResult(url, path, content, sha256_bytes(content), False, utc_now_iso())
        raise RuntimeError(f"요청 실패({self.source}): {url}") from last_error
