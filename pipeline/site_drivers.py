"""드라이버 페이지와 챔피언십 분석용 JSON을 내보낸다.

build_site_data.main()이 시즌 JSON을 만든 뒤 부른다. 시즌 JSON(season/<연도>.json)의 대회 목록,
순위 추이, 폴 시터를 그대로 다시 쓰므로 드라이버 페이지와 시즌 페이지의 수치가 어긋나지 않는다.
원자료는 Jolpica-F1 결과(results), 순위(driver_standings, constructor_standings), 예선
(qualifying), 드라이버(drivers)이고 계보는 이 사이트의 계보 표(lineage/constructor_seasons)다.

    drivers.json         결승(R) 결과 행이 한 번이라도 있는 드라이버 전체의 통산 요약
    driver/<id>.json     시즌별 성적과 순위 추이, 대회별 결과, 스프린트 결과, 팀 동료 비교
    history.json         시즌별 챔피언십 요약과 통산 집계(타이틀, 우승, 계보별 성적)

정의(docs/methodology.md "드라이버 통계와 챔피언십 분석"):
- 출전(entries): 그 드라이버의 결승 결과 행이 있는 대회 수. 차량 공유로 한 대회에 행이 여럿이어도
  한 번으로 센다. Jolpica 결과에는 예선 탈락(DNQ) 행이 없다.
- 출발(starts): 출전 가운데 출발하지 않은 행만 있는 대회를 뺀 수. 출발하지 않은 행은 Jolpica
  status_code 30(Did not start, Withdrew 등)이면서 완료 랩이 0인 행이다. 랩을 돈 뒤 기권한
  행(1976 후지의 Lauda 등)은 출발로 센다.
- 우승: 결승 행의 position이 1인 대회 수. 차량 공유 우승(1951 프랑스의 Fagioli와 Fangio 등)은
  Jolpica 기록대로 두 드라이버 모두에게 센다.
- 포디움: 완주로 분류된(is_classified) 행의 position이 3 이하인 대회 수.
- 1번 그리드(grid_one): 결승 grid가 1인 대회 수. 폴(poles)은 시즌 페이지와 같은 폴 시터 규칙
  (build_site_data.pole_sitter)으로 고른 대회 수다.
- 결승 득점(points): 결승 결과 행 points의 합. 스프린트 득점은 sprint_points로 따로 둔다. 둘 다
  챔피언십 점수가 아니다. 1990년 이전의 유효 득점 규정이나 실격 처리는 챔피언십 점수에만
  반영된다.
- 챔피언십 순위와 점수: 시즌 마지막 라운드의 Jolpica 드라이버 순위 행. 순위가 비어 있으면
  (is_eligible 거짓, 또는 1997 Michael Schumacher처럼 adjustment_type 101로 제외) None이다.
  점수가 같아도 Jolpica가 매긴 순위를 그대로 쓴다(최종 라운드 순위에 동순위는 없다).
- 타이틀: 마지막 라운드 순위가 1인 시즌.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import pandas as pd

from pipeline.build_site_data import (
    CONSTRUCTOR_EXCLUDED,
    DRIVER_EXCLUDED,
    clean_points,
    round_leaders,
)
from pipeline.config import LAST_SEASON

# Jolpica 결승 결과 status_code 30은 출발하지 않은 행(Did not start, Withdrew 등)이다.
DNS_STATUS_CODE = 30
DSQ_STATUS_CODE = 20
# 컨스트럭터 순위의 adjustment_type 1: 감점(2020 Racing Point).
# 제외(101, 102)는 build_site_data에 있다.
CONSTRUCTOR_DEDUCTED = 1
CONSTRUCTOR_STANDINGS_FIRST_SEASON = 1958
QUALI_FIRST_SEASON = 1994
WINS_TOP = 30
POINT_DIGITS = 2
# 예선 세션의 깊이. 녹아웃 형식(2006-)은 더 늦은 세션까지 남은 드라이버가 앞이다. 2005년 이전은
# 한 세션(QB, 2005 합산 형식의 QA)이고 position이 최종 예선 순위다.
QUALI_DEPTH = {"Q3": 3, "Q2": 2, "Q1": 1, "QB": 1, "QO": 1, "QA": 0}
INDY = "Indianapolis 500"

# Jolpica와 F1DB(v2026.20.0)의 시즌 1위 점수가 다른 시즌. 값은 F1DB 점수다(2026-11-11 대조,
# pipeline/quality/test_site_drivers.py가 F1DB 원본이 있을 때 다시 대조한다). 사이트의 순위와 점수는
# Jolpica 값을 쓰고, 이 시즌에는 history.json의 d1/c1에 f1db_pts를 덧붙여 차이를 밝힌다.
F1DB_DRIVER_CHAMPION_POINTS = {1977: 72}
F1DB_CONSTRUCTOR_CHAMPION_POINTS = {1961: 40, 1967: 63, 1973: 92, 1974: 73, 1977: 95, 1995: 137}

NATIONALITY_KO = {
    "American": "미국",
    "Argentine": "아르헨티나",
    "Australian": "오스트레일리아",
    "Austrian": "오스트리아",
    "Belgian": "벨기에",
    "Brazilian": "브라질",
    "British": "영국",
    "Canadian": "캐나다",
    "Chilean": "칠레",
    "Chinese": "중국",
    "Colombian": "콜롬비아",
    "Czech": "체코",
    "Danish": "덴마크",
    "Dutch": "네덜란드",
    "East German": "동독",
    "Finnish": "핀란드",
    "French": "프랑스",
    "German": "독일",
    "Hungarian": "헝가리",
    "Indian": "인도",
    "Indonesian": "인도네시아",
    "Irish": "아일랜드",
    "Italian": "이탈리아",
    "Japanese": "일본",
    "Liechtensteiner": "리히텐슈타인",
    "Malaysian": "말레이시아",
    "Mexican": "멕시코",
    "Monegasque": "모나코",
    "New Zealander": "뉴질랜드",
    "Polish": "폴란드",
    "Portuguese": "포르투갈",
    "Rhodesian": "로디지아",
    "Russian": "러시아",
    "South African": "남아프리카 공화국",
    "Spanish": "스페인",
    "Swedish": "스웨덴",
    "Swiss": "스위스",
    "Thai": "태국",
    "Uruguayan": "우루과이",
    "Venezuelan": "베네수엘라",
}


def _pts(value: float) -> float | int:
    """점수 합을 소수 둘째 자리로 맞춘다. Jolpica 점수는 소수 둘째 자리까지다(1/7 = 0.14)."""
    number = round(float(value), POINT_DIGITS)
    return int(number) if number.is_integer() else number


def _opt(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and value != value:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class Row(NamedTuple):
    """결과 한 행. 결측은 None으로 바꿔 둔다."""

    season: int
    round: int
    driver_id: str
    constructor_id: str
    grid: int | None
    position: int
    is_classified: bool
    status_code: int | None
    status_detail: str | None
    laps: int
    points: float

    @property
    def race(self) -> tuple[int, int]:
        return (self.season, self.round)

    @property
    def started(self) -> bool:
        return not (self.status_code == DNS_STATUS_CODE and self.laps == 0)


def _rows(frame: pd.DataFrame) -> list[Row]:
    frame = frame.sort_values(["season", "round", "position"])
    return [
        Row(
            season=int(r.season),
            round=int(r.round),
            driver_id=r.driver_id,
            constructor_id=r.constructor_id,
            grid=_opt(r.grid),
            position=int(r.position),
            is_classified=bool(_opt(r.is_classified)),
            status_code=_opt(r.status_code),
            status_detail=r.status_detail if isinstance(r.status_detail, str) else None,
            laps=_opt(r.laps_completed) or 0,
            points=float(_opt(r.points) or 0),
        )
        for r in frame.itertuples()
    ]


def outcome(row: Row) -> str:
    """결과 행의 결과 분류. F 완주 분류, D 실격, N 출발하지 않음, R 그 밖의 미분류(리타이어 등)."""
    if row.is_classified:
        return "F"
    if row.status_code == DSQ_STATUS_CODE:
        return "D"
    if not row.started:
        return "N"
    return "R"


def _better(a: Row, b: Row) -> int:
    """두 결과 행의 앞뒤. a가 앞이면 1, 뒤면 -1, 비교하지 않으면 0.

    완주로 분류된 행이 분류되지 않은 행보다 앞이다. 둘 다 분류되면 position이 작은 쪽이 앞이고,
    같으면(차량 공유) 비교하지 않는다. 둘 다 분류되지 않으면 비교하지 않는다.
    """
    if not a.is_classified and not b.is_classified:
        return 0
    if a.is_classified != b.is_classified:
        return 1 if a.is_classified else -1
    if a.position == b.position:
        return 0
    return 1 if a.position < b.position else -1


def _best_row(rows: list[Row]) -> Row:
    """한 대회에서 같은 팀으로 낸 결과 행이 여럿이면(차량 공유, 교대) 가장 앞선 행을 쓴다."""
    return min(rows, key=lambda r: (not r.is_classified, r.position))


def _quali_keys(qualifying: pd.DataFrame) -> dict[tuple[int, int, str], tuple[int, int]]:
    """(시즌, 라운드, 드라이버)별 예선 정렬 키. 작을수록 앞이다.

    가장 늦은 세션의 깊이(음수)와 그 세션의 position이다. 스프린트 예선(SQ1-SQ3)은 뺀다.
    2023년 이후 API로 반영한 라운드는 세션별 position이 그 세션 기록 순이고, 그 이전 덤프 행은
    세션마다 최종 예선 순위가 같다. 어느 쪽이든 이 키의 순서는 최종 예선 순위의 순서다.
    position이 빈 행(기록 없음)은 그 세션의 맨 뒤로 둔다.
    """
    q = qualifying[qualifying["session_type"].isin(QUALI_DEPTH)]
    q = q[q["season"] >= QUALI_FIRST_SEASON]
    out: dict[tuple[int, int, str], tuple[int, int]] = {}
    for r in q.itertuples():
        pos = _opt(r.position)
        key = (-QUALI_DEPTH[r.session_type], pos if pos is not None else 999)
        k = (int(r.season), int(r.round), r.driver_id)
        if k not in out or key < out[k]:
            out[k] = key
    return out


class _Context:
    """시즌 JSON과 정제 테이블에서 미리 뽑아 둔 값."""

    def __init__(self, t: object, seasons: dict[int, dict]) -> None:
        self.t = t
        self.seasons = seasons
        res = t.results
        self.race = _rows(res[res["session_type"] == "R"])
        self.sprint = _rows(res[res["session_type"] == "SR"])
        self.race_by_driver: dict[str, list[Row]] = {}
        for r in self.race:
            self.race_by_driver.setdefault(r.driver_id, []).append(r)
        self.sprint_by_driver: dict[str, list[Row]] = {}
        for r in self.sprint:
            self.sprint_by_driver.setdefault(r.driver_id, []).append(r)
        # (시즌, 라운드, 컨스트럭터) -> 드라이버 -> 결과 행. 팀 동료 비교에 쓴다.
        self.car_rows: dict[tuple[int, int, str], dict[str, list[Row]]] = {}
        for r in self.race:
            key = (r.season, r.round, r.constructor_id)
            self.car_rows.setdefault(key, {}).setdefault(r.driver_id, []).append(r)
        self.info = {r.driver_id: r for r in t.drivers.itertuples()}
        self.short = {
            (season, r["round"]): r["short_ko"]
            for season, d in seasons.items()
            for r in d["rounds"]
        }
        self.race_names = {
            (season, r["round"]): r["name"] for season, d in seasons.items() for r in d["rounds"]
        }
        self.poles = {
            (season, r["round"]): r["pole"][0]["id"]
            for season, d in seasons.items()
            for r in d["rounds"]
            if r["pole"]
        }
        self.series = {
            (season, d["id"]): d for season, data in seasons.items() for d in data["drivers"]
        }
        # 마지막 라운드의 순위 행. 시즌 JSON의 position은 마지막으로 비어 있지 않은 값이라
        # 여기서는 원자료의 마지막 라운드 행을 직접 읽는다.
        last_round = t.races.groupby("season")["round"].max().to_dict()
        ds = t.driver_standings
        final = ds[ds["round"] == ds["season"].map(last_round)]
        self.final_driver = {(int(r.season), r.driver_id): r for r in final.itertuples()}
        cs = t.constructor_standings
        cfinal = cs[cs["round"] == cs["season"].map(last_round)]
        self.final_constructor = {(int(r.season), r.constructor_id): r for r in cfinal.itertuples()}
        self.champion = {int(r.season): r for r in final.itertuples() if _opt(r.position) == 1}
        self.quali = _quali_keys(t.qualifying)

    def lineage(self, season: int, cid: str) -> str | None:
        return self.t.lineage_of(season, cid)


def _result_row(ctx: _Context, r: Row, multi: bool) -> dict:
    row = {
        "s": r.season,
        "r": r.round,
        "n": ctx.short[r.race],
        "c": r.constructor_id,
        "g": r.grid,
        "p": r.position,
        "o": outcome(r),
        "st": r.status_detail,
        "pts": _pts(r.points),
    }
    if multi:
        row["x"] = 1
    return row


def _tally(rows: list[Row], poles: dict, driver_id: str) -> dict:
    """결승 결과 행 묶음의 출전, 출발, 우승, 포디움, 완주, 1번 그리드, 폴, 결승 득점."""
    races = {r.race for r in rows}
    return {
        "entries": len(races),
        "starts": len({r.race for r in rows if r.started}),
        "wins": len({r.race for r in rows if r.position == 1}),
        "podiums": len({r.race for r in rows if r.is_classified and r.position <= 3}),
        "classified": len({r.race for r in rows if r.is_classified}),
        "grid_one": len({r.race for r in rows if r.grid == 1}),
        "poles": sum(1 for k in races if poles.get(k) == driver_id),
        "points": _pts(sum(r.points for r in rows)),
    }


def _teammates(ctx: _Context, rows: list[Row], driver_id: str) -> list[dict]:
    """같은 시즌, 같은 컨스트럭터, 같은 대회에 결과 행이 있는 동료와의 결승, 예선 비교."""
    out: dict[tuple[str, str], dict] = {}
    cars = dict.fromkeys((r.season, r.round, r.constructor_id) for r in rows)
    for key in cars:
        season, rnd, cid = key
        # 인디애나폴리스 500(1950-1960)은 섀시 제작사(kurtis_kraft 등) 하나에 참가자가 수십 명이라
        # 같은 컨스트럭터를 동료로 볼 수 없다. 비교에서 뺀다.
        if ctx.race_names[(season, rnd)] == INDY:
            continue
        drivers = ctx.car_rows[key]
        me = _best_row(drivers[driver_id])
        mk = ctx.quali.get((season, rnd, driver_id))
        for mate_id, mate_rows in drivers.items():
            if mate_id == driver_id:
                continue
            entry = out.setdefault(
                (mate_id, cid),
                {
                    "id": mate_id,
                    "name": ctx.t.driver_names.get(mate_id, mate_id),
                    "c": cid,
                    "n": 0,
                    "rc": 0,
                    "ra": 0,
                    "qc": 0,
                    "qa": 0,
                },
            )
            entry["n"] += 1
            verdict = _better(me, _best_row(mate_rows))
            if verdict:
                entry["rc"] += 1
                entry["ra"] += int(verdict > 0)
            tk = ctx.quali.get((season, rnd, mate_id))
            if mk is not None and tk is not None and mk != tk:
                entry["qc"] += 1
                entry["qa"] += int(mk < tk)
    return sorted(out.values(), key=lambda r: (-r["n"], r["name"], r["id"], r["c"]))


def _season_row(ctx: _Context, driver_id: str, season: int, rows: list[Row]) -> dict:
    t = ctx.t
    data = ctx.seasons[season]
    n_rounds = len(data["rounds"])
    teams = list(dict.fromkeys(r.constructor_id for r in rows))
    series = ctx.series.get((season, driver_id))
    final = ctx.final_driver.get((season, driver_id))
    champ = ctx.champion.get(season)
    sprint = [r for r in ctx.sprint_by_driver.get(driver_id, []) if r.season == season]
    tally = _tally(rows, ctx.poles, driver_id)
    return {
        "s": season,
        "rounds": n_rounds,
        "teams": [
            {"id": c, "name": t.team_name(season, c), "lineage_id": ctx.lineage(season, c)}
            for c in teams
        ],
        **{k: tally[k] for k in ("entries", "starts", "wins", "podiums", "grid_one", "poles")},
        # 이 시즌 결승 출전 대회 가운데 Jolpica 예선 행이 있는 대회 수.
        # 1994년부터이고 1994년과 1996-2002년은 일부 대회만 있다.
        "q_cov": sum(1 for rnd in {r.round for r in rows} if (season, rnd, driver_id) in ctx.quali),
        "rpts": tally["points"],
        "spts": _pts(sum(r.points for r in sprint)),
        "pos": _opt(final.position) if final is not None else None,
        "pts": clean_points(final.points) if final is not None else None,
        "excluded": bool(final is not None and _opt(final.adjustment_type) == DRIVER_EXCLUDED),
        "champ_id": champ.driver_id if champ is not None else None,
        "champ_pts": clean_points(champ.points) if champ is not None else None,
        "round_pos": series["positions"] if series else [None] * n_rounds,
        "round_pts": series["points"] if series else [None] * n_rounds,
        "mates": _teammates(ctx, rows, driver_id),
    }


def build_driver(ctx: _Context, driver_id: str) -> tuple[dict, dict]:
    """드라이버 한 명의 (drivers.json 행, driver/<id>.json)."""
    t = ctx.t
    rows = ctx.race_by_driver[driver_id]
    info = ctx.info[driver_id]
    by_season: dict[int, list[Row]] = {}
    for r in rows:
        by_season.setdefault(r.season, []).append(r)
    seasons = sorted(by_season)
    season_rows = [_season_row(ctx, driver_id, s, by_season[s]) for s in seasons]
    tally = _tally(rows, ctx.poles, driver_id)
    sprint = ctx.sprint_by_driver.get(driver_id, [])
    teams = list(dict.fromkeys(r.constructor_id for r in rows))
    last = rows[-1]
    lineages = list(
        dict.fromkeys(
            lin for r in rows if (lin := ctx.lineage(r.season, r.constructor_id)) is not None
        )
    )
    titles = [s["s"] for s in season_rows if s["pos"] == 1]
    positions = [s["pos"] for s in season_rows if s["pos"] is not None]
    best = min(positions) if positions else None
    nationality = info.nationality if isinstance(info.nationality, str) else None
    summary = {
        "id": driver_id,
        "name": t.driver_names.get(driver_id, driver_id),
        "code": t.driver_codes.get(driver_id),
        "nationality": nationality,
        "nationality_ko": NATIONALITY_KO.get(nationality) if nationality else None,
        "dob": str(info.date_of_birth)[:10] if _opt(info.date_of_birth) is not None else None,
        "first_season": seasons[0],
        "last_season": seasons[-1],
        "seasons": len(seasons),
        **{
            k: tally[k]
            for k in ("entries", "starts", "wins", "podiums", "classified", "grid_one", "poles")
        },
        "points": tally["points"],
        "sprint_points": _pts(sum(r.points for r in sprint)),
        "sprint_wins": sum(1 for r in sprint if r.position == 1),
        "titles": len(titles),
        "title_seasons": titles,
        "best": best,
        "best_n": sum(1 for p in positions if p == best) if best is not None else 0,
        "teams": [{"id": c, "name": t.constructor_names.get(c, c)} for c in teams],
        "last_team": {
            "id": last.constructor_id,
            "name": t.team_name(last.season, last.constructor_id),
        },
        "lineages": lineages,
        "in_2025": LAST_SEASON in by_season,
        "indy_only": {ctx.race_names[r.race] for r in rows} == {INDY},
    }
    per_race: dict[tuple[int, int], int] = {}
    for r in rows:
        per_race[r.race] = per_race.get(r.race, 0) + 1
    detail = {
        **summary,
        "season_rows": season_rows,
        "races": [_result_row(ctx, r, per_race[r.race] > 1) for r in rows],
        "sprints": [_result_row(ctx, r, False) for r in sprint],
    }
    return summary, detail


# --- 챔피언십 분석 -----------------------------------------------------------------------


def _entry(ctx: _Context, row: object, key: str) -> dict:
    season = int(row.season)
    if key == "driver_id":
        return {
            "id": row.driver_id,
            "name": ctx.t.driver_names.get(row.driver_id, row.driver_id),
            "pts": clean_points(row.points),
        }
    return {
        "id": row.constructor_id,
        "name": ctx.t.team_name(season, row.constructor_id),
        "lineage_id": ctx.lineage(season, row.constructor_id),
        "pts": clean_points(row.points),
    }


def _margin(first: dict | None, second: dict | None) -> tuple[object, object]:
    if first is None or second is None or first["pts"] is None or second["pts"] is None:
        return None, None
    diff = round(first["pts"] - second["pts"], POINT_DIGITS)
    pct = round(diff / first["pts"] * 100, 2) if first["pts"] else None
    return (int(diff) if float(diff).is_integer() else diff), pct


def _history_season(ctx: _Context, season: int) -> dict:
    data = ctx.seasons[season]
    finals_d = {
        _opt(r.position): r
        for (s, _), r in ctx.final_driver.items()
        if s == season and _opt(r.position) in (1, 2)
    }
    finals_c = {
        _opt(r.position): r
        for (s, _), r in ctx.final_constructor.items()
        if s == season and _opt(r.position) in (1, 2)
    }
    d1 = _entry(ctx, finals_d[1], "driver_id") if 1 in finals_d else None
    d2 = _entry(ctx, finals_d[2], "driver_id") if 2 in finals_d else None
    c1 = _entry(ctx, finals_c[1], "constructor_id") if 1 in finals_c else None
    c2 = _entry(ctx, finals_c[2], "constructor_id") if 2 in finals_c else None
    if d1 is not None:
        champ_series = next(d for d in data["drivers"] if d["id"] == d1["id"])
        d1["wins"] = sum(
            1 for r in data["rounds"] if any(w["id"] == d1["id"] for w in r["winners"])
        )
        # 시즌 뒤 순위에서 제외된 드라이버(1997 Schumacher)도 그 시점 점수로 1위를 다시 정한다.
        # 계산할 수 없으면(round_leaders가 None) None이다.
        excluded_ids = tuple(
            r.driver_id
            for (s, _), r in ctx.final_driver.items()
            if s == season and _opt(r.adjustment_type) == DRIVER_EXCLUDED
        )
        leaders = round_leaders(data["rounds"], data["drivers"], "id", excluded_ids)
        d1["led"] = None if leaders is None else sum(1 for _, lid in leaders if lid == d1["id"])
        d1["teams"] = champ_series["constructors"]
    if d1 is not None and season in F1DB_DRIVER_CHAMPION_POINTS:
        d1["f1db_pts"] = F1DB_DRIVER_CHAMPION_POINTS[season]
    if c1 is not None and season in F1DB_CONSTRUCTOR_CHAMPION_POINTS:
        c1["f1db_pts"] = F1DB_CONSTRUCTOR_CHAMPION_POINTS[season]
    if c1 is not None:
        c1["wins"] = ctx.t.race_tally.get((season, c1["id"]), {}).get("wins", 0)
    margin, margin_pct = _margin(d1, d2)
    c_margin, c_margin_pct = _margin(c1, c2)
    facts = data["facts"]
    excluded = [
        {
            "id": r.driver_id,
            "name": ctx.t.driver_names.get(r.driver_id),
            "pts": clean_points(r.points),
        }
        for (s, _), r in ctx.final_driver.items()
        if s == season and _opt(r.adjustment_type) == DRIVER_EXCLUDED
    ]
    c_adjusted = [
        {
            "id": r.constructor_id,
            "name": ctx.t.team_name(season, r.constructor_id),
            "kind": "excluded" if _opt(r.adjustment_type) == CONSTRUCTOR_EXCLUDED else "deducted",
            "pts": clean_points(r.points),
            "pos": _opt(r.position),
        }
        for (s, _), r in ctx.final_constructor.items()
        if s == season and _opt(r.adjustment_type) in (CONSTRUCTOR_EXCLUDED, CONSTRUCTOR_DEDUCTED)
    ]
    return {
        "season": season,
        "rounds": len(data["rounds"]),
        "d1": d1,
        "d2": d2,
        "margin": margin,
        "margin_pct": margin_pct,
        "c1": c1,
        "c2": c2,
        "c_margin": c_margin,
        "c_margin_pct": c_margin_pct,
        "winners": facts["winners"],
        "lead_change": facts["driver_lead"]["round"] if facts["driver_lead"] else None,
        "c_lead_change": facts["constructor_lead"]["round"] if facts["constructor_lead"] else None,
        "excluded": excluded,
        "c_adjusted": c_adjusted,
    }


def build_history(ctx: _Context, drivers: list[dict]) -> dict:
    t = ctx.t
    seasons = [_history_season(ctx, s) for s in sorted(ctx.seasons)]
    titled = [d for d in drivers if d["titles"]]
    titled.sort(key=lambda d: (-d["titles"], d["title_seasons"][0]))
    by_wins = sorted(drivers, key=lambda d: (-d["wins"], d["starts"], d["name"]))
    cutoff = by_wins[WINS_TOP - 1]["wins"] if len(by_wins) >= WINS_TOP else 0
    top_wins = [d for d in by_wins if d["wins"] >= max(cutoff, 1)]

    c_titles: dict[str, list[int]] = {}
    for s in seasons:
        if s["c1"] is not None:
            c_titles.setdefault(s["c1"]["id"], []).append(s["season"])
    constructor_titles = [
        {"id": cid, "name": t.constructor_names.get(cid, cid), "titles": len(ys), "seasons": ys}
        for cid, ys in c_titles.items()
    ]
    constructor_titles.sort(key=lambda r: (-r["titles"], r["seasons"][0]))

    lineage_rows = []
    for lin in t.lineages.itertuples():
        members = t.constructor_seasons[t.constructor_seasons["lineage_id"] == lin.lineage_id]
        rows = []
        for m in members.sort_values(["season", "constructor_id"]).itertuples():
            season = int(m.season)
            final = ctx.final_constructor.get((season, m.constructor_id))
            tally = t.race_tally.get((season, m.constructor_id), {})
            rows.append(
                {
                    "s": season,
                    "c": m.constructor_id,
                    "name": m.team_name,
                    "pos": _opt(final.position) if final is not None else None,
                    "pts": clean_points(final.points) if final is not None else None,
                    "entered": tally.get("entered", 0),
                    "wins": tally.get("wins", 0),
                    "podiums": tally.get("podiums", 0),
                }
            )
        title_years = sorted({r["s"] for r in rows if r["pos"] == 1})
        lineage_rows.append(
            {
                "lineage_id": lin.lineage_id,
                "name_ko": lin.name_ko,
                "titles": len(title_years),
                "title_seasons": title_years,
                "wins": sum(r["wins"] for r in rows),
                "entered": sum(r["entered"] for r in rows),
                "podiums": sum(r["podiums"] for r in rows),
                "seasons": rows,
            }
        )
    keep = ("id", "name", "nationality_ko", "first_season", "last_season")
    return {
        "first_season": min(ctx.seasons),
        "last_season": max(ctx.seasons),
        "constructor_first_season": CONSTRUCTOR_STANDINGS_FIRST_SEASON,
        "seasons": seasons,
        "driver_titles": [
            {**{k: d[k] for k in keep}, "titles": d["titles"], "seasons": d["title_seasons"]}
            for d in titled
        ],
        "wins": [
            {
                **{k: d[k] for k in keep},
                "wins": d["wins"],
                "starts": d["starts"],
                "titles": d["titles"],
            }
            for d in top_wins
        ],
        "constructor_titles": constructor_titles,
        "lineages": lineage_rows,
    }


def build_all(t: object, seasons: dict[int, dict], write: Callable[[str, object], None]) -> dict:
    """세 산출물을 쓰고 개수를 돌려준다."""
    ctx = _Context(t, seasons)
    summaries = []
    for driver_id in sorted(ctx.race_by_driver):
        summary, detail = build_driver(ctx, driver_id)
        summaries.append(summary)
        write(f"driver/{driver_id}.json", detail)
    summaries.sort(key=lambda d: (-d["titles"], -d["wins"], -d["podiums"], -d["starts"], d["name"]))
    write("drivers.json", summaries)
    write("history.json", build_history(ctx, summaries))
    return {"drivers": len(summaries)}
