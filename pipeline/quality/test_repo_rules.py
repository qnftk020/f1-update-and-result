"""저장소 규칙 테스트: 구조, 금지 파일, 문구 규칙."""

from pathlib import Path

from pipeline.config import REPO_ROOT
from pipeline.quality.check_text_rules import find_violations


def test_required_layout_exists():
    for rel in [
        "pipeline/sources",
        "pipeline/parsers",
        "pipeline/transforms",
        "pipeline/quality",
        "data/curated",
        "data/manifests",
        "site",
        "docs",
        "LICENSE",
        "DATA_LICENSE",
    ]:
        assert (REPO_ROOT / rel).exists(), rel


def test_raw_cache_is_gitignored():
    lines = Path(REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/raw/" in lines


def test_no_forbidden_files_or_em_dash():
    assert find_violations() == []
