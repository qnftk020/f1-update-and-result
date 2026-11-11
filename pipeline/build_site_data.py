"""data/curated 의 정제 데이터를 사이트 빌드용 JSON으로 내보낸다.

사이트는 서버 코드 없이 여기서 만든 JSON만 읽는다. 화면에 올리는 수치는 모두 이 파일을 거치므로
어느 정제 테이블에서 왔는지 따라갈 수 있다. 내보내는 파일:

    meta.json               기준일, 범위, 출처별 수집 정보
    labels.json             화면 표기용 한글 이름(대회, 부품 영역, 변경 사유 등)
    seasons.json            시즌 목록과 챔피언
    season/<연도>.json      대회, 순위 추이, 팀별 페이스 지수
    teams.json              2025 그리드 10개 계보 요약
    team/<계보>.json        계보 구간, 근거, 시즌별 성적과 지수
    upgrades.json           Car Presentation 업그레이드 항목 전체
    home.json               최신 대회 요약
    engines.json            PU 공급사와 구성요소 사용 현황 (정제 테이블이 있을 때)
    regulations.json        규정 아카이브 (정제 테이블이 있을 때)

실행: uv run python -m pipeline.build_site_data
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

from pipeline import manifest
from pipeline.config import CURATED_DIR, LAST_SEASON, MANIFEST_DIR, SITE_DATA_DIR

KST = timezone(timedelta(hours=9))
QUALI_FIRST_SEASON = 1996
RACE_INDEX_FIRST_SEASON = 2023
UPGRADES_FIRST_SEASON = 2023

COMPONENT_AREAS_KO = {
    "front_wing": "프런트 윙",
    "nose": "노즈",
    "front_suspension": "프런트 서스펜션",
    "front_corner": "프런트 코너",
    "floor": "플로어",
    "diffuser": "디퓨저",
    "sidepod": "사이드포드",
    "engine_cover": "엔진 커버와 냉각",
    "cockpit": "콕핏 주변",
    "rear_suspension": "리어 서스펜션",
    "rear_corner": "리어 코너",
    "rear_wing": "리어 윙",
    "beam_wing": "빔 윙",
    "other": "기타",
}
REASON_CATEGORIES_KO = {
    "performance": "성능",
    "circuit_specific": "서킷 대응",
    "reliability": "신뢰성",
    "other": "기타",
}
LINK_TYPES_KO = {
    "origin": "출발",
    "acquired": "인수",
    "renamed": "명칭 변경",
    "entry_purchase": "참가권 인수",
}
QUALI_FORMATS_KO = {
    "ONE_SESSION": "단일 세션",
    "ONE_LAP": "원랩",
    "AGGREGATE": "합산",
    "KNOCKOUT": "녹아웃",
    "ELIMINATION": "엘리미네이션",
    "SPRINT_RACE": "스프린트 주말 녹아웃",
}
# 업그레이드 문서의 팀 상태. "문서 부재"는 그 대회의 공개 문서를 찾지 못했다는 뜻이다.
TEAM_STATUS_KO = {
    "updates": "제출",
    "no_updates": "변경 0건",
    "needs_review": "검수 대기",
    "nodoc": "문서 부재",
}
CATEGORY_ORDER = ["performance", "circuit_specific", "reliability", "other"]
# 지수의 내보내기 자릿수. 화면은 퀄리파잉 지수를 소수 셋째 자리, 레이스 지수를 둘째 자리로 적는다.
# 반올림을 두 번 하면 끝자리가 어긋날 수 있어(0.24451 -> 0.2445 -> 0.244)
# 화면 자릿수보다 넉넉히 남긴다.
QUALI_DIGITS = 9
RACE_DIGITS = 6


# --- 도우미 ---------------------------------------------------------------------------


def write_json(name: str, payload: object) -> None:
    path = SITE_DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(text, encoding="utf-8")


def clean(value: object, digits: int | None = None) -> object:
    """NaN과 NaT를 None으로, numpy 값을 파이썬 값으로 바꾼다."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float | int) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return None
        number = float(value)
        if digits is not None:
            return round(number, digits)
        return int(number) if number.is_integer() else number
    if hasattr(value, "item"):
        return clean(value.item(), digits)
    if pd.isna(value) if not isinstance(value, list | dict | str) else False:
        return None
    return value


def quartiles(values: list[float]) -> dict | None:
    """가운데 절반 띠와 중앙값. 값이 넷 미만이면 띠를 그리지 않는다(None)."""
    vals = sorted(v for v in values if v is not None)
    if len(vals) < 4:
        return None
    q = statistics.quantiles(vals, n=4, method="inclusive")
    return {
        "q1": round(q[0], QUALI_DIGITS),
        "med": round(statistics.median(vals), QUALI_DIGITS),
        "q3": round(q[2], QUALI_DIGITS),
    }


def kst_date(iso_utc: str) -> str:
    """UTC 시각 문자열을 한국 날짜(YYYY-MM-DD)로 바꾼다."""
    text = iso_utc.replace("Z", "+00:00")
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(KST).strftime("%Y-%m-%d")


class Tables:
    """정제 테이블을 한 번만 읽어 둔다."""

    def __init__(self) -> None:
        con = duckdb.connect()

        def read(relative: str) -> pd.DataFrame:
            return con.execute(f"select * from '{CURATED_DIR / relative}'").df()

        self.races = read("jolpica/races.parquet")
        self.results = read("jolpica/results.parquet")
        self.qualifying = read("jolpica/qualifying.parquet")
        self.driver_standings = read("jolpica/driver_standings.parquet")
        self.constructor_standings = read("jolpica/constructor_standings.parquet")
        self.drivers = read("jolpica/drivers.parquet")
        self.constructors = read("jolpica/constructors.parquet")
        self.f1db_races = read("f1db/races.parquet")
        self.engines = read("f1db/engine_manufacturers.parquet")
        self.constructor_seasons = read("lineage/constructor_seasons.parquet")
        self.quali_index = read("pace/qualifying_index.parquet")
        # 화면의 퀄리파잉 지수는 ms 기록에서 다시 계산한 값이다. 정제 테이블의 index_pct는 소수 넷째
        # 자리로 저장되어 있어 셋째 자리 반올림이 어긋날 수 있다(2025 R24 McLaren 0.2445 -> 0.245).
        qi = self.quali_index
        exact = (qi["team_best_ms"] / qi["session_best_ms"] - 1) * 100
        has_ms = qi["team_best_ms"].notna() & qi["session_best_ms"].notna()
        self.quali_index["v"] = exact.where(has_ms, qi["index_pct"])
        self.race_index = read("pace/race_index.parquet")
        self.upgrades = read("fia/car_presentation.parquet")
        self.upgrade_teams = pd.read_csv(CURATED_DIR / "fia" / "car_presentation_teams.csv")
        self.upgrade_docs = pd.read_csv(CURATED_DIR / "fia" / "car_presentation_documents.csv")
        self.lineages = pd.read_csv(CURATED_DIR / "lineage" / "lineages.csv")
        self.lineage_links = pd.read_csv(CURATED_DIR / "lineage" / "lineage_links.csv")
        self.lineage_evidence = pd.read_csv(CURATED_DIR / "lineage" / "lineage_evidence.csv")
        self.gp_ko = pd.read_csv(CURATED_DIR / "labels" / "grand_prix_ko.csv")
        # 차량 공유로 결승 1번 그리드 드라이버가 여럿인 대회의 폴 시터(f1db 예선 1위 근거)
        shared_poles = pd.read_csv(CURATED_DIR / "labels" / "pole_shared_cars.csv")
        self.shared_poles = {
            (int(r.season), int(r.round)): (r.driver_id, r.constructor_id)
            for r in shared_poles.itertuples()
        }

        self.driver_names = {
            r.driver_id: f"{r.forename} {r.surname}".strip() for r in self.drivers.itertuples()
        }
        self.driver_codes = {
            r.driver_id: (r.abbreviation if isinstance(r.abbreviation, str) else None)
            for r in self.drivers.itertuples()
        }
        self.constructor_names = {r.constructor_id: r.name for r in self.constructors.itertuples()}
        self.season_team = {
            (int(r.season), r.constructor_id): r for r in self.constructor_seasons.itertuples()
        }
        self.engine_names = {r.engine_manufacturer_id: r.name for r in self.engines.itertuples()}
        self.gp_names = {r.race_name: (r.name_ko, r.short_ko) for r in self.gp_ko.itertuples()}
        # 시즌별 컨스트럭터의 결승 출전 대회 수, 우승, 포디움(완주 분류 3위 이내).
        # 결승 결과에서 센다.
        race = self.results[self.results["session_type"] == "R"]
        self.race_tally: dict[tuple[int, str], dict[str, int]] = {}
        for (season, cid), g in race.groupby(["season", "constructor_id"]):
            classified = g[g["is_classified"].fillna(False).astype(bool)]
            self.race_tally[(int(season), cid)] = {
                "entered": int(g["round"].nunique()),
                "wins": int(g.loc[g["position"] == 1, "round"].nunique()),
                "podiums": int((classified["position"] <= 3).sum()),
            }

    def team_name(self, season: int, constructor_id: str) -> str:
        row = self.season_team.get((season, constructor_id))
        if row is not None and isinstance(row.team_name, str):
            return row.team_name
        return self.constructor_names.get(constructor_id, constructor_id)

    def lineage_of(self, season: int, constructor_id: str) -> str | None:
        row = self.season_team.get((season, constructor_id))
        if row is not None and isinstance(row.lineage_id, str):
            return row.lineage_id
        return None

    def pu_of(self, season: int, constructor_id: str) -> dict | None:
        row = self.season_team.get((season, constructor_id))
        if row is None or not isinstance(row.pu_manufacturer_id, str):
            return None
        pu = row.pu_manufacturer_id
        # 한 시즌에 엔진 제조사가 여럿이면 ID가 '|'로 이어져 있으므로 각각 이름을 찾는다.
        name = ", ".join(self.engine_names.get(p, p) for p in pu.split("|"))
        return {"id": pu, "name": name}

    def driver(self, driver_id: str) -> dict:
        return {
            "id": driver_id,
            "name": self.driver_names.get(driver_id, driver_id),
            "code": self.driver_codes.get(driver_id),
        }

    def gp(self, race_name: str) -> tuple[str, str]:
        if race_name not in self.gp_names:
            raise KeyError(
                f"대회 한글 이름이 없다: {race_name} (data/curated/labels/grand_prix_ko.csv)"
            )
        return self.gp_names[race_name]


# --- 시즌 ------------------------------------------------------------------------------


def raced_rounds(t: Tables, season: int) -> set[int]:
    """결승 결과가 들어온 라운드 번호. 진행 중인 시즌에는 일정상 라운드보다 적다."""
    results = t.results[(t.results["season"] == season) & (t.results["session_type"] == "R")]
    return {int(r) for r in results["round"].unique()}


def pole_sitter(
    t: Tables, season: int, rnd: int, res: pd.DataFrame, fmt: str | None
) -> tuple[str, str] | None:
    """폴 시터 한 명을 (driver_id, constructor_id)로 고른다.

    기본은 결승 1번 그리드다. 벌칙으로 1번 그리드가 바뀐 대회도 공식 기록은 그리드를 따른다.
    2022년 스프린트 주말(f1db SPRINT_RACE)은 결승 1번 그리드가 스프린트 우승자이므로 예선 1위를
    쓴다. 2021년은 스프린트 우승자가 폴 기록을 받았으므로 그리드를 그대로 쓴다. 차량 공유로
    1번 그리드 드라이버가 여럿이면 큐레이션 표(data/curated/labels/pole_shared_cars.csv)를 따르고,
    표에 없으면 빌드를 멈춘다.
    """
    if fmt == "SPRINT_RACE" and season >= 2022:
        quali = t.qualifying[
            (t.qualifying["season"] == season)
            & (t.qualifying["round"] == rnd)
            & (t.qualifying["position"] == 1)
        ]
        pairs = zip(quali["driver_id"], quali["constructor_id"], strict=True)
        candidates = list(dict.fromkeys(pairs))
        if len(candidates) != 1:
            raise ValueError(f"{season} R{rnd} 예선 1위를 하나로 정할 수 없다: {candidates}")
        return candidates[0]
    grid = res[res["grid"] == 1]
    candidates = list(dict.fromkeys(zip(grid["driver_id"], grid["constructor_id"], strict=True)))
    if len({d for d, _ in candidates}) <= 1:
        return candidates[0] if candidates else None
    if (season, rnd) not in t.shared_poles:
        raise ValueError(
            f"{season} R{rnd} 결승 1번 그리드가 여러 명이다: {candidates}."
            " data/curated/labels/pole_shared_cars.csv에 폴 시터를 기록해야 한다"
        )
    return t.shared_poles[(season, rnd)]


def season_rounds(t: Tables, season: int) -> list[dict]:
    races = t.races[t.races["season"] == season].sort_values("round")
    results = t.results[(t.results["season"] == season) & (t.results["session_type"] == "R")]
    formats = {
        int(r.round): r.qualifying_format
        for r in t.f1db_races[t.f1db_races["season"] == season].itertuples()
    }
    quali = t.quali_index[t.quali_index["season"] == season]
    quali_by_round = {int(k): g.iloc[0] for k, g in quali.groupby("round")}
    # 그 대회 필드(지수가 있는 모든 팀)의 중앙값과 가운데 절반. 차트의 회색 선과 띠다.
    field_by_round = {
        int(k): (quartiles([clean(v) for v in g["v"]]), int(g["v"].notna().sum()))
        for k, g in quali.groupby("round")
    }
    race = t.race_index[t.race_index["season"] == season]
    race_by_round = {int(k): g.iloc[0] for k, g in race.groupby("round")}
    rounds = []
    for r in races.itertuples():
        rnd = int(r.round)
        name_ko, short_ko = t.gp(r.race_name)
        res = results[results["round"] == rnd]
        winners = res[res["position"] == 1]
        q = quali_by_round.get(rnd)
        x = race_by_round.get(rnd)
        fmt = formats.get(rnd)
        pole = pole_sitter(t, season, rnd, res, fmt)
        rounds.append(
            {
                "round": rnd,
                "name": r.race_name,
                "name_ko": name_ko,
                "short_ko": short_ko,
                "date": str(r.date)[:10],
                "circuit": r.circuit_name,
                "locality": r.locality,
                "country": r.country,
                "has_sprint": bool(r.has_sprint),
                # 공동 우승(1951, 1956, 1957년의 차량 공유)은 여러 명이다.
                "winners": [
                    {
                        **t.driver(w.driver_id),
                        "constructor_id": w.constructor_id,
                        "constructor": t.team_name(season, w.constructor_id),
                    }
                    for w in winners.itertuples()
                ],
                # 폴은 많아야 한 명이다. 목록 모양은 화면 타입(EntryRef[])에 맞춘 것이다.
                "pole": []
                if pole is None
                else [
                    {
                        **t.driver(pole[0]),
                        "constructor_id": pole[1],
                        "constructor": t.team_name(season, pole[1]),
                    }
                ],
                "quali": None
                if q is None
                else {
                    "format": fmt,
                    "format_ko": QUALI_FORMATS_KO.get(fmt, fmt),
                    "reference": bool(q.is_reference_format),
                    "wet": q.wet_flag,
                    "source": q.time_source,
                    "best_ms": clean(q.session_best_ms),
                    "field": field_by_round[rnd][0],
                    "teams": field_by_round[rnd][1],
                },
                "race": None if x is None else {"wet": bool(x.is_wet), "laps": clean(x.race_laps)},
            }
        )
    return rounds


def standings_series(
    standings: pd.DataFrame, key: str, rounds: list[int]
) -> dict[str, dict[str, list]]:
    """참가자별로 라운드 순서의 순위와 누적 점수를 만든다. 기록이 없는 라운드는 None이다."""
    out: dict[str, dict[str, list]] = {}
    index = {rnd: i for i, rnd in enumerate(rounds)}
    for row in standings.itertuples():
        entry = out.setdefault(
            getattr(row, key),
            {"positions": [None] * len(rounds), "points": [None] * len(rounds), "wins": 0},
        )
        i = index.get(int(row.round))
        if i is None:
            continue
        entry["positions"][i] = clean(row.position)
        entry["points"][i] = clean(row.points)
        entry["wins"] = max(entry["wins"], int(row.wins or 0))
    return out


def last_value(values: list) -> object:
    for v in reversed(values):
        if v is not None:
            return v
    return None


def build_season(t: Tables, season: int) -> dict:
    rounds = season_rounds(t, season)
    round_numbers = [r["round"] for r in rounds]
    results = t.results[(t.results["season"] == season) & (t.results["session_type"] == "R")]

    ds = t.driver_standings[t.driver_standings["season"] == season]
    driver_series = standings_series(ds, "driver_id", round_numbers)
    teams_of_driver: dict[str, list[str]] = {}
    last_team: dict[str, str] = {}
    for row in results.sort_values("round").itertuples():
        seen = teams_of_driver.setdefault(row.driver_id, [])
        if row.constructor_id not in seen:
            seen.append(row.constructor_id)
        last_team[row.driver_id] = row.constructor_id
    drivers = []
    for driver_id, series in driver_series.items():
        drivers.append(
            {
                **t.driver(driver_id),
                "constructor_ids": teams_of_driver.get(driver_id, []),
                "constructors": [
                    t.team_name(season, c) for c in teams_of_driver.get(driver_id, [])
                ],
                # 마지막으로 결승에 나간 팀. 순위표의 팀 칸과 리드 문장의 괄호에 쓴다.
                "team": t.team_name(season, last_team[driver_id])
                if driver_id in last_team
                else None,
                "position": last_value(series["positions"]),
                "final_points": last_value(series["points"]),
                "wins": series["wins"],
                "positions": series["positions"],
                "points": series["points"],
            }
        )
    drivers.sort(key=lambda d: (d["position"] is None, d["position"] or 0, d["name"]))

    cs = t.constructor_standings[t.constructor_standings["season"] == season]
    constructor_series = standings_series(cs, "constructor_id", round_numbers)
    quali = t.quali_index[t.quali_index["season"] == season]
    race = t.race_index[t.race_index["season"] == season]
    entered = list(
        dict.fromkeys(results.sort_values(["round", "constructor_id"])["constructor_id"])
    )
    constructor_ids = list(dict.fromkeys([*constructor_series, *entered, *quali["constructor_id"]]))
    index = {rnd: i for i, rnd in enumerate(round_numbers)}
    quali_wet = [bool(r["quali"] and r["quali"]["wet"] == "wet") for r in rounds]
    race_wet = [bool(r["race"] and r["race"]["wet"]) for r in rounds]
    constructors = []
    for cid in constructor_ids:
        series = constructor_series.get(cid)
        qi = [None] * len(round_numbers)
        for row in quali[quali["constructor_id"] == cid].itertuples():
            qi[index[int(row.round)]] = clean(row.v, QUALI_DIGITS)
        ri = [None] * len(round_numbers)
        for row in race[race["constructor_id"] == cid].itertuples():
            value = clean(row.index_pct, RACE_DIGITS)
            ri[index[int(row.round)]] = (
                None
                if value is None
                else {
                    "v": value,
                    "lo": clean(row.ci_low_pct, RACE_DIGITS),
                    "hi": clean(row.ci_high_pct, RACE_DIGITS),
                    "n": clean(row.clean_laps),
                }
            )
        # 시즌 평균: 우천 예선(2023년부터 판정)과 우천 결승을 뺀 대회의 평균이다. 2022년 이전 예선은
        # 우천 여부가 미분류라 모든 예선이 들어간다. 작은 다중 칸 제목과 팀 페이지 리드에 쓴다.
        q_vals = [v for v, wet in zip(qi, quali_wet, strict=True) if v is not None and not wet]
        r_vals = [x["v"] for x, wet in zip(ri, race_wet, strict=True) if x is not None and not wet]
        constructors.append(
            {
                "id": cid,
                "name": t.team_name(season, cid),
                "lineage_id": t.lineage_of(season, cid),
                "pu": t.pu_of(season, cid),
                "position": last_value(series["positions"]) if series else None,
                "final_points": last_value(series["points"]) if series else None,
                "wins": series["wins"] if series else None,
                "positions": series["positions"] if series else None,
                "points": series["points"] if series else None,
                "quali_index": qi if any(v is not None for v in qi) else None,
                "race_index": ri if any(v is not None for v in ri) else None,
                "quali_mean": round(statistics.fmean(q_vals), QUALI_DIGITS) if q_vals else None,
                "quali_n": len(q_vals),
                "race_mean": round(statistics.fmean(r_vals), RACE_DIGITS) if r_vals else None,
                "race_n": len(r_vals),
            }
        )
    constructors.sort(
        key=lambda c: (c["position"] is None, c["position"] or 0, c["name"].casefold())
    )
    return {
        "season": season,
        "rounds": rounds,
        "drivers": drivers,
        "constructors": constructors,
        "has_constructor_standings": bool(len(cs)),
        "has_quali_index": bool(len(quali)),
        "has_race_index": bool(len(race)),
        "facts": season_facts(rounds, drivers, constructors),
    }


def last_lead_change(rounds: list[dict], entries: list[dict], key: str) -> dict | None:
    """순위표 1위가 마지막으로 바뀐 라운드와 그 뒤의 1위. 순위가 없는 라운드는 건너뛴다."""
    leaders: list[tuple[int, str]] = []
    for i, rnd in enumerate(rounds):
        top = [e[key] for e in entries if e["positions"] and e["positions"][i] == 1]
        if top:
            leaders.append((rnd["round"], top[0]))
    if not leaders:
        return None
    change = leaders[0][0]
    for (_, prev), (rnd, cur) in zip(leaders, leaders[1:], strict=False):
        if cur != prev:
            change = rnd
    return {"round": change, "leader_id": leaders[-1][1], "first_round": leaders[0][0]}


def season_facts(rounds: list[dict], drivers: list[dict], constructors: list[dict]) -> dict:
    """사실 줄, 캘린더 문장, 순위 추이 문장에 쓰는 시즌 집계. 모두 rounds와 순위표에서 센다."""
    winners: list[str] = []
    for r in rounds:
        for w in r["winners"]:
            if w["id"] not in winners:
                winners.append(w["id"])
    quali = [r for r in rounds if r["quali"]]
    reference = [r for r in quali if r["quali"]["reference"]]
    return {
        "races": len(rounds),
        "sprints": [r["round"] for r in rounds if r["has_sprint"]],
        "winners": len(winners),
        "quali_rounds": len(quali),
        "quali_wet": [r["round"] for r in quali if r["quali"]["wet"] == "wet"],
        "quali_unclassified": [r["round"] for r in quali if r["quali"]["wet"] == "unclassified"],
        "quali_reference": [r["round"] for r in reference],
        "quali_reference_formats": sorted({r["quali"]["format_ko"] for r in reference}),
        "race_index_rounds": sum(1 for r in rounds if r["race"]),
        "race_wet": [r["round"] for r in rounds if r["race"] and r["race"]["wet"]],
        "driver_lead": last_lead_change(rounds, drivers, "id"),
        "constructor_lead": last_lead_change(
            rounds, [c for c in constructors if c["positions"]], "id"
        ),
    }


def season_summary(season_data: dict) -> dict:
    # 마지막 일정 라운드의 순위가 들어오기 전에는 현재 1위를 챔피언으로 적지 않는다.
    complete = any(
        d["positions"] and d["positions"][-1] is not None for d in season_data["drivers"]
    )
    drivers = [d for d in season_data["drivers"] if complete and d["position"] == 1]
    constructors = [c for c in season_data["constructors"] if complete and c["position"] == 1]
    return {
        "season": season_data["season"],
        "rounds": len(season_data["rounds"]),
        "champion_driver": None
        if not drivers
        else {k: drivers[0][k] for k in ("id", "name", "constructors", "final_points")},
        "champion_constructor": None
        if not constructors
        else {k: constructors[0][k] for k in ("id", "name", "final_points")},
        "has_quali_index": season_data["has_quali_index"],
        "has_race_index": season_data["has_race_index"],
    }


# --- 팀(계보) --------------------------------------------------------------------------


def _raw_index(table: pd.DataFrame, season: int, constructor_id: str) -> dict[int, float]:
    """라운드별 지수 원값(반올림 전). 결측(NaN)인 라운드는 빠진다."""
    rows = table[(table["season"] == season) & (table["constructor_id"] == constructor_id)]
    return {
        int(r.round): float(r.index_pct)
        for r in rows.itertuples()
        if clean(r.index_pct) is not None
    }


def name_history(segments: list[dict]) -> list[str]:
    """계보 구간의 팀 이름 변천. 이웃한 구간의 같은 이름은 하나로 줄이고 재등장은 남긴다."""
    names = [s["team_name"] for s in segments]
    return [n for i, n in enumerate(names) if i == 0 or n != names[i - 1]]


def season_field(data: dict) -> tuple[dict | None, list[float]]:
    """시즌 평균 퀄리파잉 지수의 필드.

    그 시즌 마른(미분류 포함) 예선의 절반 이상에 지수가 있는 팀들의 시즌 평균에서 구한
    중앙값과 가운데 절반이다. 대체 출전으로 몇 대회만 나온 팀은 뺀다.
    """
    rounds = sum(1 for r in data["rounds"] if r["quali"] and r["quali"]["wet"] != "wet")
    need = max(1, rounds // 2)
    means = [
        c["quali_mean"]
        for c in data["constructors"]
        if c["quali_mean"] is not None and c["quali_n"] >= need
    ]
    return quartiles(means), sorted(means)


def team_timeline(lineage_id: str, seasons: dict[int, dict], upgrades: dict) -> dict:
    """업그레이드 단위 차트의 줄: 시즌마다 라운드별 그 팀의 상태와 범주별 항목 수."""
    docs = {(d["season"], d["round"]): d for d in upgrades["documents"]}
    items: dict[tuple[int, int], list[dict]] = {}
    for i in upgrades["items"]:
        if i["lineage_id"] == lineage_id:
            items.setdefault((i["season"], i["round"]), []).append(i)
    out: dict[str, list[dict]] = {}
    for season in range(UPGRADES_FIRST_SEASON, LAST_SEASON + 1):
        rows = []
        for rnd in seasons[season]["rounds"]:
            key = (season, rnd["round"])
            doc = docs.get(key)
            mine = items.get(key, [])
            status = "nodoc"
            if doc is not None:
                team = next((x for x in doc["teams"] if x["lineage_id"] == lineage_id), None)
                status = team["status"] if team else "nodoc"
            rows.append(
                {
                    "round": rnd["round"],
                    "short": rnd["short_ko"],
                    "name": rnd["name"],
                    "status": status,
                    "doc_review": bool(doc and doc["review"]),
                    "url": doc["url"] if doc else None,
                    "published_at": doc["published_at"] if doc else None,
                    "cats": {c: sum(1 for i in mine if i["category"] == c) for c in CATEGORY_ORDER},
                    "n": len(mine),
                }
            )
        out[str(season)] = rows
    return out


def lineage_totals(rows: list[dict]) -> dict:
    """계보(또는 그 일부 구간)의 시즌, 출전 대회, 우승, 컨스트럭터 챔피언 시즌."""
    return {
        "seasons": len({r["season"] for r in rows}),
        "races": sum(r["entered"] for r in rows),
        "wins": sum(r["race_wins"] for r in rows),
        "podiums": sum(r["podiums"] for r in rows),
        "best_position": min((r["position"] for r in rows if r["position"]), default=None),
        "titles": sorted({r["season"] for r in rows if r["position"] == 1}),
    }


def build_team(t: Tables, lineage: object, seasons: dict[int, dict], upgrades: dict) -> dict:
    lineage_id = lineage.lineage_id
    links = t.lineage_links[t.lineage_links["lineage_id"] == lineage_id].sort_values("season_from")
    evidence = t.lineage_evidence[t.lineage_evidence["lineage_id"] == lineage_id]
    members = t.constructor_seasons[t.constructor_seasons["lineage_id"] == lineage_id]
    rows = []
    for member in members.sort_values(["season", "constructor_id"]).itertuples():
        season = int(member.season)
        data = seasons[season]
        entry = next((c for c in data["constructors"] if c["id"] == member.constructor_id), None)
        field, field_means = season_field(data)
        mean = entry["quali_mean"] if entry else None
        tally = t.race_tally.get((season, member.constructor_id), {})
        # 중앙값은 정제 테이블의 원값으로 내고 한 번만 반올림한다. 시즌 JSON의 대회별 값은 이미
        # 소수 셋째 자리로 반올림되어 있어, 대회 수가 짝수면 가운데 두 값의 평균이 어긋난다.
        raw_quali = _raw_index(t.quali_index, season, member.constructor_id)
        raw_race = _raw_index(t.race_index, season, member.constructor_id)
        dry_quali, all_quali = [], []
        race_values = []
        for rnd in data["rounds"]:
            value = raw_quali.get(rnd["round"])
            if value is not None:
                all_quali.append(value)
                if rnd["quali"] and rnd["quali"]["wet"] != "wet":
                    dry_quali.append(value)
            race_value = raw_race.get(rnd["round"])
            if race_value is not None and rnd["race"] and not rnd["race"]["wet"]:
                race_values.append(race_value)
        quali_formats = {r["quali"]["format"] for r in data["rounds"] if r["quali"]}
        rows.append(
            {
                "season": season,
                "constructor_id": member.constructor_id,
                "team_name": member.team_name,
                "entrant": member.entrant_name if isinstance(member.entrant_name, str) else None,
                "pu": t.pu_of(season, member.constructor_id),
                "position": entry["position"] if entry else None,
                "points": entry["final_points"] if entry else None,
                "wins": entry["wins"] if entry else None,
                "races": len(data["rounds"]),
                # 시즌 요약은 우천 이상값에 덜 흔들리도록 중앙값을 쓴다.
                "quali_index_median": clean(pd.Series(dry_quali).median(), 3)
                if dry_quali
                else None,
                "quali_rounds": len(dry_quali),
                "quali_rounds_all": len(all_quali),
                "quali_wet_unclassified": season < RACE_INDEX_FIRST_SEASON and bool(all_quali),
                "quali_reference": bool(quali_formats & {"ONE_LAP", "AGGREGATE"}),
                "race_index_median": clean(pd.Series(race_values).median(), 3)
                if race_values
                else None,
                "race_rounds": len(race_values),
                # 시즌 평균(ms 기록에서 다시 계산한 지수의 평균).
                # 시즌별 기록 표와 긴 흐름 차트가 쓴다.
                "quali_index_mean": mean,
                "quali_wet_rounds": len(all_quali) - len(dry_quali),
                "quali_field": field,
                # 필드(season_field의 팀들) 가운데 평균이 작은 순서.
                # 자기 팀이 필드에 없으면 None이다.
                "quali_rank": (sum(1 for m in field_means if m < mean) + 1)
                if mean is not None and mean in field_means
                else None,
                "quali_teams": len(field_means),
                "entered": tally.get("entered", 0),
                "race_wins": tally.get("wins", 0),
                "podiums": tally.get("podiums", 0),
            }
        )
    current = t.season_team.get((LAST_SEASON, lineage.constructor_id_2025))
    # 현재 컨스트럭터 시기: 마지막 계보 구간. 계보 보기를 끈 화면의 범위다.
    current_from = int(links.iloc[-1]["season_from"]) if len(links) else LAST_SEASON
    current_rows = [r for r in rows if r["season"] >= current_from]
    last_results = t.results[
        (t.results["season"] == LAST_SEASON)
        & (t.results["session_type"] == "R")
        & (t.results["constructor_id"] == lineage.constructor_id_2025)
    ].sort_values("round")
    timeline = team_timeline(lineage_id, seasons, upgrades)
    mine = [i for i in upgrades["items"] if i["lineage_id"] == lineage_id]
    return {
        "lineage_id": lineage_id,
        "name_ko": lineage.name_ko,
        "base": lineage.base,
        "constructor": {
            "id": lineage.constructor_id_2025,
            "name": t.team_name(LAST_SEASON, lineage.constructor_id_2025),
        },
        "entrant": current.entrant_name if current is not None else None,
        "pu": t.pu_of(LAST_SEASON, lineage.constructor_id_2025),
        "segments": [
            {
                "constructor_id": r.constructor_id,
                "team_name": r.team_name,
                "from": int(r.season_from),
                "to": int(r.season_to),
                "link_type": r.link_type,
                # 한글 표기가 없는 연결 유형은 영문 ID를 화면에 내보내지 않도록 빌드를 멈춘다.
                "link_type_ko": LINK_TYPES_KO[r.link_type],
                "note": r.note if isinstance(r.note, str) else None,
            }
            for r in links.itertuples()
        ],
        "evidence": [
            {
                "constructor_id": r.constructor_id,
                "season_from": int(r.season_from),
                "kind": r.evidence_kind,
                "url": r.evidence_url,
                "quote": r.quote,
                "verified_on": r.verified_on,
            }
            for r in evidence.itertuples()
        ],
        "seasons": rows,
        "current_from": current_from,
        "totals": lineage_totals(rows),
        "totals_current": lineage_totals(current_rows),
        "drivers_last": [t.driver(d) for d in dict.fromkeys(last_results["driver_id"])],
        "upgrades": {
            "items": len(mine),
            "events": len({(i["season"], i["round"]) for i in mine}),
            "by_category": {c: sum(1 for i in mine if i["category"] == c) for c in CATEGORY_ORDER},
            "timeline": timeline,
        },
    }


# --- 업그레이드 ------------------------------------------------------------------------


def build_upgrades(t: Tables) -> dict:
    items = []
    for r in t.upgrades.sort_values(
        ["season", "round", "constructor_id", "row_order"]
    ).itertuples():
        season, rnd = int(r.season), int(r.round)
        name_ko, short_ko = t.gp(r.event)
        items.append(
            {
                "season": season,
                "round": rnd,
                "event": r.event,
                "event_ko": name_ko,
                "event_short_ko": short_ko,
                "constructor_id": r.constructor_id,
                "team": t.team_name(season, r.constructor_id),
                "lineage_id": t.lineage_of(season, r.constructor_id),
                "no": r.item_no,
                "no_inferred": bool(r.item_no_inferred),
                "component": r.updated_component,
                "area": r.component_area,
                "reason": r.primary_reason,
                "category": r.reason_category,
                "category_inferred": bool(r.reason_category_inferred),
                "detail": r.reason_detail,
                "geometry": r.geometric_differences,
                "description": r.description,
                "description_shared": bool(r.description_shared),
                "review": r.document_status != "ok",
                "url": r.source_url,
            }
        )
    documents = []
    for d in t.upgrade_docs.sort_values(["season", "round"]).itertuples():
        name_ko, short_ko = t.gp(d.event)
        teams = t.upgrade_teams[
            (t.upgrade_teams["season"] == d.season) & (t.upgrade_teams["round"] == d.round)
        ]
        documents.append(
            {
                "season": int(d.season),
                "round": int(d.round),
                "event": d.event,
                "event_ko": name_ko,
                "event_short_ko": short_ko,
                "published_at": d.published_at if isinstance(d.published_at, str) else None,
                "url": d.url,
                "items": int(d.rows),
                "review": d.status != "ok",
                "problems": d.problems if isinstance(d.problems, str) else None,
                "teams": [
                    {
                        "constructor_id": x.constructor_id,
                        "team": t.team_name(int(d.season), x.constructor_id),
                        "lineage_id": t.lineage_of(int(d.season), x.constructor_id),
                        "status": x.status,
                        "items": int(x.rows),
                        "page": int(x.page),
                    }
                    for x in teams.sort_values("constructor_id").itertuples()
                ],
            }
        )
    # 목록이 없는 대회(문서를 찾지 못한 대회)를 밝힌다.
    have = {(d["season"], d["round"]) for d in documents}
    missing = []
    for r in (
        t.races[t.races["season"] >= UPGRADES_FIRST_SEASON]
        .sort_values(["season", "round"])
        .itertuples()
    ):
        if (int(r.season), int(r.round)) not in have:
            name_ko, short_ko = t.gp(r.race_name)
            missing.append(
                {
                    "season": int(r.season),
                    "round": int(r.round),
                    "event": r.race_name,
                    "event_ko": name_ko,
                    "event_short_ko": short_ko,
                }
            )
    return {"items": items, "documents": documents, "missing_events": missing}


# --- 홈 --------------------------------------------------------------------------------


def format_gap(ms: float | None, winner_ms: float | None) -> str | None:
    if ms is None or winner_ms is None:
        return None
    return f"+{(ms - winner_ms) / 1000:.3f}"


def format_race_time(ms: float) -> str:
    total = ms / 1000
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{seconds:06.3f}"


def format_lap(ms: float) -> str:
    minutes, seconds = divmod(ms / 1000, 60)
    return f"{int(minutes)}:{seconds:06.3f}"


def build_home(t: Tables, seasons: dict[int, dict], upgrades: dict) -> dict:
    season = LAST_SEASON
    data = seasons[season]
    # 진행 중인 시즌에는 일정상 마지막 라운드가 아니라 결승 결과가 있는 마지막 라운드를 쓴다.
    done = raced_rounds(t, season)
    index = max(i for i, r in enumerate(data["rounds"]) if r["round"] in done)
    last = data["rounds"][index]
    rnd = last["round"]
    res = t.results[
        (t.results["season"] == season)
        & (t.results["round"] == rnd)
        & (t.results["session_type"] == "R")
    ]
    winner_ms = res.loc[res["position"] == 1, "time_ms"]
    winner_ms = clean(winner_ms.iloc[0]) if len(winner_ms) else None
    classification = []
    winner_laps = clean(res.loc[res["position"] == 1, "laps_completed"].max())
    ordered = res.assign(_order=res["position"].fillna(999)).sort_values(["_order", "grid"])
    for r in ordered.itertuples():
        time_ms = clean(r.time_ms)
        laps = clean(r.laps_completed)
        behind = None if laps is None or winner_laps is None else int(winner_laps - laps)
        if r.position == 1 and time_ms is not None:
            time_text = format_race_time(time_ms)
        elif r.is_classified and behind:
            time_text = f"+{behind}랩"  # 한 바퀴 이상 뒤진 차는 시간 차 대신 랩 수 차를 적는다
        elif r.is_classified and time_ms is not None:
            time_text = format_gap(time_ms, winner_ms)
        else:
            time_text = None
        classification.append(
            {
                "position": clean(r.position),
                "classified": bool(r.is_classified),
                **t.driver(r.driver_id),
                "number": clean(r.car_number),
                "constructor_id": r.constructor_id,
                "constructor": t.team_name(season, r.constructor_id),
                "lineage_id": t.lineage_of(season, r.constructor_id),
                "grid": clean(r.grid),
                "laps": clean(r.laps_completed),
                "time": time_text,
                "status": r.status_detail,
                "points": clean(r.points),
                # 랩 기록이 없는 차는 순위가 NULL(pd.NA)이므로 clean()을 거쳐 비교한다.
                "fastest_lap": clean(r.fastest_lap_rank) == 1,
            }
        )
    quali = t.qualifying[(t.qualifying["season"] == season) & (t.qualifying["round"] == rnd)]
    quali = quali[quali["session_type"].isin(["Q1", "Q2", "Q3"])].dropna(subset=["best_time_ms"])
    session_best = None
    if len(quali):
        best = quali.sort_values("best_time_ms").iloc[0]
        session_best = {
            **t.driver(best.driver_id),
            "constructor": t.team_name(season, best.constructor_id),
            "session": best.session_type,
            "time": format_lap(float(best.best_time_ms)),
        }
    pace = []
    for c in data["constructors"]:
        pace.append(
            {
                "constructor_id": c["id"],
                "constructor": c["name"],
                "lineage_id": c["lineage_id"],
                "quali": c["quali_index"][index] if c["quali_index"] else None,
                "race": c["race_index"][index] if c["race_index"] else None,
            }
        )
    documents = [d for d in upgrades["documents"] if d["season"] == season]
    this_weekend = next((d for d in documents if d["round"] == rnd), None)
    latest_with_items = next((d for d in reversed(documents) if d["items"] > 0), None)

    def weekend(doc: dict | None) -> dict | None:
        if doc is None:
            return None
        return {
            **{
                k: doc[k]
                for k in (
                    "season",
                    "round",
                    "event",
                    "event_ko",
                    "event_short_ko",
                    "url",
                    "items",
                    "review",
                )
            },
            "published_at": doc["published_at"],
            "teams": doc["teams"],
            "list": [
                i for i in upgrades["items"] if i["season"] == season and i["round"] == doc["round"]
            ],
        }

    return {
        "season": season,
        "race": last,
        "classification": classification,
        "session_best": session_best,
        "pace": pace,
        "upgrades_this_weekend": weekend(this_weekend),
        "upgrades_latest": weekend(latest_with_items),
        # 순위표는 이 대회가 끝난 뒤의 순위다(시즌이 끝났으면 최종 순위).
        "standings_round": rnd,
        "drivers": [
            {
                **{k: d[k] for k in ("id", "name", "code", "team")},
                "position": d["positions"][index],
                "points": d["points"][index],
                "wins": d["wins"],
            }
            for d in sorted(
                (d for d in data["drivers"] if d["positions"][index] is not None),
                key=lambda d: d["positions"][index],
            )
        ],
        "constructors": [
            {
                **{k: c[k] for k in ("id", "name", "lineage_id")},
                "position": c["positions"][index],
                "points": c["points"][index],
                "wins": c["wins"],
            }
            for c in sorted(
                (c for c in data["constructors"] if c["positions"] and c["positions"][index]),
                key=lambda c: c["positions"][index],
            )
        ],
        **home_pace(t, season, rnd, data),
        "pole": home_pole(t, season, rnd, last),
        "fastest_lap": home_fastest_lap(t, season, rnd, classification),
        "rounds_in_season": len(data["rounds"]),
        "round_counts": [
            {
                "round": d["round"],
                "name_ko": d["event_ko"],
                "short_ko": d["event_short_ko"],
                "n": sum(
                    1
                    for i in upgrades["items"]
                    if i["season"] == season and i["round"] == d["round"]
                ),
                "review": d["review"],
            }
            for d in documents
        ],
    }


def home_pace(t: Tables, season: int, rnd: int, data: dict) -> dict:
    """페이스 스냅샷: 퀄리파잉 지수(빠른 순, ms에서 다시 계산)와 레이스 지수(빠른 순)."""
    q = t.quali_index[(t.quali_index["season"] == season) & (t.quali_index["round"] == rnd)]
    quali = []
    for r in q.itertuples():
        v = clean(r.v, QUALI_DIGITS)
        team_ms = clean(r.team_best_ms)
        quali.append(
            {
                "constructor_id": r.constructor_id,
                "constructor": t.team_name(season, r.constructor_id),
                "lineage_id": t.lineage_of(season, r.constructor_id),
                "v": v,
                "gap_s": None
                if team_ms is None
                else round((team_ms - float(r.session_best_ms)) / 1000, 3),
                "team_best_ms": team_ms,
            }
        )
    quali.sort(key=lambda d: (d["v"] is None, d["v"] or 0))
    first = q.iloc[0] if len(q) else None
    x = t.race_index[(t.race_index["season"] == season) & (t.race_index["round"] == rnd)]
    race = [
        {
            "constructor_id": r.constructor_id,
            "constructor": t.team_name(season, r.constructor_id),
            "lineage_id": t.lineage_of(season, r.constructor_id),
            "v": clean(r.index_pct, RACE_DIGITS),
            "lo": clean(r.ci_low_pct, RACE_DIGITS),
            "hi": clean(r.ci_high_pct, RACE_DIGITS),
            "laps": clean(r.clean_laps),
        }
        for r in x.itertuples()
    ]
    race.sort(key=lambda d: (d["v"] is None, d["v"] or 0))
    return {
        "quali": quali,
        "quali_meta": None
        if first is None
        else {
            "wet": first.wet_flag,
            "reference": bool(first.is_reference_format),
            "format": first.qualifying_format,
            "source": first.time_source,
            "session_best_ms": clean(first.session_best_ms),
            "session_best": format_lap(float(first.session_best_ms)),
        },
        "race_index": race,
        "race_meta": None
        if not len(x)
        else {"wet": bool(x.iloc[0].is_wet), "laps": clean(x.iloc[0].race_laps)},
    }


def home_pole(t: Tables, season: int, rnd: int, race: dict) -> dict | None:
    """폴 포지션 타일: 시즌 캘린더의 폴 시터와 그 드라이버의 마지막 예선 세션 기록."""
    if not race["pole"]:
        return None
    pole = race["pole"][0]
    q = t.qualifying[
        (t.qualifying["season"] == season)
        & (t.qualifying["round"] == rnd)
        & (t.qualifying["driver_id"] == pole["id"])
    ].dropna(subset=["best_time_ms"])
    q = q[q["session_type"].isin(["Q1", "Q2", "Q3"])].sort_values("session_type")
    if not len(q):
        return {**pole, "session": None, "time": None}
    best = q.iloc[-1]
    return {**pole, "session": best.session_type, "time": format_lap(float(best.best_time_ms))}


def home_fastest_lap(t: Tables, season: int, rnd: int, classification: list[dict]) -> dict | None:
    """결승 패스티스트 랩의 기록과 랩 번호.

    Jolpica는 순위만 있어 시각과 랩 번호는 OpenF1 랩에서 읽는다.
    """
    who = next((c for c in classification if c["fastest_lap"]), None)
    if who is None or season < RACE_INDEX_FIRST_SEASON:
        return None
    meetings = pd.read_csv(CURATED_DIR / "openf1" / "meeting_map.csv")
    hit = meetings[(meetings["season"] == season) & (meetings["round"] == rnd)]
    drivers = pd.read_csv(CURATED_DIR / "openf1" / "driver_map.csv")
    numbers = drivers[(drivers["season"] == season) & (drivers["driver_id"] == who["id"])]
    if not len(hit) or not len(numbers) or pd.isna(hit.iloc[0]["race_session_key"]):
        return None
    con = duckdb.connect()
    row = con.execute(
        f"select lap_number, lap_duration from '{CURATED_DIR / 'openf1' / 'laps.parquet'}'"
        " where session_key = ? and driver_number = ? and lap_duration is not null"
        " order by lap_duration limit 1",
        [int(hit.iloc[0]["race_session_key"]), int(numbers.iloc[0]["driver_number"])],
    ).fetchall()
    if not row:
        return None
    lap, duration = row[0]
    return {
        **{k: who[k] for k in ("id", "name", "code", "constructor_id", "constructor")},
        "lap": int(lap),
        "time": format_lap(round(duration * 1000)),
        "source": "openf1",
    }


# --- 기준일과 표기 ---------------------------------------------------------------------


def build_meta(t: Tables) -> dict:
    rows = manifest.read_rows("datasets.csv")
    # 출처마다 기준 행을 하나 고른다. Jolpica는 덤프 행을 기준으로 하되, API로 대회를 더 반영했으면
    # 기준일은 가장 늦은 수집 시각을 쓰고 버전에 반영한 마지막 라운드를 덧붙인다.
    datasets = {r["source"]: r for r in rows if r["name"] != "api-rounds"}
    api_rounds = next(
        (r for r in rows if (r["source"], r["name"]) == ("jolpica", "api-rounds")), None
    )
    if api_rounds and api_rounds["fetched_at"] > datasets["jolpica"]["fetched_at"]:
        datasets["jolpica"] = {
            **datasets["jolpica"],
            "version": f"{datasets['jolpica']['version'][:10]} + API {api_rounds['version']}",
            "fetched_at": api_rounds["fetched_at"],
        }
    fia = manifest.read_rows("fia_documents.csv")
    indexed = max(r["indexed_at"] for r in fia)
    raced = t.races[
        (t.races["season"] == LAST_SEASON) & t.races["round"].isin(raced_rounds(t, LAST_SEASON))
    ]
    last_race = raced.sort_values("round").iloc[-1]
    car_docs = [r for r in fia if r["doc_type"] == "car_presentation"]
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    dump = next(r for r in rows if (r["source"], r["name"]) == ("jolpica", "delayed-dump-csv"))
    api = (
        api_rounds["version"]
        if api_rounds and api_rounds["fetched_at"] > dump["fetched_at"]
        else None
    )
    # 지수는 입력(결과, 예선, OpenF1 랩)이 바뀔 때마다 다시 계산한다(pipeline.update).
    # 계산일은 입력 가운데 가장 늦게 받은 자료의 날짜로 적는다.
    computed = max(datasets[s]["fetched_at"] for s in ("jolpica", "f1db", "openf1"))
    review = t.upgrade_docs[t.upgrade_docs["status"] != "ok"].sort_values(["season", "round"])
    return {
        "generated_at": now,
        "generated_on": kst_date(now),
        "first_season": int(t.races["season"].min()),
        "last_season": LAST_SEASON,
        "last_race": {
            "season": LAST_SEASON,
            "round": int(last_race["round"]),
            "name": last_race["race_name"],
            "name_ko": t.gp(last_race["race_name"])[0],
            "date": str(last_race["date"])[:10],
        },
        "sources": {
            "jolpica": {
                "name": "Jolpica-F1",
                "url": "https://github.com/jolpica/jolpica-f1",
                "license": "CC BY-NC-SA 4.0",
                "version": datasets["jolpica"]["version"].split("T")[0]
                if " + API" not in datasets["jolpica"]["version"]
                else datasets["jolpica"]["version"],
                "as_of": kst_date(datasets["jolpica"]["fetched_at"]),
                # 화면의 Jolpica 기준일은 덤프 날짜다.
                # API로 대회를 더 반영했으면 api에 그 범위가 있다.
                "dump": dump["version"][:10],
                "api": api,
            },
            "f1db": {
                "name": "F1DB",
                "url": "https://github.com/f1db/f1db",
                "license": "CC BY 4.0",
                "version": datasets["f1db"]["version"],
                "as_of": kst_date(datasets["f1db"]["fetched_at"]),
            },
            "openf1": {
                "name": "OpenF1",
                "url": "https://openf1.org",
                "license": "CC BY-NC-SA 4.0",
                "version": datasets["openf1"]["version"],
                "as_of": kst_date(datasets["openf1"]["fetched_at"]),
            },
            "fia": {
                "name": "FIA 결정 문서",
                "url": "https://www.fia.com/documents",
                "license": "FIA 저작물, 원문 링크와 구조화 정보만 게시",
                "version": f"{len(car_docs)}개 Car Presentation 문서",
                "as_of": kst_date(indexed),
            },
            "pace": {
                "name": "페이스 지수 (이 사이트 계산)",
                "url": "https://github.com/qnftk020/f1-update-and-result/blob/main/docs/methodology.md",
                "license": "CC BY-NC-SA 4.0",
                "version": f"퀄리파잉 {QUALI_FIRST_SEASON}-{LAST_SEASON},"
                f" 레이스 {RACE_INDEX_FIRST_SEASON}-{LAST_SEASON}",
                "as_of": kst_date(computed),
            },
        },
        "review_documents": [
            {
                "season": int(d.season),
                "round": int(d.round),
                "event": d.event,
                "event_ko": t.gp(d.event)[0],
                "event_short_ko": t.gp(d.event)[1],
                "url": d.url,
            }
            for d in review.itertuples()
        ],
        "counts": {
            "races": int(len(t.races)),
            "seasons": int(t.races["season"].nunique()),
            "upgrade_items": int(len(t.upgrades)),
            "upgrade_documents": int(len(t.upgrade_docs)),
            "quali_index_races": int(t.quali_index.groupby(["season", "round"]).ngroups),
            "race_index_races": int(t.race_index.groupby(["season", "round"]).ngroups),
            "parse_failures": len(manifest.read_rows("parse_failures.csv")),
        },
    }


def build_labels(t: Tables) -> dict:
    return {
        "component_areas": COMPONENT_AREAS_KO,
        "reason_categories": REASON_CATEGORIES_KO,
        "category_order": CATEGORY_ORDER,
        "team_status": TEAM_STATUS_KO,
        "link_types": LINK_TYPES_KO,
        "quali_formats": QUALI_FORMATS_KO,
        "grand_prix": {
            name: {"ko": ko, "short": short} for name, (ko, short) in t.gp_names.items()
        },
    }


# --- 선택 항목(정제 테이블이 있을 때만) ------------------------------------------------


def optional_builders() -> dict[str, object]:
    """T6, T8 산출물이 있으면 해당 내보내기 함수를 불러 쓴다."""
    out: dict[str, object] = {}
    from pipeline import site_data_extra

    for name, builder in site_data_extra.BUILDERS.items():
        payload = builder()
        if payload is not None:
            out[name] = payload
    return out


def main() -> None:
    t = Tables()
    first, last = int(t.races["season"].min()), LAST_SEASON
    seasons = {season: build_season(t, season) for season in range(first, last + 1)}
    for season, data in seasons.items():
        write_json(f"season/{season}.json", data)
    write_json("seasons.json", [season_summary(seasons[s]) for s in sorted(seasons, reverse=True)])

    upgrades = build_upgrades(t)
    teams = [build_team(t, lineage, seasons, upgrades) for lineage in t.lineages.itertuples()]
    for team in teams:
        write_json(f"team/{team['lineage_id']}.json", team)
    write_json(
        "teams.json",
        [
            {
                **{
                    k: team[k]
                    for k in ("lineage_id", "name_ko", "base", "constructor", "entrant", "pu")
                },
                "since": team["segments"][0]["from"],
                "names": name_history(team["segments"]),
                "segments_n": len(team["segments"]),
                "last": next(
                    (
                        {k: s[k] for k in ("position", "points", "quali_index_mean", "quali_rank")}
                        for s in reversed(team["seasons"])
                        if s["season"] == LAST_SEASON
                    ),
                    None,
                ),
                "upgrade_items": team["upgrades"]["items"],
            }
            for team in teams
        ],
    )

    write_json("upgrades.json", upgrades)
    write_json("home.json", build_home(t, seasons, upgrades))
    write_json("labels.json", build_labels(t))
    write_json("references.json", build_references())
    extra = optional_builders()
    for name, payload in extra.items():
        write_json(name, payload)
    meta = build_meta(t)
    meta["available"] = sorted(extra)
    write_json("meta.json", meta)

    files = sorted(p for p in SITE_DATA_DIR.rglob("*.json"))
    total = sum(p.stat().st_size for p in files)
    print(f"wrote {len(files)} files, {total / 1e6:.1f} MB under {_relative(SITE_DATA_DIR)}")


def _relative(path: Path) -> str:
    root = MANIFEST_DIR.parents[1]
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


# --- 선행 작업 목록(데이터와 방법론 > 소개) ------------------------------------------------


def build_references() -> dict:
    """data/curated/references/prior_work.csv를 그대로 옮긴다. 글은 고치지 않는다."""
    import csv

    path = CURATED_DIR / "references" / "prior_work.csv"
    with path.open(encoding="utf-8", newline="") as f:
        rows = [
            {
                k: (v.strip() or None) if k != "year" else (int(v) if v.strip() else None)
                for k, v in row.items()
            }
            for row in csv.DictReader(f)
        ]
    return {"prior_work": rows}


if __name__ == "__main__":
    main()
