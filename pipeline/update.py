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
    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    row = races[(races["season"] == season) & (races["round"] == rnd)]
    if row.empty:
        raise SystemExit(f"{season}년 {rnd}라운드가 정제 테이블에 없다")
    r = row.iloc[0]
    return {
        "season": season,
        "round": rnd,
        "race_name": r["race_name"],
        "date": str(r["date"])[:10],
    }


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
    from pipeline.transforms import openf1_tables, pace_index

    info = race(season, rnd)
    sessions = openf1.collect_round(season, info["date"])
    record_openf1_fetch()
    return {
        **info,
        "sessions": sessions,
        "openf1": openf1_tables.build(),
        "race_index_rows": pace_index.build_race(),
        "wet_flags": pace_index.add_qualifying_wet_flags(),
    }


def record_openf1_fetch() -> None:
    from pipeline.http import utc_now_iso
    from pipeline.sources.jolpica import DATASET_FIELDS, DATASET_MANIFEST

    rows = {r["source"]: r for r in manifest.read_rows(DATASET_MANIFEST)}
    row = rows.get("openf1", {"source": "openf1", "name": "sessions-2023-2025"})
    row |= {"version": f"2023-{LAST_SEASON}", "url": "https://api.openf1.org/v1/",
            "fetched_at": utc_now_iso()}  # fmt: skip
    manifest.upsert_rows(DATASET_MANIFEST, [row], key=["source", "name"], fieldnames=DATASET_FIELDS)


def post_race(season: int, rnd: int) -> dict:
    """Jolpica API에서 결과와 순위를 받아 반영하고 퀄리파잉 지수를 다시 만든다."""
    from pipeline.transforms import lineage, pace_index, results_api

    counts = results_api.apply_round(season, rnd, force=True)
    return {
        **race(season, rnd),
        "jolpica": counts,
        "constructor_seasons": lineage.build(),
        "qualifying_index_rows": pace_index.build_qualifying(),
        "wet_flags": pace_index.add_qualifying_wet_flags(),
    }


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
