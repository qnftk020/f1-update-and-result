"""T6(PU 구성요소), T8(규정 아카이브) 산출물을 사이트용 JSON으로 내보낸다.

정제 테이블이 아직 없으면 None을 돌려주고, 사이트는 해당 영역을 "준비 중"으로 표시한다.
"""

from __future__ import annotations

from collections.abc import Callable


def build_engines() -> dict | None:
    return None


def build_regulations() -> dict | None:
    return None


BUILDERS: dict[str, Callable[[], dict | None]] = {
    "engines.json": build_engines,
    "regulations.json": build_regulations,
}
