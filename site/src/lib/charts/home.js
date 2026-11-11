// 홈 차트 함수. 다른 차트 함수와 같이 (data, opts)를 받아 요소를 돌려준다. opts.width는 mount()가 넘긴다.
import * as Plot from "@observablehq/plot";
import { C, frameOf, plot, readout, textWidth } from "./core.js";
import { formatPoints } from "../format.ts";

/* ------------------------------------------------------------------ 시즌별 1위와 2위 점수 차이 (세로 막대) */

/**
 * data: [{s, d, dm, d1, d1p, d2, d2p, c, cm, c1, c1p, c2, c2p}] 시즌 순.
 *   d: 드라이버 1위와 2위 점수 차이(1위 점수 대비 %), dm: 점수 차이. c, cm은 컨스트럭터(1958년 전은 null).
 * kind "d" 드라이버, "c" 컨스트럭터. selected: 고른 시즌(핑크 막대와 값 라벨). onSelect(season)는 막대를 누를 때.
 */
export function seasonMargins(data, { width, kind = "d", selected, onSelect, label = "시즌별 1위와 2위의 점수 차" }) {
  const narrow = width < 560;
  const H = narrow ? 210 : 250;
  const mt = 28;
  const mb = 28;
  const ml = 36;
  // 마지막 눈금(2025) 글자가 그림 오른쪽 끝을 넘지 않도록 여백을 둔다
  const mr = 18;
  const key = kind === "c" ? "c" : "d";
  const rows = data.filter((r) => r[key] != null);
  const first = data[0].s;
  const last = data[data.length - 1].s;
  const max = Math.max(...rows.map((r) => r[key]));
  const sel = rows.find((r) => r.s === selected);
  const selAny = data.find((r) => r.s === selected);
  const ticks = [];
  const step = narrow ? 25 : 10;
  for (let y = Math.ceil(first / step) * step; y <= last; y += step) ticks.push(y);
  if (!narrow && last - ticks[ticks.length - 1] >= 4) ticks.push(last);
  const missingTo = rows.length ? rows[0].s - 1 : last;
  const top = max * 1.08;
  const marks = [
    Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 4 }),
    // 고른 시즌 칸: 막대가 아주 낮아도 보이도록 옅은 핑크 띠를 세로 전체에 깐다
    selAny ? Plot.rect([selAny], { x1: (r) => r.s - 0.5, x2: (r) => r.s + 0.5, y1: 0, y2: top, fill: C.s2, fillOpacity: 0.16 }) : null,
    Plot.rectY(rows, {
      x1: (r) => r.s - 0.5, x2: (r) => r.s + 0.5, y: key, insetLeft: narrow ? 0.4 : 0.8, insetRight: narrow ? 0.4 : 0.8,
      fill: (r) => (r.s === selected ? C.s2 : C.s1),
    }),
    Plot.ruleY([0], { stroke: C.axis }),
    Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 4, label: null, tickFormat: (d, i, a) => (i === a.length - 1 ? `${d}%` : d) }),
    Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks, tickFormat: (d) => String(d) }),
  ];
  if (kind === "c" && missingTo >= first && !(selAny && !sel)) {
    marks.push(Plot.text([0], { x: () => first - 0.5, y: () => top, dx: 2, dy: 8, text: () => `${missingTo + 1}년 전 순위 없음`, fill: C.ink3, fontSize: 11, textAnchor: "start" }));
  }
  if (selAny) {
    const sel2 = selAny;
    const txt = sel ? `${sel.s} ${formatPoints(sel[key])}%` : `${sel2.s} 순위 없음`;
    const px = ((sel2.s - first + 0.5) / (last - first + 1)) * (width - ml - mr);
    const anchor = px + textWidth(txt, 12) / 2 > width - ml - mr ? "end" : px - textWidth(txt, 12) / 2 < 0 ? "start" : "middle";
    marks.push(
      ...(sel ? [Plot.ruleX([sel], { x: "s", y1: top, y2: (r) => r[key], stroke: C.s2, strokeWidth: 1 })] : []),
      Plot.text([sel2], { x: "s", y: () => top, dy: -9, text: () => txt, textAnchor: anchor, fill: C.ink, fontWeight: 700, fontSize: 12, stroke: C.paper, strokeWidth: 3, paintOrder: "stroke" }),
    );
  }
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [first - 0.5, last + 0.5] },
    y: { domain: [0, top], nice: false },
    marks,
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((r) => {
    const name1 = kind === "c" ? r.c1 : r.d1;
    const name2 = kind === "c" ? r.c2 : r.d2;
    const p1 = kind === "c" ? r.c1p : r.d1p;
    const p2 = kind === "c" ? r.c2p : r.d2p;
    const diff = kind === "c" ? r.cm : r.dm;
    return {
      px: xs.apply(r.s), py: ys.apply(r[key]), top: mt, bottom: H - mb,
      head: `${r.s} 시즌`,
      rows: [
        { value: `${formatPoints(r[key])}%`, label: `차이 ${formatPoints(diff)}점, 1위 점수 대비`, key: { type: "rect", color: r.s === selected ? C.s2 : C.s1 } },
        { value: `${formatPoints(p1)}점`, label: `1위 ${name1}` },
        { value: `${formatPoints(p2)}점`, label: `2위 ${name2}` },
      ],
      note: onSelect ? "누르면 이 시즌을 고른다." : undefined,
      season: r.s,
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label, onSelect: onSelect ? (s) => onSelect(s.season) : undefined });
  if (sel) w.dataset.idx = String(rows.indexOf(sel));
  return w;
}

