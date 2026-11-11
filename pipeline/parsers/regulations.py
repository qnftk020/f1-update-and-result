"""FIA 포뮬러 원 기술·스포팅 규정 조항 파서와 판 사이 비교. (T8, 등급 A 2018-2025)

문서 구조(2018-2025 판을 렌더링해 확인한 결과, docs/methodology.md "규정 조항 파싱과 비교"):

- 표지와 목차가 앞에 온다. 목차 줄은 "ARTICLE 3: AERODYNAMIC COMPONENTS 11", "3.5 Floor"처럼
  본문 제목과 똑같이 생겼으므로, 쪽 번호가 붙지 않은 1조 제목이 나오기 전까지는 모두
  앞부분으로 본다.
- 기술 규정의 조 제목은 "ARTICLE 5: POWER UNIT", 스포팅 규정의 조 제목은 "28) POWER UNIT USAGE"
  꼴의 굵은 글씨다.
- 조항 번호("3.5.1", "28.2")는 왼쪽 여백 열에 따로 찍히고 본문은 들여 쓴 열에서 시작한다. 본문 줄이
  "54.3 the stewards ..."처럼 숫자로 시작해도 여백 열이 아니므로 조항으로 보지 않는다.
- 소제목이 있는 조항은 번호 뒤 글이 모두 굵다("3.6.1 Nose"). 없는 조항은 번호 뒤에 바로 본문이 온다.
- 개정 부분은 분홍색 글씨로, 삭제 부분은 취소선으로 표시한다. 취소선 글자는 그 판에서 효력이
  없으므로 조항 글에서 뺀다. 색 글씨는 글로는 그대로 두고 조항에 표시(marked)만 남긴다. 조·부록
  제목만 지우고 그 아래 알림 글("-Void-", "[Note. ...]")은 남긴 판이 있어, 지운 제목은 경계로
  쓰고 그 조·부록을 효력 없는 조항(struck)으로 둔다. 알림이 아닌 글이 남아 있으면 문제로 적는다.
- 쪽마다 아래쪽에 머리말·꼬리말(문서명, 쪽 번호, 날짜, 저작권)이 있다.
- 부록은 "APPENDIX 4: ..." 제목으로 시작하고 번호가 1부터 다시 시작한다. 부록 조항 키에는 "A4-"를
  붙인다. 번호 없는 그림과 표는 조항으로 나누지 않고 개수만 센다.

비교 단위는 번호가 붙은 조항이다(기술 규정 "3.5.1", 스포팅 규정 "24.3"). 조와 그 아래 각 단계의
번호도 각각 한 행이 되며, 그 행의 글은 다음 번호가 나오기 전까지의 글이다. 문자로 매긴 하위 항목
("a)", "i.")은 자기 번호 조항의 글에 속한다.

저작권 규칙: 조항 본문은 정제 테이블에 쓰지 않는다. 비교용 본문은 data/raw/ 아래(커밋하지 않음)의
파싱 캐시에만 둔다. 정제 테이블에는 번호, 제목, 쪽, 글자 수, 해시, 변경 여부만 쓴다.

실행: uv run python -m pipeline.parsers.regulations [--cached]
"""

from __future__ import annotations

import contextlib
import csv
import difflib
import fcntl
import functools
import hashlib
import io
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pdfplumber

PARSER_VERSION = "9"
DOC_TYPES = {"technical": "regulation_technical", "sporting": "regulation_sporting"}

# 줄 단위 패턴
ARTICLE_TECH = re.compile(r"^ARTICLE\s+(\d+)\s*[:.]?\s*(.*)$")
# "40 PRE-SPRINT AND PRE-RACE PARC FERME"처럼 괄호가 빠진 제목도 있다(2023년 판).
ARTICLE_SPORT = re.compile(r"^(\d+)(?:\)\s*|\s+(?=[A-Z]{2}))(.*)$")
APPENDIX = re.compile(r"^APPENDIX\s+(\d+[A-Z]?)\b\s*[:.\-–]?\s*(.*)$")
NUMBERED = re.compile(r"^(\d+(?:\.\d+)+)\.?(?:\s+(.*))?$")
APPENDIX_SECTION = re.compile(r"^(\d+)\.?\s+(.*)$")
TOC_PAGE_REF = re.compile(r"\s\d+(?:\s*[-‐–]\s*\d+)?$")
NOT_USED = re.compile(
    r"^[\[(]?\s*(?:article\s+)?(?:not\s+used|void|deleted|intentionally\s+left\s+blank)"
    r"\s*[\])]?\.?$",
    re.I,
)
BOLD_FONT = re.compile(r"bold|black|heavy", re.I)
# 다음 해 규정의 바뀐 조항을 옮겨 적은 조·부록. 번호가 그 해 규정의 번호라 조항으로 나누지 않는다.
FUTURE_CHANGES = re.compile(r"\bCHANGES FOR\b", re.I)

# 조항 번호 열의 x 위치 허용 범위(pt). 본문 들여쓰기는 여백보다 28pt 이상 안쪽이다.
# 여백보다 바깥으로 내어 쓴 번호(2022-2025 기술 규정 3.7.6-3.7.8, 8.5pt)가 있어 왼쪽은 더 넓게 둔다.
MARGIN_LEFT = 12.0
MARGIN_RIGHT = 8.0
HEADER_BAND = 0.09  # 쪽 위쪽 9%
FOOTER_BAND = 0.88  # 쪽 아래쪽 12%
STRIKE_BAND = (0.3, 0.7)  # 글자 높이 안에서 취소선이 지나는 위치(위에서부터 비율)


# --- 글 정규화 ---------------------------------------------------------------------------

_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")
_QUOTES = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x00A0: " "}


def normalise(text: str) -> str:
    """비교와 해시에 쓰는 정규형.

    유니코드 호환 정규화, 대시·따옴표 통일, 공백 정리. 문장부호 앞과 여는 괄호 뒤의 공백도
    지운다("include :" 와 "include:"는 같은 글로 본다).
    """
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_QUOTES)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r" ([,.:;)\]])", r"\1", text)
    return re.sub(r"([(\[]) ", r"\1", text).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def join_lines(lines: list[str], pages: list[int] | None = None) -> tuple[str, list[list[int]]]:
    """줄을 이어 붙인다. 줄 끝이 하이픈이고 그 앞이 공백이 아니면 띄어 쓰지 않는다
    ("end-" + "of-session", "8853-" + "2016.", "(+1%/-" + "0)").

    쪽이 바뀌는 글자 위치 목록 [[위치, 쪽], ...]을 함께 돌려준다(근거 인용의 쪽을 찾는 데 쓴다).
    """
    out = ""
    starts: list[list[int]] = []
    for i, raw in enumerate(lines):
        line = normalise(raw)
        if not line:
            continue
        if out.endswith("-") and len(out) > 1 and not out[-2].isspace():
            joined = out + line
        else:
            joined = f"{out} {line}" if out else line
        page = pages[i] if pages else 0
        if not starts or starts[-1][1] != page:
            starts.append([len(joined) - len(line), page])
        out = joined
    return normalise(out), starts


def page_at(clause: Clause, offset: int) -> int:
    """조항 글의 offset 위치가 찍힌 쪽."""
    page = clause.page
    for start, number in clause.page_starts:
        if start <= offset:
            page = number
    return page


def number_key(number: str) -> tuple[int, ...]:
    return tuple(int(p) for p in number.split("."))


def appendix_key(label: str) -> tuple[int, str]:
    m = re.fullmatch(r"(\d+)([A-Z]?)", label)
    return (int(m.group(1)), m.group(2)) if m else (10**6, label)


# --- 쪽에서 줄 읽기 ----------------------------------------------------------------------


@dataclass
class Line:
    page: int
    x0: float
    top: float
    text: str
    bold: float  # 줄 전체의 굵은 글자 비율
    rest_bold: float  # 첫 낱말 뒤 글자의 굵은 글자 비율
    small_number: bool  # 첫 낱말이 뒤따르는 글보다 작은 글자다(조항 번호의 글꼴)
    marked: bool  # 검정·회색이 아닌 색 글자가 있다
    in_table: bool  # 첫 글자가 표 안에 있다(표 칸의 글은 행 하나가 줄 하나다)
    band: str  # "header" | "footer" | "body"
    x1: float = 0.0
    image: str = ""  # 그림 자리 표시 줄이면 그림 데이터의 sha256(글은 비어 있다)
    struck: bool = False  # 취소선으로 지운 조·부록 제목 줄(struck_heading_lines)


def is_bold(char: dict) -> bool:
    return bool(BOLD_FONT.search(char.get("fontname", "")))


def is_rotated(char: dict) -> bool:
    """세로로 돌려 찍은 글자. 표 머리("Item No")에 쓰인다.

    pdfplumber가 upright로 보고하는 경우가 있어(2025년 기술 규정 부록 3) 글자 행렬도 본다.
    기울임꼴은 행렬의 c 값만 바뀌므로 여기에 걸리지 않는다.
    """
    matrix = char.get("matrix") or (1, 0, 0, 1, 0, 0)
    return not char.get("upright", True) or abs(matrix[1]) > abs(matrix[0])


def is_coloured(char: dict) -> bool:
    """검정과 회색이 아닌 글자. 개정 표시(분홍, 진홍)를 찾는 데 쓴다."""
    colour = char.get("non_stroking_color")
    if colour is None or isinstance(colour, (int, float)):
        return False
    values = [float(v) for v in colour] if isinstance(colour, (list, tuple)) else []
    if len(values) == 3:
        return max(values) - min(values) > 0.2
    if len(values) == 4:  # CMYK
        return max(values[:3]) - min(values[:3]) > 0.2
    return False


def strike_segments(page) -> list[tuple[float, float, float]]:
    """가로로 얇은 선과 사각형 (x0, x1, y)."""
    segments = []
    for obj in page.lines + page.rects:
        if obj["bottom"] - obj["top"] < 1.6 and obj["x1"] - obj["x0"] > 2:
            segments.append((obj["x0"], obj["x1"], (obj["top"] + obj["bottom"]) / 2))
    return segments


def struck_chars(chars: list[dict], segments: list[tuple[float, float, float]]) -> set[int]:
    """취소선이 그어진 글자(id)를 찾는다.

    선이 글자 높이의 30-70% 사이를 지나면 취소선이다. 밑줄(2018년 판의 개정 표시)은 글자 아래쪽
    80% 부근을 지나므로 여기에 걸리지 않는다.
    """
    found: set[int] = set()
    if not segments:
        return found
    low, high = STRIKE_BAND
    for c in chars:
        height = c["bottom"] - c["top"]
        if height <= 0 or not c["text"].strip():
            continue
        cx = (c["x0"] + c["x1"]) / 2
        for x0, x1, y in segments:
            if x0 - 0.5 <= cx <= x1 + 0.5 and low <= (y - c["top"]) / height <= high:
                found.add(id(c))
                break
    return found


def same_row_runs(chars: list[dict]) -> list[list[dict]]:
    """같은 높이(0.5pt 안)에서 틈 없이(0.8pt 안) 이어진 글자 묶음."""
    rows: list[list[dict]] = []
    for c in sorted(chars, key=lambda c: c["top"]):
        if rows and c["top"] - rows[-1][-1]["top"] < 0.5:
            rows[-1].append(c)
        else:
            rows.append([c])
    runs: list[list[dict]] = []
    for row in rows:
        start = len(runs)
        for c in sorted(row, key=lambda c: c["x0"]):
            if len(runs) > start and abs(c["x0"] - runs[-1][-1]["x1"]) <= 0.8:
                runs[-1].append(c)
            else:
                runs.append([c])
    return runs


def snap_offset_chars(chars: list[dict]) -> tuple[list[dict], int]:
    """줄에서 위아래로 비켜 찍힌 글자를 그 줄로 옮긴다.

    아래첨자·위첨자("X" 다음 작은 "DIF")는 높이가 3pt쯤 달라 판에 따라 다른 줄로 묶이거나
    다른 자리에 끼어 같은 인쇄면이 다른 글로 읽힌다. 다른 글꼴로 찍은 낱글자(2024년 기술 규정
    13.7.2 "mid-point"의 하이픈은 글자 상자가 두 줄 아래에 있다)도 같다. 그래서 아래 두 경우에
    그 글자 묶음의 높이를 이웃 글자의 높이로 맞춘다(가로 위치는 그대로 둔다). 묶음 양옆에
    높이가 1pt 안으로 같은 글자가 붙어 있으면 이미 제 줄에 있으므로 옮기지 않는다.

    - 이웃보다 작은 글자 묶음이 왼쪽이나 오른쪽 글자에 바로(0.8pt 안) 붙어 있고, 묶음의 세로
      가운데가 그 글자의 높이 안에 있다("X" 다음 "DIF", "C" 앞 "o").
    - 바로 붙은 이웃 글자가 모두 글자 높이의 절반 넘게 위아래로 떨어진 낱글자가 다른 줄의
      두 글자 사이 틈에 꼭 맞게(양쪽 0.8pt 안) 들어가 있고 그 줄 글자와 크기가 같다(15% 안).
      그런 줄이 여럿이면 세로로 가장 가까운 줄로 옮긴다.
    """
    if not chars:
        return chars, 0
    ends: dict[int, list[dict]] = {}
    starts: dict[int, list[dict]] = {}
    for c in chars:
        ends.setdefault(round(c["x1"]), []).append(c)
        starts.setdefault(round(c["x0"]), []).append(c)

    def near(index: dict[int, list[dict]], x: float, key: str, skip: set[int]) -> list[dict]:
        found = []
        for k in (round(x) - 1, round(x), round(x) + 1):
            found += [c for c in index.get(k, []) if abs(c[key] - x) <= 0.8 and id(c) not in skip]
        return found

    moved: dict[int, dict] = {}
    for run in same_row_runs(chars):
        first, last = run[0], run[-1]
        members = {id(c) for c in run}
        lefts = near(ends, first["x0"], "x1", members)
        rights = near(starts, last["x1"], "x0", members)
        if any(abs(c["top"] - first["top"]) < 1.0 for c in lefts + rights):
            continue
        size = max(c["size"] for c in run)
        mid = (min(c["top"] for c in run) + max(c["bottom"] for c in run)) / 2
        target = None
        small = [
            c for c in lefts + rights if size < 0.85 * c["size"] and c["top"] <= mid <= c["bottom"]
        ]  # fmt: skip
        alone = not any(abs(c["top"] - first["top"]) < 0.5 * size for c in lefts + rights)
        if small:
            target = moved.get(id(small[0]), small[0])
        elif len(run) == 1 and first["text"].strip() and alone:
            pairs = [
                (abs(a["top"] - first["top"]), a) for a in lefts for b in rights
                if abs(a["top"] - b["top"]) < 0.5 and abs(a["top"] - first["top"]) < 3 * size
                and 0.85 * a["size"] <= size <= a["size"] / 0.85
            ]  # fmt: skip
            if pairs:
                target = min(pairs, key=lambda t: t[0])[1]
        if target is None:
            continue
        for c in run:
            moved[id(c)] = {
                **c, "top": target["top"], "bottom": target["bottom"],
                "doctop": c["doctop"] + target["top"] - c["top"],
            }  # fmt: skip
    return [moved.get(id(c), c) for c in chars], len(moved)


def text_lines(chars: list[dict], page) -> list[dict]:
    """글자 목록을 pdfplumber의 줄 묶음 규칙으로 줄로 나눈다."""
    if not chars:
        return []
    textmap = pdfplumber.utils.chars_to_textmap(
        chars, layout_bbox=page.bbox, layout_width=page.width, layout_height=page.height,
        x_tolerance=1.5,
    )  # fmt: skip
    return textmap.extract_text_lines(strip=True, return_chars=True)


def inside(char: dict, bbox: tuple[float, float, float, float]) -> bool:
    cx, cy = (char["x0"] + char["x1"]) / 2, (char["top"] + char["bottom"]) / 2
    return bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]


def rotated_text(chars: list[dict]) -> str:
    """돌려 찍은 글자를 내용 흐름 순서대로 잇는다. 글자 상자 사이가 글자 크기의 1/4보다 멀면
    띄어 쓴다(세로 글의 낱말 사이, 다른 세로 줄)."""
    out = ""
    last: dict | None = None
    for c in chars:
        if not c["text"].strip():
            out += " "
            last = None
            continue
        if last is not None:
            gap = max(c["x0"] - last["x1"], last["x0"] - c["x1"], c["top"] - last["bottom"],
                      last["top"] - c["bottom"])  # fmt: skip
            if gap > 0.25 * max(c["size"], last["size"]):
                out += " "
        out += c["text"]
        last = c
    return normalise(out)


def table_rows(
    tables: list, chars: list[dict], page, rotated: list[dict] | None = None
) -> tuple[list[dict], list[dict]]:
    """표 칸의 글을 행마다 한 줄로 만든다. 칸 안의 줄바꿈은 띄어쓰기로 잇는다.

    표를 줄 단위로 읽으면 한 칸의 줄바꿈 위치가 바뀌었을 때(2018과 2019년 판 부록 2의 28행)
    옆 칸 글과 섞이는 순서가 달라져 같은 표가 다른 글로 읽힌다. 칸 단위로 읽으면 그렇지 않다.
    칸 안의 돌려 찍은 글자(표 머리 "Item No")는 칸 글 뒤에 붙인다. 그래야 표 머리가 바뀐 판을
    변경으로 잡는다. 돌려주는 값은 (행 줄 목록, 칸 밖에 남은 글자)다.
    """
    rows: list[dict] = []
    used: set[int] = set()
    rotated = rotated or []
    for table in tables:
        for row in table.rows:
            cells, row_chars, row_rotated = [], [], []
            for bbox in row.cells:
                if bbox is None:
                    continue
                cell = [c for c in chars if id(c) not in used and inside(c, bbox)]
                used.update(id(c) for c in cell)
                turned = [c for c in rotated if id(c) not in used and inside(c, bbox)]
                used.update(id(c) for c in turned)
                text, _ = join_lines([ln["text"] for ln in text_lines(cell, page)])
                if turned:
                    text = normalise(f"{text} {rotated_text(turned)}")
                if text:
                    cells.append(text)
                    row_chars += [c for c in cell if c["text"].strip()]
                    row_rotated += [c for c in turned if c["text"].strip()]
            if cells:
                x0, top, x1, _ = row.bbox
                # 글꼴 셈(굵기, 번호 글자 크기)은 바로 선 글자로 하고, 돌린 글자만 있는 행이면
                # 돌린 글자로 한다.
                rows.append({"text": " ".join(cells), "x0": x0, "x1": x1, "top": top,
                             "chars": row_chars + row_rotated, "rotated": row_rotated})  # fmt: skip
    return rows, [c for c in chars if id(c) not in used]


IMAGE_HASH_SIDE = 16  # 그림 지문의 한 변(16 x 16 = 256비트)
IMAGE_TOLERANCE = 10  # 같은 그림으로 볼 지문의 최대 차이(비트 수)


def image_signature(page, image: dict) -> str:
    """그림 자리를 낮은 해상도로 그려 만든 차이 해시(dHash, 256비트)의 16진수.

    그림 데이터의 바이트는 같은 그림도 판마다 다시 압축되어 달라진다(2024년 판 PNG와 2025년
    판 JPEG). 그래서 보이는 모양으로 비교한다. 다시 압축한 같은 그림은 0-7비트, 다른 그림은
    100비트 안팎이 다르다. 글자 하나 정도의 작은 수정은 잡지 못할 수 있다.
    """
    bbox = (
        max(0.0, image["x0"]), max(0.0, image["top"]),
        min(page.width, image["x1"]), min(page.height, image["bottom"]),
    )  # fmt: skip
    if bbox[2] - bbox[0] < 1 or bbox[3] - bbox[1] < 1:
        return "0" * (IMAGE_HASH_SIDE**2 // 4)
    side = IMAGE_HASH_SIDE
    picture = page.crop(bbox).to_image(resolution=36).original.convert("L")
    pixels = list(picture.resize((side + 1, side)).tobytes())
    bits = "".join(
        "1" if pixels[r * (side + 1) + c] > pixels[r * (side + 1) + c + 1] else "0"
        for r in range(side)
        for c in range(side)
    )
    return f"{int(bits, 2):0{side * side // 4}x}"


def images_match(a: list[str], b: list[str]) -> bool:
    """두 조항의 그림이 같은 수이고 차례로 IMAGE_TOLERANCE 안에서 같다."""
    if len(a) != len(b):
        return False
    pairs = zip(a, b, strict=True)
    return all(bin(int(x, 16) ^ int(y, 16)).count("1") <= IMAGE_TOLERANCE for x, y in pairs)


def make_line(raw: dict, number: int, page, in_table: bool, tables: list) -> Line | None:
    chars = [c for c in raw["chars"] if c["text"].strip()]
    text = raw["text"].strip()
    if not chars or not text:
        return None
    first = text.split()[0]
    head = chars[: len(first)]
    rest = chars[len(first) :]
    small_number = bool(rest) and max(c["size"] for c in head) < 0.9 * statistics.median(
        c["size"] for c in rest
    )
    in_table = in_table or any(inside(chars[0], t.bbox) for t in tables)
    if raw["top"] < page.height * HEADER_BAND:
        band = "header"
    elif raw["top"] > page.height * FOOTER_BAND:
        band = "footer"
    else:
        band = "body"
    return Line(
        page=number, x0=raw["x0"], top=raw["top"], text=text,
        bold=sum(is_bold(c) for c in chars) / len(chars),
        rest_bold=sum(is_bold(c) for c in rest) / len(rest) if rest else 0.0,
        small_number=small_number, marked=any(is_coloured(c) for c in chars),
        in_table=in_table, band=band, x1=raw.get("x1", 0.0),
    )  # fmt: skip


def is_fill_block(obj: dict) -> bool:
    """칠하기만 하고 테두리를 긋지 않은 넓은 사각형(개정 강조 상자, 칸 바탕색).

    표의 칸 선은 두께 2pt 아래의 가는 사각형이나 선으로 찍힌다. 칠한 상자로만 이루어진 "표"는
    표가 아니다(2023년 스포팅 규정 Issue 3의 노란 개정 상자는 줄마다 상자가 있어 표처럼 읽혔고,
    그 안의 42.2가 앞 조항에 붙었다).
    """
    return (
        obj.get("object_type") == "rect"
        and bool(obj.get("fill"))
        and not obj.get("stroke")
        and obj["x1"] - obj["x0"] > 2
        and obj["bottom"] - obj["top"] > 2
    )


def find_tables(page) -> tuple[list, int]:
    """칸 선이 있는 표(행 2개 이상)와, 표를 찾을 때 뺀 칠한 상자의 수."""
    blocks = sum(is_fill_block(r) for r in page.rects)
    source = page.filter(lambda obj: not is_fill_block(obj)) if blocks else page
    return [t for t in source.find_tables() if len(t.rows) >= 2], blocks


def is_band_picture(image: dict, height: float) -> bool:
    """머리말·꼬리말 띠의 그림(문서 로고)인지 본다.

    위 띠는 상자 전체가 띠 안에 있어야 한다. 위 끝만 띠 안에 있고 본문으로 내려오는 그림은 본문
    그림이다(2021년 기술 규정 부록 1의 도면은 57pt에서 시작해 400pt까지 내려온다). 예외는 위 띠에서
    시작하고 높이가 띠 높이 이하인 로고 띠다. 스포팅 규정 참가 신청서 쪽의 FIA 로고 띠([32, 32,
    366, 87], 띠는 71pt까지)는 띠를 조금 넘지만 본문 그림이 아니고, 판마다 다시 넣어 지문이 달라져
    가짜 그림 변경을 만든다. 아래 띠는 위 끝이 띠 안이면 상자 전체가 띠 안이다.
    """
    band = height * HEADER_BAND
    banner = image["top"] < band and image["bottom"] - image["top"] <= band
    return image["bottom"] <= band or banner or image["top"] > height * FOOTER_BAND


def page_lines(page, number: int) -> tuple[list[Line], dict[str, int]]:
    """한 쪽의 줄 목록과 셈(취소선 글자, 돌린 글자, 표, 색 글자)을 돌려준다.

    줄은 위에서 아래 순서다. 표는 행마다 한 줄, 그림은 글이 빈 자리 표시 줄 하나가 된다.
    돌려 찍은 글자는 표 칸 안에 있으면 그 칸 글에 붙이고(table_rows), 표 밖이면 셈만 남긴다.
    """
    stats = Counter()
    struck = struck_chars(page.chars, strike_segments(page))
    stats["struck_chars"] = len(struck)
    chars, rotated = [], []
    for c in page.chars:
        if id(c) in struck:
            continue
        if is_rotated(c):
            stats["rotated_chars"] += bool(c["text"].strip())
            rotated.append(c)
            continue
        chars.append(c)
    stats["marked_chars"] = sum(is_coloured(c) for c in chars if c["text"].strip())
    chars, stats["snapped_chars"] = snap_offset_chars(chars)
    live = chars
    tables, stats["fill_blocks"] = find_tables(page)
    stats["tables"] = len(tables)
    rows, chars = table_rows(tables, chars, page, rotated)
    stats["rotated_table_chars"] = sum(
        bool(c["text"].strip()) for row in rows for c in row.get("rotated", [])
    )
    lines = [make_line(raw, number, page, False, tables) for raw in text_lines(chars, page)]
    lines += [make_line(raw, number, page, True, tables) for raw in rows]
    gone = [c for c in page.chars if id(c) in struck and not is_rotated(c)]
    lines += struck_heading_lines(gone, live, number, page, tables)
    for image in page.images:
        if not is_band_picture(image, page.height):
            lines.append(
                Line(number, image["x0"], image["top"], "", 0.0, 0.0, False, False, False,
                     "body", image["x1"], image_signature(page, image))
            )  # fmt: skip
    lines = sorted((ln for ln in lines if ln is not None), key=lambda ln: (ln.top, ln.x0))
    for ln in lines:
        rejoin_struck_number(ln, [c for c in page.chars if id(c) in struck])
    return lines, stats


def struck_heading_lines(
    struck: list[dict], live: list[dict], number: int, page, tables: list
) -> list[Line]:
    """취소선으로 지운 조·부록 제목 줄("APPENDIX 6", "ARTICLE 18: ...")을 표시 줄로 남긴다.

    취소선 글자는 조항 글에서 빼지만, 지운 제목 줄까지 없애면 그 아래 지우지 않은 글("-Void-",
    "[Note. ...]")이 앞 조항의 끝에 붙는다(2021년 스포팅 규정 Issue 2의 부록 6, 2022년 기술 규정
    Issue 9의 18조). 그래서 줄 전체가 지워진 굵은 조·부록 제목은 struck 표시를 단 줄로 돌려주고,
    segment가 그 줄로 조·부록의 경계를 잡는다. 같은 높이에 지우지 않은 글자가 있는 줄(옛 제목을
    지우고 새 제목을 옆에 쓴 줄)과 표 안의 줄은 남기지 않는다.
    """
    out = []
    for raw in text_lines(struck, page):
        line = make_line(raw, number, page, False, tables)
        if line is None or line.in_table or line.bold < 0.6:
            continue
        if not any(p.match(line.text) for p in (ARTICLE_TECH, ARTICLE_SPORT, APPENDIX)):
            continue
        glyphs = [c for c in raw["chars"] if c["text"].strip()]
        top, bottom = min(c["top"] for c in glyphs), max(c["bottom"] for c in glyphs)
        middle = (top + bottom) / 2
        if any(c["text"].strip() and c["top"] <= middle <= c["bottom"] for c in live):
            continue
        line.struck = True
        out.append(line)
    return out


def rejoin_struck_number(line: Line, struck: list[dict]) -> None:
    """번호 안의 지운 숫자를 뺀 자리에 생긴 틈을 메운다.

    "3.6.5 6"처럼 옛 번호의 끝자리를 취소선으로 지우고 새 끝자리를 붙여 쓴 판(2024년 기술 규정
    Issue 3)은 지운 글자를 빼면 "3.6. 6"이 된다. 줄 머리 번호의 두 토막 사이에 지운 글자가
    있을 때만 붙인다.
    """
    m = re.match(r"^(\d+(?:\.\d+)*\.)\s+(\d+)(?=\s|$)", line.text)
    if not m or not struck:
        return
    if any(abs(c["top"] - line.top) < 3 and line.x0 <= c["x0"] <= line.x0 + 40 for c in struck):
        line.text = f"{m.group(1)}{m.group(2)}{line.text[m.end() :]}"


def running_text_key(text: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", text)).strip().casefold()


PAGE_NUMBER = re.compile(r"(?:page\s*)?(\d+)(\s*/\s*\d+)?", re.I)


def page_number_offset(lines: list[Line]) -> int | None:
    """띠 안의 숫자만 있는 줄에서 가장 흔한 (쪽 순번 - 찍힌 번호). 쪽 번호의 규칙이다.

    세 쪽 이상에서 같은 규칙이 보일 때만 쪽 번호로 본다.
    """
    offsets = Counter(
        ln.page - int(m.group(1))
        for ln in lines
        if ln.band != "body" and (m := PAGE_NUMBER.fullmatch(ln.text)) and not m.group(2)
    )
    if not offsets or offsets.most_common(1)[0][1] < 3:
        return None
    return offsets.most_common(1)[0][0]


def is_page_number(line: Line, offset: int | None) -> bool:
    """띠 안의 "12/108" 꼴, 또는 쪽 번호 규칙에 맞는 숫자만 있는 줄.

    규칙에 맞지 않는 숫자 줄은 본문이다(2023-2025년 기술 규정 부록 1의 20.2는 값 "325"가 쪽
    맨 위 줄에 찍혀 있다).
    """
    m = PAGE_NUMBER.fullmatch(line.text)
    if line.band == "body" or not m:
        return False
    return bool(m.group(2)) or line.page - int(m.group(1)) == offset


def drop_running_lines(lines: list[Line], pages: int) -> tuple[list[Line], int]:
    """머리말·꼬리말을 뺀다.

    쪽 위아래 띠에 있으면서 숫자를 지운 모양이 여러 쪽(쪽 수의 40% 이상, 최소 3쪽)에 되풀이되는
    줄, 그리고 띠 안의 쪽 번호 줄(is_page_number)이 대상이다. 여러 쪽에 되풀이되는 그림(문서
    로고)도 뺀다.
    """
    pages_with = Counter()
    banded = {
        (ln.page, running_text_key(ln.text)) for ln in lines if ln.band != "body" and not ln.struck
    }
    for key in banded:
        pages_with[key[1]] += 1
    images_on = Counter(image for _, image in {(ln.page, ln.image) for ln in lines if ln.image})
    threshold = max(3, int(pages * 0.4))
    offset = page_number_offset([ln for ln in lines if not ln.struck])
    kept, dropped = [], 0
    for ln in lines:
        if ln.struck:  # 지운 조·부록 제목 표시 줄은 머리말이 아니다
            kept.append(ln)
            continue
        if ln.image:
            if images_on[ln.image] < threshold:
                kept.append(ln)
            continue
        # 가로로 돌린 쪽(부록 도면)은 꼬리말이 띠 밖에 찍히므로, 되풀이되는 줄은 위치와
        # 상관없이 뺀다.
        # 숫자만 있는 줄은 숫자를 지우면 모두 같은 모양이 되므로 쪽 번호 규칙으로만 가른다.
        numeric = PAGE_NUMBER.fullmatch(ln.text)
        if is_page_number(ln, offset) or (
            not numeric and pages_with[running_text_key(ln.text)] >= threshold
        ):
            dropped += 1
            continue
        kept.append(ln)
    return kept, dropped


# --- 조항 나누기 -------------------------------------------------------------------------


@dataclass
class Clause:
    clause_no: str
    part: str  # "body" | "appendix"
    level: int
    page: int
    heading: str
    top_article: str
    top_title: str
    text: str = ""
    not_used: bool = False
    marked: bool = False
    struck: bool = False  # 조·부록 제목이 취소선으로 지워졌다(그 판에서 효력이 없다)
    page_starts: list[list[int]] = field(default_factory=list, repr=False)
    images: list[str] = field(default_factory=list, repr=False)  # 조항 안 그림의 지문
    lines: list[str] = field(default_factory=list, repr=False)
    line_pages: list[int] = field(default_factory=list, repr=False)

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def text_sha256(self) -> str:
        return text_hash(self.text)

    @property
    def image_sha256(self) -> str:
        """조항 안 그림 지문들을 이은 값의 sha256. 그림이 없으면 빈 글."""
        if not self.images:
            return ""
        return hashlib.sha256("\n".join(self.images).encode("ascii")).hexdigest()


@dataclass
class ParsedDocument:
    path: Path
    pages: int
    clauses: list[Clause]
    problems: list[str]
    stats: dict[str, int]

    @property
    def ok(self) -> bool:
        return not self.problems and bool(self.clauses)


def article_heading(line: Line, style: str, expected: int | None = None) -> tuple[int, str] | None:
    """조 제목 줄이면 (조 번호, 제목). style은 조 제목 양식("technical" 또는 "sporting")이다.

    조 제목은 굵은 글씨다. 개정 색으로 새로 넣은 조 제목은 굵지 않게 찍힌 판이 있어(2023년
    스포팅 규정 Issue 3의 "64) TEAM EQUIPMENT"), 굵지 않아도 번호가 바로 다음 조 번호이고
    "N)" 꼴에 제목이 대문자뿐이면 조 제목으로 본다.
    """
    pattern = ARTICLE_TECH if style == "technical" else ARTICLE_SPORT
    m = pattern.match(line.text)
    if not m:
        return None
    number, title = int(m.group(1)), m.group(2).strip()
    if line.bold >= 0.6:
        return number, title
    plain_ok = (
        number == expected
        and re.match(r"^\d+\)", line.text)
        and re.search(r"[A-Z]{2}", title)
        and title == title.upper()
    )
    return (number, title) if plain_ok else None


def heading_style(lines: list[Line], section: str) -> str:
    """조 제목 양식. 스포팅 규정 초기 판(2022년 규정 Issue 1-3)은 기술 규정처럼
    "ARTICLE 1: ..." 양식에 세 단계 번호를 쓴다."""
    if (
        section == "sporting"
        and find_body_start(lines, "sporting") is None
        and find_body_start(lines, "technical") is not None
    ):
        return "technical"
    return section


def appendix_heading(line: Line) -> tuple[str, str] | None:
    if line.bold < 0.6:
        return None
    m = APPENDIX.match(line.text)
    return (m.group(1), m.group(2).strip()) if m else None


def find_body_start(lines: list[Line], section: str) -> int | None:
    """목차 다음, 쪽 번호가 붙지 않은 1조 제목 줄의 위치. 지운 제목 줄은 보지 않는다."""
    for i, line in enumerate(lines):
        if line.struck:
            continue
        heading = article_heading(line, section)
        if heading and heading[0] == 1 and not TOC_PAGE_REF.search(line.text):
            return i
    return None


def clause_margin(lines: list[Line]) -> float | None:
    """조항 번호가 찍히는 왼쪽 여백 열의 x 위치(가장 흔한 값)."""
    xs = [
        round(ln.x0)
        for ln in lines
        if NUMBERED.match(ln.text) and not ln.in_table and not ln.struck
    ]
    return statistics.mode(xs) if xs else None


def clean_heading(text: str) -> str:
    return normalise(text).rstrip(" :").strip()


def toc_check(front: list[Line], clauses: list[Clause]) -> dict[str, int]:
    """목차의 두 단계 번호("3.5 Floor")와 본문 조항을 맞춰 본다(기술 규정만 이렇게 적는다).

    목차가 본문보다 늦게 고쳐진 판이 있어(2018-2019년 판 17.3, 2020-2021년 판 7.9) 문제로 적지
    않고 셈만 남긴다. 검수할 때 이 셈이 0이 아닌 문서를 렌더링해 본다.
    """
    toc = {m.group(1) for ln in front if (m := re.match(r"^(\d+\.\d+)\s+\S", ln.text))}
    if not toc:
        return {}
    body = {c.clause_no for c in clauses if c.part == "body" and c.level == 2}
    return {
        "toc_entries": len(toc),
        "toc_not_in_body": len(toc - body),
        "body_not_in_toc": len(body - toc),
    }


def is_clause_start(line: Line, margin: float) -> bool:
    """여백 열에서 시작하고 표 안이 아니면 조항 시작 후보다.

    본문 줄은 들여 쓴 열에서 시작하므로 줄 머리의 상호 참조("54.3 the stewards ...")는 여기서
    걸러진다. 번호와 본문 사이 간격은 판마다 1pt 아래부터 30pt까지 달라 기준으로 쓰지 않는다.
    """
    return not line.in_table and at_margin(line, margin)


def at_margin(line: Line, margin: float) -> bool:
    return -MARGIN_LEFT <= line.x0 - margin <= MARGIN_RIGHT


def split_clause_no(clause_no: str) -> tuple[str, tuple[int, ...]]:
    """조항 키를 (부록 접두어, 번호)로 나눈다.

    "A1-15.2" -> ("A1", (15, 2)), "3.5" -> ("", (3, 5)), "A1" -> ("A1", ()).
    """
    if clause_no.startswith("A"):
        label, _, rest = clause_no.partition("-")
        return label, number_key(rest) if rest else ()
    return "", number_key(clause_no)


def join_clause_no(prefix: str, parts: tuple[int, ...]) -> str:
    number = ".".join(map(str, parts))
    if not prefix:
        return number
    return f"{prefix}-{number}" if number else prefix


def gap_problem(page: int, before: str, after: str) -> str:
    return f"{page}쪽: 조항 번호가 건너뛴다({before} 다음 {after})"


GAP_PROBLEM = re.compile(r"^(\d+)쪽: 조항 번호가 건너뛴다\((\S+) 다음 (\S+)\)$")


def sibling_gaps(clauses: list[Clause]) -> list[tuple[int, str, str]]:
    """같은 상위 번호 아래의 번호가 1부터 이어지지 않는 곳 (쪽, 앞 번호, 뒤 번호).

    앞 번호는 바로 앞 형제 번호이고, 첫 하위 번호가 1이 아니면 상위 번호다. 조와 부록 번호는
    segment가 따로 본다. 번호가 거꾸로 가거나 겹치는 곳은 순서 문제로 이미 적으므로 여기서는
    번호가 앞으로 건너뛴 곳만 본다.
    """
    last: dict[tuple[str, tuple[int, ...]], int] = {}
    seen: set[tuple[str, tuple[int, ...]]] = set()
    gaps = []
    for c in clauses:
        prefix, parts = split_clause_no(c.clause_no)
        # 조항이 없는 상위 번호("A1-3.1"의 "A1-3")도 형제 순서에 넣어 본다.
        for depth in range(1 if prefix else 2, len(parts) + 1):
            node = (prefix, parts[:depth])
            if node in seen:
                continue
            seen.add(node)
            parent, number = (prefix, parts[: depth - 1]), parts[depth - 1]
            before = last.get(parent, 0)
            if number > before + 1:
                prev = parts[: depth - 1] + ((before,) if before else ())
                gaps.append((c.page, join_clause_no(prefix, prev), join_clause_no(*node)))
            last[parent] = max(before, number)
    return gaps


def segment(lines: list[Line], section: str) -> tuple[list[Clause], list[str], Counter]:
    """본문 줄을 조항으로 나눈다. 순서가 어긋나면 문제로 적는다(고치지 않는다)."""
    problems: list[str] = []
    stats: Counter = Counter()
    sporting = section == "sporting"
    section = heading_style(lines, section)
    stats["technical_style"] = int(sporting and section == "technical")
    start = find_body_start(lines, section)
    if start is None:
        return [], ["목차 뒤 본문 1조 제목을 찾지 못했다"], stats
    stats["front_lines"] = start
    body = lines[start:]
    margin = clause_margin(body)
    if margin is None:
        return [], ["번호 붙은 조항 줄을 찾지 못했다"], stats

    clauses: list[Clause] = []
    current: Clause | None = None
    article: tuple[int, str] | None = None
    appendix: tuple[str, str] | None = None
    last_number: tuple[int, ...] = ()
    title_lines_left = 0
    # 앞 제목 줄의 쪽, 위치, 가로 가운데, 왼쪽 끝, 오른쪽 끝
    last_top: tuple[float, ...] = (0, 0.0, 0.0, 0.0, 0.0)
    # 지운 조·부록 제목으로 연 조항과, 그 제목을 만나기 전의 (조, 부록, 마지막 번호)
    struck_top: Clause | None = None
    struck_saved: tuple = (None, None, ())
    layout = text_layout([ln for ln in body if not ln.struck])
    texts = [ln for ln in body if not ln.image and not ln.struck]
    following = {id(a): b for a, b in zip(texts, texts[1:], strict=False)}
    # 줄마다 그 뒤 여백 열에서 처음 나오는 여러 단계 번호("16.1")
    next_numbered: dict[int, str] = {}
    upcoming = ""
    for ln in reversed(texts):
        next_numbered[id(ln)] = upcoming
        m = NUMBERED.match(ln.text)
        if m and is_clause_start(ln, margin):
            upcoming = m.group(1)

    def open_clause(clause: Clause) -> Clause:
        clauses.append(clause)
        return clause

    def close_struck() -> None:
        """지운 제목 아래에 지우지 않은 글이 없으면 그 조항을 없던 것으로 되돌린다.

        제목과 글을 모두 지운 조·부록(2022년 스포팅 규정 Issue 2의 부록 4, 6A)은 예전처럼 조항
        목록에 남지 않고, 다음 제목의 번호 순서도 지운 제목 앞의 번호로 본다.
        """
        nonlocal struck_top, current, article, appendix, last_number
        if struck_top is None:
            return
        if clauses and clauses[-1] is struck_top and not struck_top.lines + struck_top.images:
            clauses.pop()
            article, appendix, last_number = struck_saved
            current = clauses[-1] if clauses else None
        struck_top = None

    for line in body:
        if line.image:
            if current is not None:
                current.images.append(line.image)
            continue
        if line.struck:
            # 지운 조·부록 제목. 그 아래 지우지 않은 글이 이 조항에 모인다(끝에서 검사한다).
            struck_art = article_heading(line, section) if appendix is None else None
            struck_app = appendix_heading(line)
            if struck_art and at_margin(line, margin):
                close_struck()
                struck_saved = (article, appendix, last_number)
                number, title = struck_art
                article = (number, clean_heading(title))
                key, part, top_title = str(number), "body", article[1]
                last_number = (number,)
            elif struck_app:
                close_struck()
                struck_saved = (article, appendix, last_number)
                appendix = (struck_app[0], clean_heading(struck_app[1]))
                key, part, top_title = f"A{appendix[0]}", "appendix", appendix[1]
                last_number = ()
            else:
                continue
            current = open_clause(
                Clause(key, part, 1, line.page, top_title, key, top_title, struck=True)
            )
            struck_top = current
            stats["struck_headings"] += 1
            title_lines_left = 0
            continue
        expected = article[0] + 1 if article else None
        art = article_heading(line, section, expected) if appendix is None else None
        app = appendix_heading(line)
        if struck_top is not None and ((art and at_margin(line, margin)) or app):
            close_struck()
            expected = article[0] + 1 if article else None
            art = article_heading(line, section, expected) if appendix is None else None
        if art and -MARGIN_LEFT <= line.x0 - margin <= MARGIN_RIGHT:
            number, title = art
            if article and number <= article[0]:
                problems.append(
                    f"{line.page}쪽: 조 번호 순서가 어긋난다({article[0]} 다음 {number})"
                )
            elif article and number != article[0] + 1:
                problems.append(f"{line.page}쪽: 조 번호가 {article[0]}에서 {number}로 건너뛴다")
            article = (number, clean_heading(title))
            current = open_clause(
                Clause(str(number), "body", 1, line.page, article[1], str(number), article[1])
            )
            last_number = (number,)
            title_lines_left = TITLE_LINES
            last_top = (line.page, line.top, centre(line), line.x0, line.x1)
            continue
        if app:
            label, title = app
            if appendix and appendix_key(label) <= appendix_key(appendix[0]):
                problems.append(
                    f"{line.page}쪽: 부록 번호 순서가 어긋난다({appendix[0]} 다음 {label})"
                )
            appendix = (label, clean_heading(title))
            key = f"A{label}"
            current = open_clause(
                Clause(key, "appendix", 1, line.page, appendix[1], key, appendix[1])
            )
            last_number = ()
            title_lines_left = TITLE_LINES
            last_top = (line.page, line.top, centre(line), line.x0, line.x1)
            continue
        # 제목이 다음 줄로 넘어간 조·부록·조항 제목
        if (
            title_lines_left
            and current is not None
            and continues_heading(current, line, last_top, layout)
        ):
            current.heading = clean_heading(f"{current.heading} {line.text}")
            if current.level == 1:
                current.top_title = current.heading
                if appendix:
                    appendix = (appendix[0], current.heading)
                elif article:
                    article = (article[0], current.heading)
            last_top = (line.page, line.top, centre(line), line.x0, line.x1)
            title_lines_left -= 1
            continue
        title_lines_left = 0

        number, rest = numbered_start(line, margin, appendix is not None, last_number)
        if (
            number is None
            and appendix is not None
            and plain_appendix_section(line, margin, last_number, next_numbered.get(id(line), ""))
        ):
            m = APPENDIX_SECTION.match(line.text)
            number, rest = m.group(1), m.group(2).strip()
            stats["plain_sections"] += 1
        top_title = appendix[1] if appendix else (article[1] if article else "")
        # 다음 해 규정을 옮겨 적은 조에서도 그 조의 번호로 시작하는 번호("47.1 Changes to
        # Article 21.7")는 이 판의 조항이다. 나머지는 다음 해 규정의 번호다.
        if (
            number is not None
            and FUTURE_CHANGES.search(top_title)
            and (appendix is not None or not article or number_key(number)[0] != article[0])
        ):
            stats["future_change_numbers"] += 1
            number = None
        if number is not None and current is not None:
            parts = number_key(number)
            if struck_top is not None:
                # 제목은 지웠는데 그 아래 번호 붙은 조항은 지우지 않았다. 어느 쪽이 맞는지 추측하지
                # 않는다.
                problems.append(struck_problem(line.page, struck_top))
                struck_top = None
            if appendix is None and article and parts[0] != article[0]:
                problems.append(f"{line.page}쪽: {number}가 {article[0]}조 안에 있다")
            if parts <= last_number:
                problems.append(
                    f"{line.page}쪽: 조항 번호 순서가 어긋난다"
                    f"({'.'.join(map(str, last_number))} 다음 {number})"
                )
            last_number = parts
            heading = ""
            if rest and (line.rest_bold >= 0.8 or (appendix is not None and len(parts) == 1)):
                heading = clean_heading(rest)
            elif (section == "sporting" or not is_clause_start(line, margin)) and plain_heading(
                line, rest, following.get(id(line)), layout
            ):
                heading = clean_heading(rest)
                stats["plain_headings"] += 1
            if appendix is None:
                key, level = number, len(parts)
                top, title = str(article[0]), article[1]
            else:
                key, level = f"A{appendix[0]}-{number}", len(parts) + 1
                top, title = f"A{appendix[0]}", appendix[1]
            current = open_clause(Clause(key, current.part, level, line.page, heading, top, title))
            current.marked = line.marked
            if rest and not heading:
                current.lines.append(rest)
                current.line_pages.append(line.page)
            title_lines_left = 1 if heading and line.rest_bold >= 0.8 else 0
            last_top = (line.page, line.top, centre(line), line.x0, line.x1)
            continue
        if current is None:
            continue
        inline = NUMBERED.match(line.text)
        if inline:
            stats["inline_numbers"] += 1  # 본문이나 표 줄이 숫자로 시작한다(상호 참조 등)
            rest = inline.group(2) or ""
            if (
                number_key(inline.group(1)) in successors(last_number)
                and rest[:1].isupper()
                and not FUTURE_CHANGES.search(top_title)
            ):
                # 다음 번호와 소제목처럼 생긴 줄이 여백 열이 아닌 곳이나 표 안에 있다. 조항인지
                # 상호 참조나 표 칸인지 위치만으로 가를 수 없으므로 추측하지 않고 문제로 남긴다.
                where = "표 안 줄" if line.in_table else "들여 쓴 줄"
                problems.append(
                    f"{line.page}쪽: {where}이 다음 조항 번호로 시작한다({inline.group(1)})"
                )
        current.lines.append(line.text)
        current.line_pages.append(line.page)
        current.marked = current.marked or line.marked

    close_struck()
    stats.update(toc_check(lines[:start], clauses))
    keys = Counter(c.clause_no for c in clauses)
    for key, n in keys.items():
        if n > 1:
            problems.append(f"조항 번호 {key}가 {n}번 나온다")
    # 형제 번호가 건너뛰면 조항 하나를 앞 조항에 붙였을 수 있다(강조 상자 안의 번호). 렌더링한
    # 쪽에서 원문에도 번호가 빠져 있음을 확인한 곳만 build()가 VERIFIED_GAPS로 문제에서 뺀다.
    gaps = sibling_gaps(clauses)
    stats["number_gaps"] = len(gaps)
    problems += [gap_problem(*gap) for gap in gaps]
    for c in clauses:
        c.text, c.page_starts = join_lines(c.lines, c.line_pages)
        c.not_used = is_not_used(c)
        if c.struck:
            # 지운 제목 아래에 남은 글이 그 삭제를 알리는 말("-Void-", "[Note. ...]")뿐이면 효력
            # 없는 조항이다. 다른 글이나 그림이 남아 있으면 추측하지 않고 문제로 적는다.
            if struck_note(c):
                c.not_used = True
            elif struck_problem(c.page, c) not in problems:
                problems.append(struck_problem(c.page, c))
    return clauses, problems, stats


STRUCK_NOTE = re.compile(r"^[\[(]?\s*note\b", re.I)


def struck_note(clause: Clause) -> bool:
    """지운 조·부록 제목 아래에 남은 글이 없거나, 삭제를 알리는 말뿐이다.

    "-Void-"나 "Not used"(is_not_used), 또는 "Note"로 시작하는 한 문단("Note: This Article has
    been moved to Appendix 6", "[Note. The changes ... have now been incorporated ...]")이다.
    """
    text = clause.text.strip()
    if clause.images:
        return False
    if not text or is_not_used(clause):
        return True
    return bool(STRUCK_NOTE.match(text)) and len(text) <= 300


def struck_problem(page: int, clause: Clause) -> str:
    what = f"부록 {clause.clause_no[1:]}" if clause.part == "appendix" else f"{clause.clause_no}조"
    return f"{page}쪽: 취소선으로 지운 {what} 제목 뒤에 지우지 않은 글이 있다"


def plain_appendix_section(line: Line, margin: float, last: tuple[int, ...], upcoming: str) -> bool:
    """굵지 않게 찍힌 부록의 한 단계 소제목("16 Engine Cover Reference Volume")인지 본다.

    2022년 기술 규정 Issue 11-13의 부록 1 16과 Issue 11의 부록 4 2는 소제목이 다른 글꼴(Courier
    New, Times New Roman)로 찍혀 굵지 않다(렌더링한 쪽에서 확인). 아래를 모두 만족할 때만 소제목으로
    본다. 하나라도 어긋나면 본문 줄로 두고, 형제 번호 검사가 건너뛴 번호를 문제로 적는다.

    - 여백 열에서 시작하고 번호가 바로 앞 소제목 번호의 다음 번호다.
    - 그 뒤 여백 열에서 처음 나오는 여러 단계 번호가 이 번호의 첫 하위 번호("16.1")다.
    - 번호 뒤 글이 대문자로 시작하고 90자 이하이며 문장부호로 끝나지 않는다.
    """
    m = APPENDIX_SECTION.match(line.text)
    if not m or not last or not is_clause_start(line, margin):
        return False
    number, rest = int(m.group(1)), m.group(2).strip()
    if number != last[0] + 1 or upcoming != f"{number}.1":
        return False
    return bool(rest) and rest[:1].isupper() and len(rest) <= 90 and rest[-1] not in ".,;:"


def is_not_used(clause: Clause) -> bool:
    """효력 없는 조항: 제목이나 글이 "Not used", "VOID", "Deleted"뿐이다.

    효력 없는 부록 뒤에 그 까닭을 적은 "NOTE:" 문장이 붙은 경우(2021년 스포팅 규정 부록 6
    "-Void-")도 같다.
    """
    if NOT_USED.match(clause.heading or "") and not clause.text:
        return True
    marker, note, rest = clause.text.partition("NOTE")
    if note and NOT_USED.match(marker.strip(" -")) and rest.lstrip().startswith(":"):
        return True
    return bool(NOT_USED.match(clause.text.strip(" -")))


def centre(line: Line) -> float:
    return (line.x0 + line.x1) / 2


# 조·부록 제목의 둘째 줄이 연도로 시작할 수 있다("2020-2025 POWER UNIT HOMOLOGATION").
TITLE_YEAR = re.compile(r"^(?:19|20)\d\d(?:\s*[-\u2010-\u2015]\s*(?:19|20)\d\d)?\s+[A-Z]")


TITLE_LINES = 8  # 조·부록 제목이 이어질 수 있는 줄 수의 상한(굵은 대문자 줄이 이어지는 동안)
TITLE_GAP = 2.5  # 조·부록 제목 둘째 줄까지의 거리 상한(본문 줄 간격의 배수)


def continues_heading(
    clause: Clause, line: Line, last_top: tuple[float, ...], layout: Layout | None = None
) -> bool:
    """줄이 바로 앞 제목 줄의 뒷부분인지 본다.

    굵은 글이고, 표 안이 아니며, 번호나 항목 기호로 시작하지 않고(조·부록 제목의 연도는
    된다), 같은 쪽에서 앞 제목 줄 바로 밑(16pt 안)에 있어야 한다. 조·부록 제목이 비어
    있으면("APPENDIX 1" 다음 줄에 제목) 거리는 보지 않는다. 조·부록 제목은 대문자로만 쓰고,
    아래 경우에는 더 떨어져 있어도 된다.

    - 앞 제목 줄과 가로 가운데가 같은 가운데 맞춤 제목 줄은 40pt까지(스포팅 규정 부록 2).
    - 앞 제목 줄과 왼쪽 끝이 같은 왼쪽 맞춤 제목 줄은 본문 줄 간격의 TITLE_GAP배까지. 단 이 줄의
      첫 낱말이 앞 제목 줄 끝에 들어갈 자리가 없어야 한다(제목이 길어 줄을 바꾼 것이다). 2021년
      스포팅 규정 첫 판의 부록 3과 4는 제목 둘째 줄("COMPETITION", "SEASONS")이 첫 줄보다
      25.7pt 아래에 있다. 짧은 조 제목 아래의 굵은 대문자 알림("NOTE: A REVIEW IS ...", 2021년
      기술 규정 첫 판 13조)은 제목이 아니다.
    """
    if clause.lines or line.in_table or line.bold < 0.9:
        return False
    title_year = clause.level == 1 and TITLE_YEAR.match(line.text)
    if re.match(r"[\d(]|[a-z][.)]\s", line.text, re.I) and not title_year:
        return False
    if line.page != last_top[0]:
        return False
    gap = line.top - last_top[1]
    if clause.level > 1:
        return not clause.heading or gap <= 16
    if not is_title_text(line.text):
        return False
    centred = abs(centre(line) - last_top[2]) <= 12
    if not clause.heading or gap <= 16 or (centred and gap <= 40):
        return True
    if layout is None or abs(line.x0 - last_top[3]) > 2 or gap > TITLE_GAP * layout.line_gap:
        return False
    first = line.text.split()[0]
    width = (line.x1 - line.x0) * len(first) / max(1, len(line.text))
    return last_top[4] + width > layout.right_edge


def is_title_text(text: str) -> bool:
    """조·부록 제목의 둘째 줄로 볼 수 있는 글. 대문자로만 쓰고 번호로 시작하지 않는다."""
    if TITLE_YEAR.match(text):
        return text == text.upper()
    return text == text.upper() and not re.match(r"[\d(]|[a-z][.)]\s", text, re.I)


@dataclass
class Layout:
    line_gap: float  # 문단 안 줄 사이 간격(가장 흔한 값)
    right_edge: float  # 본문 줄의 오른쪽 끝(양쪽 맞춤 줄이 닿는 곳)


def text_layout(lines: list[Line]) -> Layout:
    gaps = Counter(
        round(b.top - a.top)
        for a, b in zip(lines, lines[1:], strict=False)
        if a.page == b.page and not a.image and not b.image and 6 <= b.top - a.top <= 30
    )
    ends = sorted(ln.x1 for ln in lines if not ln.in_table and not ln.image)
    return Layout(
        line_gap=float(gaps.most_common(1)[0][0]) if gaps else 12.0,
        right_edge=ends[int(len(ends) * 0.9)] if ends else 0.0,
    )


def plain_heading(line: Line, rest: str, following: Line | None, layout: Layout) -> bool:
    """굵지 않은 조항 소제목인지 본다.

    스포팅 규정은 번호만 굵게 찍고 소제목("30.1 Supply of tyres")은 본문과 같은 글꼴로 찍는다.
    2023년 기술 규정 12.5.2도 굵지 않다. 번호 뒤 글이 본문의 첫 줄인 조항과는 아래로 가른다.

    - 대문자로 시작하고 90자 이하이며 마침표·쉼표·쌍점·쌍반점으로 끝나지 않는다.
    - 줄이 오른쪽 끝까지 가지 않는다(본문 첫 줄은 양쪽 맞춤으로 끝까지 간다).
    - 다음 줄이 문단 간격(줄 간격의 1.15배 이상)만큼 떨어져 있다. 다음 줄이 다음 쪽이면 이
      조건은 보지 않는다. 문단 안 줄 간격의 비는 1.0 안팎이고 소제목 뒤는 1.23 이상이다.

    기술 규정은 소제목을 굵게 찍고, 마침표 없이 끝나는 한 줄 본문("11.3.2 All discs must ...")이
    있어 이 규칙을 쓰지 않는다. 여백 열에서 밀려 찍힌 줄(2023년 판 12.5.2)만 예외다.
    """
    if not rest or not rest[:1].isupper() or len(rest) > 90 or rest[-1] in ".,;:":
        return False
    if re.match(r"[A-Z][.)]\s", rest) or line.x1 > layout.right_edge - 30:
        return False
    if following is None or following.page != line.page:
        return True
    return following.top - line.top >= 1.15 * layout.line_gap


def successors(number: tuple[int, ...]) -> set[tuple[int, ...]]:
    """번호 다음에 올 수 있는 번호: 첫 하위 번호, 그리고 각 단계의 다음 번호."""
    if not number:
        return set()
    out = {(*number, 1)}
    for depth in range(2, len(number) + 1):
        out.add((*number[: depth - 1], number[depth - 1] + 1))
    return out


def numbered_start(
    line: Line, margin: float, in_appendix: bool, last: tuple[int, ...] = ()
) -> tuple[str | None, str]:
    """조항 시작 줄이면 (번호, 번호 뒤 글)."""
    m = NUMBERED.match(line.text)
    if (
        m
        and line.small_number
        and number_key(m.group(1)) in successors(last)
        and (not line.in_table or at_margin(line, margin))
    ):
        # 여백 열에서 밀려 찍힌 조항(2023년 판 12.5.2, 51.1). FIA는 조항 번호를 본문보다 작은
        # 글자로 찍고, 본문 속 상호 참조는 본문 글자 크기다. 다음 번호이면서 작은 글자면 조항이다.
        # 표로 읽힌 줄도 여백 열에서 시작하는 작은 글자의 다음 번호면 조항이다(칸 선이 있는 표
        # 안에 개정 강조로 조항이 통째로 들어간 경우).
        return m.group(1), (m.group(2) or "").strip()
    if not is_clause_start(line, margin):
        return None, ""
    if m:
        return m.group(1), (m.group(2) or "").strip()
    if in_appendix:
        # 부록의 한 단계 번호("1 General conditions")는 굵은 소제목일 때만 조항으로 본다.
        m = APPENDIX_SECTION.match(line.text)
        if m and line.rest_bold >= 0.8:
            return m.group(1), m.group(2).strip()
    return None, ""


def parse_document(path: Path, section: str) -> ParsedDocument:
    """규정 PDF 한 부를 조항 목록으로 나눈다. section은 "technical" 또는 "sporting"."""
    stats: Counter = Counter()
    lines: list[Line] = []
    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        for number, page in enumerate(pdf.pages, 1):
            page_result, page_stats = page_lines(page, number)
            stats.update(page_stats)
            body_lines = [
                ln for ln in page_result if ln.band == "body" and not ln.image and not ln.struck
            ]
            if len(body_lines) < 3 and (page.images or len(page.curves) + len(page.lines) > 10):
                stats["figure_pages"] += 1
            lines.extend(page_result)
    lines, stats["running_lines"] = drop_running_lines(lines, pages)
    clauses, problems, segment_stats = segment(lines, section)
    stats.update(segment_stats)
    if clauses and not any(c.part == "body" and c.level > 1 for c in clauses):
        problems.append("번호 붙은 조항이 하나도 없다")
    return ParsedDocument(path, pages, clauses, problems, dict(stats))


# --- 파싱 캐시 ---------------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parsed_cache_path(row: dict[str, str]) -> Path:
    from pipeline.config import RAW_DIR

    name = Path(row["url"]).name.rsplit(".", 1)[0]
    return (
        RAW_DIR / "fia" / "regulations" / "parsed" / row["season"] / row["section"] / f"{name}.json"
    )


@functools.cache
def cache_key() -> str:
    """파싱 캐시를 다시 쓸 수 있는 조건: 파서 판, pdfplumber 판, 이 파일의 sha256이 모두 같다.

    PARSER_VERSION을 올리는 것을 잊고 파서를 고쳐도 낡은 캐시를 쓰지 않는다.
    """
    source = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return f"{PARSER_VERSION}|pdfplumber {pdfplumber.__version__}|{source}"


def read_cache(row: dict[str, str], digest: str) -> dict | None:
    """원문 sha256과 캐시 키가 맞는 파싱 캐시. 없거나 낡았거나 깨졌으면 None."""
    cache = parsed_cache_path(row)
    if not cache.exists():
        return None
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("sha256") != digest or data.get("cache_key") != cache_key():
        return None
    return data


def parse_cached(row: dict[str, str], path: Path, digest: str | None = None) -> ParsedDocument:
    """파싱 결과를 data/raw/ 아래(커밋하지 않음)에 캐시한다.

    원문 sha256과 캐시 키(cache_key)가 같으면 캐시를 다시 쓴다. 캐시 파일은 원자적으로 쓴다(여러
    프로세스가 함께 데워도 반쯤 쓴 파일을 읽지 않는다).
    """
    from pipeline.http import write_atomic

    digest = digest or file_sha256(path)
    data = read_cache(row, digest)
    if data is not None:
        clauses = [Clause(**c) for c in data["clauses"]]
        return ParsedDocument(path, data["pages"], clauses, data["problems"], data["stats"])
    parsed = parse_document(path, row["section"])
    payload = {
        "sha256": digest,
        "cache_key": cache_key(),
        "parser_version": PARSER_VERSION,
        "pages": parsed.pages,
        "problems": parsed.problems,
        "stats": parsed.stats,
        "clauses": [{**asdict(c), "lines": [], "line_pages": []} for c in parsed.clauses],
    }
    write_atomic(parsed_cache_path(row), json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return parsed


def _parse_into_cache(job: tuple[dict[str, str], Path]) -> None:
    parse_cached(*job)


def warm_cache(jobs: list[tuple[dict[str, str], Path]], workers: int = 4) -> None:
    """캐시가 없거나 낡은 문서를 여러 프로세스로 미리 파싱한다(한 부에 10-20초 걸린다)."""
    todo = [(row, path) for row, path in jobs if path.exists() and not cache_is_fresh(row, path)]
    if len(todo) < 2:
        return
    with ProcessPoolExecutor(max_workers=min(workers, os.cpu_count() or 1)) as pool:
        list(pool.map(_parse_into_cache, todo))


def cache_is_fresh(row: dict[str, str], path: Path) -> bool:
    return read_cache(row, file_sha256(path)) is not None


# --- 판 순서와 비교 ----------------------------------------------------------------------


def version_key(row: dict[str, str]) -> str:
    return f"{row['version_date']}-{row['variant']}" if row["variant"] else row["version_date"]


def version_order(row: dict[str, str]) -> tuple:
    m = re.fullmatch(r"(\d+)([a-z]*)", row.get("issue", ""))
    issue = (int(m.group(1)), m.group(2)) if m else (-1, "")
    return (row["version_date"], issue, row["variant"])


def compared_text(clause: Clause) -> str:
    return normalise(f"{clause.heading}\n{clause.text}")


def similarity(a: str, b: str) -> float:
    """낱말 단위 순서 비교(difflib)의 유사도."""
    return round(difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio(), 4)


def same_content(a: Clause, b: Clause) -> bool:
    """소제목과 정규화한 글이 같고 그림이 같은 그림이다(images_match)."""
    return (a.heading, normalise(a.text)) == (b.heading, normalise(b.text)) and images_match(
        a.images, b.images
    )


def move_key(clause: Clause) -> tuple | None:
    """번호가 바뀐 조항을 같은 글로 찾을 때 쓰는 열쇠. 조·부록 행은 제외한다.

    글이 25자보다 짧으면 같은 글이 흔하므로 조 제목까지 같아야 한다.
    """
    if clause.level == 1:
        return None
    text = normalise(clause.text)
    key = (clause.part, clause.heading, text, clause.image_sha256)
    if len(text) < 25 and not clause.image_sha256:
        return (*key, clause.top_title.casefold())
    return key


MOVE_SIMILARITY = 0.8  # 번호가 바뀌면서 글도 고친 조항으로 볼 최소 유사도
WEAK_SIMILARITY = 0.5  # 같은 번호 짝이 이보다 덜 비슷하면 다른 조항일 수 있다
MOVE_MIN_WORDS = 6


class Matcher:
    """두 판의 조항을 짝짓는다. 결과는 old 번호 -> new 번호 사전이다.

    번호만으로 맞추면 조항을 하나 끼워 넣은 판에서 뒤 조항이 모두 "글이 완전히 바뀐 조항"으로
    나온다(2021년 스포팅 규정은 스프린트 조를 넣으며 옛 36-46조를 37-56조로 밀었다). 그래서
    아래 순서로 맞춘다.

    1. 같은 번호이고 글이 같다(변경 없음).
    2. 다른 번호에 같은 글이 한 번씩만 있다(번호만 바뀜).
    3. 같은 조나 같은 제목의 조 안에서 다른 번호의 조항이 MOVE_SIMILARITY 이상 비슷하고, 같은
       번호의 짝은 WEAK_SIMILARITY보다 덜 비슷하다(번호가 바뀌고 글도 고침).
    4. 조와 부록 행은 1-3의 하위 조항이 가장 많이 옮겨 간 조와 짝짓는다. 하위 조항이 없으면
       같은 제목, 그다음 같은 번호의 조와 짝짓는다.
    5. 남은 조항은 같은 번호끼리 짝짓는다. 단 4에서 두 조가 서로 다른 조와 짝지어졌으면 같은
       번호라도 다른 조항이다.
    """

    def __init__(self, old: list[Clause], new: list[Clause]) -> None:
        self.old = [c for c in old if not c.not_used]
        self.new = [c for c in new if not c.not_used]
        self.old_by = {c.clause_no: c for c in self.old}
        self.new_by = {c.clause_no: c for c in self.new}
        self.pairs: dict[str, str] = {}
        self.taken: set[str] = set()
        self._words: dict[int, list[str]] = {}

    def pair(self, a: Clause, b: Clause) -> None:
        self.pairs[a.clause_no] = b.clause_no
        self.taken.add(b.clause_no)

    def free(self, side: str) -> list[Clause]:
        if side == "old":
            return [c for c in self.old if c.clause_no not in self.pairs]
        return [c for c in self.new if c.clause_no not in self.taken]

    def words(self, clause: Clause) -> list[str]:
        if id(clause) not in self._words:
            self._words[id(clause)] = compared_text(clause).split()
        return self._words[id(clause)]

    def ratio(self, a: Clause, b: Clause) -> float:
        return difflib.SequenceMatcher(None, self.words(a), self.words(b), autojunk=False).ratio()

    def same_number_ratio(self, clause: Clause, other_by: dict[str, Clause], free: set) -> float:
        partner = other_by.get(clause.clause_no)
        if partner is None or partner.clause_no not in free:
            return 0.0
        return self.ratio(*((clause, partner) if other_by is self.new_by else (partner, clause)))

    def run(self) -> dict[str, str]:
        for a in self.old:
            b = self.new_by.get(a.clause_no)
            if b is not None and same_content(a, b):
                self.pair(a, b)
        self.match_identical()
        self.match_similar()
        align = self.align_articles()
        back = {v: k for k, v in align.items()}
        for a in self.free("old"):
            b = self.new_by.get(a.clause_no)
            if b is None or b.clause_no in self.taken:
                continue
            if align.get(a.top_article, b.top_article) != b.top_article:
                continue
            if back.get(b.top_article, a.top_article) != a.top_article:
                continue
            self.pair(a, b)
        return self.pairs

    def match_identical(self) -> None:
        groups: dict[tuple, list[list[Clause]]] = {}
        for index, side in enumerate(("old", "new")):
            for c in self.free(side):
                key = move_key(c)
                if key is not None:
                    groups.setdefault(key, [[], []])[index].append(c)
        for olds, news in groups.values():
            if len(olds) == 1 and len(news) == 1:
                self.pair(olds[0], news[0])

    def match_similar(self) -> None:
        olds = [c for c in self.free("old") if c.level > 1]
        news = [c for c in self.free("new") if c.level > 1]
        free_old = {c.clause_no for c in olds}
        free_new = {c.clause_no for c in news}
        pool: dict[str, list[Clause]] = {}
        for b in news:
            pool.setdefault(f"#{b.top_article}", []).append(b)
            pool.setdefault(f"T{b.top_title.casefold()}", []).append(b)
        candidates = []
        for a in olds:
            if len(self.words(a)) < MOVE_MIN_WORDS:
                continue
            seen: set[str] = set()
            for b in pool.get(f"#{a.top_article}", []) + pool.get(f"T{a.top_title.casefold()}", []):
                if b.clause_no in seen or b.clause_no == a.clause_no or b.part != a.part:
                    continue
                seen.add(b.clause_no)
                if len(self.words(b)) < MOVE_MIN_WORDS:
                    continue
                wa, wb = self.words(a), self.words(b)
                matcher = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
                if min(matcher.real_quick_ratio(), matcher.quick_ratio()) < MOVE_SIMILARITY:
                    continue
                score = matcher.ratio()
                if score >= MOVE_SIMILARITY:
                    candidates.append((score, a, b))
        candidates.sort(key=lambda t: (-t[0], clause_sort_key(t[1].clause_no), t[2].clause_no))
        for _, a, b in candidates:
            if a.clause_no in self.pairs or b.clause_no in self.taken:
                continue
            left_old, left_new = free_old - set(self.pairs), free_new - self.taken
            if self.same_number_ratio(a, self.new_by, left_new) >= WEAK_SIMILARITY:
                continue
            if self.same_number_ratio(b, self.old_by, left_old) >= WEAK_SIMILARITY:
                continue
            self.pair(a, b)

    def align_articles(self) -> dict[str, str]:
        """옛 조(부록) -> 새 조(부록). 조 행도 여기서 짝짓는다."""
        votes = Counter(
            (self.old_by[o].top_article, self.new_by[n].top_article)
            for o, n in self.pairs.items()
            if self.old_by[o].level > 1
        )
        align: dict[str, str] = {}
        ordered = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0][0] != kv[0][1], kv[0]))
        for (a, b), _ in ordered:
            if a not in align and b not in align.values():
                align[a] = b
        old_tops = {c.clause_no: c for c in self.old if c.level == 1}
        new_tops = {c.clause_no: c for c in self.new if c.level == 1}
        titles: dict[str, list[str]] = {}
        for no, c in new_tops.items():
            titles.setdefault(c.top_title.casefold(), []).append(no)
        for rule in ("title", "number"):
            for no, c in old_tops.items():
                if no in align:
                    continue
                if rule == "title":
                    same = titles.get(c.top_title.casefold(), [])
                    target = same[0] if len(same) == 1 else None
                else:
                    target = no if no in new_tops else None
                if target is not None and target not in align.values():
                    align[no] = target
        for a, b in align.items():
            if a in old_tops and b in new_tops and a not in self.pairs and b not in self.taken:
                self.pair(old_tops[a], new_tops[b])
        return align


def compare(old: list[Clause], new: list[Clause]) -> tuple[list[dict], dict[str, int]]:
    """두 판의 조항을 짝지어(Matcher) 바뀐 조항만 돌려준다. 셈도 함께 돌려준다.

    효력 없는 조항("Not used", "VOID")은 없는 조항과 같게 본다. 그래서 본문이 있던 조항이
    "Not used"로 바뀌면 removed, 그 반대면 added다. 짝지어진 두 조항은 번호, 소제목, 글, 그림
    가운데 하나라도 다르면 modified다. 번호가 바뀐 행은 renumbered가 참이고 from_clause_no가 옛
    번호다. 번호만 바뀌고 글이 같으면 similarity는 1이다. change 값은 명세대로 세 가지만 쓴다.
    """
    matcher = Matcher(old, new)
    pairs = matcher.run()
    rows = []
    unchanged = 0
    for a in matcher.old:
        b = matcher.new_by[pairs[a.clause_no]] if a.clause_no in pairs else None
        if b is None:
            rows.append(change_row(a, None, "removed"))
        elif same_content(a, b) and a.clause_no == b.clause_no:
            unchanged += 1
        else:
            rows.append(change_row(a, b, "modified", matcher.ratio(a, b)))
    rows += [change_row(None, b, "added") for b in matcher.new if b.clause_no not in matcher.taken]
    rows.sort(key=lambda r: (clause_sort_key(r["clause_no"]), r["from_clause_no"] or ""))
    counts = Counter(r["change"] for r in rows)
    totals = {
        **{k: counts[k] for k in CHANGE_KINDS},
        "renumbered": sum(r["renumbered"] for r in rows),
        "unchanged": unchanged,
    }
    return rows, totals


CHANGE_KINDS = ("added", "removed", "modified")


def change_row(a: Clause | None, b: Clause | None, change: str, sim: float | None = None) -> dict:
    ref = b or a
    return {
        "clause_no": ref.clause_no, "from_clause_no": a.clause_no if a else None,
        "top_article": ref.top_article, "top_title": ref.top_title, "heading": ref.heading,
        "change": change, "similarity": None if sim is None else round(sim, 4),
        "renumbered": bool(a and b and a.clause_no != b.clause_no),
        "images_changed": bool(a and b and not images_match(a.images, b.images)),
        "chars_from": a.char_count if a else None, "chars_to": b.char_count if b else None,
        "page_from": a.page if a else None, "page_to": b.page if b else None,
    }  # fmt: skip


def clause_sort_key(clause_no: str) -> tuple:
    """본문 조항을 먼저, 부록을 뒤에 두는 번호 순서."""
    if clause_no.startswith("A"):
        label, _, rest = clause_no[1:].partition("-")
        return (1, appendix_key(label), number_key(rest) if rest else ())
    return (0, (0, ""), number_key(clause_no))


# --- 규정에서 읽는 사실 ------------------------------------------------------------------

PU_ELEMENT = re.compile(
    r"(?P<count>\w+(?:\s*\(\d+\))?)\s+(?P<name>engines|turbochargers|energy stores|"
    r"control electronics|motor generator\s*units?\s*-\s*heat|"
    r"motor generator\s*units?\s*-\s*kinetic)"
    r"\s*\((?P<code>ICE|TC|ES|CE|MGU-H|MGU-K)\)",
    re.I,
)
EXHAUST = re.compile(
    r"(?P<count>\w+(?:\s*\(\d+\))?)\s+of each of the four \(4\) elements constituting a set of "
    r"Engine exhaust systems",
    re.I,
)
WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10,
}  # fmt: skip
QUOTE_LIMIT = 200


def count_value(text: str) -> int | None:
    m = re.search(r"\((\d+)\)", text)
    if m:
        return int(m.group(1))
    word = text.split()[0].casefold()
    if word.isdigit():
        return int(word)
    return WORD_NUMBERS.get(word)


def quote(text: str, start: int, end: int) -> str:
    """사실 근거 인용. 원문 그대로(공백만 정리), 200자 이하."""
    return text[start:end][:QUOTE_LIMIT]


def pu_allocation(clauses: list[Clause]) -> list[dict]:
    """스포팅 규정에서 시즌 동안 페널티 없이 쓸 수 있는 PU 구성요소 수를 읽는다.

    "each driver may use no more than ..."으로 시작하는 첫 문장만 읽는다. 같은 조항 뒤쪽의 조건부
    할당(2020년 판: 경주 수가 14회 이하, 11회 이하로 줄면 쓰는 수)은 기본 할당이 아니므로
    읽지 않는다.
    """
    for clause in clauses:
        text = clause.text
        lead = re.search(r"each driver may use no more than", text, re.I)
        if not lead:
            continue
        end = text.find(". ", lead.start())
        span_end = end if end != -1 else len(text)
        span = text[lead.start() : span_end]
        if "(ICE)" not in span:
            continue
        rows = []
        for m in PU_ELEMENT.finditer(span):
            value = count_value(m.group("count"))
            if value is None:
                continue
            start = lead.start() if not rows else lead.start() + m.start()
            rows.append(
                fact_row(clause, start, lead.start() + m.end(), m.group("code").upper(), value)
            )
        m = EXHAUST.search(span)
        if m and (value := count_value(m.group("count"))) is not None:
            rows.append(
                fact_row(clause, lead.start() + m.start(), lead.start() + m.end(), "EX", value)
            )
        if rows:
            return rows
    return []


def fact_row(clause: Clause, start: int, end: int, element: str, value: int) -> dict:
    return {
        "element": element, "allowed": value, "clause_no": clause.clause_no,
        "page": page_at(clause, start), **quote_fields(clause, start, end),
    }  # fmt: skip


def quote_fields(clause: Clause, start: int, end: int) -> dict:
    """인용과, 원문 캐시 없이도 인용의 근거를 맞춰 볼 수 있는 값.

    quote_start는 조항 글(정규형) 안에서 인용이 시작하는 위치이고, text_sha256은 그 조항 글의
    해시(articles.parquet의 text_sha256과 같은 값)다. CI처럼 파싱 캐시가 없는 곳에서는 인용이
    그 조항의 그 판 글에서 나왔고 글 길이 안에 있는지까지만 본다. 인용이 조항 글의 일부를 그대로
    옮겼는지는 캐시가 있을 때만 본다(test_quotes_are_substrings_of_their_clause).
    """
    text = quote(clause.text, start, end)
    lead = len(text) - len(text.lstrip())
    return {
        "quote": text.strip(), "quote_start": start + lead, "text_sha256": clause.text_sha256,
    }  # fmt: skip


FUEL_RACE = re.compile(r"[^.]*\b110\s?kg\b[^.]*\.", re.I)
FUEL_FLOW = re.compile(r"Fuel mass flow must not exceed (\d+)\s?kg/h\.?", re.I)


def fuel_rules(clauses: list[Clause]) -> list[dict]:
    """경주에서 쓸 수 있는 연료 질량(110kg) 조항과, 그 곁의 최대 연료 유량 조항."""
    rows = []
    for i, clause in enumerate(clauses):
        m = FUEL_RACE.search(clause.text)
        if m and re.search(r"fuel", m.group(0), re.I):
            rows.append(fuel_row(clause, "race_fuel_mass", "110 kg", m))
            # 바로 곁(앞뒤 조항)의 연료 유량 조항
            for near in clauses[max(0, i - 1) : i + 2]:
                flow = FUEL_FLOW.search(near.text)
                if flow:
                    rows.append(fuel_row(near, "max_fuel_mass_flow", f"{flow.group(1)} kg/h", flow))
    return rows


def fuel_row(clause: Clause, rule: str, value: str, m: re.Match) -> dict:
    return {
        "rule": rule, "value": value, "clause_no": clause.clause_no,
        "page": page_at(clause, m.start()), **quote_fields(clause, m.start(), m.end()),
    }  # fmt: skip


def flow_rules(clauses: list[Clause]) -> list[dict]:
    """110kg 조항 곁에 연료 유량 조항이 없는 시즌에 기술 규정의 최대 연료 유량 조항을 찾는다."""
    for clause in clauses:
        m = FUEL_FLOW.search(clause.text)
        if m:
            return [fuel_row(clause, "max_fuel_mass_flow", f"{m.group(1)} kg/h", m)]
    return []


# --- 정제 테이블 만들기 -----------------------------------------------------------------

# 렌더링한 쪽에서 원문에도 형제 번호가 빠져 있음을 확인한 곳. 여기 있는 건너뜀만 문제에서 뺀다.
# (시즌, 구분, 판 키) -> {(앞 번호, 뒤 번호): 확인 내용}
A10_NOTE = (
    "부록 10은 본문 30조를 바꿔 쓰는 부록이라 번호가 30.1부터 시작한다"
    "(Issue 6 110쪽, Issue 7 113쪽 렌더링으로 확인)"
)
VERIFIED_GAPS: dict[tuple[int, str, str], dict[tuple[str, str], str]] = {
    (2022, "sporting", "2022-04-29"): {("A10", "A10-30"): A10_NOTE},
    (2022, "sporting", "2022-06-29"): {("A10", "A10-30"): A10_NOTE},
}

# 렌더링한 쪽에서 확인한 원문의 번호 오류. 정책대로 문서는 needs_review로 두고, 그 번호에 대한
# 문제 글(순서 어긋남, 겹친 번호)을 아래 설명 하나로 바꾼다. 사이트는 이 글로 원문 오류임을 밝힌다.
SOURCE_NUMBERING_ERRORS: dict[tuple[int, str, str], dict[str, str]] = {
    (2021, "sporting", "2020-12-16"): {
        "42.12": (
            "47쪽: 원문 번호 오류(렌더링한 쪽에서 확인). 원문에 42.12가 두 번 찍혀 있다. 다음 판"
            "(2021-02-19)은 두 번째 조항을 42.13으로 고쳐 매겼다"
        ),
    },
    (2025, "sporting", "2025-04-30"): {
        "23.6": (
            "25쪽: 원문 번호 오류(렌더링한 쪽에서 확인). 원문에 23.6이 두 번 찍혀 있고 두 번째 "
            "23.6은 이 판에 새로 넣은 분홍 글이다"
        ),
    },
}


def review_problems(key: tuple[int, str, str], problems: list[str]) -> list[str]:
    """파서가 적은 문제에 확인 결과를 반영한다.

    VERIFIED_GAPS에 있는 건너뜀은 뺀다. SOURCE_NUMBERING_ERRORS의 번호에 대한 문제는 그 설명으로
    바꾼다(문제는 남는다).
    """
    allowed = VERIFIED_GAPS.get(key, {})
    errors = SOURCE_NUMBERING_ERRORS.get(key, {})
    out: list[str] = []
    for problem in problems:
        gap = GAP_PROBLEM.match(problem)
        if gap and (gap.group(2), gap.group(3)) in allowed:
            continue
        hit = next(
            (
                no
                for no in errors
                if f"({no} 다음 {no})" in problem or problem.startswith(f"조항 번호 {no}가 ")
            ),
            None,
        )
        if hit is None:
            out.append(problem)
        elif errors[hit] not in out:
            out.append(errors[hit])
    return out


class ShrinkError(RuntimeError):
    """캐시에 원문이 없어 커밋된 정제 데이터가 줄어들 상황. 아무 파일도 쓰지 않는다."""


def check_shrink(previous: list[dict], current: list[dict], allow_shrink: bool = False) -> None:
    """새 문서 목록이 커밋된 목록(documents.csv)보다 줄어들면 쓰기 전에 멈춘다.

    - ok 문서가 하나도 없으면 언제나 멈춘다(새로 받은 저장소나 CI 캐시가 빈 경우).
    - 전에 ok였던 판이 not_downloaded가 되면 멈춘다. allow_shrink가 참일 때만 그대로 쓴다.
    전에 ok였던 판이 needs_review가 되는 것은 파서 검사의 결과이므로 막지 않는다.
    """
    if not any(d["status"] == "ok" for d in current):
        raise ShrinkError(
            "파싱된(ok) 문서가 하나도 없어 정제 테이블을 쓰지 않는다. 원문 캐시를 확인한다"
        )
    was_ok = {
        (int(r["season"]), r["section"], str(r["version_key"]))
        for r in previous
        if r.get("status") == "ok"
    }
    lost = sorted(
        (int(d["season"]), d["section"], str(d["version_key"]))
        for d in current
        if d["status"] == "not_downloaded"
        and (int(d["season"]), d["section"], str(d["version_key"])) in was_ok
    )
    if lost and not allow_shrink:
        listed = ", ".join(f"{s} {sec} {v}" for s, sec, v in lost[:5])
        more = f" 외 {len(lost) - 5}건" if len(lost) > 5 else ""
        raise ShrinkError(
            f"전에 ok였던 {len(lost)}개 판의 원문이 캐시에 없다({listed}{more}). "
            "원문을 받은 뒤 다시 돌리거나, 줄이려는 것이면 --allow-shrink를 쓴다"
        )


def read_previous_documents(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build(only_cached: bool = False, allow_shrink: bool = False) -> dict[str, int]:
    """manifest의 기술·스포팅 규정을 파싱해 조항, 변경 목록, 사실 테이블과 실패 목록을 쓴다.

    only_cached=False면 먼저 fia_regulations.download()로 빠진 원문을 받는다. True면 캐시에 있는
    원문만 처리하고 나머지는 not_downloaded로 적는다(파싱 실패가 아니다). 그 결과가 커밋된
    documents.csv보다 줄어들면 아무것도 쓰지 않고 멈춘다(check_shrink).
    """
    import pandas as pd

    from pipeline import manifest
    from pipeline.config import CURATED_DIR
    from pipeline.http import utc_now_iso
    from pipeline.sources import fia_regulations

    if not only_cached:
        fia_regulations.download()
    rows = [
        r
        for r in manifest.read_rows(fia_regulations.MANIFEST)
        if r["section"] in fia_regulations.PARSED_SECTIONS
    ]
    rows.sort(key=lambda r: (int(r["season"]), r["section"], version_order(r)))

    warm_cache([(r, fia_regulations.local_path(r)) for r in rows])
    doc_rows, article_rows, failures = [], [], []
    parsed: dict[tuple[int, str, str], ParsedDocument] = {}
    for row in rows:
        season, section, vkey = int(row["season"]), row["section"], version_key(row)
        path = fia_regulations.local_path(row)
        base = {
            "season": season, "section": section, "issue": row["issue"],
            "variant": row["variant"], "version_key": vkey, "version_date": row["version_date"],
            "published_at": row["published_at"], "url": row["url"],
        }  # fmt: skip
        if not path.exists():
            doc_rows.append({**base, "pages": None, "clauses": None, "characters": None,
                             "status": "not_downloaded", "problems": "", "pdf_sha256": "",
                             "sha256_check": ""})  # fmt: skip
            continue
        digest = file_sha256(path)
        problems: list[str] = []
        if not row.get("sha256"):
            check = "manifest_missing"  # manifest에 아직 sha256이 없다(받은 뒤 기록 전)
        elif row["sha256"] == digest:
            check = "match"
        else:
            check = "differs"
            problems.append("원문이 manifest의 sha256과 다르다")
        if check == "differs":
            doc = ParsedDocument(path, 0, [], [], {})
        else:
            doc = parse_cached(row, path, digest)
        problems += review_problems((season, section, vkey), doc.problems)
        if not doc.clauses and not problems:
            problems.append("조항을 하나도 읽지 못했다")
        status = "needs_review" if problems else "ok"
        doc_rows.append(
            {
                **base, "pages": doc.pages, "clauses": len(doc.clauses),
                "characters": sum(c.char_count for c in doc.clauses), "status": status,
                "problems": summarise(problems), "pdf_sha256": digest, "sha256_check": check,
                **{name: doc.stats.get(name, 0) for name in DOCUMENT_STATS},
            }
        )  # fmt: skip
        if problems:
            failures.append(
                {
                    "season": season, "round": "", "event": f"{section} {vkey}",
                    "doc_type": DOC_TYPES[section], "url": row["url"],
                    "problems": summarise(problems), "recorded_at": utc_now_iso()[:10],
                }
            )  # fmt: skip
            continue
        parsed[(season, section, vkey)] = doc
        for c in doc.clauses:
            article_rows.append(
                {
                    "season": season, "section": section, "version_key": vkey,
                    "clause_no": c.clause_no, "top_article": c.top_article,
                    "top_title": c.top_title, "heading": c.heading, "level": c.level,
                    "page": c.page, "char_count": c.char_count, "text_sha256": c.text_sha256,
                    "images": len(c.images), "image_sha256": c.image_sha256,
                    "not_used": c.not_used,
                    "marked": c.marked,
                    "struck": c.struck,
                }
            )  # fmt: skip

    out = CURATED_DIR / "regulations"
    check_shrink(read_previous_documents(out / "documents.csv"), doc_rows, allow_shrink)
    change_rows, comparison_rows = build_changes(rows, parsed)
    pu_rows, fuel = build_facts(rows, parsed)
    out.mkdir(parents=True, exist_ok=True)
    documents = pd.DataFrame(doc_rows, columns=DOCUMENT_COLUMNS)
    for column in ("pages", "clauses", "characters", *DOCUMENT_STATS):
        documents[column] = documents[column].astype("Int64")
    documents.to_csv(out / "documents.csv", index=False)
    articles = pd.DataFrame(article_rows, columns=ARTICLE_COLUMNS)
    articles.to_parquet(out / "articles.parquet", index=False, compression="zstd")
    changes = pd.DataFrame(change_rows, columns=CHANGE_COLUMNS)
    changes.to_parquet(out / "changes.parquet", index=False, compression="zstd")
    pd.DataFrame(comparison_rows, columns=COMPARISON_COLUMNS).to_csv(
        out / "comparisons.csv", index=False
    )
    pd.DataFrame(pu_rows, columns=PU_COLUMNS).to_csv(out / "pu_allocation_rules.csv", index=False)
    pd.DataFrame(fuel, columns=FUEL_COLUMNS).to_csv(out / "fuel_rules.csv", index=False)
    write_failures(failures)
    return {
        "documents": len(doc_rows),
        "parsed": len(parsed),
        "not_downloaded": sum(d["status"] == "not_downloaded" for d in doc_rows),
        "needs_review": len(failures),
        "clauses": len(article_rows),
        "comparisons": len(comparison_rows),
        "comparisons_with_skipped": sum(bool(c["skipped_versions"]) for c in comparison_rows),
        "changes": len(change_rows),
        "pu_rules": len(pu_rows),
        "fuel_rules": len(fuel),
    }


# 문서마다 남기는 셈: 건너뛴 표와 도면 쪽, 뺀 취소선 글자·머리말·꼬리말·목차 줄, 목차 대조 결과,
# 번호 검사(형제 번호 건너뜀, 줄 머리 숫자, 굵지 않은 소제목), 취소선으로 지운 조·부록 제목
DOCUMENT_STATS = [
    "tables", "figure_pages", "struck_chars", "marked_chars", "rotated_chars",
    "rotated_table_chars", "fill_blocks", "running_lines", "front_lines", "toc_not_in_body",
    "body_not_in_toc", "number_gaps", "inline_numbers", "plain_headings", "plain_sections",
    "struck_headings",
]  # fmt: skip
DOCUMENT_COLUMNS = [
    "season", "section", "issue", "variant", "version_key", "version_date", "published_at", "url",
    "pages", "clauses", "characters", "status", "problems", "pdf_sha256", "sha256_check",
    *DOCUMENT_STATS,
]  # fmt: skip
ARTICLE_COLUMNS = [
    "season", "section", "version_key", "clause_no", "top_article", "top_title", "heading",
    "level", "page", "char_count", "text_sha256", "images", "image_sha256", "not_used", "marked",
    "struck",
]  # fmt: skip
CHANGE_COLUMNS = [
    "kind", "section", "from_season", "from_version", "to_season", "to_version", "clause_no",
    "from_clause_no", "top_article", "top_title", "heading", "change", "similarity", "renumbered",
    "images_changed", "chars_from", "chars_to", "page_from", "page_to",
]  # fmt: skip
COMPARISON_COLUMNS = [
    "kind", "section", "from_season", "from_version", "to_season", "to_version", "clauses_from",
    "clauses_to", "added", "removed", "modified", "unchanged", "renumbered", "skipped_versions",
]  # fmt: skip
FACT_SOURCE = ["season", "version_key", "is_final_issue"]
QUOTE_SOURCE = ["quote", "quote_start", "text_sha256"]
PU_COLUMNS = [*FACT_SOURCE, "element", "allowed", "clause_no", "page", "url", *QUOTE_SOURCE]
FUEL_COLUMNS = [*FACT_SOURCE, "section", "rule", "value", "clause_no", "page", "url", *QUOTE_SOURCE]
PU_SEASONS = range(2020, 2026)
# 110kg(경주 연료 질량)는 2019-2021년 스포팅 규정 30.5에 있다. 2022-2025년 판에는 없어 그 시즌은
# 기술 규정의 최대 연료 유량 조항만 적는다.
FUEL_SEASONS = range(2019, 2026)


def summarise(problems: list[str], limit: int = 250) -> str:
    """문제 목록을 한 칸에 적는다. 길면 앞부분만 적고 나머지는 건수로 남긴다."""
    out: list[str] = []
    for i, problem in enumerate(problems):
        if out and len(" / ".join([*out, problem])) > limit:
            return " / ".join(out) + f" / 외 {len(problems) - i}건"
        out.append(problem)
    return " / ".join(out)


def doc_key(row: dict) -> tuple[int, str, str]:
    return int(row["season"]), row["section"], version_key(row)


def skipped_label(row: dict) -> str:
    return f"{row['season']}:{version_key(row)}"


def version_pairs(rows: list[dict], parsed: dict) -> list[tuple[str, dict, dict, list[str]]]:
    """비교할 판의 쌍과 그 사이에 건너뛴 판.

    - "issue": 같은 시즌에서 파싱된(ok) 판끼리 차례로 짝짓는다. 사이에 needs_review이거나 받지 않은
      판이 있으면 그 판들을 건너뛴 판으로 적는다. 그 구간의 변경은 두 판의 차이로 한꺼번에 나온다.
    - "season": 이웃 시즌의 마지막으로 파싱된 판끼리. 시즌의 마지막 판이 파싱되지 않았으면 그
      판(들)을 건너뛴 판으로 적는다.

    - 시즌의 첫 파싱된 판보다 앞선 파싱되지 않은 판(앞 판)은 그 시즌으로 들어오는 season 비교에
      적는다. 그 비교가 없으면(앞 시즌에 파싱된 판이 없다) 그 시즌의 첫 issue 비교에 적는다.
    - 시즌의 마지막 파싱된 판보다 늦은 파싱되지 않은 판(뒤 판)은 그 시즌에서 나가는 season 비교에
      적는다. 그 비교가 없으면(다음 시즌이 없거나 파싱된 판이 없다) 그 시즌의 마지막 issue 비교에
      적는다.

    그래서 시즌에 비교가 하나라도 있으면 그 시즌의 파싱되지 않은 판은 모두 어느 비교의 건너뛴
    판에 나온다. 건너뛴 판은 "시즌:판 키"로 적고, 한 비교 안에서는 판 순서대로 적는다.
    """
    by_series: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        by_series.setdefault((row["section"], int(row["season"])), []).append(row)
    ordered = {key: sorted(series, key=version_order) for key, series in by_series.items()}
    done = {key: [i for i, r in enumerate(s) if doc_key(r) in parsed] for key, s in ordered.items()}

    def leading(key: tuple[str, int]) -> list[dict]:
        return ordered[key][: done[key][0]] if done.get(key) else []

    def trailing(key: tuple[str, int]) -> list[dict]:
        return ordered[key][done[key][-1] + 1 :] if done.get(key) else []

    def has_season_pair(section: str, season: int) -> bool:
        return bool(done.get((section, season))) and bool(done.get((section, season + 1)))

    pairs = []
    for (section, season), series in sorted(ordered.items()):
        key = (section, season)
        marks = done[key]
        issues = []
        for i, j in zip(marks, marks[1:], strict=False):
            issues.append(["issue", series[i], series[j], series[i + 1 : j]])
        if issues and not has_season_pair(section, season - 1):
            issues[0][3] = leading(key) + issues[0][3]
        if issues and not has_season_pair(section, season):
            issues[-1][3] = issues[-1][3] + trailing(key)
        pairs += [(kind, a, b, [skipped_label(r) for r in s]) for kind, a, b, s in issues]
        if has_season_pair(section, season):
            nxt = (section, season + 1)
            skipped = trailing(key) + leading(nxt) + trailing(nxt)
            pairs.append(
                (
                    "season",
                    series[marks[-1]],
                    ordered[nxt][done[nxt][-1]],
                    [skipped_label(r) for r in skipped],
                )
            )
    return pairs


def latest_parsed(series: list[dict], parsed: dict) -> dict | None:
    done = [r for r in series if doc_key(r) in parsed]
    return done[-1] if done else None


def build_changes(rows: list[dict], parsed: dict) -> tuple[list[dict], list[dict]]:
    change_rows, comparison_rows = [], []
    for kind, a, b, skipped in version_pairs(rows, parsed):
        old, new = parsed[doc_key(a)], parsed[doc_key(b)]
        key = {
            "kind": kind, "section": a["section"], "from_season": int(a["season"]),
            "from_version": version_key(a), "to_season": int(b["season"]),
            "to_version": version_key(b),
        }  # fmt: skip
        diffs, counts = compare(old.clauses, new.clauses)
        comparison_rows.append(
            {
                **key,
                "clauses_from": sum(not c.not_used for c in old.clauses),
                "clauses_to": sum(not c.not_used for c in new.clauses),
                **counts,
                "skipped_versions": ";".join(skipped),
            }
        )
        change_rows += [{**key, **d} for d in diffs]
    return change_rows, comparison_rows


def fact_source(rows: list[dict], season: int, section: str, parsed: dict) -> dict | None:
    """시즌의 마지막으로 파싱된 판과, 그것이 그 시즌의 마지막 판인지(is_final_issue)."""
    series = series_of(rows, season, section)
    row = latest_parsed(series, parsed)
    if row is None:
        return None
    return {
        "row": row,
        "season": season,
        "version_key": version_key(row),
        "is_final_issue": version_key(row) == version_key(series[-1]),
    }


def build_facts(rows: list[dict], parsed: dict) -> tuple[list[dict], list[dict]]:
    """시즌마다 마지막으로 파싱된 판에서 PU 할당 수와 연료 조항을 읽는다.

    시즌의 마지막 판이 파싱되지 않았으면(needs_review, 받지 않음) 그 앞 판에서 읽고
    is_final_issue를 거짓으로 적는다.
    """
    pu_rows, fuel = [], []

    def meta(source: dict) -> dict:
        return {k: source[k] for k in FACT_SOURCE}

    for season in PU_SEASONS:
        source = fact_source(rows, season, "sporting", parsed)
        if source:
            doc = parsed[doc_key(source["row"])]
            for fact in pu_allocation(doc.clauses):
                pu_rows.append({**meta(source), **fact, "url": source["row"]["url"]})
    for season in FUEL_SEASONS:
        for section in ("technical", "sporting"):
            source = fact_source(rows, season, section, parsed)
            if not source:
                continue
            doc = parsed[doc_key(source["row"])]
            for fact in fuel_rules(doc.clauses):
                fuel.append(
                    {**meta(source), "section": section, **fact, "url": source["row"]["url"]}
                )
    # 110kg 조항 곁에서 최대 연료 유량 조항을 찾지 못한 시즌은 기술 규정에서 찾는다.
    for season in FUEL_SEASONS:
        if any(f["season"] == season and f["rule"] == "max_fuel_mass_flow" for f in fuel):
            continue
        source = fact_source(rows, season, "technical", parsed)
        if source:
            doc = parsed[doc_key(source["row"])]
            for fact in flow_rules(doc.clauses):
                fuel.append(
                    {**meta(source), "section": "technical", **fact, "url": source["row"]["url"]}
                )
    fuel.sort(key=lambda f: (f["season"], f["section"], f["rule"], f["clause_no"]))
    return pu_rows, fuel


def series_of(rows: list[dict], season: int, section: str) -> list[dict]:
    return sorted(
        (r for r in rows if int(r["season"]) == season and r["section"] == section),
        key=version_order,
    )


FAILURE_FIELDS = ["season", "round", "event", "doc_type", "url", "problems", "recorded_at"]


def failure_order(row: dict) -> tuple:
    """실패 목록의 정렬 기준: 문서 유형, 시즌, 라운드, URL(라운드가 없으면 시즌 안에서 앞)."""

    def number(value: object) -> int:
        text = str(value if value is not None else "").strip()
        return int(text) if text.lstrip("-").isdigit() else -1

    return row["doc_type"], number(row["season"]), number(row["round"]), row["url"]


@contextlib.contextmanager
def failures_lock():
    """parse_failures.csv를 읽고 쓰는 동안 다른 파서 프로세스를 막는 잠금(data/raw/_locks/)."""
    from pipeline.config import RAW_DIR

    path = RAW_DIR / "_locks" / "parse_failures.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_failures(failures: list[dict]) -> None:
    """parse_failures.csv에서 규정 문서 행만 갈아 끼운다.

    다른 파서의 행은 그대로 두고, 처음 기록한 날짜는 유지한다. 잠금을 잡은 채 읽고, 정렬해서
    원자적으로 쓴다. 그래서 다른 파서가 같은 때 돌아도 서로의 행을 지우지 않고, 어느 파서가
    마지막에 돌았든 같은 내용이면 같은 파일이 된다.
    """
    from pipeline import manifest
    from pipeline.config import MANIFEST_DIR
    from pipeline.http import write_atomic

    ours = set(DOC_TYPES.values())
    with failures_lock():
        existing = manifest.read_rows("parse_failures.csv")
        first_seen = {r["url"]: r["recorded_at"] for r in existing if r["doc_type"] in ours}
        mine = [{**f, "recorded_at": first_seen.get(f["url"], f["recorded_at"])} for f in failures]
        others = [r for r in existing if r["doc_type"] not in ours]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=FAILURE_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in sorted(others + mine, key=failure_order):
            writer.writerow({k: row.get(k, "") for k in FAILURE_FIELDS})
        write_atomic(MANIFEST_DIR / "parse_failures.csv", buffer.getvalue().encode("utf-8"))


if __name__ == "__main__":
    flags = set(sys.argv[1:])
    try:
        result = build(only_cached="--cached" in flags, allow_shrink="--allow-shrink" in flags)
    except ShrinkError as exc:
        raise SystemExit(f"regulations: {exc}") from exc
    for name, n in result.items():
        print(f"regulations {name}: {n}")
