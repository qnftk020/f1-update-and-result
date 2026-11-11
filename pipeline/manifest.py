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


FAILURES = "parse_failures.csv"
FAILURE_FIELDS = ["season", "round", "event", "doc_type", "url", "problems", "recorded_at"]


def _failure_order(row: dict) -> tuple:
    """실패 목록의 정렬 기준: 문서 유형, 시즌, 라운드, URL.

    라운드가 없는 행은 시즌 안에서 앞에 둔다.
    """

    def number(value: object) -> int:
        text = str(value if value is not None else "").strip()
        return int(text) if text.lstrip("-").isdigit() else -1

    return row["doc_type"], number(row["season"]), number(row["round"]), row["url"]


def replace_failures(doc_types: set[str] | list[str], failures: list[dict]) -> Path:
    """parse_failures.csv에서 doc_types의 행만 새 실패 목록으로 갈아 끼운다.

    다른 파서의 행은 그대로 둔다. 이미 적힌 실패는 처음 기록한 날짜(recorded_at)를 유지한다. 어느
    파서가 마지막에 돌았든 같은 내용이면 같은 파일이 되도록 (doc_type, season, round, url) 순으로
    정렬해 쓴다.
    """
    ours = set(doc_types)
    existing = read_rows(FAILURES)
    first_seen = {r["url"]: r["recorded_at"] for r in existing if r["doc_type"] in ours}
    mine = [
        {**f, "recorded_at": first_seen.get(f["url"], f["recorded_at"])}
        for f in failures
        if f["doc_type"] in ours
    ]
    others = [r for r in existing if r["doc_type"] not in ours]
    return write_rows(FAILURES, sorted(others + mine, key=_failure_order), FAILURE_FIELDS)


def upsert_rows(name: str, new_rows: list[dict], key: list[str], fieldnames: list[str]) -> Path:
    """key 열이 같은 행은 새 행으로 바꾸고, 없으면 추가한다. key 순으로 정렬해 저장한다."""
    merged = {tuple(r[k] for k in key): r for r in read_rows(name)}
    for row in new_rows:
        merged[tuple(str(row[k]) for k in key)] = {k: str(v) for k, v in row.items()}
    ordered = [merged[k] for k in sorted(merged)]
    return write_rows(name, ordered, fieldnames)
