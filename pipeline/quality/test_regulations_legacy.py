"""T8 규정 문서 2001-2017년 판 manifest 검증. 네트워크 요청 없이 manifest만 본다."""

import re
from itertools import product

import pytest

from pipeline import manifest
from pipeline.sources import fia_regulations_legacy as legacy

SEASONS = range(legacy.FIRST_SEASON, legacy.LAST_SEASON + 1)
LANGUAGES = {"en", "fr", "fr+en"}
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

# 후보 주소를 하나도 찾지 못해 manifest에 행이 없는 (시즌, 구분).
# 웨이백 색인은 수집된 주소만 알므로, 여기 있다고 해서 문서가 없었다는 뜻은 아니다.
ABSENT_FROM_MANIFEST: set[tuple[int, str]] = set()

# 후보 주소는 있으나 FIA 서버가 지금 PDF를 주는 주소가 하나도 없는 (시즌, 구분).
# 2001-2004년 판과 2005년 스포팅 규정은 옛 fia.com 주소(/regle/, /Reglements-sportifs/,
# /resources/documents/)에만 있었고, 그 주소는 2026-11-11 확인 때 모두 404였다.
NO_LIVE_DOCUMENT: set[tuple[int, str]] = {
    *product(range(2001, 2005), legacy.SECTIONS),
    (2005, "sporting"),
}


@pytest.fixture(scope="module")
def rows():
    return manifest.read_rows(legacy.MANIFEST)


def combos(rows, status=None):
    return {
        (int(r["season"]), r["section"]) for r in rows if status is None or r["status"] == status
    }


def test_columns_and_allowed_values(rows):
    assert rows
    for r in rows:
        assert list(r) == legacy.FIELDS
        assert int(r["season"]) in SEASONS
        assert r["section"] in legacy.SECTIONS
        assert r["status"] in {"live", "gone"}
        assert r["host"] in legacy.SOURCES
        assert r["url"].startswith(f"https://{r['host']}/")
        assert r["version_date"] == "" or ISO_DATE.fullmatch(r["version_date"])
        assert r["variant"] in {*legacy.VARIANTS, ""}
        assert r["language"] in {*LANGUAGES, ""}
        assert r["found_via"] == "wayback_cdx" or r["found_via"].startswith(
            "https://web.archive.org/web/"
        )
        assert r["wayback_timestamp"] == "" or re.fullmatch(r"\d{14}", r["wayback_timestamp"])
        assert ISO_TIME.fullmatch(r["checked_at"])


def test_live_rows_have_a_complete_file_record(rows):
    live = [r for r in rows if r["status"] == "live"]
    assert live
    for r in live:
        assert re.fullmatch(r"[0-9a-f]{64}", r["sha256"])
        assert int(r["bytes"]) > 0
        assert int(r["pages"]) > 0
        assert r["is_text_pdf"] in {"true", "false"}
        assert ISO_TIME.fullmatch(r["fetched_at"])
        assert r["variant"] in legacy.VARIANTS
        # 글자를 뽑을 수 없는 스캔본(도면)만 언어와 제목이 비어 있다.
        assert r["is_text_pdf"] == "false" or (r["language"] in LANGUAGES and r["title_in_pdf"])
        # 본문에 날짜가 찍히지 않은 부속서, 도면, 변경 안내만 판 날짜가 비어 있다.
        assert r["version_date"] or r["variant"] in {"appendix", "drawings", "changes"}


def test_gone_rows_have_an_empty_or_complete_file_record(rows):
    """처음부터 gone 인 행은 파일 열이 비어 있다. check()가 live 에서 gone 으로 바꾼 행만
    예전에 받은 파일의 기록을 그대로 가진다."""
    for r in rows:
        if r["status"] == "gone":
            filled = [bool(r[k]) for k in legacy.FILE_FIELDS]
            assert all(filled) or not any(filled)
            if not any(filled):  # 본문을 본 적이 없으면 본문에서 읽는 값도 없다
                assert r["title_in_pdf"] == r["language"] == r["variant"] == ""


def test_no_duplicate_urls_or_cache_paths(rows):
    urls = [r["url"] for r in rows]
    assert len(set(urls)) == len(urls)
    paths = [(r["host"], legacy.cache_path(r).lower()) for r in rows]
    assert len(set(paths)) == len(paths)


def test_rows_are_sorted(rows):
    keys = [(r["season"], r["section"], r["version_date"], r["url"]) for r in rows]
    assert keys == sorted(keys)


def test_same_file_is_identified_the_same_way(rows):
    """같은 파일이 여러 주소에 올라와 있으면 본문에서 읽은 값도 같아야 한다."""
    seen: dict[str, tuple[str, ...]] = {}
    for r in rows:
        if r["sha256"]:
            identity = tuple(
                r[k] for k in ("season", "section", "version_date", "variant", "language", "pages")
            )
            assert seen.setdefault(r["sha256"], identity) == identity


def test_every_season_and_section_is_covered_or_documented(rows):
    every = set(product(SEASONS, legacy.SECTIONS))
    assert every - combos(rows) == ABSENT_FROM_MANIFEST
    assert every - combos(rows, "live") - ABSENT_FROM_MANIFEST == NO_LIVE_DOCUMENT


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://argent.fia.com/web/fia-public.nsf/115F0A1E47E0A282C12573FB0042CB0D/$FILE/"
            "1-2008%20F1%20TECHNICAL%20REGULATIONS%2022-02-2008.pdf",
            "115F0A1E47E0A282C12573FB0042CB0D_1-2008 F1 TECHNICAL REGULATIONS 22-02-2008.pdf",
        ),
        (
            "https://www.fia.com/sites/default/files/regulation/file/"
            "1-2014%20SPORTING%20REGULATIONS%202014-02-28.pdf",
            "1-2014 SPORTING REGULATIONS 2014-02-28.pdf",
        ),
        ("https://www.fia.com/file/40714/download/14519?token=aIudaF8D", "file_40714.pdf"),
        (
            "https://www.fia.com/Reglements-sportifs/2002%20F1%20R%E8glement%20Sportif.pdf",
            "2002 F1 Règlement Sportif.pdf",
        ),
    ],
)
def test_cache_name(url, expected):
    assert legacy.cache_name(url) == expected
