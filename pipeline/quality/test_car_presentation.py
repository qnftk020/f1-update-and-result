"""T5 Car Presentation 파서 검증."""

import csv

import pandas as pd
import pytest

from pipeline import manifest, review
from pipeline.config import CURATED_DIR, RAW_DIR
from pipeline.parsers import car_presentation as cp
from pipeline.sources import fia_docs

FIA = CURATED_DIR / "fia"
# 표가 그림으로만 들어 있어 읽을 수 없는 문서. 사이트에는 "검수 대기"로 표시한다. 2024 라스베이거스
# Williams(14쪽)는 사람이 그림 속 문구를 확인해(human_review.csv i00) 더는 검수 대기가 아니다.
KNOWN_FAILURES: set[tuple[int, str]] = set()
VEGAS_URL = (
    "https://www.fia.com/sites/default/files/decision-document/"
    "2024%20Las%20Vegas%20Grand%20Prix%20-%20Car%20Presentation%20Submissions.pdf"
)
# 원문을 다시 받아 파싱 결과를 대조하는 표본. 양식이 서로 다른 문서를 골랐다.
SAMPLE = [
    (2023, "Mexico City Grand Prix"),  # 2023년 뉴스 첨부 양식
    (2024, "Saudi Arabian Grand Prix"),  # 번호 열 칸이 없는 팀, 같은 번호가 두 번 나오는 팀
    (2024, "Spanish Grand Prix"),  # 표가 다음 쪽으로 이어지는 팀
    (2024, "Las Vegas Grand Prix"),  # 표가 그림인 팀(사람 검수 i00으로 업데이트 없음)
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
        ("- Performance Flow Conditioning", "performance"),
        ("Local load", "performance"),
        ("Balance range", "circuit_specific"),
        ("Driver Cooling", "other"),
    ],
)
def test_reason_category(reason, category):
    assert cp.reason_category(reason) == category


@pytest.mark.parametrize(
    ("reason", "parts"),
    [
        ("Performance - Local Load", ("performance", "Local Load", False)),
        ("Performance \u2013 Local load", ("performance", "Local Load", False)),
        ("Performance -Flow Conditioning", ("performance", "Flow Conditioning", False)),
        ("Circuit specific", ("circuit_specific", "", False)),
        ("Circuit specific \u2013 Drag Level", ("circuit_specific", "Drag Level", False)),
        ("Reliability", ("reliability", "", False)),
        ("Local load", ("performance", "Local Load", True)),
        ("Other - Local flow alignment", ("other", "Local flow alignment", False)),
    ],
)
def test_reason_parts(reason, parts):
    """세부 사유만 적힌 행은 FIA 양식의 범주로 보고 표시를 남긴다."""
    assert cp.reason_parts(reason) == parts


@pytest.mark.parametrize(
    ("component", "area"),
    [
        ("Front Wing", "front_wing"),
        ("Front Wing Endplate", "front_wing"),
        ("Rear Beam Wing", "beam_wing"),
        ("Rear Wing / Beam Wing", "rear_wing"),
        ("Floor fences", "floor"),
        ("Edge wing", "floor"),
        ("Floor Corner", "front_corner"),  # 2025년 캐나다 Mercedes, 프런트 브레이크 덕트 항목
        ("Floor Corner Fences", "floor"),  # 예외 규칙은 이 표기 하나에만 맞는다
        ("Coke / Engine Cover", "engine_cover"),
        ("Cooling Louvres", "engine_cover"),
        ("Sidepod Inlet / Engine cover", "sidepod"),
        ("Other - rear view mirrors", "cockpit"),
        ("Rear Impact Structure", "other"),
    ],
)
def test_component_area(component, area):
    assert cp.component_area(component) == area


def test_every_component_has_an_area(items):
    """부품 표기가 새로 생기면 영역 규칙을 보완하도록 '기타'의 범위를 고정해 둔다."""
    other = set(items.loc[items["component_area"] == "other", "updated_component"])
    assert other <= {"Rear Impact Structure"}
    inferred = items[items["reason_category_inferred"]]
    assert set(inferred["reason_category"]) <= {"performance", "circuit_specific"}
    assert len(inferred) < 20


def test_floor_corner_typo_is_front_corner(items):
    """2025년 캐나다 Mercedes 1번 항목은 원문 표기가 Floor Corner인 브레이크 덕트 항목이다."""
    row = items[
        (items["season"] == 2025)
        & (items["round"] == 10)
        & (items["constructor_id"] == "mercedes")
        & (items["updated_component"] == "Floor Corner")
    ]
    assert len(row) == 1
    assert row["component_area"].iloc[0] == "front_corner"
    assert "front brake duct" in row["description"].iloc[0].lower()


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
    assert (teams["status"] != "needs_review").all()
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
        parsed = cp.parse_document(
            RAW_DIR / "fia" / fia_docs.pdf_cache_path(doc), cp.document_reviews(doc["url"])
        )
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


# --- 사람 검수 결정 ---------------------------------------------------------------------------


def test_human_review_marks_vegas_williams_as_no_updates(teams, documents):
    """i00: 2024 라스베이거스 14쪽 Williams는 그림 속 문구대로 업데이트 없음이고 문서는 정상이다."""
    [decision] = [r for r in review.decisions("car_presentation") if r["id"] == "i00"]
    assert decision["source_url"] == VEGAS_URL and decision["decision"] == "no_updates"
    vegas = teams[(teams["season"] == 2024) & (teams["round"] == 22)].set_index("constructor_id")
    williams = vegas.loc["williams"]
    assert (williams["status"], williams["rows"], williams["page"]) == ("no_updates", 0, 14)
    assert williams["note"].startswith("사람 검수(2026-11-13, i00): 14쪽")
    # 결정은 그 팀 한 줄에만 붙는다
    assert teams["note"].notna().sum() == 1
    doc = documents.set_index("url").loc[VEGAS_URL]
    assert (doc["status"], doc["no_update_teams"], doc["teams"], doc["rows"]) == ("ok", 1, 10, 19)
    assert pd.isna(doc["problems"])
    assert VEGAS_URL not in {r["url"] for r in manifest.read_rows("parse_failures.csv")}


def test_reviewed_no_updates_is_keyed_by_page_and_team():
    rows = [{"id": "x1", "reviewed_at": "2026-11-13", "decision": "no_updates",
             "target": "williams", "page": "14", "source_url": "u"}]  # fmt: skip
    assert cp.reviewed_no_updates(rows, 14, "williams") is rows[0]
    assert cp.reviewed_no_updates(rows, 13, "williams") is None
    assert cp.reviewed_no_updates(rows, 14, "haas") is None
    assert cp.reviewed_no_updates([{**rows[0], "decision": "other"}], 14, "williams") is None


def test_vegas_review_applies_only_where_it_points():
    """결정이 없으면 원래대로 검수 대기이고, 쪽이 틀린 결정은 적용하지 않고 문제로 남긴다."""
    docs = [
        r for r in manifest.read_rows(fia_docs.INDEX_MANIFEST) if r["url"] == VEGAS_URL
    ]  # fmt: skip
    path = RAW_DIR / "fia" / fia_docs.pdf_cache_path(docs[0])
    if not path.exists():
        pytest.skip("원문이 캐시에 없다")
    reviews = cp.document_reviews(VEGAS_URL)
    assert [r["id"] for r in reviews] == ["i00"]
    assert cp.parse_document(path, reviews).ok
    plain = cp.parse_document(path)
    assert plain.problems == ["14쪽: Williams Racing: 표도 'No updates submitted'도 글자로 없다"]
    wrong = cp.parse_document(path, [{**reviews[0], "page": "13"}])
    assert len(wrong.problems) == 2 and "i00" in wrong.problems[1]
