"""Jolpica-F1 수집기.

- 초기 적재: 무료(비상업) 등급의 지연 덤프(CSV, 업로드 14일 뒤 공개)를 받는다.
- 증분 갱신과 대조: Ergast 호환 API를 쓴다. 모든 응답을 캐시한다.

이용 조건: https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md
요청 제한: https://github.com/jolpica/jolpica-f1/blob/main/docs/rate_limits.md
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from pipeline import manifest
from pipeline.config import RAW_DIR
from pipeline.http import PoliteClient, sha256_bytes, utc_now_iso

API_BASE = "https://api.jolpi.ca/ergast/f1"
DUMP_INDEX_URL = "https://api.jolpi.ca/data/dumps/download/"
DATASET_MANIFEST = "datasets.csv"
DATASET_FIELDS = [
    "source", "name", "version", "url", "sha256", "bytes", "upstream_published_at", "fetched_at",
]  # fmt: skip


def download_dump(*, force: bool = False) -> Path:
    """지연 덤프(CSV zip)를 받아 풀고, 풀린 폴더 경로를 돌려준다."""
    with PoliteClient("jolpica") as client:
        index = json.loads(
            client.get(DUMP_INDEX_URL, "dump/index.json", force=True).content.decode("utf-8")
        )
        info = index["delayed_dumps"]["csv"]
        file_hash = info["file_hash"]
        result = client.get(info["download_url"], f"dump/{file_hash}.zip", force=force)
    if sha256_bytes(result.content) != file_hash:
        raise RuntimeError("Jolpica 덤프의 sha256이 목록의 file_hash와 다르다")
    out_dir = RAW_DIR / "jolpica" / "dump" / file_hash
    if not out_dir.exists():
        with zipfile.ZipFile(result.path) as zf:
            zf.extractall(out_dir)
    manifest.upsert_rows(
        DATASET_MANIFEST,
        [
            {
                "source": "jolpica",
                "name": "delayed-dump-csv",
                "version": info["uploaded_at"],
                "url": info["download_url"],
                "sha256": file_hash,
                "bytes": info["file_size"],
                "upstream_published_at": info["uploaded_at"],
                "fetched_at": result.fetched_at or utc_now_iso(),
            }
        ],
        key=["source", "name"],
        fieldnames=DATASET_FIELDS,
    )
    return out_dir


def fetch_api(path: str, *, limit: int = 100, offset: int = 0, force: bool = False) -> dict:
    """Ergast 호환 API 한 페이지를 받는다. 예: fetch_api("2025/24/results")."""
    path = path.strip("/")
    cache = f"api/{path}/limit{limit}-offset{offset}.json"
    with PoliteClient("jolpica") as client:
        result = client.get(
            f"{API_BASE}/{path}/", cache, params={"limit": limit, "offset": offset}, force=force
        )
    return json.loads(result.content.decode("utf-8"))["MRData"]


def fetch_api_all(path: str, table_key: str, list_key: str, *, force: bool = False) -> list[dict]:
    """페이지를 끝까지 넘기며 목록을 모은다."""
    items: list[dict] = []
    offset = 0
    while True:
        data = fetch_api(path, limit=100, offset=offset, force=force)
        page = data[table_key][list_key]
        items.extend(page)
        offset += 100
        if offset >= int(data["total"]) or not page:
            return items
