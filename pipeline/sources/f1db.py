"""F1DB 수집기 (GitHub 릴리스의 CSV 묶음, CC BY 4.0).

https://github.com/f1db/f1db
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from pipeline import manifest
from pipeline.config import RAW_DIR
from pipeline.http import PoliteClient, utc_now_iso
from pipeline.sources.jolpica import DATASET_FIELDS, DATASET_MANIFEST

# 릴리스를 고정한다. 올릴 때는 이 값과 manifest를 함께 바꾼다.
RELEASE_TAG = "v2026.20.0"
ASSET = "f1db-csv.zip"


def download_release(tag: str = RELEASE_TAG, *, force: bool = False) -> Path:
    """릴리스 CSV 묶음을 받아 풀고, 풀린 폴더 경로를 돌려준다."""
    url = f"https://github.com/f1db/f1db/releases/download/{tag}/{ASSET}"
    with PoliteClient("f1db") as client:
        result = client.get(url, f"{tag}/{ASSET}", force=force)
    out_dir = RAW_DIR / "f1db" / tag / "csv"
    if not out_dir.exists():
        with zipfile.ZipFile(result.path) as zf:
            zf.extractall(out_dir)
    manifest.upsert_rows(
        DATASET_MANIFEST,
        [
            {
                "source": "f1db",
                "name": ASSET,
                "version": tag,
                "url": url,
                "sha256": result.sha256,
                "bytes": len(result.content),
                "upstream_published_at": "",
                "fetched_at": result.fetched_at or utc_now_iso(),
            }
        ],
        key=["source", "name"],
        fieldnames=DATASET_FIELDS,
    )
    return out_dir
