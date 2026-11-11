"""FIA 문서 목록의 대회명과 Jolpica 대회(시즌, 라운드)를 맞춘다.

두 출처의 대회명은 대부분 같지만 몇 해는 다르다(예: FIA 목록의 2021년 "Brazilian Grand Prix"는
Jolpica의 "São Paulo Grand Prix"). 다른 이름은 data/curated/labels/fia_event_aliases.csv 에 적는다.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from functools import cache

import pandas as pd

from pipeline.config import CURATED_DIR

ALIASES = CURATED_DIR / "labels" / "fia_event_aliases.csv"


def plain(text: str) -> str:
    """비교용 이름: 악센트, 대소문자, 기호 차이를 없앤다."""
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


@cache
def aliases() -> dict[tuple[int, str], str]:
    """(시즌, FIA 대회명) -> Jolpica 대회명."""
    with ALIASES.open(newline="", encoding="utf-8") as f:
        return {
            (int(r["season"]), plain(r["fia_event"])): r["race_name"] for r in csv.DictReader(f)
        }


@cache
def rounds() -> dict[tuple[int, str], int]:
    """(시즌, Jolpica 대회명) -> 라운드."""
    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    return {(int(r.season), plain(r.race_name)): int(r.round) for r in races.itertuples()}


def race_name_for(season: int, fia_event: str) -> str:
    """FIA 대회명에 해당하는 Jolpica 대회명. 별칭이 없으면 같은 이름으로 본다."""
    return aliases().get((season, plain(fia_event)), fia_event)


def round_for(season: int, fia_event: str) -> int | None:
    """FIA 대회명의 라운드. 대회가 아니면(테스트, 취소된 대회 등) None이다."""
    return rounds().get((season, plain(race_name_for(season, fia_event))))


def fia_names_for(season: int, race_name: str) -> list[str]:
    """Jolpica 대회명에 해당할 수 있는 FIA 대회명들(같은 이름과 별칭)."""
    names = [race_name]
    with ALIASES.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["season"]) == season and plain(r["race_name"]) == plain(race_name):
                names.append(r["fia_event"])
    return names
