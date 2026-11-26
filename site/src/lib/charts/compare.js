// 드라이버·컨스트럭터 목록 비교 절의 차트. charts.js와 같은 약속을 따른다: (data, {width, ...})를 받아 요소를 돌려주고,
// width < 560이면 좁은 모양으로 그린다. 색은 CSS 변수다.
// 계열은 고른 순서대로 s1(원), s2(네모), s3(세모)이고 색과 모양을 함께 바꾼다. 범례는 페이지가 그리고,
// 넉넉하면 선 끝에 이름을 직접 단다(글자는 잉크 색). 세로축은 하나다.
import * as Plot from "@observablehq/plot";
import { C, dotBox, el, frameOf, linX, placeLabel, plot, readout } from "./core.js";
import { yearTicks } from "./drivers.js";

/** 계열 모양: 범례 열쇠(key-dot, key-sq, key-tri-c)와 차트 표식이 같다 */
export const SERIES = [
  { color: C.s1, symbol: "circle", key: "dot" },
  { color: C.s2, symbol: "square", key: "sq" },
  { color: C.s3, symbol: "triangle", key: "tri-c" },
];

/** 컨스트럭터 챔피언십이 시작한 해. 그 앞 시즌은 컨스트럭터 순위가 없다. */
const CC_FIRST = 1958;

function careerTicks(from, to, narrow) {
  const span = to - from;
  const step = span <= 8 ? 1 : span <= 16 ? (narrow ? 4 : 2) : narrow ? 10 : 5;
  const t = [];
  for (let x = from; x <= to; x++) if (x === from || x % step === 0) t.push(x);
  return t;
}

/**
 * input: {kind: "d" | "c", mode: "year" | "career", series: [{name, short, slot, pts: [{s, x, pos, wins, cum, team, champ, ex}]}]}
 * metric "pos": 시즌 최종 순위(위가 1위). 순위가 없는 시즌은 맨 아래 "미부여" 줄에 빈 원으로 둔다.
 *   컨스트럭터의 1958년 앞 시즌은 챔피언십이 없어 그리지 않는다.
 * metric "cum": 그 시즌까지의 누적 결승 우승. 쉰 해에는 앞 값이 이어진다.
 */
export function compareSeasons(input, { width, metric = "pos", label = "시즌별 비교" }) {
  const narrow = width < 560;
  const { series, mode, kind } = input;
  const ranked = (p) => !(kind === "c" && p.s < CC_FIRST);
  const every = series.flatMap((sr) => sr.pts);
  if (!series.length) return el("p", "fig-fallback", `선택한 ${kind === "c" ? "컨스트럭터" : "드라이버"}가 없다.`);
  if (!every.length) return el("p", "fig-fallback", "표시할 시즌이 없다.");
  const from = Math.min(...every.map((p) => p.x));
  const to = Math.max(...every.map((p) => p.x));
  const ml = 46;
  const mr = narrow ? 12 : 104;
  const mt = 14;
  const mb = 30;
  const H = narrow ? 240 : 280;
  const px = linX(from - 0.5, to + 0.5, ml, width - mr);

  let yDomain;
  let yTicks;
  let U = null;
  let py;
  if (metric === "pos") {
    const pts = every.filter(ranked);
    const maxPos = Math.max(10, ...pts.map((p) => p.pos || 0));
    const unr = pts.some((p) => p.pos == null);
    U = unr ? maxPos + Math.max(2, Math.round(maxPos * 0.12)) : maxPos;
    const base = maxPos <= 12 ? [1, 5, 10] : maxPos <= 24 ? [1, 5, 10, 15, 20] : [1, 10, 20, 30, 40, 50];
    yTicks = base.filter((t) => t <= maxPos);
    if (unr) yTicks = [...yTicks, U];
    yDomain = [1, U];
    py = linX(1, U, mt, H - mb);
  } else {
    const maxCum = Math.max(1, ...every.map((p) => p.cum));
    const step = maxCum <= 5 ? 1 : maxCum <= 12 ? 2 : maxCum <= 30 ? 5 : maxCum <= 60 ? 10 : 20;
    const top = Math.ceil(maxCum / step) * step;
    yTicks = [];
    for (let t = 0; t <= top; t += step) yTicks.push(t);
    yDomain = [0, top];
    py = linX(0, top, H - mb, mt);
  }
  const yOf = (p) => (metric === "pos" ? p.pos ?? U : p.cum);

  const marks = [Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: yTicks.filter((t) => t !== U) })];
  if (U != null && yTicks.includes(U)) marks.push(Plot.ruleY([U], { stroke: C.grid }));
  const obstacles = [];
  const ends = [];
  series.forEach((sr) => {
    const S = SERIES[sr.slot];
    const pts = metric === "pos" ? sr.pts.filter(ranked) : sr.pts;
    if (!pts.length) return;
    const by = new Map(pts.map((p) => [p.x, p]));
    const line = [];
    let carry = null;
    for (let x = pts[0].x; x <= pts[pts.length - 1].x; x++) {
      const p = by.get(x);
      if (metric === "pos") line.push({ x, y: p?.pos ?? NaN });
      else {
        if (p) carry = p.cum;
        line.push({ x, y: carry });
      }
    }
    marks.push(Plot.line(line, { x: "x", y: "y", stroke: S.color, strokeWidth: 2, curve: metric === "pos" ? "linear" : "step-after" }));
    if (metric === "pos") {
      const on = pts.filter((p) => p.pos != null);
      const off = pts.filter((p) => p.pos == null);
      marks.push(
        Plot.dot(on.filter((p) => !p.champ), { x: "x", y: "pos", r: 3.5, symbol: S.symbol, fill: S.color, stroke: C.paper, strokeWidth: 1.5 }),
        Plot.dot(on.filter((p) => p.champ), { x: "x", y: "pos", r: 6, symbol: S.symbol, fill: S.color, stroke: C.paper, strokeWidth: 1.5 }),
        Plot.dot(off, { x: "x", y: () => U, r: 3.5, symbol: S.symbol, fill: C.paper, stroke: S.color, strokeWidth: 1.5 }),
      );
      for (const p of pts) obstacles.push(dotBox(px(p.x), py(yOf(p)), p.champ ? 7 : 5));
    } else {
      const last = pts[pts.length - 1];
      marks.push(Plot.dot([last], { x: "x", y: "cum", r: 4.5, symbol: S.symbol, fill: S.color, stroke: C.paper, strokeWidth: 1.5 }));
      obstacles.push(dotBox(px(last.x), py(last.cum), 6));
    }
    const last = pts[pts.length - 1];
    ends.push({ sr, last });
  });

  // 직접 라벨: 마지막 점 옆에 성(누적 우승은 값도). 자리가 없으면 범례와 툴팁에 맡긴다.
  if (!narrow) {
    const placed = [];
    const bounds = { x0: ml, y0: 0, x1: width, y1: H - mb + 6 };
    for (const { sr, last } of ends) {
      const name = sr.short;
      const texts = metric === "cum" ? [`${name} ${last.cum}`, name] : [name];
      const at = placeLabel({ x: px(last.x), y: py(yOf(last)), texts, obstacles, placed, bounds });
      if (at) {
        marks.push(Plot.text([last], { x: "x", y: () => yOf(last), text: () => at.text, dx: at.dx, dy: at.dy, textAnchor: at.textAnchor, fill: C.ink2, fontSize: 12 }));
      }
    }
  }

  const ticks = mode === "year" ? yearTicks(from, to, narrow) : careerTicks(from, to, narrow);
  marks.push(
    Plot.axisY({
      tickSize: 0,
      tickPadding: 6,
      ticks: yTicks,
      label: null,
      tickFormat: (d) => (metric === "pos" ? (d === U && every.some((p) => ranked(p) && p.pos == null) ? "미부여" : `${d}위`) : String(d)),
    }),
    Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks, tickFormat: (d) => (mode === "year" ? String(d) : `${d}년차`) }),
  );

  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: metric === "pos" ? { domain: yDomain, reverse: true } : { domain: yDomain },
    marks,
  });

  // 읽기 층: x마다 한 자리. 그 x에 시즌이 있는 계열만 줄을 단다.
  const xsAll = [...new Set(every.map((p) => p.x))].sort((a, b) => a - b);
  const stops = xsAll.map((x) => {
    const rows = [];
    for (const sr of series) {
      const p = sr.pts.find((q) => q.x === x);
      if (!p) continue;
      const S = SERIES[sr.slot];
      let value;
      if (metric === "pos") value = !ranked(p) ? "순위 없음" : p.pos ? `${p.pos}위` : p.ex ? "제외" : "미부여";
      else value = `${p.cum}번`;
      const when = mode === "career" ? ` ${p.s}` : "";
      const extra = metric === "pos" && p.champ ? " · 챔피언" : metric === "cum" && p.wins ? ` · 이 시즌 ${p.wins}번` : "";
      rows.push({ value, label: `${sr.short}${when}${extra}${p.team ? ` · ${p.team}` : ""}`, key: { type: S.key, color: S.color } });
    }
    const ys = series.flatMap((sr) => sr.pts.filter((q) => q.x === x && (metric !== "pos" || ranked(q))).map((q) => py(yOf(q))));
    return {
      px: px(x),
      py: ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : (mt + H - mb) / 2,
      top: mt,
      bottom: H - mb,
      head: mode === "year" ? String(x) : `${x}년차`,
      rows,
      note: metric === "pos" && kind === "c" && rows.some((r) => r.value === "순위 없음") ? `컨스트럭터 챔피언십은 ${CC_FIRST}년부터다.` : null,
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}
