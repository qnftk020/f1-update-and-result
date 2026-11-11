"""갱신 명령과 대회명 대응 테스트. (T13)"""

from __future__ import annotations

import shutil
import subprocess
from datetime import date

import pandas as pd
import pytest

from pipeline import events, manifest, update
from pipeline.config import CURATED_DIR, REPO_ROOT
from pipeline.sources import fia_docs


def test_fia_event_names_map_to_rounds():
    """2020년 이후 모든 대회가 FIA 문서 목록의 대회와 서로 맞는다(별칭 포함)."""
    races = pd.read_parquet(CURATED_DIR / "jolpica" / "races.parquet")
    races = races[races["season"] >= 2020]
    pages = {
        (int(r["season"]), events.plain(r["event"])): r["url"]
        for r in manifest.read_rows(fia_docs.EVENT_MANIFEST)
    }
    for r in races.itertuples():
        names = events.fia_names_for(int(r.season), r.race_name)
        found = [n for n in names if (int(r.season), events.plain(n)) in pages]
        assert found, (r.season, r.race_name)
        assert events.round_for(int(r.season), found[0]) == int(r.round)


@pytest.mark.parametrize(
    ("season", "fia_event", "rnd"),
    [
        (2021, "Brazilian Grand Prix", 19),
        (2022, "Mexican Grand Prix", 20),
        (2020, "Formula 1 70th Anniversary Grand Prix", 5),
        (2025, "Abu Dhabi Grand Prix", 24),
        (2024, "Bahrain Tests Season", None),
        (2020, "Australian Grand Prix", None),  # 취소된 대회
    ],
)
def test_round_for(season, fia_event, rnd):
    assert events.round_for(season, fia_event) == rnd


def test_watched_documents_all_have_rounds():
    rows = manifest.read_rows(fia_docs.INDEX_MANIFEST)
    watched = [r for r in rows if r["doc_type"] in update.FIA_DOC_TYPES]
    assert len(watched) > 300
    assert all(events.round_for(int(r["season"]), r["event"]) is not None for r in watched)


def test_race_week_window(monkeypatch):
    from pipeline.sources import jolpica

    schedule = {"RaceTable": {"Races": [
        {"season": "2025", "round": "24", "raceName": "Abu Dhabi Grand Prix", "date": "2025-12-07"}
    ]}}  # fmt: skip
    monkeypatch.setattr(jolpica, "fetch_api", lambda *a, **k: schedule)
    assert update.race_week(date(2025, 12, 3))["race_week"] is False
    thursday = update.race_week(date(2025, 12, 4))
    assert thursday["race_week"] and thursday["round"] == 24 and thursday["day_offset"] == -3
    assert update.race_week(date(2025, 12, 8))["day_offset"] == 1
    assert update.race_week(date(2025, 12, 10))["race_week"] is False


def test_heartbeat_writes_status(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "MANIFEST_DIR", tmp_path)
    (tmp_path / "x.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    status = update.heartbeat()
    assert status["manifests"] == {"x.csv": 2}
    assert status["last_race"]["season"] == 2025 and status["last_race"]["round"] == 24
    assert (tmp_path / "heartbeat.json").exists()


# 갱신 명령의 흐름 (네트워크 없이 원문 수집과 무거운 단계를 바꿔 끼운다)


def test_race_falls_back_to_schedule(monkeypatch):
    """결과가 반영되기 전(races.parquet에 행이 없을 때)에는 Jolpica 일정에서 대회를 읽는다."""
    from pipeline.sources import jolpica

    schedule = {"RaceTable": {"Races": [
        {"season": "2026", "round": "22", "raceName": "Las Vegas Grand Prix", "date": "2026-11-21"}
    ]}}  # fmt: skip
    monkeypatch.setattr(jolpica, "fetch_api", lambda *a, **k: schedule)
    assert update.race(2026, 22) == {
        "season": 2026, "round": 22, "race_name": "Las Vegas Grand Prix", "date": "2026-11-21"
    }  # fmt: skip
    with pytest.raises(SystemExit, match="일정에 23라운드가 없다"):
        update.race(2026, 23)
    assert update.race(2025, 24)["race_name"] == "Abu Dhabi Grand Prix"  # 정제 테이블이 먼저다


def _openf1_raw(raw, year: int, sessions: list[tuple[int, str, str]], *, empty_pit=False) -> None:
    """세션 목록과 세션별 엔드포인트 원문을 흉내 낸다. empty_pit이면 pit을 빈 목록으로 둔다."""
    import json

    from pipeline.sources.openf1 import ENDPOINTS

    rows = [
        {"session_key": k, "meeting_key": k * 10, "year": year, "session_name": name,
         "date_start": start, "date_end": start, "location": "X", "country_name": "Y",
         "circuit_short_name": "Z", "circuit_key": 1, "is_cancelled": False}
        for k, name, start in sessions
    ]  # fmt: skip
    (raw / str(year)).mkdir(parents=True, exist_ok=True)
    (raw / str(year) / "sessions.json").write_text(json.dumps(rows), encoding="utf-8")
    for k, _, start in sessions:
        folder = raw / str(year) / str(k)
        folder.mkdir()
        for e in ENDPOINTS:
            row = {"session_key": k, "driver_number": 1, "lap_number": 1, "stint_number": 1,
                   "date": start, "position": 1, "message": "m", "track_temperature": 0.0,
                   "humidity": 50.0, "pressure": 1000.0}  # fmt: skip
            body = [] if empty_pit and e == "pit" else [row]
            (folder / f"{e}.json").write_text(json.dumps(body), encoding="utf-8")


def test_post_session_updates_only_received_sessions(tmp_path, monkeypatch):
    """원문 캐시에 이번 대회분만 있는 러너에서도 정제 테이블에 그 대회를 더한다."""
    from pipeline.sources import openf1
    from pipeline.transforms import openf1_tables as ot
    from pipeline.transforms import pace_index

    raw, out = tmp_path / "raw", tmp_path / "out"
    monkeypatch.setattr(ot, "RAW", raw)
    monkeypatch.setattr(ot, "OUT", out)
    monkeypatch.setattr(ot, "build_meeting_map", lambda s: s[["session_key"]])
    monkeypatch.setattr(ot, "build_driver_map", lambda m, d: d[["session_key"]])
    # 지난 시즌 세션 하나로 커밋된 정제 테이블을 만든 뒤, 그 원문은 지운다(차가운 러너).
    _openf1_raw(raw, 2024, [(50, "Race", "2024-12-08T13:00:00+00:00")])
    ot.build(allow_partial=True)
    shutil.rmtree(raw / "2024")
    _openf1_raw(raw, 2025, [
        (1, "Qualifying", "2025-12-06T14:00:00+00:00"), (2, "Race", "2025-12-07T13:00:00+00:00")
    ], empty_pit=True)  # fmt: skip

    info = {"season": 2025, "round": 24, "race_name": "Abu Dhabi Grand Prix", "date": "2025-12-07"}
    monkeypatch.setattr(update, "race", lambda s, r: info)
    monkeypatch.setattr(openf1, "collect_round", lambda year, day: [1, 2])
    monkeypatch.setattr(update, "record_openf1_fetch", lambda: None)
    monkeypatch.setattr(update, "race_index_status", lambda s, r: "unmapped", raising=False)
    monkeypatch.setattr(pace_index, "build_race", lambda: 0)
    monkeypatch.setattr(pace_index, "add_qualifying_wet_flags", dict)
    result = update.post_session(2025, 24)

    assert result["openf1"]["sessions"] == 3
    sessions = pd.read_parquet(out / "sessions.parquet")
    assert sessions["session_key"].tolist() == [50, 1, 2]  # 시작 시각 순
    laps = pd.read_parquet(out / "laps.parquet")
    assert sorted(laps["session_key"]) == [1, 2, 50]
    weather = pd.read_parquet(out / "weather.parquet")
    assert weather["track_temperature"].isna().all()  # 노면 온도 0.0은 결측
    pit = pd.read_parquet(out / "pit.parquet")
    assert pit["session_key"].tolist() == [50]  # 받은 세션의 pit이 모두 비어도 된다
    assert len(pd.read_csv(out / "meeting_map.csv")) == 3

    # 같은 대회를 다시 돌려도 행이 늘지 않는다.
    update.update_openf1_sessions([1, 2])
    assert len(pd.read_parquet(out / "laps.parquet")) == 3


def test_post_session_reports_missing_raw(tmp_path, monkeypatch):
    from pipeline.transforms import openf1_tables as ot

    monkeypatch.setattr(ot, "RAW", tmp_path / "raw")
    monkeypatch.setattr(ot, "OUT", tmp_path / "out")
    _openf1_raw(tmp_path / "raw", 2025, [(1, "Race", "2025-12-07T13:00:00+00:00")])
    with pytest.raises(RuntimeError, match=r"\[2\]"):
        update.update_openf1_sessions([1, 2])


@pytest.fixture
def post_race_stubs(tmp_path, monkeypatch):
    """post-race의 무거운 단계를 기록만 하는 함수로 바꾼다. 호출 순서를 돌려준다."""
    from pipeline.transforms import lineage, pace_index, results_api

    calls: list[str] = []

    def stub(name, value=0):
        return lambda *a, **k: calls.append(name) or value

    monkeypatch.setattr(manifest, "MANIFEST_DIR", tmp_path)
    monkeypatch.setattr(results_api, "apply_round", stub("apply_round", {}))
    monkeypatch.setattr(lineage, "build", stub("lineage"))
    monkeypatch.setattr(update, "reparse_unmatched_fia", stub("reparse"), raising=False)
    monkeypatch.setattr(update, "refresh_openf1_maps", stub("maps", {}), raising=False)
    monkeypatch.setattr(pace_index, "build_qualifying", stub("qualifying"))
    monkeypatch.setattr(pace_index, "build_race", stub("race"))
    monkeypatch.setattr(pace_index, "add_qualifying_wet_flags", stub("wet", {}))
    return calls


def test_post_race_rebuilds_race_index(post_race_stubs, monkeypatch):
    """결과가 들어온 뒤 대응표와 레이스 지수를 다시 만들고, 그 다음에 우천 플래그를 붙인다."""
    monkeypatch.setattr(update, "race_index_status", lambda s, r: "ok", raising=False)
    result = update.post_race(2025, 24)
    calls = post_race_stubs
    assert calls.index("apply_round") < calls.index("maps") < calls.index("race")
    assert calls.index("race") < calls.index("wet")
    assert result["race_index_status"] == "ok"


def test_post_race_fails_when_laps_have_no_team(post_race_stubs, monkeypatch):
    monkeypatch.setattr(update, "race_index_status", lambda s, r: "unmatched", raising=False)
    with pytest.raises(RuntimeError, match="팀을 붙이지 못했다"):
        update.post_race(2025, 24)


def test_race_index_status_committed_data():
    assert update.race_index_status(2025, 24) == "ok"
    assert update.race_index_status(2026, 1) == "unmapped"


def test_post_race_records_api_apply(post_race_stubs, monkeypatch):
    """API로 반영한 시각을 datasets.csv에 남기고, 덤프 행과 OpenF1 행은 건드리지 않는다."""
    from pipeline.sources.jolpica import DATASET_FIELDS, DATASET_MANIFEST

    monkeypatch.setattr(update, "race_index_status", lambda s, r: "ok", raising=False)
    dump = {"source": "jolpica", "name": "delayed-dump-csv", "version": "2026-10-27T07:12:03Z",
            "url": "https://api.jolpi.ca/data/dumps/download/delayed/?dump_type=csv",
            "sha256": "abc", "bytes": "1", "upstream_published_at": "2026-10-27T07:12:03Z",
            "fetched_at": "2026-11-10T15:42:35Z"}  # fmt: skip
    of1 = {"source": "openf1", "name": "sessions-2023-2025", "version": "2023-2025",
           "url": "https://api.openf1.org/v1/", "fetched_at": "2026-11-11T01:55:03Z"}  # fmt: skip
    manifest.write_rows(DATASET_MANIFEST, [dump, of1], DATASET_FIELDS)
    update.post_race(2025, 24)
    rows = {(r["source"], r["name"]): r for r in manifest.read_rows(DATASET_MANIFEST)}
    api = rows[("jolpica", "api-rounds")]
    assert api["version"] == "2025 R24" and api["fetched_at"] > dump["fetched_at"]
    assert rows[("jolpica", "delayed-dump-csv")] == {k: dump.get(k, "") for k in DATASET_FIELDS}

    update.record_openf1_fetch()
    rows = {(r["source"], r["name"]): r for r in manifest.read_rows(DATASET_MANIFEST)}
    assert len(rows) == 3
    assert rows[("openf1", "sessions-2023-2025")]["fetched_at"] > of1["fetched_at"]
    assert rows[("jolpica", "api-rounds")] == api


def test_reparse_unmatched_fia(tmp_path, monkeypatch):
    """결과 반영 전에 라운드를 맞추지 못한 그 대회 문서가 있을 때만 FIA 문서를 다시 파싱한다."""
    import sys
    import types

    import pipeline.parsers

    monkeypatch.setattr(manifest, "MANIFEST_DIR", tmp_path)
    fake = {}
    for name in ("car_presentation", "pu_elements"):
        module = types.SimpleNamespace(build=lambda name=name: f"{name} built")
        fake[name] = module
        monkeypatch.setitem(sys.modules, f"pipeline.parsers.{name}", module)
        monkeypatch.setattr(pipeline.parsers, name, module, raising=False)
    fields = ["season", "round", "event", "doc_type", "url", "problems", "recorded_at"]
    other = {"season": "2025", "round": "23", "event": "Qatar Grand Prix", "doc_type": "pu_new"}
    manifest.write_rows("parse_failures.csv", [other], fields)
    assert update.reparse_unmatched_fia(2025, "Abu Dhabi Grand Prix") is None
    unmatched = {"season": "2025", "round": "", "event": "Abu Dhabi Grand Prix",
                 "doc_type": "car_presentation"}  # fmt: skip
    manifest.write_rows("parse_failures.csv", [other, unmatched], fields)
    assert update.reparse_unmatched_fia(2025, "Abu Dhabi Grand Prix") == {
        "car_presentation": "car_presentation built", "pu_elements": "pu_elements built"
    }  # fmt: skip


# 워크플로 설정 (실제 실행 대신 YAML과 단계의 셸 스크립트를 본다)

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CALLERS = ["fia-weekend-watch.yml", "post-session.yml", "post-race.yml"]
# 2026-11-11에 `gh api repos/<action>/tags`로 있는 것을 확인한 태그와 커밋.
PUBLISHED_REFS = {
    "actions/checkout": {"v7", "v7.0.1"},
    "actions/setup-node": {"v7", "v7.1.0"},
    "actions/cache": {"v6", "v6.1.0"},
    "actions/configure-pages": {"v6", "v6.0.0"},
    "actions/upload-pages-artifact": {"v5", "v5.0.0"},
    "actions/deploy-pages": {"v5", "v5.0.1"},
    "astral-sh/setup-uv": {"68559e99cc807c1eb7e9238fd43a15bba460eec2", "v10.3.3"},
}


def _workflow(name: str) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _step(job: dict, name: str) -> dict:
    return next(s for s in job["steps"] if s.get("name") == name)


def _run_step(step: dict, env: dict, tmp_path) -> subprocess.CompletedProcess:
    """GitHub가 쓰는 셸 명령으로 단계를 돌린다. shell이 없으면 bash -e, bash면 pipefail이 켜진다."""
    script = tmp_path / "step.sh"
    script.write_text(step["run"], encoding="utf-8")
    shell = {None: ["bash", "-e"], "bash": ["bash", "--noprofile", "--norc", "-eo", "pipefail"]}
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_uv = bin_dir / "uv"  # 호출되면 기록을 남기고 실패한다(네트워크 없음)
    fake_uv.write_text(f'#!/bin/sh\necho called >> "{tmp_path}/uv-called"\nexit 3\n')
    fake_uv.chmod(0o755)
    output = tmp_path / "github_output"
    output.write_text("")
    full_env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "GITHUB_OUTPUT": str(output), **env}
    return subprocess.run(
        [*shell[step.get("shell")], str(script)], cwd=tmp_path, env=full_env,
        capture_output=True, text=True,
    )  # fmt: skip


def test_workflow_actions_use_published_refs():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job in _workflow(path.name)["jobs"].values():
            for step in job.get("steps", []):
                if "uses" not in step:
                    continue
                action, ref = step["uses"].split("@")
                assert ref in PUBLISHED_REFS[action], (path.name, step["uses"])


def test_update_step_fails_when_command_fails(tmp_path):
    """갱신 명령이 실패하면 tee로 넘겨도 단계가 실패해야 품질 테스트와 커밋이 건너뛰어진다."""
    step = _step(_workflow("update-run.yml")["jobs"]["update"], "갱신 실행")
    done = _run_step(step, {"COMMAND": "post-session", "SEASON": "2025", "ROUND": "24"}, tmp_path)
    assert (tmp_path / "uv-called").exists()
    assert done.returncode != 0


def test_new_document_issue_needs_a_count():
    step = _step(_workflow("update-run.yml")["jobs"]["update"], "새 문서 이슈")
    assert "steps.run.outputs.new_documents != ''" in step["if"]


def test_failures_open_one_issue():
    """갱신과 배포 실패는 report-failure가, 대상 라운드를 못 정한 실패는 plan-failure가 맡는다."""
    jobs = _workflow("update-run.yml")["jobs"]
    report = jobs["report-failure"]
    assert set(report["needs"]) == {"update", "deploy"} and report["if"] == "failure()"
    assert report["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert not any("failure()" in str(s.get("if", "")) for s in jobs["update"]["steps"])
    for name in CALLERS:
        jobs = _workflow(name)["jobs"]
        plan_failure = jobs["plan-failure"]
        assert plan_failure["needs"] == "plan" and plan_failure["if"] == "failure()"
        assert "gh issue create" in plan_failure["steps"][0]["run"]


def test_plan_jobs_fail_fast_when_blocked():
    for name in CALLERS:
        assert _workflow(name)["jobs"]["plan"]["env"]["PIPELINE_BLOCK_COOLDOWNS"] == ""


def test_data_update_queue_keeps_pending_runs():
    concurrency = _workflow("update-run.yml")["concurrency"]
    assert concurrency == {"group": "data-update", "cancel-in-progress": False, "queue": "max"}


@pytest.mark.parametrize("name", CALLERS)
def test_plan_needs_both_season_and_round(name, tmp_path):
    step = _step(_workflow(name)["jobs"]["plan"], "대상 라운드 정하기")
    for season, rnd in [("2025", ""), ("", "24")]:
        done = _run_step(step, {"INPUT_SEASON": season, "INPUT_ROUND": rnd}, tmp_path)
        assert done.returncode == 1 and "둘 다 채우거나 둘 다 비워야" in done.stdout
        assert not (tmp_path / "uv-called").exists()  # 오늘의 레이스 주간으로 넘어가지 않는다
    done = _run_step(step, {"INPUT_SEASON": "2025", "INPUT_ROUND": "24"}, tmp_path)
    assert done.returncode == 0
    assert (tmp_path / "github_output").read_text() == "run=true\nseason=2025\nround=24\n"
