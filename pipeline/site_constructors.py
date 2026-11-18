"""컨스트럭터 페이지용 JSON을 내보낸다.

build_site_data.main()이 드라이버 JSON을 만든 뒤 부른다. 결과 행, 시즌 JSON, 순위는 드라이버 쪽과
같은 _Context(pipeline/site_drivers.py)에서 읽으므로 두 쪽의 수치가 어긋나지 않는다.

    constructors.json         결승(R) 결과 행이 한 번이라도 있는 Jolpica 컨스트럭터 전체의 통산 요약
    constructor/<id>.json     시즌별 성적, 드라이버 구성, 리타이어 원인, 대회별 결과(차마다 한 줄)

정의(docs/methodology.md "컨스트럭터 통계"):
- 컨스트럭터는 Jolpica constructor_id 단위다. 1950-1960년대에는 섀시와 엔진 조합이 따로 ID를
  가진다(cooper-climax 등). 계보(lineage_id)와 다르다.
- 출전: 그 컨스트럭터의 결승 결과 행이 있는 대회 수. 차량 수와 상관없이 한 번으로 센다.
- 우승: 결승 position 1인 행이 있는 대회 수. 포디움: 완주로 분류된 3위 이내 결과 행 수(차 기준,
  build_site_data.Tables.race_tally와 같다). 원투: 같은 대회에서 완주 분류 1위와 2위를 모두 낸
  대회 수.
- 리타이어 원인: site_drivers.retire_cause의 분류를 결과 행마다 센다.
- 순위와 점수: 시즌 마지막 라운드의 Jolpica 컨스트럭터 순위 행(1958년부터).
- 드라이버 타이틀: 그 시즌 드라이버 챔피언이 이 컨스트럭터로 결승에 한 번 이상 나선 시즌.
- 섀시와 엔진(kit): F1DB의 참가 팀별 시즌 섀시·엔진 표. Jolpica 컨스트럭터와 F1DB 컨스트럭터·엔진
  제조사는 kit_map()으로 맞춘다. 몇 라운드부터 썼는지는 F1DB에 없다. 2010-2021년은 싣지 않는다
  (KIT_EXCLUDED).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

import pandas as pd

from pipeline.build_site_data import CONSTRUCTOR_EXCLUDED, clean_points
from pipeline.config import CURATED_DIR, LAST_SEASON
from pipeline.site_drivers import (
    CONSTRUCTOR_DEDUCTED,
    NATIONALITY_KO,
    Row,
    _Context,
    _opt,
    _pts,
    outcome,
    retire_cause,
)

CAUSES = ("acc", "mech", "unk", "nc", "oth")

# 2026-11-18 사용자 결정: 2010-2021년은 팀이 섀시 이름을 바꾸지 않고 부품만 바꿔 F1DB에 시즌 중
# 교체 기록이 사실상 없다(한 시즌에 섀시 둘 이상은 2015 Force India 1건). 일단 싣지 않는다.
KIT_EXCLUDED = range(2010, 2022)


def _engines(t: object, race: list[Row]) -> dict[tuple[int, str], str]:
    """(시즌, Jolpica 컨스트럭터 ID)별 F1DB 엔진 제조사 이름. 여럿이면 쉼표로 잇는다.

    F1DB ID는 Jolpica ID의 밑줄을 하이픈으로 바꾼 값이고, 다른 경우는 계보 표의 대응표
    (lineage/constructor_crosswalk.csv)를 따른다. 섀시와 엔진 조합 ID(cooper-climax 등)는 F1DB에
    같은 ID가 없어 비워 둔다.
    """
    override = _crosswalk()
    entrants = t.season_entrants
    by: dict[tuple[int, str], list[str]] = {}
    for r in entrants.itertuples():
        if not isinstance(r.engine_manufacturer_id, str):
            continue
        names = by.setdefault((int(r.season), r.f1db_constructor_id), [])
        name = t.engine_names.get(r.engine_manufacturer_id, r.engine_manufacturer_id)
        if name not in names:
            names.append(name)
    out: dict[tuple[int, str], str] = {}
    for season, cid in {(r.season, r.constructor_id) for r in race}:
        f1db = override.get((season, cid), cid.replace("_", "-"))
        if (season, f1db) in by:
            out[(season, cid)] = ", ".join(by[(season, f1db)])
    return out


def _crosswalk() -> dict[tuple[int, str], str]:
    """계보 표의 (시즌, Jolpica ID) -> F1DB 컨스트럭터 ID 대응.

    근거 파일: data/curated/lineage/constructor_crosswalk.csv
    """
    crosswalk = pd.read_csv(CURATED_DIR / "lineage" / "constructor_crosswalk.csv")
    out: dict[tuple[int, str], str] = {}
    for r in crosswalk.itertuples():
        for season in range(int(r.season_from), int(r.season_to) + 1):
            out[(season, r.constructor_id)] = r.f1db_constructor_id
    return out


def kit_map(t: object) -> dict[tuple[int, str], tuple[str, frozenset[str]]]:
    """(시즌, Jolpica 컨스트럭터 ID) -> (F1DB 컨스트럭터 ID, F1DB 엔진 제조사 ID 집합).

    Jolpica는 1950-1960년대에 섀시와 엔진 조합마다 ID를 따로 두고(cooper-climax, lotus-brm),
    이름도 다른 경우가 있다(team_lotus, alfa). 그래서 결승 결과 행을 대회와 차 번호로
    F1DB 결승 결과에 맞춰, 그 Jolpica 컨스트럭터의 차가 F1DB에서 어느 컨스트럭터와
    엔진 제조사로 적혔는지 센다.
    한 대회에 같은 차 번호가 둘 이상인 행(인디애나폴리스 500 등)은 맞추지 않는다.

    F1DB 컨스트럭터는 이름 대응(계보 대응표, 밑줄을 하이픈으로 바꾼 ID)이 그 시즌 F1DB 섀시 표에
    있으면 그것을, 없으면 가장 많이 맞은 것을 쓴다. 엔진 제조사는 그 F1DB 컨스트럭터로 맞은 엔진
    제조사들이다. 맞은 행이 없으면 조합 ID의 앞뒤(cooper-maserati -> cooper, maserati)로 찾는다.
    """
    ch = t.entrant_chassis
    engines_of: dict[tuple[int, str], set[str]] = {}
    for r in ch.itertuples():
        engines_of.setdefault((int(r.season), r.f1db_constructor_id), set()).add(
            r.engine_manufacturer_id
        )
    race = t.results[t.results["session_type"] == "R"]
    keys = ["season", "round", "car_number"]
    j = race.dropna(subset=["car_number"])[[*keys, "constructor_id"]]
    j = j[~j.duplicated(keys, keep=False)]
    f = t.f1db_race_entries.dropna(subset=["car_number"])
    f = f[~f.duplicated(keys, keep=False)]
    joined = j.merge(f, on=keys)
    votes: dict[tuple[int, str], Counter] = {}
    for r in joined.itertuples():
        votes.setdefault((int(r.season), r.constructor_id), Counter())[
            (r.f1db_constructor_id, r.engine_manufacturer_id)
        ] += 1
    override = _crosswalk()
    out: dict[tuple[int, str], tuple[str, frozenset[str]]] = {}
    pairs = set(zip(race["season"].astype(int), race["constructor_id"], strict=True))
    for season, cid in pairs:
        named = override.get((season, cid), cid.replace("_", "-"))
        vote = votes.get((season, cid), Counter())
        prefix, _, suffix = cid.partition("-")
        prefix, suffix = prefix.replace("_", "-"), suffix.replace("_", "-")
        if (season, named) in engines_of:
            f1c = named
        elif vote:
            f1c = vote.most_common(1)[0][0][0]
        elif suffix and (season, prefix) in engines_of:
            f1c = prefix
        else:
            continue
        available = engines_of.get((season, f1c), set())
        engines = {e for (c, e), _ in vote.items() if c == f1c} & available
        if not engines and suffix:
            engines = {e for e in available if e == suffix or e.startswith(f"{suffix}-")}
        if not engines:
            engines = available
        if engines:
            out[(season, cid)] = (f1c, frozenset(engines))
    return out


def kit_rows(t: object, kmap: dict, season: int, cid: str) -> list[dict] | None:
    """그 시즌 이 컨스트럭터로 등록된 참가 팀별 섀시와 엔진. 싣지 않는 시즌은 None이다.

    [{"e": 참가 팀 이름, "c": [섀시 전체 이름], "g": [엔진 전체 이름]}], 참가 팀 이름순.
    섀시와 엔진은 이름순이다(F1DB에 쓴 순서가 없다). 예선 탈락 등으로 결승에 나서지 못한
    참가 팀도 들어갈 수 있다.
    """
    if season in KIT_EXCLUDED:
        return None
    key = kmap.get((season, cid))
    if key is None:
        return []
    f1c, engines = key

    def pick(df: pd.DataFrame) -> pd.DataFrame:
        return df[
            (df["season"] == season)
            & (df["f1db_constructor_id"] == f1c)
            & (df["engine_manufacturer_id"].isin(engines))
        ]

    chassis = pick(t.entrant_chassis)
    motors = pick(t.entrant_engines)
    rows = []
    for entrant, group in chassis.groupby("entrant_id"):
        g = motors[motors["entrant_id"] == entrant]
        rows.append(
            {
                "e": group["entrant_name"].iloc[0],
                "c": sorted(set(group["chassis_full_name"])),
                "g": sorted(set(g["engine_full_name"])),
            }
        )
    rows.sort(key=lambda r: r["e"].casefold())
    return rows


def _driver_tally(rows: list[Row]) -> dict:
    races = {r.round for r in rows}
    classified = [r.position for r in rows if r.is_classified]
    return {
        "n": len(races),
        "w": len({r.round for r in rows if r.position == 1}),
        "p": sum(1 for r in rows if r.is_classified and r.position <= 3),
        "pts": _pts(sum(r.points for r in rows)),
        "best": min(classified) if classified else None,
    }


def _season_row(
    ctx: _Context, cid: str, season: int, rows: list[Row], engines: dict, kmap: dict
) -> dict:
    t = ctx.t
    data = ctx.seasons[season]
    by_driver: dict[str, list[Row]] = {}
    for r in sorted(rows, key=lambda r: (r.round, r.position)):
        by_driver.setdefault(r.driver_id, []).append(r)
    by_round: dict[int, list[Row]] = {}
    for r in rows:
        by_round.setdefault(r.round, []).append(r)
    one_two = sum(
        1 for rs in by_round.values() if {1, 2} <= {r.position for r in rs if r.is_classified}
    )
    causes = Counter(c for r in rows if (c := retire_cause(r)) is not None)
    final = ctx.final_constructor.get((season, cid))
    champ = next(
        (r for (s, _), r in ctx.final_constructor.items() if s == season and _opt(r.position) == 1),
        None,
    )
    series = next((c for c in data["constructors"] if c["id"] == cid), None)
    adjustment = _opt(final.adjustment_type) if final is not None else None
    champion = ctx.champion.get(season)
    return {
        "s": season,
        "rounds": len(data["rounds"]),
        "name": t.team_name(season, cid),
        "lineage_id": ctx.lineage(season, cid),
        "engine": engines.get((season, cid)),
        "kit": kit_rows(t, kmap, season, cid),
        "entries": len(by_round),
        "cars": len(rows),
        "wins": len({r.round for r in rows if r.position == 1}),
        "podiums": sum(1 for r in rows if r.is_classified and r.position <= 3),
        "one_two": one_two,
        "classified": sum(1 for r in rows if r.is_classified),
        "dsq": sum(1 for r in rows if outcome(r) == "D"),
        "dns": sum(1 for r in rows if outcome(r) == "N"),
        "causes": {c: causes.get(c, 0) for c in CAUSES},
        "rpts": _pts(sum(r.points for r in rows)),
        "pos": _opt(final.position) if final is not None else None,
        "pts": clean_points(final.points) if final is not None else None,
        "excluded": adjustment == CONSTRUCTOR_EXCLUDED,
        "deducted": adjustment == CONSTRUCTOR_DEDUCTED,
        "champ_id": champ.constructor_id if champ is not None else None,
        "champ_pts": clean_points(champ.points) if champ is not None else None,
        "driver_champ": champion.driver_id
        if champion is not None and champion.driver_id in by_driver
        else None,
        "round_pos": series["positions"] if series and series["positions"] else None,
        "round_pts": series["points"] if series and series["points"] else None,
        "quali_mean": series["quali_mean"] if series else None,
        "quali_n": series["quali_n"] if series else 0,
        "drivers": [
            {"id": d, "name": t.driver_names.get(d, d), **_driver_tally(rs)}
            for d, rs in by_driver.items()
        ],
    }


def _race_row(ctx: _Context, r: Row, multi: bool) -> dict:
    row = {
        "s": r.season,
        "r": r.round,
        "n": ctx.short[r.race],
        "d": r.driver_id,
        "g": r.grid,
        "p": r.position,
        "o": outcome(r),
        "st": r.status_detail,
        "pts": _pts(r.points),
    }
    if (q := ctx.quali_rank.get((r.season, r.round, r.driver_id))) is not None:
        row["q"] = q
    if (cause := retire_cause(r)) is not None:
        row["rc"] = cause
    if multi:
        row["x"] = 1
    return row


def build_constructor(
    ctx: _Context, cid: str, rows: list[Row], engines: dict, kmap: dict
) -> tuple[dict, dict]:
    """컨스트럭터 하나의 (constructors.json 행, constructor/<id>.json)."""
    t = ctx.t
    by_season: dict[int, list[Row]] = {}
    for r in rows:
        by_season.setdefault(r.season, []).append(r)
    seasons = sorted(by_season)
    season_rows = [_season_row(ctx, cid, s, by_season[s], engines, kmap) for s in seasons]
    info = t.constructor_info.get(cid)
    raw = info.nationality if info is not None else None
    nationality = raw if isinstance(raw, str) else None
    titles = [s["s"] for s in season_rows if s["pos"] == 1]
    positions = [s["pos"] for s in season_rows if s["pos"] is not None]
    best = min(positions) if positions else None
    driver_titles = [s["s"] for s in season_rows if s["driver_champ"]]
    names = list(dict.fromkeys(s["name"] for s in season_rows))
    lineages = list(dict.fromkeys(s["lineage_id"] for s in season_rows if s["lineage_id"]))
    by_driver: dict[str, list[Row]] = {}
    for r in rows:
        by_driver.setdefault(r.driver_id, []).append(r)
    career = []
    for d, rs in by_driver.items():
        tally = Counter()
        races: set[tuple[int, int]] = set()
        wins: set[tuple[int, int]] = set()
        for r in rs:
            races.add(r.race)
            if r.position == 1:
                wins.add(r.race)
            if r.is_classified and r.position <= 3:
                tally["p"] += 1
        career.append(
            {
                "id": d,
                "name": t.driver_names.get(d, d),
                "seasons": sorted({r.season for r in rs}),
                "n": len(races),
                "w": len(wins),
                "p": tally["p"],
                "pts": _pts(sum(r.points for r in rs)),
            }
        )
    career.sort(key=lambda d: (-d["n"], d["seasons"][0], d["name"]))
    summary = {
        "id": cid,
        "name": t.constructor_names.get(cid, cid),
        "nationality": nationality,
        "nationality_ko": NATIONALITY_KO.get(nationality) if nationality else None,
        "first_season": seasons[0],
        "last_season": seasons[-1],
        "seasons": len(seasons),
        "years": seasons,
        "entries": sum(s["entries"] for s in season_rows),
        "cars": len(rows),
        "wins": sum(s["wins"] for s in season_rows),
        "podiums": sum(s["podiums"] for s in season_rows),
        "one_two": sum(s["one_two"] for s in season_rows),
        "titles": len(titles),
        "title_seasons": titles,
        "driver_titles": len(driver_titles),
        "driver_title_seasons": driver_titles,
        "best": best,
        "best_n": sum(1 for p in positions if p == best) if best is not None else 0,
        "names": names,
        "lineages": lineages,
        "drivers_n": len(career),
        "in_2025": LAST_SEASON in by_season,
    }
    per_race: Counter = Counter((r.race, r.driver_id) for r in rows)
    detail = {
        **summary,
        "season_rows": season_rows,
        "drivers": career,
        "races": [_race_row(ctx, r, per_race[(r.race, r.driver_id)] > 1) for r in rows],
    }
    return summary, detail


def build_all(ctx: _Context, write: Callable[[str, object], None]) -> dict:
    """constructors.json과 constructor/<id>.json을 쓰고 개수를 돌려준다."""
    engines = _engines(ctx.t, ctx.race)
    kmap = kit_map(ctx.t)
    by_cid: dict[str, list[Row]] = {}
    for r in ctx.race:
        by_cid.setdefault(r.constructor_id, []).append(r)
    summaries = []
    for cid in sorted(by_cid):
        summary, detail = build_constructor(ctx, cid, by_cid[cid], engines, kmap)
        summaries.append(summary)
        write(f"constructor/{cid}.json", detail)
    summaries.sort(
        key=lambda c: (-c["titles"], -c["wins"], -c["podiums"], -c["entries"], c["name"])
    )
    write("constructors.json", summaries)
    return {"constructors": len(summaries)}
