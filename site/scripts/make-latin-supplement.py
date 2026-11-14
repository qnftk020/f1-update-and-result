"""Pretendard 동적 서브셋에 빠진 라틴 글자(á, ä, ö, − 등)만 담은 보조 글꼴을 만든다.

Pretendard(SIL OFL 1.1, Reserved Font Name "Pretendard")의 전체 가변 글꼴에서
글자를 뽑아 이름을 "F1 Latin Supplement"로 바꾼다. OFL은 수정본(서브셋 포함)에
예약 이름을 쓰지 못하게 하므로 이름을 바꾸고, 원래 저작권 고지와 라이선스 문구
(name ID 0, 13, 14)는 그대로 둔다.

글꼴 파일을 바꿀 때만 한 번 돌린다(빌드에는 쓰지 않는다).
fontTools는 프로젝트 의존성에 넣지 않고 그때만 받는다.
  uv run --no-project --with fonttools --with brotli python site/scripts/make-latin-supplement.py
"""

import re
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

SITE = Path(__file__).resolve().parents[1]
SRC = SITE / "node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2"
CSS = SITE / "node_modules/pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css"
OUT = SITE / "src/assets/fonts/f1-latin-supplement.woff2"
CSS_OUT = SITE / "src/styles/latin-supplement.css"
NAME = "F1 Latin Supplement"

# 대상: 라틴 1 보충과 라틴 확장 A(유럽 드라이버 이름의 악센트 글자),
# 루마니아어 ș ț, 수학 빼기 기호(−).
# 이 가운데 동적 서브셋이 이미 덮는 글자는 뺀다.
WANT = [*range(0x00C0, 0x0180), *range(0x0218, 0x021C), 0x2212]


def covered_by_dynamic_subset() -> set[int]:
    cov: set[int] = set()
    for m in re.finditer(r"unicode-range:\s*([^;}]+)", CSS.read_text()):
        for part in m.group(1).split(","):
            a, _, z = part.strip()[2:].partition("-")
            cov.update(range(int(a, 16), int(z or a, 16) + 1))
    return cov


def main() -> None:
    font = TTFont(SRC)
    cmap = font.getBestCmap()
    cov = covered_by_dynamic_subset()
    codes = sorted(c for c in WANT if c in cmap and c not in cov)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.name_IDs = ["*"]  # 저작권(0)과 라이선스(13, 14)를 남긴다
    opts.layout_features = ["*"]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=codes)
    sub.subset(font)
    # 예약 이름 바꾸기: 가족 이름, 전체 이름, PostScript 이름, 고유 ID, 선호 가족 이름
    ps = NAME.replace(" ", "")
    for rec in font["name"].names:
        if rec.nameID in (1, 16, 21):
            rec.string = NAME
        elif rec.nameID == 4:
            rec.string = f"{NAME} Regular"
        elif rec.nameID == 6:
            rec.string = f"{ps}-Regular"
        elif rec.nameID == 3:
            rec.string = f"{ps};derived from Pretendard 1.3.9"
        elif rec.nameID == 25:
            rec.string = ps
    OUT.parent.mkdir(parents=True, exist_ok=True)
    font.save(OUT)
    # 이어진 글자 코드를 범위로 묶어 unicode-range를 만든다
    spans: list[list[int]] = []
    for c in codes:
        if spans and c == spans[-1][1] + 1:
            spans[-1][1] = c
        else:
            spans.append([c, c])
    ranges = ", ".join(f"U+{a:04X}" if a == z else f"U+{a:04X}-{z:04X}" for a, z in spans)
    CSS_OUT.write_text(
        "/* 이 파일은 site/scripts/make-latin-supplement.py가 만든다. 손으로 고치지 않는다.\n"
        "   Pretendard 동적 서브셋에 없는 라틴 글자와 빼기 기호를 담은 보조 글꼴\n"
        "   (Pretendard 1.3.9에서 뽑아 이름을 바꿈, SIL OFL 1.1).\n"
        "   글꼴 목록에서 Pretendard Variable 바로 뒤에 두고,\n"
        "   이 글자를 쓰는 쪽에서만 내려받는다. */\n"
        "@font-face {\n"
        f"  font-family: '{NAME}';\n"
        "  font-style: normal;\n"
        "  font-display: optional;\n"
        "  font-weight: 45 920;\n"
        "  src: url('../assets/fonts/f1-latin-supplement.woff2') format('woff2-variations');\n"
        f"  unicode-range: {ranges};\n"
        "}\n"
    )
    print(
        f"{OUT.name}: 글자 {len(codes)}개, {OUT.stat().st_size / 1024:.1f}KB, 범위 {len(spans)}개"
    )


if __name__ == "__main__":
    main()
