"""대회 주간 갱신 명령. (T13)

GitHub Actions 워크플로가 부르는 진입점이다. 각 명령은 원문을 예의 있게 받아 정제 테이블을 다시
만들고, 무엇이 바뀌었는지 JSON 한 줄로 출력한다. 워크플로는 그 뒤에 품질 테스트를 돌리고
데이터를 커밋한 다음 사이트를 다시 배포한다.

    uv run python -m pipeline.update fia-weekend --season 2025 --round 24
    uv run python -m pipeline.update post-session --season 2025 --round 24
    uv run python -m pipeline.update post-race --season 2025 --round 24
    uv run python -m pipeline.update regulations
    uv run python -m pipeline.update heartbeat
    uv run python -m pipeline.update race-week [--date 2025-12-05]

스케줄 실행은 2026 시즌으로 범위를 넓힐 때 켠다. 그 전에는 수동 실행으로 2025 대회를 재현해
검증한다(CLAUDE.md "범위 조정").
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from pipeline import manifest
from pipeline.config import CURATED_DIR, LAST_SEASON, MANIFEST_DIR, REPO_ROOT

FIA_DOC_TYPES = ["car_presentation", "pu_new", "pu_used"]


def race(season: int, rnd: int) -> dict:
    """대회명과 결승 날짜.

    races.parquet에는 post-race가 결과를 반영해야 행이 생긴다. 그 전에 도는 fia-weekend와
    post-session을 위해, 정제 테이블에 없으면 Jolpica 시즌 일정(캐시)에서 읽는다.
    """
    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    row = races[(races["season"] == season) & (races["round"] == rnd)]
    if not row.empty:
        r = row.iloc[0]
        return {
            "season": season,
            "round": rnd,
            "race_name": r["race_name"],
            "date": str(r["date"])[:10],
        }
    from pipeline.sources import jolpica

    schedule = jolpica.fetch_api(f"{season}")["RaceTable"]["Races"]
    r = next((r for r in schedule if int(r["round"]) == rnd), None)
    if r is None:
        raise SystemExit(f"{season}년 일정에 {rnd}라운드가 없다")
    return {"season": season, "round": rnd, "race_name": r["raceName"], "date": r["date"][:10]}


def changed_paths() -> list[str]:
    """작업 폴더에서 바뀐 데이터 파일(커밋 대상) 목록."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "--", "data/curated", "data/manifests"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return [line[3:] for line in out.splitlines() if line.strip()]


def fia_weekend(season: int, rnd: int) -> dict:
    """그 대회의 FIA 문서 목록을 다시 읽고, 새 Car Presentation과 PU 문서를 받아 파싱한다."""
    from pipeline.parsers import car_presentation, pu_elements
    from pipeline.sources import fia_docs

    info = race(season, rnd)
    new_docs = fia_docs.index_event(season, info["race_name"])
    event, _ = fia_docs.event_page(season, info["race_name"])
    wanted = {
        r["url"]
        for r in manifest.read_rows(fia_docs.INDEX_MANIFEST)
        if int(r["season"]) == season and r["event"] == event and r["doc_type"] in FIA_DOC_TYPES
    }
    fia_docs.download_documents(FIA_DOC_TYPES, [season], urls=wanted)
    built = {
        "car_presentation": car_presentation.build(),
        "pu_elements": pu_elements.build(),
    }
    failures = [
        r for r in manifest.read_rows("parse_failures.csv")
        if int(r["season"]) == season and r["event"] == event
    ]  # fmt: skip
    return {
        **info,
        "event": event,
        "new_documents": [
            {"doc_type": d["doc_type"], "title": d["title"], "url": d["url"]} for d in new_docs
        ],
        "watched_documents": len(wanted),
        "built": built,
        "parse_failures": failures,
    }


def post_session(season: int, rnd: int) -> dict:
    """OpenF1에서 그 대회의 본 예선과 결승을 받고 레이스 페이스 지수와 우천 플래그를 다시 만든다."""
    from pipeline.sources import openf1
    from pipeline.transforms import pace_index

    info = race(season, rnd)
    sessions = openf1.collect_round(season, info["date"])
    record_openf1_fetch()
    tables = update_openf1_sessions(sessions)
    race_rows = pace_index.build_race()
    return {
        **info,
        "sessions": sessions,
        "openf1": tables,
        "race_index_rows": race_rows,
        # Jolpica 결과가 아직 없으면 그 대회의 레이스 지수가 없다. post-race가 다시 만든다.
        "race_index_status": race_index_status(season, rnd),
        "wet_flags": pace_index.add_qualifying_wet_flags(),
    }


def update_openf1_sessions(keys: list[int]) -> dict[str, int]:
    """받은 세션만 OpenF1 정제 테이블에 더하거나 바꾼다.

    openf1_tables.build()는 2023년부터의 원문 전체를 다시 읽으므로, 원문 캐시가 한 대회분뿐인
    러너에서는 실패한다. 여기서는 커밋된 정제 테이블을 읽고, 이번에 받은 세션 키의 행만 원문으로
    다시 만들어 바꾼다. 대응표(meeting_map, driver_map)는 정제 테이블만 읽으므로 합친 표로
    다시 만든다.
    """
    from pipeline.sources.openf1 import ENDPOINTS
    from pipeline.transforms import openf1_tables as ot

    keys = [int(k) for k in keys]
    fresh = ot.load_sessions(allow_partial=True)
    fresh = fresh[fresh["session_key"].isin(keys)].reset_index(drop=True)
    missing = sorted(set(keys) - set(fresh["session_key"].astype(int)))
    if missing:
        raise RuntimeError(f"OpenF1 원문 캐시에 세션이 없거나 엔드포인트가 빠졌다: {missing}")

    def merged(name: str, new: pd.DataFrame) -> pd.DataFrame:
        path = ot.OUT / f"{name}.parquet"
        if not path.exists():
            return new
        old = pd.read_parquet(path)
        old = old[~old["session_key"].isin(keys)]
        return pd.concat([old, new], ignore_index=True) if len(new) else old

    sessions = merged("sessions", fresh)
    sessions = sessions.sort_values(["date_start"], kind="stable").reset_index(drop=True)
    ot.write_parquet(sessions, "sessions")
    counts = {"sessions": len(sessions)}
    tables = {}
    for endpoint in ENDPOINTS:
        try:
            new = ot.load_endpoint(fresh, endpoint)
        except ValueError:  # 받은 세션 모두 그 엔드포인트가 빈 목록이다(pd.concat에 넣을 것이 없음)
            new = pd.DataFrame(columns=ot.KEEP[endpoint])
        if endpoint == "weather" and len(new):
            new = ot.clean_weather(new)
        df = merged(endpoint, new).sort_values(ot.SORT[endpoint], kind="stable")
        df = df.reset_index(drop=True)
        tables[endpoint] = df
        ot.write_parquet(df, endpoint)
        counts[endpoint] = len(df)
    counts |= refresh_openf1_maps(sessions, tables["drivers"])
    return counts


def refresh_openf1_maps(
    sessions: pd.DataFrame | None = None, drivers: pd.DataFrame | None = None
) -> dict[str, int]:
    """Jolpica와 OpenF1의 미팅·드라이버 대응표를 정제 테이블로 다시 만든다(원문은 읽지 않는다)."""
    from pipeline.transforms import openf1_tables as ot

    if sessions is None:
        sessions = pd.read_parquet(ot.OUT / "sessions.parquet")
    if drivers is None:
        drivers = pd.read_parquet(ot.OUT / "drivers.parquet")
    meeting_map = ot.build_meeting_map(sessions)
    meeting_map.to_csv(ot.OUT / "meeting_map.csv", index=False)
    driver_map = ot.build_driver_map(meeting_map, drivers)
    driver_map.to_csv(ot.OUT / "driver_map.csv", index=False)
    return {"meeting_map": len(meeting_map), "driver_map": len(driver_map)}


def race_index_status(season: int, rnd: int) -> str:
    """그 대회의 레이스 지수 상태.

    - ok: 레이스 지수 행이 있다.
    - unmapped: 미팅 대응표에 그 대회의 결승 세션이 없다. post-race 전에는 races.parquet에
      대회 행이 없어 대응표에 오르지 못한다.
    - no_laps: 결승 세션은 맞췄지만 OpenF1 랩이 없다.
    - unmatched: 결승 랩은 있는데 레이스 지수 행이 없다(팀을 붙이지 못했다).
    """
    of = CURATED_DIR / "openf1"
    meeting_map = pd.read_csv(of / "meeting_map.csv")
    row = meeting_map[(meeting_map["season"] == season) & (meeting_map["round"] == rnd)]
    row = row.dropna(subset=["race_session_key"])
    if row.empty:
        return "unmapped"
    key = int(row.iloc[0]["race_session_key"])
    laps = pd.read_parquet(of / "laps.parquet", columns=["session_key"])
    if not (laps["session_key"] == key).any():
        return "no_laps"
    index_path = CURATED_DIR / "pace" / "race_index.parquet"
    index = pd.read_parquet(index_path, columns=["season", "round"])
    if ((index["season"] == season) & (index["round"] == rnd)).any():
        return "ok"
    return "unmatched"


def record_dataset(row: dict) -> None:
    """datasets.csv에서 (source, name)이 같은 행을 바꾸거나 더한다."""
    from pipeline.sources.jolpica import DATASET_FIELDS, DATASET_MANIFEST

    rows = {(r["source"], r["name"]): r for r in manifest.read_rows(DATASET_MANIFEST)}
    merged = rows.get((row["source"], row["name"]), {}) | row
    manifest.upsert_rows(
        DATASET_MANIFEST, [merged], key=["source", "name"], fieldnames=DATASET_FIELDS
    )


def record_openf1_fetch() -> None:
    from pipeline.http import utc_now_iso

    record_dataset(
        {"source": "openf1", "name": "sessions-2023-2025", "version": f"2023-{LAST_SEASON}",
         "url": "https://api.openf1.org/v1/", "fetched_at": utc_now_iso()}
    )  # fmt: skip


def record_jolpica_api_apply(season: int, rnd: int) -> None:
    """post-race가 API로 반영한 라운드와 시각을 남긴다. 덤프 행(delayed-dump-csv)은 그대로 둔다."""
    from pipeline.http import utc_now_iso
    from pipeline.sources.jolpica import API_BASE

    record_dataset(
        {"source": "jolpica", "name": "api-rounds", "version": f"{season} R{rnd}",
         "url": f"{API_BASE}/", "fetched_at": utc_now_iso()}
    )  # fmt: skip


def post_race(season: int, rnd: int) -> dict:
    """Jolpica API에서 결과와 순위를 받아 반영하고 페이스 지수를 다시 만든다.

    결과가 들어와야 races.parquet에 그 대회가 생기고 레이스 지수에 팀이 붙는다. 그래서 여기서
    미팅·드라이버 대응표와 레이스 지수를 다시 만들고, 결과가 들어오기 전에 라운드를 맞추지 못한
    FIA 문서가 있으면 다시 파싱한다.
    """
    from pipeline import events
    from pipeline.transforms import lineage, pace_index, results_api

    counts = results_api.apply_round(season, rnd, force=True)
    record_jolpica_api_apply(season, rnd)
    events.rounds.cache_clear()
    info = race(season, rnd)
    result = {
        **info,
        "jolpica": counts,
        "constructor_seasons": lineage.build(),
        "fia_reparsed": reparse_unmatched_fia(season, info["race_name"]),
        "openf1_maps": refresh_openf1_maps(),
        "qualifying_index_rows": pace_index.build_qualifying(),
        "race_index_rows": pace_index.build_race(),
        "wet_flags": pace_index.add_qualifying_wet_flags(),
    }
    status = race_index_status(season, rnd)
    if status == "unmatched":
        raise RuntimeError(
            f"{season}년 {rnd}라운드는 결승 랩이 있는데 레이스 지수에 팀을 붙이지 못했다"
        )
    result["race_index_status"] = status
    return result


def reparse_unmatched_fia(season: int, race_name: str) -> dict | None:
    """그 대회의 FIA 문서 중 라운드를 맞추지 못해 검수 대기로 남은 것이 있으면 다시 파싱한다.

    fia-weekend는 결과가 반영되기 전에 돌므로, 그때는 events.round_for가 라운드를 찾지 못한다.
    """
    from pipeline import events

    names = {events.plain(n) for n in events.fia_names_for(season, race_name)}
    unmatched = [
        r for r in manifest.read_rows("parse_failures.csv")
        if int(r["season"]) == season and not r["round"] and events.plain(r["event"]) in names
    ]  # fmt: skip
    if not unmatched:
        return None
    from pipeline.parsers import car_presentation, pu_elements

    return {"car_presentation": car_presentation.build(), "pu_elements": pu_elements.build()}


def regulations() -> dict:
    """fia.com 규정 페이지를 다시 읽어 새 문서(새 Issue)를 찾는다."""
    from pipeline.sources import fia_regulations

    added = fia_regulations.index(force=True)
    return {
        "new_documents": [
            {"season": r["season"], "section": r["section"], "title": r["title"], "url": r["url"]}
            for r in added
        ]
    }


def heartbeat() -> dict:
    """상태 점검: 데이터 범위와 원문 기록 수를 data/manifests/heartbeat.json 에 남긴다."""
    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    last = races.sort_values(["season", "round"]).iloc[-1]
    status = {
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_race": {
            "season": int(last["season"]),
            "round": int(last["round"]),
            "race_name": last["race_name"],
            "date": str(last["date"])[:10],
        },  # fmt: skip
        "manifests": {
            path.name: sum(1 for _ in path.open(encoding="utf-8")) - 1
            for path in sorted(MANIFEST_DIR.glob("*.csv"))
        },
        "parse_failures": len(manifest.read_rows("parse_failures.csv")),
    }
    (MANIFEST_DIR / "heartbeat.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return status


def race_week(today: date) -> dict:
    """오늘이 레이스 주간(결승 사흘 전부터 이틀 뒤까지)인지 Jolpica 일정으로 판단한다."""
    from pipeline.sources import jolpica

    schedule = jolpica.fetch_api(f"{today.year}", force=True)["RaceTable"]["Races"]
    for r in schedule:
        race_day = date.fromisoformat(r["date"])
        if race_day - timedelta(days=3) <= today <= race_day + timedelta(days=2):
            return {
                "race_week": True, "season": int(r["season"]), "round": int(r["round"]),
                "race_name": r["raceName"], "date": r["date"],
                "day_offset": (today - race_day).days,
            }  # fmt: skip
    return {"race_week": False}


def emit(result: dict) -> None:
    """결과를 출력하고, GitHub Actions에서는 다음 단계가 쓸 값을 남긴다."""
    result["changed"] = changed_paths()
    print(json.dumps(result, ensure_ascii=False, default=str))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if result['changed'] else 'false'}\n")
            f.write(f"new_documents={len(result.get('new_documents', []))}\n")
            if "race_week" in result:
                f.write(f"race_week={'true' if result['race_week'] else 'false'}\n")
                f.write(f"season={result.get('season', '')}\n")
                f.write(f"round={result.get('round', '')}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fia-weekend", "post-session", "post-race"):
        p = sub.add_parser(name)
        p.add_argument("--season", type=int, required=True)
        p.add_argument("--round", type=int, required=True)
    sub.add_parser("regulations")
    sub.add_parser("heartbeat")
    p = sub.add_parser("race-week")
    p.add_argument("--date", default=None)
    args = parser.parse_args(argv)

    if args.command == "fia-weekend":
        emit(fia_weekend(args.season, args.round))
    elif args.command == "post-session":
        emit(post_session(args.season, args.round))
    elif args.command == "post-race":
        emit(post_race(args.season, args.round))
    elif args.command == "regulations":
        emit(regulations())
    elif args.command == "heartbeat":
        emit(heartbeat())
    elif args.command == "race-week":
        today = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
        emit(race_week(today))


if __name__ == "__main__":
    main()
