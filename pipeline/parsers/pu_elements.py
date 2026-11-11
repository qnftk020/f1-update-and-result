"""FIA PU 구성요소 문서 파서. (T6)

기술 대표(Technical Delegate)가 대회마다 내는 두 가지 문서를 읽는다.

- pu_used ("PU elements used per driver up to now"): 차량마다 구성요소별 누적 사용 개수를 적은 표다.
  열은 N°, Car, Driver, 그리고 구성요소(2020년 ICE, TC, MGU-H, MGU-K, ES, CE. 2021년부터 EX 추가)다.
  표에 테두리가 없어서 머리글 낱말의 좌표로 열을 정하고, 각 행의 숫자가 머리글 아래에 놓였는지 본다.
- pu_new ("New PU elements for this Event" 등): 구성요소마다 도입 문장, 작은 표(Number, Car, Driver,
  Previously used X), 배정 문장("... is one of the three new ... allowed for the 2021 Championship
  season and this is in conformity with ...")이 차례로 나온다. 한 문서가 여러 구성요소와 여러
  드라이버를 다루고, 한 대회에 문서가 여러 건 나오기도 한다.

"up to now"의 뜻(같은 대회의 새 구성요소와의 관계). 문서에서 확인한 사실은 셋이다.

- 누적 문서는 같은 대회의 어느 선언 문서보다 먼저 나온다(2020-2021년은 대개 목요일, 2022년부터는
  대개 금요일 오전).
- 같은 대회 선언 문서의 "Previously used" 값은 거의 모두 그 대회 누적 문서의 값과 같다. 대회 시작 때
  새로 끼운 구성요소("will start the sixth Event ... with a new ...")도 누적 값에 들어 있지 않다.
  따라서 누적 값은 그 대회에서 선언되는 새 구성요소를 세기 전의 개수다.
- 다음 누적 값은 대부분 앞 누적 값에 그 사이 선언된 개수를 더한 값과 같다. 맞지 않는 칸은 거의
  모두 선언된 것보다 더 늘어난 경우이고(줄어든 칸은 몇 건뿐이다), 선언 문서에 없이 처분 문서
  ("Offence - Car 33 - PU elements")에만 나오는 교체가 있다. 앞 대회 처분과 함께 나오는 경우와 뒤
  대회 처분과 함께 나오는 경우가 섞여 있어, 누적 문서가 그 대회 주행 전에 이미 끼운 구성요소를 세는
  경우가 있는지는 문서만으로 가릴 수 없다.

그래서 파생 표(pu_usage)는 아래처럼 만든다.

    used_before_event = 그 대회 pu_used 문서의 값(그 대회 선언 문서에 나오는 구성요소를 세기 전)
    new_at_event      = 그 대회 정상 pu_new 문서에 선언된 개수. 그 대회의 선언 문서가 manifest에
                        없거나, 검수 대기 선언 문서가 그 좌석을 다루거나, 다루는 좌석을 알 수 없는
                        문서(미수집, 행을 빠뜨린 문서)가 있으면 비운다(새 구성요소가 없었다고
                        단정하지 않는다).
    used_after_event  = used_before_event + new_at_event. 처분 문서에만 나오는 교체는
                        들어가지 않는다. 같은 대회 선언의 Previously used가 before, before+1, ...과
                        다르면 두 문서가 이전 개수를 달리 적은 것이므로 비운다.

누적 개수는 드라이버가 아니라 좌석(팀의 차량 한 대)에 붙는다. 대체 드라이버는 원래 드라이버의
개수를 이어받으므로, 누적 표에 없는 번호의 선언은 그 대회 결승에 나오지 않은 같은 팀 차량의 좌석에
더한다(2020 Eifel 27번 Hülkenberg는 18번 좌석). 차량 번호가 바뀐 좌석은 같은 팀 안에서 이어 붙여
비교한다.

뒤 누적 값이 위 등식과 맞지 않는 칸, 선언 문서의 Previously used가 누적 값과 다른 칸은 고치지 않고
pu_inconsistencies.csv 에 두 문서의 URL과 같은 차량의 처분 문서 URL(제목으로 찾은 것)을 함께 적는다.
비교는 표를 확실히 읽은 누적 문서를 라운드 순으로 이웃끼리 한다. 값이 줄어든 이웃 쌍은 두 문서를
검수 대기로 두고 snapshot_decrease로 한 번만 적는다. 사이 대회에 선언 문서가 manifest에 없으면 그
대회의 선언 수를 0으로 계산하고 note에 밝힌다.

읽은 값은 원문 그대로 둔다. 확실히 읽지 못한 값이 있으면 그 문서를 실패("검수 대기")로 적고
추측으로 채우지 않는다. 검수 대기 문서와 정정으로 대체된 문서의 행은 파생 표에 쓰지 않는다.
표 없이 "All drivers will start the first Competition ..."이라고만 적은 시즌 첫 대회 선언은
pu_new에 차량 번호 없는 행으로만 두고, 차량을 적지 않았으므로 pu_usage와 pu_ice_events에는
펼치지 않는다.

캐시가 덜 찬 상태(--cached)에서 같은 대회의 나중 문서를 받지 않았으면, 앞 문서가 그 문서로 대체
(정정)되었는지 알 수 없으므로 앞 문서를 held로 두고 검사와 파생 표에 쓰지 않는다. 받지 않은 선언
문서가 있는 대회는 pu_ice_events와 pu_allocations에도 싣지 않는다.

pu_ice_events의 순번(ice_number)은 Previously used + 1이다. 같은 대회 누적 문서나 같은 문서의 배정
문장이 다른 값을 적으면 순번을 비우고, 원문 값(printed_previously_used, stated_ordinal)과 어긋난
내용(conflict)을 따로 둔다. 2025년처럼 허용 개수를 넘는 구성요소를 선언 문서 없이 파크 페르메
처분 문서("Infringement - Car 1 - PU elements ...")로만 밝힌 경우가 있어, 새 ICE 투입 이벤트는
선언 문서에 나온 것만이고 누적 문서의 개수보다 적을 수 있다.

실행: uv run python -m pipeline.parsers.pu_elements [--cached]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber

from pipeline.events import plain
from pipeline.parsers.car_presentation import clean

# 구성요소 약칭. 표의 열 순서이기도 하다.
ELEMENTS = ["ICE", "TC", "MGU-H", "MGU-K", "ES", "CE", "EX"]
DOC_TYPES = ["pu_new", "pu_used"]
CARS_PER_TEAM = 2  # 참가 차량 수는 그 대회 결과에 나온 팀 수의 두 배로 본다
LINE_TOLERANCE = (
    3.0  # 같은 줄로 보는 세로 차이(pt). 줄바꿈된 칸은 6pt쯤 어긋나므로 그보다 작게 둔다.
)
COLUMN_TOLERANCE = 3.0  # 열 시작 좌표의 허용 오차(pt)
ALIGN_TOLERANCE = 10.0  # "Previously used" 머리글과 그 아래 숫자의 가로 허용 오차(pt)
WRAP_DISTANCE = 20.0  # 줄바꿈된 칸의 줄이 같은 행의 앞 줄에서 떨어질 수 있는 거리(pt)
NAME_SIMILARITY = 0.8  # 원문의 이름 오타("Russel")를 같은 사람으로 보는 기준
CAR_NUMBER = re.compile(r"\d{1,2}")
COVER_NUMBER = re.compile(r"\bDocument\s*:?\s*(\d+)\b")
CORRECTION = re.compile(r"\bcorrect(?:ed|ion)\b", re.I)
# 쪽에 보이지 않는 글자: Symbol 글꼴의 빈칸(U+F020)
INVISIBLE = str.maketrans("", "", "")

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}  # fmt: skip
ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15,
}  # fmt: skip


@dataclass
class Line:
    """한 쪽의 한 줄. 낱말은 왼쪽에서 오른쪽 순서다."""

    page: int
    top: float
    words: list[dict]

    @property
    def text(self) -> str:
        return " ".join(w["text"] for w in self.words)

    @property
    def x0(self) -> float:
        return self.words[0]["x0"]


def group_lines(words: list[dict], page: int = 1) -> list[Line]:
    """낱말을 세로 위치로 묶어 줄을 만든다."""
    lines: list[Line] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - lines[-1].top) <= LINE_TOLERANCE:
            lines[-1].words.append(word)
        else:
            lines.append(Line(page, word["top"], [word]))
    for line in lines:
        line.words.sort(key=lambda w: w["x0"])
    return lines


def visible_words(words: list[dict]) -> list[dict]:
    """보이지 않는 글자를 뺀 낱말 목록.

    Symbol 글꼴의 빈칸(U+F020)은 쪽에 보이지 않는데 낱말로 뽑힌다(2020 벨기에 선언 문서의 빈 단락).
    이런 글자만으로 된 낱말은 버리고, 낱말 안에 섞인 것은 지운다.
    """
    found: list[dict] = []
    for word in words:
        text = word["text"].translate(INVISIBLE).strip()
        if text:
            found.append({**word, "text": text})
    return found


def read_lines(path: Path) -> list[Line]:
    """문서의 모든 쪽을 줄 단위로 읽는다."""
    lines: list[Line] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
            lines.extend(group_lines(visible_words(words), number))
    return lines


def center(word: dict) -> float:
    return (word["x0"] + word["x1"]) / 2


def element_code(text: str) -> str | None:
    """원문 표기("MGU-H", "MGU - K")를 약칭으로 바꾼다. 모르는 표기는 None이다."""
    code = re.sub(r"\s+", "", text).upper().strip("():")
    return code if code in ELEMENTS else None


def cover_number(lines: list[Line]) -> str:
    """표지의 문서 번호("Document 3"). 첫 쪽 머리에서만 찾고, 없으면 빈 문자열이다."""
    for line in [ln for ln in lines if ln.page == 1][:8]:
        match = COVER_NUMBER.search(line.text)
        if match:
            return match.group(1)
    return ""


def correction_note(lines: list[Line]) -> str:
    """정정 문서임을 알리는 줄.

    본문의 줄("Correction of the number of EX used by ...")을 먼저 쓴다.
    """
    notes = [clean(line.text) for line in lines if CORRECTION.search(line.text)]
    body = [n for n in notes if not re.match(r"(Description|Title)\b", n)]
    return (body or notes or [""])[0]


# --- pu_used: 누적 사용 개수 표 -------------------------------------------------------------


@dataclass
class UsedColumns:
    """누적 표의 열 좌표. 머리글 줄에서 얻는다."""

    car_x0: float
    driver_x0: float
    elements: list[tuple[str, float, float]]  # (약칭, 머리글 낱말의 왼쪽, 오른쪽 좌표)


@dataclass
class UsedDocument:
    path: Path | None
    doc_number: str
    elements: list[str]
    rows: list[dict]  # car_number, team_text, driver_name, used{약칭: 개수}
    correction: str
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def used_columns(line: Line) -> tuple[UsedColumns | None, list[str]]:
    """머리글 줄(N° Car Driver ICE ...)이면 열 좌표를 돌려준다. 머리글이 아니면 None이다."""
    words = line.words
    if len(words) < 4 or [w["text"] for w in words[1:3]] != ["Car", "Driver"]:
        return None, []
    if not words[0]["text"].startswith("N"):
        return None, []
    problems: list[str] = []
    elements: list[tuple[str, float, float]] = []
    for word in words[3:]:
        code = element_code(word["text"])
        if code is None or code in [e[0] for e in elements]:
            problems.append(f"모르는 열 머리글이 있다: {word['text']!r}")
            continue
        elements.append((code, word["x0"], word["x1"]))
    return UsedColumns(words[1]["x0"], words[2]["x0"], elements), problems


def is_car_row(line: Line, car_x0: float) -> bool:
    """줄이 차량 번호로 시작하는지 본다. 번호는 Car 열보다 왼쪽에 있어야 한다."""
    first = line.words[0]
    return bool(CAR_NUMBER.fullmatch(first["text"])) and first["x1"] <= car_x0 + COLUMN_TOLERANCE


def used_row(line: Line, columns: UsedColumns) -> tuple[dict | None, str | None]:
    """누적 표의 한 행을 읽는다. 숫자가 열마다 하나씩 머리글 아래에 있어야 한다.

    숫자는 문서에 따라 머리글의 가운데나 왼쪽 끝에 맞춰져 있다. 어느 쪽이든 숫자의 가운데가 머리글
    낱말의 폭 안에 든다.
    """
    n = len(columns.elements)
    words = line.words
    where = f"{line.page}쪽 {words[0]['text']}번"
    # 첫 구성요소 열보다 왼쪽은 팀과 드라이버 칸, 그 오른쪽은 개수 칸이다
    start = columns.elements[0][1] - COLUMN_TOLERANCE
    values = [w for w in words[1:] if center(w) >= start]
    names = [w for w in words[1:] if center(w) < start]
    if len(values) != n:
        return None, f"{where}: 개수 칸 수({len(values)})가 열 수({n})와 다르다: {line.text!r}"
    used: dict[str, int] = {}
    for word, (code, x0, x1) in zip(values, columns.elements, strict=True):
        if not word["text"].isdigit():
            return None, f"{where}: {code} 칸이 숫자가 아니다: {word['text']!r}"
        if not x0 - COLUMN_TOLERANCE <= center(word) <= x1 + COLUMN_TOLERANCE:
            return None, f"{where}: {code} 칸의 숫자가 머리글 아래에 있지 않다"
        used[code] = int(word["text"])
    limit = columns.driver_x0 - COLUMN_TOLERANCE
    team = clean(" ".join(w["text"] for w in names if w["x0"] < limit))
    driver = clean(" ".join(w["text"] for w in names if w["x0"] >= limit))
    if not team or not driver:
        return None, f"{where}: 팀이나 드라이버 칸이 비어 있다: {line.text!r}"
    row = {
        "car_number": int(words[0]["text"]), "team_text": team, "driver_name": driver,
        "used": used,
    }  # fmt: skip
    return row, None


def parse_used_lines(lines: list[Line]) -> tuple[list[str], list[dict], list[str]]:
    """줄 목록에서 누적 표를 읽는다. (구성요소 열, 행 목록, 문제 목록)을 돌려준다."""
    problems: list[str] = []
    columns: UsedColumns | None = None
    rows: list[dict] = []
    ended = False
    for line in lines:
        found, header_problems = used_columns(line)
        if found is not None:
            if columns is not None:
                problems.append(f"{line.page}쪽: 표 머리글이 두 번 나온다")
                continue
            columns = found
            problems.extend(header_problems)
            continue
        if columns is None or ended:
            continue
        if is_car_row(line, columns.car_x0):
            row, problem = used_row(line, columns)
            if row is not None:
                rows.append(row)
            if problem:
                problems.append(problem)
        elif line.x0 >= columns.car_x0 - COLUMN_TOLERANCE:
            problems.append(f"{line.page}쪽: 표 안에 행이 아닌 줄이 있다: {line.text!r}")
        else:
            ended = True  # 왼쪽 여백에서 시작하는 글이 나오면 표가 끝난 것이다
    if columns is None:
        return [], [], ["누적 표의 머리글(N° Car Driver ...)을 찾지 못했다"]
    if not rows:
        problems.append("누적 표에서 행을 하나도 읽지 못했다")
    numbers = [r["car_number"] for r in rows]
    for number in sorted({n for n in numbers if numbers.count(n) > 1}):
        problems.append(f"차량 번호 {number}번이 두 번 나온다")
    return [e[0] for e in columns.elements], rows, problems


def parse_used(path: Path) -> UsedDocument:
    """누적 사용 개수 문서 한 건을 읽는다."""
    lines = read_lines(path)
    elements, rows, problems = parse_used_lines(lines)
    return UsedDocument(path, cover_number(lines), elements, rows, correction_note(lines), problems)


# --- pu_new: 새 구성요소 선언 ---------------------------------------------------------------

INTRO = re.compile(r"^(The following|All drivers)\b", re.I)
EVERYONE = re.compile(r"^All drivers\b", re.I)
INTRO_ELEMENT = re.compile(r"\(([A-Za-z]+(?:\s*-\s*[A-Za-z])?)\)")
NEW_HEADER = re.compile(r"^Number\s*Car\s+Driver\s+Previously\s+used\s+(?P<code>\S.*)$", re.I)
STATEMENT_HEAD = re.compile(r"^The\s+[A-Za-z][A-Za-z \-]*?\s+used\s+(?:by\s+)?\S", re.I)
FOLLOW_UP = re.compile(r"^(As this|Therefore|Consequently|As a result|I am referring)\b", re.I)
GENERIC_SUBJECT = re.compile(
    r"used\s+by\s+(?:the\s+)?(?:other\s+)?(?:above|both|all)(?:\s+listed|\s+mentioned)?\s+"
    r"drivers?\b",
    re.I,
)
# "is in not conformity"(2022 싱가포르 ES)처럼 어순이 바뀐 부정도 부정으로 읽는다. 순서 문구와 허용
# 개수가 함께 있으면 check_statements가 판정과 견준다.
NOT_WITHIN = re.compile(r"\b(?:not\s+in|in\s+not)\s+(?:conformity|compliance)\b", re.I)
WITHIN = re.compile(r"\bin\s+(?:conformity|compliance)\b", re.I)
DIGITS = r"(?:\s*\(\s*(?P<{name}>\d+)(?:st|nd|rd|th)?\s*\))?"  # "four (4)"의 괄호 숫자
ALLOWED = re.compile(
    r"\bof\s+the\s+(?P<allowed>[A-Za-z]+|\d+)"
    + DIGITS.format(name="allowed_digits")
    + r"\s+new\s+[A-Za-z \-]+?\s+allowed\s+for\s+the\s+(?P<season>\d{4})\s+Championship\s+season",
    re.I,
)
ORDINAL = re.compile(
    r"is\s+(?:the\s+)?(?P<ordinal>[a-z]+|\d+(?:st|nd|rd|th))"
    + DIGITS.format(name="ordinal_digits")
    + r"\s+(?:of\s+the|new)\b",
    re.I,
)
SEASON_MENTION = re.compile(r"Championship\s+season", re.I)
# 배정 문장에 허용 개수나 순서가 적혀 있다는 표시. 읽지 못했으면 statement_unread로 적는다.
ALLOWED_WORD = re.compile(r"\ballowed\b", re.I)
ORDINAL_HINT = re.compile(r"\bis\s+the\s+(?:[a-z]+|\d+(?:st|nd|rd|th)?)\b", re.I)


@dataclass
class NewColumns:
    """선언 표의 열 좌표. 머리글 줄(Number Car Driver Previously used X)에서 얻는다."""

    car_x0: float
    driver_x0: float
    count_x0: float
    count_x1: float


@dataclass
class NewBlock:
    """구성요소 하나에 대한 묶음: 도입 문장, 표, 그 뒤의 글.

    everyone은 표 없이 "All drivers will start ... with a new ..."라고만 적은 묶음이다.
    """

    element: str
    page: int
    everyone: bool = False
    columns: NewColumns | None = None
    table: list[Line] = field(default_factory=list)
    tail: list[str] = field(default_factory=list)


@dataclass
class NewDocument:
    path: Path | None
    doc_number: str
    # car_number, team_text, driver_name, element, previously_used, allocation_text,
    # within_allocation, allowed, allowed_season, ordinal
    rows: list[dict]
    correction: str
    problems: list[str]
    # 표의 행을 하나도 빠뜨리지 않고 읽었는지. 거짓이면 이 문서가 다루는 차량을 다 알 수 없다.
    complete: bool = True

    @property
    def ok(self) -> bool:
        return not self.problems


def new_columns(line: Line) -> NewColumns:
    """선언 표 머리글 줄에서 열 좌표를 얻는다. "NumberCar"처럼 붙은 낱말도 다룬다."""
    words = line.words
    by_text = {w["text"].lower(): w for w in words}
    driver, previously = by_text["driver"], by_text["previously"]
    if "car" in by_text:
        car_x0 = by_text["car"]["x0"]
    else:  # "NumberCar": 낱말 폭을 글자 수로 나눠 Car가 시작하는 자리를 얻는다
        merged = words[0]
        car_x0 = merged["x0"] + (merged["x1"] - merged["x0"]) * len("Number") / len("NumberCar")
    return NewColumns(car_x0, driver["x0"], previously["x0"], words[-1]["x1"])


def is_table_line(line: Line, columns: NewColumns) -> bool:
    """선언 표에 속한 줄인지 본다: 차량 번호로 시작하는 행이거나 줄바꿈된 칸의 줄이다.

    줄바꿈된 칸의 줄은 Car 열이나 Driver 열 안에서 시작하고 끝난다. 본문 글은 왼쪽 여백에서
    시작한다.
    """
    if line.x0 >= columns.car_x0 - COLUMN_TOLERANCE:
        return line.words[-1]["x1"] <= (columns.count_x0 + columns.count_x1) / 2
    return is_car_row(line, columns.car_x0)


def split_blocks(lines: list[Line]) -> tuple[list[NewBlock], list[str], bool]:
    """문서의 줄을 구성요소별 묶음으로 나눈다. (묶음, 문제, 빠뜨린 표가 없는지)를 돌려준다.

    도입 문장("The following driver will use a new energy store (ES) ...:")이 묶음을 열고,
    표 머리글이 열 좌표를 정한다. 표 뒤의 글은 다음 도입 문장이 나올 때까지 그 묶음의 글로
    모은다. 구성요소 약칭이 없는 도입 문장("The following parts have been replaced ...")은
    PU와 무관한 부분의 시작이다.
    """
    blocks: list[NewBlock] = []
    problems: list[str] = []
    complete = True
    current: NewBlock | None = None
    intro: list[str] | None = None

    def open_block(text: str, page: int) -> NewBlock | None:
        codes = [c for c in map(element_code, INTRO_ELEMENT.findall(text)) if c]
        if not codes:
            return None
        blocks.append(NewBlock(codes[0], page, everyone=bool(EVERYONE.match(text))))
        return blocks[-1]

    for line in lines:
        text = line.text
        if intro is not None or INTRO.match(text):  # 도입 문장은 다음 줄로 이어지기도 한다
            intro = [*(intro or []), text]
            if text.rstrip().endswith((":", ".")) or len(intro) >= 4:
                current = open_block(" ".join(intro), line.page)
                intro = None
            continue
        header = NEW_HEADER.match(text)
        if header:
            code = element_code(header["code"])
            if code is None:
                problems.append(f"{line.page}쪽: 모르는 구성요소 표기: {header['code']!r}")
                current, complete = None, False
                continue
            if current is None or current.columns is not None:
                blocks.append(NewBlock(code, line.page))  # 도입 문장 없이 나온 표
                current = blocks[-1]
            elif current.element != code:
                problems.append(
                    f"{line.page}쪽: 도입 문장({current.element})과 표 머리글({code})이 다르다"
                )
            current.columns = new_columns(line)
            continue
        if current is None or (current.columns is None and not current.everyone):
            continue
        if current.columns and not current.tail and is_table_line(line, current.columns):
            current.table.append(line)
        elif current.columns and current.tail and looks_like_row(line, current.columns):
            # 표 중간에 왼쪽 여백에서 시작하는 줄(쪽 바닥글 등)이 끼면 그 뒤의 행을 글로
            # 삼키게 된다. 행을 버리지 않았다고 말할 수 없으므로 문제로 남긴다.
            problems.append(f"{line.page}쪽: 표가 끝난 뒤에 차량 행이 있다: {text!r}")
            complete = False
        else:
            current.tail.append(text)
    return blocks, problems, complete


def looks_like_row(line: Line, columns: NewColumns) -> bool:
    """선언 표의 행처럼 생긴 줄: 차량 번호로 시작하고 낱말이 셋 이상이며, 마지막 낱말이 개수 열
    아래의 숫자이거나, 개수 칸이 비었고(마지막 낱말이 개수 열에 닿지 않는다) Driver 열에 낱말이
    있다.

    뒤의 꼴은 Previously used 칸이 빈 행(2023 마이애미 CE 81번, 2024 바레인 CE 04번)이다. new_row가
    빈 칸으로 읽는 기준과 같다.
    """
    if len(line.words) < 3 or not is_car_row(line, columns.car_x0):
        return False
    last = line.words[-1]
    low, high = columns.count_x0 - ALIGN_TOLERANCE, columns.count_x1 + ALIGN_TOLERANCE
    if last["text"].isdigit() and low <= center(last) <= high:
        return True
    limit = columns.driver_x0 - COLUMN_TOLERANCE
    return last["x1"] < low and any(w["x0"] >= limit for w in line.words[1:])


def assign_wrapped(table: list[Line], car_x0: float) -> tuple[list[tuple[Line, list[dict]]], list]:
    """표의 줄을 행으로 묶는다. (행 기준 줄, 줄바꿈으로 딸린 낱말) 목록과 문제 목록을 돌려준다.

    차량 번호로 시작하는 줄이 행의 기준이다. 나머지 줄은 같은 쪽에서 가장 가까운 줄의 행에 붙인다.
    두 행의 한가운데에 있어 어느 쪽인지 알 수 없으면 붙이지 않고 문제로 남긴다.
    """
    problems: list[str] = []
    anchors = [ln for ln in table if is_car_row(ln, car_x0)]
    extra: list[list[dict]] = [[] for _ in anchors]
    placed = [(a.page, a.top, i) for i, a in enumerate(anchors)]
    for line in table:
        if any(line is a for a in anchors):
            continue
        near = sorted((abs(line.top - top), i) for page, top, i in placed if page == line.page)
        rival = [d for d, i in near if i != near[0][1]] if near else []
        if not near or near[0][0] > WRAP_DISTANCE or (rival and rival[0] - near[0][0] < 1.5):
            problems.append(f"{line.page}쪽: 어느 행에 속하는지 알 수 없는 줄: {line.text!r}")
            continue
        extra[near[0][1]].extend(line.words)
        placed.append((line.page, line.top, near[0][1]))
    return list(zip(anchors, extra, strict=True)), problems


def new_row(
    anchor: Line, extra: list[dict], columns: NewColumns, element: str
) -> tuple[dict | None, str | None]:
    """선언 표의 한 행. 마지막 낱말이 "Previously used" 아래의 숫자여야 한다.

    개수 칸이 비어 있으면(2024 바레인 CE) 원문대로 개수 없는 행을 남기고 문제로 적는다.
    """
    number, count = anchor.words[0], anchor.words[-1]
    where = f"{anchor.page}쪽 {element} {number['text']}번"
    low, high = columns.count_x0 - ALIGN_TOLERANCE, columns.count_x1 + ALIGN_TOLERANCE
    blank = count["x1"] < low  # 마지막 낱말이 개수 열에 닿지 않는다: 개수 칸이 비었다
    if len(anchor.words) < 3 or not (
        blank or count["text"].isdigit() and low <= center(count) <= high
    ):
        return None, f"{where}: 이전 사용 개수를 읽지 못했다: {anchor.text!r}"
    cells = anchor.words[1:] if blank else anchor.words[1:-1]
    words = sorted(cells + extra, key=lambda w: (round(w["top"]), w["x0"]))
    limit = columns.driver_x0 - COLUMN_TOLERANCE
    team = clean(" ".join(w["text"] for w in words if w["x0"] < limit))
    driver = clean(" ".join(w["text"] for w in words if w["x0"] >= limit))
    if not team or not driver:
        return None, f"{where}: 팀이나 드라이버 칸이 비어 있다: {anchor.text!r}"
    previously_used = None if blank else int(count["text"])
    row = declared_row(int(number["text"]), team, driver, element, previously_used)
    return row, f"{where}: 이전 사용 개수 칸이 비어 있다" if blank else None


def declared_row(
    car_number: int | None, team: str, driver: str, element: str, previously_used: int | None
) -> dict:
    """선언 한 건. 배정 문장에서 읽는 값은 비워 두고 apply_statements가 채운다."""
    return {
        "car_number": car_number, "team_text": team, "driver_name": driver, "element": element,
        "previously_used": previously_used, "allocation_text": "", "within_allocation": None,
        "allowed": None, "allowed_season": None, "ordinal": None,
    }  # fmt: skip


def table_rows(block: NewBlock) -> tuple[list[dict], list[str], bool]:
    """묶음의 표를 읽는다. (행, 문제, 행을 하나도 빠뜨리지 않았는지)를 돌려준다.

    팀 이름이 두 줄로 나뉜 칸은 가장 가까운 행에 붙인다. 표 없이 모든 드라이버를 가리키는 묶음은
    차량 번호가 없는 행 하나로 둔다.
    """
    if block.everyone:
        return [declared_row(None, "", "All drivers", block.element, None)], [], True
    if block.columns is None:
        return [], [f"{block.page}쪽 {block.element}: 도입 문장 뒤에 표가 없다"], False
    grouped, problems = assign_wrapped(block.table, block.columns.car_x0)
    rows: list[dict] = []
    for anchor, extra in grouped:
        row, problem = new_row(anchor, extra, block.columns, block.element)
        if row is not None:
            rows.append(row)
        if problem:
            problems.append(problem)
    if not rows:
        problems.append(f"{block.page}쪽 {block.element}: 표에서 행을 읽지 못했다")
    return rows, problems, bool(rows) and len(rows) == len(grouped)


def split_sentences(text: str) -> list[str]:
    """글을 문장으로 나눈다. 조항 번호("23.3a")의 마침표에서는 나누지 않는다."""
    return [s.strip() for s in re.split(r"(?<=[.:])\s+(?=[A-Z])", clean(text)) if s.strip()]


def statements(tail: list[str]) -> list[str]:
    """표 뒤의 글에서 배정 문장을 뽑는다.

    "The <구성요소> used by ..."로 시작하는 문장과 바로 이어지는 뒷문장("As this is ...",
    "Therefore I am referring ...")을 한 덩어리로 본다. 그 밖의 문장은 배정 문장이 아니다.
    """
    found: list[str] = []
    open_statement = False
    for sentence in split_sentences(" ".join(tail)):
        if STATEMENT_HEAD.match(sentence):
            found.append(sentence)
            open_statement = True
        elif open_statement and FOLLOW_UP.match(sentence):
            found[-1] = f"{found[-1]} {sentence}"
        else:
            open_statement = False
    return found


def squash(text: str) -> str:
    """이름 비교용: 악센트, 대소문자, 빈칸, 기호를 없앤다."""
    return plain(text).replace(" ", "")


def names_driver(statement: str, driver_name: str) -> bool:
    """배정 문장이 이 드라이버를 이름으로 가리키는지 본다. 원문의 띄어쓰기 오타는 넘긴다."""
    if squash(driver_name) in squash(statement):
        return True
    tokens = set(plain(driver_name).split())
    return bool(tokens) and tokens <= set(plain(statement).split())


def subject(statement: str) -> str:
    """배정 문장의 주어 부분("used by" 뒤부터 "is" 앞까지)."""
    match = re.search(r"\bused\s+(?:by\s+)?(?P<who>.+?)\s*(?:is\b|$)", statement)
    return match["who"] if match else ""


def named_rows(statement: str, rows: list[dict]) -> list[dict]:
    """배정 문장이 이름으로 가리키는 행.

    이름이 그대로 나오지 않으면 문장 주어의 낱말과 드라이버 이름의 낱말을 작은 철자 차이까지 견준다
    (2022 헝가리 "George Russel"). 이렇게 맞는 행이 정확히 하나일 때만 그 행으로 본다.
    """
    exact = [r for r in rows if names_driver(statement, r["driver_name"])]
    if exact:
        return exact
    words = plain(subject(statement)).split()
    close = [r for r in rows if words and same_person(" ".join(words), r["driver_name"])]
    return close if len(close) == 1 else []


def spelled_number(word: str, digits: str | None, table: dict[str, int]) -> int | None:
    """글자로 적은 수("four", "fifth")나 숫자("4", "4th")를 읽는다.

    괄호 숫자("(4)")가 함께 있으면 둘이 같아야 한다. 서수 접미사가 수와 맞지 않으면("4st") 읽지
    않는다.
    """
    suffixed = re.fullmatch(r"(\d+)(st|nd|rd|th)", word, re.I)
    if suffixed:
        value = int(suffixed[1])
        if suffixed[2].lower() != ordinal_suffix(value):
            return None
    else:
        value = int(word) if word.isdigit() else table.get(word.lower())
    return value if digits is None or value == int(digits) else None


def ordinal_suffix(value: int) -> str:
    if 10 <= value % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")


def statement_facts(statement: str) -> dict:
    """배정 문장에서 적합 여부, 허용 개수, 몇 번째인지를 읽는다. 문장에 없으면 None이다."""
    within = False if NOT_WITHIN.search(statement) else True if WITHIN.search(statement) else None
    allowed = ALLOWED.search(statement)
    ordinal = ORDINAL.search(statement)
    count = allowed and spelled_number(allowed["allowed"], allowed["allowed_digits"], NUMBER_WORDS)
    return {
        "within_allocation": within,
        "allowed": count or None,
        "allowed_season": int(allowed["season"]) if count else None,
        "ordinal": ordinal
        and spelled_number(ordinal["ordinal"], ordinal["ordinal_digits"], ORDINAL_WORDS),
    }


def apply_statements(block: NewBlock, rows: list[dict]) -> list[str]:
    """배정 문장을 표의 행에 붙인다. 문장이 가리키는 행을 알 수 없으면 문제로 남긴다.

    이름을 적은 문장은 그 드라이버의 행에, "the above drivers"처럼 묶어 말한 문장은 이름으로 불리지
    않은 나머지 행에 붙인다. 문장이 없는 행은 문서가 말하지 않은 것이므로 비워 둔다.
    """
    problems: list[str] = []
    where = f"{block.page}쪽 {block.element}"
    found = statements(block.tail)
    if len(SEASON_MENTION.findall(" ".join(block.tail))) > len(found):
        problems.append(f"{where}: 배정 문장으로 보이는 글을 다 읽지 못했다")
    named = [named_rows(s, rows) for s in found]
    named_ids = {id(r) for group in named for r in group}
    hits: dict[int, list[str]] = {id(r): [] for r in rows}
    for statement, group in zip(found, named, strict=True):
        generic = GENERIC_SUBJECT.search(statement)
        targets = group or ([r for r in rows if id(r) not in named_ids] if generic else [])
        if not targets:
            problems.append(f"{where}: 배정 문장이 가리키는 행을 표에서 찾지 못했다: {statement!r}")
        for row in targets:
            hits[id(row)].append(statement)
    for row in rows:
        texts = hits[id(row)]
        if len(texts) > 1:
            problems.append(f"{where} {row['car_number']}번: 배정 문장이 {len(texts)}개다")
        if len(texts) != 1:
            continue
        facts = statement_facts(texts[0])
        if facts["within_allocation"] is None:
            problems.append(f"{where} {row['car_number']}번: 배정 문장에서 적합 여부를 읽지 못했다")
        row.update(allocation_text=texts[0], **facts)
    return problems


def read_declarations(lines: list[Line]) -> tuple[list[dict], list[str], bool]:
    """줄 목록에서 새 구성요소 선언을 읽는다. (행, 문제, 표의 행을 빠뜨리지 않았는지)를 돌려준다."""
    blocks, problems, complete = split_blocks(lines)
    rows: list[dict] = []
    for block in blocks:
        block_rows, row_problems, block_complete = table_rows(block)
        problems.extend(row_problems)
        complete = complete and block_complete
        if block_rows:
            problems.extend(apply_statements(block, block_rows))
        rows.extend(block_rows)
    if not blocks:
        problems.append("새 구성요소 선언(도입 문장이나 표 머리글)을 찾지 못했다")
    return rows, problems, complete and bool(blocks)


def parse_new_lines(lines: list[Line]) -> tuple[list[dict], list[str]]:
    """줄 목록에서 새 구성요소 선언을 읽는다. (행 목록, 문제 목록)을 돌려준다."""
    rows, problems, _ = read_declarations(lines)
    return rows, problems


def parse_new(path: Path) -> NewDocument:
    """새 구성요소 선언 문서 한 건을 읽는다."""
    lines = read_lines(path)
    rows, problems, complete = read_declarations(lines)
    number, correction = cover_number(lines), correction_note(lines)
    return NewDocument(path, number, rows, correction, problems, complete)


# --- manifest 문서와 결과 연결 ----------------------------------------------------------------


@dataclass
class Document:
    """manifest의 문서 한 건과 그 파싱 결과."""

    meta: dict
    season: int
    round: int | None
    parsed: UsedDocument | NewDocument | None = None
    problems: list[str] = field(default_factory=list)
    superseded_by: str = ""
    # 같은 대회의 나중 문서를 아직 받지 않아 이 문서가 대체되었는지 알 수 없을 때 그 문서의 URL
    held_by: str = ""
    # 정정 표시 없이 다시 낸 나중 문서가 이 문서를 대체할 때, 이 문서에만 있던 선언 행
    dropped: list[dict] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return self.meta["doc_type"]

    @property
    def url(self) -> str:
        return self.meta["url"]

    @property
    def published_at(self) -> str:
        return self.meta["published_at"]

    @property
    def doc_number(self) -> str:
        """문서 번호. 목록에 번호가 없던 해는 표지에 적힌 번호를 쓴다."""
        return self.meta["doc_number"] or (self.parsed.doc_number if self.parsed else "")

    @property
    def rows(self) -> list[dict]:
        return self.parsed.rows if self.parsed else []

    @property
    def car_rows(self) -> list[dict]:
        """차량이 적힌 행. "All drivers"로만 적힌 선언은 차량 번호가 없다."""
        return [r for r in self.rows if r["car_number"] is not None]

    @property
    def status(self) -> str:
        """문서 상태. held는 읽었지만 같은 대회의 나중 문서를 받지 않아 아직 쓰지 않는 문서다."""
        if self.superseded_by:
            return "superseded"
        if self.parsed is None:
            return "not_downloaded"
        if self.problems:
            return "needs_review"
        return "held" if self.held_by else "ok"

    @property
    def event_key(self) -> tuple[int, str]:
        return self.season, self.meta["event"]

    @property
    def order(self) -> tuple:
        return self.season, self.round or 0, self.meta["event"], self.published_at, self.url


def parse_document(kind: str, path: Path) -> UsedDocument | NewDocument:
    """문서 한 건을 읽는다. 읽다가 오류가 나면 빈 결과에 오류 내용을 문제로 적어 돌려준다.

    오류가 난 문서 하나 때문에 전체 빌드가 멈추지 않게 하고, 그 문서는 검수 대기로 남긴다.
    """
    try:
        return parse_used(path) if kind == "pu_used" else parse_new(path)
    except Exception as error:  # 어떤 오류든 그 문서의 문제로 남긴다
        problem = f"파싱 중 오류가 났다: {type(error).__name__}: {error}"
        if kind == "pu_used":
            return UsedDocument(path, "", [], [], "", [problem])
        return NewDocument(path, "", [], "", [problem], complete=False)


def load_documents(manifest_rows: list[dict], raw_dir: Path) -> list[Document]:
    """manifest의 PU 문서를 읽는다. 캐시에 없는 문서는 파싱 결과 없이 둔다(실패가 아니다).

    manifest에 sha256이 있는데 캐시 파일의 값이 다르면 원문이 바뀐 것이므로 문제로 남긴다.
    """
    from pipeline import events
    from pipeline.http import sha256_bytes
    from pipeline.sources import fia_docs

    documents: list[Document] = []
    for meta in manifest_rows:
        if meta["doc_type"] not in DOC_TYPES:
            continue
        season = int(meta["season"])
        doc = Document(meta, season, events.round_for(season, meta["event"]))
        path = raw_dir / "fia" / fia_docs.pdf_cache_path(meta)
        if path.exists():
            expected = meta.get("sha256", "")
            if expected and sha256_bytes(path.read_bytes()) != expected:
                doc.problems.append("캐시에 있는 원문의 sha256이 manifest와 다르다")
            doc.parsed = parse_document(doc.kind, path)
            doc.problems.extend(doc.parsed.problems)
            if doc.round is None:
                doc.problems.append(f"대회명을 라운드에 맞추지 못했다: {meta['event']}")
        documents.append(doc)
    return sorted(documents, key=lambda d: d.order)


@dataclass
class Entries:
    """결과에서 얻은 대회별 출전 차량과 드라이버 이름."""

    starters: dict[
        tuple[int, int | None], dict[int, tuple[str, str]]
    ]  # 차량 번호 -> (드라이버, 팀)
    names: dict[str, str]  # driver_id -> "이름 성"
    surnames: dict[str, str]  # driver_id -> 성

    def teams(self, season: int, round_no: int | None) -> set[str]:
        return {team for _, team in self.starters.get((season, round_no), {}).values()}

    def started(self, season: int, round_no: int | None) -> set[str]:
        return {driver for driver, _ in self.starters.get((season, round_no), {}).values()}

    def season_drivers(self, season: int) -> set[str]:
        return {
            d for (s, _), cars in self.starters.items() if s == season for d, _ in cars.values()
        }

    def find(self, driver_name: str, season: int) -> str | None:
        """이름으로 드라이버를 찾는다. 낱말이 모두 들어맞는 한 명일 때만 돌려준다."""
        wanted = set(plain(driver_name).split())
        hits = [
            driver_id
            for driver_id, name in self.names.items()
            if wanted and (wanted <= set(plain(name).split()) or set(plain(name).split()) <= wanted)
        ]
        in_season = [d for d in hits if d in self.season_drivers(season)]
        hits = in_season or hits
        return hits[0] if len(hits) == 1 else None


def load_entries(first_season: int) -> Entries:
    import pandas as pd

    from pipeline.config import CURATED_DIR

    results = pd.read_parquet(CURATED_DIR / "jolpica" / "results.parquet")
    race = results[
        (results["session_type"] == "R")
        & (results["season"] >= first_season)
        & results["car_number"].notna()
    ]
    starters: dict[tuple[int, int | None], dict[int, tuple[str, str]]] = {}
    for r in race.itertuples():
        cars = starters.setdefault((int(r.season), int(r.round)), {})
        cars[int(r.car_number)] = (r.driver_id, r.constructor_id)
    drivers = pd.read_parquet(CURATED_DIR / "jolpica" / "drivers.parquet")
    names = {r.driver_id: f"{r.forename} {r.surname}" for r in drivers.itertuples()}
    surnames = {r.driver_id: r.surname for r in drivers.itertuples()}
    return Entries(starters, names, surnames)


def same_person(printed_name: str, surname: str) -> bool:
    """원문의 이름에 결과에서 찾은 드라이버의 성이 들어 있는지 본다. 작은 오타는 넘긴다."""
    printed = plain(printed_name).split()
    return all(
        any(SequenceMatcher(None, part, p).ratio() >= NAME_SIMILARITY for p in printed)
        for part in plain(surname).split()
    )


def team_map(rows: list[dict]) -> dict[str, set[str]]:
    """팀 표기 -> 차량 번호로 맞춘 행의 컨스트럭터들."""
    found: dict[str, set[str]] = {}
    for row in rows:
        if row.get("constructor_id"):
            found.setdefault(plain(row["team_text"]), set()).add(row["constructor_id"])
    return found


def link_by_car(doc: Document, entries: Entries) -> None:
    """그 대회 결과의 차량 번호로 driver_id와 constructor_id를 붙인다."""
    starters = entries.starters.get((doc.season, doc.round), {})
    for row in doc.rows:
        row["driver_id"], row["constructor_id"] = "", ""
        hit = starters.get(row["car_number"])
        if hit and same_person(row["driver_name"], entries.surnames[hit[0]]):
            row["driver_id"], row["constructor_id"] = hit


def link_by_name(doc: Document, entries: Entries, season_teams: dict) -> list[str]:
    """결승에 나오지 않은 드라이버를 이름으로 찾는다. 팀은 같은 표기의 다른 행에서 얻는다."""
    problems: list[str] = []
    doc_teams = team_map(doc.rows)
    started = entries.started(doc.season, doc.round)
    for row in doc.car_rows:
        if row["driver_id"]:
            continue
        where = f"{row['car_number']}번 {row['driver_name']}"
        driver_id = entries.find(row["driver_name"], doc.season)
        if driver_id is None:
            problems.append(f"{where}: 결과의 차량 번호로도 이름으로도 드라이버를 찾지 못했다")
            continue
        if driver_id in started:
            problems.append(f"{where}: 이 대회 결과의 차량 번호와 문서의 번호가 다르다")
            continue
        team = plain(row["team_text"])
        teams = doc_teams.get(team) or season_teams.get((doc.season, team), set())
        row["driver_id"] = driver_id
        if len(teams) != 1:
            problems.append(f"{where}: 팀 표기 {row['team_text']!r}의 컨스트럭터를 정하지 못했다")
            continue
        row["constructor_id"] = next(iter(teams))
    return problems


def link_documents(documents: list[Document], entries: Entries) -> None:
    """모든 문서의 행에 driver_id와 constructor_id를 붙이고, 못 붙인 행을 문제로 남긴다."""
    parsed = [d for d in documents if d.parsed is not None]
    season_teams: dict[tuple[int, str], set[str]] = {}
    usual: dict[tuple[int, str], Counter] = {}
    for doc in parsed:
        link_by_car(doc, entries)
        for row in doc.rows:
            if row["constructor_id"]:
                key = (doc.season, plain(row["team_text"]))
                usual.setdefault(key, Counter())[row["constructor_id"]] += 1
                season_teams.setdefault(key, set()).add(row["constructor_id"])
    for doc in parsed:
        doc.problems.extend(team_conflicts(doc, usual))
        doc.problems.extend(link_by_name(doc, entries, season_teams))


def team_conflicts(doc: Document, usual: dict[tuple[int, str], Counter]) -> list[str]:
    """한 문서 안에서 같은 팀 표기가 결과의 서로 다른 컨스트럭터에 걸리면 문제로 남긴다.

    차량 번호, 드라이버, 팀 표기 가운데 하나가 그 대회 출전 기록과 맞지 않는다는 뜻이다(예: 2025
    일본 누적 문서는 드라이버 교체 전의 팀 표기를 싣고 있다). 그 시즌에 그 표기가 가장 많이 걸린
    컨스트럭터와 다른 행을 적는다. 어느 쪽이 맞는지 정하지 않는다.
    """
    problems: list[str] = []
    for team, ids in sorted(team_map(doc.rows).items()):
        if len(ids) < 2:
            continue
        common = usual[doc.season, team].most_common()
        expected = common[0][0] if len(common) == 1 or common[0][1] > common[1][1] else None
        for row in doc.rows:
            if plain(row["team_text"]) == team and row["constructor_id"] != expected:
                problems.append(
                    f"{row['car_number']}번 {row['driver_name']}: 팀 표기 {row['team_text']!r}와 "
                    f"결과의 컨스트럭터({row['constructor_id']})가 맞지 않는다"
                )
    return problems


def check_cars(doc: Document, entries: Entries) -> list[str]:
    """누적 문서의 차량 수가 그 대회 참가 차량 수(팀 수의 두 배)와 같은지, 팀마다 두 대인지 본다."""
    teams = entries.teams(doc.season, doc.round)
    if not teams:
        return ["이 대회의 결과가 없어 참가 차량 수를 확인하지 못했다"]
    problems: list[str] = []
    expected = CARS_PER_TEAM * len(teams)
    if len(doc.rows) != expected:
        problems.append(f"차량 수가 {len(doc.rows)}대다(참가 {expected}대)")
    listed = [r["constructor_id"] for r in doc.rows if r["constructor_id"]]
    for team in sorted(teams | set(listed)):
        if listed.count(team) != CARS_PER_TEAM:
            problems.append(f"{team}의 차량이 {listed.count(team)}대다")
    return problems


def is_correction(doc: Document) -> bool:
    """제목이나 본문이 정정 문서임을 밝히는지 본다."""
    return bool(CORRECTION.search(doc.meta["title"]) or (doc.parsed and doc.parsed.correction))


def mark_superseded(documents: list[Document]) -> None:
    """같은 대회의 문서 사이에서 대체 관계를 정한다.

    누적 문서는 대회마다 표 하나가 유효하므로 나중에 나온 문서가 앞선 문서를 대체한다. 선언 문서는
    대회 안에서 쌓이는 문서라서, 정정 문서가 같은 선언(차량과 구성요소)을 다시 싣고 있는 앞선 문서만
    대체하고, 정정 표시가 없어도 같은 선언을 Previously used 값까지 그대로 다시 실은 앞선 문서를
    대체한다(repeats_rows). 이때 앞 문서에만 있던 선언 행은 dropped에 남긴다(조용히 사라지지 않게
    불일치 목록과 pu_usage의 basis에 적는다).

    대체 여부는 나중 문서를 읽어야 알 수 있다. 같은 대회의 나중 문서가 캐시에 없으면 앞 문서가 그
    문서로 대체되었는지(정정되었는지) 알 수 없으므로, 앞 문서를 held로 두고 파생 표와 검사에 쓰지
    않는다. 받지 않은 문서 자체는 아무것도 대체하지 않는다.
    """
    groups: dict[tuple, list[Document]] = {}
    for doc in sorted(documents, key=lambda d: d.order):
        groups.setdefault((doc.event_key, doc.kind), []).append(doc)
    for (_, kind), group in groups.items():
        for i, later in enumerate(group):
            for earlier in group[:i]:
                if later.parsed is None:
                    if earlier.parsed is not None and not earlier.held_by:
                        earlier.held_by = later.url
                elif kind == "pu_used" or (is_correction(later) and shares_rows(earlier, later)):
                    earlier.superseded_by, earlier.dropped = later.url, []
                elif repeats_rows(earlier, later):
                    earlier.superseded_by = later.url
                    earlier.dropped = dropped_rows(earlier, later)


def dropped_declarations(documents: list[Document]) -> list[tuple[Document, dict]]:
    """대체된 문서에서 빠진 선언 (앞 문서, 행) 목록. 같은 선언은 한 번만 싣는다.

    정정 표시 없는 재발행이 세 번 이상 이어지면(A, B, C) A와 B가 모두 C로 대체되어 같은 선언이
    두 문서의 dropped에 들어간다. (차량, 구성요소, Previously used, 대체한 문서)가 같으면 같은
    선언으로 보고 가장 먼저 낸 앞 문서의 것만 남긴다.
    """
    seen: set[tuple] = set()
    out: list[tuple[Document, dict]] = []
    for doc in sorted(documents, key=lambda d: d.order):
        for row in doc.dropped:
            key = (
                doc.season, doc.round, row.get("constructor_id", ""), row["car_number"],
                row["element"], row["previously_used"], doc.superseded_by,
            )  # fmt: skip
            if key not in seen:
                seen.add(key)
                out.append((doc, row))
    return out


def dropped_rows(earlier: Document, later: Document) -> list[dict]:
    """정정 표시 없이 다시 낸 나중 문서에 없는, 앞 문서의 차량 선언 행."""
    keys = {(r["car_number"], r["element"], r["previously_used"]) for r in later.rows}
    return [
        r
        for r in earlier.car_rows
        if (r["car_number"], r["element"], r["previously_used"]) not in keys
    ]


def shares_rows(earlier: Document, later: Document) -> bool:
    keys = {(r["car_number"], r["element"]) for r in later.rows}
    return any((r["car_number"], r["element"]) in keys for r in earlier.rows)


def repeats_rows(earlier: Document, later: Document) -> bool:
    """나중 선언 문서가 앞 문서의 선언을 Previously used 값까지 똑같이 다시 싣는지 본다.

    같은 대회에서 같은 차량의 같은 구성요소를 두 번째로 새로 쓰면 Previously used가 하나 늘어야
    한다. 값이 같으면 같은 선언을 다시 낸 것이다(2023 마이애미 문서 24와 26: 26은 24에서 Norris를
    뺀 나머지를 다시 싣는다). 제목에 정정 표시가 없어도 나중 문서가 앞 문서를 대체한다.
    """
    if earlier.parsed is None:
        return False
    keys = {
        (r["car_number"], r["element"], r["previously_used"])
        for r in later.rows
        if r["car_number"] is not None and r["previously_used"] is not None
    }
    return any((r["car_number"], r["element"], r["previously_used"]) in keys for r in earlier.rows)


# --- 문서 사이의 검사 ----------------------------------------------------------------------

Seat = tuple[str, int]  # (constructor_id, 차량 번호)
INCONSISTENCY_FIELDS = [
    "season", "kind", "constructor_id", "car_number", "element", "earlier_round", "later_round",
    "earlier_value", "new_declared", "expected", "actual", "difference", "earlier_url",
    "later_url", "note", "related_documents",
]  # fmt: skip
# 같은 차량의 PU 관련 처분 문서 제목("Offence - Car 33 - PU elements", "Infringement - Car 10 -
# Changes made during Parc Ferme" 등). 파크 페르메 교체 처분에도 PU 교체가 들어 있는 경우가 있다.
# 내용은 읽지 않고 제목만 본다.
DECISION_TITLE = re.compile(
    r"^(?:Offence|Infringement|Decision|Summons)\b.*?\bCar\s+(?P<car>\d+)\b.*"
    r"\b(?:PU|Power\s+Unit|Parc\s+Ferm)",
    re.I,
)


def seat_table(doc: Document) -> dict[Seat, dict[str, int]]:
    """누적 문서의 표를 좌석별로 본다."""
    return {(r["constructor_id"], r["car_number"]): r["used"] for r in doc.rows}


def pair_seats(earlier: set[Seat], later: set[Seat]) -> list[tuple[Seat, Seat]]:
    """앞뒤 누적 표의 차량을 좌석으로 잇는다.

    팀과 번호가 같으면 같은 좌석이다. 한 팀에서 번호가 하나만 바뀌었으면 드라이버가 바뀐 좌석으로
    보고 잇는다. 한 팀의 두 대가 모두 바뀌면 잇지 않는다.
    """
    pairs = [(seat, seat) for seat in sorted(earlier & later)]
    for team in sorted({team for team, _ in earlier ^ later}):
        gone = sorted(s for s in earlier - later if s[0] == team)
        came = sorted(s for s in later - earlier if s[0] == team)
        if len(gone) == len(came) == 1:
            pairs.append((gone[0], came[0]))
    return pairs


def seat_of(row: dict, seats: set[Seat], racing: dict[int, tuple[str, str]]) -> Seat | None:
    """선언 행이 누적 표의 어느 좌석인지 정한다.

    표에 없는 번호는 대체 드라이버다. 그 대회 결승에 그 번호가 나왔고 같은 팀에서 표의 차량 한 대만
    결승에 나오지 않았으면 그 좌석으로 본다. 그렇지 않으면 None이다.
    """
    team, car = row["constructor_id"], row["car_number"]
    if (team, car) in seats:
        return team, car
    ran = {number for number, (_, t) in racing.items() if t == team}
    absent = [s for s in seats if s[0] == team and s[1] not in ran]
    return absent[0] if car in ran and len(absent) == 1 else None


def declarations(documents: list[Document]) -> dict[tuple[int, int | None], list[dict]]:
    """대회별 새 구성요소 선언. 정상 문서의 행만, 게시 순서와 문서 안의 순서대로 모은다."""
    found: dict[tuple[int, int | None], list[dict]] = {}
    for doc in sorted(documents, key=lambda d: d.order):
        if doc.kind == "pu_new" and doc.status == "ok":
            rows = found.setdefault((doc.season, doc.round), [])
            rows.extend({**row, "url": doc.url} for row in doc.car_rows)
    return found


@dataclass
class Pending:
    """한 대회의 선언 문서 가운데 아직 쓸 수 없는 문서(검수 대기, 미수집).

    검수 대기 문서라도 표의 행을 모두 읽었으면 그 문서가 다루는 차량을 안다(rows). 그 밖의 차량에
    대한 판단은 이 문서와 상관없다. 미수집 문서나 행을 빠뜨린 문서가 있으면 어느 차량이 걸리는지
    알 수 없으므로 대회 전체를 막는다(whole).
    """

    counts: dict[str, int] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    whole: bool = False

    def describe(self) -> str:
        return ", ".join(f"{n} {status}" for status, n in sorted(self.counts.items()))

    def seats(self, seats: set[Seat], racing: dict[int, tuple[str, str]]) -> set[Seat] | None:
        """이 문서들이 다루는 좌석. 정할 수 없으면 None(대회 전체)이다."""
        if self.whole:
            return None
        found = {seat_of(row, seats, racing) for row in self.rows}
        return None if None in found else found  # type: ignore[return-value]


def pending_rounds(documents: list[Document]) -> dict[tuple[int, int | None], Pending]:
    """선언 문서 가운데 아직 쓸 수 없는 문서(검수 대기, 미수집, 보류)가 있는 대회."""
    found: dict[tuple[int, int | None], Pending] = {}
    for doc in documents:
        if doc.kind != "pu_new" or doc.status not in ("needs_review", "not_downloaded", "held"):
            continue
        pending = found.setdefault((doc.season, doc.round), Pending())
        pending.counts[doc.status] = pending.counts.get(doc.status, 0) + 1
        rows = doc.rows
        known = (
            doc.parsed is not None
            and getattr(doc.parsed, "complete", True)
            and all(r["car_number"] is not None and r.get("constructor_id") for r in rows)
        )
        if known:
            pending.rows.extend(rows)
        else:
            pending.whole = True
    return found


def blocked_seats(
    pending: dict, season: int, rounds: range, seats: set[Seat], entries: Entries
) -> set[Seat] | None:
    """여러 대회의 쓸 수 없는 선언 문서가 다루는 좌석을 모은다. 대회 전체가 막히면 None이다."""
    found: set[Seat] = set()
    for round_no in rounds:
        if (season, round_no) not in pending:
            continue
        racing = entries.starters.get((season, round_no), {})
        hit = pending[season, round_no].seats(seats, racing)
        if hit is None:
            return None
        found |= hit
    return found


def waiting_rounds(documents: list[Document]) -> set[tuple[int, int | None]]:
    """받지 않은 선언 문서가 있는 대회. 그 대회의 다른 선언도 정정되었을 수 있다."""
    return {(d.season, d.round) for d in documents if d.kind == "pu_new" and d.parsed is None}


def silent_rounds(documents: list[Document], entries: Entries) -> set[tuple[int, int]]:
    """결과가 있는데 manifest에 선언 문서가 하나도 없는 대회."""
    listed = {(d.season, d.round) for d in documents if d.kind == "pu_new"}
    seasons = {d.season for d in documents}
    return {key for key in entries.starters if key[0] in seasons and key not in listed}


def silent_note(season: int, rounds: range, silent: set[tuple[int, int]]) -> str:
    """사이 대회 가운데 선언 문서가 없는 대회를 밝히는 문구. 없으면 빈 문자열이다."""
    missing = [f"R{n}" for n in rounds if (season, n) in silent]
    if not missing:
        return ""
    return (
        f"{', '.join(missing)}에는 manifest에 pu_new 문서가 없어 그 대회 선언 수를 0으로 계산했다"
    )


def inconsistency(doc: Document, kind: str, seat: Seat, element: str, **values) -> dict:
    row = {
        "season": doc.season, "kind": kind, "constructor_id": seat[0], "car_number": seat[1],
        "element": element, "later_round": doc.round, "later_url": doc.url, "note": "",
    }  # fmt: skip
    row.update(values)
    known = row.get("actual") is not None and row.get("expected") is not None
    row["difference"] = row["actual"] - row["expected"] if known else None
    return row


def check_decrease(earlier: Document, later: Document) -> list[dict]:
    """같은 좌석의 누적 개수가 줄었으면 두 문서 모두에 문제로 남기고 불일치 행을 돌려준다.

    어느 쪽이 틀렸는지 알 수 없으므로 한쪽만 고르지 않는다.
    """
    before, after = seat_table(earlier), seat_table(later)
    found: list[dict] = []
    for a, b in pair_seats(set(before), set(after)):
        for element in before[a]:
            if element in after[b] and after[b][element] < before[a][element]:
                change = f"{b[1]}번 {element} {before[a][element]} -> {after[b][element]}"
                earlier.problems.append(f"다음 누적 문서(R{later.round})에서 값이 줄었다: {change}")
                later.problems.append(f"앞선 누적 문서(R{earlier.round})보다 값이 줄었다: {change}")
                found.append(
                    inconsistency(
                        later, "snapshot_decrease", b, element, earlier_round=earlier.round,
                        earlier_value=before[a][element], new_declared=None,
                        expected=before[a][element], actual=after[b][element],
                        earlier_url=earlier.url, note="두 문서 모두 검수 대기로 둔다",
                    )
                )  # fmt: skip
    return found


def check_decreases(chain: list[Document]) -> list[dict]:
    """시즌마다 라운드 순으로 이웃한 누적 문서 쌍에서 값이 줄었는지 한 번씩 본다.

    chain은 표를 확실히 읽은 누적 문서다. 줄어든 쌍의 두 문서는 검수 대기가 되지만 사슬에서
    빼지 않는다. 빼고 다시 이으면 이웃하지 않은 문서끼리 비교해 같은 끊김을 여러 번 적고, 정확히
    읽은 앞뒤 문서까지 검수 대기로 만든다(2023 Sargeant EX는 R14 5에서 R15 4로 한 번 줄었다).
    """
    found: list[dict] = []
    for season in sorted({d.season for d in chain}):
        docs = sorted((d for d in chain if d.season == season), key=lambda d: d.round)
        for earlier, later in zip(docs, docs[1:], strict=False):
            found.extend(check_decrease(earlier, later))
    return found


def check_sequence(
    earlier: Document, later: Document, declared: dict, entries: Entries,
    skip: set[Seat] | frozenset = frozenset(), silent: set | frozenset = frozenset(),
) -> tuple[list[dict], int]:  # fmt: skip
    """뒤 대회의 누적 값이 앞 대회의 누적 값에 그 사이 선언된 개수를 더한 값인지 본다.

    skip은 쓸 수 없는 선언 문서(검수 대기)가 다루는 앞 문서의 좌석이고 비교하지 않는다. 값이 줄어든
    칸은 check_decreases가 따로 적으므로 여기서 다시 적지 않는다. 사이 대회에 선언 문서가 manifest에
    없으면(silent) 그 대회의 선언 수를 0으로 계산하고 그 사실을 note에 적는다.
    (맞지 않는 경우의 목록, 비교한 칸 수)를 돌려준다.
    """
    before, after = seat_table(earlier), seat_table(later)
    added: dict[tuple[Seat, str], int] = {}
    stray: dict[str, set[int]] = {}
    for round_no in range(earlier.round, later.round):
        racing = entries.starters.get((earlier.season, round_no), {})
        for row in declared.get((earlier.season, round_no), []):
            seat = seat_of(row, set(before), racing)
            if seat is None:
                stray.setdefault(row["constructor_id"], set()).add(row["car_number"])
                continue
            added[seat, row["element"]] = added.get((seat, row["element"]), 0) + 1
    quiet = silent_note(earlier.season, range(earlier.round, later.round), silent)
    found: list[dict] = []
    compared = 0
    for a, b in pair_seats(set(before), set(after)):
        if a in skip:
            continue
        for element, value in before[a].items():
            if element not in after[b] or after[b][element] < value:
                continue
            compared += 1
            new = added.get((a, element), 0)
            if after[b][element] == value + new:
                continue
            notes = [f"앞 문서의 차량 번호는 {a[1]}번이다"] if a != b else []
            if stray.get(a[0]):
                cars = ", ".join(str(n) for n in sorted(stray[a[0]]))
                notes.append(f"같은 팀의 {cars}번 선언은 좌석을 정하지 못해 넣지 않았다")
            if quiet:
                notes.append(quiet)
            found.append(
                inconsistency(
                    later, "snapshot_sequence", b, element, earlier_round=earlier.round,
                    earlier_value=value, new_declared=new, expected=value + new,
                    actual=after[b][element], earlier_url=earlier.url, note=". ".join(notes),
                )
            )  # fmt: skip
    return found, compared


def check_first_snapshot(
    first: Document, declared: dict, entries: Entries, skip: set[Seat] | frozenset = frozenset()
) -> list[dict]:
    """시즌 첫 누적 문서를 그 앞 대회의 선언과 견준다: Previously used 값 + 선언 개수.

    skip은 쓸 수 없는 선언 문서가 다루는 좌석이고 비교하지 않는다.
    """
    seats = seat_table(first)
    groups: dict[tuple[Seat, str], list[tuple[int, dict]]] = {}
    for round_no in range(1, first.round):
        racing = entries.starters.get((first.season, round_no), {})
        for row in declared.get((first.season, round_no), []):
            seat = seat_of(row, set(seats), racing)
            if seat is not None and seat not in skip and row["element"] in seats[seat]:
                groups.setdefault((seat, row["element"]), []).append((round_no, row))
    found: list[dict] = []
    for (seat, element), rows in groups.items():
        round_no, row = min(rows, key=lambda item: item[1]["previously_used"])
        expected = row["previously_used"] + len(rows)
        if seats[seat][element] != expected:
            found.append(
                inconsistency(
                    first, "snapshot_sequence", seat, element, earlier_round=round_no,
                    earlier_value=row["previously_used"], new_declared=len(rows),
                    expected=expected, actual=seats[seat][element], earlier_url=row["url"],
                    note="앞 값은 선언 문서의 Previously used 값이다",
                )
            )  # fmt: skip
    return found


def check_previously_used(
    snapshot: Document, rows: list[dict], entries: Entries
) -> tuple[list[dict], int]:
    """같은 대회 선언 문서의 Previously used 값이 누적 문서의 값과 같은지 본다.

    같은 좌석의 같은 구성요소가 한 대회에서 두 번 선언되면 둘째는 하나 더 큰 값이어야 한다.
    (맞지 않는 경우의 목록, 비교한 선언 수)를 돌려준다.
    """
    seats = seat_table(snapshot)
    racing = entries.starters.get((snapshot.season, snapshot.round), {})
    seen: dict[tuple[Seat, str], int] = {}
    found: list[dict] = []
    compared = 0
    for row in rows:
        seat = seat_of(row, set(seats), racing)
        if seat is None or row["element"] not in seats[seat]:
            continue
        compared += 1
        earlier = seen.get((seat, row["element"]), 0)
        seen[seat, row["element"]] = earlier + 1
        expected = seats[seat][row["element"]] + earlier
        if row["previously_used"] != expected:
            found.append(
                inconsistency(
                    snapshot, "previously_used", (seat[0], row["car_number"]), row["element"],
                    earlier_round=snapshot.round, earlier_value=seats[seat][row["element"]],
                    new_declared=earlier, expected=expected, actual=row["previously_used"],
                    earlier_url=snapshot.url, later_url=row["url"],
                )
            )  # fmt: skip
    return found, compared


def unread_facts(row: dict) -> list[str]:
    """배정 문장이 있는데 읽지 못한 값(허용 개수, 몇 번째인지). 문장이 없으면 빈 목록이다.

    허용 개수는 문장에 "allowed"가 있는데 읽지 못한 경우, 순서는 "is the <낱말>"이 있는데 읽지
    못한 경우다. 둘 다 없으면 어느 검사도 할 수 없으므로 둘 다 읽지 못한 것으로 본다.
    """
    text = row["allocation_text"]
    if not text:
        return []
    unread: list[str] = []
    if row["allowed"] is None and (ALLOWED_WORD.search(text) or row["ordinal"] is None):
        unread.append("허용 개수")
    if row["ordinal"] is None and (ORDINAL_HINT.search(text) or row["allowed"] is None):
        unread.append("순서")
    return unread


def check_statements(doc: Document) -> list[dict]:
    """배정 문장이 같은 문서의 표와 어긋나는 경우: 몇 번째인지, 적합 여부, 시즌 표기.

    문장은 있는데 허용 개수나 순서를 읽지 못해 검사를 건너뛰는 행은 statement_unread로 적는다.
    """
    found: list[dict] = []
    for row in doc.car_rows:
        nth = row["previously_used"] + 1
        seat = (row["constructor_id"], row["car_number"])
        base = {
            "earlier_round": doc.round, "earlier_value": row["previously_used"],
            "new_declared": 1, "earlier_url": doc.url,
        }  # fmt: skip
        unread = unread_facts(row)
        if unread:
            note = f"배정 문장에서 {', '.join(unread)}를 읽지 못해 그 검사를 하지 않았다"
            found.append(
                inconsistency(doc, "statement_unread", seat, row["element"], **base,
                              expected=None, actual=None, note=note)
            )  # fmt: skip
        if row["ordinal"] is not None and row["ordinal"] != nth:
            note = "문장에 적힌 순서(actual)가 Previously used + 1(expected)과 다르다"
            found.append(
                inconsistency(doc, "statement_ordinal", seat, row["element"], **base,
                              expected=nth, actual=row["ordinal"], note=note)
            )  # fmt: skip
        if row["allowed"] is None or row["within_allocation"] is None:
            continue
        if row["allowed_season"] != doc.season:
            note = "문장에 적힌 시즌(actual)이 문서의 시즌(expected)과 다르다"
            found.append(
                inconsistency(doc, "statement_season", seat, row["element"], **base,
                              expected=doc.season, actual=row["allowed_season"], note=note)
            )  # fmt: skip
        if row["within_allocation"] != (nth <= row["allowed"]):
            note = "적합 여부가 허용 개수(expected)와 Previously used + 1(actual)의 비교와 다르다"
            found.append(
                inconsistency(doc, "statement_verdict", seat, row["element"], **base,
                              expected=row["allowed"], actual=nth, note=note)
            )  # fmt: skip
    return found


def pu_decisions(manifest_rows: list[dict]) -> dict[tuple[int, int], list[tuple[int, str]]]:
    """(시즌, 차량 번호) -> 그 차량의 PU 관련 처분 문서 (라운드, URL) 목록. manifest 제목만 본다."""
    from pipeline import events

    found: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for meta in manifest_rows:
        match = DECISION_TITLE.match(meta["title"])
        if meta["doc_type"] in DOC_TYPES or not match:
            continue
        season = int(meta["season"])
        round_no = events.round_for(season, meta["event"])
        if round_no is not None:
            found.setdefault((season, int(match["car"])), []).append((round_no, meta["url"]))
    return {key: sorted(value) for key, value in found.items()}


def attach_decisions(inconsistencies: list[dict], decisions: dict) -> None:
    """불일치 행에 두 대회 사이(양 끝 포함)에 나온 같은 차량의 PU 처분 문서를 붙인다.

    선언 문서에 없는 구성요소가 처분 문서에만 나오는 경우가 있어, 불일치를 읽는 사람이 원문을 찾도록
    돕는 열이다. 값을 고치는 데 쓰지 않는다.
    """
    for row in inconsistencies:
        first, last = row["earlier_round"], row["later_round"]
        hits = [
            f"R{round_no} {url}"
            for round_no, url in decisions.get((row["season"], row["car_number"]), [])
            if first <= round_no <= last
        ]
        row["related_documents"] = " ".join(hits)


def cross_checks(documents: list[Document], entries: Entries) -> tuple[list[dict], dict[str, int]]:
    """문서 사이의 검사를 모두 돌린다. (불일치 목록, 검사 건수)를 돌려준다.

    사슬은 표를 확실히 읽은 누적 문서(이 검사 전에 정상인 문서)로 만든다. 누적 값이 줄어든 이웃 쌍은
    두 문서 모두 검수 대기로 바꾸지만 사슬에는 남겨 이웃 관계를 유지한다. 그 밖의 불일치는 목록에만
    적는다. 검수 대기 선언 문서가 끼면 그 문서가 다루는 좌석만 비교에서 빼고, 어느 좌석인지 알 수
    없으면(미수집 등) 그 쌍 전체를 건너뛴다.
    """
    snapshots = [d for d in documents if d.kind == "pu_used" and d.status == "ok"]
    found = check_decreases(snapshots)
    declared = declarations(documents)
    pending = pending_rounds(documents)
    silent = silent_rounds(documents, entries)
    stats = {
        "sequence_pairs": 0, "sequence_cells": 0, "sequence_pairs_skipped": 0,
        "sequence_seats_skipped": 0, "previously_used_checked": 0,
    }  # fmt: skip
    for season in sorted({d.season for d in snapshots}):
        chain = sorted((d for d in snapshots if d.season == season), key=lambda d: d.round)
        first = chain[0]
        skip = blocked_seats(
            pending, season, range(1, first.round), set(seat_table(first)), entries
        )
        if skip is not None:
            found.extend(check_first_snapshot(first, declared, entries, skip))
        for earlier, later in zip(chain, chain[1:], strict=False):
            seats = set(seat_table(earlier))
            skip = blocked_seats(pending, season, range(earlier.round, later.round), seats, entries)
            if skip is None:
                stats["sequence_pairs_skipped"] += 1
                continue
            rows, compared = check_sequence(earlier, later, declared, entries, skip, silent)
            found.extend(rows)
            stats["sequence_pairs"] += 1
            stats["sequence_cells"] += compared
            stats["sequence_seats_skipped"] += len(skip)
        for doc in chain:
            rows, compared = check_previously_used(
                doc, declared.get((season, doc.round), []), entries
            )
            found.extend(rows)
            stats["previously_used_checked"] += compared
    for doc in documents:
        if doc.kind == "pu_new" and doc.status == "ok":
            found.extend(check_statements(doc))
    found.extend(dropped_inconsistencies(documents))
    found.extend(check_allocations(documents))
    return found, stats


def dropped_inconsistencies(documents: list[Document]) -> list[dict]:
    """정정 표시 없이 다시 낸 문서에서 빠진 앞 문서의 선언. 어느 쪽이 맞는지 정하지 않는다."""
    by_url = {d.url: d for d in documents}
    found: list[dict] = []
    note = (
        "앞 문서의 선언(expected 1건)이 정정 표시 없이 다시 낸 나중 문서에 없다(actual 0건). 앞 "
        "문서는 대체되어 이 선언은 pu_usage와 pu_ice_events에 들어가지 않는다"
    )
    for doc, row in dropped_declarations(documents):
        later = by_url[doc.superseded_by]
        found.append(
            inconsistency(
                later, "superseded_row_dropped", (row.get("constructor_id", ""),
                row["car_number"]), row["element"], earlier_round=doc.round,
                earlier_value=row["previously_used"], new_declared=1, expected=1, actual=0,
                earlier_url=doc.url, note=note,
            )
        )  # fmt: skip
    return found


# --- 정제 테이블 만들기 -----------------------------------------------------------------------

DOCUMENT_FIELDS = [
    "season", "round", "event", "doc_type", "doc_number", "published_at", "url", "rows",
    "teams", "drivers", "status", "superseded_by", "held_by", "problems",
]  # fmt: skip
ROW_KEYS = ["season", "round", "event", "doc_number", "published_at"]
CAR_FIELDS = ["car_number", "team_text", "driver_name", "driver_id", "constructor_id"]
USED_FIELDS = [*ROW_KEYS, *CAR_FIELDS, "element", "used", "document_status", "source_url"]
NEW_FIELDS = [
    *ROW_KEYS, *CAR_FIELDS, "element", "previously_used", "allocation_text", "within_allocation",
    "document_status", "source_url",
]  # fmt: skip
USAGE_FIELDS = [
    "season", "round", "car_number", "driver_id", "constructor_id", "element",
    "used_before_event", "new_at_event", "used_after_event", "basis",
]  # fmt: skip
ICE_FIELDS = [
    "season", "round", "event", "car_number", "driver_id", "driver_name", "constructor_id",
    "ice_number", "printed_previously_used", "stated_ordinal", "within_allocation", "conflict",
    "source_url",
]  # fmt: skip
ALLOCATION_FIELDS = [
    "season", "element", "allowed", "first_round", "documents", "statement", "source_url",
]  # fmt: skip


def document_row(doc: Document) -> dict:
    """문서 한 건의 요약 행: 추출 행 수, 팀 수, 드라이버 수, 상태.

    팀 수는 차량이 적힌 행의 컨스트럭터 수다. 컨스트럭터를 붙이지 못한 행은 원문 팀 표기로 센다.
    """
    parsed = doc.parsed is not None
    teams = {r.get("constructor_id") or plain(r["team_text"]) for r in doc.car_rows}
    return {
        "season": doc.season, "round": doc.round, "event": doc.meta["event"],
        "doc_type": doc.kind, "doc_number": doc.doc_number, "published_at": doc.published_at,
        "url": doc.url, "rows": len(doc.rows) if parsed else None,
        "teams": len(teams) if parsed else None,
        "drivers": len({r["driver_name"] for r in doc.car_rows}) if parsed else None,
        "status": doc.status, "superseded_by": doc.superseded_by, "held_by": doc.held_by,
        "problems": " / ".join(doc.problems) if parsed else "",
    }  # fmt: skip


def row_base(doc: Document, row: dict) -> dict:
    """행 테이블의 공통 열: 문서 정보와 원문 그대로의 차량, 팀, 드라이버."""
    base = {
        "season": doc.season, "round": doc.round, "event": doc.meta["event"],
        "doc_number": doc.doc_number, "published_at": doc.published_at,
        "document_status": doc.status, "source_url": doc.url,
    }  # fmt: skip
    return {**base, **{name: row[name] for name in CAR_FIELDS}}


def used_rows(doc: Document) -> list[dict]:
    """누적 문서의 표를 문서 x 차량 x 구성요소 행으로 편다."""
    return [
        {**row_base(doc, row), "element": element, "used": row["used"][element]}
        for row in doc.rows
        for element in doc.parsed.elements
    ]


def new_rows(doc: Document) -> list[dict]:
    """선언 문서의 행. 배정 문장과 적합 여부는 문서가 말한 대로만 싣는다."""
    names = ["element", "previously_used", "allocation_text", "within_allocation"]
    return [{**row_base(doc, row), **{name: row[name] for name in names}} for row in doc.rows]


def usage_seats(
    snapshot: Document | None, rows: list[dict], racing: dict[int, tuple[str, str]]
) -> tuple[dict[Seat, dict], dict[Seat, list[dict]]]:
    """한 대회의 좌석과 좌석마다의 선언 행.

    누적 표의 차량이 좌석이다. 표에 없는 번호의 선언(대체 드라이버)은 seat_of로 원래 좌석에 붙인다
    (2020 Eifel 27번 Hülkenberg는 18번 좌석, 2023 미국 3번 Ricciardo는 40번 좌석). 좌석을 정하지
    못한 선언은 그 번호로 따로 둔다.
    """
    cars: dict[Seat, dict] = {
        (r["constructor_id"], r["car_number"]): r for r in (snapshot.rows if snapshot else [])
    }
    seats = set(cars)
    mine: dict[Seat, list[dict]] = {}
    for row in rows:
        seat = seat_of(row, seats, racing) or (row["constructor_id"], row["car_number"])
        cars.setdefault(seat, {**row, "used": None})
        mine.setdefault(seat, []).append(row)
    return cars, mine


def count_basis(
    before: int, hits: list[dict], seat: Seat, blocked: set[Seat] | None, pending: Pending | None,
    listed: int,
) -> tuple[int | None, int | None, str]:  # fmt: skip
    """한 칸의 (new, after, basis 뒷부분)을 정한다.

    new는 정상 선언 수다. 그 대회의 선언 문서가 manifest에 없거나, 쓸 수 없는 선언 문서가 이 좌석을
    다루거나 다루는지 알 수 없으면 비운다. 선언의 Previously used가 before, before+1, ...과 맞지
    않으면 두 문서가 이 대회 이전 개수를 달리 적은 것이므로 after를 비운다(어느 쪽도 고르지 않는다).
    """
    if not listed:
        return None, None, "; new=unknown (no pu_new document listed for this event); after=unknown"
    if blocked is None or seat in blocked:
        return None, None, f"; new=unknown (pu_new pending: {pending.describe()}); after=unknown"
    other = f" (pu_new pending for other cars: {pending.describe()})" if pending else ""
    if not hits:
        return 0, before, f"; new=none in {listed} pu_new documents{other}; after=before+new"
    urls = " ".join(dict.fromkeys(r["url"] for r in hits))
    cars = sorted({r["car_number"] for r in hits if r["car_number"] != seat[1]})
    if cars:
        urls += f" (declared for car {', '.join(map(str, cars))} in this seat)"
    printed = sorted(r["previously_used"] for r in hits)
    if printed != list(range(before, before + len(hits))):
        said = ", ".join(map(str, printed))
        note = f"; after=unknown (pu_new Previously used {said} differs from before {before})"
        return len(hits), None, f"; new=pu_new {urls}{other}{note}"
    return len(hits), before + len(hits), f"; new=pu_new {urls}{other}; after=before+new"


def event_usage(
    key: tuple[int, int | None], snapshot: Document | None, rows: list[dict],
    pending: Pending | None, listed: int, racing: dict[int, tuple[str, str]] | None = None,
    dropped: list[dict] = (),
) -> list[dict]:  # fmt: skip
    """한 대회의 좌석별, 구성요소별 누적 행을 만든다.

    누적 문서에 있는 좌석은 모든 구성요소를, 선언 문서에만 있는 좌석은 선언된 구성요소만 싣는다.
    선언 문서에만 있는 좌석의 이전 개수는 그 문서의 Previously used 값이다. listed는 그 대회의
    선언 문서 수(상태와 상관없이 manifest에 있는 것)다. 하나도 없으면 새 구성요소가 없었다고
    단정하지 않고 new와 after를 비워 둔다. dropped는 정정 표시 없이 다시 낸 문서에서 빠진 앞 문서의
    선언(url, later_url 포함)이고, 세지 않은 채 basis에 그 사실을 적는다.
    """
    racing = racing or {}
    cars, mine = usage_seats(snapshot, rows, racing)
    blocked = (
        pending.seats(set(seat_table(snapshot)) if snapshot else set(), racing)
        if pending
        else set()
    )
    gone: dict[tuple[Seat, str], list[str]] = {}
    for row in dropped:
        seat = seat_of(row, set(cars), racing) or (row.get("constructor_id"), row["car_number"])
        gone.setdefault((seat, row["element"]), []).append(
            f"; dropped=pu_new {row['url']} declared car {row['car_number']} "
            f"(Previously used {row['previously_used']}) but {row['later_url']} reissued it "
            "without a correction label and without this row (not counted)"
        )
    out: list[dict] = []
    for seat, info in cars.items():
        declared_here = mine.get(seat, [])
        elements = info["used"] or [
            e for e in ELEMENTS if any(r["element"] == e for r in declared_here)
        ]
        for element in elements:
            hits = [r for r in declared_here if r["element"] == element]
            if info["used"]:
                before, basis = info["used"][element], f"before=pu_used {snapshot.url}"
            else:
                first = min(hits, key=lambda r: r["previously_used"])
                before = first["previously_used"]
                basis = f"before=previously_used in pu_new {first['url']}"
            new, after, rest = count_basis(before, hits, seat, blocked, pending, listed)
            out.append(
                {
                    "season": key[0], "round": key[1], "car_number": info["car_number"],
                    "driver_id": info["driver_id"], "constructor_id": info["constructor_id"],
                    "element": element, "used_before_event": before, "new_at_event": new,
                    "used_after_event": after,
                    "basis": basis + rest + "".join(gone.get((seat, element), [])),
                }
            )  # fmt: skip
    return out


def usage_rows(documents: list[Document], entries: Entries) -> list[dict]:
    """대회별, 좌석별 누적 사용 개수(파생 표). 정상 문서만 쓴다."""
    declared = declarations(documents)
    pending = pending_rounds(documents)
    snapshots = {
        (d.season, d.round): d for d in documents if d.kind == "pu_used" and d.status == "ok"
    }
    listed: dict[tuple, int] = {}
    dropped: dict[tuple, list[dict]] = {}
    for doc in documents:
        if doc.kind == "pu_new":
            listed[doc.season, doc.round] = listed.get((doc.season, doc.round), 0) + 1
    for doc, row in dropped_declarations(documents):
        dropped.setdefault((doc.season, doc.round), []).append(
            {**row, "url": doc.url, "later_url": doc.superseded_by}
        )
    out: list[dict] = []
    for key in sorted(set(snapshots) | set(declared), key=lambda k: (k[0], k[1] or 0)):
        out.extend(
            event_usage(
                key, snapshots.get(key), declared.get(key, []), pending.get(key),
                listed.get(key, 0), entries.starters.get(key, {}), dropped.get(key, []),
            )
        )  # fmt: skip
    return out


CONFLICT_KINDS = ("previously_used", "statement_ordinal")


def ice_rows(documents: list[Document], inconsistencies: list[dict] = ()) -> list[dict]:
    """새 ICE 투입 이벤트. 정상 선언 문서의 ICE 행이다.

    순번(ice_number)은 Previously used + 1이다. 같은 대회 누적 문서가 이전 개수를 달리 적거나
    (previously_used) 같은 문서의 배정 문장이 다른 순서를 적으면(statement_ordinal) 어느 쪽도
    고르지 않고 순번을 비운다. 원문 값은 printed_previously_used, stated_ordinal에 따로 두고, 어긋난
    내용은 conflict에 적는다. 받지 않은 선언 문서가 있는 대회는 그 대회의 다른 문서도 정정되었을
    수 있으므로 싣지 않는다.
    """
    conflicts: dict[tuple[str, int, str], list[str]] = {}
    for issue in inconsistencies:
        if issue["kind"] in CONFLICT_KINDS:
            key = (issue["later_url"], issue["car_number"], issue["element"])
            conflicts.setdefault(key, []).append(
                f"{issue['kind']} (expected {issue['expected']}, actual {issue['actual']})"
            )
    waiting = waiting_rounds(documents)
    out: list[dict] = []
    for doc in documents:
        if doc.kind != "pu_new" or doc.status != "ok" or (doc.season, doc.round) in waiting:
            continue
        for row in doc.car_rows:
            if row["element"] != "ICE":
                continue
            base = row_base(doc, row)
            conflict = conflicts.get((doc.url, row["car_number"], "ICE"), [])
            out.append(
                {
                    **{name: base[name] for name in ICE_FIELDS if name in base},
                    "ice_number": None if conflict else row["previously_used"] + 1,
                    "printed_previously_used": row["previously_used"],
                    "stated_ordinal": row["ordinal"],
                    "within_allocation": row["within_allocation"],
                    "conflict": "; ".join(conflict),
                }
            )
    return out


def allocation_values(documents: list[Document]) -> dict[tuple[int, str, int], list[tuple]]:
    """(시즌, 구성요소, 허용 개수) -> 그 값을 밝힌 (문서, 문장) 목록. 게시 순서대로다.

    정상 선언 문서의 문장만 쓴다. 받지 않은 선언 문서가 있는 대회는 그 대회의 다른 문서도 정정되었을
    수 있으므로 쓰지 않는다. 문서 한 건이 같은 값을 여러 문장에서 밝혀도 한 번만 센다.
    """
    waiting = waiting_rounds(documents)
    found: dict[tuple[int, str, int], list[tuple]] = {}
    for doc in sorted(documents, key=lambda d: d.order):
        if doc.kind != "pu_new" or doc.status != "ok" or (doc.season, doc.round) in waiting:
            continue
        for row in doc.rows:
            if row["allowed"] is None or row["allowed_season"] != doc.season:
                continue
            stated = found.setdefault((doc.season, row["element"], row["allowed"]), [])
            if all(d is not doc for d, _ in stated):
                stated.append((doc, row["allocation_text"]))
    return found


def allocation_rows(documents: list[Document]) -> list[dict]:
    """문서가 밝힌 시즌별 허용 개수. 값이 처음 나온 문서의 문장을 싣는다.

    한 시즌 안에서 값이 달라지면(2020년 ICE는 2개에서 3개로 바뀐다) 값마다 한 행을 둔다.
    documents는 그 값을 밝힌 문서 수이고, 한 건뿐인 값은 오타일 수 있어 check_allocations가 불일치
    목록에 적는다.
    """
    values = allocation_values(documents)
    out: list[dict] = []
    for key in sorted(values, key=lambda k: (k[0], ELEMENTS.index(k[1]), k[2])):
        doc, statement = values[key][0]
        out.append(
            {
                "season": key[0], "element": key[1], "allowed": key[2], "first_round": doc.round,
                "documents": len(values[key]), "statement": statement, "source_url": doc.url,
            }
        )  # fmt: skip
    return sorted(out, key=lambda r: (r["season"], ELEMENTS.index(r["element"]), r["first_round"]))


def check_allocations(documents: list[Document]) -> list[dict]:
    """한 시즌의 한 구성요소에 허용 개수가 여럿이고 그 가운데 문서 한 건에만 나온 값을 적는다.

    expected는 같은 시즌의 다른 값 가운데 가장 많은 문서가 밝힌 값이다. 시즌 도중 규정이 바뀐 경우
    (2020년 ICE 2개에서 3개)도 여기에 걸릴 수 있으므로 어느 값이 맞는지 정하지 않는다.

    두 문서는 다른 불일치와 같이 게시 순서대로 earlier와 later에 둔다. 값이 한 건뿐인 문서가 그 값이
    처음 나온 문서보다 먼저일 수도, 나중일 수도 있다. earlier_value는 earlier 문서가 밝힌 값이고,
    어느 문서가 한 건뿐인 값인지는 note에 적는다.
    """
    values = allocation_values(documents)
    found: list[dict] = []
    for (season, element, allowed), stated in sorted(values.items()):
        others = [
            (len(v), k[2], v[0][0]) for k, v in values.items()
            if k[:2] == (season, element) and k[2] != allowed
        ]  # fmt: skip
        if len(stated) != 1 or not others:
            continue
        count, common, source = max(others, key=lambda item: (item[0], -item[1]))
        doc = stated[0][0]
        note = (
            f"허용 개수 {allowed}(actual)는 문서 한 건(R{doc.round})에만 나온다. 같은 "
            f"시즌 다른 값 {common}(expected)은 문서 {count}건에 나오고, 그 값이 처음 나온 문서는 "
            f"R{source.round}다. earlier와 later는 두 문서의 게시 순서다"
        )
        (earlier, earlier_value), (later, _) = sorted(
            [(doc, allowed), (source, common)], key=lambda pair: pair[0].order
        )
        found.append(
            inconsistency(
                later, "allocation_single_document", ("", None), element,
                earlier_round=earlier.round, earlier_value=earlier_value, new_declared=None,
                expected=common, actual=allowed, earlier_url=earlier.url, note=note,
            )
        )  # fmt: skip
    return found


def failure_rows(documents: list[Document], today: str) -> list[dict]:
    """검수 대기 문서 목록. 처음 기록한 날짜는 manifest.replace_failures가 유지한다."""
    return [
        {
            "season": doc.season,
            "round": doc.round,
            "event": doc.meta["event"],
            "doc_type": doc.kind,
            "url": doc.url,
            "problems": " / ".join(doc.problems),
            "recorded_at": today,
        }  # fmt: skip
        for doc in documents
        if doc.status == "needs_review"
    ]


def frame(rows: list[dict], fields: list[str], integers: list[str], booleans: tuple = ()):
    """행 목록을 정해진 열과 자료형의 표로 만든다. 빈 값이 있는 정수 열도 정수로 둔다."""
    import pandas as pd

    table = pd.DataFrame(rows, columns=fields)
    for name in integers:
        table[name] = table[name].astype("Int64")
    for name in booleans:
        table[name] = table[name].astype("boolean")
    return table


def build(only_cached: bool = False) -> dict[str, int]:
    """manifest의 PU 문서를 모두 파싱해 정제 테이블, 파생 테이블, 실패 목록을 쓴다.

    only_cached가 거짓이면 로컬 캐시에 없는 원문을 manifest를 보고 먼저 받는다(sha256이 다르면
    멈춘다). 참이면 네트워크 요청 없이 캐시에 있는 문서만 읽고 나머지는 not_downloaded로 적는다.
    """
    from pipeline import manifest
    from pipeline.config import CURATED_DIR, PU_ELEMENTS_FIRST_SEASON, RAW_DIR
    from pipeline.http import utc_now_iso
    from pipeline.sources import fia_docs

    if not only_cached:
        fia_docs.download_documents(DOC_TYPES)
    manifest_rows = manifest.read_rows(fia_docs.INDEX_MANIFEST)
    documents = load_documents(manifest_rows, RAW_DIR)
    entries = load_entries(PU_ELEMENTS_FIRST_SEASON)
    link_documents(documents, entries)
    for doc in documents:
        if doc.kind == "pu_used" and doc.parsed is not None and doc.round is not None:
            doc.problems.extend(check_cars(doc, entries))
    mark_superseded(documents)
    inconsistencies, stats = cross_checks(documents, entries)
    attach_decisions(inconsistencies, pu_decisions(manifest_rows))

    out = CURATED_DIR / "fia"
    out.mkdir(parents=True, exist_ok=True)
    counts = ["used", "previously_used", "used_before_event", "new_at_event", "used_after_event"]
    used = frame(
        [r for d in documents if d.kind == "pu_used" for r in used_rows(d)],
        USED_FIELDS, ["round", "car_number", "used"],
    )  # fmt: skip
    new = frame(
        [r for d in documents if d.kind == "pu_new" for r in new_rows(d)],
        NEW_FIELDS, ["round", "car_number", "previously_used"], ("within_allocation",),
    )  # fmt: skip
    usage = frame(
        usage_rows(documents, entries), USAGE_FIELDS, ["round", "car_number", *counts[2:]]
    )
    ice = frame(
        ice_rows(documents, inconsistencies), ICE_FIELDS,
        ["round", "car_number", "ice_number", "printed_previously_used", "stated_ordinal"],
        ("within_allocation",),
    )  # fmt: skip
    allocations = frame(
        allocation_rows(documents), ALLOCATION_FIELDS, ["allowed", "first_round", "documents"]
    )
    listed = frame(
        [document_row(d) for d in documents], DOCUMENT_FIELDS,
        ["round", "rows", "teams", "drivers"],
    )  # fmt: skip
    order = [
        "season",
        "later_round",
        "kind",
        "constructor_id",
        "car_number",
        "element",
        "later_url",
    ]
    issues = frame(
        inconsistencies, INCONSISTENCY_FIELDS,
        [n for n in INCONSISTENCY_FIELDS if n.endswith(("round", "value")) or n in
         ("car_number", "new_declared", "expected", "actual", "difference")],
    ).sort_values(order, kind="stable")  # fmt: skip
    used.to_parquet(out / "pu_used.parquet", index=False, compression="zstd")
    new.to_parquet(out / "pu_new.parquet", index=False, compression="zstd")
    usage.to_parquet(out / "pu_usage.parquet", index=False, compression="zstd")
    listed.to_csv(out / "pu_documents.csv", index=False)
    ice.to_csv(out / "pu_ice_events.csv", index=False)
    allocations.to_csv(out / "pu_allocations.csv", index=False)
    issues.to_csv(out / "pu_inconsistencies.csv", index=False)

    # 실패 목록은 문서 유형별로 갈아 끼운다(다른 파서의 기록은 건드리지 않는다)
    failures = failure_rows(documents, utc_now_iso()[:10])
    manifest.replace_failures(DOC_TYPES, failures)
    statuses = [d.status for d in documents]
    return {
        "documents": len(documents), **{s: statuses.count(s) for s in sorted(set(statuses))},
        "used_rows": len(used), "new_rows": len(new), "usage_rows": len(usage),
        "ice_events": len(ice), "allocations": len(allocations),
        "inconsistencies": len(issues), **stats, "failures": len(failures),
    }  # fmt: skip


if __name__ == "__main__":
    for name, n in build(only_cached="--cached" in sys.argv[1:]).items():
        print(f"pu_elements {name}: {n}")
