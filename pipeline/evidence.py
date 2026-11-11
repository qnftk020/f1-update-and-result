"""근거 인용문 대조 도구.

문서에 적는 사실에는 출처 URL과 그 페이지에 실제로 있는 짧은 인용문을 함께 남긴다. 이 모듈은
페이지를 받아(캐시) 인용문이 정말 들어 있는지 확인한다. 본문 전체를 저장소에 싣지는 않는다.

실행: uv run python -m pipeline.evidence <url> "<quote>"
"""

from __future__ import annotations

import hashlib
import html
import re
import sys
from urllib.parse import urlparse

import httpx

from pipeline.http import PoliteClient, SourceBlocked


class EvidenceUnavailable(RuntimeError):
    """페이지를 받지 못해 인용문을 확인할 수 없다(차단, 삭제 등)."""


FIA_HOSTS = {
    "www.fia.com": "fia",
    "fia.com": "fia",
    "argent.fia.com": "fia_argent",
    "historicdb.fia.com": "fia_historic",
}


def source_for(url: str) -> str:
    """URL의 호스트에 맞는 요청 규칙 이름. FIA 호스트가 아니면 일반 규칙을 쓴다."""
    return FIA_HOSTS.get(urlparse(url).netloc.lower(), "web")


def page_text(raw: str) -> str:
    """HTML에서 글만 남긴다. 각주 번호([12])는 지운다."""
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"\[\s*(?:\d+|note \d+|[a-z])\s*\]", "", text)
    return re.sub(r"\s+", " ", text)


def normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[‐-―]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"\s*([,.\-:;()])\s*", r"\1", text).strip()


def fetch_text(url: str, *, force: bool = False) -> str:
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    try:
        with PoliteClient(source_for(url)) as client:
            raw = client.get(url, f"evidence/{key}.html", force=force).content
    except httpx.HTTPStatusError as exc:
        raise EvidenceUnavailable(f"{exc.response.status_code} {url}") from exc
    except SourceBlocked as exc:
        raise EvidenceUnavailable(str(exc)) from exc
    return page_text(raw.decode("utf-8", "ignore"))


def quote_found(url: str, quote: str, *, force: bool = False) -> bool:
    """quote가 url의 페이지 글에 그대로 들어 있으면 True."""
    return normalise(quote) in normalise(fetch_text(url, force=force))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit('usage: python -m pipeline.evidence <url> "<quote>"')
    try:
        found = quote_found(sys.argv[1], sys.argv[2])
    except EvidenceUnavailable as exc:
        print(f"UNAVAILABLE {exc}")
        raise SystemExit(2) from exc
    print("OK" if found else "FAIL")
    raise SystemExit(0 if found else 1)
