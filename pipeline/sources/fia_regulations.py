"""FIA 포뮬러 원 규정 문서 인덱서. (T8, 등급 A 2018년 이후)

fia.com 규정 페이지는 "Archives" 아래에 연도별 묶음을 두고, 그 안에 Sporting, Technical,
Financial 묶음과 문서 목록(제목, 링크, 게시일)을 둔다. 이 목록을 manifest에 적고,
기술·스포팅 규정 PDF를 로컬 캐시에 받는다.

- PDF 원본은 data/raw/fia/regulations/ 에만 두고 커밋하지 않는다.
- manifest에는 URL, 게시일, 수집 시각, sha256만 적는다.
- 범위는 config.LAST_SEASON 까지다. 그 뒤 시즌 규정은 목록에서 건너뛴다.

실행:
    uv run python -m pipeline.sources.fia_regulations index [--force]
    uv run python -m pipeline.sources.fia_regulations download
"""

from __future__ import annotations

import html
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from pipeline import manifest
from pipeline.config import LAST_SEASON, RAW_DIR
from pipeline.http import PoliteClient, sha256_bytes, utc_now_iso
from pipeline.sources.fia_docs import absolute_url, file_time_iso

CATEGORY_URL = "https://www.fia.com/regulation/category/110"
CATEGORY_CACHE = "regulations/index/category-110.html"
MANIFEST = "fia_regulations.csv"
FIELDS = [
    "season", "section", "issue", "variant", "version_date", "title", "url", "published_at",
    "listed_season", "indexed_at", "sha256", "bytes", "fetched_at",
]  # fmt: skip
FIRST_SEASON = 2018
PARSED_SECTIONS = ("technical", "sporting")

TOKEN = re.compile(
    r'<div class="view-grouping-header">(?P<header>.*?)</div>'
    r'|<li class="list-item">\s*<a href="(?P<href>[^"]+)"[^>]*>.*?'
    r'<div class="title">(?P<title>.*?)</div>.*?date-display-single">(?P<date>[^<]+)<',
    re.S,
)
ISSUE = re.compile(r"\biss(?:ue)?[ ._-]*0*(\d+[a-z]?)(?![a-z0-9])", re.I)
VARIANT = re.compile(r"\bv(\d)\b", re.I)
ISO_DATE = re.compile(r"(?<!\d)(20\d\d)-(\d\d)-(\d\d)(?!\d)")
DOTTED_DATE = re.compile(r"published on (\d{1,2})\.(\d{1,2})\.(20\d\d)", re.I)
YEAR = re.compile(r"(?<!\d)(20\d\d)(?!\d)")


def parse_listing_date(text: str) -> str:
    """'30.04.25' 를 'YYYY-MM-DD' 로 바꾼다."""
    try:
        return datetime.strptime(text.strip(), "%d.%m.%y").strftime("%Y-%m-%d")
    except ValueError:
        return text.strip()


def version_date(title: str, filename: str, published_at: str) -> str:
    """문서 판의 날짜. 제목, 파일 이름, 게시일 순으로 찾는다."""
    for text in (title, filename):
        m = ISO_DATE.search(text)
        if m:
            return "-".join(m.groups())
        m = DOTTED_DATE.search(text)
        if m:
            day, month, year = m.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    return published_at


def parse_category_page(page: str) -> list[dict[str, str]]:
    """규정 페이지에서 (목록의 연도, 구분, 제목, URL, 게시일)을 읽는다."""
    rows: list[dict[str, str]] = []
    listed_season: str | None = None
    section: str | None = None
    for m in TOKEN.finditer(page):
        if m.group("header") is not None:
            header = html.unescape(re.sub(r"<[^>]+>", "", m.group("header"))).strip()
            if re.fullmatch(r"\d{4}", header):
                listed_season, section = header, None
            elif re.fullmatch(r"\d{4} Regulations|Archives", header):
                listed_season, section = None, None
            else:
                section = header.lower()
            continue
        if listed_season is None or section is None:
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group("title")))
        title = re.sub(r"\s+", " ", title).strip()
        url = absolute_url(m.group("href"))
        filename = unquote(url.rsplit("/", 1)[1])
        published_at = parse_listing_date(m.group("date"))
        # 기술·스포팅 규정은 제목에 적힌 연도가 그 문서의 시즌이다. 목록의 묶음과 다를 수 있다.
        season = listed_season
        if section in PARSED_SECTIONS:
            year = YEAR.search(title)
            if year:
                season = year.group(1)
        issue = ISSUE.search(title) or ISSUE.search(filename.replace("_", " "))
        variant = VARIANT.search(title) or VARIANT.search(filename.replace("_", " "))
        rows.append(
            {
                "season": season,
                "section": section,
                "issue": issue.group(1).lower() if issue else "",
                "variant": f"v{variant.group(1)}" if variant else "",
                "version_date": version_date(title, filename, published_at),
                "title": title,
                "url": url,
                "published_at": published_at,
                "listed_season": listed_season,
            }
        )
    return rows


def index(*, force: bool = False) -> list[dict[str, str]]:
    """규정 페이지를 읽어 manifest를 갱신한다. 새로 생긴 행의 목록을 돌려준다."""
    with PoliteClient("fia") as client:
        page = client.get(CATEGORY_URL, CATEGORY_CACHE, force=force).content.decode(
            "utf-8", "ignore"
        )
    rows = parse_category_page(page)
    if not rows:
        raise RuntimeError("규정 페이지에서 문서를 하나도 읽지 못했다(마크업 변경)")
    in_scope = [r for r in rows if FIRST_SEASON <= int(r["season"]) <= LAST_SEASON]
    known = {r["url"]: r for r in manifest.read_rows(MANIFEST)}
    now = utc_now_iso()
    added = []
    for row in in_scope:
        old = known.get(row["url"])
        row["indexed_at"] = old["indexed_at"] if old else now
        for k in ("sha256", "bytes", "fetched_at"):
            row[k] = old.get(k, "") if old else ""
        if not old:
            added.append(row)
    manifest.upsert_rows(MANIFEST, in_scope, key=["season", "section", "url"], fieldnames=FIELDS)
    return added


def pdf_cache_path(row: dict[str, str]) -> str:
    name = Path(unquote(row["url"])).name
    return f"regulations/pdf/{row['season']}/{row['section']}/{name}"


def download(sections: tuple[str, ...] = PARSED_SECTIONS) -> list[Path]:
    """manifest의 규정 PDF를 받아 sha256을 적는다. 이미 받은 파일은 건너뛴다."""
    rows = manifest.read_rows(MANIFEST)
    paths: list[Path] = []
    try:
        with PoliteClient("fia") as client:
            for row in rows:
                if row["section"] not in sections:
                    continue
                result = client.get(row["url"], pdf_cache_path(row))
                if not result.content.startswith(b"%PDF-"):
                    result.path.unlink(missing_ok=True)
                    raise RuntimeError(f"PDF가 아닌 응답을 받았다: {row['url']}")
                if row["sha256"] and row["sha256"] != result.sha256:
                    raise RuntimeError(f"원문이 manifest와 다르다: {row['url']}")
                if not row["sha256"]:
                    row["sha256"] = sha256_bytes(result.content)
                    row["bytes"] = str(len(result.content))
                    row["fetched_at"] = result.fetched_at or file_time_iso(result.path)
                paths.append(result.path)
    finally:
        manifest.write_rows(MANIFEST, rows, FIELDS)
    return paths


def local_path(row: dict[str, str]) -> Path:
    return RAW_DIR / "fia" / pdf_cache_path(row)


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "index":
        new_rows = index(force="--force" in args)
        print(f"{len(manifest.read_rows(MANIFEST))} rows in manifest, {len(new_rows)} new")
        for r in new_rows:
            print(f"new: {r['season']} {r['section']} {r['title']}")
    elif command == "download":
        print(f"{len(download())} files")
    else:
        raise SystemExit("usage: fia_regulations.py index [--force] | download")
