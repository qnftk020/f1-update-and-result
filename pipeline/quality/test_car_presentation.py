"""T5 Car Presentation 파서 검증."""

import csv

import pandas as pd
import pytest

from pipeline import manifest
from pipeline.config import CURATED_DIR, RAW_DIR
from pipeline.parsers import car_presentation as cp
from pipeline.sources import fia_docs

FIA = CURATED_DIR / "fia"
# 표가 그림으로만 들어 있어 읽을 수 없는 문서. 사이트에는 "검수 대기"로 표시한다.
KNOWN_FAILURES = {(2024, "Las Vegas Grand Prix")}
# 원문을 다시 받아 파싱 결과를 대조하는 표본. 양식이 서로 다른 문서를 골랐다.
SAMPLE = [
    (2023, "Mexico City Grand Prix"),  # 2023년 뉴스 첨부 양식
    (2024, "Saudi Arabian Grand Prix"),  # 번호 열 칸이 없는 팀, 같은 번호가 두 번 나오는 팀
    (2024, "Spanish Grand Prix"),  # 표가 다음 쪽으로 이어지는 팀
    (2024, "Las Vegas Grand Prix"),  # 표가 그림인 팀(실패 문서)
    (2025, "Australian Grand Prix"),  # 행이 가장 많은 문서, 건너뛴 번호
    (2025, "Bahrain Grand Prix"),  # 병합된 설명 칸
]


@pytest.fixture(scope="module")
def items():
    return pd.read_parquet(FIA / "car_presentation.parquet")


@pytest.fixture(scope="module")
def teams():
    return pd.read_csv(FIA / "car_presentation_teams.csv")


@pytest.fixture(scope="module")
def documents():
    return pd.read_csv(FIA / "car_presentation_documents.csv")


@pytest.mark.parametrize(
    ("reason", "category"),
    [
        ("Performance - Local Load", "performance"),
        ("Performance – Drag Reduction", "performance"),
        ("Circuit specific - Drag Range", "circuit_specific"),
        ("Circuit Specific – Balance Range", "circuit_specific"),
        ("Reliability", "reliability"),
        ("Cooling", "other"),
        ("Other - Local flow alignment", "other"),
    ],
)
def test_reason_category(reason, category):
    assert cp.reason_category(reason) == category


@pytest.mark.parametrize(
    ("name", "constructor_id"),
    [
        ("Oracle Red Bull Racing", "red_bull"),
        ("Visa Cash App Racing Bulls", "rb"),
        ("VISA CASH APP RB FORMULA ONE TEAM", "rb"),
        ("Scuderia AlphaTauri", "alphatauri"),
        ("Stake F1 Team KICK Sauber", "sauber"),
        ("Alfa Romeo F1 Team Stake", "alfa"),
        ("Mercedes-AMG PETRONAS F1 Team", "mercedes"),
        ("Aston Martin Aramco F1 Team", "aston_martin"),
        ("MoneyGram Haas F1 Team", "haas"),
        ("SCUDERIA FERRARI HP", "ferrari"),
    ],
)
def test_constructor_for(name, constructor_id):
    assert cp.constructor_for(name) == constructor_id


def test_every_document_lists_ten_teams(teams, documents):
    per_doc = teams.groupby(["season", "round"]).constructor_id.nunique()
    assert len(per_doc) == len(documents) == 54
    assert (per_doc == cp.GRID_TEAMS).all()


def test_teams_match_the_grid_of_that_race(teams):
    """문서의 팀이 그 대회 결과에 나온 팀과 같은지 본다."""
    results = pd.read_parquet(CURATED_DIR / "jolpica" / "results.parquet")
    grid = (
        results[results["session_type"] == "R"]
        .groupby(["season", "round"])
        .constructor_id.agg(lambda s: frozenset(s))
    )
    listed = teams.groupby(["season", "round"]).constructor_id.agg(lambda s: frozenset(s))
    for key, value in listed.items():
        assert value == grid[key], key


def test_only_known_documents_need_review(teams, documents):
    review_docs = documents[documents["status"] != "ok"]
    assert {(r.season, r.event) for r in review_docs.itertuples()} == KNOWN_FAILURES
    review_teams = teams[teams["status"] == "needs_review"]
    assert [(r.season, r.event, r.constructor_id) for r in review_teams.itertuples()] == [
        (2024, "Las Vegas Grand Prix", "williams")
    ]
    failures = [
        r for r in manifest.read_rows("parse_failures.csv") if r["doc_type"] == "car_presentation"
    ]
    assert {(int(r["season"]), r["event"]) for r in failures} == KNOWN_FAILURES


def test_rows_are_complete(items, teams):
    assert len(items) >= 850
    for column in ["updated_component", "primary_reason", "geometric_differences", "description"]:
        assert (items[column].str.len() > 0).all(), column
    assert set(items["reason_category"]) <= {
        "performance", "circuit_specific", "reliability", "other",
    }  # fmt: skip
    assert items["item_no"].str.fullmatch(r"\d+").all()
    counted = items.groupby(["season", "round", "constructor_id"]).size()
    declared = teams[teams["rows"] > 0].set_index(["season", "round", "constructor_id"])["rows"]
    assert counted.to_dict() == declared.to_dict()


def test_merged_description_is_shared(items):
    """2025 바레인 Ferrari: 설명 칸 하나가 1-4번 행에 걸쳐 있다 (docs/methodology.md)."""
    rows = items[
        (items["season"] == 2025) & (items["round"] == 4) & (items["constructor_id"] == "ferrari")
    ].sort_values("row_order")
    assert list(rows["updated_component"]) == [
        "Floor Fences", "Floor Body", "Floor Edge", "Diffuser", "Rear Wing",
    ]  # fmt: skip
    assert list(rows["description_shared"]) == [True, True, True, True, False]
    assert rows["description"].iloc[0] == rows["description"].iloc[3]


@pytest.mark.network
def test_parser_reproduces_curated_rows_from_source(items, teams):
    """원문을 manifest에서 다시 받아(없으면) 파싱 결과가 커밋된 데이터와 같은지 본다."""
    docs = {
        (int(r["season"]), r["event"]): r
        for r in manifest.read_rows(fia_docs.INDEX_MANIFEST)
        if r["doc_type"] == "car_presentation"
    }
    wanted = [docs[key] for key in SAMPLE]
    fia_docs.download_documents(["car_presentation"], urls={d["url"] for d in wanted})
    for doc in wanted:
        season, event = int(doc["season"]), doc["event"]
        parsed = cp.parse_document(RAW_DIR / "fia" / fia_docs.pdf_cache_path(doc))
        assert parsed.ok == ((season, event) not in KNOWN_FAILURES)
        expected = items[(items["season"] == season) & (items["event"] == event)]
        got = [
            (t.constructor_id, r["item_no"], r["updated_component"], r["primary_reason"],
             r["geometric_differences"], r["description"])
            for t in sorted(parsed.teams, key=lambda t: t.constructor_id)
            for r in t.rows
        ]  # fmt: skip
        want = [
            (r.constructor_id, r.item_no, r.updated_component, r.primary_reason,
             r.geometric_differences, r.description)
            for r in expected.sort_values(["constructor_id", "row_order"]).itertuples()
        ]  # fmt: skip
        assert got == want, (season, event)


def test_documents_file_is_consistent_with_manifest(documents):
    urls = {
        r["url"]
        for r in manifest.read_rows(fia_docs.INDEX_MANIFEST)
        if r["doc_type"] == "car_presentation"
    }
    assert set(documents["url"]) == urls
    with open(FIA / "car_presentation_documents.csv", newline="", encoding="utf-8") as f:
        assert next(csv.reader(f))[:3] == ["season", "round", "event"]
