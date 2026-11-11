"""FIA 대회별 결정 문서 인덱서. (T4)

fia.com 문서 아카이브에서 시즌별 대회 목록과 대회별 문서 목록을 모으고, 제목 패턴으로
Car Presentation, PU elements, Car Display Procedure 문서를 분류해 manifest에 적는다.

- 요청 간 3초 이상. 목록 페이지(HTML)는 data/raw/fia/index/ 에 캐시한다.
- PDF 원본은 data/raw/fia/pdf/ 에만 두고 커밋하지 않는다.
- manifest에는 URL, 수집 시각, sha256만 적는다.

실행: uv run python -m pipeline.sources.fia_docs index 2023 2024 2025
"""

from __future__ import annotations

import html
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

from pipeline import manifest
from pipeline.http import PoliteClient, utc_now_iso

BASE = "https://www.fia.com"
F1_DOCUMENTS = f"{BASE}/documents/championships/fia-formula-one-world-championship-14"
INDEX_MANIFEST = "fia_documents.csv"
INDEX_FIELDS = [
    "season", "event", "doc_type", "doc_number", "title", "url", "published_at", "route",
    "indexed_at", "sha256", "bytes", "fetched_at",
]  # fmt: skip

# 제목 패턴. 위에서부터 먼저 맞는 유형을 쓴다. 근거: 2020-2025 실제 목록 (docs/sources.md).
DOC_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("car_presentation", re.compile(r"car presentation\s*(-\s*)?submissions?", re.I)),
    ("pu_used", re.compile(r"pu elements used", re.I)),
    ("pu_new", re.compile(r"new pu elements|new power unit elements", re.I)),
    ("car_display", re.compile(r"(car|automobile) (presentation and )?display procedure", re.I)),
]

SEASON_OPTION = re.compile(
    r'<option[^>]*value="(/documents/championships/fia-formula-one-world-championship-14'
    r'/season/season-(\d{4})-\d+)"',
)
EVENT_OPTION = re.compile(r'<option[^>]*value="([^"]*/event/[^"]*)"[^>]*>([^<]*)</option>')
DOC_ROW = re.compile(r'<li class="document-row[^"]*">(.*?)</li>', re.S)
ROW_HREF = re.compile(r'href="([^"]+)"')
# 제목 칸의 마크업은 대회 페이지마다 두 가지다(필드 래퍼가 있는 것과 없는 것). 둘 다 받는다.
ROW_TITLE = re.compile(r'<div class="title">(.*?)<div class="(?:published|panel-separator)"', re.S)
ROW_DATE = re.compile(r'date-display-single">([^<]+)<')
DOC_NUMBER = re.compile(r"^\s*Doc(?:ument)?\s*(\d+)\s*[-:]?\s*", re.I)


def classify(title: str) -> str:
    for doc_type, pattern in DOC_TYPE_PATTERNS:
        if pattern.search(title):
            return doc_type
    return "other"


def parse_published(text: str) -> str:
    """'11.04.25 11:30' (CET 표기) 를 'YYYY-MM-DD HH:MM' 로 바꾼다. 시간대는 원문 그대로다."""
    try:
        return datetime.strptime(text.strip(), "%d.%m.%y %H:%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text.strip()


def absolute_url(href: str) -> str:
    """상대 경로를 절대 URL로 바꾸고 공백 등을 퍼센트 인코딩한다."""
    href = html.unescape(href)
    return urljoin(BASE, quote(unquote(href), safe="/:%"))


def parse_season_links(page: str) -> dict[int, str]:
    return {int(year): urljoin(BASE, path) for path, year in SEASON_OPTION.findall(page)}


def parse_event_links(page: str) -> list[tuple[str, str]]:
    """(대회명, 대회 문서 페이지 URL) 목록."""
    events = []
    for path, name in EVENT_OPTION.findall(page):
        events.append((html.unescape(name).strip(), urljoin(BASE, html.unescape(path))))
    return events


def parse_document_rows(page: str) -> list[dict[str, str]]:
    rows = []
    for block in DOC_ROW.findall(page):
        href = ROW_HREF.search(block)
        title = ROW_TITLE.search(block)
        date = ROW_DATE.search(block)
        if not href or not title:
            continue
        full_title = html.unescape(re.sub(r"<[^>]+>", "", title.group(1)))
        full_title = re.sub(r"\s+", " ", full_title).strip()
        number = DOC_NUMBER.match(full_title)
        rows.append(
            {
                "doc_number": number.group(1) if number else "",
                "title": DOC_NUMBER.sub("", full_title),
                "url": absolute_url(href.group(1)),
                "published_at": parse_published(date.group(1)) if date else "",
            }
        )
    return rows


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", unquote(text).lower()).strip("-")


def index_seasons(seasons: list[int], *, force: bool = False) -> list[dict]:
    """시즌별 모든 대회의 문서 목록을 모아 manifest에 합친다."""
    all_rows: list[dict] = []
    with PoliteClient("fia") as client:
        root = client.get(F1_DOCUMENTS, "index/root.html", force=force).content.decode("utf-8")
        season_links = parse_season_links(root)
        for season in seasons:
            if season not in season_links:
                raise RuntimeError(f"fia.com 시즌 목록에 {season}년이 없다")
            season_page = client.get(
                season_links[season], f"index/{season}/_season.html", force=force
            ).content.decode("utf-8")
            events = parse_event_links(season_page)
            if not events:
                raise RuntimeError(f"{season}년 대회 목록을 찾지 못했다")
            for event, url in events:
                page = client.get(
                    url, f"index/{season}/{slug(event)}.html", force=force
                ).content.decode("utf-8")
                docs = parse_document_rows(page)
                if not docs and page.count("document-row") > 1:
                    raise RuntimeError(f"{season} {event}: 문서 행을 읽지 못했다(마크업 변경)")
                print(f"{season} {event}: {len(docs)} docs", flush=True)
                for doc in docs:
                    all_rows.append(
                        {
                            "season": season,
                            "event": event,
                            "doc_type": classify(doc["title"]),
                            "route": "decision_document",
                            "indexed_at": utc_now_iso(),
                            "sha256": "",
                            "bytes": "",
                            "fetched_at": "",
                            **doc,
                        }
                    )
    # 이미 받은 PDF의 sha256 등은 유지한다.
    known = {r["url"]: r for r in manifest.read_rows(INDEX_MANIFEST)}
    for row in all_rows:
        old = known.get(row["url"])
        if old:
            for k in ("sha256", "bytes", "fetched_at"):
                row[k] = old.get(k, "")
    manifest.upsert_rows(INDEX_MANIFEST, all_rows, key=["season", "event", "url"],
                         fieldnames=INDEX_FIELDS)  # fmt: skip
    return all_rows


NEWS_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
NEWS_PDF = re.compile(r'href="([^"]+car[_ -]presentation[^"]*\.pdf)"', re.I)


def index_news_car_presentations(season: int, *, force: bool = False) -> list[dict]:
    """FIA 뉴스 "F1 - Tech updates at the ... Grand Prix"에 첨부된 Car Presentation을 찾는다.

    2023년에는 이 문서가 결정 문서 목록이 아니라 뉴스 첨부로만 공개됐다. 대회명으로 주소를 만들어
    확인하고, 없는 주소는 뉴스 목록으로 넘어가므로 제목으로 구분한다.
    """
    rows = manifest.read_rows(INDEX_MANIFEST)
    events = sorted({r["event"] for r in rows if int(r["season"]) == season})
    found: list[dict] = []
    with PoliteClient("fia") as client:
        for event in events:
            if "grand prix" not in event.lower() or " - " in event:
                continue
            url = f"{BASE}/news/f1-tech-updates-{slug(event)}"
            page = client.get(url, f"news/{season}/{slug(event)}.html", force=force).content.decode(
                "utf-8", "ignore"
            )
            title = NEWS_TITLE.search(page)
            title_text = html.unescape(title.group(1)).strip() if title else ""
            pdf = NEWS_PDF.search(page)
            date = ROW_DATE.search(page)
            published = parse_news_date(date.group(1)) if date else ""
            ok = "tech updates" in title_text.lower() and pdf and published.startswith(str(season))
            print(f"{season} {event}: {'found ' + published if ok else 'not found'}", flush=True)
            if not ok:
                continue
            found.append(
                {
                    "season": season, "event": event, "doc_type": "car_presentation",
                    "doc_number": "", "title": "Car Presentation Submissions",
                    "url": absolute_url(pdf.group(1)), "published_at": published,
                    "route": f"news_attachment {url}", "indexed_at": utc_now_iso(),
                    "sha256": "", "bytes": "", "fetched_at": "",
                }
            )  # fmt: skip
    known = {r["url"]: r for r in rows}
    for row in found:
        old = known.get(row["url"])
        if old:
            for k in ("sha256", "bytes", "fetched_at"):
                row[k] = old.get(k, "")
    manifest.upsert_rows(INDEX_MANIFEST, found, key=["season", "event", "url"],
                         fieldnames=INDEX_FIELDS)  # fmt: skip
    return found


def parse_news_date(text: str) -> str:
    """뉴스 날짜 '06.10.23' 을 'YYYY-MM-DD' 로 바꾼다."""
    try:
        return datetime.strptime(text.strip(), "%d.%m.%y").strftime("%Y-%m-%d")
    except ValueError:
        return text.strip()


def pdf_cache_path(row: dict) -> str:
    name = Path(unquote(row["url"])).name
    return f"pdf/{row['season']}/{slug(row['event'])}/{name}"


def download_documents(
    doc_types: list[str], seasons: list[int] | None = None, urls: set[str] | None = None
) -> list[Path]:
    """manifest에 있는 해당 유형 문서의 PDF를 받아 sha256을 기록한다. 이미 받은 파일은 건너뛴다.

    manifest에 sha256이 있는데 새로 받은 파일의 값이 다르면 멈춘다(원문이 바뀐 경우).
    """
    rows = manifest.read_rows(INDEX_MANIFEST)
    paths: list[Path] = []
    try:
        with PoliteClient("fia") as client:
            for row in rows:
                if row["doc_type"] not in doc_types:
                    continue
                if seasons and int(row["season"]) not in seasons:
                    continue
                if urls is not None and row["url"] not in urls:
                    continue
                result = client.get(row["url"], pdf_cache_path(row))
                if row["sha256"] and row["sha256"] != result.sha256:
                    raise RuntimeError(f"원문이 manifest와 다르다: {row['url']}")
                if not row["sha256"]:
                    row["sha256"] = result.sha256
                    row["bytes"] = str(len(result.content))
                    row["fetched_at"] = result.fetched_at or file_time_iso(result.path)
                paths.append(result.path)
    finally:
        # 중간에 멈춰도 그때까지 받은 파일의 기록은 남긴다.
        manifest.write_rows(INDEX_MANIFEST, rows, INDEX_FIELDS)
    return paths


def record_cached(doc_types: list[str]) -> int:
    """이미 로컬 캐시에 있는 PDF의 sha256을 manifest에 적는다. 네트워크 요청은 하지 않는다."""
    from pipeline.config import RAW_DIR
    from pipeline.http import sha256_bytes

    rows = manifest.read_rows(INDEX_MANIFEST)
    n = 0
    for row in rows:
        if row["doc_type"] not in doc_types or row["sha256"]:
            continue
        path = RAW_DIR / "fia" / pdf_cache_path(row)
        if not path.exists():
            continue
        content = path.read_bytes()
        row["sha256"] = sha256_bytes(content)
        row["bytes"] = str(len(content))
        row["fetched_at"] = file_time_iso(path)
        n += 1
    manifest.write_rows(INDEX_MANIFEST, rows, INDEX_FIELDS)
    return n


def file_time_iso(path: Path) -> str:
    """캐시 파일이 저장된 시각(UTC)."""
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "index":
        index_seasons([int(a) for a in args])
    elif command == "news":
        index_news_car_presentations(int(args[0]))
    elif command == "record-cached":
        print(f"{record_cached(args[0].split(','))} rows recorded")
    elif command == "download":
        got = download_documents(args[0].split(","), [int(a) for a in args[1:]] or None)
        print(f"{len(got)} files")
    else:
        raise SystemExit("usage: fia_docs.py index <season>... | download <types> [season...]")
