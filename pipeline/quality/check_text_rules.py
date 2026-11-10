"""커밋 전 문구·파일 규칙 검사 (pre-commit과 pytest가 함께 쓴다).

- em dash(U+2014)를 어디에도 쓰지 않는다. 외부 라이선스 원문은 예외.
- PDF와 data/raw/ 아래 파일은 커밋하지 않는다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EM_DASH = chr(0x2014)
EM_DASH_EXEMPT = {"DATA_LICENSE", "LICENSE", "uv.lock", "site/package-lock.json"}
TEXT_SUFFIXES = {
    ".py", ".md", ".astro", ".ts", ".js", ".mjs", ".json", ".yml", ".yaml",
    ".toml", ".csv", ".css", ".html", ".txt",
}  # fmt: skip


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def find_violations(files: list[str] | None = None) -> list[str]:
    problems: list[str] = []
    for rel in files if files is not None else tracked_files():
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        if rel.lower().endswith(".pdf"):
            problems.append(f"{rel}: PDF는 커밋하지 않는다")
            continue
        if rel.startswith("data/raw/"):
            problems.append(f"{rel}: data/raw/ 아래 파일은 커밋하지 않는다")
            continue
        if rel in EM_DASH_EXEMPT or path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if EM_DASH in line:
                problems.append(f"{rel}:{lineno}: em dash(U+2014) 사용 금지")
    return problems


def main(argv: list[str]) -> int:
    problems = find_violations(argv or None)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
