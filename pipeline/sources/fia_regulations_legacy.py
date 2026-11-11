"""FIA 포뮬러 원 기술·스포팅 규정 2001-2017년 판의 존재 확인과 보관. (T8)

fia.com 규정 페이지는 2018년 이후 문서만 싣는다(fia_regulations.py). 그 이전 판은 지금 목록이
없으므로, 후보 주소를 웨이백 머신의 색인(CDX)과 보존된 FIA 목록 화면에서 모으고 주소마다 FIA
서버에 직접 물어 지금도 PDF를 받을 수 있는지 확인했다. 그 결과가
data/manifests/fia_regulations_legacy.csv 다.

- 이 모듈은 후보 주소를 새로 찾지 않는다. manifest에 적힌 주소만 다시 받거나 다시 확인한다.
- status 는 live(FIA 서버가 PDF를 준다) 또는 gone(404, 또는 PDF가 아닌 응답)이다.
- live 행의 season, section, version_date, variant, language, title_in_pdf 는 파일 이름이 아니라
  PDF 본문 첫 쪽에서 읽었다. gone 행은 본문을 볼 수 없으므로 같은 열을 보존된 목록 화면의 제목이나
  파일 이름에서 읽었고, 확인되지 않은 값(판 날짜, 언어 등)은 비워 두었다.
- 제목과 쪽 아래 줄에 시즌이 적혀 있지 않은 판이 다섯 개 있다(2009-08-19 "Stable" 기술·스포팅
  판, 2009-12-11 스포팅 판, 2010-06-23 기술·스포팅 판). 2010-06-23 판은 같은 argent 문서 ID가
  보존 목록에 "2010 F1 ... Regulations"로 실려 있고, 나머지는 본문이 2010년 판들과 가장 많이
  겹쳐서 2010으로 적었다. 글자를 뽑을 수 없는 도면(08F1_Drawings.pdf)은 보존 목록 제목에서
  시즌을 읽었다.
- 같은 판이 여러 주소에 있으면 행도 여러 개다. sha256이 같은 행은 같은 파일이다.
- variant 값: clean(깨끗한 판), marked(직전 판에서 바뀐 곳을 색 글자로 표시한 판),
  excerpt(바뀐 쪽만 모은 판), appendix(기술 규정 부속서), drawings(기술 규정 도면),
  changes(다음 해 규정 변경 안내), draft(초안).
- found_via 는 주소의 근거다. web.archive.org 주소는 그 링크가 실린 보존 목록 화면이고,
  wayback_cdx 는 웨이백 색인에만 주소가 있다는 뜻이다. wayback_timestamp 는 웨이백 머신이 그 주소를
  PDF로 마지막으로 보존한 시각이며, PDF로 보존된 적이 없으면 비어 있다.
- Drupal 파일 링크(/file/<번호>/download...)는 같은 번호에 토큰만 다른 주소가 여럿 보존되어
  있어서, 번호마다 가장 늦게 목록에 실린 주소 하나만 적었다.
- PDF 원본은 data/raw/<데이터원>/regulations_legacy/ 에만 두고 커밋하지 않는다.

실행:
    uv run python -m pipeline.sources.fia_regulations_legacy download
    uv run python -m pipeline.sources.fia_regulations_legacy check
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from pipeline import manifest
from pipeline.config import RAW_DIR
from pipeline.http import PoliteClient, utc_now_iso

MANIFEST = "fia_regulations_legacy.csv"
FIELDS = [
    "season", "section", "version_date", "variant", "language", "title_in_pdf", "url", "host",
    "found_via", "wayback_timestamp", "status", "pages", "is_text_pdf", "sha256", "bytes",
    "fetched_at", "checked_at",
]  # fmt: skip
FILE_FIELDS = ("pages", "is_text_pdf", "sha256", "bytes", "fetched_at")
FIRST_SEASON, LAST_SEASON = 2001, 2017
SECTIONS = ("technical", "sporting")
VARIANTS = ("clean", "marked", "excerpt", "appendix", "drawings", "changes", "draft")
SOURCES = {"argent.fia.com": "fia_argent", "www.fia.com": "fia"}  # host -> PoliteClient 데이터원
GONE_STATUS = (404, 410)
MIN_TEXT_CHARS = 200  # 한 쪽에서 공백을 뺀 글자가 이만큼 나오면 글자가 있는 쪽으로 본다

FILE_ENTITY = re.compile(r"/file/(\d+)/download(?:/\d+)?")


def cache_name(url: str) -> str:
    """캐시 파일 이름. 같은 이름의 파일이 여러 주소에 있으므로 주소의 구분 값을 붙인다."""
    raw = urlsplit(url).path
    path = unquote(raw, errors="strict") if _is_utf8(raw) else unquote(raw, encoding="latin-1")
    if "/$FILE/" in path:  # argent: <문서 ID>/$FILE/<이름>. 문서 ID가 다르면 다른 파일이다.
        document, name = path.split("/$FILE/")
        return f"{document.rsplit('/', 1)[1]}_{name}"
    file_entity = FILE_ENTITY.fullmatch(path)
    if file_entity:  # www: /file/<번호>/download 에는 파일 이름이 없다.
        return f"file_{file_entity.group(1)}.pdf"
    return path.rsplit("/", 1)[1]


def _is_utf8(raw: str) -> bool:
    """옛 fia.com 주소에는 è 를 %E8(latin-1)로 적은 것이 있다."""
    try:
        unquote(raw, errors="strict")
    except UnicodeDecodeError:
        return False
    return True


def cache_path(row: dict[str, str]) -> str:
    return f"regulations_legacy/{row['season']}/{row['section']}/{cache_name(row['url'])}"


def local_path(row: dict[str, str]) -> Path:
    return RAW_DIR / SOURCES[row["host"]] / cache_path(row)


def describe_pdf(path: Path) -> dict[str, str]:
    """쪽수, 텍스트 추출 가능 여부, 첫 쪽 앞부분의 글자. 본문으로 판을 가려낼 때 쓴다."""
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        texts = [page.extract_text() or "" for page in pdf.pages]
    with_text = sum(len(re.sub(r"\s", "", text)) >= MIN_TEXT_CHARS for text in texts)
    return {
        "pages": str(len(texts)),
        "is_text_pdf": "true" if with_text * 2 >= len(texts) else "false",
        "first_page": texts[0] if texts else "",
    }


def download() -> list[Path]:
    """status 가 live 인 행의 PDF를 캐시에 받는다. 이미 받은 파일은 다시 요청하지 않는다.

    받은 파일이 PDF가 아니거나 sha256이 manifest와 다르면 멈춘다(원문이 바뀌었거나 다른 응답이
    온 경우). 그때 받은 응답은 지우지 않고 그대로 두어 사람이 확인하게 한다.
    """
    rows = [r for r in manifest.read_rows(MANIFEST) if r["status"] == "live"]
    clients: dict[str, PoliteClient] = {}
    paths: list[Path] = []
    try:
        for row in rows:
            source = SOURCES[row["host"]]
            client = clients.setdefault(source, PoliteClient(source))
            result = client.get(row["url"], cache_path(row))
            if not result.content.startswith(b"%PDF-"):
                raise RuntimeError(f"PDF가 아닌 응답을 받았다: {row['url']} ({result.path})")
            if result.sha256 != row["sha256"]:
                raise RuntimeError(f"원문이 manifest와 다르다: {row['url']} ({result.path})")
            paths.append(result.path)
    finally:
        for client in clients.values():
            client.close()
    return paths


def check() -> list[tuple[str, dict[str, str]]]:
    """모든 행의 주소를 FIA 서버에 다시 물어 status 와 checked_at 을 고친다.

    아무것도 지우지 않는다. 행과 파일 기록, 캐시의 원문은 그대로 두고, 이번 응답은
    regulations_legacy/_check/ 아래에 덮어써 남긴다. (결과, 행) 목록을 돌려준다. 결과는 다음 가운데
    하나다.
    - same: 앞서 확인한 상태 그대로다(live 는 sha256까지 같다).
    - gone: live 였던 주소가 404를 준다. status 를 gone 으로 바꾸고 파일 기록은 남긴다.
    - changed: live 였던 주소가 다른 내용이나 PDF가 아닌 응답을 준다. 행은 고치지 않는다.
    - revived: gone 이던 주소가 PDF를 준다. 본문을 사람이 확인해야 하므로 행은 고치지 않는다.
    """
    rows = manifest.read_rows(MANIFEST)
    clients: dict[str, PoliteClient] = {}
    outcomes: list[tuple[str, dict[str, str]]] = []
    try:
        for row in rows:
            source = SOURCES[row["host"]]
            client = clients.setdefault(source, PoliteClient(source))
            probe = f"regulations_legacy/_check/{row['season']}/{cache_name(row['url'])}"
            try:
                result = client.get(row["url"], probe, force=True)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in GONE_STATUS:
                    raise  # 모르는 응답이면 추측하지 않고 멈춘다
                outcome = "same" if row["status"] == "gone" else "gone"
                row["status"], row["checked_at"] = "gone", utc_now_iso()
            else:
                is_pdf = result.content.startswith(b"%PDF-")
                if row["status"] == "live":
                    outcome = "same" if is_pdf and result.sha256 == row["sha256"] else "changed"
                else:
                    outcome = "revived" if is_pdf else "same"
                if outcome == "same":
                    row["checked_at"] = result.fetched_at or utc_now_iso()
            outcomes.append((outcome, row))
    finally:
        for client in clients.values():
            client.close()
        manifest.write_rows(MANIFEST, rows, FIELDS)  # 중간에 멈춰도 그때까지 확인한 결과는 남긴다
    return outcomes


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "download":
        print(f"{len(download())} files")
    elif command == "check":
        results = check()
        for outcome, r in results:
            if outcome != "same":
                print(f"{outcome}: {r['season']} {r['section']} {r['version_date']} {r['url']}")
        print(f"{len(results)} rows checked")
    else:
        raise SystemExit("usage: fia_regulations_legacy.py download | check")
