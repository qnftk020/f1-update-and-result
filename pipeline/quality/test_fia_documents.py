"""T4 FIA 문서 인덱스 검증."""

import pytest

from pipeline import manifest
from pipeline.sources import fia_docs

# 결정 문서 목록과 뉴스 첨부 어디에서도 Car Presentation을 찾지 못한 대회 (docs/sources.md).
KNOWN_MISSING_CAR_PRESENTATION = {("2024", "Bahrain Grand Prix")}


@pytest.fixture(scope="module")
def rows():
    return manifest.read_rows(fia_docs.INDEX_MANIFEST)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Car Presentation Submissions", "car_presentation"),
        ("PU elements used per driver up to now", "pu_used"),
        ("Corrected number of PU elements used per driver up to now", "pu_used"),
        ("New PU elements for this Competition", "pu_new"),
        ("New PU elements for this Event, Parc Fermé issue", "pu_new"),
        ("Car Display Procedure", "car_display"),
        ("Car Presentation and Display Procedure", "car_display"),
        ("Automobile Display Procedure", "car_display"),
        ("Offence - Car 16 - PU elements", "other"),
        ("Final Race Classification", "other"),
    ],
)
def test_classify(title, expected):
    assert fia_docs.classify(title) == expected


def test_parse_both_row_markups():
    with_wrapper = """<li class="document-row key-10"><div class="node">
      <a href="/system/files/decision-document/a_-_car_presentation_submissions.pdf" download>
      <div class="title"><div class="field field-name-title-field"><div class="field-items">
      <div class="field-item even">Doc 10 - Car Presentation Submissions</div></div></div></div>
      <div class="panel-separator"></div><div class="published">Published on
      <span  class="date-display-single">11.04.25 11:00</span> CET</div></a></div></li>"""
    plain = """<li class="document-row key-56">  <a href="/system/files/b points.pdf" download>
      <div class="title">
      Doc 56 - Championship Points
      </div>
      <div class="published">
      Published on <span  class="date-display-single">07.12.25 17:35</span> CET  </div></a></li>"""
    a, b = fia_docs.parse_document_rows(with_wrapper + plain)
    assert (a["doc_number"], a["title"]) == ("10", "Car Presentation Submissions")
    assert a["published_at"] == "2025-04-11 11:00"
    assert (b["doc_number"], b["title"]) == ("56", "Championship Points")
    assert b["url"] == "https://www.fia.com/system/files/b%20points.pdf"


def test_every_grand_prix_has_car_presentation_2024_2025(rows):
    events = {
        (r["season"], r["event"])
        for r in rows
        if r["season"] in {"2024", "2025"} and "Tests" not in r["event"]
    }
    have = {(r["season"], r["event"]) for r in rows if r["doc_type"] == "car_presentation"}
    assert len([e for e in events if e[0] == "2024"]) == 24
    assert len([e for e in events if e[0] == "2025"]) == 24
    assert events - have == KNOWN_MISSING_CAR_PRESENTATION


def test_car_presentation_documents_have_checksums(rows):
    docs = [r for r in rows if r["doc_type"] == "car_presentation"]
    assert len(docs) >= 54
    assert all(len(r["sha256"]) == 64 and r["fetched_at"] for r in docs)
    assert len({r["sha256"] for r in docs}) == len(docs)


def test_no_event_is_empty(rows):
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        counts[(r["season"], r["event"])] = counts.get((r["season"], r["event"]), 0) + 1
    grands_prix = {k: n for k, n in counts.items() if k[1].lower().endswith("grand prix")}
    assert len(grands_prix) >= 130
    assert min(grands_prix.values()) >= 5  # 취소된 2020 호주 GP가 5건으로 가장 적다
