"""T8 규정 조항 파서와 판 사이 비교 검증.

합성 줄로 위험 요소(목차, 머리말·꼬리말, 상호 참조, 색 글씨, 취소선, 삭제 조항, 부록 번호
재시작, 순서 어긋남)를 하나씩 확인하고, 정제 테이블의 키·순서·일관성·저작권 규칙을 확인한다.
테스트의 문장은 지어낸 글이다. 규정 본문을 옮겨 적지 않는다.
"""

from __future__ import annotations

import os
from collections import Counter

import pandas as pd
import pdfplumber
import pytest

from pipeline import manifest
from pipeline.config import CURATED_DIR
from pipeline.parsers import regulations as reg
from pipeline.sources import fia_regulations

OUT = CURATED_DIR / "regulations"
OWN_FILES = [
    "documents.csv", "articles.parquet", "changes.parquet", "comparisons.csv",
    "pu_allocation_rules.csv", "fuel_rules.csv",
]  # fmt: skip
QUOTE_COLUMNS = {"quote"}
TITLE_LIMIT = 140  # 조·조항 제목 글자 수 상한(본문이 제목으로 새어 들어오지 않았는지 본다)
# 원문을 다시 파싱해 커밋된 조항 목록과 맞춰 보는 표본. 시대와 구분이 다른 세 부를 골랐다.
SAMPLE = [
    ("2018", "technical", "2017-12-19"),  # 2018년 양식, 도면 부록, 목차 낡음(17.3)
    ("2022", "sporting", "2022-10-19"),  # 취소선이 가장 많은 판
    ("2025", "technical", "2025-04-07"),  # 여백 밖으로 내어 쓴 번호(3.7.6-3.7.8), 부록 표
]
# 사이트 운영자가 원문 번호 오류로 확인한 판(data/curated/review/human_review.csv, 2026-11-13)
HUMAN_REVIEWED = {
    (2021, "sporting", "2020-12-16"): "i08",
    (2025, "sporting", "2025-04-30"): "i09",
    (2021, "technical", "2019-10-31"): "i10",
    (2021, "technical", "2020-03-06"): "i11",
    (2022, "technical", "2020-03-30"): "i12",
    (2022, "technical", "2020-10-30"): "i13",
    (2022, "technical", "2021-02-19"): "i14",
    (2022, "technical", "2021-04-30"): "i15",
    (2022, "technical", "2021-07-08"): "i16",
    (2022, "technical", "2021-09-13"): "i17",
    (2022, "technical", "2021-12-15"): "i18",
}
# 파서를 고쳐 검수 대기에서 벗어난 판(human_review.csv i19)
PARSER_FIXED = (2023, "technical", "2023-02-22")
MARGIN = 70.9
BODY = 99.2


def line(text, x0=MARGIN, page=1, top=100.0, bold=0.0, rest_bold=None, **kw) -> reg.Line:
    """합성 줄. 기본은 여백 열에서 시작하는 보통 글씨."""
    return reg.Line(
        page=page, x0=x0, top=top, text=text, bold=bold,
        rest_bold=bold if rest_bold is None else rest_bold,
        small_number=kw.get("small_number", False), marked=kw.get("marked", False),
        in_table=kw.get("in_table", False), band=kw.get("band", "body"),
        x1=kw.get("x1", x0 + 6.0 * len(text)), image=kw.get("image", ""),
    )  # fmt: skip


def body(*lines: reg.Line) -> list[reg.Line]:
    """줄 사이 간격을 12pt로 매겨 돌려준다."""
    out = []
    for i, ln in enumerate(lines):
        ln.top = 60.0 + 12 * i
        out.append(ln)
    return out


def tech_start() -> list[reg.Line]:
    return [line("ARTICLE 1: GENERAL", bold=1.0), line("1.1 Scope", bold=1.0)]


def keys(clauses) -> list[str]:
    return [c.clause_no for c in clauses]


# --- 위험 요소별 합성 테스트 -------------------------------------------------------------


def test_table_of_contents_is_skipped():
    """목차 줄("ARTICLE 1: ... 6", "1.1 ...")은 본문 1조 제목 전까지 조항으로 읽지 않는다."""
    lines = body(
        line("CONTENTS:", bold=1.0),
        line("ARTICLE 1: GENERAL 6", bold=1.0),
        line("1.1 Scope"),
        line("1.2 Words used", x0=82.0),
        line("ARTICLE 2: CAR 9", bold=1.0),
        line("ARTICLE 1: GENERAL", bold=1.0),
        line("1.1 Scope", bold=1.0),
        line("Invented sentence for the first clause.", x0=BODY),
        line("1.2 Words used", bold=1.0),
    )
    clauses, problems, stats = reg.segment(lines, "technical")
    assert problems == []
    assert keys(clauses) == ["1", "1.1", "1.2"]
    assert stats["front_lines"] == 5
    assert clauses[1].text == "Invented sentence for the first clause."


def test_missing_body_start_is_a_problem():
    clauses, problems, _ = reg.segment(body(line("ARTICLE 1: GENERAL 6", bold=1.0)), "technical")
    assert clauses == [] and problems


def test_running_headers_footers_and_page_numbers_are_dropped():
    lines = []
    for page in range(1, 6):
        lines += [
            line(f"2030 Formula 1 Rules {page}/5 01 May 2030", page=page, top=780, band="footer"),
            line("© 2030 Some Federation", page=page, top=792, band="footer"),
            line(f"Body line on page {page}", page=page, top=300),
            line(str(page + 12), page=page, top=20, band="header"),
        ]
    lines.append(line("17", page=5, top=30, band="header"))
    kept, dropped = reg.drop_running_lines(lines, 5)
    assert [ln.text for ln in kept] == [f"Body line on page {p}" for p in range(1, 6)]
    assert dropped == 16


def test_number_at_page_top_that_is_not_a_page_number_is_kept():
    """쪽 번호 규칙(쪽 순번 - 12)에 맞지 않는 띠 안 숫자 줄은 본문이다(부록 1 20.2의 "325")."""
    lines = [line(str(page + 12), page=page, top=20, band="header") for page in range(1, 6)]
    lines.append(line("325", page=3, top=40, band="header"))
    kept, dropped = reg.drop_running_lines(lines, 5)
    assert [ln.text for ln in kept] == ["325"] and dropped == 5
    single = [line("325", page=3, top=40, band="header")]
    assert [ln.text for ln in reg.drop_running_lines(single, 5)[0]] == ["325"]


def test_repeated_logo_images_are_dropped_and_figures_kept():
    lines = [line("", page=p, top=200, image="logo") for p in range(1, 6)]
    lines.append(line("", page=2, top=300, image="figure"))
    kept, _ = reg.drop_running_lines(lines, 5)
    assert [ln.image for ln in kept] == ["figure"]


def test_cross_reference_at_line_start_stays_in_its_clause():
    """들여 쓴 줄 머리의 "4.2 of ..."는 상호 참조다. 새 조항이 아니다."""
    lines = body(
        *tech_start(),
        line("1.1.1 Invented first clause refers to Article", rest_bold=0.0),
        line("4.2 of these rules and continues.", x0=104.9),
        line("1.1.2 Invented second clause.", rest_bold=0.0),
    )
    clauses, problems, stats = reg.segment(lines, "technical")
    assert problems == []
    assert keys(clauses) == ["1", "1.1", "1.1.1", "1.1.2"]
    assert clauses[2].text.endswith("Article 4.2 of these rules and continues.")
    assert stats["inline_numbers"] == 1


def test_indented_next_number_with_heading_is_a_problem_not_a_guess():
    lines = body(*tech_start(), line("1.1.1 Alpha", bold=1.0), line("1.1.2 Beta", x0=130.0))
    _, problems, _ = reg.segment(lines, "technical")
    assert any("1.1.2" in p for p in problems)


def test_displaced_clause_number_in_small_type_is_a_clause():
    """여백에서 밀려 찍혔어도 작은 글자의 다음 번호는 조항이다(2023년 기술 규정 12.5.2)."""
    lines = body(
        *tech_start(),
        line("1.1.1 Alpha", bold=1.0),
        line("1.1.2 Beta", x0=130.0, small_number=True),
        line("Invented text.", x0=BODY),
    )
    clauses, problems, _ = reg.segment(lines, "technical")
    assert problems == []
    assert keys(clauses)[-1] == "1.1.2"


def test_amendment_colour_is_kept_as_text_and_marked():
    assert reg.is_coloured({"non_stroking_color": (1.0, 0.0, 1.0)})
    assert reg.is_coloured({"non_stroking_color": (0.753, 0.0, 0.0)})
    assert not reg.is_coloured({"non_stroking_color": (0.0,)})
    assert not reg.is_coloured({"non_stroking_color": (0.651,)})
    assert not reg.is_coloured({"non_stroking_color": (0.2, 0.2, 0.2)})
    lines = body(*tech_start(), line("New invented wording.", x0=BODY, marked=True))
    clauses, _, _ = reg.segment(lines, "technical")
    assert clauses[1].marked and clauses[1].text == "New invented wording."
    assert not clauses[0].marked


def char(text, x0, top=100.0, size=11.0):
    return {"text": text, "x0": x0, "x1": x0 + 5, "top": top, "bottom": top + size}


def glyph(text, x0, top, size=10.0, width=5.0, **kw):
    """pdfplumber 글자 사전 꼴의 합성 글자."""
    return {
        "text": text, "x0": x0, "x1": x0 + width, "top": top, "bottom": top + size,
        "doctop": top, "size": size, "upright": True, "fontname": "Invented",
        "matrix": kw.get("matrix", (size, 0, 0, size, x0, 0)), "width": width, "height": size,
        "non_stroking_color": (0,),
    }  # fmt: skip


def word(text, x0, top, size=10.0, width=5.0):
    return [glyph(ch, x0 + i * width, top, size, width) for i, ch in enumerate(text)]


def test_subscript_is_moved_onto_its_line():
    """ "X" 뒤 작은 "DIF"는 3pt 아래에 찍혀도 "XDIF"로 한 줄에 읽는다(부록 1 41.1)."""
    chars = word("at X", 100, 171.1) + word("DIF", 120, 174.2, size=6.5, width=3.0)
    chars += word("=0", 129, 171.1)
    moved, count = reg.snap_offset_chars(chars)
    assert count == 3
    assert {c["top"] for c in moved} == {171.1}


def test_superscript_before_a_letter_is_moved_onto_its_line():
    chars = word("Flashpoint ", 100, 222.6, size=11.0) + [glyph("o", 160.5, 221.5, 7.0, 3.7)]
    chars += word("C", 164.2, 222.6, size=11.0)
    chars += word("rejected", 120.0, 240.6, size=11.0)
    moved, _ = reg.snap_offset_chars(chars)
    assert moved[11]["top"] == 222.6  # 아래 줄의 틈이 아니라 붙어 있는 "C"의 줄로 간다


def test_stray_glyph_is_moved_into_the_gap_it_fits():
    """글자 상자가 두 줄 아래에 잡힌 하이픈은 꼭 맞는 틈("mid" 와 "point" 사이)으로 간다."""
    chars = word("mid", 100, 286.6, size=11.0) + word("point", 118.7, 286.6, size=11.0)
    chars += [glyph("-", 115.0, 310.4, 11.0, 3.7)]
    chars += word("A radius", 100, 316.6, size=11.0)
    moved, count = reg.snap_offset_chars(chars)
    assert count == 1 and moved[8]["top"] == 286.6


def test_letter_next_to_subscripts_stays_on_its_line():
    """아래첨자 사이에 낀 큰 글자("XC, X DIF")는 아래첨자 줄로 내려가지 않는다."""
    chars = word("X", 100, 320.8) + word("C, ", 105, 323.9, size=6.5, width=1.7)
    chars += word("X", 110.1, 320.8) + word("DIF", 115.1, 323.9, size=6.5, width=3.0)
    moved, _ = reg.snap_offset_chars(chars)
    assert {c["top"] for c in moved} == {320.8}


def test_rotated_letters_are_recognised():
    assert reg.is_rotated({"upright": False, "matrix": (1, 0, 0, 1, 0, 0)})
    assert reg.is_rotated({"upright": True, "matrix": (0.0, 1.0, -1.0, 0.0, 66.9, 703.9)})
    assert not reg.is_rotated({"upright": True, "matrix": (11.0, 0.0, 2.3, 11.0, 0, 0)})


class FakeRow:
    def __init__(self, cells):
        self.cells = cells
        self.bbox = (cells[0][0], cells[0][1], cells[-1][2], cells[0][3])


class FakeTable:
    def __init__(self, rows):
        self.rows = [FakeRow(r) for r in rows]
        self.bbox = (rows[0][0][0], rows[0][0][1], rows[-1][-1][2], rows[-1][-1][3])


class FakePage:
    bbox = (0, 0, 600, 800)
    width, height = 600, 800


def test_table_cells_are_read_cell_by_cell():
    """칸 안 줄바꿈 위치가 달라도 표 행의 글은 같다(2018과 2019년 판 부록 2의 28행)."""
    table = FakeTable([[(100, 100, 300, 140), (300, 100, 400, 140)]])
    wrap_a = word("tubes, hoses,", 105, 102) + word("supports", 105, 116) + word("EXC", 305, 102)
    wrap_b = word("tubes,", 105, 102) + word("hoses, supports", 105, 116) + word("EXC", 305, 102)
    for chars in (wrap_a, wrap_b):
        rows, rest = reg.table_rows([table], chars, FakePage())
        assert [r["text"] for r in rows] == ["tubes, hoses, supports EXC"] and rest == []


def test_plain_heading_is_told_apart_from_body_text():
    """스포팅 규정의 굵지 않은 소제목("30.1 Supply of tyres")과 번호 뒤 본문 첫 줄을 가른다."""
    layout = reg.Layout(line_gap=15.0, right_edge=524.0)
    heading = line("30.1 Supply of tyres", top=100.0, x1=170.0)
    assert reg.plain_heading(heading, "Supply of tyres", line("a) Text", top=121.5), layout)
    body = line("2.2 The Championship is governed by the", top=100.0, x1=480.0)
    assert not reg.plain_heading(body, "The Championship is governed by the",
                                 line("Code.", top=115.0), layout)  # fmt: skip
    short = line("5.4 An allocation will take place at up to two (2) Events", top=100.0, x1=300.0)
    assert not reg.plain_heading(short, "An allocation will take place at up to two (2) Events",
                                 line("for the season.", top=113.4), layout)  # fmt: skip
    ends = line("29.1 Each car must carry a camera.", top=100.0, x1=300.0)
    assert not reg.plain_heading(ends, "Each car must carry a camera.", None, layout)


def test_sporting_plain_headings_are_read_and_technical_body_is_not():
    sport = [
        line("1) GENERAL", bold=1.0, top=60.0),
        line("1.1 Supply of tyres", top=80.0, x1=170.0),
        line("a) Invented first item.", x0=BODY, top=101.5),
        line("1.2 Invented body text that is a full justified first line of the", top=123.0,
             x1=524.0),
        *(line("Invented continuation line of the same paragraph.", x0=BODY, top=138.0 + 15 * i,
               x1=524.0) for i in range(4)),
    ]  # fmt: skip
    clauses, problems, stats = reg.segment(sport, "sporting")
    assert problems == [] and stats["plain_headings"] == 1
    assert [(c.clause_no, c.heading) for c in clauses] == [
        ("1", "GENERAL"), ("1.1", "Supply of tyres"), ("1.2", ""),
    ]  # fmt: skip
    tech = [
        line("ARTICLE 1: GENERAL", bold=1.0, top=60.0),
        line("1.1 All discs must have a maximum thickness of 3mm", top=80.0, x1=300.0),
        line("1.2 Next", bold=1.0, top=101.5),
    ]
    clauses, _, _ = reg.segment(tech, "technical")
    assert clauses[1].heading == "" and clauses[1].text.startswith("All discs")


def test_appendix_title_lines_with_year_or_centred_gap_are_joined():
    """부록 제목 둘째 줄이 연도로 시작하거나(부록 4) 가운데 맞춤으로 떨어져 있다(부록 2)."""
    lines = [
        line("1) GENERAL", bold=1.0, top=60.0),
        line("1.1 Invented text.", top=80.0, x1=400.0),
        line("APPENDIX 2", bold=1.0, x0=270.0, top=90.0, x1=330.0),
        line("SOME FEDERATION NAME", bold=1.0, x0=230.0, top=126.0, x1=370.0),
        line("2030 ENTRY FORM", bold=1.0, x0=250.0, top=162.0, x1=350.0),
        line("THE APPLICANT", bold=1.0, top=198.0, x1=160.0),
        line("APPENDIX 4", bold=1.0, x0=270.0, top=300.0, x1=330.0),
        line("2026‐2030 POWER UNIT HOMOLOGATION", bold=1.0, x0=200.0, top=324.0, x1=400.0),
        line("1) Invented item.", top=360.0, x1=300.0),
    ]
    clauses, problems, _ = reg.segment(lines, "sporting")
    assert problems == []
    titles = {c.clause_no: c.top_title for c in clauses if c.level == 1}
    assert titles["A2"] == "SOME FEDERATION NAME 2030 ENTRY FORM"
    assert titles["A4"] == "2026-2030 POWER UNIT HOMOLOGATION"
    assert clauses[-1].text == "1) Invented item."


def test_void_appendix_with_note_is_not_used():
    void = reg.Clause("A6", "appendix", 1, 70, "", "A6", "", "-Void- NOTE: Invented reason.")
    assert reg.is_not_used(void)
    kept = reg.Clause("A7", "appendix", 1, 71, "", "A7", "", "Invented NOTE: on a real rule.")
    assert not reg.is_not_used(kept)


def struck(ln: reg.Line) -> reg.Line:
    ln.struck = True
    return ln


def test_struck_heading_line_is_kept_as_a_marker(tmp_path):
    """취소선으로 지운 부록 제목("APPENDIX 6") 아래의 지우지 않은 "-Void-"는 앞 조항에 붙지 않는다
    (2021년 스포팅 규정 Issue 2의 부록 6). 지운 제목은 struck 줄로 남고, 부록 6은 효력 없는
    조항이 된다."""
    ops = (
        text_op(70.9, 740, "ARTICLE 1: GENERAL", bold=True)
        + text_op(70.9, 720, "1.1", bold=True)
        + text_op(99.2, 720, "Invented first clause text.")
        + text_op(270.4, 700, "APPENDIX 6", bold=True)
        + "265 703.2 75 0.6 re f\n"  # 글자 높이 가운데를 지나는 취소선
        + text_op(70.9, 670, "-Void-")
    )
    path = tmp_path / "struck.pdf"
    path.write_bytes(tiny_pdf(ops))
    with pdfplumber.open(path) as pdf:
        lines, stats = reg.page_lines(pdf.pages[0], 1)
    assert stats["struck_chars"] == len("APPENDIX6")
    assert [(ln.text, ln.struck) for ln in lines if ln.struck] == [("APPENDIX 6", True)]
    clauses, problems, seg = reg.segment(lines, "technical")
    assert problems == [] and seg["struck_headings"] == 1
    assert keys(clauses) == ["1", "1.1", "A6"]
    assert clauses[1].text == "Invented first clause text."
    a6 = clauses[2]
    assert a6.struck and a6.not_used and a6.text == "-Void-"


def test_struck_heading_with_only_a_note_is_not_used():
    """지운 조 제목 아래에 "Note: ..." 한 문단만 남은 조(2022년 기술 규정 Issue 9의 18조)."""
    lines = body(
        *tech_start(),
        line("Invented text.", x0=BODY),
        struck(line("ARTICLE 2: INVENTED FUTURE CHANGES", bold=1.0)),
        line("Note: This Article has been moved to Appendix 9", bold=1.0),
        line("APPENDIX 1: INVENTED", bold=1.0),
        struck(line("APPENDIX 2", bold=1.0, x0=270.0)),
        line("[Note. Invented reason for removing this appendix.]"),
    )
    clauses, problems, _ = reg.segment(lines, "technical")
    assert problems == []
    assert keys(clauses) == ["1", "1.1", "2", "A1", "A2"]
    assert clauses[1].text == "Invented text."
    assert [(c.clause_no, c.struck, c.not_used) for c in clauses if c.struck] == [
        ("2", True, True), ("A2", True, True),
    ]  # fmt: skip
    assert clauses[2].heading == "INVENTED FUTURE CHANGES"


def test_struck_heading_without_live_text_is_dropped():
    """제목과 글을 모두 지운 부록, 지운 제목 바로 뒤에 새 제목을 쓴 부록은 예전처럼 조항으로 남지
    않고 번호 순서 문제도 만들지 않는다(2022년 스포팅 규정 Issue 2의 부록 4, 6A)."""
    lines = body(
        *tech_start(),
        line("APPENDIX 1: INVENTED", bold=1.0),
        line("1 Invented section", bold=1.0),
        struck(line("APPENDIX 2: OLD TITLE", bold=1.0)),
        line("APPENDIX 2: NEW TITLE", bold=1.0),
        line("Invented text.", x0=BODY),
        struck(line("APPENDIX 3: DELETED", bold=1.0)),
    )
    clauses, problems, stats = reg.segment(lines, "technical")
    assert problems == [] and stats["struck_headings"] == 2
    assert keys(clauses) == ["1", "1.1", "A1", "A1-1", "A2"]
    assert clauses[-1].heading == "NEW TITLE" and not clauses[-1].struck


def test_live_text_under_a_struck_heading_is_a_problem():
    """지운 제목 아래에 지우지 않은 조항 번호나 본문이 있으면 추측하지 않고 문제로 남긴다."""
    numbered = body(
        *tech_start(),
        struck(line("ARTICLE 2: INVENTED", bold=1.0)),
        line("2.1 Invented live clause", bold=1.0),
    )
    _, problems, _ = reg.segment(numbered, "technical")
    assert problems == ["1쪽: 취소선으로 지운 2조 제목 뒤에 지우지 않은 글이 있다"]
    text = body(
        *tech_start(),
        struck(line("APPENDIX 1: INVENTED", bold=1.0)),
        line("Invented live paragraph that is not a note."),
    )
    clauses, problems, _ = reg.segment(text, "technical")
    assert problems == ["1쪽: 취소선으로 지운 부록 1 제목 뒤에 지우지 않은 글이 있다"]
    assert clauses[1].text == "" and not clauses[-1].not_used


def test_left_aligned_appendix_title_wraps_with_a_wide_gap():
    """부록 제목 둘째 줄이 왼쪽 맞춤으로 25.7pt 아래에 있다(2021년 스포팅 규정 첫 판 74쪽 부록 3:
    60.3pt와 86.0pt). 제목 줄은 굵은 대문자가 이어지는 동안 모두 잇는다."""
    lines = [
        line("1) GENERAL", bold=1.0, top=60.0),
        *(line(f"1.{i} Invented text.", top=80.0 + 12 * i, x1=400.0) for i in range(1, 6)),
        line("APPENDIX 3: INVENTED TITLE THAT IS LONG ENOUGH TO WRAP BEFORE A", bold=1.0,
             top=60.3, page=2, x1=476.4),
        line("COMPETITION", bold=1.0, top=86.0, page=2, x1=154.5),
        line("PART A.", top=122.8, page=2, x1=106.1),
        line("APPENDIX 5", bold=1.0, x0=271.0, top=78.3, page=3, x1=341.0),
        line("INVENTED FEDERATION NAME", bold=1.0, x0=191.2, top=103.1, page=3, x1=420.9),
        line("INVENTED STAFF REGISTRATION FORM FOR THE", bold=1.0, x0=185.0, top=123.3, page=3,
             x1=427.0),
        line("INVENTED WORLD CHAMPIONSHIP", bold=1.0, x0=205.9, top=143.4, page=3, x1=406.2),
        line("Invented form line.", top=181.0, page=3, x1=520.5),
    ]  # fmt: skip
    clauses, problems, _ = reg.segment(lines, "sporting")
    assert problems == []
    titles = {c.clause_no: (c.top_title, c.text) for c in clauses if c.level == 1}
    # 짧은 조 제목 아래 25pt의 굵은 대문자 알림 줄은 첫 낱말이 앞 줄에 들어가므로 제목이 아니다
    # (2021년 기술 규정 첫 판 13조).
    note = [
        *tech_start(),
        line("Invented text.", x0=BODY, top=72.0, x1=520.0),
        *(line(f"Invented line {i}.", x0=BODY, top=84.0 + 12 * i, x1=520.0) for i in range(4)),
        line("ARTICLE 2: SHORT TITLE", bold=1.0, top=200.0, x1=230.0),
        line("NOTE: AN INVENTED NOTICE IN BOLD CAPITALS", bold=1.0, top=225.0, x1=330.0),
    ]
    for i, ln in enumerate(note[:2]):
        ln.top = 48.0 + 12 * i
    clauses_note, _, _ = reg.segment(note, "technical")
    assert clauses_note[-1].heading == "SHORT TITLE"
    assert clauses_note[-1].text == "NOTE: AN INVENTED NOTICE IN BOLD CAPITALS"
    assert titles["A3"] == (
        "INVENTED TITLE THAT IS LONG ENOUGH TO WRAP BEFORE A COMPETITION", "PART A.",
    )  # fmt: skip
    assert titles["A5"] == (
        "INVENTED FEDERATION NAME INVENTED STAFF REGISTRATION FORM FOR THE INVENTED WORLD "
        "CHAMPIONSHIP",
        "Invented form line.",
    )


def test_own_number_inside_future_changes_article_is_a_clause():
    """다음 해 변경을 옮겨 적은 조 안에서도 그 조의 번호("47.1")는 이 판의 조항이다."""
    lines = body(
        line("1) GENERAL", bold=1.0),
        line("1.1 Invented text.", x1=400.0),
        line("2) CHANGES FOR 2031", bold=1.0),
        line("2.1 Changes to Article 21.7", x1=200.0),
        line("21.7 Invented future wording.", x0=BODY),
    )
    clauses, problems, stats = reg.segment(lines, "sporting")
    assert problems == [] and keys(clauses) == ["1", "1.1", "2", "2.1"]
    assert clauses[-1].text.endswith("21.7 Invented future wording.")


def test_pictures_belong_to_the_clause_they_follow():
    lines = body(*tech_start(), line("", image="abc"), line("1.2 Next", bold=1.0))
    clauses, problems, _ = reg.segment(lines, "technical")
    assert problems == [] and clauses[1].images == ["abc"] and clauses[2].images == []
    assert clauses[1].image_sha256 and clauses[2].image_sha256 == ""


def test_strikethrough_is_found_and_underline_is_not():
    chars = [char("a", 10), char("b", 15), char("c", 40), char("d", 45)]
    strike = [(9.0, 21.0, 100.0 + 11 * 0.5)]  # 글자 높이 가운데
    underline = [(39.0, 51.0, 100.0 + 11 * 0.85)]  # 2018년 판의 개정 밑줄
    found = reg.struck_chars(chars, strike + underline)
    assert found == {id(chars[0]), id(chars[1])}


def test_deleted_or_unused_clauses_are_marked_not_used():
    lines = body(
        line("ARTICLE 1: GENERAL", bold=1.0),
        line("1.1 [Article Not Used]", bold=1.0),
        line("1.2 Kept", bold=1.0),
        line("Invented text.", x0=BODY),
        line("ARTICLE 2: VOID", bold=1.0),
    )
    clauses, problems, _ = reg.segment(lines, "technical")
    assert problems == []
    assert {c.clause_no: c.not_used for c in clauses} == {
        "1": False, "1.1": True, "1.2": False, "2": True,
    }  # fmt: skip
    sport = body(line("29) VOID", bold=1.0), line("29.1 Not used"))
    sport.insert(0, line("1) GENERAL", bold=1.0))
    clauses, _, _ = reg.segment(sport, "sporting")
    assert [c.not_used for c in clauses] == [False, True, True]


def test_sporting_article_heading_without_bracket():
    """2023년 판 "40 PRE-SPRINT AND PRE-RACE PARC FERME"처럼 괄호가 빠진 조 제목."""
    lines = body(
        line("1) GENERAL", bold=1.0),
        line("1.1 Invented text."),
        line("2 PARC FERME", bold=1.0),
        line("2.1 Invented text."),
    )
    clauses, problems, _ = reg.segment(lines, "sporting")
    assert problems == []
    assert keys(clauses) == ["1", "1.1", "2", "2.1"]


def test_numbering_restarts_in_appendices_with_prefix():
    lines = body(
        *tech_start(),
        line("APPENDIX 1: REFERENCE VOLUMES", bold=1.0),
        line("1 General Definitions", bold=1.0),
        line("1.1 Invented appendix text."),
        line("2 Floor Surface", bold=1.0),
        line("APPENDIX 2", bold=1.0),
        line("DRAWINGS", bold=1.0),
        line("1. Invented unnumbered list item.", rest_bold=0.0),
    )
    clauses, problems, _ = reg.segment(lines, "technical")
    assert problems == []
    assert keys(clauses) == ["1", "1.1", "A1", "A1-1", "A1-1.1", "A1-2", "A2"]
    a2 = clauses[-1]
    assert a2.heading == "DRAWINGS" and a2.top_article == "A2" and a2.level == 1
    assert clauses[4].level == 3 and clauses[4].top_title == "REFERENCE VOLUMES"


def test_order_breaks_and_duplicates_are_problems():
    lines = body(
        *tech_start(),
        line("1.2 Second", bold=1.0),
        line("1.2 Second again", bold=1.0),
        line("1.1.5 Back", bold=1.0),
        line("ARTICLE 3: SKIPPED", bold=1.0),
    )
    _, problems, _ = reg.segment(lines, "technical")
    text = " / ".join(problems)
    assert "1.2 다음 1.2" in text
    assert "1.2 다음 1.1.5" in text
    assert "1.2가 2번" in text
    assert "1에서 3으로" in text or "1에서 3로" in text


def test_clause_number_outside_its_article_is_a_problem():
    lines = body(*tech_start(), line("7.1 Wrong place", bold=1.0))
    _, problems, _ = reg.segment(lines, "technical")
    assert any("7.1가 1조 안에" in p for p in problems)


def test_future_change_sections_are_not_split():
    """다음 해 규정을 옮겨 적은 조·부록은 그 해 번호를 조항으로 나누지 않는다."""
    lines = body(
        *tech_start(),
        line("APPENDIX 6: APPROVED CHANGES FOR 2031", bold=1.0),
        line("6.5.3 Invented future wording."),
        line("4.1 Mass", bold=1.0),
    )
    clauses, problems, stats = reg.segment(lines, "technical")
    assert problems == []
    assert keys(clauses)[-1] == "A6"
    assert stats["future_change_numbers"] == 2


def test_wrapped_headings_are_joined():
    lines = body(
        line("ARTICLE 1: GENERAL", bold=1.0),
        line("1.1 Materials and construction - Energy", bold=1.0),
        line("storage systems", bold=1.0, x0=BODY),
        line("Invented text.", x0=BODY),
        line("APPENDIX 1", bold=1.0),
        line("INFORMATION REQUIRED", bold=1.0),
        line("BEFORE A COMPETITION", bold=1.0),
        line("1. NAME OF THE ORGANISER", bold=1.0),
    )
    clauses, _, _ = reg.segment(lines, "technical")
    assert clauses[1].heading == "Materials and construction - Energy storage systems"
    assert clauses[1].text == "Invented text."
    assert clauses[2].heading == "INFORMATION REQUIRED BEFORE A COMPETITION"


def test_normalise_and_join():
    assert reg.normalise("a – b “q”  include :") == 'a - b "q" include:'
    text, starts = reg.join_lines(["end-", "of-session rule", "next"], [3, 3, 4])
    assert text == "end-of-session rule next"
    assert starts == [[0, 3], [20, 4]]
    # 줄 끝 하이픈 앞이 숫자나 기호여도 잇는다(14.4 "8853-2016", 16.4 "(+1%/-0)").
    assert reg.join_lines(["standard 8853-", "2016."])[0] == "standard 8853-2016."
    assert reg.join_lines(["(+1%/-", "0)"])[0] == "(+1%/-0)"
    assert reg.join_lines(["list -", "item"])[0] == "list - item"
    clause = reg.Clause("1.1", "body", 2, 3, "", "1", "GENERAL", text, page_starts=starts)
    assert reg.page_at(clause, 0) == 3 and reg.page_at(clause, 21) == 4
    assert reg.text_hash("a  b") == reg.text_hash("a b")


def test_version_order():
    rows = [
        {"version_date": "2021-03-05", "issue": "10", "variant": ""},
        {"version_date": "2020-03-30", "issue": "3b", "variant": ""},
        {"version_date": "2021-03-05", "issue": "9", "variant": ""},
        {"version_date": "2024-04-30", "issue": "6", "variant": "v2"},
        {"version_date": "2024-04-30", "issue": "6", "variant": "v1"},
    ]
    ordered = sorted(rows, key=reg.version_order)
    assert [(r["issue"], r["variant"]) for r in ordered] == [
        ("3b", ""), ("9", ""), ("10", ""), ("6", "v1"), ("6", "v2"),
    ]  # fmt: skip
    assert reg.version_key(rows[3]) == "2024-04-30-v2"
    assert reg.version_key(rows[0]) == "2021-03-05"


def clause(no, text, heading="", not_used=False, page=1):
    return reg.Clause(no, "body", no.count(".") + 1, page, heading, no.split(".")[0], "T", text,
                      not_used)  # fmt: skip


def test_compare_classifies_changes():
    old = [clause("1", ""), clause("1.1", "alpha beta gamma"), clause("1.2", "same"),
           clause("1.3", "gone"), clause("1.4", "content")]  # fmt: skip
    new = [clause("1", ""), clause("1.1", "alpha beta delta"), clause("1.2", "same"),
           clause("1.4", "", "[Article Not Used]", True), clause("1.5", "new")]  # fmt: skip
    found, totals = reg.compare(old, new)
    rows = {r["clause_no"]: r for r in found}
    assert {k: r["change"] for k, r in rows.items()} == {
        "1.1": "modified", "1.3": "removed", "1.4": "removed", "1.5": "added",
    }  # fmt: skip
    assert 0 < rows["1.1"]["similarity"] < 1
    assert rows["1.5"]["similarity"] is None and rows["1.3"]["chars_to"] is None
    assert rows["1.5"]["from_clause_no"] is None and rows["1.3"]["from_clause_no"] == "1.3"
    assert totals == {"unchanged": 2, "added": 1, "removed": 2, "modified": 1, "renumbered": 0}
    assert not any(r["renumbered"] for r in found)


SENTENCES = [
    "Invented clause about the colour of the timing screens in the paddock area.",
    "Invented clause about how many spare wheels each team may bring to an event.",
    "Invented clause about the hours during which the garage doors must stay closed.",
    "Invented clause about where the marshals stand when a red flag is shown.",
]


def test_compare_follows_renumbered_clauses():
    """조항 하나를 끼워 넣어 뒤 번호가 밀리면 번호만 바뀐 조항은 renumbered가 참이고 유사도가
    1인 modified다(2019년 판 22.14). change 값은 added, removed, modified 세 가지뿐이다."""
    old = [clause("1", ""), *(clause(f"1.{i + 1}", t) for i, t in enumerate(SENTENCES[:3]))]
    new = [clause("1", ""), clause("1.1", SENTENCES[3]),
           *(clause(f"1.{i + 2}", t) for i, t in enumerate(SENTENCES[:3]))]  # fmt: skip
    rows, totals = reg.compare(old, new)
    assert [(r["from_clause_no"], r["clause_no"], r["change"], r["renumbered"]) for r in rows] == [
        (None, "1.1", "added", False), ("1.1", "1.2", "modified", True),
        ("1.2", "1.3", "modified", True), ("1.3", "1.4", "modified", True),
    ]  # fmt: skip
    assert {r["similarity"] for r in rows if r["renumbered"]} == {1.0}
    assert totals["renumbered"] == 3 and totals["modified"] == 3 and totals["unchanged"] == 1


def test_compare_follows_moved_and_edited_clause():
    """번호가 바뀌면서 글도 조금 고친 조항은 옛 번호를 단 modified다(2018년 판 21.3.5)."""
    edited = SENTENCES[1].replace("spare", "extra")
    old = [clause("1", ""), clause("1.1", SENTENCES[0]), clause("1.2", SENTENCES[1])]
    new = [clause("1", ""), clause("1.1", SENTENCES[2]), clause("1.2", SENTENCES[3]),
           clause("1.3", edited)]  # fmt: skip
    rows = {(r["from_clause_no"], r["clause_no"]): r for r in reg.compare(old, new)[0]}
    assert rows[("1.2", "1.3")]["change"] == "modified"
    assert 0.8 <= rows[("1.2", "1.3")]["similarity"] < 1


def test_compare_does_not_pair_same_number_in_different_articles():
    """조가 통째로 밀렸으면 같은 번호의 조항끼리 짝짓지 않는다(2021년 스포팅 규정 39.1)."""

    def art(no, title, texts):
        head = reg.Clause(no, "body", 1, 1, title, no, title, "")
        return [head] + [
            reg.Clause(f"{no}.{i + 1}", "body", 2, 1, "", no, title, t) for i, t in enumerate(texts)
        ]

    old = art("1", "GENERAL", SENTENCES[:1]) + art("2", "SAFETY CAR", SENTENCES[1:3])
    new = (
        art("1", "GENERAL", SENTENCES[:1])
        + art("2", "EXTRA LAP", [SENTENCES[3]])
        + art("3", "SAFETY CAR", SENTENCES[1:3])
    )
    rows = {(r["from_clause_no"], r["clause_no"]): r["change"] for r in reg.compare(old, new)[0]}
    assert rows == {
        ("2", "3"): "modified", ("2.1", "3.1"): "modified", ("2.2", "3.2"): "modified",
        (None, "2"): "added", (None, "2.1"): "added",
    }  # fmt: skip


def test_compare_counts_changed_pictures():
    a = reg.Clause("A3", "appendix", 1, 1, "FLOW", "A3", "FLOW", "", images=["0" * 64])
    same = reg.Clause("A3", "appendix", 1, 1, "FLOW", "A3", "FLOW", "", images=["1" + "0" * 63])
    other = reg.Clause("A3", "appendix", 1, 1, "FLOW", "A3", "FLOW", "", images=["f" * 64])
    assert reg.images_match(a.images, same.images)  # 1비트 차이는 다시 압축한 같은 그림
    assert reg.compare([a], [same])[0] == []
    rows = reg.compare([a], [other])[0]
    assert rows[0]["change"] == "modified" and rows[0]["images_changed"]
    assert rows[0]["similarity"] == 1.0  # 글은 같다


def test_pu_allocation_reads_only_the_first_sentence():
    text = (
        "a) Invented lead, each driver may use no more than five (5) engines (ICE), six (6) "
        "turbochargers (TC), one (1) energy stores (ES) and 7 motor generator units-kinetic "
        "(MGU-K) during a season. Should fewer events take place, each driver may use no more "
        "than 2 engines (ICE)."
    )
    rows = reg.pu_allocation([clause("9.2", text, page=4)])
    assert [(r["element"], r["allowed"]) for r in rows] == [
        ("ICE", 5), ("TC", 6), ("ES", 1), ("MGU-K", 7),
    ]  # fmt: skip
    assert rows[0]["quote"].startswith("each driver may use no more than five (5) engines")
    assert all(len(r["quote"]) <= reg.QUOTE_LIMIT for r in rows)


def tiny_pdf(ops: str) -> bytes:
    """글꼴 두 개(Helvetica, Helvetica-Bold)를 쓰는 한 쪽짜리 PDF. ops는 쪽 내용 연산자다."""
    stream = ops.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref,
    )  # fmt: skip
    return out


def text_op(x, y, text, size=11, bold=False):
    return f"BT /{'F2' if bold else 'F1'} {size} Tf {x} {y} Td ({text}) Tj ET\n"


def test_clause_number_inside_highlight_box_is_a_clause(tmp_path):
    """노란 개정 강조 상자(칠하기만 한 사각형)는 표가 아니다. 그 안의 작은 글자 번호는 조항이다
    (2023년 스포팅 규정 Issue 3의 42.2는 상자 안에 있어 42.1에 붙었다)."""
    ops = (
        "1 1 0 rg\n70 652 454 14 re f\n70 637 454 14 re f\n0 g\n"
        + text_op(70.9, 720, "ARTICLE 1: GENERAL", bold=True)
        + text_op(70.9, 700, "1.1", size=9, bold=True)
        + text_op(99.2, 700, "Invented first clause text.")
        + text_op(70.9, 655, "1.2", size=9, bold=True)
        + text_op(99.2, 655, "Invented highlighted clause text")
        + text_op(99.2, 640, "that continues on a second line.")
        + text_op(70.9, 610, "1.3", size=9, bold=True)
        + text_op(99.2, 610, "Invented last clause text.")
    )
    path = tmp_path / "box.pdf"
    path.write_bytes(tiny_pdf(ops))
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        assert [len(t.rows) for t in page.find_tables()] == [2]  # 거르지 않으면 표로 읽힌다
        tables, blocks = reg.find_tables(page)
        assert tables == [] and blocks == 2
        lines, stats = reg.page_lines(page, 1)
    assert stats["tables"] == 0 and not any(ln.in_table for ln in lines)
    clauses, problems, seg = reg.segment(lines, "technical")
    assert problems == [] and seg["number_gaps"] == 0
    assert keys(clauses) == ["1", "1.1", "1.2", "1.3"]
    assert clauses[2].text == "Invented highlighted clause text that continues on a second line."


def test_fill_blocks_are_not_table_borders():
    yellow = {"object_type": "rect", "fill": True, "stroke": False,
              "x0": 70, "x1": 524, "top": 100, "bottom": 114}  # fmt: skip
    border = {**yellow, "bottom": 100.5}
    stroked = {**yellow, "stroke": True}
    assert reg.is_fill_block(yellow)
    assert not reg.is_fill_block(border) and not reg.is_fill_block(stroked)


def test_small_margin_number_in_a_table_is_a_clause():
    """칸 선이 있는 표 안이라도 여백 열의 작은 글자 다음 번호는 조항이다."""
    lines = body(
        *tech_start(),
        line("Invented text.", x0=BODY),
        line("1.2 Invented boxed clause.", in_table=True, small_number=True),
        line("Invented boxed continuation.", x0=BODY, in_table=True),
    )
    clauses, problems, _ = reg.segment(lines, "technical")
    assert problems == [] and keys(clauses) == ["1", "1.1", "1.2"]
    assert clauses[2].text == "Invented boxed clause. Invented boxed continuation."


def test_next_number_in_a_table_line_is_a_problem():
    """표 안 줄이 다음 조항 번호와 소제목처럼 시작하면 조항인지 표 칸인지 추측하지 않는다."""
    lines = body(*tech_start(), line("1.2 Next heading", x0=BODY, in_table=True))
    clauses, problems, stats = reg.segment(lines, "technical")
    assert keys(clauses) == ["1", "1.1"]
    assert any("표 안 줄" in p and "(1.2)" in p for p in problems)
    assert stats["inline_numbers"] == 1


def test_sibling_number_gap_is_a_problem():
    """형제 번호가 건너뛰면(1.1 다음 1.3) 조항 하나를 앞 조항에 붙였을 수 있으므로 문제다."""
    lines = body(*tech_start(), line("1.3 Third", bold=1.0), line("1.3.2 Deeper", bold=1.0))
    _, problems, stats = reg.segment(lines, "technical")
    assert stats["number_gaps"] == 2
    gaps = [m.groups()[1:] for p in problems if (m := reg.GAP_PROBLEM.match(p))]
    assert gaps == [("1.1", "1.3"), ("1.3", "1.3.2")]


def review_row(key, pages="", rid="i99"):
    season, section, version = key
    return {
        "id": rid, "reviewed_at": "2030-01-02", "doc_type": reg.DOC_TYPES[section],
        "season": str(season), "round": "", "source_url": "", "page": pages, "target": version,
        "decision": reg.ACCEPT_SOURCE_NUMBERING, "value": "", "note": "지어낸 검수 메모",
    }  # fmt: skip


def test_verified_gaps_and_human_reviewed_numbering(monkeypatch):
    key = (2030, "technical", "2030-01-01")
    problems = [
        reg.gap_problem(5, "1.1", "1.3"),
        reg.gap_problem(6, "2.1", "2.4"),
        "7쪽: 조항 번호 순서가 어긋난다(3.2 다음 3.2)",
        "9쪽: 조항 번호 순서가 어긋난다(4.3 다음 4.3)",
        "조항 번호 3.2가 2번 나온다",
        "조항 번호 4.3가 2번 나온다",
        "8쪽: 들여 쓴 줄이 다음 조항 번호로 시작한다(3.3)",
    ]
    monkeypatch.setitem(reg.VERIFIED_GAPS, key, {("1.1", "1.3"): "invented check"})
    reviews = {key: review_row(key, "6;7")}
    kept, accepted = reg.review_problems(key, problems, reviews)
    # 검수한 쪽(6, 7)의 번호 문제와, 뺀 순서 문제의 겹친 번호(3.2)만 뺀다. 검수 밖의 쪽(9)과 번호
    # 문제가 아닌 글은 남는다.
    assert accepted == [problems[1], problems[2], problems[4]]
    assert kept == [problems[3], problems[5], problems[6]]
    # 쪽을 적지 않은 검수는 모든 쪽의 번호 문제를 뺀다.
    kept, accepted = reg.review_problems(key, problems[:6], {key: review_row(key)})
    assert kept == [] and len(accepted) == 5
    # 검수가 없는 판은 VERIFIED_GAPS만 반영한다.
    other = (2030, "sporting", "2030-01-01")
    assert reg.review_problems(other, problems, reviews) == (problems, [])
    # 적용할 번호 문제를 찾지 못한 검수는 문제로 남긴다(조용히 넘어가지 않는다).
    kept, accepted = reg.review_problems(key, [], reviews)
    assert accepted == [] and kept[0].startswith("사람 검수(2030-01-02, i99)")


def test_human_review_note_names_the_review_and_duplicate_keys():
    key = (2030, "technical", "2030-01-01")
    note = reg.review_note(review_row(key), ["15.2.3"])
    assert note.startswith("사람 검수(2030-01-02, i99): 조항 번호 문제는 FIA 원문에 찍힌 그대로다.")
    assert "지어낸 검수 메모." in note and "15.2.3#2" in note and "\u2014" not in note


def test_duplicate_clause_numbers_get_distinct_keys():
    """원문에 같은 번호가 두 번 찍히면 두 번째 조항 키에 "#2"를 붙인다. 문제는 그대로 적는다."""
    lines = tech_start() + body(
        line("1.2 First", bold=1.0), line("Some text.", x0=BODY),
        line("1.2 Second", bold=1.0), line("Other text.", x0=BODY),
        line("1.3 Third", bold=1.0), line("More text.", x0=BODY),
    )  # fmt: skip
    clauses, problems, _ = reg.segment(lines, "technical")
    keys = [c.clause_no for c in clauses]
    assert keys == ["1", "1.1", "1.2", "1.2#2", "1.3"]
    assert "조항 번호 1.2가 2번 나온다" in problems
    assert reg.number_key("1.2#2") == (1, 2) and reg.split_clause_no("A1-3.2#2") == ("A1", (3, 2))
    assert sorted(["1.3", "1.2#2", "1.2"], key=reg.clause_sort_key) == ["1.2", "1.2#2", "1.3"]
    # 짝짓기는 키가 겹치지 않아 두 조항을 따로 본다.
    old = [c for c in clauses if c.clause_no != "1.2#2"]
    rows, counts = reg.compare(old, clauses)
    assert [(r["clause_no"], r["change"]) for r in rows] == [("1.2#2", "added")]


def test_number_font_ratio_catches_pasted_paragraph():
    """조항 번호 9pt 뒤에 10pt 본문이 오는 줄(2023년 기술 규정 Issue 5의 2.9.2)도 번호
    글꼴로 본다. 본문과 같은 크기로 찍힌 상호 참조는 번호 글꼴이 아니다."""
    assert reg.NUMBER_SIZE_RATIO * 10.0 > 9.0
    assert reg.NUMBER_SIZE_RATIO * 11.0 <= 11.0
    lines = tech_start() + body(
        line("1.2 Planes", bold=1.0),
        line("1.2.1 Reference plane: text.", small_number=True),
        line("more text.", x0=BODY),
        line("1.2.2 Centre plane: text.", x0=MARGIN + 14.2, small_number=True),
        line("1.2.3 Plane A-A: text.", small_number=True),
    )  # fmt: skip
    clauses, problems, _ = reg.segment(lines, "technical")
    assert [c.clause_no for c in clauses] == ["1", "1.1", "1.2", "1.2.1", "1.2.2", "1.2.3"]
    assert problems == []


def test_numbering_reviews_come_from_human_review_csv():
    """human_review.csv의 accept_source_numbering 행 11개가 판 키로 읽힌다."""
    reviews = reg.numbering_reviews()
    assert sorted((k, r["id"]) for k, r in reviews.items()) == sorted(HUMAN_REVIEWED.items())


def test_unbold_appendix_section_is_a_clause_only_with_its_first_subclause():
    """굵지 않게 찍힌 부록 소제목(2022년 기술 규정 Issue 11 부록 1 16)은 다음 번호이고 바로 뒤
    여백 열 번호가 그 첫 하위 번호일 때만 조항이다."""
    head = [*tech_start(), line("APPENDIX 1: VOLUMES", bold=1.0),
            line("1 Invented Volume", bold=1.0), line("1.1 Invented text.")]  # fmt: skip
    lines = body(*head, line("2 Invented Plain Volume"), line("Invented intro.", x0=BODY),
                 line("2.1 Invented text."))  # fmt: skip
    clauses, problems, stats = reg.segment(lines, "technical")
    assert problems == [] and stats["plain_sections"] == 1
    assert keys(clauses)[-2:] == ["A1-2", "A1-2.1"]
    assert clauses[-2].heading == "Invented Plain Volume" and clauses[-2].text == "Invented intro."
    lines = body(*head, line("2 Invented Plain Volume"), line("3.1 Invented text."))
    clauses, problems, stats = reg.segment(lines, "technical")
    assert stats["plain_sections"] == 0 and "A1-2" not in keys(clauses)
    gaps = [m.groups()[1:] for p in problems if (m := reg.GAP_PROBLEM.match(p))]
    assert gaps == [("A1-1", "A1-3")]  # 조항 A1-3.1의 상위 번호 A1-3도 형제 검사에 든다


def test_rotated_header_text_is_part_of_the_table_row():
    """돌려 찍은 표 머리 글자도 행 글에 들어가야 표 머리가 바뀐 판을 변경으로 잡는다."""
    table = FakeTable([[(100, 100, 300, 160), (300, 100, 400, 160)],
                       [(100, 160, 300, 200), (300, 160, 400, 200)]])  # fmt: skip
    turned = [{**g, "upright": False} for g in word("No", 310, 110)]
    for g, top in zip(turned, (140, 130), strict=True):
        g.update(x0=310, x1=320, top=top, bottom=top + 10)
    chars = word("Item", 105, 120) + word("Value", 105, 170)
    rows, rest = reg.table_rows([table], chars, FakePage(), turned)
    assert [r["text"] for r in rows] == ["Item No", "Value"] and rest == []
    assert rows[0]["rotated"] == turned


def test_picture_is_a_header_logo_only_inside_the_top_band():
    height = 800
    assert reg.is_band_picture({"top": 10, "bottom": 60}, height)
    assert not reg.is_band_picture({"top": 40, "bottom": 400}, height)  # 본문으로 내려온다
    assert reg.is_band_picture({"top": 720, "bottom": 780}, height)
    assert not reg.is_band_picture({"top": 300, "bottom": 500}, height)


def doc_row(season, section, version, status, issue=""):
    return {
        "season": season, "section": section, "version_date": version, "variant": "",
        "issue": issue, "version_key": version, "status": status, "url": f"u/{version}",
    }  # fmt: skip


def test_version_pairs_skip_unparsed_versions():
    """needs_review 판을 사이에 둔 두 파싱된 판도 비교하고, 건너뛴 판을 적는다."""
    rows = [
        doc_row("2030", "technical", "2029-01-01", "ok", "1"),
        doc_row("2030", "technical", "2029-06-01", "needs_review", "2"),
        doc_row("2030", "technical", "2030-01-01", "ok", "3"),
        doc_row("2030", "technical", "2030-06-01", "needs_review", "4"),
        doc_row("2031", "technical", "2030-07-01", "ok", "1"),
    ]
    parsed = {reg.doc_key(r): object() for r in rows if r["status"] == "ok"}
    got = [(k, a["version_date"], b["version_date"], s) for k, a, b, s in
           reg.version_pairs(rows, parsed)]  # fmt: skip
    assert got == [
        ("issue", "2029-01-01", "2030-01-01", ["2030:2029-06-01"]),
        ("season", "2030-01-01", "2030-07-01", ["2030:2030-06-01"]),
    ]  # fmt: skip


def test_version_pairs_list_unparsed_versions_before_and_after_the_chain():
    """시즌의 첫 파싱된 판 앞과 마지막 파싱된 판 뒤의 판도 어느 비교의 건너뛴 판에 나온다.

    앞 판은 그 시즌으로 들어오는 season 비교에, 그 비교가 없으면 첫 issue 비교에 적는다. 뒤 판은
    나가는 season 비교에, 그 비교가 없으면 마지막 issue 비교에 적는다(2022년 기술 규정 Issue
    1-6, 2025년 스포팅 규정 Issue 5).
    """
    rows = [
        doc_row("2030", "technical", "2029-01-01", "needs_review", "1"),
        doc_row("2030", "technical", "2029-06-01", "ok", "2"),
        doc_row("2030", "technical", "2030-01-01", "ok", "3"),
        doc_row("2031", "technical", "2030-03-01", "not_downloaded", "1"),
        doc_row("2031", "technical", "2030-07-01", "ok", "2"),
        doc_row("2031", "technical", "2031-01-01", "ok", "3"),
        doc_row("2031", "technical", "2031-06-01", "needs_review", "4"),
    ]
    parsed = {reg.doc_key(r): object() for r in rows if r["status"] == "ok"}
    got = [(k, a["version_date"], b["version_date"], s) for k, a, b, s in
           reg.version_pairs(rows, parsed)]  # fmt: skip
    assert got == [
        ("issue", "2029-06-01", "2030-01-01", ["2030:2029-01-01"]),
        ("season", "2030-01-01", "2031-01-01", ["2031:2030-03-01", "2031:2031-06-01"]),
        ("issue", "2030-07-01", "2031-01-01", ["2031:2031-06-01"]),
    ]  # fmt: skip


def test_shrinking_the_curated_tables_is_refused():
    previous = [doc_row("2030", "technical", "2030-01-01", "ok"),
                doc_row("2030", "sporting", "2030-01-01", "ok")]  # fmt: skip
    current = [doc_row(2030, "technical", "2030-01-01", "ok"),
               doc_row(2030, "sporting", "2030-01-01", "not_downloaded")]  # fmt: skip
    with pytest.raises(reg.ShrinkError, match="2030 sporting 2030-01-01"):
        reg.check_shrink(previous, current)
    reg.check_shrink(previous, current, allow_shrink=True)
    reg.check_shrink(previous, [{**current[1], "status": "ok"}, current[0]])
    review = [current[0], {**current[1], "status": "needs_review"}]
    reg.check_shrink(previous, review)  # 파서 검사로 needs_review가 되는 것은 막지 않는다
    nothing = [{**d, "status": "not_downloaded"} for d in current]
    for allow in (False, True):
        with pytest.raises(reg.ShrinkError, match="하나도 없어"):
            reg.check_shrink([], nothing, allow_shrink=allow)


def test_build_without_cached_sources_writes_nothing(monkeypatch, tmp_path):
    """원문 캐시가 빈 저장소(새로 받은 저장소, CI 캐시 없음)에서 --cached로 돌려도 커밋된 정제
    테이블과 실패 목록을 빈 표로 덮어쓰지 않는다."""
    targets = [OUT / name for name in OWN_FILES] + [manifest.MANIFEST_DIR / "parse_failures.csv"]
    before = {p: p.read_bytes() for p in targets if p.exists()}
    monkeypatch.setattr(fia_regulations, "local_path", lambda row: tmp_path / "absent.pdf")
    with pytest.raises(reg.ShrinkError):
        reg.build(only_cached=True)
    with pytest.raises(reg.ShrinkError):
        reg.build(only_cached=True, allow_shrink=True)
    assert {p: p.read_bytes() for p in targets if p.exists()} == before


def test_cache_key_covers_parser_source_and_pdfplumber():
    key = reg.cache_key()
    assert reg.PARSER_VERSION in key and pdfplumber.__version__ in key
    source = reg.hashlib.sha256(reg.Path(reg.__file__).read_bytes()).hexdigest()
    assert key.endswith(source)


# --- 정제 테이블 ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def documents():
    frame = pd.read_csv(
        OUT / "documents.csv",
        dtype={"issue": str, "variant": str, "version_key": str, "pdf_sha256": str,
               "problems": str, "review_note": str},
    )  # fmt: skip
    return frame.fillna(
        {"issue": "", "variant": "", "problems": "", "review_note": "", "pdf_sha256": "",
         "sha256_check": ""}
    )  # fmt: skip


@pytest.fixture(scope="module")
def articles():
    return pd.read_parquet(OUT / "articles.parquet")


@pytest.fixture(scope="module")
def changes():
    return pd.read_parquet(OUT / "changes.parquet")


@pytest.fixture(scope="module")
def comparisons():
    frame = pd.read_csv(
        OUT / "comparisons.csv",
        dtype={"from_version": str, "to_version": str, "skipped_versions": str},
    )
    return frame.fillna({"skipped_versions": ""})


def manifest_rows():
    return [
        r
        for r in manifest.read_rows(fia_regulations.MANIFEST)
        if r["section"] in fia_regulations.PARSED_SECTIONS
    ]


def test_documents_cover_the_manifest(documents):
    rows = manifest_rows()
    assert len(documents) == len(rows)
    assert set(documents["url"]) == {r["url"] for r in rows}
    assert set(documents["status"]) <= {"ok", "needs_review", "not_downloaded"}
    assert not documents.duplicated(["season", "section", "version_key"]).any()
    waiting = documents[documents["status"] == "not_downloaded"]
    assert waiting["clauses"].isna().all() and (waiting["problems"] == "").all()
    review = documents[documents["status"] == "needs_review"]
    assert (review["problems"] != "").all()


def test_documents_record_the_parsed_pdf_sha256(documents):
    """파싱한 원문의 sha256을 적고 manifest의 값과 맞춰 본다. 다르면 문제다."""
    manifest_sha = {r["url"]: r["sha256"] for r in manifest_rows()}
    read = documents[documents["status"] != "not_downloaded"]
    assert read["pdf_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert set(read["sha256_check"]) <= {"match", "differs", "manifest_missing"}
    for row in read.itertuples():
        expected = manifest_sha[row.url]
        if not expected:
            assert row.sha256_check == "manifest_missing"
        elif expected == row.pdf_sha256:
            assert row.sha256_check == "match"
        else:
            assert row.sha256_check == "differs" and row.status == "needs_review"
            assert "sha256" in row.problems
    waiting = documents[documents["status"] == "not_downloaded"]
    assert (waiting["pdf_sha256"] == "").all()


def test_number_checks_are_recorded(documents):
    """번호 검사 셈(형제 번호 건너뜀, 줄 머리 숫자, 굵지 않은 소제목)이 문서마다 남는다."""
    read = documents[documents["status"] != "not_downloaded"]
    for name in ("number_gaps", "inline_numbers", "plain_headings", "plain_sections"):
        assert name in documents.columns and read[name].notna().all(), name


def test_ok_documents_have_a_plausible_number_of_clauses(documents):
    ok = documents[documents["status"] == "ok"]
    assert len(ok) >= 15
    bounds = {"technical": (450, 1400), "sporting": (300, 650)}
    for row in ok.itertuples():
        low, high = bounds[row.section]
        assert low <= row.clauses <= high, (row.season, row.section, row.version_key)
        assert row.characters > 150_000


def test_failures_match_documents_needing_review(documents):
    failures = [
        r
        for r in manifest.read_rows("parse_failures.csv")
        if r["doc_type"].startswith("regulation_")
    ]
    review = documents[documents["status"] == "needs_review"]
    assert {r["url"] for r in failures} == set(review["url"])
    assert {r["doc_type"] for r in failures} <= set(reg.DOC_TYPES.values())
    every = manifest.read_rows("parse_failures.csv")
    # 어느 파서가 마지막에 써도 같은 순서다
    assert every == sorted(every, key=manifest._failure_order)


def test_write_failures_uses_shared_locked_helper(tmp_path, monkeypatch):
    """규정 파서도 manifest.replace_failures로 쓴다. 잠금을 두 번 잡지 않으므로 멈추지 않는다."""
    monkeypatch.setattr(manifest, "MANIFEST_DIR", tmp_path / "manifests")
    monkeypatch.setattr(manifest, "RAW_DIR", tmp_path / "raw")
    fields = manifest.FAILURE_FIELDS

    def failure(doc_type, season, url, day):
        return dict(zip(fields, [season, "", "", doc_type, url, "p", day], strict=True))

    manifest.write_rows(manifest.FAILURES, [
        failure("regulation_sporting", 2025, "s", "2026-01-01"),
        failure("pu_used", 2025, "u", "2026-01-02"),
    ], fields)  # fmt: skip
    calls = []
    real = manifest.replace_failures
    monkeypatch.setattr(
        manifest, "replace_failures", lambda types, rows: calls.append(types) or real(types, rows)
    )
    reg.write_failures([
        failure("regulation_technical", 2024, "t", "2026-02-02"),
        failure("regulation_sporting", 2025, "s", "2026-02-02"),
    ])  # fmt: skip
    assert calls == [set(reg.DOC_TYPES.values())]
    got = [
        (r["doc_type"], r["url"], r["recorded_at"]) for r in manifest.read_rows(manifest.FAILURES)
    ]
    assert got == [
        ("pu_used", "u", "2026-01-02"),  # 다른 파서의 행은 남는다
        ("regulation_sporting", "s", "2026-01-01"),  # 처음 기록한 날짜를 유지한다
        ("regulation_technical", "t", "2026-02-02"),
    ]


def test_articles_keys_values_and_order(articles, documents):
    assert not articles.duplicated(["season", "section", "version_key", "clause_no"]).any()
    ok = documents[documents["status"] == "ok"][["season", "section", "version_key"]]
    parsed = articles[["season", "section", "version_key"]].drop_duplicates()
    assert len(parsed.merge(ok)) == len(parsed) == len(ok)
    assert articles["text_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert (articles["char_count"] >= 0).all() and (articles["page"] >= 1).all()
    reviews = reg.numbering_reviews()
    for key, doc in articles.groupby(["season", "section", "version_key"], sort=False):
        order = [reg.clause_sort_key(k) for k in doc["clause_no"]]
        assert len(set(order)) == len(order)
        # 사람이 원문 번호 오류로 확인한 판은 원문에 찍힌 순서 그대로다(2021년 기술 규정 Issue 2의
        # 5.25.2 다음 5.23.3, 2022년 기술 규정 Issue 6의 8.18 다음 8.17).
        if key not in reviews:
            assert order == sorted(order), key
        pages = list(doc["page"])
        assert pages == sorted(pages)
        for row in doc.itertuples():
            if row.clause_no.startswith("A"):
                rest = row.clause_no.partition("-")[2]
                assert row.level == (rest.count(".") + 2 if rest else 1)
                assert row.top_article == row.clause_no.partition("-")[0]
            else:
                assert row.level == row.clause_no.count(".") + 1
                assert row.top_article == row.clause_no.split(".")[0]


def test_every_ok_document_has_articles_from_one(articles):
    for (_, section, _), doc in articles.groupby(["season", "section", "version_key"]):
        tops = [int(k) for k in doc.loc[doc["level"] == 1, "clause_no"] if not k.startswith("A")]
        assert tops == list(range(1, len(tops) + 1))
        # 스포팅 규정 초기 판(2022년 규정 Issue 1-3)은 기술 규정 양식(10개 조, 세 단계 번호)이다.
        body_levels = set(doc.loc[~doc["clause_no"].str.startswith("A"), "level"])
        technical_style = section == "technical" or 3 in body_levels
        assert len(tops) >= (10 if technical_style else 45)
        if section == "technical":
            assert len(tops) >= 17


def live(articles, season, section, version):
    doc = articles[
        (articles["season"] == season)
        & (articles["section"] == section)
        & (articles["version_key"] == version)
    ]
    return doc[~doc["not_used"]].set_index("clause_no")


PAIR = ["kind", "section", "from_season", "from_version", "to_season", "to_version"]


def pair_rows(changes, key):
    return changes[(changes[PAIR] == pd.Series(dict(zip(PAIR, key, strict=True)))).all(axis=1)]


def test_changes_are_consistent_with_articles(articles, changes, comparisons):
    """변경 행이 두 판의 조항 목록과 맞는다.

    옛 판의 살아 있는 조항은 정확히 한 번, 변경 없음(같은 번호, 같은 소제목과 해시, 행 없음)이거나
    removed, modified 행의 from_clause_no로 나온다. 새 판도 같은 방식으로 한 번씩 나온다(added,
    modified 행의 clause_no). 번호가 바뀐 modified 행은 renumbered가 참이다.
    """
    assert set(changes["kind"]) <= {"issue", "season"}
    assert set(changes["change"]) <= {"added", "removed", "modified"}
    assert (
        (changes["renumbered"] == (changes["clause_no"] != changes["from_clause_no"]))
        .loc[changes["change"] == "modified"]
        .all()
    )
    assert not changes.loc[changes["change"] != "modified", "renumbered"].any()
    modified = changes[changes["change"] == "modified"]
    assert modified["similarity"].between(0, 1).all()
    assert changes.loc[changes["change"] != "modified", "similarity"].isna().all()
    assert not changes.loc[changes["change"] != "modified", "images_changed"].any()
    for key, comp in comparisons.set_index(PAIR).iterrows():
        _, section, fs, fv, ts, tv = key
        a, b = live(articles, fs, section, fv), live(articles, ts, section, tv)
        rows = pair_rows(changes, key)
        assert not rows.duplicated(["clause_no", "from_clause_no"]).any(), key
        olds = rows.loc[rows["change"] != "added", "from_clause_no"]
        news = rows.loc[rows["change"] != "removed", "clause_no"]
        assert olds.is_unique and news.is_unique, key
        assert set(olds) <= set(a.index) and set(news) <= set(b.index), key
        untouched_old, untouched_new = set(a.index) - set(olds), set(b.index) - set(news)
        assert untouched_old == untouched_new, key  # 변경 없는 조항은 같은 번호로 양쪽에 있다
        for no in untouched_old:
            assert (a.at[no, "text_sha256"], a.at[no, "heading"]) == (
                b.at[no, "text_sha256"],
                b.at[no, "heading"],
            ), (key, no)
        for row in rows.itertuples():
            if row.change != "added":
                assert row.chars_from == a.at[row.from_clause_no, "char_count"]
                assert row.page_from == a.at[row.from_clause_no, "page"]
            if row.change != "removed":
                assert row.chars_to == b.at[row.clause_no, "char_count"]
                assert row.page_to == b.at[row.clause_no, "page"]
            if row.change == "removed":
                assert row.clause_no == row.from_clause_no
            same_text = row.change == "modified" and (
                a.at[row.from_clause_no, "text_sha256"],
                a.at[row.from_clause_no, "heading"],
            ) == (b.at[row.clause_no, "text_sha256"], b.at[row.clause_no, "heading"])
            if same_text and not row.images_changed:
                assert row.renumbered and row.similarity == 1.0  # 번호만 바뀌었다
            if row.change == "modified" and not row.images_changed and not row.renumbered:
                old, new = a.loc[row.from_clause_no], b.loc[row.clause_no]
                assert (old["text_sha256"], old["heading"]) != (new["text_sha256"], new["heading"])
        assert comp["clauses_from"] == len(a) and comp["clauses_to"] == len(b)


def test_comparison_totals_add_up(comparisons, changes):
    c = comparisons
    moved = c["unchanged"] + c["modified"]
    assert (c["clauses_from"] == moved + c["removed"]).all()
    assert (c["clauses_to"] == moved + c["added"]).all()
    counted = changes.groupby([*PAIR, "change"]).size().unstack(fill_value=0)
    merged = c.set_index(PAIR)
    for name in ("added", "removed", "modified"):
        if name in counted.columns:
            got = counted[name].reindex(merged.index, fill_value=0)
        else:
            got = pd.Series(0, index=merged.index)
        assert (merged[name] == got).all(), name
    assert not c.duplicated(PAIR).any()
    moved = changes[changes["renumbered"]].groupby(PAIR).size()
    assert (merged["renumbered"] == moved.reindex(merged.index, fill_value=0)).all()


def change_of(changes, section, season, clause_no=None, from_clause_no=None):
    """season -> season + 1 시즌 비교에서 한 조항의 변경 행. 비교가 없으면 None."""
    rows = changes[
        (changes["kind"] == "season")
        & (changes["section"] == section)
        & (changes["from_season"] == season)
    ]
    if rows.empty:
        return None
    if clause_no is not None:
        rows = rows[rows["clause_no"] == clause_no]
    if from_clause_no is not None:
        rows = rows[rows["from_clause_no"] == from_clause_no]
    return rows


def need(rows):
    if rows is None:
        pytest.skip("이 시즌 비교가 아직 없다")
    return rows


def test_known_renumberings_are_followed(changes):
    """검증에서 번호만 바뀐 것으로 확인한 조항(렌더링한 쪽에서 글이 같음)."""
    cases = [
        ("technical", 2018, "21.5", "21.4"),  # Installation
        ("technical", 2018, "11.5.1", "11.7.1"),
        ("technical", 2019, "5.1.12", "5.1.13"),
        ("technical", 2020, "1.34", "1.43"),  # PU-CE 정의
        ("sporting", 2018, "22.16", "22.17"),  # 2019년 판에서 분홍 번호
        ("sporting", 2018, "A8-2.8", "A8-2.9"),
        ("sporting", 2020, "39.5", "48.5"),
        ("sporting", 2020, "45.1", "55.1"),
    ]
    for section, season, old, new in cases:
        rows = need(change_of(changes, section, season, from_clause_no=old))
        got = list(zip(rows["clause_no"], rows["change"], rows["similarity"], strict=True))
        assert got == [(new, "modified", 1.0)], (section, season, old)
        assert rows["renumbered"].all()


def test_shifted_article_is_not_paired_by_number(changes):
    """2021년 스포팅 규정 39조(EXTRA FORMATION LAP)는 2020년 39조(SAFETY CAR)의 수정이 아니다."""
    rows = need(change_of(changes, "sporting", 2020, clause_no="39.1"))
    assert list(rows["change"]) == ["added"]
    moved = need(change_of(changes, "sporting", 2020, from_clause_no="39.1"))
    assert list(moved["clause_no"]) == ["48.1"]


def test_layout_only_differences_are_not_changes(changes):
    """인쇄면이 같은데 추출 순서만 달랐던 조항(아래첨자, 표 칸 줄바꿈, 줄 끝 하이픈)."""
    cases = [
        ("technical", 2018, ["A2", "16.4"]),
        ("technical", 2019, ["14.4"]),
        ("technical", 2022, ["A1-9.1", "2.11.3", "16.4.1", "3.5.2", "12.2.2", "A1-10.1"]),
        ("technical", 2024, ["A1-41.1", "13.7.2", "A3"]),
    ]
    for section, season, keys in cases:
        rows = need(change_of(changes, section, season))
        assert not set(keys) & set(rows["clause_no"]), (section, season)


def test_changed_picture_is_reported(changes):
    """2021년 기술 규정 부록 3은 글 없는 그림인데 그림이 바뀌었다."""
    rows = need(change_of(changes, "technical", 2020, clause_no="A3"))
    assert list(zip(rows["change"], rows["images_changed"], strict=True)) == [("modified", True)]


def latest_articles(articles, documents, season, section):
    ok = documents[
        (documents["status"] == "ok")
        & (documents["season"] == season)
        & (documents["section"] == section)
    ]
    if ok.empty:
        pytest.skip("파싱된 판이 없다")
    version = sorted(ok.to_dict("records"), key=reg.version_order)[-1]["version_key"]
    doc = articles[
        (articles["season"] == season)
        & (articles["section"] == section)
        & (articles["version_key"] == version)
    ]
    return doc.set_index("clause_no")


def test_known_headings_and_flags(articles, documents):
    """검증에서 렌더링한 쪽으로 확인한 소제목과 효력 없음 표시."""
    t23 = latest_articles(articles, documents, 2023, "technical")
    assert t23.at["12.5.2", "heading"] == "Helmet Position"
    s23 = latest_articles(articles, documents, 2023, "sporting")
    assert s23.at["30.1", "heading"] == "Supply of tyres"
    assert s23.at["10.6", "heading"].startswith("Safety and Technical Requirements")
    s21 = latest_articles(articles, documents, 2021, "sporting")
    assert s21.at["A6", "not_used"]
    assert s21.at["A4", "top_title"] == "2020-2025 POWER UNIT HOMOLOGATION"
    assert "ENTRY FORM" in s21.at["A2", "top_title"]
    s19 = latest_articles(articles, documents, 2019, "sporting")
    assert s19.at["47.1", "heading"] == "Changes to Article 21.7"
    lengths = {
        latest_articles(articles, documents, season, "technical").at["A1-20.2", "char_count"]
        for season in (2023, 2024, 2025)
    }
    assert len(lengths) == 1  # 쪽 맨 위 값 "325"가 세 판 모두 들어 있다


def article_at(articles, season, section, version, clause_no):
    doc = articles[
        (articles["season"] == season)
        & (articles["section"] == section)
        & (articles["version_key"] == version)
        & (articles["clause_no"] == clause_no)
    ]
    if doc.empty:
        pytest.skip(f"{season} {section} {version} {clause_no}가 정제 데이터에 없다")
    return doc.iloc[0]


def test_struck_headings_do_not_leak_into_the_previous_clause(articles):
    """취소선으로 지운 조·부록 제목 아래의 지우지 않은 알림 글은 효력 없는 조항이 되고 앞 조항에
    붙지 않는다(렌더링한 쪽에서 제목만 지워진 것을 확인한 네 판). 그래서 앞 조항의 해시가 이웃 판과
    같다."""
    cases = [
        # (시즌, 구분, 지운 제목이 있는 판, 지운 조·부록, 앞 조항, 앞 조항이 같아야 할 판)
        (2021, "sporting", "2020-05-27", ["A6"], "A5", "2020-10-30"),
        (2021, "sporting", "2020-06-19", ["A6"], "A5", "2020-10-30"),
        (2022, "sporting", "2022-07-19", ["A9", "A10"], "A8-2", "2022-10-19"),
        (2022, "technical", "2022-02-18", ["18"], "17.7", "2022-03-17"),
    ]
    for season, section, version, gone, before, neighbour in cases:
        for no in gone:
            row = article_at(articles, season, section, version, no)
            assert row["struck"] and row["not_used"], (season, section, version, no)
        mine = article_at(articles, season, section, version, before)
        other = article_at(articles, season, section, neighbour, before)
        assert mine["text_sha256"] == other["text_sha256"], (season, section, version, before)
    assert (
        article_at(articles, 2022, "technical", "2021-10-15", "17.7")["text_sha256"]
        == article_at(articles, 2022, "technical", "2022-02-18", "17.7")["text_sha256"]
    )
    assert not articles.loc[articles["struck"], "not_used"].eq(False).any()


def test_wrapped_appendix_titles_are_whole(articles):
    """왼쪽 맞춤으로 25.7pt 아래에 이어진 부록 제목 둘째 줄과 셋째 제목 줄이 제목에 들어 있다."""
    cases = [
        (2021, "sporting", "2019-10-31", "A3", "INFORMATION REQUIRED BY THE FIA 90 DAYS BEFORE A "
         "COMPETITION"),
        (2021, "sporting", "2019-10-31", "A4", "SUPPLY OF POWER UNITS FOR THE 2021-2025 "
         "CHAMPIONSHIP SEASONS"),
        (2021, "sporting", "2019-10-31", "A5", "FEDERATION INTERNATIONALE DE L'AUTOMOBILE "
         "COMPETITOR'S STAFF REGISTRATION FORM FOR THE FIA FORMULA ONE WORLD CHAMPIONSHIP"),
        (2022, "sporting", "2020-05-27", "A6", "SUPPLY OF POWER UNITS FOR THE 2021-2025 "
         "CHAMPIONSHIP SEASONS"),
    ]  # fmt: skip
    for season, section, version, no, title in cases:
        assert article_at(articles, season, section, version, no)["top_title"] == title


def ordered_series(documents, season, section):
    series = documents[(documents["season"] == season) & (documents["section"] == section)]
    return sorted(series.to_dict("records"), key=reg.version_order)


def edges(documents, season, section) -> tuple[list[str], list[str]]:
    """시즌의 첫 ok 판 앞의 판과 마지막 ok 판 뒤의 판("시즌:판 키")."""
    order = ordered_series(documents, season, section)
    ok = [i for i, r in enumerate(order) if r["status"] == "ok"]
    if not ok:
        return [], []
    label = [f"{season}:{r['version_key']}" for r in order]
    return label[: ok[0]], label[ok[-1] + 1 :]


def test_pairs_follow_the_version_order(comparisons, documents):
    """issue 비교는 같은 시즌의 이웃한 ok 판끼리이고, 그 사이 판은 모두 skipped_versions에 있다.
    season 비교는 이웃 시즌의 마지막 ok 판끼리이고, 앞 시즌의 마지막 ok 판 뒤의 판, 뒤 시즌의 첫
    ok 판 앞의 판과 마지막 ok 판 뒤의 판이 skipped_versions에 있다. season 비교가 없는 쪽의 앞
    판·뒤 판은 그 시즌의 첫·마지막 issue 비교에 있다."""
    seasons = set(
        zip(comparisons.loc[comparisons["kind"] == "season", "section"],
            comparisons.loc[comparisons["kind"] == "season", "from_season"], strict=True)
    )  # fmt: skip
    for row in comparisons.itertuples():
        skipped = [v for v in row.skipped_versions.split(";") if v]
        if row.kind == "issue":
            assert row.from_season == row.to_season
            order = ordered_series(documents, row.from_season, row.section)
            versions = [r["version_key"] for r in order]
            ok = [i for i, r in enumerate(order) if r["status"] == "ok"]
            i, j = versions.index(row.from_version), versions.index(row.to_version)
            between = order[i + 1 : j]
            assert j > i and all(r["status"] != "ok" for r in between)
            assert ok.index(j) == ok.index(i) + 1
            lead, trail = edges(documents, row.from_season, row.section)
            expected = [f"{row.from_season}:{r['version_key']}" for r in between]
            if i == ok[0] and (row.section, row.from_season - 1) not in seasons:
                expected = lead + expected
            if j == ok[-1] and (row.section, row.from_season) not in seasons:
                expected = expected + trail
            assert skipped == expected, row
        else:
            assert row.to_season == row.from_season + 1
            for season, version in ((row.from_season, row.from_version),
                                    (row.to_season, row.to_version)):  # fmt: skip
                order = ordered_series(documents, season, row.section)
                ok = [r["version_key"] for r in order if r["status"] == "ok"]
                assert ok[-1] == version
            _, from_trail = edges(documents, row.from_season, row.section)
            to_lead, to_trail = edges(documents, row.to_season, row.section)
            assert skipped == from_trail + to_lead + to_trail, row


def test_every_consecutive_parsed_pair_is_compared(comparisons, documents):
    """사이에 needs_review 판이 있어도 이웃한 ok 판의 비교가 빠지지 않는다."""
    have = set(
        zip(comparisons["kind"], comparisons["section"], comparisons["from_season"],
            comparisons["from_version"], comparisons["to_version"], strict=True)
    )  # fmt: skip
    for (season, section), _ in documents.groupby(["season", "section"]):
        ok = [r["version_key"] for r in ordered_series(documents, season, section)
              if r["status"] == "ok"]  # fmt: skip
        for a, b in zip(ok, ok[1:], strict=False):
            assert ("issue", section, season, a, b) in have, (season, section, a, b)
        nxt = [r["version_key"] for r in ordered_series(documents, season + 1, section)
               if r["status"] == "ok"]  # fmt: skip
        if ok and nxt:
            assert ("season", section, season, ok[-1], nxt[-1]) in have, (season, section)


def test_every_unparsed_version_is_listed_as_skipped(comparisons, documents):
    """비교가 하나라도 걸린 시즌이면, 그 시즌의 needs_review·not_downloaded 판은 모두 어느 비교의
    skipped_versions에 나온다. 첫 ok 판 앞의 판(2022년 기술 규정 Issue 1-6)과 마지막 ok 판 뒤의 판
    (2025년 스포팅 규정 Issue 5)도 빠지지 않는다."""
    listed = {v for value in comparisons["skipped_versions"] for v in value.split(";") if v}
    involved = set()
    for row in comparisons.itertuples():
        involved |= {(row.section, row.from_season), (row.section, row.to_season)}
    checked = 0
    for (season, section), _ in documents.groupby(["season", "section"]):
        if (section, season) not in involved:
            continue
        for r in ordered_series(documents, season, section):
            if r["status"] != "ok":
                assert f"{season}:{r['version_key']}" in listed, (season, section, r["version_key"])
                checked += 1
    # 2026-11-13 사람 검수 뒤로는 파싱되지 않은 판이 없어 셀 판이 없을 수 있다.
    assert checked == len(listed)


def test_sibling_numbers_are_continuous_in_ok_documents(articles):
    """ok 문서의 형제 번호는 1부터 이어진다. 원문에서 확인한 건너뜀(VERIFIED_GAPS)과 사람이 원문
    오류로 확인한 쪽의 건너뜀(human_review.csv)만 예외다."""
    reviews = reg.numbering_reviews()
    for (season, section, version), doc in articles.groupby(["season", "section", "version_key"]):
        clauses = [reg.Clause(r.clause_no, "", 0, r.page, "", "", "") for r in doc.itertuples()]
        gaps = [reg.gap_problem(*gap) for gap in reg.sibling_gaps(clauses)]
        kept, _ = reg.review_problems((season, section, version), gaps, reviews)
        assert all(p.startswith("사람 검수(") for p in kept), (season, section, version, kept)


def failure_urls():
    return {
        r["url"]
        for r in manifest.read_rows("parse_failures.csv")
        if r["doc_type"].startswith("regulation_")
    }


def check_fact_sources(facts, documents, section=None):
    """사실 행의 판이 그 시즌의 마지막 ok 판이고, is_final_issue가 문서 목록과 맞는다."""
    for row in facts.itertuples():
        sec = section or row.section
        order = ordered_series(documents, row.season, sec)
        ok = [r for r in order if r["status"] == "ok"]
        assert ok and ok[-1]["version_key"] == row.version_key and ok[-1]["url"] == row.url
        final = order[-1]
        assert bool(row.is_final_issue) == (final["version_key"] == row.version_key)
        if not row.is_final_issue:
            assert final["status"] != "ok"


def check_quote_sources(facts, articles, section=None):
    """파싱 캐시 없이 하는 인용 근거 검사. 사실 행의 text_sha256이 그 판 그 조항의 해시와 같고,
    인용 자리(quote_start부터 인용 길이)가 조항 글 길이 안에 있다. 인용이 조항 글의 일부를 그대로
    옮겼는지는 파싱 캐시가 있을 때 test_quotes_are_substrings_of_their_clause가 본다."""
    index = articles.set_index(["season", "section", "version_key", "clause_no"])
    assert len(facts)
    for row in facts.itertuples():
        found = index.loc[(row.season, section or row.section, row.version_key, row.clause_no)]
        assert found["text_sha256"] == row.text_sha256, (row.season, row.clause_no)
        assert row.quote_start >= 0
        assert row.quote_start + len(row.quote) <= found["char_count"], (row.season, row.clause_no)


def test_pu_allocation_rules(articles, documents):
    pu = pd.read_csv(OUT / "pu_allocation_rules.csv", dtype={"clause_no": str, "version_key": str})
    assert list(pu.columns) == reg.PU_COLUMNS
    assert set(pu["season"]) <= set(range(2020, 2026))
    assert set(pu["element"]) <= {"ICE", "TC", "MGU-H", "MGU-K", "ES", "CE", "EX"}
    assert not pu.duplicated(["season", "element"]).any()
    assert pu["allowed"].between(1, 10).all()
    assert (pu["quote"].str.len() <= reg.QUOTE_LIMIT).all()
    check_fact_sources(pu, documents, "sporting")
    check_quote_sources(pu, articles, "sporting")
    for row in pu.itertuples():
        assert row.element in row.quote or row.element == "EX"
        doc = documents[documents["url"] == row.url].iloc[0]
        assert (
            doc["status"] == "ok" and doc["section"] == "sporting" and doc["season"] == row.season
        )
        found = articles[
            (articles["version_key"] == doc["version_key"])
            & (articles["section"] == "sporting")
            & (articles["season"] == row.season)
            & (articles["clause_no"] == row.clause_no)
        ]
        assert len(found) == 1 and found["page"].iloc[0] <= row.page <= found["page"].iloc[0] + 2
    # 확인된 값(docs/methodology.md): 2020-2022 시즌 ICE 3기, 2023-2025 시즌 4기
    ice = pu[pu["element"] == "ICE"].set_index("season")["allowed"].to_dict()
    for season, value in {2020: 3, 2021: 3, 2022: 3, 2023: 4, 2024: 4, 2025: 4}.items():
        if season in ice:
            assert ice[season] == value


def test_pu_allocation_covers_every_season(documents):
    """2020-2025 모든 시즌에 ICE 행이 있다. 예외는 그 시즌의 스포팅 규정에 ok 판이 하나도 없고
    마지막 판이 needs_review로 실패 목록에 있는 시즌뿐이다."""
    pu = pd.read_csv(OUT / "pu_allocation_rules.csv")
    failed = failure_urls()
    for season in reg.PU_SEASONS:
        if ((pu["season"] == season) & (pu["element"] == "ICE")).any():
            continue
        order = ordered_series(documents, season, "sporting")
        assert order and not any(r["status"] == "ok" for r in order), season
        assert order[-1]["status"] == "needs_review" and order[-1]["url"] in failed, season


def test_fuel_rules(articles, documents):
    """110kg(경주 연료 질량)는 2019-2021년 스포팅 규정에 있고, 2022-2025년 판에는 없다(아래
    캐시 테스트가 원문 조항 글로 확인한다). 최대 연료 유량은 시즌마다 기술 규정에서 읽는다."""
    fuel = pd.read_csv(OUT / "fuel_rules.csv", dtype={"clause_no": str, "version_key": str})
    assert list(fuel.columns) == reg.FUEL_COLUMNS
    assert set(fuel["season"]) <= set(reg.FUEL_SEASONS)
    assert set(fuel["rule"]) <= {"race_fuel_mass", "max_fuel_mass_flow"}
    assert (fuel["quote"].str.len() <= reg.QUOTE_LIMIT).all()
    assert set(fuel["url"]) <= set(documents.loc[documents["status"] == "ok", "url"])
    check_fact_sources(fuel, documents)
    check_quote_sources(fuel, articles)
    flow = fuel[fuel["rule"] == "max_fuel_mass_flow"]
    assert (flow["value"] == "100 kg/h").all()
    race = fuel[fuel["rule"] == "race_fuel_mass"]
    assert (race["value"] == "110 kg").all() and race["quote"].str.contains("110").all()
    assert set(race["season"]) <= {2019, 2020, 2021}
    for season in reg.FUEL_SEASONS:
        if any(r["status"] == "ok" for r in ordered_series(documents, season, "technical")):
            assert season in set(flow["season"]), season
        if season <= 2021 and any(
            r["status"] == "ok" for r in ordered_series(documents, season, "sporting")
        ):
            assert season in set(race.loc[race["section"] == "sporting", "season"]), season


def string_cells(path):
    frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, dtype=str)
    for column in frame.columns:
        values = frame[column].dropna()
        if values.map(lambda v: isinstance(v, str)).any():
            yield column, values.astype(str)


def test_no_regulation_text_in_curated_files():
    """정제 파일에 규정 본문이 들어가지 않는다. 300자를 넘는 글 칸이 없고, 인용은 200자 이하다."""
    for name in OWN_FILES:
        for column, values in string_cells(OUT / name):
            limit = reg.QUOTE_LIMIT if column in QUOTE_COLUMNS else 300
            assert values.str.len().max() <= limit, (name, column)
    articles = pd.read_parquet(OUT / "articles.parquet")
    assert "text" not in articles.columns
    # 가장 긴 실제 제목은 세 줄로 찍힌 2021-2022년 스포팅 규정 부록 5(121자)다.
    assert articles["heading"].str.len().max() <= TITLE_LIMIT
    assert articles["top_title"].str.len().max() <= TITLE_LIMIT
    changes = pd.read_parquet(OUT / "changes.parquet")
    assert changes["heading"].str.len().max() <= TITLE_LIMIT
    assert changes["top_title"].str.len().max() <= TITLE_LIMIT


def test_no_em_dash_in_outputs():
    for name in OWN_FILES:
        for _, values in string_cells(OUT / name):
            assert not values.str.contains("\u2014").any(), name


@pytest.mark.network
def test_parser_reproduces_curated_clauses_from_source(articles, documents):
    """캐시에 있는 표본 원문을 다시 파싱해 조항 번호와 해시가 커밋된 데이터와 같은지 본다.

    파싱 캐시를 쓰지 않고 PDF에서 바로 읽는다. 원문은 내려받지 않는다. 표본이 캐시에 없거나
    PIPELINE_OFFLINE=1이면 건너뛴다. 돌릴 때는 원문 sha256이 documents.csv의 pdf_sha256과 같은지
    먼저 본다.
    """
    if os.environ.get("PIPELINE_OFFLINE") == "1":
        pytest.skip("PIPELINE_OFFLINE=1")
    rows = {(r["season"], r["section"], reg.version_key(r)): r for r in manifest_rows()}
    wanted = [rows[key] for key in SAMPLE]
    missing = [r["url"] for r in wanted if not fia_regulations.local_path(r).exists()]
    if missing:
        pytest.skip(f"표본 원문이 캐시에 없다: {missing}")
    for row in wanted:
        path = fia_regulations.local_path(row)
        recorded = documents.loc[documents["url"] == row["url"], "pdf_sha256"]
        assert list(recorded) == [reg.file_sha256(path)], row["url"]
        if row["sha256"]:
            assert recorded.iloc[0] == row["sha256"]
        parsed = reg.parse_document(path, row["section"])
        problems, _ = reg.review_problems(
            reg.doc_key(row), parsed.problems, reg.numbering_reviews()
        )
        assert parsed.clauses and not problems, problems
        expected = live_all(articles, row)
        got = [(c.clause_no, c.text_sha256, c.page, c.heading) for c in parsed.clauses]
        assert got == expected, row["url"]


def live_all(articles, row):
    doc = articles[
        (articles["season"] == int(row["season"]))
        & (articles["section"] == row["section"])
        & (articles["version_key"] == reg.version_key(row))
    ]
    return [(r.clause_no, r.text_sha256, r.page, r.heading) for r in doc.itertuples()]


def test_human_reviewed_versions_are_ok_and_say_so(documents, comparisons):
    """사람이 원문 번호 오류로 확인한 11개 판과 파서를 고친 판은 ok이고 판 사이 비교에 들어간다.
    확인한 판은 review_note에 검수 id를 적는다."""
    by = {(r.season, r.section, r.version_key): r for r in documents.itertuples()}
    for key, rid in HUMAN_REVIEWED.items():
        row = by[key]
        assert row.status == "ok" and row.problems == "", key
        assert row.review_note.startswith(f"사람 검수(2026-11-13, {rid}): "), key
        assert "FIA 원문" in row.review_note
    fixed = by[PARSER_FIXED]
    assert fixed.status == "ok" and fixed.problems == "" and fixed.review_note == ""
    compared = set(
        zip(comparisons["section"], comparisons["from_season"], comparisons["from_version"],
            strict=True)
    ) | set(
        zip(comparisons["section"], comparisons["to_season"], comparisons["to_version"],
            strict=True)
    )  # fmt: skip
    for season, section, version in [*HUMAN_REVIEWED, PARSER_FIXED]:
        assert (section, season, version) in compared, (season, section, version)


def test_duplicate_numbers_in_reviewed_versions_have_distinct_keys(articles):
    """원문에 두 번 찍힌 번호는 두 번째 조항이 "#2" 키를 갖고, 판 안의 조항 키는 겹치지 않는다."""
    assert not articles.duplicated(["season", "section", "version_key", "clause_no"]).any()
    marked = articles[articles["clause_no"].str.contains(reg.DUPLICATE_MARK, regex=False)]
    got = {(r.season, r.section, r.version_key, r.clause_no) for r in marked.itertuples()}
    assert got == {
        (2021, "sporting", "2020-12-16", "42.12#2"),
        (2025, "sporting", "2025-04-30", "23.6#2"),
        (2021, "technical", "2019-10-31", "8.2.5#2"),
        (2021, "technical", "2019-10-31", "15.2.3#2"),
        (2021, "technical", "2020-03-06", "8.2.5#2"),
        (2021, "technical", "2020-03-06", "15.2.3#2"),
        (2022, "technical", "2020-03-30", "8.2.5#2"),
        (2022, "technical", "2020-03-30", "15.2.3#2"),
        (2022, "technical", "2020-10-30", "15.2.3#2"),
        (2022, "technical", "2021-02-19", "15.2.3#2"),
        (2022, "technical", "2021-04-30", "15.2.3#2"),
        (2022, "technical", "2021-07-08", "15.2.3#2"),
        (2022, "technical", "2021-12-15", "14.3.3#2"),
    }


def test_indented_clause_2_9_2_is_parsed(articles):
    """2023년 기술 규정 Issue 5 8쪽의 2.9.2(번호 9pt, 본문 10pt로 들여 찍힘)를 조항으로 읽는다."""
    season, section, version = PARSER_FIXED
    doc = articles[
        (articles["season"] == season)
        & (articles["section"] == section)
        & (articles["version_key"] == version)
    ]
    numbers = doc["clause_no"].tolist()
    i = numbers.index("2.9.1")
    assert numbers[i : i + 3] == ["2.9.1", "2.9.2", "2.9.3"]
    row = doc[doc["clause_no"] == "2.9.2"].iloc[0]
    assert row.page == 8 and row.char_count > 0


def test_sample_documents_are_parsed(documents):
    """대조 표본 세 부가 정제 데이터에 ok로 들어 있다."""
    for season, section, version in SAMPLE:
        row = documents[
            (documents["season"] == int(season))
            & (documents["section"] == section)
            & (documents["version_key"] == version)
        ]
        assert list(row["status"]) == ["ok"]


# --- 파싱 캐시(data/raw, 커밋하지 않음)가 있을 때만 도는 검사 -----------------------------------
#
# 아래 검사는 조항 글이 있는 로컬 파싱 캐시에서만 돈다. CI는 규정 원문을 받지 않고 파싱도 하지
# 않으므로 여기서는 언제나 건너뛴다. 그래서 정제 규정 데이터를 커밋하기 전에 로컬에서
# `uv run python -m pipeline.parsers.regulations --cached` 뒤 이 파일 전체가 건너뜀 없이 통과해야
# 한다. CI에서는 캐시 없이 도는 check_quote_sources(인용 자리와 조항 해시)와 길이 상한만 본다.


@pytest.fixture(scope="module")
def cached(documents):
    """ok 문서마다 ({조항 번호: 조항 글}, {조·조항 제목}). 파싱 캐시가 없거나 낡은 문서는 뺀다."""
    by_url = {r["url"]: r for r in manifest_rows()}
    texts, titles = {}, {}
    for doc in documents[documents["status"] == "ok"].itertuples():
        data = reg.read_cache(by_url[doc.url], doc.pdf_sha256)
        if data is not None:
            texts[doc.url] = {c["clause_no"]: c["text"] for c in data["clauses"]}
            titles[doc.url] = {
                reg.normalise(c[k]) for c in data["clauses"] for k in ("heading", "top_title")
            }
    if not texts:
        pytest.skip("파싱 캐시가 없다")
    return texts, titles


@pytest.fixture(scope="module")
def cached_texts(cached):
    return cached[0]


def test_quotes_are_substrings_of_their_clause(cached_texts):
    """사실 행의 인용은 그 조항 글의 일부를 그대로 옮긴 것이다."""
    checked = 0
    for name in ("pu_allocation_rules.csv", "fuel_rules.csv"):
        facts = pd.read_csv(OUT / name, dtype={"clause_no": str})
        for row in facts.itertuples():
            if row.url not in cached_texts:
                continue
            text = cached_texts[row.url][row.clause_no]
            assert row.quote in text, (name, row.season)
            assert text[row.quote_start : row.quote_start + len(row.quote)] == row.quote
            assert reg.text_hash(text) == row.text_sha256, (name, row.season)
            checked += 1
    assert checked


def test_struck_appendix_note_is_not_in_the_previous_clause(documents, cached_texts):
    """2021년 스포팅 규정 Issue 2(2020-05-27)의 A5 글에 지운 부록 6 아래의 알림 글이 없다."""
    row = documents[
        (documents["season"] == 2021)
        & (documents["section"] == "sporting")
        & (documents["version_key"] == "2020-05-27")
    ]
    if row.empty or row.iloc[0]["url"] not in cached_texts:
        pytest.skip("2021년 스포팅 규정 Issue 2의 파싱 캐시가 없다")
    texts = cached_texts[row.iloc[0]["url"]]
    assert "Appendix 6" not in texts["A5"]
    assert texts["A6"].startswith("-Void-")


def test_110kg_is_not_stated_from_2022(documents, cached_texts):
    """2022-2025년 시즌의 사실 원천 판(마지막 ok 판)에는 110kg 경주 연료 질량 문장이 없다."""
    for season in range(2022, 2026):
        for section in ("technical", "sporting"):
            ok = [r for r in ordered_series(documents, season, section) if r["status"] == "ok"]
            if ok and ok[-1]["url"] in cached_texts:
                texts = cached_texts[ok[-1]["url"]].values()
                assert not any(reg.FUEL_RACE.search(t) for t in texts), (season, section)


WINDOW = 40


def shares_window(value: str, text: str) -> bool:
    """value와 text가 WINDOW자 이상 같은 글을 갖는지 본다. WINDOW/2 간격으로 자른 조각이 text에
    없으면 WINDOW자 공통 글이 있을 수 없으므로 그때만 전부 맞춰 본다."""
    half = WINDOW // 2
    pieces = [value[i : i + half] for i in range(0, len(value) - half + 1, half)]
    if not any(p in text for p in pieces):
        return False
    return any(value[i : i + WINDOW] in text for i in range(len(value) - WINDOW + 1))


def test_no_body_text_outside_quotes(documents, cached):
    """인용(quote) 말고는 어느 열에도 그 문서 조항 글과 40자 넘게 같은 글이 없다.

    조·조항 제목은 게시하는 값이고 본문에서 그대로 인용되기도 하므로
    ("Driver adjustable bodywork permitted by Article 3.10.10 of the Technical Regulations"),
    그 문서의 어느 조항 제목과 같은 값은 본다. 글 열은 pandas 판에 따라 dtype이 object이거나
    str이므로 is_string_dtype으로 고르고, 실제로 본 칸이 있는지도 확인한다(검사할 칸이 없어
    늘 통과하지 않게).
    """
    cached_texts, titles = cached
    url_of = {
        (int(r.season), r.section, str(r.version_key)): r.url
        for r in documents.itertuples()
        if r.url in cached_texts
    }
    joined = {url: "\n".join(t.values()) for url, t in cached_texts.items()}

    def doc_urls(row: dict) -> set[str]:
        if row.get("url") in joined:
            return {row["url"]}
        keys = [
            ("season", "section", "version_key"),
            ("from_season", "section", "from_version"),
            ("to_season", "section", "to_version"),
        ]
        found = set()
        for a, b, c in keys:
            if a in row and b in row and c in row:
                url = url_of.get((int(row[a]), row[b], str(row[c])))
                if url:
                    found.add(url)
        return found

    examined: Counter = Counter()
    for name in OWN_FILES:
        path = OUT / name
        frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, dtype=str)
        columns = [
            c
            for c in frame.columns
            if c not in QUOTE_COLUMNS
            and (pd.api.types.is_string_dtype(frame[c]) or pd.api.types.is_object_dtype(frame[c]))
        ]
        examined[f"{name} columns"] = len(columns)
        seen: set[tuple[str, str]] = set()
        for row in frame.to_dict("records"):
            urls = doc_urls(row)
            for column in columns:
                value = row[column]
                if not isinstance(value, str) or len(value) < WINDOW:
                    continue
                text = reg.normalise(value)
                # 비교 행의 제목은 두 판 가운데 한쪽에만 있을 수 있다(새로 생긴 제목)
                named = any(text in titles[url] for url in urls)
                for url in urls:
                    if (url, value) in seen:
                        continue
                    seen.add((url, value))
                    examined["cells"] += 1
                    if named:
                        examined["titles"] += 1
                        continue
                    assert not shares_window(text, joined[url]), (name, column, value[:60])
    for name in OWN_FILES:
        assert examined[f"{name} columns"] > 0, name
    assert examined["cells"] > examined["titles"] > 0
