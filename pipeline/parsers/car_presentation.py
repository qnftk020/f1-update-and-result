"""Car Presentation Submissions PDF 파서. (T5)

문서는 팀마다 한 쪽씩이고, 업데이트가 있는 팀은 다섯 열짜리 표를 낸다.

    번호 | Updated component | Primary reason for update | Geometric differences | Description

표의 테두리가 얇은 사각형으로 그려져 있어 격자 좌표를 그대로 읽을 수 있다. 설명 칸은 여러 행에
걸쳐 병합되기도 한다. 병합된 칸의 글은 걸친 모든 행에 같은 값으로 넣고
`description_shared`로 표시한다.

- 문서마다 추출 행 수, 팀 수, "No updates submitted" 팀 수를 기록한다.
- 팀 수가 그리드 팀 수와 다르면 실패로 처리한다. 추측으로 채우지 않는다.

실행: uv run python -m pipeline.parsers.car_presentation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

GRID_TEAMS = 10
COLUMNS = ["item_no", "updated_component", "primary_reason", "geometric_differences", "description"]
NO_UPDATES = re.compile(r"no\s+updates?\s+(were\s+)?submitted", re.I)
TITLE_LINE = re.compile(r"^(car presentation|pre-event automobile display)\b", re.I)
EDGE_TOLERANCE = 2.5
MIN_CELL_HEIGHT = 8.0

# 원문 분류의 앞부분으로 상위 범주를 정한다. 원문 분류는 그대로 따로 저장한다.
REASON_CATEGORIES = [
    ("circuit_specific", re.compile(r"^circuit[\s-]*specific", re.I)),
    ("performance", re.compile(r"^performance", re.I)),
    ("reliability", re.compile(r"^reliability", re.I)),
]

# 팀 표기에서 constructor_id를 정하는 규칙. 위에서부터 먼저 맞는 것을 쓴다.
TEAM_RULES: list[tuple[re.Pattern[str], str | dict[int, str]]] = [
    (re.compile(r"racing bulls|visa cash app|\brb\b", re.I), "rb"),
    (re.compile(r"alphatauri", re.I), "alphatauri"),
    (re.compile(r"red bull", re.I), "red_bull"),
    (re.compile(r"aston martin", re.I), "aston_martin"),
    (re.compile(r"mclaren", re.I), "mclaren"),
    (re.compile(r"williams", re.I), "williams"),
    (re.compile(r"alpine", re.I), "alpine"),
    (re.compile(r"haas", re.I), "haas"),
    (re.compile(r"alfa romeo", re.I), "alfa"),
    (re.compile(r"sauber", re.I), "sauber"),
    (re.compile(r"ferrari", re.I), "ferrari"),
    (re.compile(r"mercedes", re.I), "mercedes"),
]


def constructor_for(team_name: str) -> str | None:
    for pattern, constructor_id in TEAM_RULES:
        if pattern.search(team_name):
            return constructor_id
    return None


def reason_category(primary_reason: str) -> str:
    for category, pattern in REASON_CATEGORIES:
        if pattern.search(primary_reason.strip()):
            return category
    return "other"


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


@dataclass
class TeamPage:
    page: int
    team_name: str
    constructor_id: str | None
    no_updates: bool
    rows: list[dict] = field(default_factory=list)


@dataclass
class ParsedDocument:
    path: Path
    teams: list[TeamPage]
    problems: list[str]

    @property
    def row_count(self) -> int:
        return sum(len(t.rows) for t in self.teams)

    @property
    def no_update_teams(self) -> int:
        return sum(1 for t in self.teams if t.no_updates and not t.rows)

    @property
    def ok(self) -> bool:
        return not self.problems


def cluster(values: list[float], tolerance: float = EDGE_TOLERANCE) -> list[float]:
    """가까운 좌표를 하나로 묶어 대표값(평균)을 돌려준다."""
    groups: list[list[float]] = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] <= tolerance:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def column_edges(page) -> list[float]:
    """표의 세로 경계 여섯 개(다섯 열)를 찾는다. 못 찾으면 빈 목록."""
    xs = [r["x0"] for r in page.rects if r["x1"] - r["x0"] < 1.5 and r["bottom"] - r["top"] > 5]
    edges = cluster(xs)
    return edges if len(edges) == len(COLUMNS) + 1 else []


def cell_boxes(page, edges: list[float]) -> dict[int, list[tuple[float, float]]]:
    """열 번호별 셀의 (위, 아래) 목록. 가로 테두리 선에서 얻는다.

    테두리는 열 구간마다 얇은 사각형으로 그려져 있다. 병합된 칸은 중간 테두리가 없어서
    자연히 큰 셀 하나가 된다. 칸 채움 상자는 양식에 따라 없는 경우가 있어 쓰지 않는다.
    """
    cells: dict[int, list[tuple[float, float]]] = {}
    for i in range(len(COLUMNS)):
        tops = [
            r["top"]
            for r in page.rects
            if r["bottom"] - r["top"] < 1.5
            and r["x1"] - r["x0"] > 5
            and r["x0"] <= edges[i] + EDGE_TOLERANCE
            and r["x1"] >= edges[i + 1] - EDGE_TOLERANCE
        ]
        bounds = cluster(tops, 1.5)
        cells[i] = [
            (a, b) for a, b in zip(bounds, bounds[1:], strict=False) if b - a >= MIN_CELL_HEIGHT
        ]
    return cells


def words_in(page, x0: float, x1: float, top: float, bottom: float) -> list[dict]:
    found = []
    for w in page.extract_words(x_tolerance=1.5, y_tolerance=2):
        cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
        if x0 - 1 <= cx <= x1 + 1 and top - 1 <= cy <= bottom + 1:
            found.append(w)
    return sorted(found, key=lambda w: (round(w["top"] / 3), w["x0"]))


def cell_text(page, x0: float, x1: float, top: float, bottom: float) -> str:
    return clean(" ".join(w["text"] for w in words_in(page, x0, x1, top, bottom)))


def parse_table(page) -> tuple[list[dict], list[str], bool]:
    """한 쪽의 표를 읽는다. (행 목록, 문제 목록, 머리글 행이 있었는지)를 돌려준다.

    행의 위아래 경계는 번호 열의 셀에서 얻는다. 번호 열을 그리지 않는 양식은 부품 열의 셀을 쓴다.
    머리글 행이 없는 쪽은 앞쪽 표가 이어진 것이다.
    """
    problems: list[str] = []
    edges = column_edges(page)
    if not edges:
        return [], ["표의 열 경계 여섯 개를 찾지 못했다"], False
    cells = cell_boxes(page, edges)
    row_column = 0 if cells[0] else 1
    row_cells = cells[row_column]
    if not row_cells:
        return [], ["행을 나눌 셀을 찾지 못했다"], False
    # 머리글 행은 열마다 정해진 말로 시작한다. 본문에 "Updated ..."가 나와도 머리글로 보지 않는다.
    first = [
        cell_text(page, edges[i], edges[i + 1], *cells[i][0]).casefold() if cells[i] else ""
        for i in range(len(COLUMNS))
    ]
    has_header = (
        first[1].startswith("updated component")
        or first[2].startswith("primary reason")
        or first[3].startswith("geometric differences")
    )
    rows: list[dict] = []
    for top, bottom in row_cells[1:] if has_header else row_cells:
        middle = (top + bottom) / 2
        row: dict = {"description_shared": False}
        for i, name in enumerate(COLUMNS):
            # 칸 상자가 그려지지 않은 곳은 행의 위아래 경계로 같은 자리를 읽는다
            box = next(((t, b) for t, b in cells[i] if t - 1 <= middle <= b + 1), (top, bottom))
            row[name] = cell_text(page, edges[i], edges[i + 1], box[0], box[1])
            if name == "description":
                row["description_shared"] = (box[1] - box[0]) > (bottom - top) + EDGE_TOLERANCE
        if not any(row.get(c) for c in COLUMNS[1:]):
            continue  # 빈 행(글자가 없는 머리글 행 포함)
        rows.append(row)
    # 번호가 칸 경계에 걸쳐 그려진 양식이 있다. 번호 개수가 행 수와 같으면 위에서부터 차례로 맞춘다.
    if rows:
        first_top = (row_cells[1] if has_header and len(row_cells) > 1 else row_cells[0])[0]
        numbers = [
            w["text"]
            for w in words_in(page, edges[0], edges[1], first_top, row_cells[-1][1] + 20)
            if w["text"].isdigit()
        ]
        if len(numbers) == len(rows):
            for row, number in zip(rows, numbers, strict=True):
                row["item_no"] = number
        elif row_column == 1:
            for row in rows:
                row["item_no"] = ""
    return rows, problems, has_header


def finish_rows(rows: list[dict], problems: list[str], where: str) -> None:
    """번호를 확인하고 상위 범주를 붙인다. 번호 열이 없는 양식은 순서대로 번호를 매긴다."""
    consistent = all(not r["item_no"] or r["item_no"] == str(n) for n, r in enumerate(rows, 1))
    if consistent:  # 빠진 번호는 순서로 채우고 표시한다
        for n, row in enumerate(rows, 1):
            if not row["item_no"]:
                row["item_no"] = str(n)
                row["item_no_inferred"] = True
    for row in rows:
        row.setdefault("item_no_inferred", False)
        if not re.fullmatch(r"\d+", row["item_no"]):
            problems.append(f"{where}: 번호가 숫자가 아니다: {row['item_no']!r}")
        row["reason_category"] = reason_category(row["primary_reason"])


def team_name_from(lines: list[str]) -> str:
    """쪽 머리의 팀 이름. 제목 줄("Car Presentation ...")이 있으면 그 다음 줄이다."""
    lines = [clean(line).strip("* ") for line in lines if clean(line)]
    lines = [line for line in lines if not TITLE_LINE.match(line)]
    return clean(lines[0]) if lines else ""


def merge_continuation(previous: list[dict], rows: list[dict]) -> None:
    """앞쪽에서 이어진 표를 붙인다. 번호 없는 첫 행은 앞쪽 마지막 행의 뒷부분이다."""
    if previous and rows and not rows[0]["item_no"]:
        head = rows.pop(0)
        last = previous[-1]
        for name in COLUMNS[1:]:
            last[name] = clean(f"{last[name]} {head[name]}")
    previous.extend(rows)


def parse_document(path: Path) -> ParsedDocument:
    teams: list[TeamPage] = []
    problems: list[str] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if len(text.strip()) < 20:
                continue  # 사진만 있는 쪽
            if "From" in text[:200] and "Document" in text[:200] and "Title" in text:
                continue  # FIA 표지
            edges = column_edges(page)
            lines = text.splitlines()
            rows: list[dict] = []
            has_header = False
            if edges:
                rows, row_problems, has_header = parse_table(page)
                problems.extend(f"{number}쪽: {p}" for p in row_problems)
                # 표 위쪽 글만 팀 이름 후보로 본다
                table_top = min(r["top"] for r in page.rects if r["bottom"] - r["top"] > 5)
                head = page.crop((0, 0, page.width, max(table_top, 1))).extract_text() or ""
                lines = head.splitlines()
            name = team_name_from(lines)
            constructor_id = constructor_for(name)
            no_updates = bool(NO_UPDATES.search(text))
            if edges and not rows and not no_updates:
                problems.append(f"{number}쪽: 표가 있는데 행을 하나도 읽지 못했다")
            if constructor_id is None and edges:
                # 팀 이름 없이 표만 있는 쪽은 앞쪽 팀의 표가 이어진 것이다
                if not teams:
                    problems.append(f"{number}쪽: 이어지는 표인데 앞쪽 팀이 없다")
                    continue
                merge_continuation(teams[-1].rows, rows)
                continue
            if constructor_id is None and not no_updates:
                continue  # 사진 설명만 있는 쪽
            if constructor_id is None:
                problems.append(f"{number}쪽: 팀 이름을 알 수 없다: {name!r}")
                continue
            if not edges and not no_updates:
                # 표가 그림으로만 들어간 쪽. 읽을 수 없으므로 팀만 기록하고 문제로 남긴다.
                problems.append(f"{number}쪽: {name}: 표도 'No updates submitted'도 글자로 없다")
            previous = next((t for t in teams if t.constructor_id == constructor_id), None)
            if previous is not None:  # 같은 팀의 표가 다음 쪽으로 이어진 경우
                merge_continuation(previous.rows, rows)
                previous.no_updates = previous.no_updates and no_updates
                continue
            teams.append(TeamPage(number, name, constructor_id, no_updates, rows))
    if len(teams) != GRID_TEAMS:
        problems.append(f"팀 수가 {len(teams)}개다(그리드는 {GRID_TEAMS}개)")
    for t in teams:
        finish_rows(t.rows, problems, t.team_name)
        if t.rows and t.no_updates:
            problems.append(f"{t.team_name}: 표와 'No updates submitted'가 함께 있다")
    return ParsedDocument(path, teams, problems)


# --- 정제 테이블 만들기 -----------------------------------------------------------------


def build() -> dict[str, int]:
    """manifest의 Car Presentation 문서를 모두 파싱해 정제 테이블과 실패 목록을 쓴다.

    원문 PDF가 로컬 캐시에 없으면 manifest를 보고 다시 받는다(sha256이 다르면 멈춘다).
    """
    import pandas as pd

    from pipeline import manifest
    from pipeline.config import CURATED_DIR, RAW_DIR
    from pipeline.http import utc_now_iso
    from pipeline.sources import fia_docs

    fia_docs.download_documents(["car_presentation"])
    docs = [
        r
        for r in manifest.read_rows(fia_docs.INDEX_MANIFEST)
        if r["doc_type"] == "car_presentation"
    ]
    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    rounds = {(int(r.season), r.race_name.casefold()): int(r.round) for r in races.itertuples()}

    item_rows, team_rows, doc_rows, failures = [], [], [], []
    for doc in docs:
        season = int(doc["season"])
        round_no = rounds.get((season, doc["event"].casefold()))
        parsed = parse_document(RAW_DIR / "fia" / fia_docs.pdf_cache_path(doc))
        problems = list(parsed.problems)
        if round_no is None:
            problems.append(f"대회명을 라운드에 맞추지 못했다: {doc['event']}")
        status = "ok" if not problems else "needs_review"
        key = {"season": season, "round": round_no, "event": doc["event"]}
        doc_rows.append(
            {
                **key, "published_at": doc["published_at"], "url": doc["url"],
                "teams": len(parsed.teams), "rows": parsed.row_count,
                "no_update_teams": parsed.no_update_teams, "status": status,
                "problems": " / ".join(problems),
            }
        )  # fmt: skip
        if problems:
            failures.append(
                {
                    **key, "doc_type": "car_presentation", "url": doc["url"],
                    "problems": " / ".join(problems), "recorded_at": utc_now_iso()[:10],
                }
            )  # fmt: skip
        for team in parsed.teams:
            if team.rows:
                team_status = "updates"
            elif team.no_updates:
                team_status = "no_updates"
            else:
                team_status = "needs_review"  # 표가 그림으로만 들어간 팀 등
            team_rows.append(
                {
                    **key, "constructor_id": team.constructor_id, "team_name": team.team_name,
                    "status": team_status, "rows": len(team.rows), "page": team.page,
                }
            )  # fmt: skip
            for order, row in enumerate(team.rows, 1):
                item_rows.append(
                    {
                        **key, "constructor_id": team.constructor_id, "row_order": order,
                        "item_no": row["item_no"], "item_no_inferred": row["item_no_inferred"],
                        "updated_component": row["updated_component"],
                        "primary_reason": row["primary_reason"],
                        "reason_category": row["reason_category"],
                        "geometric_differences": row["geometric_differences"],
                        "description": row["description"],
                        "description_shared": row["description_shared"],
                        "document_status": status, "source_url": doc["url"],
                    }
                )  # fmt: skip

    out = CURATED_DIR / "fia"
    out.mkdir(parents=True, exist_ok=True)
    order = ["season", "round", "constructor_id"]
    items = pd.DataFrame(item_rows).sort_values([*order, "row_order"])
    items.to_parquet(out / "car_presentation.parquet", index=False, compression="zstd")
    pd.DataFrame(team_rows).sort_values(order).to_csv(
        out / "car_presentation_teams.csv", index=False
    )
    pd.DataFrame(doc_rows).sort_values(["season", "round"]).to_csv(
        out / "car_presentation_documents.csv", index=False
    )
    # 실패 목록은 문서 유형별로 갈아 끼운다(다른 파서의 기록은 건드리지 않는다)
    fields = ["season", "round", "event", "doc_type", "url", "problems", "recorded_at"]
    others = [
        r for r in manifest.read_rows("parse_failures.csv") if r["doc_type"] != "car_presentation"
    ]
    manifest.write_rows("parse_failures.csv", others + failures, fields)
    return {"documents": len(doc_rows), "teams": len(team_rows), "rows": len(items),
            "failures": len(failures)}  # fmt: skip


if __name__ == "__main__":
    for name, n in build().items():
        print(f"car_presentation {name}: {n}")
