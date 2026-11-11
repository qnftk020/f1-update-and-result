"""T6(PU 구성요소), T8(규정 아카이브) 산출물을 사이트용 JSON으로 내보낸다.

두 정제 테이블은 다른 작업이 아직 채우는 중이라 열이나 행이 비어 있을 수 있다. 여기서는 있는 것만
그대로 옮기고, 비어 있는 자리는 비어 있다고 적는다(추측으로 채우지 않는다). 테이블이 아예 없으면
None을 돌려주고, 사이트는 해당 영역을 "준비 중"으로 표시한다.

engines.json
    seasons[<연도>]  PU 공급사와 팀, 허용 개수(규정 조항 또는 FIA 문서 문장),
                     드라이버별 라운드 누적, 새 ICE 투입 이벤트,
                     문서 범위(읽은 라운드, 미수집, 검수 대기)
    coverage[]       시즌별 문서 수와 상태

    라운드 누적 값은 pu_usage의 used_after_event(그 대회 누적 문서 값 + 그 대회 선언 문서의
    새 구성요소)다. 선언 문서가 없거나 검수 대기인 대회는 used_after_event가 비어 있으므로
    used_before_event(대회 시작 전 누적)를 적고 그 라운드를 unknown_new_rounds에 남긴다.
    누적 문서를 읽지 않은 라운드는 null이다.

    allocation[구성요소]는 규정 조항에서 읽은 값이면 그 판(version_key, issue)과 시즌 마지막
    판인지(is_final_issue), 마지막 판의 상태(final_issue)를 함께 적는다. allocation_statements에는
    FIA 선언 문서의 배정 문장이 밝힌 값과 처음 나온 라운드, 그 값을 적은 문서 수를 둔다.

    ice_events[]의 ice_number는 문서끼리 어긋나면 비어 있다(null). 그때 printed_previously_used,
    stated_ordinal(원문 값)과 conflict(어긋난 내용), conflict_ko(한국어 설명)를 함께 둔다.

    teams[].drivers[].rounds는 PU 문서에 그 드라이버 값이 있는 라운드다. 문서는 대회 전
    상태를 적으므로 결승 출전 라운드와 다를 수 있다. 결승 출전은 teams[].race_drivers
    (Jolpica 결승 결과)에 둔다.

regulations.json
    years[]          1982-2025 연도 x (기술, 스포팅) 존재 여부와 등급
    documents{연도}  문서 목록(제목, 판, 게시일, 등급, 상태, 원문 링크)
    summaries{연도}  주요 변경 요약(한국어 요약과 출처 링크. 인용문은 싣지 않는다)
    comparisons[]    2018년 이후 조항 단위 비교(조항 번호, 제목, 변경 유형, 쪽). 본문은 싣지 않는다.
                     skipped_versions는 비교가 건너뛴 검수 대기·미수집 판이고, 하나라도 있으면
                     review가 참이다.
    facts{연도}      규정에서 읽은 수치(PU 할당 수, 연료 조항). 값, 조항, 쪽, 판과 그 판이 시즌
                     마지막 판인지만 싣는다. 인용문은 싣지 않는다.

    documents의 검수 대기 판에는 problems(파서가 적은 문제)와 review_reasons(사람이 읽을 한국어
    설명)를 둔다.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from pipeline.config import CURATED_DIR, LAST_SEASON, MANIFEST_DIR, PU_ELEMENTS_FIRST_SEASON

KST = timezone(timedelta(hours=9))
ELEMENTS = ["ICE", "TC", "MGU-H", "MGU-K", "ES", "CE", "EX"]
REG_FIRST_YEAR = 1982
REG_SECTIONS = ["technical", "sporting"]
FIA = CURATED_DIR / "fia"
REG = CURATED_DIR / "regulations"


# --- 도우미 ---------------------------------------------------------------------------


def _read(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _val(v: object) -> object:
    """pandas 값을 JSON 값으로. NaN, NA는 None, 정수형 실수는 int."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        if math.isnan(v):
            return None
        if v.is_integer():
            return int(v)
    return v


def _str(v: object) -> str | None:
    v = _val(v)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """열이 없으면 빈 값 열을 돌려준다(작성 중인 테이블에 열이 아직 없을 수 있다)."""
    if name in df.columns:
        return df[name]
    return pd.Series([None] * len(df), index=df.index, dtype="object")


def _kst_date(stamps: list[object]) -> str | None:
    """ISO 시각(UTC) 또는 날짜 문자열 가운데 가장 늦은 것을 한국 날짜로."""
    best: datetime | None = None
    for s in stamps:
        s = _str(s)
        if not s:
            continue
        try:
            if "T" in s:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
            else:
                dt = datetime.fromisoformat(s[:10]).replace(tzinfo=KST)
        except ValueError:
            continue
        if best is None or dt > best:
            best = dt
    return best.astimezone(KST).strftime("%Y-%m-%d") if best else None


def _host(url: str | None) -> str | None:
    return urlparse(url).netloc or None if url else None


class _Lookups:
    """이름표: 드라이버, 팀, 엔진 제조사, 대회."""

    def __init__(self) -> None:
        drivers = pd.read_parquet(CURATED_DIR / "jolpica" / "drivers.parquet")
        self.driver_name = {
            r.driver_id: f"{r.forename} {r.surname}".strip() for r in drivers.itertuples()
        }
        self.driver_code = {
            r.driver_id: (r.abbreviation if isinstance(r.abbreviation, str) else None)
            for r in drivers.itertuples()
        }
        cs = pd.read_parquet(CURATED_DIR / "lineage" / "constructor_seasons.parquet")
        self.team_rows = cs
        self.season_team = {(int(r.season), r.constructor_id): r for r in cs.itertuples()}
        constructors = pd.read_parquet(CURATED_DIR / "jolpica" / "constructors.parquet")
        self.constructor_name = {r.constructor_id: r.name for r in constructors.itertuples()}
        engines = pd.read_parquet(CURATED_DIR / "f1db" / "engine_manufacturers.parquet")
        self.engine_name = {r.engine_manufacturer_id: r.name for r in engines.itertuples()}
        self.races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
        results = pd.read_parquet(
            CURATED_DIR / "jolpica" / "results.parquet",
            columns=["season", "round", "session_type", "driver_id", "constructor_id"],
        )
        self.race_results = results[
            (results["session_type"] == "R") & (results["season"] >= PU_ELEMENTS_FIRST_SEASON)
        ]
        gp = pd.read_csv(CURATED_DIR / "labels" / "grand_prix_ko.csv")
        self.gp = {r.race_name: (r.name_ko, r.short_ko) for r in gp.itertuples()}
        standings = pd.read_parquet(CURATED_DIR / "jolpica" / "constructor_standings.parquet")
        last = standings.sort_values("round").groupby("season").tail(10_000)
        self.final_pos: dict[tuple[int, str], int] = {}
        for season, g in last.groupby("season"):
            top = g[g["round"] == g["round"].max()]
            for r in top.itertuples():
                if not pd.isna(r.position):
                    self.final_pos[(int(season), r.constructor_id)] = int(r.position)

    def team(self, season: int, cid: str) -> str:
        row = self.season_team.get((season, cid))
        if row is not None and isinstance(row.team_name, str):
            return row.team_name
        return self.constructor_name.get(cid, cid)

    def lineage(self, season: int, cid: str) -> str | None:
        row = self.season_team.get((season, cid))
        return row.lineage_id if row is not None and isinstance(row.lineage_id, str) else None

    def pu(self, season: int, cid: str) -> dict | None:
        row = self.season_team.get((season, cid))
        if row is None or not isinstance(row.pu_manufacturer_id, str):
            return None
        pid = row.pu_manufacturer_id
        name = ", ".join(self.engine_name.get(p, p) for p in pid.split("|"))
        return {"id": pid, "name": name}

    def race_entrants(self, season: int, cid: str) -> list[dict]:
        """Jolpica 결승 결과에서 그 시즌 그 컨스트럭터로 결승에 나간 드라이버와 라운드."""
        r = self.race_results
        g = r[(r["season"] == season) & (r["constructor_id"] == cid)]
        out = []
        for did, dg in g.groupby("driver_id"):
            out.append(
                {
                    "driver_id": did,
                    "name": self.driver_name.get(did, did),
                    "code": self.driver_code.get(did),
                    "rounds": sorted(int(x) for x in dg["round"].unique()),
                }
            )
        out.sort(key=lambda d: (d["rounds"][0], d["name"]))
        return out

    def rounds(self, season: int) -> list[dict]:
        races = self.races[self.races["season"] == season].sort_values("round")
        out = []
        for r in races.itertuples():
            ko, short = self.gp.get(r.race_name, (r.race_name, r.race_name))
            out.append(
                {
                    "round": int(r.round),
                    "name": r.race_name,
                    "name_ko": ko,
                    "short_ko": short,
                    "date": str(r.date)[:10],
                }
            )
        return out


# --- 엔진 ------------------------------------------------------------------------------


def _final_issue(reg_docs, season: int, section: str) -> dict | None:
    """그 시즌·규정의 마지막 판(판 날짜 순 마지막)과 상태."""
    if reg_docs is None:
        return None
    rows = reg_docs[(reg_docs["season"] == season) & (reg_docs["section"] == section)]
    if not len(rows):
        return None
    last = rows.sort_values(["version_date", "version_key"]).iloc[-1]
    return {
        "issue": _str(last.get("issue")),
        "version": _str(last.get("version_key")),
        "status": _reg_status(_str(last.get("status"))),
        "url": _str(last.get("url")),
        "review_reasons": review_reasons(_str(last.get("problems")))
        if _str(last.get("status")) == "needs_review"
        else [],
    }


def _fact_source(row, reg_docs, season: int, section: str) -> dict:
    """규정 사실 행이 나온 판과, 그 판이 시즌 마지막 판인지."""
    version = _str(row.get("version_key"))
    issue = None
    if reg_docs is not None and version:
        hit = reg_docs[
            (reg_docs["season"] == season)
            & (reg_docs["section"] == section)
            & (reg_docs["version_key"].astype(str) == version)
        ]
        issue = _str(hit.iloc[0]["issue"]) if len(hit) else None
    final = _val(row.get("is_final_issue"))
    is_final = None if final is None else str(final).strip().lower() == "true"
    return {
        "version_key": version,
        "issue": issue,
        "is_final_issue": is_final,
        "final_issue": None if is_final else _final_issue(reg_docs, season, section),
    }


def _allocation(season: int, elements: list[str], rules, statements, reg_docs=None) -> dict:
    """허용 개수. 규정 조항(pu_allocation_rules)이 있으면 그것을 쓴다.

    없으면 FIA 선언 문서의 배정 문장을 쓴다.

    선언 문서 문장은 한 시즌에 값이 여럿일 수 있다(2020년 ICE "two"와 "three"). 규정 조항이 없는데
    값이 여럿이면 정하지 않고 비운다. 규정 조항 값에는 그 값을 읽은 판을 적는다. 시즌 마지막 판이
    검수 대기라 앞 판에서 읽었으면 is_final_issue가 거짓이고 final_issue에 마지막 판이 있다.
    """
    out: dict[str, dict | None] = {}
    for el in elements:
        entry = None
        if rules is not None:
            hit = rules[(rules["season"] == season) & (rules["element"] == el)]
            if len(hit):
                r = hit.iloc[0]
                entry = {
                    "allowed": _val(r["allowed"]),
                    "basis": "regulation",
                    "clause_no": _str(r.get("clause_no")),
                    "page": _val(r.get("page")),
                    "url": _str(r.get("url")),
                    **_fact_source(r, reg_docs, season, "sporting"),
                }
        if entry is None and statements is not None:
            hit = statements[(statements["season"] == season) & (statements["element"] == el)]
            values = sorted({int(v) for v in hit["allowed"].dropna()})
            if len(values) == 1:
                entry = {
                    "allowed": values[0],
                    "basis": "document",
                    "clause_no": None,
                    "page": None,
                    "url": _str(hit.iloc[0].get("source_url")),
                    "version_key": None,
                    "issue": None,
                    "is_final_issue": None,
                    "final_issue": None,
                }
        out[el] = entry
    return out


def _allocation_statements(season: int, elements: list[str], statements) -> dict[str, list]:
    """FIA 선언 문서의 배정 문장이 밝힌 허용 개수. 값마다 처음 나온 라운드와 문서 수, 첫 문서."""
    out: dict[str, list] = {}
    if statements is None:
        return out
    rows = statements[statements["season"] == season]
    for el in elements:
        hit = rows[rows["element"] == el].sort_values(["first_round", "allowed"])
        out[el] = [
            {
                "allowed": _val(r.allowed),
                "first_round": _val(r.first_round),
                "documents": _val(r.documents),
                "url": _str(r.source_url),
            }
            for r in hit.itertuples()
        ]
    return out


CONFLICT = re.compile(
    r"^(?P<kind>[a-z_]+) \(expected (?P<expected>[^,]+), actual (?P<actual>[^)]+)\)$"
)


def conflict_ko(conflict: str | None) -> str | None:
    """pu_ice_events의 conflict를 한국어 설명으로 옮긴다. 비어 있으면 None.

    previously_used: 같은 대회 누적 문서로 센 이전 개수(expected)와 선언 문서의 Previously
    used(actual)가 다르다. statement_ordinal: 선언 문서의 배정 문장이 적은 순서(actual)가
    Previously used + 1(expected)과 다르다.
    """
    if not conflict:
        return None
    out = []
    for part in [p.strip() for p in conflict.split(";") if p.strip()]:
        m = CONFLICT.match(part)
        if not m:
            out.append(f"문서끼리 값이 어긋난다({part}).")
            continue
        kind, expected, actual = m["kind"], m["expected"], m["actual"]
        if kind == "previously_used":
            out.append(
                f"선언 문서는 이전 사용 개수를 {actual}개로 적었으나 같은 대회 누적 문서로 센 값은 "
                f"{expected}개다."
            )
        elif kind == "statement_ordinal":
            out.append(
                f"선언 문서의 배정 문장은 {actual}번째라고 적었으나 이전 사용 개수에 1을 더하면 "
                f"{expected}번째다."
            )
        else:
            out.append(f"문서끼리 값이 어긋난다({part}).")
    out.append("어느 쪽도 고르지 않고 순번을 비워 둔다.")
    return " ".join(out)


def _engine_season(season: int, lk: _Lookups, tables: dict) -> dict:
    usage, docs, events, incons = (
        tables["usage"],
        tables["docs"],
        tables["events"],
        tables["incons"],
    )
    rounds = lk.rounds(season)
    n = len(rounds)
    u = usage[usage["season"] == season] if usage is not None else usage
    has = u is not None and len(u) > 0

    # 공급사와 팀(F1DB 시즌 엔트런트에서 온 계보 테이블)
    teams_season = lk.team_rows[lk.team_rows["season"] == season]
    by_pu: dict[str, dict] = {}
    for r in teams_season.itertuples():
        pu = lk.pu(season, r.constructor_id)
        key = pu["id"] if pu else "unknown"
        entry = by_pu.setdefault(
            key, {"id": key, "name": pu["name"] if pu else "확인 안 됨", "teams": []}
        )
        entry["teams"].append(
            {
                "constructor_id": r.constructor_id,
                "team": lk.team(season, r.constructor_id),
                "lineage_id": lk.lineage(season, r.constructor_id),
            }
        )
    suppliers = sorted(by_pu.values(), key=lambda s: (-len(s["teams"]), s["name"]))
    for s in suppliers:
        s["teams"].sort(key=lambda t: t["team"])

    present = [e for e in ELEMENTS if has and (u["element"] == e).any()]
    elements = present or [
        e
        for e in ELEMENTS
        if tables["rules"] is not None
        and ((tables["rules"]["season"] == season) & (tables["rules"]["element"] == e)).any()
    ]
    allocation = _allocation(
        season, elements, tables["rules"], tables["statements"], tables.get("reg_docs")
    )
    statements = _allocation_statements(season, elements, tables["statements"])

    parsed_rounds: list[int] = []
    partial_rounds: list[int] = []
    unknown_new: list[int] = []
    teams_out: list[dict] = []
    if has:
        # 누적 문서(pu_used)를 읽은 라운드. 그 밖의 행은 선언 문서의 "Previously used"에서 온
        # 일부 드라이버 값이다(basis가 before=previously_used).
        from_used = _col(u, "basis").fillna("").astype(str).str.startswith("before=pu_used")
        parsed_rounds = sorted(int(r) for r in u.loc[from_used, "round"].dropna().unique())
        partial_rounds = sorted(
            int(r) for r in u["round"].dropna().unique() if int(r) not in parsed_rounds
        )
        per_round = u.groupby("round")["new_at_event"].apply(lambda s: s.isna().all())
        unknown_new = sorted(
            int(r) for r, unknown in per_round.items() if unknown and int(r) in parsed_rounds
        )
        value = u["used_after_event"].astype("Float64").fillna(u["used_before_event"])
        u = u.assign(v=value)
        order_cid = sorted(
            u["constructor_id"].unique(),
            key=lambda c: (lk.final_pos.get((season, c), 99), lk.team(season, c)),
        )
        for cid in order_cid:
            g = u[u["constructor_id"] == cid]
            drivers = []
            for did, dg in g.groupby("driver_id"):
                by = {}
                final = {}
                for el in elements:
                    eg = dg[dg["element"] == el]
                    series: list[int | None] = [None] * n
                    for r in eg.itertuples():
                        if 1 <= int(r.round) <= n and not pd.isna(r.v):
                            series[int(r.round) - 1] = int(r.v)
                    by[el] = series
                    known = [x for x in series if x is not None]
                    final[el] = known[-1] if known else None
                driver_rounds = sorted(int(r) for r in dg["round"].unique())
                drivers.append(
                    {
                        "driver_id": did,
                        "name": lk.driver_name.get(did, did),
                        "code": lk.driver_code.get(did),
                        "car_numbers": sorted({int(c) for c in dg["car_number"].dropna()}),
                        "rounds": driver_rounds,
                        "by": by,
                        "final": final,
                        "exceed": [
                            el
                            for el in elements
                            if final.get(el) is not None
                            and allocation.get(el)
                            and final[el] > allocation[el]["allowed"]
                        ],
                    }
                )
            drivers.sort(key=lambda d: (d["rounds"][0], d["car_numbers"][:1]))
            teams_out.append(
                {
                    "constructor_id": cid,
                    "team": lk.team(season, cid),
                    "lineage_id": lk.lineage(season, cid),
                    "pu": lk.pu(season, cid),
                    "drivers": drivers,
                    "race_drivers": lk.race_entrants(season, cid),
                }
            )

    ev_out: list[dict] = []
    if events is not None:
        ev = events[events["season"] == season].sort_values(["round", "car_number"])
        for r in ev.itertuples():
            cid = _str(r.constructor_id)
            ev_out.append(
                {
                    "round": int(r.round),
                    "driver_id": _str(r.driver_id),
                    "name": lk.driver_name.get(r.driver_id, _str(r.driver_name)),
                    "constructor_id": cid,
                    "team": lk.team(season, cid) if cid else None,
                    "car_number": _val(r.car_number),
                    "ice_number": _val(r.ice_number),
                    "printed_previously_used": _val(getattr(r, "printed_previously_used", None)),
                    "stated_ordinal": _val(getattr(r, "stated_ordinal", None)),
                    "within_allocation": _val(r.within_allocation),
                    "conflict": _str(getattr(r, "conflict", None)),
                    "conflict_ko": conflict_ko(_str(getattr(r, "conflict", None))),
                    "url": _str(r.source_url),
                }
            )

    doc_rows = docs[docs["season"] == season] if docs is not None else None
    review_docs = []
    counts: dict[str, dict[str, int]] = {}
    if doc_rows is not None:
        for (dtype, status), g in doc_rows.groupby(["doc_type", "status"]):
            counts.setdefault(str(dtype), {})[str(status)] = int(len(g))
        for r in doc_rows[doc_rows["status"] == "needs_review"].sort_values("round").itertuples():
            ko, short = lk.gp.get(r.event, (r.event, r.event))
            review_docs.append(
                {
                    "round": int(r.round),
                    "event": r.event,
                    "event_ko": ko,
                    "event_short_ko": short,
                    "doc_type": r.doc_type,
                    "url": _str(r.url),
                }
            )
    missing_rounds = [r["round"] for r in rounds if r["round"] not in parsed_rounds]
    n_incons = int((incons["season"] == season).sum()) if incons is not None else 0

    return {
        "season": season,
        "rounds": n,
        "round_labels": rounds,
        "suppliers": suppliers,
        "elements": elements,
        "allocation": allocation,
        "allocation_statements": statements,
        "parsed_rounds": parsed_rounds,
        "missing_rounds": missing_rounds,
        "partial_rounds": partial_rounds,
        "unknown_new_rounds": unknown_new,
        "teams": teams_out,
        "ice_events": ev_out,
        "documents": counts,
        "review_documents": review_docs,
        "inconsistencies": n_incons,
    }


def build_engines() -> dict | None:
    usage = _read(FIA / "pu_usage.parquet")
    if usage is None:
        return None
    tables = {
        "usage": usage,
        "docs": _read(FIA / "pu_documents.csv"),
        "events": _read(FIA / "pu_ice_events.csv"),
        "incons": _read(FIA / "pu_inconsistencies.csv"),
        "rules": _read(REG / "pu_allocation_rules.csv"),
        "statements": _read(FIA / "pu_allocations.csv"),
        "reg_docs": _read(REG / "documents.csv"),
    }
    lk = _Lookups()
    seasons = {
        str(s): _engine_season(s, lk, tables)
        for s in range(PU_ELEMENTS_FIRST_SEASON, LAST_SEASON + 1)
    }
    manifest = _read(MANIFEST_DIR / "fia_documents.csv")
    as_of = None
    if manifest is not None:
        pu_docs = manifest[manifest["doc_type"].isin(["pu_new", "pu_used"])]
        as_of = _kst_date(list(_col(pu_docs, "fetched_at")) + list(_col(pu_docs, "indexed_at")))
    return {
        "first_season": PU_ELEMENTS_FIRST_SEASON,
        "last_season": LAST_SEASON,
        "elements": ELEMENTS,
        "as_of": as_of,
        "seasons": seasons,
        "coverage": [
            {
                "season": int(k),
                "rounds": v["rounds"],
                "parsed_rounds": len(v["parsed_rounds"]),
                "missing_rounds": v["missing_rounds"],
                "partial_rounds": v["partial_rounds"],
                "unknown_new_rounds": v["unknown_new_rounds"],
                "documents": v["documents"],
                "review_documents": len(v["review_documents"]),
                "inconsistencies": v["inconsistencies"],
                "ice_events": len(v["ice_events"]),
                "ice_unsure": sum(e["ice_number"] is None for e in v["ice_events"]),
            }
            for k, v in seasons.items()
        ],
    }


# --- 규정 아카이브 -----------------------------------------------------------------------


def grade_of(year: int) -> str:
    """CLAUDE.md 규정 문서 등급: A 2008-, B 2001-2007, C 1982-2000."""
    if year >= 2008:
        return "A"
    if year >= 2001:
        return "B"
    return "C"


def _first_sentence(text: str | None) -> str | None:
    if not text:
        return None
    head = text.split(". ")[0].rstrip(".")
    return f"{head}."


REG_STATUS = {"ok": "parsed", "not_downloaded": "listed"}


def _reg_status(status: str | None) -> str:
    """documents.csv의 상태를 사이트 상태로. ok: 조항 파싱, not_downloaded: 목록만 확인."""
    status = status or "listed"
    return REG_STATUS.get(status, status)


def split_problems(text: str | None) -> list[str]:
    """documents.csv problems 칸(" / "로 이음)을 문제 목록으로."""
    return [p.strip() for p in (text or "").split(" / ") if p.strip()]


SOURCE_ERROR = re.compile(
    r"^(?P<page>\d+)쪽: 원문 번호 오류\(렌더링한 쪽에서 확인\)\. 원문에 (?P<no>\S+?)[이가] 두 번 "
    r"찍혀 (?:있다\.\s*|있고\s*)(?P<rest>.*)$"
)
DUPLICATE = re.compile(r"^조항 번호 (?P<no>\S+?)[이가] (?P<n>\d+)번 나온다$")
ORDER = re.compile(r"^(?P<page>\d+)쪽: 조항 번호 순서가 어긋난다\((?P<a>\S+) 다음 (?P<b>\S+)\)$")
GAP = re.compile(r"^(?P<page>\d+)쪽: 조항 번호가 건너뛴다\((?P<a>\S+) 다음 (?P<b>\S+)\)$")
INLINE = re.compile(
    r"^(?P<page>\d+)쪽: (?:들여 쓴 줄|표 안 줄)이 다음 조항 번호로 시작한다\((?P<no>\S+)\)$"
)
MORE = re.compile(r"^외 (?P<n>\d+)건$")


def review_reasons(problems: str | None) -> list[str]:
    """검수 대기 판의 문제(파서가 적은 글)를 사람이 읽을 한국어 설명으로 묶는다.

    렌더링한 쪽에서 확인한 원문 번호 오류는 "FIA 원문에 같은 조항 번호가 두 번 인쇄되어 있다"로
    적는다. 파서가 찾았지만 사람이 확인하지 않은 문제는 종류별로 묶고, 원문 오류인지 파싱 오류인지
    아직 확인하지 않았다고 덧붙인다. 알아보지 못한 글은 그대로 옮긴다.
    """
    items = split_problems(problems)
    if not items:
        return []
    out: list[str] = []
    dup: list[str] = []
    order: list[str] = []
    gaps: list[str] = []
    inline: list[str] = []
    other: list[str] = []
    more = 0
    verified = False
    for item in items:
        if m := SOURCE_ERROR.match(item):
            verified = True
            rest = m["rest"].strip().rstrip(".")
            out.append(
                f"FIA 원문에 같은 조항 번호가 두 번 인쇄되어 있다({m['page']}쪽 {m['no']}). "
                "렌더링한 쪽을 보고 확인했다." + (f" {rest}." if rest else "")
            )
        elif m := DUPLICATE.match(item):
            dup.append(m["no"])
        elif m := ORDER.match(item):
            if m["a"] != m["b"]:  # 같은 번호가 이어진 경우는 겹친 번호로 이미 센다
                order.append(f"{m['page']}쪽 {m['a']} 다음 {m['b']}")
        elif m := GAP.match(item):
            gaps.append(f"{m['page']}쪽 {m['a']} 다음 {m['b']}")
        elif m := INLINE.match(item):
            inline.append(f"{m['page']}쪽 {m['no']}")
        elif m := MORE.match(item):
            more += int(m["n"])
        else:
            other.append(item.rstrip("."))
    if dup:
        out.append(f"자동 파싱에서 같은 조항 번호가 두 번 읽혔다({', '.join(dup)}).")
    if order:
        out.append(f"조항 번호 순서가 어긋나는 곳이 있다({', '.join(order)}).")
    if gaps:
        out.append(f"조항 번호가 건너뛰는 곳이 있다({', '.join(gaps)}).")
    if inline:
        out.append(
            "본문 줄이 다음 조항 번호로 시작해 조항 경계를 자동으로 정하지 못했다"
            f"({', '.join(inline)})."
        )
    out += [f"{x}." for x in other]
    if more:
        out.append(f"그 밖에 {more}건이 더 있다.")
    if not verified:
        out.append("원문의 오류인지 파싱의 오류인지 아직 사람이 확인하지 않았다.")
    return out


VARIANT_KO = {"marked": "변경 표시본", "clean": "정리본", "appendix": "부록"}


def _reg_documents(year: int, links, legacy, current) -> list[dict]:
    docs: list[dict] = []
    grade = grade_of(year)
    if year <= 2007 and links is not None:
        rows = links[(links["year"] == year) & (links["status"] == "ok")]
        for r in rows.itertuples():
            url = _str(r.url)
            if not url:
                continue
            docs.append(
                {
                    "section": r.section,
                    "title": _str(r.title),
                    "language": _str(r.language),
                    "issue": None,
                    "version": None,
                    "variant": None,
                    "published_at": None,
                    "url": url,
                    "host": _str(r.host) or _host(url),
                    "format": _str(r.format),
                    "grade": grade,
                    "status": "linked",
                    # 등급 C 문서의 설명은 스캔 내용을 옮긴 문장이 섞여 있어 싣지 않는다.
                    "note_ko": _str(r.note_ko) if grade == "B" else None,
                    "pages": None,
                    "clauses": None,
                    "version_key": None,
                    "problems": [],
                    "review_reasons": [],
                }
            )
    elif 2008 <= year <= 2017 and legacy is not None:
        rows = legacy[(legacy["season"] == year) & (legacy["status"] == "live")]
        rows = rows.drop_duplicates("url").sort_values(["section", "version_date"])
        for r in rows.itertuples():
            url = _str(r.url)
            docs.append(
                {
                    "section": r.section,
                    "title": _str(r.title_in_pdf),
                    "language": _str(r.language),
                    "issue": None,
                    "version": _str(r.version_date),
                    "variant": VARIANT_KO.get(_str(r.variant) or "", _str(r.variant)),
                    "published_at": None,
                    "url": url,
                    "host": _str(r.host) or _host(url),
                    "format": "text" if _val(r.is_text_pdf) in (True, "True", "true") else None,
                    "grade": grade,
                    "status": "linked",
                    "note_ko": None,
                    "pages": _val(r.pages),
                    "clauses": None,
                    "version_key": None,
                    "problems": [],
                    "review_reasons": [],
                }
            )
    elif year >= 2018 and current is not None:
        rows = current[(current["season"] == year) & current["section"].isin(REG_SECTIONS)]
        rows = rows.sort_values(["section", "version_date", "version_key"])
        for r in rows.itertuples():
            url = _str(r.url)
            status = _str(r.status) or "listed"
            review = status == "needs_review"
            problems = _str(getattr(r, "problems", None))
            docs.append(
                {
                    "section": r.section,
                    "title": None,
                    "language": "en",
                    "issue": _str(r.issue),
                    "version": _str(r.version_date),
                    "version_key": _str(r.version_key),
                    "variant": _str(r.variant),
                    "published_at": _str(r.published_at),
                    "url": url,
                    "host": _host(url),
                    "format": "text",
                    "grade": grade,
                    # ok: 조항 파싱, needs_review: 검수 대기, not_downloaded: 목록만 확인
                    "status": _reg_status(status),
                    "note_ko": None,
                    "pages": _val(r.pages),
                    "clauses": _val(r.clauses),
                    "problems": split_problems(problems) if review else [],
                    "review_reasons": review_reasons(problems) if review else [],
                }
            )
    return docs


def build_regulations() -> dict | None:
    links = _read(REG / "archive_links.csv")
    current = _read(REG / "documents.csv")
    if links is None and current is None:
        return None
    legacy = _read(MANIFEST_DIR / "fia_regulations_legacy.csv")
    summaries = _read(REG / "change_summaries.csv")
    comparisons = _read(REG / "comparisons.csv")
    changes = _read(REG / "changes.parquet")

    documents: dict[str, list[dict]] = {}
    years: list[dict] = []
    for year in range(REG_FIRST_YEAR, LAST_SEASON + 1):
        docs = _reg_documents(year, links, legacy, current)
        documents[str(year)] = docs
        cells = {}
        for section in REG_SECTIONS:
            mine = [d for d in docs if d["section"] == section]
            note = None
            if not mine and links is not None and year <= 2007:
                miss = links[(links["year"] == year) & (links["section"] == section)]
                if len(miss):
                    note = _first_sentence(_str(miss.iloc[0]["note_ko"]))
            primary = None
            if mine:
                parsed = [d for d in mine if d["status"] == "parsed"]
                # 대표 링크: 조항을 파싱한 판, 없으면 가장 늦은 판(목록 끝)
                primary = (parsed or mine)[-1]["url"]
            cells[section] = {
                "found": bool(mine),
                "count": len(mine),
                "url": primary,
                "scan": any(d["format"] == "scan" for d in mine),
                "parsed": sum(d["status"] == "parsed" for d in mine),
                "review": sum(d["status"] == "needs_review" for d in mine),
                "note": note,
            }
        n_sum = 0
        if summaries is not None:
            n_sum = int((summaries["year"] == year).sum())
        years.append({"year": year, "grade": grade_of(year), **cells, "summaries": n_sum})

    summaries_out: dict[str, list[dict]] = {}
    if summaries is not None:
        for r in summaries.sort_values(["year", "section"], kind="stable").itertuples():
            url = _str(r.source_url)
            summaries_out.setdefault(str(int(r.year)), []).append(
                {
                    "section": r.section,
                    "summary_ko": _str(r.summary_ko),
                    "source_url": url,
                    "source_host": _host(url),
                    "verified_on": _str(r.verified_on),
                }
            )

    def _skipped_versions(text: str | None, section: str) -> list[dict]:
        """comparisons.csv skipped_versions("시즌:판 키"를 ;로 이음)를 판 정보 목록으로."""
        out = []
        for token in [t.strip() for t in (text or "").split(";") if t.strip()]:
            season_text, _, version = token.partition(":")
            season = int(season_text)
            hit = None
            if current is not None:
                rows = current[
                    (current["season"] == season)
                    & (current["section"] == section)
                    & (current["version_key"].astype(str) == version)
                ]
                hit = rows.iloc[0] if len(rows) else None
            status = _str(hit["status"]) if hit is not None else None
            out.append(
                {
                    "season": season,
                    "version": version,
                    "issue": _str(hit["issue"]) if hit is not None else None,
                    "url": _str(hit["url"]) if hit is not None else None,
                    "status": _reg_status(status) if status else None,
                    "review_reasons": review_reasons(_str(hit["problems"]))
                    if status == "needs_review"
                    else [],
                }
            )
        return out

    comps: list[dict] = []
    if comparisons is not None:
        for c in comparisons.sort_values(["to_season", "section"]).itertuples():
            rows = []
            if changes is not None:
                sel = changes[
                    (changes["section"] == c.section)
                    & (changes["from_version"] == c.from_version)
                    & (changes["to_version"] == c.to_version)
                    # 판 키는 날짜라 두 시즌 규정이 같은 날 나오면 겹친다(2020-05-27).
                    & (changes["from_season"] == c.from_season)
                    & (changes["to_season"] == c.to_season)
                ]
                for r in sel.itertuples():
                    rows.append(
                        {
                            "clause_no": _str(r.clause_no),
                            "top_article": _str(r.top_article),
                            "top_title": _str(r.top_title),
                            "heading": _str(r.heading),
                            "change": _str(r.change),
                            "renumbered": bool(_val(getattr(r, "renumbered", False))),
                            "from_clause_no": _str(getattr(r, "from_clause_no", None)),
                            "page_from": _val(r.page_from),
                            "page_to": _val(r.page_to),
                        }
                    )

            def doc_url(season: int, version: str, section: str = c.section) -> str | None:
                if current is None:
                    return None
                hit = current[
                    (current["season"] == season)
                    & (current["section"] == section)
                    & (current["version_key"].astype(str) == str(version))
                ]
                return _str(hit.iloc[0]["url"]) if len(hit) else None

            def doc_issue(season: int, version: str, section: str = c.section) -> str | None:
                if current is None:
                    return None
                hit = current[
                    (current["season"] == season)
                    & (current["section"] == section)
                    & (current["version_key"].astype(str) == str(version))
                ]
                return _str(hit.iloc[0]["issue"]) if len(hit) else None

            skipped = _skipped_versions(_str(getattr(c, "skipped_versions", None)), c.section)
            comps.append(
                {
                    "kind": c.kind,
                    "section": c.section,
                    "from_season": int(c.from_season),
                    "from_version": str(c.from_version),
                    "from_issue": doc_issue(int(c.from_season), c.from_version),
                    "from_url": doc_url(int(c.from_season), c.from_version),
                    "to_season": int(c.to_season),
                    "to_version": str(c.to_version),
                    "to_issue": doc_issue(int(c.to_season), c.to_version),
                    "to_url": doc_url(int(c.to_season), c.to_version),
                    "clauses_from": _val(c.clauses_from),
                    "clauses_to": _val(c.clauses_to),
                    "added": _val(c.added),
                    "removed": _val(c.removed),
                    "modified": _val(c.modified),
                    "unchanged": _val(c.unchanged),
                    "renumbered": _val(getattr(c, "renumbered", None)),
                    "skipped_versions": skipped,
                    "review": bool(skipped),
                    "changes": rows,
                }
            )

    facts: dict[str, list[dict]] = {}
    pu_rules = _read(REG / "pu_allocation_rules.csv")
    fuel_rules = _read(REG / "fuel_rules.csv")
    if pu_rules is not None:
        for r in pu_rules.sort_values(["season"], kind="stable").itertuples():
            season = int(r.season)
            facts.setdefault(str(season), []).append(
                {
                    "kind": "pu_allocation",
                    "section": "sporting",
                    "rule": "pu_allocation",
                    "element": _str(r.element),
                    "value": f"{_val(r.allowed)}개",
                    "clause_no": _str(r.clause_no),
                    "page": _val(r.page),
                    "url": _str(r.url),
                    **_fact_source(r._asdict(), current, season, "sporting"),
                }
            )
    if fuel_rules is not None:
        for r in fuel_rules.sort_values(["season"], kind="stable").itertuples():
            season = int(r.season)
            facts.setdefault(str(season), []).append(
                {
                    "kind": "fuel",
                    "section": _str(r.section),
                    "rule": _str(r.rule),
                    "element": None,
                    "value": _str(r.value),
                    "clause_no": _str(r.clause_no),
                    "page": _val(r.page),
                    "url": _str(r.url),
                    **_fact_source(r._asdict(), current, season, _str(r.section) or "sporting"),
                }
            )

    stamps: list[object] = []
    if links is not None:
        stamps += list(_col(links, "checked_on"))
    if legacy is not None:
        stamps += list(_col(legacy, "checked_at"))
    cur_manifest = _read(MANIFEST_DIR / "fia_regulations.csv")
    if cur_manifest is not None:
        stamps += list(_col(cur_manifest, "indexed_at")) + list(_col(cur_manifest, "fetched_at"))
    return {
        "first_year": REG_FIRST_YEAR,
        "last_year": LAST_SEASON,
        "as_of": _kst_date(stamps),
        "summaries_verified_on": _kst_date(
            list(_col(summaries, "verified_on")) if summaries is not None else []
        ),
        "years": years,
        "documents": documents,
        "summaries": summaries_out,
        "comparisons": comps,
        "facts": facts,
    }


BUILDERS: dict[str, Callable[[], dict | None]] = {
    "engines.json": build_engines,
    "regulations.json": build_regulations,
}
