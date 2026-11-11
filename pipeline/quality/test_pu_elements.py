"""T6 PU 구성요소 문서 파서 검증."""

import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
import pytest

from pipeline import manifest
from pipeline.config import CURATED_DIR, RAW_DIR
from pipeline.http import sha256_bytes
from pipeline.parsers import pu_elements as pu
from pipeline.sources import fia_docs

FIA = CURATED_DIR / "fia"
STATUSES = {"ok", "needs_review", "not_downloaded", "superseded", "held"}
# 원문 자체가 어긋나 자동으로 읽지 않는 문서(파일 이름 -> 까닭). 사이트에는 "검수 대기"로 표시한다.
KNOWN_FAILURES = {
    "2022 Belgian Grand Prix - New PU elements for this Event, Parc Fermé issue.pdf": (
        "MGU-K 표에는 Yuki Tsunoda가 있는데 배정 문장은 Pierre Gasly를 가리킨다"
    ),
    "2025_chinese_grand_prix_-_pu_elements_used_per_driver_up_to_now.pdf": (
        "Isack Hadjar의 행에 차량 번호가 30으로 적혀 30번이 두 번 나온다"
    ),
    "2024 Bahrain Grand Prix - New PU elements for this Competition.pdf": (
        "CE 표의 Previously used 칸이 비어 있다"
    ),
    "2023 Miami Grand Prix - New PU elements for this Competition.pdf": (
        "CE 표의 Previously used 칸이 비어 있다"
    ),
    # 2023 Sargeant(2번) EX: R13, R14는 5, R15부터 4. 값이 줄어든 이웃 쌍(R14, R15)만 검수 대기로
    # 둔다. 앞뒤의 R13, R16 문서는 정확히 읽혔고 이웃 쌍과의 값도 맞으므로 정상이다.
    "2023 Italian Grand Prix - PU elements used per driver up to now.pdf": "Sargeant EX 5 -> 4",
    "2023 Singapore Grand Prix - PU elements used per driver up to now.pdf": "Sargeant EX 5 -> 4",
    "2025_japanese_grand_prix_-_pu_elements_used_per_driver_up_to_now.pdf": (
        "Tsunoda와 Lawson이 팀을 맞바꾼 대회인데 표는 앞 대회의 번호, 이름, 팀 조합 그대로다"
    ),
}
# 원문을 다시 파싱해 정제 데이터와 대조하는 표본. 양식이 서로 다른 문서를 골랐다.
SAMPLE = [
    "2020 Austrian Grand Prix - New PU elements for this Event.pdf",  # 한 쪽 양식, 줄바꿈된 팀 칸
    "2020 Sakhir Grand Prix - PU elements used per driver up to now.pdf",  # 대체 드라이버 셋
    "2021 Azerbaijan Grand Prix - New PU elements for this Event.pdf",  # 69행, 쪽을 넘는 표
    "2022 Belgian Grand Prix - New PU elements for this Event, Parc Fermé issue.pdf",  # 실패 문서
    "2025_australian_grand_prix_-_new_pu_elements_for_this_competition.pdf",  # "All drivers"
    "2025_bahrain_grand_prix_-_pu_elements_used_per_driver_up_to_now.pdf",  # 왼쪽 맞춤 숫자
]
MARGIN = 56.7


def file_name(url: str) -> str:
    return Path(unquote(url)).name


# --- 합성 입력 ---------------------------------------------------------------------------------


def word(text: str, x0: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + 5.5 * len(text), "top": top, "bottom": top + 10}


def prose(top: float, text: str, x0: float = MARGIN) -> list[dict]:
    """글 한 줄의 낱말. x0에서 시작해 차례로 놓는다."""
    words: list[dict] = []
    for part in text.split():
        words.append(word(part, x0, top))
        x0 = words[-1]["x1"] + 3
    return words


def cells(top: float, *pairs: tuple[float, str]) -> list[dict]:
    """(왼쪽 좌표, 글) 쌍으로 표의 한 줄을 만든다."""
    return [w for x0, text in pairs for w in prose(top, text, x0)]


def lines(*rows: list[dict], page: int = 1) -> list[pu.Line]:
    return pu.group_lines([w for row in rows for w in row], page)


USED_HEADER = [
    (MARGIN, "N°"), (83.3, "Car"), (225.1, "Driver"), (320.8, "ICE"), (355.3, "TC"),
    (388.1, "MGU-H"), (437.7, "MGU-K"), (484.9, "ES"), (514.4, "CE"), (540.0, "EX"),
]  # fmt: skip
CENTERED = (326.3, 359.2, 399.0, 448.6, 487.6, 517.2, 542.8)  # 머리글 가운데에 맞춘 숫자
LEFT = (320.9, 355.4, 388.2, 437.8, 485.0, 514.5, 540.1)  # 머리글 왼쪽 끝에 맞춘 숫자


def used_line(top: float, number: str, team: str, driver: str, values: str, xs=CENTERED):
    counts = list(zip(xs, values.split(), strict=False))
    return cells(top, (MARGIN, number), (83.3, team), (225.1, driver), *counts)


NEW_HEADER = [(MARGIN, "Number"), (110.0, "Car"), (280.0, "Driver"), (410.0, "Previously used ICE")]


def new_line(top: float, number: str, team: str, driver: str, count: str) -> list[dict]:
    return cells(top, (MARGIN, number), (110.0, team), (280.0, driver), (462.0, count))


WITHIN = (
    "is one of the three new internal combustion engines allowed for the 2021 Championship "
    "season and this is in conformity with Article 23.3a of the 2021 Formula One Sporting "
    "Regulations."
)
OVER = (
    "is the fourth of the three new internal combustion engines allowed for the 2021 "
    "Championship season and this is not in conformity with Article 23.3a of the 2021 Formula "
    "One Sporting Regulations."
)
INTRO = "The following drivers will use a new internal combustion engine (ICE) for the Event:"
CE_INTRO = "The following driver will use a new control electronics (CE) for the Event"


def new_document(*rows: list[dict], tail: list[str], start: float = 100.0) -> list[pu.Line]:
    """도입 문장, 머리글, 행, 뒤따르는 글로 이루어진 한 쪽을 만든다."""
    body = [prose(start, INTRO), cells(start + 15, *NEW_HEADER)]
    body += [[{**w, "top": w["top"] + start + 30} for w in row] for row in rows]
    bottom = max(w["top"] for row in body for w in row)
    body += [prose(bottom + 15 * (i + 1), text) for i, text in enumerate(tail)]
    return lines(*body)


# --- 글과 표 파싱 (합성 입력) --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "code"),
    [("ICE", "ICE"), ("MGU-H", "MGU-H"), ("MGU - K", "MGU-K"), ("(EX)", "EX"), ("ERS", None)],
)
def test_element_code(text, code):
    assert pu.element_code(text) == code


def test_visible_words_drop_symbol_font_spaces():
    """2020 벨기에 선언 문서: 빈 단락의 U+F020이 배정 문장 끝에 붙지 않아야 한다."""
    words = [word("Regulations.", MARGIN, 100), word("", MARGIN, 120), word("A", 90, 100)]
    assert [w["text"] for w in pu.visible_words(words)] == ["Regulations.", "A"]


def test_group_lines_keeps_wrapped_cell_lines_apart():
    """줄바꿈된 팀 칸의 두 줄은 행의 기준 줄과 6pt쯤 어긋난다. 서로 다른 줄로 둔다."""
    rows = lines(
        cells(372.7, (89.5, "Alfa Romeo Racing")),
        cells(378.7, (46.0, "99"), (203.2, "Antonio Giovinazzi"), (346.3, "1")),
        cells(385.2, (89.5, "Ferrari")),
    )
    assert [r.text for r in rows] == ["Alfa Romeo Racing", "99 Antonio Giovinazzi 1", "Ferrari"]


@pytest.mark.parametrize("xs", [CENTERED, LEFT])
def test_parse_used_lines(xs):
    elements, rows, problems = pu.parse_used_lines(
        lines(
            prose(80, "The drivers entered in the 2021 Formula One Championship have used"),
            cells(100, *USED_HEADER),
            used_line(112, "44", "Mercedes", "Lewis Hamilton", "3 3 3 3 2 2 4", xs),
            used_line(124, "05", "Aston Martin Mercedes", "Sebastian Vettel", "2 2 2 3 2 2 10", xs),
            prose(150, "Jo Bauer"),
            used_line(170, "99", "Not A Row", "After The Table", "1 1 1 1 1 1 1", xs),
        )
    )
    assert problems == []
    assert elements == ["ICE", "TC", "MGU-H", "MGU-K", "ES", "CE", "EX"]
    assert [(r["car_number"], r["team_text"], r["driver_name"]) for r in rows] == [
        (44, "Mercedes", "Lewis Hamilton"),
        (5, "Aston Martin Mercedes", "Sebastian Vettel"),
    ]
    assert list(rows[0]["used"].values()) == [3, 3, 3, 3, 2, 2, 4]
    assert rows[1]["used"]["EX"] == 10


def test_parse_used_lines_reads_only_the_printed_columns():
    """2020년 문서에는 EX 열이 없다. 머리글에 있는 열만 읽는다."""
    elements, rows, problems = pu.parse_used_lines(
        lines(
            cells(100, *USED_HEADER[:-1]),
            used_line(112, "44", "Mercedes", "Lewis Hamilton", "3 3 3 3 2 2"),
        )
    )
    assert (elements, problems) == (["ICE", "TC", "MGU-H", "MGU-K", "ES", "CE"], [])
    assert rows[0]["used"] == {"ICE": 3, "TC": 3, "MGU-H": 3, "MGU-K": 3, "ES": 2, "CE": 2}


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        (used_line(112, "44", "Mercedes", "Lewis Hamilton", "3 3 3 3 2 2"), "열 수(7)와 다르다"),
        (used_line(112, "44", "Mercedes", "Lewis Hamilton", "3 3 3 - 2 2 4"), "숫자가 아니다"),
        (
            used_line(112, "44", "Mercedes", "Lewis Hamilton", "3 3 3 3 2 2 4", (*LEFT[:6], 500.0)),
            "머리글 아래에 있지 않다",
        ),
        (cells(112, (83.3, "Mercedes"), (225.1, "Lewis Hamilton")), "행이 아닌 줄"),
    ],
)
def test_parse_used_lines_does_not_guess(row, problem):
    """칸이 비었거나 숫자가 아니거나 열에서 벗어나면 그 행을 읽지 않고 문제로 남긴다."""
    _, rows, problems = pu.parse_used_lines(lines(cells(100, *USED_HEADER), row))
    assert rows == []
    assert any(problem in p for p in problems), problems


def test_parse_used_lines_flags_repeated_car_number_and_missing_table():
    _, rows, problems = pu.parse_used_lines(
        lines(
            cells(100, *USED_HEADER),
            used_line(112, "30", "Red Bull Racing Honda RBPT", "Liam Lawson", "1 1 1 1 1 1 1"),
            used_line(124, "30", "Racing Bulls Honda RBPT", "Isack Hadjar", "1 1 1 1 1 1 1"),
        )
    )
    assert len(rows) == 2 and problems == ["차량 번호 30번이 두 번 나온다"]
    assert pu.parse_used_lines(lines(prose(100, "Technical Delegate's Report")))[2] == [
        "누적 표의 머리글(N° Car Driver ...)을 찾지 못했다"
    ]


def test_parse_new_lines_reads_table_and_statement():
    rows, problems = pu.parse_new_lines(
        new_document(
            new_line(0, "44", "Mercedes", "Lewis Hamilton", "2"),
            new_line(12, "04", "McLaren Mercedes", "Lando Norris", "1"),
            tail=[f"The internal combustion engine used by the above drivers {WITHIN}"],
        )
    )
    assert problems == []
    got = [(r["car_number"], r["team_text"], r["driver_name"], r["previously_used"]) for r in rows]
    assert got == [
        (44, "Mercedes", "Lewis Hamilton", 2),
        (4, "McLaren Mercedes", "Lando Norris", 1),
    ]  # fmt: skip
    assert {r["element"] for r in rows} == {"ICE"}
    assert all(r["within_allocation"] is True and r["allowed"] == 3 for r in rows)
    assert rows[0]["allocation_text"].startswith("The internal combustion engine used by the above")
    assert rows[0]["allocation_text"].endswith("Formula One Sporting Regulations.")


def test_statements_follow_the_named_driver():
    """이름을 적은 문장은 그 행에, "the other above drivers"는 나머지 행에 붙는다."""
    rows, problems = pu.parse_new_lines(
        new_document(
            new_line(0, "16", "Ferrari", "Charles Leclerc", "3"),
            new_line(12, "55", "Ferrari", "Carlos Sainz", "2"),
            new_line(24, "24", "Alfa Romeo Racing Ferrari", "Zhou Guanyu", "2"),
            tail=[
                f"The internal combustion engine used by Charles Leclercis {OVER}",
                f"The internal combustion engine used by the other above drivers {WITHIN}",
            ],
        )
    )
    assert problems == []
    assert [(r["car_number"], r["within_allocation"], r["ordinal"]) for r in rows] == [
        (16, False, 4), (55, True, None), (24, True, None),
    ]  # fmt: skip


def test_row_without_statement_stays_empty():
    """문서가 일부 드라이버에 대해서만 말하면 나머지 행의 적합 여부는 비워 둔다."""
    rows, problems = pu.parse_new_lines(
        new_document(
            new_line(0, "16", "Ferrari", "Charles Leclerc", "3"),
            new_line(12, "55", "Ferrari", "Carlos Sainz", "2"),
            tail=[f"The internal combustion engine used by Charles Leclerc {OVER}"],
        )
    )
    assert problems == []
    assert [(r["within_allocation"], r["allocation_text"] != "") for r in rows] == [
        (False, True), (None, False),
    ]  # fmt: skip


def test_statement_about_a_driver_not_in_the_table_is_a_problem():
    """표에 없는 드라이버를 가리키는 문장은 어느 행의 것인지 알 수 없다. 추측하지 않는다."""
    rows, problems = pu.parse_new_lines(
        new_document(
            new_line(0, "22", "AlphaTauri RBPT", "Yuki Tsunoda", "3"),
            tail=[f"The internal combustion engine used by Pierre Gasly {OVER}"],
        )
    )
    assert rows[0]["within_allocation"] is None and rows[0]["allocation_text"] == ""
    assert len(problems) == 1 and "가리키는 행을 표에서 찾지 못했다" in problems[0]


def test_statement_with_a_misspelled_name_follows_the_only_close_row():
    """2022 헝가리: 표는 "George Russell", 문장은 "George Russel".

    철자가 비슷한 행이 하나뿐이면 그 행의 문장으로 본다.
    """
    rows, problems = pu.parse_new_lines(
        new_document(
            new_line(0, "63", "Mercedes", "George Russell", "2"),
            tail=[f"The internal combustion engine used by George Russel {WITHIN}"],
        )
    )
    assert problems == [] and rows[0]["within_allocation"] is True
    assert pu.named_rows("The engine used by Pierre Gasly is the fifth", rows) == []


def test_unread_statement_is_a_problem():
    """배정 문장의 꼴이 달라 읽지 못하면 비워 두지 않고 문제로 남긴다."""
    rows, problems = pu.parse_new_lines(
        new_document(
            new_line(0, "44", "Mercedes", "Lewis Hamilton", "2"),
            tail=["This engine is within the three allowed for the 2021 Championship season."],
        )
    )
    assert rows[0]["within_allocation"] is None
    assert any("다 읽지 못했다" in p for p in problems)


def test_blank_previously_used_cell_keeps_the_row_and_is_a_problem():
    """2024 바레인 CE 표는 개수 칸이 비어 있다. 행은 원문대로 싣고 개수는 비우며 문제로 남긴다."""
    blank = cells(30, (MARGIN, "04"), (110.0, "McLaren Mercedes"), (280.0, "Lando Norris"))
    rows, problems = pu.parse_new_lines(
        new_document(blank, tail=[f"The internal combustion engine used by Lando Norris {WITHIN}"])
    )
    assert [(r["car_number"], r["driver_name"], r["previously_used"]) for r in rows] == [
        (4, "Lando Norris", None)
    ]
    assert len(problems) == 1 and "이전 사용 개수 칸이 비어 있다" in problems[0]


def test_declarations_report_whether_every_table_row_was_read():
    """행을 하나라도 읽지 못하면 그 문서가 다루는 차량을 다 알 수 없다(complete가 거짓)."""
    statement = f"The internal combustion engine used by the above drivers {WITHIN}"
    good = new_document(new_line(0, "44", "Mercedes", "Lewis Hamilton", "2"), tail=[statement])
    bad = new_document(
        new_line(0, "44", "Mercedes", "Lewis Hamilton", "2"),
        new_line(12, "04", "McLaren Mercedes", "Lando Norris", "x"),
        tail=[statement],
    )
    assert pu.read_declarations(good)[2] is True
    rows, problems, complete = pu.read_declarations(bad)
    assert [r["car_number"] for r in rows] == [44] and problems and complete is False


def test_wrapped_team_cell_and_merged_header():
    """한 쪽 양식: "NumberCar"가 붙어 나오고 팀 이름이 행의 위아래 두 줄로 나뉜다."""
    rows, problems = pu.parse_new_lines(
        lines(
            prose(313.7, f"{CE_INTRO}:", 46.0),
            cells(347.7, (46.0, "NumberCar"), (203.2, "Driver"), (268.2, "Previously used CE")),
            cells(372.7, (89.5, "Alfa Romeo Racing")),
            cells(378.7, (46.0, "99"), (203.2, "Antonio Giovinazzi"), (346.3, "1")),
            cells(385.2, (89.5, "Ferrari")),
            prose(431.8, f"The control electronics used by Antonio Giovinazzi {WITHIN}", 46.0),
        )
    )  # fmt: skip
    assert problems == []
    assert [(r["car_number"], r["team_text"], r["driver_name"], r["element"]) for r in rows] == [
        (99, "Alfa Romeo Racing Ferrari", "Antonio Giovinazzi", "CE")
    ]
    assert rows[0]["previously_used"] == 1 and rows[0]["within_allocation"] is True


def test_table_continues_on_the_next_page():
    """머리글이 쪽 끝에 있고 행이 다음 쪽에 있어도 같은 표로 읽는다."""
    first = lines(prose(700, INTRO), cells(715, *NEW_HEADER), page=2)
    second = lines(
        new_line(60, "04", "McLaren Renault", "Lando Norris", "2"),
        prose(80, f"The internal combustion engine used by Lando Norris {WITHIN}"),
        prose(100, "The PU elements have been replaced with the approval of the FIA."),
        page=3,
    )  # fmt: skip
    rows, problems = pu.parse_new_lines(first + second)
    assert problems == []
    assert [(r["car_number"], r["previously_used"]) for r in rows] == [(4, 2)]
    assert "approval" not in rows[0]["allocation_text"]


def test_car_row_after_the_table_ended_is_a_problem():
    """표 중간에 왼쪽 여백에서 시작하는 줄(쪽 바닥글)이 끼어도 그 뒤의 행을 글로 삼키지 않는다.

    그 행은 문제로 남기고, 문서가 다루는 차량을 다 알 수 없으므로 complete를 거짓으로 둔다.
    """
    statement = f"The internal combustion engine used by the above drivers {WITHIN}"
    body = lines(
        prose(100, INTRO),
        cells(115, *NEW_HEADER),
        new_line(130, "44", "Mercedes", "Lewis Hamilton", "2"),
        prose(142, "Page 1 of 2"),
        new_line(154, "04", "McLaren Mercedes", "Lando Norris", "1"),
        prose(170, statement),
    )  # fmt: skip
    rows, problems, complete = pu.read_declarations(body)
    assert [r["car_number"] for r in rows] == [44] and complete is False
    assert any("표가 끝난 뒤에 차량 행이 있다" in p and "Lando Norris" in p for p in problems)
    assert not any("Lando Norris" in r["allocation_text"] for r in rows)  # 글로 삼키지 않는다


def test_blank_count_row_after_the_table_ended_is_a_problem():
    """쪽 바닥글 뒤에 Previously used 칸이 빈 행이 나와도 글로 삼키지 않고 문제로 남긴다."""
    statement = f"The internal combustion engine used by the above drivers {WITHIN}"
    blank = cells(154, (MARGIN, "04"), (110.0, "McLaren Mercedes"), (280.0, "Lando Norris"))
    body = lines(
        prose(100, INTRO),
        cells(115, *NEW_HEADER),
        new_line(130, "44", "Mercedes", "Lewis Hamilton", "2"),
        prose(142, "Page 1 of 2"),
        blank,
        prose(170, statement),
        prose(185, "11 drivers have used a new internal combustion engine at this Event so far."),
    )  # fmt: skip
    rows, problems, complete = pu.read_declarations(body)
    assert [r["car_number"] for r in rows] == [44] and complete is False
    assert sum("표가 끝난 뒤에 차량 행이 있다" in p for p in problems) == 1
    assert any("Lando Norris" in p for p in problems)
    # 숫자로 시작하는 글 줄은 행으로 보지 않는다(글 줄은 오른쪽 개수 열까지 이어진다). 개수 열에
    # 닿지 않는 짧은 글 줄이 Driver 열까지 오면 행으로 보아 검수 대기로 두는 쪽을 택한다.
    columns = pu.new_columns(lines(cells(115, *NEW_HEADER))[0])
    wide = lines(
        prose(185, "11 drivers have used a new internal combustion engine at this Event so far.")
    )
    assert wide[0].words[-1]["x1"] > columns.count_x0
    assert not pu.looks_like_row(wide[0], columns)


def test_all_drivers_block_has_no_car_number():
    """첫 대회 문서는 표 없이 "All drivers"라고만 적는다. 차량 번호 없는 행 하나로 둔다."""
    text = (
        "The energy store used by all drivers is one (1) of the two (2) new energy stores allowed "
        "for the 2025 Championship season and this is in conformity with Article 28.2 of the 2025 "
        "Formula One Sporting Regulations."
    )
    rows, problems = pu.parse_new_lines(
        lines(
            prose(
                100, "All drivers will start the first Competition of the 2025 Formula One World"
            ),
            prose(112, "Championship with a new energy store (ES)."),
            prose(130, text),
            prose(160, "Jo Bauer"),
        )
    )
    assert problems == []
    got = [(r["car_number"], r["driver_name"], r["element"], r["previously_used"]) for r in rows]
    assert got == [
        (None, "All drivers", "ES", None)
    ]  # fmt: skip
    assert rows[0]["within_allocation"] is True and rows[0]["allowed"] == 2
    assert rows[0]["allocation_text"] == text


def test_section_without_element_code_is_not_a_declaration():
    """PU와 무관한 부분("The following parts have been replaced ...")은 선언으로 읽지 않는다."""
    rows, problems = pu.parse_new_lines(
        lines(
            prose(100, "The following parts have been replaced during the Parc Fermé:"),
            prose(115, "Car 77: Rear wing assembly"),
        )
    )
    assert rows == [] and problems == ["새 구성요소 선언(도입 문장이나 표 머리글)을 찾지 못했다"]


@pytest.mark.parametrize(
    ("statement", "facts"),
    [
        (f"The internal combustion engine used by Carlos Sainz {WITHIN}", (True, 3, None)),
        (f"The internal combustion engine used by Carlos Sainz {OVER}", (False, 3, 4)),
        (
            "The energy store used by Kevin Magnussen is the third new energy store for the 2020 "
            "Championship season. As this is in not in compliance with Article 23.3a of the 2020 "
            "Formula One Sporting Regulations, I am referring this matter to the stewards.",
            (False, None, 3),
        ),
        (
            "The energy store used by the above driver is the third of the two new energy stores "
            "allowed for the 2020 Championship season and this is not in conformity with Article "
            "23.3a of the 2020 Formula One Sporting Regulations.",
            (False, 2, 3),
        ),
        (
            "The exhaust system used by Franco Colapinto is one (1) of the eight (8) new exhaust "
            "systems allowed for the 2025 Championship season and this is in conformity with "
            "Article 28.2 of the 2025 Formula One Sporting Regulations.",
            (True, 8, None),
        ),
        (
            "The energy store used by George Russell is the third of the two new energy stores "
            "allowed for the 2022 Championship season and this is in not conformity with Article "
            "28.2 of the 2022 Formula One Sporting Regulations.",
            (False, 2, 3),
        ),
        ("The exhaust system used by Franco Colapinto is new.", (None, None, None)),
        (
            "The internal combustion engine used by Driver 1 is the 4th of the three new internal "
            "combustion engines allowed for the 2021 Championship season and this is not in "
            "conformity with Article 23.3a.",
            (False, 3, 4),
        ),
        (
            "The energy store used by Driver 1 is the 2nd (2nd) new energy store for the 2021 "
            "Championship season.",
            (None, None, 2),
        ),
    ],
)
def test_statement_facts(statement, facts):
    got = pu.statement_facts(statement)
    assert (got["within_allocation"], got["allowed"], got["ordinal"]) == facts


def test_ordinal_written_as_digits_is_read_or_left_unread():
    """숫자로 적은 순서("4th")를 읽는다. 접미사가 수와 맞지 않거나("4st") 접미사 없는 숫자("is the
    4 of the three")는 읽지 않고 statement_unread가 되게 순서를 읽지 못했다고 적는다.
    """
    for ordinal, value in [("1st", 1), ("2nd", 2), ("3rd", 3), ("4th", 4), ("11th", 11)]:
        text = f"The engine used by Driver 1 is the {ordinal} of the three new engines allowed"
        assert pu.statement_facts(text)["ordinal"] == value
    for ordinal in ["4st", "11st", "4"]:
        text = (
            f"The engine used by Driver 1 is the {ordinal} of the three new engines allowed for "
            "the 2021 Championship season and this is not in conformity with Article 23.3a."
        )
        facts = pu.statement_facts(text)
        assert (facts["allowed"], facts["ordinal"]) == (3, None)
        row = {**declared("a", 1, "ICE", 3), **facts, "allocation_text": text}
        assert pu.unread_facts(row) == ["순서"], ordinal


def test_statements_keep_follow_up_sentences_only():
    tail = [
        "The turbocharger used by George Russell is the fourth new turbocharger for the 2020",
        "Championship season. As this is in not in compliance with Article 23.3a of the 2020",
        "Formula One Sporting Regulations, I am referring this matter to the stewards for their",
        "consideration.",
        "All the above listed PU elements have been replaced with the approval of the FIA.",
        "Jo Bauer",
    ]
    found = pu.statements(tail)
    assert len(found) == 1
    assert found[0].startswith("The turbocharger used by George Russell")
    assert found[0].endswith("for their consideration.")


def test_names_driver_tolerates_spacing_typos():
    assert pu.names_driver(
        "The energy store used by Fernando Alonsois the fourth", "Fernando Alonso"
    )
    assert pu.names_driver("used by Guanyu Zhou and Mick Schumacher is", "Zhou Guanyu")
    assert not pu.names_driver("The turbocharger used by Pierre Gasly is", "Yuki Tsunoda")


def test_same_person_accepts_small_typos_only():
    assert pu.same_person("George Russel", "Russell")
    assert pu.same_person("Zhou Guanyu", "Zhou")
    assert pu.same_person("Nyck de Vries", "de Vries")
    assert not pu.same_person("Jack Aitken", "Russell")


# --- 문서 사이의 관계 (합성 입력) ---------------------------------------------------------


def document(
    kind: str, round_no: int, rows: list[dict], *, title: str = "", at: str = ""
) -> pu.Document:
    meta = {
        "doc_type": kind, "event": f"Round {round_no}", "title": title or kind,
        "url": f"https://example.invalid/{kind}-{round_no}-{at or 'a'}.pdf",
        "published_at": at or f"2021-01-{round_no:02d} 10:00", "doc_number": "",
    }  # fmt: skip
    if kind == "pu_used":
        parsed = pu.UsedDocument(None, "", ["ICE", "ES"], rows, "", [])
    else:
        parsed = pu.NewDocument(None, "", rows, "", [])
    return pu.Document(meta, 2021, round_no, parsed)


def seat(team: str, car: int, ice: int, es: int) -> dict:
    return {"constructor_id": team, "driver_id": f"d{car}", "car_number": car, "team_text": team,
            "driver_name": f"Driver {car}", "used": {"ICE": ice, "ES": es}}  # fmt: skip


def declared(team: str, car: int, element: str, previously_used: int) -> dict:
    row = pu.declared_row(car, team, f"Driver {car}", element, previously_used)
    return {**row, "constructor_id": team, "driver_id": f"d{car}"}


def entries(*rounds: dict[int, str]) -> pu.Entries:
    """대회별 {차량 번호: 팀}으로 출전 기록을 만든다. 첫 항목이 1라운드다."""
    starters = {
        (2021, n): {car: (f"d{car}", team) for car, team in cars.items()}
        for n, cars in enumerate(rounds, 1)
    }
    return pu.Entries(starters, {}, {})


def test_team_conflicts_name_the_rows_that_disagree_with_the_results():
    """2025 일본처럼 표가 교체 전 팀 조합을 실으면, 결과와 맞지 않는 행을 문제로 남긴다."""

    def row(car: int, team_text: str, constructor_id: str) -> dict:
        return {**seat(constructor_id, car, 1, 1), "team_text": team_text}

    before = document(
        "pu_used",
        2,
        [
            row(1, "Red Bull", "red_bull"),
            row(30, "Red Bull", "red_bull"),
            row(22, "Racing Bulls", "rb"),
            row(6, "Racing Bulls", "rb"),
        ],
    )
    after = document(
        "pu_used",
        3,
        [
            row(1, "Red Bull", "red_bull"),
            row(30, "Red Bull", "rb"),
            row(22, "Racing Bulls", "red_bull"),
            row(6, "Racing Bulls", "rb"),
        ],
    )
    usual: dict = {}
    for doc in (before, after):
        for r in doc.rows:
            usual.setdefault((2021, pu.plain(r["team_text"])), pu.Counter())[
                r["constructor_id"]
            ] += 1
    assert pu.team_conflicts(before, usual) == []
    problems = pu.team_conflicts(after, usual)
    assert [p.split(":")[0] for p in problems] == ["22번 Driver 22", "30번 Driver 30"]


def test_pair_seats_follows_a_driver_change_within_a_team():
    earlier = {("haas", 8), ("haas", 20), ("williams", 63), ("mercedes", 44)}
    later = {("haas", 51), ("haas", 20), ("williams", 89), ("mercedes", 63)}
    assert pu.pair_seats(earlier, later) == [
        (("haas", 20), ("haas", 20)),
        (("haas", 8), ("haas", 51)),
        (("mercedes", 44), ("mercedes", 63)),
        (("williams", 63), ("williams", 89)),
    ]
    assert pu.pair_seats({("haas", 8), ("haas", 20)}, {("haas", 50), ("haas", 51)}) == []


def test_seat_of_maps_a_substitute_to_the_absent_car():
    seats = {("racing_point", 11), ("racing_point", 18)}
    racing = {11: ("perez", "racing_point"), 27: ("hulkenberg", "racing_point")}
    assert pu.seat_of(declared("racing_point", 27, "ES", 1), seats, racing) == ("racing_point", 18)
    assert pu.seat_of(declared("racing_point", 11, "ES", 1), seats, racing) == ("racing_point", 11)
    assert pu.seat_of(declared("racing_point", 27, "ES", 1), seats, {}) is None


def test_cross_checks_list_what_does_not_add_up():
    """뒤 누적 값 = 앞 누적 값 + 앞 대회 선언 수. 맞지 않는 칸만 목록에 남는다."""
    docs = [
        document("pu_used", 2, [seat("a", 1, 1, 1), seat("a", 2, 1, 1)]),
        document("pu_new", 2, [declared("a", 1, "ICE", 1), declared("a", 2, "ES", 2)]),
        document("pu_used", 3, [seat("a", 1, 2, 1), seat("a", 2, 2, 2)]),
    ]
    found, stats = pu.cross_checks(docs, entries({}, {1: "a", 2: "a"}, {1: "a", 2: "a"}))
    assert stats == {"sequence_pairs": 1, "sequence_cells": 4, "sequence_pairs_skipped": 0,
                     "sequence_seats_skipped": 0, "previously_used_checked": 2}  # fmt: skip
    got = {(r["kind"], r["car_number"], r["element"], r["expected"], r["actual"]) for r in found}
    assert got == {
        ("snapshot_sequence", 2, "ICE", 1, 2),  # 선언 없이 늘었다
        ("previously_used", 2, "ES", 1, 2),  # 선언 문서의 이전 개수가 누적 문서와 다르다
    }
    assert [d.status for d in docs] == ["ok", "ok", "ok"]
    assert all(r["earlier_url"] and r["later_url"] for r in found)


def test_cross_checks_count_a_substitute_towards_the_seat():
    docs = [
        document("pu_used", 1, [seat("a", 11, 1, 1), seat("a", 18, 1, 1)]),
        document("pu_new", 1, [declared("a", 27, "ES", 1)]),
        document("pu_used", 2, [seat("a", 11, 1, 1), seat("a", 18, 1, 2)]),
    ]
    found, _ = pu.cross_checks(docs, entries({11: "a", 27: "a"}, {11: "a", 18: "a"}))
    assert found == []


def test_decrease_sends_both_documents_to_review():
    docs = [
        document("pu_used", 1, [seat("a", 1, 3, 1), seat("a", 2, 1, 1)]),
        document("pu_used", 2, [seat("a", 1, 2, 1), seat("a", 2, 1, 1)]),
    ]
    found, _ = pu.cross_checks(docs, entries({1: "a", 2: "a"}, {1: "a", 2: "a"}))
    assert [d.status for d in docs] == ["needs_review", "needs_review"]
    assert "1번 ICE 3 -> 2" in docs[0].problems[0] and "1번 ICE 3 -> 2" in docs[1].problems[0]
    assert [(r["element"], r["difference"]) for r in found] == [("ICE", -1)]


def test_decrease_marks_only_the_neighbouring_pair_once():
    """2023 Sargeant EX: 5, 5, 4, 4. 줄어든 이웃 쌍만 검수 대기가 되고 끊김은 한 번만 적는다.

    앞뒤 문서를 사슬에서 빼고 다시 이으면 R1 -> R4를 비교해 같은 끊김을 또 적게 된다.
    """
    docs = [document("pu_used", n, [seat("a", 1, 1, ex), seat("a", 2, 1, 1)]) for n, ex in
            [(1, 5), (2, 5), (3, 4), (4, 4)]]  # fmt: skip
    found, stats = pu.cross_checks(docs, entries(*[{1: "a", 2: "a"}] * 4))
    assert [d.status for d in docs] == ["ok", "needs_review", "needs_review", "ok"]
    assert "R3" in docs[1].problems[0] and "R2" in docs[2].problems[0]
    got = [(r["kind"], r["earlier_round"], r["later_round"]) for r in found]
    assert got == [("snapshot_decrease", 2, 3)]
    assert stats["sequence_pairs"] == 3


def test_unreadable_declaration_document_skips_the_whole_pair():
    """받지 못한 선언 문서는 어느 차량을 다루는지 모르므로 그 사이 쌍 전체를 건너뛴다."""
    docs = [
        document("pu_used", 1, [seat("a", 1, 1, 1), seat("a", 2, 1, 1)]),
        document("pu_new", 1, [declared("a", 1, "ICE", 1)]),
        document("pu_used", 2, [seat("a", 1, 3, 1), seat("a", 2, 2, 1)]),
    ]
    docs[1].parsed = None
    found, stats = pu.cross_checks(docs, entries({1: "a", 2: "a"}, {1: "a", 2: "a"}))
    assert found == [] and stats["sequence_pairs_skipped"] == 1


def test_pending_declaration_blocks_only_the_seats_it_lists():
    """2022 벨기에 문서 60은 22번만 다룬다. 검수 대기여도 다른 차량의 끊김은 그대로 적는다."""
    docs = [
        document("pu_used", 1, [seat("a", 1, 1, 1), seat("a", 2, 1, 1)]),
        document("pu_new", 1, [declared("a", 1, "ICE", 1)]),
        document("pu_used", 2, [seat("a", 1, 3, 1), seat("a", 2, 2, 1)]),
    ]
    docs[1].problems.append("배정 문장이 가리키는 행을 표에서 찾지 못했다")
    found, stats = pu.cross_checks(docs, entries({1: "a", 2: "a"}, {1: "a", 2: "a"}))
    assert [(r["car_number"], r["element"], r["expected"], r["actual"]) for r in found] == [
        (2, "ICE", 1, 2)
    ]
    assert stats["sequence_pairs_skipped"] == 0 and stats["sequence_seats_skipped"] == 1
    docs[1].parsed.complete = False  # 행을 빠뜨린 문서는 다루는 차량을 다 알 수 없다
    assert pu.cross_checks(docs, entries({1: "a", 2: "a"}, {1: "a", 2: "a"}))[0] == []


def test_round_without_declaration_document_is_noted():
    """2024 헝가리처럼 선언 문서가 manifest에 없는 대회는 0건으로 계산하되 그 사실을 적는다."""
    docs = [
        document("pu_used", 1, [seat("a", 1, 1, 1)]),
        document("pu_new", 2, [declared("a", 1, "ES", 1)]),
        document("pu_used", 2, [seat("a", 1, 2, 1)]),
        document("pu_used", 3, [seat("a", 1, 2, 2)]),
    ]
    found, _ = pu.cross_checks(docs, entries({1: "a"}, {1: "a"}, {1: "a"}))
    notes = {(r["earlier_round"], r["element"]): r["note"] for r in found}
    assert set(notes) == {(1, "ICE")}
    assert "R1에는 manifest에 pu_new 문서가 없어" in notes[1, "ICE"]


def test_mark_superseded():
    """누적 문서는 나중 문서가 앞 문서를 대체한다. 선언 문서는 정정 문서만 같은 선언을 대체한다."""
    used = [
        document("pu_used", 1, [seat("a", 1, 1, 1)], at="2021-01-01 09:00"),
        document("pu_used", 1, [seat("a", 1, 1, 1)], at="2021-01-01 12:00"),
    ]
    friday = document("pu_new", 1, [declared("a", 1, "ICE", 1)], at="2021-01-01 13:00")
    fixed = document(
        "pu_new", 1, [declared("a", 1, "ICE", 2)], at="2021-01-01 15:00",
        title="Correction of New PU elements for this Event",
    )  # fmt: skip
    saturday = document("pu_new", 1, [declared("a", 2, "ES", 1)], at="2021-01-02 13:00")
    unread = document("pu_used", 1, [], at="2021-01-01 18:00")
    unread.parsed = None  # 캐시에 없는 문서
    pu.mark_superseded([*used, friday, fixed, saturday, unread])
    assert used[0].status == "superseded" and used[0].superseded_by == used[1].url
    assert [d.status for d in (friday, fixed, saturday)] == ["superseded", "ok", "ok"]
    assert unread.status == "not_downloaded"
    # 받지 않은 나중 누적 문서가 앞 문서를 대체했을 수 있다. 앞 문서는 쓰지 않고 보류한다.
    assert used[1].status == "held" and used[1].held_by == unread.url
    assert not used[1].superseded_by


def test_held_snapshot_is_not_used_until_the_later_document_is_read():
    """캐시가 덜 찬 상태: 같은 대회의 나중 누적 문서를 받지 않았으면 앞 문서를 검사와 pu_usage에
    쓰지 않는다. 받지 않은 선언 문서가 있는 대회의 ICE 투입과 허용 개수도 싣지 않는다.
    """
    first = document("pu_used", 1, [seat("a", 1, 1, 1), seat("a", 2, 1, 1)])
    early = document("pu_used", 2, [seat("a", 1, 9, 1), seat("a", 2, 1, 1)], at="2021-01-02 09:00")
    late = document("pu_used", 2, [], at="2021-01-02 12:00")
    late.parsed = None
    statement = f"The internal combustion engine used by Driver 1 {WITHIN}"
    friday = document(
        "pu_new", 2, [{**declared("a", 1, "ICE", 1), **pu.statement_facts(statement),
                       "allocation_text": statement}], at="2021-01-02 13:00",
    )  # fmt: skip
    saturday = document("pu_new", 2, [], at="2021-01-03 13:00")
    saturday.parsed = None
    docs = [first, early, late, friday, saturday]
    pu.mark_superseded(docs)
    assert [d.status for d in docs] == ["ok", "held", "not_downloaded", "held", "not_downloaded"]
    racing = entries({1: "a", 2: "a"}, {1: "a", 2: "a"})
    found, stats = pu.cross_checks(docs, racing)
    assert found == [] and stats["sequence_pairs"] == 0  # 9로 늘어난 값을 비교하지 않는다
    usage = pu.usage_rows(docs, racing)
    assert {r["round"] for r in usage} == {1}
    assert pu.ice_rows(docs, found) == [] and pu.allocation_rows(docs) == []
    # 나중 문서를 받아 읽으면 보류가 풀린다
    late.parsed = pu.UsedDocument(None, "", ["ICE", "ES"], early.rows, "", [])
    saturday.parsed = pu.NewDocument(None, "", [], "", [])
    for doc in docs:
        doc.held_by = ""
    pu.mark_superseded(docs)
    assert [d.status for d in docs] == ["ok", "superseded", "ok", "ok", "ok"]
    assert [r["ice_number"] for r in pu.ice_rows(docs)] == [2]
    assert [r["allowed"] for r in pu.allocation_rows(docs)] == [3]


def test_reissued_declarations_replace_the_earlier_document():
    """2023 마이애미: 나중 문서가 같은 선언을 Previously used까지 똑같이 다시 실으면
    앞 문서를 대체한다.

    같은 구성요소를 한 대회에서 두 번 새로 쓰면 Previously used가 하나 늘므로 대체하지 않는다.
    """
    first = document(
        "pu_new", 5, [declared("a", 4, "ES", 1), declared("a", 18, "ES", 1)], at="2023-05-06 18:46"
    )
    again = document("pu_new", 5, [declared("a", 18, "ES", 1)], at="2023-05-06 20:14")
    second = document("pu_new", 6, [declared("a", 18, "ES", 1)], at="2023-05-07 10:00")
    more = document("pu_new", 6, [declared("a", 18, "ES", 2)], at="2023-05-07 12:00")
    pu.mark_superseded([first, again, second, more])
    assert [d.status for d in (first, again, second, more)] == ["superseded", "ok", "ok", "ok"]
    # 앞 문서에만 있던 4번 선언은 조용히 사라지지 않는다: 불일치 목록과 pu_usage의 basis에 적는다
    assert [(r["car_number"], r["element"]) for r in first.dropped] == [(4, "ES")]
    found = pu.dropped_inconsistencies([first, again, second, more])
    assert [(r["kind"], r["car_number"], r["earlier_url"], r["later_url"]) for r in found] == [
        ("superseded_row_dropped", 4, first.url, again.url)
    ]
    snapshot = document("pu_used", 5, [seat("a", 4, 1, 1), seat("a", 18, 1, 1)])
    usage = pu.usage_rows([snapshot, first, again], entries(*[{4: "a", 18: "a"}] * 5))
    basis = {(r["car_number"], r["element"]): r["basis"] for r in usage}
    assert "dropped=pu_new" in basis[4, "ES"] and first.url in basis[4, "ES"]
    assert "dropped=" not in basis[18, "ES"] and "dropped=" not in basis[4, "ICE"]


def test_declaration_dropped_by_a_chain_of_reissues_is_listed_once():
    """정정 표시 없는 재발행이 A, B, C로 이어지고 C에서 한 선언이 빠지면 그 선언을 한 번만
    적는다.
    """
    rows = [declared("a", 4, "ES", 1), declared("a", 18, "ES", 1)]
    a = document("pu_new", 5, rows, at="2021-01-05 10:00")
    b = document("pu_new", 5, list(rows), at="2021-01-05 11:00")
    c = document("pu_new", 5, [declared("a", 18, "ES", 1)], at="2021-01-05 12:00")
    docs = [a, b, c]
    pu.mark_superseded(docs)
    assert [d.status for d in docs] == ["superseded", "superseded", "ok"]
    found = pu.dropped_inconsistencies(docs)
    assert [(r["car_number"], r["earlier_url"], r["later_url"]) for r in found] == [
        (4, a.url, c.url)
    ]
    snapshot = document("pu_used", 5, [seat("a", 4, 1, 1), seat("a", 18, 1, 1)])
    usage = pu.usage_rows([snapshot, *docs], entries(*[{4: "a", 18: "a"}] * 5))
    basis = {(r["car_number"], r["element"]): r["basis"] for r in usage}
    assert basis[4, "ES"].count("dropped=") == 1


def test_ice_number_is_empty_when_documents_disagree():
    """2022 싱가포르 Russell: 표는 Previously used 3, 문장은 "the fifth".

    어느 쪽도 고르지 않고 순번을 비운다.
    """
    statement = (
        "The internal combustion engine used by Driver 63 is the fifth of the three new internal "
        "combustion engines allowed for the 2021 Championship season and this is not in "
        "conformity with Article 23.3a of the 2021 Formula One Sporting Regulations."
    )
    rows = [
        {**declared("a", 63, "ICE", 3), **pu.statement_facts(statement),
         "allocation_text": statement},
        declared("a", 1, "ICE", 1),
    ]  # fmt: skip
    doc = document("pu_new", 1, rows)
    found = pu.check_statements(doc)
    assert [(r["kind"], r["expected"], r["actual"]) for r in found] == [("statement_ordinal", 4, 5)]
    got = {r["car_number"]: r for r in pu.ice_rows([doc], found)}
    assert got[63]["ice_number"] is None and got[63]["printed_previously_used"] == 3
    assert got[63]["stated_ordinal"] == 5 and "statement_ordinal" in got[63]["conflict"]
    assert got[1]["ice_number"] == 2 and got[1]["conflict"] == ""


def test_unread_allowance_or_ordinal_is_listed():
    """2022 싱가포르 Russell CE: "is the third two new ..."(of the 빠짐).

    허용 개수와 순서를 읽지 못해 검사를 건너뛴 사실을 적는다.
    """
    statement = (
        "The control electronics used by Driver 63 is the third two new control electronics "
        "allowed for the 2022 Championship season and this is not in conformity with Article 28.2 "
        "of the 2022 Formula One Sporting Regulations."
    )
    facts = pu.statement_facts(statement)
    assert (facts["within_allocation"], facts["allowed"], facts["ordinal"]) == (False, None, None)
    row = {**declared("a", 63, "CE", 2), **facts, "allocation_text": statement}
    found = pu.check_statements(document("pu_new", 17, [row, declared("a", 1, "CE", 1)]))
    assert [(r["kind"], r["car_number"], r["difference"]) for r in found] == [
        ("statement_unread", 63, None)
    ]
    assert "허용 개수, 순서" in found[0]["note"]
    within = {**declared("a", 1, "ICE", 1), "allocation_text": f"The engine used by X {WITHIN}"}
    assert pu.unread_facts({**within, **pu.statement_facts(within["allocation_text"])}) == []


def test_allocation_stated_by_one_document_is_listed():
    def doc(round_no: int, allowed: str) -> pu.Document:
        text = f"The engine used by Driver 1 is one of the {allowed} new engines allowed for the "
        text += "2021 Championship season and this is in conformity with Article 23.3a."
        row = {**declared("a", 1, "ICE", 1), **pu.statement_facts(text), "allocation_text": text}
        return document("pu_new", round_no, [row])

    docs = [doc(1, "three"), doc(2, "three"), doc(3, "two")]
    rows = pu.allocation_rows(docs)
    assert [(r["allowed"], r["first_round"], r["documents"]) for r in rows] == [
        (3, 1, 2),
        (2, 3, 1),
    ]
    found = pu.check_allocations(docs)
    assert [
        (r["kind"], r["element"], r["expected"], r["actual"], r["later_url"]) for r in found
    ] == [("allocation_single_document", "ICE", 3, 2, docs[2].url)]
    assert pu.check_allocations(docs[:2]) == []
    # 한 건뿐인 값이 먼저 나와도 earlier와 later는 게시 순서다(2020 70주년 R5와 스페인 R6)
    early = [doc(1, "two"), doc(2, "three"), doc(3, "three")]
    found = pu.check_allocations(early)
    assert [
        (r["earlier_round"], r["later_round"], r["earlier_value"], r["expected"], r["actual"])
        for r in found
    ] == [(1, 2, 2, 3, 2)]
    assert found[0]["earlier_url"] == early[0].url and found[0]["later_url"] == early[1].url
    assert "문서 한 건(R1)" in found[0]["note"] and "처음 나온 문서는 R2" in found[0]["note"]


def test_load_documents_flags_changed_or_broken_files(tmp_path):
    """sha256이 manifest와 다른 캐시 파일, 읽다가 오류가 나는 파일은 검수 대기가 된다.

    오류가 나도 빌드는 멈추지 않는다.
    """
    meta = {
        "season": "2021", "event": "Bahrain Grand Prix", "doc_type": "pu_used", "doc_number": "",
        "title": "PU elements used per driver up to now", "published_at": "2021-03-26 10:00",
        "url": "https://example.invalid/broken.pdf", "sha256": "0" * 64,
    }  # fmt: skip
    path = tmp_path / "fia" / fia_docs.pdf_cache_path(meta)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a pdf")
    other = {**meta, "url": "https://example.invalid/other.pdf", "sha256": ""}
    (path.parent / "other.pdf").write_bytes(b"not a pdf either")
    docs = pu.load_documents([meta, other], tmp_path)
    assert [d.status for d in docs] == ["needs_review", "needs_review"]
    assert "sha256이 manifest와 다르다" in docs[0].problems[0]
    assert all(any("파싱 중 오류가 났다" in p for p in d.problems) for d in docs)
    assert not any("sha256" in p for p in docs[1].problems)


def usage_cells(rows: list[dict]) -> dict:
    return {
        (r["car_number"], r["element"]): (
            r["used_before_event"], r["new_at_event"], r["used_after_event"]
        )
        for r in rows
    }  # fmt: skip


def test_event_usage():
    snapshot = document("pu_used", 3, [seat("a", 1, 2, 1), seat("a", 18, 3, 1)])
    rows = [
        {**declared("a", 1, "ICE", 2), "url": "u1"},
        {**declared("a", 1, "ICE", 3), "url": "u2"},
        {**declared("a", 27, "ES", 1), "url": "u2"},
    ]
    assert usage_cells(pu.event_usage((2021, 3), snapshot, rows, None, 2)) == {
        (1, "ICE"): (2, 2, 4), (1, "ES"): (1, 0, 1), (18, "ICE"): (3, 0, 3), (18, "ES"): (1, 0, 1),
        # 좌석을 정할 수 없는 대체 차량: 선언된 구성요소만 싣고, 이전 개수는 선언 문서 값이다
        (27, "ES"): (1, 1, 2),
    }  # fmt: skip
    waiting = pu.event_usage(
        (2021, 3), snapshot, rows, pu.Pending({"not_downloaded": 1}, [], True), 2
    )
    assert {(r["new_at_event"], r["used_after_event"]) for r in waiting} == {(None, None)}
    assert all("pending" in r["basis"] for r in waiting)
    # 그 대회의 선언 문서가 하나도 없으면 새 구성요소가 없었다고 단정하지 않는다
    silent = pu.event_usage((2021, 3), snapshot, [], None, 0)
    assert {(r["new_at_event"], r["used_after_event"]) for r in silent} == {(None, None)}
    assert all("no pu_new document" in r["basis"] for r in silent)


def test_event_usage_counts_a_substitute_in_the_seat():
    """2020 Eifel: 18번 Stroll 대신 나온 27번 Hülkenberg의 새 ES는 18번 좌석의 개수에 더한다."""
    snapshot = document("pu_used", 3, [seat("a", 11, 2, 2), seat("a", 18, 3, 1)])
    rows = [{**declared("a", 27, "ES", 1), "url": "u1"}]
    racing = {11: ("d11", "a"), 27: ("d27", "a")}
    got = pu.event_usage((2021, 3), snapshot, rows, None, 1, racing)
    assert usage_cells(got) == {
        (11, "ICE"): (2, 0, 2), (11, "ES"): (2, 0, 2),
        (18, "ICE"): (3, 0, 3), (18, "ES"): (1, 1, 2),
    }  # fmt: skip
    seat_row = next(r for r in got if (r["car_number"], r["element"]) == (18, "ES"))
    assert (
        seat_row["driver_id"] == "d18" and "declared for car 27 in this seat" in seat_row["basis"]
    )


def test_event_usage_leaves_after_empty_when_documents_disagree():
    """2022 마이애미: 누적 문서는 Bottas TC 1, 선언 문서는 Previously used 2.

    두 문서가 이 대회 이전 개수를 달리 적으므로 after를 정하지 않는다.
    """
    snapshot = document("pu_used", 5, [seat("a", 77, 1, 1)])
    rows = [{**declared("a", 77, "ICE", 2), "url": "u1"}]
    cells = usage_cells(pu.event_usage((2021, 5), snapshot, rows, None, 1))
    assert cells[77, "ICE"] == (1, 1, None) and cells[77, "ES"] == (1, 0, 1)


def test_event_usage_waits_only_for_the_seats_of_a_pending_document():
    """검수 대기 선언 문서가 22번만 다루면 22번만 비우고 나머지 차량은 정상 선언으로 계산한다."""
    snapshot = document("pu_used", 14, [seat("a", 1, 3, 1), seat("a", 22, 4, 3)])
    rows = [{**declared("a", 1, "ES", 1), "url": "u1"}]
    pending = pu.Pending({"needs_review": 1}, [declared("a", 22, "ICE", 4)])
    got = pu.event_usage((2021, 14), snapshot, rows, pending, 2)
    assert usage_cells(got) == {
        (1, "ICE"): (3, 0, 3), (1, "ES"): (1, 1, 2), (22, "ICE"): (4, None, None),
        (22, "ES"): (3, None, None),
    }  # fmt: skip
    assert all("pending" in r["basis"] for r in got)


# --- 정제 테이블 -------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def documents():
    return pd.read_csv(FIA / "pu_documents.csv", keep_default_na=False, na_values=[""])


@pytest.fixture(scope="module")
def used():
    return pd.read_parquet(FIA / "pu_used.parquet")


@pytest.fixture(scope="module")
def new():
    return pd.read_parquet(FIA / "pu_new.parquet")


@pytest.fixture(scope="module")
def usage():
    return pd.read_parquet(FIA / "pu_usage.parquet")


@pytest.fixture(scope="module")
def inconsistencies():
    return pd.read_csv(FIA / "pu_inconsistencies.csv")


@pytest.fixture(scope="module")
def grid():
    """대회별 결승 출전 팀."""
    results = pd.read_parquet(CURATED_DIR / "jolpica" / "results.parquet")
    race = results[results["session_type"] == "R"]
    return race.groupby(["season", "round"]).constructor_id.agg(lambda s: frozenset(s))


def test_documents_file_is_consistent_with_manifest(documents):
    rows = [r for r in manifest.read_rows(fia_docs.INDEX_MANIFEST) if r["doc_type"] in pu.DOC_TYPES]
    assert sorted(documents["url"]) == sorted(r["url"] for r in rows)
    assert list(documents.columns) == pu.DOCUMENT_FIELDS
    assert set(documents["status"]) <= STATUSES
    assert set(documents["doc_type"]) == set(pu.DOC_TYPES)
    assert len(documents) >= 297 and (documents["status"] == "ok").sum() >= 100


def test_documents_record_rows_and_drivers(documents, used, new):
    """문서마다 추출 행 수와 드라이버 수를 적는다. 읽지 않은 문서는 비워 둔다."""
    parsed = documents[documents["rows"].notna()].set_index("url")
    assert documents.loc[documents["status"] == "not_downloaded", "rows"].isna().all()
    assert documents.loc[documents["status"].isin(["ok", "needs_review"]), "rows"].notna().all()
    assert (parsed["rows"].isna() == parsed["drivers"].isna()).all()
    assert (parsed["rows"].isna() == parsed["teams"].isna()).all()
    # 정상 누적 문서의 팀 수는 그 시즌 그리드의 팀 수(2020-2025년 10팀)다
    ok_used = parsed[(parsed["doc_type"] == "pu_used") & (parsed["status"] == "ok")]
    assert set(ok_used["teams"]) == {10}
    assert (parsed["teams"] <= parsed["drivers"]).all()
    for table, name in ((used, "pu_used"), (new, "pu_new")):
        listed = parsed[parsed["doc_type"] == name]
        cars = table[table["car_number"].notna()]
        drivers = cars.groupby("source_url").driver_name.nunique()
        if name == "pu_used":  # 누적 문서의 행은 차량 한 대(구성요소 열은 펼친 것)
            rows = table.drop_duplicates(["source_url", "car_number", "driver_name"])
            rows = rows.groupby("source_url").size()
        else:
            rows = table.groupby("source_url").size()
        assert drivers.reindex(listed.index, fill_value=0).to_dict() == listed["drivers"].to_dict()
        assert rows.reindex(listed.index, fill_value=0).to_dict() == listed["rows"].to_dict()


def test_only_known_documents_need_review(documents):
    """새로 실패한 문서가 생기면 원문을 확인하고 KNOWN_FAILURES에 까닭을 적은 뒤 통과시킨다."""
    review = {file_name(url) for url in documents.loc[documents["status"] == "needs_review", "url"]}
    downloaded = {
        file_name(url) for url in documents.loc[documents["status"] != "not_downloaded", "url"]
    }
    assert review == set(KNOWN_FAILURES) & downloaded
    failures = [
        r for r in manifest.read_rows("parse_failures.csv") if r["doc_type"] in pu.DOC_TYPES
    ]
    assert {file_name(r["url"]) for r in failures} == review
    assert all(r["problems"] and r["recorded_at"] for r in failures)
    assert documents.loc[documents["status"] == "ok", "problems"].isna().all()
    # 보류(held) 문서는 파싱 실패가 아니다. 같은 대회의 받지 않은 나중 문서를 가리킨다
    held = documents[documents["status"] == "held"]
    by_url = documents.set_index("url")
    for row in held.itertuples():
        later = by_url.loc[row.held_by]
        assert later["status"] == "not_downloaded" and later["event"] == row.event
    assert documents.loc[documents["status"] != "held", "held_by"].isna().all()


def test_failure_rows_are_sorted_the_same_whichever_parser_ran_last():
    """parse_failures.csv는 (doc_type, season, round, url) 순이다. 어느 파서가 마지막에 돌았든 같다.

    규정 문서 행은 다른 파서가 쓰므로 PU와 Car Presentation 행만 순서를 본다.
    """
    rows = [
        r for r in manifest.read_rows("parse_failures.csv")
        if r["doc_type"] in {*pu.DOC_TYPES, "car_presentation"}
    ]  # fmt: skip
    assert rows == sorted(rows, key=manifest._failure_order)


def test_replace_failures_keeps_other_parsers_and_first_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "MANIFEST_DIR", tmp_path)
    fields = manifest.FAILURE_FIELDS

    def failure(doc_type, season, round_no, url, day):
        return dict(zip(fields, [season, round_no, "E", doc_type, url, "p", day], strict=True))

    manifest.write_rows(manifest.FAILURES, [
        failure("pu_used", 2025, 3, "u3", "2026-01-01"),
        failure("car_presentation", 2024, 22, "c", "2026-01-02"),
    ], fields)  # fmt: skip
    manifest.replace_failures(["pu_new", "pu_used"], [
        failure("pu_used", 2025, 3, "u3", "2026-02-02"),
        failure("pu_new", 2022, 14, "n", "2026-02-02"),
        failure("pu_used", 2023, 14, "u1", "2026-02-02"),
    ])  # fmt: skip
    got = [
        (r["doc_type"], r["url"], r["recorded_at"]) for r in manifest.read_rows(manifest.FAILURES)
    ]
    assert got == [
        ("car_presentation", "c", "2026-01-02"),
        ("pu_new", "n", "2026-02-02"),
        ("pu_used", "u1", "2026-02-02"),
        ("pu_used", "u3", "2026-01-01"),  # 처음 기록한 날짜를 유지한다
    ]


def test_superseded_documents_point_to_a_later_document_of_the_same_event(documents):
    by_url = documents.set_index("url")
    old = documents[documents["status"] == "superseded"]
    assert len(old) >= 1 and old["superseded_by"].notna().all()
    assert documents.loc[documents["status"] != "superseded", "superseded_by"].isna().all()
    for row in old.itertuples():
        newer = by_url.loc[row.superseded_by]
        assert newer["status"] != "not_downloaded"  # 읽지 않은 문서는 아무것도 대체하지 않는다
        assert (newer["season"], newer["event"], newer["doc_type"]) == (
            row.season, row.event, row.doc_type,
        )  # fmt: skip
        assert newer["published_at"] > row.published_at


def test_used_table_values(used):
    assert list(used.columns) == pu.USED_FIELDS
    assert set(used["element"]) <= set(pu.ELEMENTS)
    assert set(used["document_status"]) <= STATUSES - {"not_downloaded"}
    assert (used["used"] >= 0).all() and (used["car_number"] > 0).all()
    assert (used["team_text"].str.len() > 0).all() and (used["driver_name"].str.len() > 0).all()
    # 같은 차량 번호가 두 번 적힌 문서는 원문 그대로 싣고 검수 대기로 둔다
    repeated = used[used.duplicated(["source_url", "car_number", "element"], keep=False)]
    assert (repeated["document_status"] == "needs_review").all()
    per_season = used[used["document_status"] == "ok"].groupby("season").element.agg(set)
    for season, elements in per_season.items():
        expected = set(pu.ELEMENTS) - ({"EX"} if season == 2020 else set())
        assert elements == expected, season


def test_every_ok_used_document_lists_the_grid(used, grid):
    """정상 누적 문서는 그 대회에 나온 팀마다 두 대씩, 참가 차량 전부를 싣는다."""
    ok = used[used["document_status"] == "ok"]
    assert (ok["driver_id"].str.len() > 0).all() and (ok["constructor_id"].str.len() > 0).all()
    cars = ok.drop_duplicates(["source_url", "car_number"])
    for (season, round_no, _), rows in cars.groupby(["season", "round", "source_url"]):
        teams = grid[(season, round_no)]
        assert len(rows) == pu.CARS_PER_TEAM * len(teams), (season, round_no)
        assert rows["constructor_id"].value_counts().to_dict() == dict.fromkeys(teams, 2)
    assert ok.groupby(["season", "round"]).source_url.nunique().max() == 1


def test_counts_never_decrease_within_a_season(used, documents, inconsistencies):
    """정상 누적 문서 사이에서 값이 줄면, 그 사이의 이웃한 두 문서가 검수 대기이고 끊김이 한 번만
    적혀 있어야 한다(2023 Sargeant EX: R14 5, R15 4).
    """
    keys = ["season", "constructor_id", "car_number", "element"]
    ok = used[used["document_status"] == "ok"].sort_values("round")
    ok = ok.assign(previous=ok.groupby(keys).used.shift(), since=ok.groupby(keys)["round"].shift())
    drops = ok[ok["used"] < ok["previous"]]
    listed = inconsistencies[inconsistencies["kind"] == "snapshot_decrease"]
    for r in drops.itertuples():
        hit = listed[
            (listed["season"] == r.season) & (listed["constructor_id"] == r.constructor_id)
            & (listed["car_number"] == r.car_number) & (listed["element"] == r.element)
            & (listed["earlier_round"] >= r.since) & (listed["later_round"] <= r.round)
        ]  # fmt: skip
        assert len(hit) == 1, (r.season, r.constructor_id, r.car_number, r.element, r.round)
    # 끊김은 이웃한 두 누적 문서(사이에 읽은 누적 문서가 없다)에 적고, 두 문서 모두 검수 대기다
    status = documents.set_index("url")["status"]
    read = documents[
        (documents["doc_type"] == "pu_used") & documents["status"].isin(["ok", "needs_review"])
    ]
    for r in listed.itertuples():
        assert status[r.earlier_url] == status[r.later_url] == "needs_review"
        between = read[(read["season"] == r.season) & (read["round"] > r.earlier_round)
                       & (read["round"] < r.later_round)]  # fmt: skip
        assert between.empty, (r.season, r.earlier_round, r.later_round)
    sargeant = listed[(listed["season"] == 2023) & (listed["car_number"] == 2)]
    assert list(zip(sargeant["earlier_round"], sargeant["later_round"], strict=True)) == [(14, 15)]


def test_new_table_values(new):
    assert list(new.columns) == pu.NEW_FIELDS
    assert set(new["element"]) <= set(pu.ELEMENTS)
    assert set(new["document_status"]) <= STATUSES - {"not_downloaded"}
    assert set(new["within_allocation"].dropna().unique()) <= {True, False}
    listed = new[new["car_number"].notna()]
    assert (listed["previously_used"] >= 0).all()
    assert (listed["team_text"].str.len() > 0).all() and (listed["driver_name"].str.len() > 0).all()
    everyone = new[new["car_number"].isna()]
    assert set(everyone["driver_name"]) <= {"All drivers"}
    assert everyone["previously_used"].isna().all()
    said = new[new["within_allocation"].notna()]
    assert said["allocation_text"].str.contains("conformity|compliance").all()
    assert (new.loc[new["within_allocation"].isna(), "allocation_text"] == "").all()
    ok = listed[listed["document_status"] == "ok"]
    assert (ok["driver_id"].str.len() > 0).all() and (ok["constructor_id"].str.len() > 0).all()


def test_up_to_now_excludes_new_elements_of_the_same_event(used, new, inconsistencies):
    """선언 문서의 Previously used 값은 같은 대회 누적 문서의 값과 같다(모듈 설명의 규칙).

    같은 대회의 첫 선언만 본다. 다른 경우는 불일치 목록에 있어야 한다.
    """
    keys = ["season", "round", "constructor_id", "car_number", "element"]
    snapshot = used[used["document_status"] == "ok"].set_index(keys)["used"]
    first = (
        new[(new["document_status"] == "ok") & new["car_number"].notna()]
        .sort_values(["published_at", "source_url"], kind="stable")
        .drop_duplicates(keys)
        .join(snapshot, on=keys, how="inner")
    )
    listed = inconsistencies[inconsistencies["kind"] == "previously_used"]
    listed = set(zip(listed["later_url"], listed["car_number"], listed["element"], strict=True))
    differs = first[first["previously_used"] != first["used"]]
    got = set(zip(differs["source_url"], differs["car_number"], differs["element"], strict=True))
    assert len(first) >= 400
    assert got <= listed
    assert len(differs) / len(first) < 0.05


def test_next_snapshot_is_previous_plus_new_or_listed(used, new, documents, inconsistencies):
    """연속한 두 대회의 누적 값은 앞 값 + 앞 대회 선언 수와 같다. 다르면 불일치 목록에 있어야 한다.

    모듈과 따로 계산한다. 대체 드라이버가 낀 팀은 좌석을 이어 붙이는 규칙이 필요하므로 여기서는
    뺀다.
    """
    keys = ["season", "constructor_id", "car_number", "element"]
    ok = used[used["document_status"] == "ok"]
    declared = new[(new["document_status"] == "ok") & new["car_number"].notna()]
    added = declared.groupby(["round", *keys]).size().rename("new").reset_index()
    waiting = documents[
        (documents["doc_type"] == "pu_new")
        & documents["status"].isin(["needs_review", "not_downloaded"])
    ]
    waiting = set(zip(waiting["season"], waiting["round"], strict=True))
    listed_cars = set(
        zip(ok["season"], ok["round"], ok["constructor_id"], ok["car_number"], strict=True)
    )
    substitutes = {
        (r.season, r.round, r.constructor_id)
        for r in declared.itertuples()
        if (r.season, r.round, r.constructor_id, r.car_number) not in listed_cars
    }
    earlier = ok.merge(added, on=["round", *keys], how="left").fillna({"new": 0})
    earlier["round"] += 1
    pairs = earlier.merge(ok, on=["round", *keys], suffixes=("_before", "_after"))
    listed = inconsistencies[inconsistencies["kind"] == "snapshot_sequence"]
    listed = set(zip(listed["season"], listed["later_round"], listed["constructor_id"],
                     listed["car_number"], listed["element"], strict=True))  # fmt: skip
    compared = 0
    for r in pairs.itertuples():
        if (r.season, r.round - 1) in waiting or (
            r.season,
            r.round - 1,
            r.constructor_id,
        ) in substitutes:
            continue
        compared += 1
        differs = r.used_after != r.used_before + r.new
        key = (r.season, r.round, r.constructor_id, r.car_number, r.element)
        assert differs == (key in listed), key
    assert compared >= 5000


def test_inconsistencies_carry_both_documents(inconsistencies, documents):
    assert list(inconsistencies.columns) == pu.INCONSISTENCY_FIELDS
    kinds = {"snapshot_sequence", "snapshot_decrease", "previously_used", "statement_ordinal",
             "statement_season", "statement_verdict", "statement_unread",
             "superseded_row_dropped", "allocation_single_document"}  # fmt: skip
    assert set(inconsistencies["kind"]) <= kinds
    urls = set(documents["url"])
    assert set(inconsistencies["earlier_url"]) <= urls and set(inconsistencies["later_url"]) <= urls
    # 읽지 못한 배정 문장은 견줄 값이 없다. 나머지는 두 값과 그 차이를 적는다
    unread = inconsistencies["kind"] == "statement_unread"
    assert inconsistencies.loc[unread, ["expected", "actual", "difference"]].isna().all().all()
    numbered = inconsistencies[~unread]
    assert (numbered["difference"] != 0).all()
    assert (numbered["actual"] - numbered["expected"] == numbered["difference"]).all()
    # 2022 싱가포르 Russell CE: "is the third two new ..."(of the 빠짐)라서
    # 허용 개수와 순서를 읽지 못한다
    singapore = inconsistencies[unread & (inconsistencies["season"] == 2022)]
    assert set(zip(singapore["car_number"], singapore["element"], strict=True)) == {(63, "CE")}
    # 정정 표시 없이 다시 낸 문서에서 빠진 선언(2023 마이애미 4번 ES, CE, 2023 멕시코 4번 EX)
    dropped = inconsistencies[inconsistencies["kind"] == "superseded_row_dropped"]
    assert set(zip(dropped["season"], dropped["later_round"], dropped["car_number"],
                   dropped["element"], strict=True)) == {
        (2023, 5, 4, "ES"), (2023, 5, 4, "CE"), (2023, 19, 4, "EX"),
    }  # fmt: skip
    status = documents.set_index("url")["status"]
    assert (dropped["earlier_url"].map(status) == "superseded").all()
    sequence = inconsistencies[inconsistencies["kind"] == "snapshot_sequence"]
    assert (sequence["earlier_url"] != sequence["later_url"]).all()
    assert (sequence["earlier_round"] < sequence["later_round"]).all()
    # 모든 kind에서 earlier와 later는 게시 순서다
    both = inconsistencies.dropna(subset=["earlier_round", "later_round"])
    assert (both["earlier_round"] <= both["later_round"]).all()
    # 함께 적은 처분 문서는 manifest에 있는, 같은 차량 번호의 PU 처분 문서이고 두 대회 사이에 있다
    titles = {r["url"]: r["title"] for r in manifest.read_rows(fia_docs.INDEX_MANIFEST)}
    for row in inconsistencies.dropna(subset=["related_documents"]).itertuples():
        parts = row.related_documents.split()
        for round_tag, url in zip(parts[::2], parts[1::2], strict=True):
            match = pu.DECISION_TITLE.match(titles[url])
            assert match and int(match["car"]) == row.car_number, url
            assert row.earlier_round <= int(round_tag[1:]) <= row.later_round
    assert inconsistencies["related_documents"].notna().sum() >= 50


def test_decision_titles():
    assert pu.DECISION_TITLE.match("Offence - Car 33 - PU elements")["car"] == "33"
    assert pu.DECISION_TITLE.match("Infringement - Car 4 - Changes made during Parc Ferme (PU)")
    assert pu.DECISION_TITLE.match("Decision - Car 16 - Power Unit Elements")
    assert pu.DECISION_TITLE.match("Infringement - Car 10 - Changes made during Parc Ferme")
    assert pu.DECISION_TITLE.match("Offence - Car 3 Parc Ferme")["car"] == "3"
    assert not pu.DECISION_TITLE.match("Offence - Car 11 - impeding car 8 in P3")
    assert not pu.DECISION_TITLE.match("New PU elements for this Event")


def test_usage_table(usage, used, new):
    assert list(usage.columns) == pu.USAGE_FIELDS
    assert not usage.duplicated(["season", "round", "car_number", "element"]).any()
    assert (usage["used_before_event"] >= 0).all()
    # 대체 드라이버의 선언은 원래 좌석에 붙으므로 한 팀이 한 대회에 세 대가 되지 않는다
    seats = usage.groupby(["season", "round", "constructor_id", "element"]).size()
    assert seats.max() <= pu.CARS_PER_TEAM
    known = usage[usage["used_after_event"].notna()]
    assert (known["used_after_event"] == known["used_before_event"] + known["new_at_event"]).all()
    assert usage.loc[usage["new_at_event"].isna(), "used_after_event"].isna().all()
    # new가 있는데 after가 빈 칸은 선언 문서의 Previously used가 누적 문서와 다른 경우뿐이다
    disagree = usage[usage["new_at_event"].notna() & usage["used_after_event"].isna()]
    assert disagree["basis"].str.contains("after=unknown \\(pu_new Previously used").all()
    assert (
        usage["basis"].str.startswith("before=").all()
        and usage["basis"].str.contains("; new=").all()
    )
    # 누적 문서에서 온 행은 그 문서의 값 그대로다
    keys = ["season", "round", "car_number", "element"]
    printed = used[used["document_status"] == "ok"].set_index(keys)["used"]
    from_snapshot = usage[usage["basis"].str.startswith("before=pu_used ")].set_index(keys)
    assert from_snapshot["used_before_event"].to_dict() == printed.to_dict()
    # 선언 수는 팀과 구성요소마다 정상 선언 문서의 행 수와 같다(대체 드라이버 선언은 좌석에 붙는다)
    team = ["season", "round", "constructor_id", "element"]
    declared = new[(new["document_status"] == "ok") & new["car_number"].notna()]
    counted = declared.groupby(team).size()
    groups = usage.groupby(team).new_at_event
    complete = groups.count() == groups.size()
    summed = groups.sum()[complete]
    assert summed.to_dict() == counted.reindex(summed.index, fill_value=0).to_dict()
    assert counted.index.isin(usage.set_index(team).index).all()


def test_usage_regressions(usage):
    """검증에서 찾은 경우가 다시 생기지 않는지 본다."""
    cell = usage.set_index(["season", "round", "car_number", "element"])
    # 2020 Eifel: 27번 Hülkenberg의 새 ES, CE는 18번 좌석의 값이다(다음 누적 문서 R12의 18번은 2)
    assert cell.loc[(2020, 11, 18, "ES"), "used_after_event"] == 2
    assert (2020, 11, 27, "ES") not in cell.index
    # 2023 미국: 3번 Ricciardo의 새 EX는 40번 좌석의 값이다
    assert cell.loc[(2023, 18, 40, "EX"), "used_after_event"] == 6
    # 2022 마이애미, 캐나다: 선언의 Previously used가 누적 값보다 크다. after를 정하지 않는다
    for key in [(2022, 5, 77, "TC"), (2022, 9, 16, "ICE"), (2022, 9, 22, "CE")]:
        assert pd.isna(cell.loc[key, "used_after_event"]) and cell.loc[key, "new_at_event"] == 1
    # 2022 벨기에: 검수 대기 문서 60은 22번만 다룬다. 다른 차량의 개수는 정해진다
    belgium = usage[(usage["season"] == 2022) & (usage["round"] == 14)]
    assert set(belgium.loc[belgium["new_at_event"].isna(), "car_number"]) == {22}


def test_inconsistency_regressions(inconsistencies, new):
    # 2022 벨기에 -> 네덜란드 쌍은 22번(검수 대기 문서 60)을 빼고 비교한다
    found = inconsistencies
    pair = found[(found["season"] == 2022) & (found["earlier_round"] == 14)
                 & (found["later_round"] == 15)]  # fmt: skip
    assert len(pair) >= 50 and 22 not in set(pair["car_number"])
    # 2023 Hülkenberg, Magnussen, Zhou의 끊김은 값이 실제로 바뀐 이웃 쌍에 적는다
    haas = inconsistencies[(inconsistencies["season"] == 2023)
                           & inconsistencies["car_number"].isin([27, 20, 24])]  # fmt: skip
    got = set(zip(haas["car_number"], haas["earlier_round"], haas["later_round"], strict=True))
    assert got == {(27, 12, 13), (20, 13, 14), (24, 15, 16)}
    # 2024 헝가리에는 선언 문서가 없다. 0건으로 계산한 행에는 그 사실을 적는다
    hungary = inconsistencies[(inconsistencies["season"] == 2024)
                              & (inconsistencies["earlier_round"] == 13)]  # fmt: skip
    assert (
        len(hungary) and hungary["note"].str.contains("R13에는 manifest에 pu_new 문서가 없어").all()
    )
    assert hungary["related_documents"].notna().any()
    # 배정 문장에 보이지 않는 글자나 앞뒤 빈칸이 붙지 않는다
    text = new["allocation_text"]
    assert not text.str.contains("[-]").any() and (text == text.str.strip()).all()


def test_ice_events_agree_with_new_table(new, inconsistencies):
    ice = pd.read_csv(FIA / "pu_ice_events.csv")
    assert list(ice.columns) == pu.ICE_FIELDS
    rows = new[
        (new["document_status"] == "ok") & (new["element"] == "ICE") & new["car_number"].notna()
    ]
    want = sorted(
        (r.season, r.round, r.car_number, r.driver_id, r.previously_used, r.source_url)
        for r in rows.itertuples()
    )
    got = sorted(
        (r.season, r.round, r.car_number, r.driver_id, r.printed_previously_used, r.source_url)
        for r in ice.itertuples()
    )
    assert got == want and len(got) >= 100
    # 순번은 Previously used + 1이다. 같은 대회 누적 문서나 배정 문장이 다른 값을 적은 행은
    # 어느 쪽도 고르지 않고 비운다(2022 캐나다 Leclerc, 2022 싱가포르 Russell)
    conflicts = inconsistencies[
        inconsistencies["kind"].isin(pu.CONFLICT_KINDS) & (inconsistencies["element"] == "ICE")
    ]
    conflicted = set(zip(conflicts["later_url"], conflicts["car_number"], strict=True))
    keys = list(zip(ice["source_url"], ice["car_number"], strict=True))
    flagged = pd.Series([key in conflicted for key in keys], index=ice.index)
    assert conflicted <= set(keys)
    assert ice.loc[flagged, "ice_number"].isna().all()
    assert ice.loc[flagged, "conflict"].notna().all() and ice.loc[~flagged, "conflict"].isna().all()
    clean = ice[~flagged]
    assert (clean["ice_number"] == clean["printed_previously_used"] + 1).all()
    assert (ice["ice_number"].dropna() >= 1).all()
    said = ice[ice["stated_ordinal"].notna() & ~flagged]
    assert (said["stated_ordinal"] == said["ice_number"]).all()
    by_car = ice.set_index(["season", "round", "car_number"])
    assert pd.isna(by_car.loc[(2022, 9, 16), "ice_number"])
    assert by_car.loc[(2022, 9, 16), "printed_previously_used"] == 3
    assert pd.isna(by_car.loc[(2022, 17, 63), "ice_number"])
    assert by_car.loc[(2022, 17, 63), "stated_ordinal"] == 5
    # 표 없이 "All drivers"로만 적은 시즌 첫 대회 선언은 차량이 없어 투입 이벤트로 펼치지 않는다
    everyone = new[(new["element"] == "ICE") & new["car_number"].isna()]
    assert set(everyone["driver_name"]) == {"All drivers"}
    assert set(everyone["round"]) == {1}
    verdict = rows.set_index(["source_url", "car_number", "previously_used"])["within_allocation"]
    for r in ice.itertuples():
        printed = verdict[(r.source_url, r.car_number, r.printed_previously_used)]
        assert pd.isna(printed) if pd.isna(r.within_allocation) else printed == r.within_allocation


def test_allocations_quote_the_documents(new, documents, inconsistencies):
    allocations = pd.read_csv(FIA / "pu_allocations.csv")
    assert list(allocations.columns) == pu.ALLOCATION_FIELDS
    assert not allocations.duplicated(["season", "element", "allowed"]).any()
    texts = set(new.loc[new["document_status"] == "ok", "allocation_text"])
    first_round = documents.set_index("url")["round"]
    for row in allocations.itertuples():
        assert row.statement in texts
        facts = pu.statement_facts(row.statement)
        assert (facts["allowed"], facts["allowed_season"]) == (row.allowed, row.season)
        assert first_round[row.source_url] == row.first_round
        # documents는 그 값을 밝힌 정상 선언 문서 수다
        ok = new[(new["document_status"] == "ok") & (new["season"] == row.season)
                 & (new["element"] == row.element)]  # fmt: skip
        facts = [pu.statement_facts(t) for t in ok["allocation_text"]]
        said = ok[[(f["allowed"], f["allowed_season"]) == (row.allowed, row.season) for f in facts]]
        assert said["source_url"].nunique() == row.documents >= 1
    stated = {(r.season, r.element): r.allowed for r in allocations.itertuples()}
    assert stated[(2021, "ICE")] == 3 and stated[(2021, "EX")] == 8 and stated[(2021, "ES")] == 2
    # 2020년에는 시즌 도중에 허용 개수가 바뀌어 같은 구성요소에 두 값이 있다
    first_2020 = allocations[(allocations["season"] == 2020) & (allocations["element"] == "ICE")]
    assert list(first_2020["allowed"]) == [2, 3]
    # 다른 값이 있는 구성요소에서 문서 한 건에만 나온 값은 불일치 목록에 있다(오타일 수 있다)
    listed = inconsistencies[inconsistencies["kind"] == "allocation_single_document"]
    listed = set(zip(listed["season"], listed["element"], listed["actual"], strict=True))
    several = allocations.groupby(["season", "element"]).allowed.transform("size") > 1
    single = allocations[several & (allocations["documents"] == 1)]
    assert set(zip(single["season"], single["element"], single["allowed"], strict=True)) == listed
    assert (2020, "ICE", 2) in listed


@pytest.mark.network
def test_parser_reproduces_curated_rows_from_source(used, new, documents):
    """표본 문서를 원문에서 다시 파싱해(캐시에 없으면 manifest를 보고 받아) 정제 데이터와 견준다."""
    docs = {
        file_name(r["url"]): r
        for r in manifest.read_rows(fia_docs.INDEX_MANIFEST)
        if r["doc_type"] in pu.DOC_TYPES
    }
    wanted = [docs[name] for name in SAMPLE]
    paths = [RAW_DIR / "fia" / fia_docs.pdf_cache_path(doc) for doc in wanted]
    if not all(path.exists() for path in paths):
        fia_docs.download_documents(pu.DOC_TYPES, urls={d["url"] for d in wanted})
    status = documents.set_index("url")["status"]
    for doc, path in zip(wanted, paths, strict=True):
        name = file_name(doc["url"])
        assert not doc["sha256"] or doc["sha256"] == sha256_bytes(path.read_bytes()), name
        if doc["doc_type"] == "pu_used":
            parsed = pu.parse_used(path)
            got = [
                (r["car_number"], r["team_text"], r["driver_name"], element, r["used"][element])
                for r in parsed.rows
                for element in parsed.elements
            ]
            rows = used[used["source_url"] == doc["url"]]
            want = [
                (r.car_number, r.team_text, r.driver_name, r.element, r.used)
                for r in rows.itertuples()
            ]
        else:
            parsed = pu.parse_new(path)
            got = [
                (r["car_number"], r["team_text"], r["driver_name"], r["element"],
                 r["previously_used"], r["allocation_text"], r["within_allocation"])
                for r in parsed.rows
            ]  # fmt: skip
            rows = (
                new[new["source_url"] == doc["url"]].astype(object).where(lambda t: t.notna(), None)
            )
            want = [
                (r.car_number, r.team_text, r.driver_name, r.element, r.previously_used,
                 r.allocation_text, r.within_allocation)
                for r in rows.itertuples()
            ]  # fmt: skip
        assert got == want and got, name
        assert parsed.ok == (name not in KNOWN_FAILURES), name
        assert (status[doc["url"]] == "needs_review") == (name in KNOWN_FAILURES), name


# 렌더링한 원문 쪽을 눈으로 읽어 옮겨 적은 값(2026-11-11). 파서 출력이 아니라 원문과 견준다.
# 누적 표: 파일 이름 -> (열, 차량 수, {차량 번호: (팀, 드라이버, 열 순서대로의 개수)})
HAND_USED = {
    # 2쪽, 문서 3. "George Russel" 오타와 Jack Aitken의 ES 1은 원문 그대로다
    "2020 Sakhir Grand Prix - PU elements used per driver up to now.pdf": (
        ["ICE", "TC", "MGU-H", "MGU-K", "ES", "CE"], 20, {
            63: ("Mercedes", "George Russel", (3, 3, 3, 3, 2, 2)),
            5: ("Ferrari", "Sebastian Vettel", (3, 3, 3, 2, 2, 2)),
            7: ("Alfa Romeo Racing Ferrari", "Kimi Räikkönen", (3, 2, 3, 2, 2, 2)),
            99: ("Alfa Romeo Racing Ferrari", "Antonio Giovinazzi", (3, 2, 2, 2, 2, 2)),
            20: ("Haas Ferrari", "Kevin Magnussen", (3, 2, 2, 2, 2, 2)),
            89: ("Williams Mercedes", "Jack Aitken", (4, 4, 4, 3, 1, 2)),
            6: ("Williams Mercedes", "Nicholas Latifi", (3, 3, 3, 3, 2, 2)),
        },
    ),
    # 2쪽, 문서 5. 허용 개수를 넘은 값은 빨간 글자로 인쇄되어 있다(Verstappen ICE 5, ES 3 등)
    "2025_abu_dhabi_grand_prix_-_pu_elements_used_per_driver_up_to_now.pdf": (
        ["ICE", "TC", "MGU-H", "MGU-K", "ES", "CE", "EX"], 20, {
            1: ("Red Bull Racing Honda RBPT", "Max Verstappen", (5, 5, 5, 5, 3, 3, 8)),
            22: ("Red Bull Racing Honda RBPT", "Yuki Tsunoda", (6, 6, 6, 6, 3, 3, 9)),
            31: ("Haas Ferrari", "Esteban Ocon", (5, 4, 4, 4, 2, 2, 5)),
            87: ("Haas Ferrari", "Oliver Bearman", (5, 5, 5, 5, 2, 3, 6)),
            30: ("Racing Bulls Honda RBPT", "Liam Lawson", (5, 5, 5, 4, 3, 3, 8)),
            81: ("McLaren Mercedes", "Oscar Piastri", (4, 4, 4, 4, 2, 2, 3)),
            5: ("Kick Sauber Ferrari", "Gabriel Bortoleto", (4, 4, 4, 4, 2, 2, 5)),
        },
    ),
}  # fmt: skip
# 선언 문서: 파일 이름 -> (구성요소별 행 수, [(구성요소, 차량, 팀, 드라이버, Previously used,
# 적합 여부, 허용 개수, 문장의 순서)])
HAND_NEW = {
    # TC 표는 2쪽 아래에서 시작해 3쪽 위에서 끝난다(첫 행 44번 Hamilton, 마지막 행 06번 Latifi)
    "2021 Azerbaijan Grand Prix - New PU elements for this Event.pdf": (
        {"ICE": 14, "TC": 14, "MGU-H": 14, "MGU-K": 10, "CE": 1, "EX": 16}, [
            ("TC", 44, "Mercedes", "Lewis Hamilton", 1, True, 3, None),
            ("TC", 6, "Williams Mercedes", "Nicholas Latifi", 1, True, 3, None),
            ("CE", 9, "Haas Ferrari", "Nikita Mazepin", 1, True, 2, None),
            ("EX", 14, "Alpine Renault", "Fernando Alonso", 4, True, 8, None),
            ("EX", 31, "Alpine Renault", "Esteban Ocon", 3, True, 8, None),
        ],
    ),
    # 2쪽: "one (1) of the four (4)"는 적합.
    # Gasly는 "the fifth (5) of the four (4)", not in conformity
    "2024 British Grand Prix - New PU elements for this Competition.pdf": (
        None, [
            ("ICE", 11, "Red Bull Racing Honda RBPT", "Sergio Perez", 3, True, 4, None),
            ("ICE", 10, "Alpine Renault", "Pierre Gasly", 4, False, 4, 5),
            ("ICE", 27, "Haas Ferrari", "Nico Hülkenberg", 2, True, 4, None),
        ],
    ),
}  # fmt: skip


def cached_sample(name: str) -> Path:
    """표본 문서의 캐시 경로. 캐시에 없으면 받지 않고 건너뛴다."""
    rows = [
        r for r in manifest.read_rows(fia_docs.INDEX_MANIFEST)
        if r["doc_type"] in pu.DOC_TYPES and file_name(r["url"]) == name
    ]  # fmt: skip
    assert len(rows) == 1, name
    path = RAW_DIR / "fia" / fia_docs.pdf_cache_path(rows[0])
    if not path.exists():
        pytest.skip(f"원문이 캐시에 없다: {name}")
    return path


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


@pytest.mark.parametrize("name", sorted(HAND_USED))
def test_used_parser_matches_hand_transcribed_values(name):
    elements, cars, expected = HAND_USED[name]
    parsed = pu.parse_used(cached_sample(name))
    assert parsed.ok and parsed.elements == elements and len(parsed.rows) == cars
    got = {
        r["car_number"]: (nfc(r["team_text"]), nfc(r["driver_name"]),
                          tuple(r["used"][e] for e in elements))
        for r in parsed.rows
    }  # fmt: skip
    for car, (team, driver, counts) in expected.items():
        assert got[car] == (nfc(team), nfc(driver), counts), (name, car)


@pytest.mark.parametrize("name", sorted(HAND_NEW))
def test_new_parser_matches_hand_transcribed_values(name):
    per_element, expected = HAND_NEW[name]
    parsed = pu.parse_new(cached_sample(name))
    assert parsed.ok and parsed.complete
    if per_element is not None:
        assert Counter(r["element"] for r in parsed.rows) == per_element
    got = {
        (r["element"], r["car_number"]): (
            nfc(r["team_text"]), nfc(r["driver_name"]), r["previously_used"],
            r["within_allocation"], r["allowed"], r["ordinal"],
        )
        for r in parsed.rows
    }  # fmt: skip
    for element, car, team, driver, before, within, allowed, ordinal in expected:
        assert got[element, car] == (nfc(team), nfc(driver), before, within, allowed, ordinal)
    if per_element is not None:  # 쪽을 넘는 표의 첫 행과 마지막 행
        tc = [r["car_number"] for r in parsed.rows if r["element"] == "TC"]
        assert (tc[0], tc[-1]) == (44, 6)
