"""data/curated 의 정제 데이터를 사이트 빌드용 JSON으로 내보낸다.

사이트는 서버 코드 없이 여기서 만든 JSON만 읽는다. 태스크가 진행되면서 내보내는 항목을 늘린다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pipeline.config import LAST_SEASON, SITE_DATA_DIR


def write_json(name: str, payload: object) -> None:
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = SITE_DATA_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path.relative_to(SITE_DATA_DIR.parents[3])}")


def build_meta() -> dict:
    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_season": LAST_SEASON,
    }


def main() -> None:
    write_json("meta.json", build_meta())


if __name__ == "__main__":
    main()
