"""사람 검수 결정을 읽는다.

자동 파싱이 "검수 대기"로 남긴 문서를 사이트 운영자가 원문과 대조해 내린 결정은
`data/curated/review/human_review.csv`에 한 줄씩 적는다. 열은 아래와 같다.

    id, reviewed_at, doc_type, season, round, source_url, page, target, decision, value, note

파서는 `decisions(doc_type)`로 자기 문서 유형의 행만 받아, 원문 URL(source_url)과 쪽, 대상이 정확히
맞는 곳에만 결정을 적용한다. 원문 값은 고쳐 쓰지 않고 남기며, 적용한 곳에는 `label(row)`로 시작하는
메모를 붙인다. 적용할 곳을 찾지 못한 결정은 파서가 문제로 남긴다(조용히 넘어가지 않는다).
"""

from __future__ import annotations

import csv
from pathlib import Path

from pipeline.config import CURATED_DIR

REVIEW_PATH = CURATED_DIR / "review" / "human_review.csv"
FIELDS = [
    "id", "reviewed_at", "doc_type", "season", "round", "source_url", "page", "target",
    "decision", "value", "note",
]  # fmt: skip


def decisions(doc_type: str, path: Path | None = None) -> list[dict[str, str]]:
    """doc_type의 사람 검수 결정 행. 값은 CSV의 문자열 그대로이고, 파일이 없으면 빈 목록이다."""
    path = path or REVIEW_PATH
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [
            {name: (row.get(name) or "").strip() for name in FIELDS}
            for row in csv.DictReader(f)
            if (row.get("doc_type") or "").strip() == doc_type
        ]


def label(row: dict[str, str]) -> str:
    """적용한 곳에 붙이는 메모의 머리: "사람 검수(2026-11-13, i02)"."""
    return f"사람 검수({row['reviewed_at']}, {row['id']})"


def pages(row: dict[str, str]) -> set[int]:
    """결정이 가리키는 쪽 번호. 여러 쪽은 ";"로 적고, 비어 있으면 빈 집합(쪽을 가리지 않음)이다."""
    return {int(p) for p in row["page"].split(";") if p.strip().isdigit()}


def unapplied(row: dict[str, str]) -> str:
    """적용할 곳을 찾지 못한 결정을 문서의 문제로 적는 문구."""
    where = f"{row['page']}쪽" if row["page"] else "쪽 지정 없음"
    return (
        f"{label(row)}: 결정({row['decision']}, {row['target']}, {where})을 적용할 곳을 찾지 못했다"
    )
