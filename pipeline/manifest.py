"""data/manifests 아래 CSV manifest를 읽고 쓰는 도우미.

manifest는 "어떤 원문을 언제 받았고 sha256이 무엇인지"를 남기는 커밋 대상 기록이다.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pipeline.config import MANIFEST_DIR


def read_rows(name: str) -> list[dict[str, str]]:
    path = MANIFEST_DIR / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(name: str, rows: list[dict], fieldnames: list[str]) -> Path:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = MANIFEST_DIR / name
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})
    return path


def upsert_rows(name: str, new_rows: list[dict], key: list[str], fieldnames: list[str]) -> Path:
    """key 열이 같은 행은 새 행으로 바꾸고, 없으면 추가한다. key 순으로 정렬해 저장한다."""
    merged = {tuple(r[k] for k in key): r for r in read_rows(name)}
    for row in new_rows:
        merged[tuple(str(row[k]) for k in key)] = {k: str(v) for k, v in row.items()}
    ordered = [merged[k] for k in sorted(merged)]
    return write_rows(name, ordered, fieldnames)
