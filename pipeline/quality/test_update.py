"""갱신 명령과 대회명 대응 테스트. (T13)"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline import events, manifest, update
from pipeline.config import CURATED_DIR
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
