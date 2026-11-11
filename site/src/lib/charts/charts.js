// F1 업그레이드와 성능 추이: 차트 함수 (design/final/charts.js에서 옮겼다)
// 차트 종류마다 함수 하나다. 각 함수는 (data, opts)를 받아 요소를 돌려준다. opts.width는 mount()가 넘긴다.
// 색은 모두 CSS 변수라서 테마가 바뀌어도 다시 그리지 않는다. 자료 모양은 각 함수 위 주석과
// briefs/site_impl_contract.md에 있다.
import * as Plot from "@observablehq/plot";
import {
  C, CATS, CAT_ORDER, MINUS, SLOTS, SVGNS, bandEdges, box, bracketStrip, catGlyph, dotBox, el, frameOf,
  int, lap, linX, num, placeLabel, plot, readout, roundTick, runs, textWidth,
} from "./core.js";

/* ------------------------------------------------------------------ 퀄리파잉 지수 순위 (가로 막대) */

/**
 * data: [{team, v, gap, ms}] 빠른 순. 단일 계열이라 범례가 없다.
 * v가 null인 팀(두 드라이버 모두 기록이 비어 있음)은 막대 없이 맨 아래 행에 "결측"만 적는다.
 */
export function qualifyingRank(input, { width, label = "퀄리파잉 페이스 지수 순위" }) {
  const have = input.filter((d) => d.v != null);
  const missing = input.filter((d) => d.v == null);
  const data = [...have, ...missing];
  const narrow = width < 480;
  const rowH = 28;
  const ml = Math.max(...data.map((d) => textWidth(d.team))) + 14;
  const mr = narrow ? 44 : 104;
  const max = Math.max(0.001, ...have.map((d) => d.v));
  const svg = plot({
    width, height: data.length * rowH + 44, marginLeft: ml, marginRight: mr, marginTop: 4, marginBottom: 36,
    x: { domain: [0, max * 1.04], nice: false },
    y: { type: "band", domain: data.map((d) => d.team), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: narrow ? 3 : 5 }),
      Plot.barX(have.filter((d) => d.v > 0), { x: "v", y: "team", fill: C.s1, insetTop: (rowH - 14) / 2, insetBottom: (rowH - 14) / 2, rx2: 4 }),
      Plot.dot(have.filter((d) => d.v === 0), { x: 0, y: "team", r: 4.5, fill: C.s1, stroke: C.paper, strokeWidth: 2 }),
      Plot.ruleX([0], { stroke: C.ink3 }),
      Plot.text(have, {
        x: "v", y: "team", dx: 7, textAnchor: "start", fill: C.ink2, fontVariant: "tabular-nums",
        text: (d) => (d.v === 0 ? (narrow ? "0" : "0 (기준)") : narrow || d.gap == null ? num(d.v, 3) : `${num(d.v, 3)}  +${d.gap.toFixed(3)}초`),
      }),
      Plot.text(missing, { x: 0, y: "team", dx: 7, textAnchor: "start", fill: C.ink3, text: () => "결측" }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 13, label: null }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, ticks: narrow ? 3 : 5, label: "세션 최고 랩 대비 (%)", labelAnchor: "right", labelOffset: 32, tickFormat: (d) => num(d, 1) }),
    ],
  });
  const ys = svg.scale("y");
  const xs = svg.scale("x");
  const stops = data.map((d) => (d.v == null
    ? { py: ys.apply(d.team) + rowH / 2, px: xs.apply(0), head: d.team, rows: [{ value: "결측", label: "퀄리파잉 지수" }], note: "두 드라이버 모두 기록이 없다." }
    : {
        py: ys.apply(d.team) + rowH / 2, px: xs.apply(d.v),
        head: d.team,
        rows: [
          { value: `${num(d.v, 3)}%`, label: "퀄리파잉 지수", key: { type: "rect", color: C.s1 } },
          ...(d.gap != null ? [{ value: `+${d.gap.toFixed(3)}초`, label: "세션 최고 랩과 차이" }] : []),
          ...(d.ms != null ? [{ value: lap(d.ms), label: "팀 최고 랩" }] : []),
        ],
      }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "y", label, band: 0, rowH });
  return w;
}

/* ------------------------------------------------------------------ 레이스 지수와 95% 구간 (가로 점과 구간) */

/**
 * data: [{team, v, lo, hi, laps}] 빠른 순. 오른쪽 열에 값과 구간을 숫자로 적는다.
 * v가 null인 팀(클린 랩 8개 미만)은 점과 구간 없이 맨 아래 행에 "결측"만 적는다.
 */
export function raceIntervals(input, { width, label = "레이스 페이스 지수와 95% 구간" }) {
  const have = input.filter((d) => d.v != null);
  const missing = input.filter((d) => d.v == null);
  const data = [...have, ...missing];
  const narrow = width < 480;
  const rowH = 28;
  const ml = Math.max(...data.map((d) => textWidth(d.team))) + 14;
  const mr = narrow ? 52 : 168;
  const lo = Math.min(...have.map((d) => d.lo), 0);
  const hi = Math.max(...have.map((d) => d.hi), 0);
  const pad = (hi - lo) * 0.06;
  const svg = plot({
    width, height: data.length * rowH + 66, marginLeft: ml, marginRight: mr, marginTop: 26, marginBottom: 36,
    x: { domain: [lo - pad, hi + pad] },
    y: { type: "band", domain: data.map((d) => d.team), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: narrow ? 3 : 6 }),
      Plot.ruleX([0], { stroke: C.ink3 }),
      Plot.text(["필드 중앙값"], { x: 0, frameAnchor: "top", dy: -14, fill: C.ink2, fontSize: 12 }),
      Plot.ruleY(have, { y: "team", x1: "lo", x2: "hi", stroke: C.s1, strokeWidth: 2, strokeLinecap: "round" }),
      Plot.dot(have, { x: "v", y: "team", r: 4.5, fill: C.s1, stroke: C.paper, strokeWidth: 2 }),
      Plot.text(have, {
        y: "team", frameAnchor: "right", dx: mr - 2, textAnchor: "end", fill: C.ink2, fontVariant: "tabular-nums",
        text: (d) => (narrow ? num(d.v, 2, { sign: true }) : `${num(d.v, 2, { sign: true })}  (${num(d.lo, 2, { sign: true })} ~ ${num(d.hi, 2, { sign: true })})`),
      }),
      Plot.text(missing, { y: "team", frameAnchor: "right", dx: mr - 2, textAnchor: "end", fill: C.ink3, text: () => "결측" }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 13, label: null }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, ticks: narrow ? 3 : 6, label: "필드 중앙값 대비 (%)", labelAnchor: "right", labelOffset: 32, tickFormat: (d) => num(d, 1, { sign: true }) }),
    ],
  });
  const ys = svg.scale("y");
  const xs = svg.scale("x");
  const stops = data.map((d) => {
    if (d.v == null) {
      return { py: ys.apply(d.team) + rowH / 2, px: xs.apply(0), head: d.team, rows: [{ value: "결측", label: "레이스 지수" }], note: "클린 랩이 8개 미만이라 지수를 내지 않았다." };
    }
    const crosses = d.lo <= 0 && d.hi >= 0;
    return {
      py: ys.apply(d.team) + rowH / 2, px: xs.apply(d.hi),
      head: d.team,
      rows: [
        { value: `${num(d.v, 2, { sign: true })}%`, label: "레이스 지수", key: { type: "dot", color: C.s1 } },
        { value: `${num(d.lo, 2, { sign: true })} ~ ${num(d.hi, 2, { sign: true })}`, label: "95% 구간", key: { type: "line", color: C.s1 } },
        { value: `${d.laps}랩`, label: "클린 랩" },
      ],
      note: crosses ? "구간이 0에 걸쳐 필드 중앙값과 구별되지 않는다." : d.hi < 0 ? "구간 전체가 필드 중앙값보다 빠른 쪽이다." : "구간 전체가 필드 중앙값보다 느린 쪽이다.",
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "y", label, rowH });
  return w;
}

/* ------------------------------------------------------------------ 출발 순위와 결승 순위 (덤벨) */

/** data: 결승 분류 순서 [{code, name, team, grid, pos}]. 5칸 이상 바뀐 차만 변화량을 적는다. */
export function gridToFinish(data, { width, label = "출발 순위와 결승 순위" }) {
  const rowH = 20;
  const n = data.length;
  const svg = plot({
    width, height: n * rowH + 44, marginLeft: 44, marginRight: 34, marginTop: 6, marginBottom: 34,
    x: { domain: [0.5, n + 0.5] },
    y: { type: "band", domain: data.map((d) => d.code), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: [1, 5, 10, 15, 20] }),
      Plot.link(data, { x1: "grid", x2: "pos", y1: "code", y2: "code", stroke: C.ink3, strokeWidth: 1.5 }),
      Plot.dot(data, { x: "grid", y: "code", r: 4, fill: C.paper, stroke: C.ink2, strokeWidth: 1.5 }),
      Plot.dot(data, { x: "pos", y: "code", r: 4.5, fill: C.s1, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.text(data.filter((d) => Math.abs(d.grid - d.pos) >= 5), {
        x: (d) => Math.max(d.grid, d.pos), y: "code", dx: 9, textAnchor: "start", fill: C.ink2, fontVariant: "tabular-nums",
        text: (d) => (d.grid > d.pos ? `+${d.grid - d.pos}` : `${MINUS}${d.pos - d.grid}`),
      }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink2, fontFamily: "var(--font-mono)", fontSize: 11, label: null }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, ticks: [1, 5, 10, 15, 20], label: "순위", labelAnchor: "right", labelOffset: 30 }),
    ],
  });
  const ys = svg.scale("y");
  const xs = svg.scale("x");
  const stops = data.map((d) => ({
    py: ys.apply(d.code) + rowH / 2, px: xs.apply(Math.max(d.grid, d.pos)),
    head: `${d.name} (${d.team})`,
    rows: [
      { value: `${d.grid}위`, label: "출발", key: { type: "ring", color: C.ink2 } },
      { value: `${d.pos}위`, label: "결승", key: { type: "dot", color: C.s1 } },
      { value: d.grid === d.pos ? "0" : d.grid > d.pos ? `+${d.grid - d.pos}` : `${MINUS}${d.pos - d.grid}`, label: "순위 변화" },
    ],
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "y", label, rowH });
  return w;
}

/* ------------------------------------------------------------------ 라운드별 항목 수 (세로 막대, 단일 계열) */

/** data: [{round, short, n, doc, review}] 한 시즌. */
export function roundCounts(data, { width, rounds = 24, label = "라운드별 업그레이드 항목 수", mark }) {
  const narrow = width < 560;
  const dom = Array.from({ length: rounds }, (_, i) => i + 1);
  const by = new Map(data.map((d) => [d.round, d]));
  const max = Math.max(...data.map((d) => d.n));
  const step = (width - 60) / rounds;
  const inset = Math.max(1, (step - Math.min(18, step * 0.66)) / 2);
  const top = data.reduce((a, b) => (b.n > a.n ? b : a));
  const svg = plot({
    width, height: narrow ? 200 : 230, marginLeft: 36, marginRight: 8, marginTop: 24, marginBottom: 30,
    x: { type: "band", domain: dom, padding: 0 },
    y: { domain: [0, max * 1.08], nice: true },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 4 }),
      Plot.barY(dom.filter((r) => !by.has(r)), { x: (r) => r, y1: 0, y2: max * 1.08, fill: C.paper3, stroke: C.axis, strokeWidth: 1 }),
      Plot.barY(data.filter((d) => d.n > 0), { x: "round", y: "n", fill: C.s1, insetLeft: inset, insetRight: inset, ry2: 3 }),
      Plot.dot(data.filter((d) => d.n === 0), { x: "round", y: 0, r: 3.5, fill: C.paper, stroke: C.ink3, strokeWidth: 1.5 }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.text([top], { x: "round", y: "n", dy: -8, dx: -inset, textAnchor: "start", fill: C.ink, fontWeight: 600, text: (d) => `${d.round}라운드 ${d.short} ${d.n}건`, stroke: C.paper, strokeWidth: 3 }),
      mark ? Plot.text([mark], { x: "round", y: (d) => by.get(d.round)?.n ?? 0, dy: -12, textAnchor: "end", dx: step / 2, fill: C.ink, fontWeight: 600, text: "text", stroke: C.paper, strokeWidth: 3 }) : null,
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 4, label: null, tickFormat: (d, i, a) => (i === a.length - 1 ? `${d}건` : d) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, tickFormat: roundTick(narrow, rounds) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = dom.map((r) => {
    const d = by.get(r);
    return {
      px: xs.apply(r) + xs.bandwidth / 2, py: ys.apply(d ? d.n : 0) - 10, top: 24, bottom: (narrow ? 200 : 230) - 30,
      head: d ? `${r}라운드 ${d.short}` : `${r}라운드`,
      rows: d ? [{ value: `${d.n}건`, label: "제출 항목", key: { type: "rect", color: C.s1 } }] : [],
      note: !d ? "공개 문서가 없는 대회다." : d.n === 0 ? "10개 팀 모두 No updates submitted로 제출했다." : d.review ? "검수 대기 문서다." : null,
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 업그레이드 단위 차트 (팀, 시즌별 줄) */

/**
 * data: { [season]: [{round, short, status, doc_review, cats:{...}, n}] }
 * 항목 한 건이 기호 하나다. 기호 모양이 변경 사유 범주를 나타내고 색은 둘째 통로다.
 */
export function upgradeUnits(data, { width, onSelect, selected, label = "업그레이드 단위 차트" }) {
  const narrow = width < 560;
  const seasons = Object.keys(data).map(Number).sort();
  const maxN = Math.max(6, ...seasons.flatMap((s) => data[s].map((d) => d.n)));
  const dom = Array.from({ length: 24 }, (_, i) => i + 1);
  const step = (width - 16) / 24;
  const host = el("div", "units");
  for (const s of seasons) {
    const rows = data[s];
    const pts = [];
    for (const d of rows) {
      let k = 0;
      for (const c of CAT_ORDER) for (let i = 0; i < d.cats[c]; i++) pts.push({ round: d.round, y: k++ + 0.62, cat: c });
    }
    // 기호 크기는 라운드 칸 폭을 따른다(좁은 화면에서 너무 작아지지 않게 칸의 30%, 3.4~4.4px)
    const unit = Math.max(3.4, Math.min(4.4, step * 0.3));
    const h = (maxN + 1.6) * unit * 2.55 + 26;
    const nodoc = runs(rows, (d) => d.status === "nodoc");
    const sel = selected && selected.season === s ? selected.round : null;
    const svg = plot({
      width, height: h, marginLeft: 8, marginRight: 8, marginTop: 6, marginBottom: 26,
      x: { type: "band", domain: dom, padding: 0 },
      y: { domain: [-0.5, maxN + 1.6], axis: null },
      marks: [
        Plot.barY(rows.filter((d) => d.status === "nodoc"), { x: "round", y1: 0, y2: maxN + 1.6, fill: C.paper3 }),
        Plot.ruleX(nodoc, { x: "from", dx: -step / 2, y1: 0, y2: maxN + 1.6, stroke: C.axis }),
        Plot.ruleX(nodoc, { x: "to", dx: step / 2, y1: 0, y2: maxN + 1.6, stroke: C.axis }),
        Plot.text(nodoc.filter((r) => r.to - r.from >= (narrow ? 5 : 3)), { x: (d) => d.from, y: maxN + 0.7, textAnchor: "start", dx: -step / 2 + 6, fill: C.ink2, text: () => "공개 문서가 없는 대회", fontSize: 12 }),
        Plot.ruleY([0], { stroke: C.axis }),
        Plot.rect(rows.filter((d) => d.status === "no_updates"), { x: "round", y1: 0, y2: 0.22, fill: C.ink3, insetLeft: (width / 24) * 0.32, insetRight: (width / 24) * 0.32 }),
        Plot.dot(pts.filter((p) => !CATS[p.cat].hollow), { x: "round", y: "y", symbol: (p) => CATS[p.cat].symbol, fill: (p) => CATS[p.cat].color, r: unit, stroke: "none" }),
        Plot.dot(pts.filter((p) => p.cat === "circuit_specific"), { x: "round", y: "y", symbol: "square", fill: C.paper, stroke: C.s2, strokeWidth: 2, r: unit - 0.6 }),
        Plot.dot(pts.filter((p) => p.cat === "other"), { x: "round", y: "y", symbol: "times", stroke: C.ctx, strokeWidth: 2, r: unit }),
        Plot.dot(rows.filter((d) => d.doc_review), { x: "round", y: (d) => d.n + 1.05, symbol: "triangle", r: 6.5, fill: C.warn, stroke: C.warnInk, strokeWidth: 1.2 }),
        Plot.text(rows.filter((d) => d.doc_review), { x: "round", y: (d) => d.n + 1.05, text: () => "!", fill: C.warnInk, fontSize: 9, fontWeight: 800, dy: 1 }),
        narrow ? null : Plot.text(rows.filter((d) => d.doc_review), { x: "round", y: (d) => d.n + 1.05, text: () => "검수 대기", textAnchor: "end", dx: -11, fill: C.ink, fontSize: 12, fontWeight: 600, stroke: C.paper, strokeWidth: 3 }),
        sel ? Plot.rect([sel], { x: (r) => r, y1: -0.5, y2: -0.32, fill: C.ink, insetLeft: 2, insetRight: 2 }) : null,
        Plot.axisX({ tickSize: 0, tickPadding: 5, label: null, tickFormat: (r) => (r > rows.length ? "" : roundTick(narrow, rows.length)(r)), fontWeight: (r) => (r === sel ? 700 : 400), fill: (r) => (r === sel ? C.ink : C.ink3) }),
      ],
    });
    // 문서가 없는 구간 띠의 오른쪽 끝을 칸 끝까지 넓힌다
    const xs = svg.scale("x");
    const stops = rows.map((d) => {
      const lines = [];
      if (d.status === "nodoc") lines.push({ value: "문서 부재", label: "FIA 공개 문서" });
      else if (d.status === "no_updates") lines.push({ value: "0건", label: "No updates submitted" });
      else for (const c of CAT_ORDER) if (d.cats[c]) lines.push({ value: `${d.cats[c]}건`, label: CATS[c].label, key: { type: "glyph", cat: c } });
      return {
        px: xs.apply(d.round) + xs.bandwidth / 2, py: 30, top: 0, bottom: h - 26,
        head: `${s} ${d.round}라운드 ${d.short}`, rows: lines,
        note: d.doc_review ? "검수 대기 문서다. 다른 팀의 쪽을 자동으로 읽지 못해 문서 전체를 검수 대기로 둔다." : d.status === "nodoc" ? "FIA가 공개한 문서가 없는 대회다." : d.n ? "Enter나 클릭으로 아래 목록을 이 대회로 바꾼다." : null,
        season: s, round: d.round,
      };
    });
    const row = el("div", "unit-row");
    const yr = el("span", "unit-year", String(s));
    const w = frameOf(svg);
    readout(w, svg, stops, { axis: "x", label: `${s} 시즌 ${label}`, onSelect: onSelect ? (st) => onSelect(st.season, st.round) : null });
    row.append(yr, w);
    host.append(row);
  }
  return host;
}

/**
 * 업그레이드 신고 줄: 같은 라운드 축 아래 세모와 항목 수. 이웃한 두 라운드의 숫자가 라운드 간격보다 넓으면
 * 숫자를 빼고 세모만 둔다(값은 툴팁과 표 보기에 있다). 세모 크기도 라운드 간격에 맞춘다.
 */
function railMarks(rail, step) {
  if (!rail.length) return { marks: [], note: null };
  const by = new Map(rail.map((r) => [r.round, r.n]));
  const tight = rail.some((r) => by.has(r.round + 1) && step < (textWidth(r.n, 11) + textWidth(by.get(r.round + 1), 11)) / 2 + 4);
  const r = Math.max(2.6, Math.min(4.2, step * 0.42));
  const marks = [Plot.dot(rail, { x: "round", frameAnchor: "bottom", dy: 36, symbol: "triangle", r, fill: C.ink })];
  if (!tight) marks.push(Plot.text(rail, { x: "round", frameAnchor: "bottom", dy: 50, text: "n", fill: C.ink2, fontSize: 11 }));
  return { marks, note: tight ? "라운드 간격이 좁아 신고 항목 수는 툴팁과 표 보기에 둔다." : null };
}

/* ------------------------------------------------------------------ 팀 대 필드 퀄리파잉 추이 (강조형) */

/**
 * rounds: [{round, short, date, wet, field:{q1,med,q3}, teams:{cid: v}}]
 * 위가 빠르다(세로축 뒤집기). 필드는 중앙값 선과 가운데 절반 띠로 줄인다.
 */
export function paceTrend(rounds, { width, cid, team, rail = [], label }) {
  const narrow = width < 560;
  const dry = rounds.filter((d) => d.wet !== "wet" && d.teams[cid] != null);
  const vals = rounds.map((d) => d.teams[cid]).filter((x) => x != null);
  const fmax = Math.max(...rounds.filter((d) => d.field).map((d) => d.field.q3));
  const dryVals = dry.map((d) => d.teams[cid]);
  const ymax = Math.max(...dryVals, fmax) * 1.08;
  const offWet = rounds.filter((d) => d.wet === "wet" && d.teams[cid] != null && d.teams[cid] > ymax);
  const H = narrow ? 260 : 300;
  const mt = 26;
  const mb = rail.length ? 62 : 30;
  const mr = narrow ? 64 : 104;
  const n = Math.max(...rounds.map((d) => d.round));
  const wet = runs(rounds, (d) => d.wet === "wet");
  const series = rounds.map((d) => ({ round: d.round, t: d.wet === "wet" ? NaN : d.teams[cid] ?? NaN, q1: d.wet === "wet" || !d.field ? NaN : d.field.q1, q3: d.wet === "wet" || !d.field ? NaN : d.field.q3, med: d.wet === "wet" || !d.field ? NaN : d.field.med }));
  const best = dry.reduce((a, b) => (b.teams[cid] < a.teams[cid] ? b : a), dry[0]);
  const worst = dry.reduce((a, b) => (b.teams[cid] > a.teams[cid] ? b : a), dry[0]);
  const last = [...series].reverse().find((d) => !Number.isNaN(d.t));
  const lastMed = [...series].reverse().find((d) => !Number.isNaN(d.med));
  const yPx = (val) => mt + (val / ymax) * (H - mt - mb);
  const xPx = linX(0.5, n + 0.5, 40, width - mr);
  const showMedLabel = last && lastMed && Math.abs(yPx(last.t) - yPx(lastMed.med)) > 15;
  // 가장 좋은 값, 가장 나쁜 값 라벨: 점, 끝 이름과 겹치지 않는 자리에 둔다
  const obstacles = rounds.filter((d) => d.teams[cid] != null && d.teams[cid] <= ymax).map((d) => dotBox(xPx(d.round), yPx(d.teams[cid])));
  if (last) obstacles.push(box(xPx(last.round) + 6, yPx(last.t) - 9, xPx(last.round) + 10 + textWidth(team), yPx(last.t) + 9));
  if (showMedLabel) obstacles.push(box(xPx(lastMed.round) + 6, yPx(lastMed.med) - 9, xPx(lastMed.round) + 10 + textWidth("필드 중앙값"), yPx(lastMed.med) + 9));
  const bounds = box(40, mt, width, H - mb);
  const placed = [];
  const labTexts = (d) => (narrow ? [`${num(d.teams[cid], 3)}%`] : [`${d.round}라운드 ${d.short} ${num(d.teams[cid], 3)}%`, `${num(d.teams[cid], 3)}%`]);
  const labMark = (d) => {
    if (!d) return null;
    const p = placeLabel({ x: xPx(d.round), y: yPx(d.teams[cid]), texts: labTexts(d), obstacles, placed, bounds, preferLeft: d.round > n * 0.75 });
    return p ? Plot.text([d], { x: "round", y: (q) => q.teams[cid], dx: p.dx, dy: p.dy, textAnchor: p.textAnchor, text: () => p.text, fill: C.ink, fontWeight: 600, stroke: C.paper, strokeWidth: 3 }) : null;
  };
  const bestMark = labMark(best);
  const worstMark = worst && worst !== best ? labMark(worst) : null;
  const railM = railMarks(rail, (width - 40 - mr) / n);
  const svg = plot({
    width, height: H, marginLeft: 40, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [0.5, n + 0.5] },
    y: { domain: [0, ymax], reverse: true },
    marks: [
      Plot.rect(wet, { x1: (d) => d.from - 0.5, x2: (d) => d.to + 0.5, y1: 0, y2: ymax, fill: C.paper3 }),
      bandEdges(wet, { y1: 0, y2: ymax }),
      Plot.text(wet, { x: (d) => (d.from + d.to) / 2, frameAnchor: "top", dy: -14, text: () => "우천", fill: C.ink2, fontSize: 11, fontWeight: 600 }),
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 4 }),
      Plot.areaY(series, { x: "round", y1: "q1", y2: "q3", fill: C.band, curve: "linear" }),
      Plot.lineY(series, { x: "round", y: "med", stroke: C.ctx, strokeWidth: 1.5 }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.lineY(series, { x: "round", y: "t", stroke: C.s1, strokeWidth: 2, curve: "linear" }),
      Plot.dot(dry, { x: "round", y: (d) => d.teams[cid], r: 3.5, fill: C.s1, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.dot(rounds.filter((d) => d.wet === "wet" && d.teams[cid] != null && d.teams[cid] <= ymax), { x: "round", y: (d) => d.teams[cid], r: 3.5, fill: C.paper, stroke: C.s1, strokeWidth: 1.5 }),
      bestMark,
      worstMark,
      last ? Plot.text([last], { x: "round", y: "t", dx: 8, textAnchor: "start", text: () => team, fill: C.ink, fontWeight: 700 }) : null,
      showMedLabel ? Plot.text([lastMed], { x: "round", y: "med", dx: 8, textAnchor: "start", text: () => "필드 중앙값", fill: C.ink2 }) : null,
      ...railM.marks,
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 4, label: null, tickFormat: (d) => (d === 0 ? "0" : `${num(d, 1)}%`) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: Array.from({ length: n }, (_, i) => i + 1), tickFormat: roundTick(narrow, n) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const railBy = new Map(rail.map((r) => [r.round, r.n]));
  const stops = rounds.map((d) => {
    const t = d.teams[cid];
    const sorted = Object.values(d.teams).filter((x) => x != null).sort((a, b) => a - b);
    const rows = [
      { value: t == null ? "결측" : `${num(t, 3)}%`, label: team, key: { type: "line", color: C.s1 } },
    ];
    if (d.field) {
      rows.push({ value: `${num(d.field.med, 3)}%`, label: "필드 중앙값", key: { type: "line", color: C.ctx } });
      rows.push({ value: `${num(d.field.q1, 3)} ~ ${num(d.field.q3, 3)}`, label: "가운데 절반", key: { type: "band", color: C.band } });
    }
    if (t != null) rows.push({ value: `${sorted.indexOf(t) + 1}번째`, label: `${sorted.length}개 팀 중` });
    if (railBy.get(d.round)) rows.push({ value: `${railBy.get(d.round)}건`, label: "업그레이드 신고", key: { type: "tri" } });
    return {
      px: xs.apply(d.round), py: t == null ? H / 2 : ys.apply(t), top: mt, bottom: H - mb,
      head: `${d.round}라운드 ${d.short} (${d.date})`, rows,
      note: d.wet === "wet" ? "우천 예선이라 평균과 순위 계산에서 뺐다." : null,
    };
  });
  const notes = [];
  if (offWet.length) notes.push(el("p", "axis-note", `우천 예선 값 ${offWet.length}개는 축 범위를 넘어 그리지 않았다. 값은 표에 있다.`));
  if (railM.note) notes.push(el("p", "axis-note", railM.note));
  const w = frameOf(svg, notes);
  readout(w, svg, stops, { axis: "x", label: label || `${team} 퀄리파잉 지수와 필드` });
  return w;
}

/* ------------------------------------------------------------------ 레이스 지수 추이 (점과 세로 구간) */

/** rounds: [{round, short, date, wet, teams:{cid: [v, lo, hi, laps] | null}}] */
export function raceTrend(rounds, { width, cid, team, rail = [], label }) {
  const narrow = width < 560;
  const H = narrow ? 260 : 300;
  const mt = 26;
  const mb = rail.length ? 62 : 30;
  const mr = narrow ? 64 : 104;
  const n = Math.max(...rounds.map((d) => d.round));
  const pts = rounds.map((d) => ({ round: d.round, short: d.short, date: d.date, wet: d.wet, x: d.teams[cid] })).map((d) => ({ ...d, v: d.x ? d.x[0] : null, lo: d.x ? d.x[1] : null, hi: d.x ? d.x[2] : null, laps: d.x ? d.x[3] : null }));
  const have = pts.filter((d) => d.v != null);
  const dryHave = have.filter((d) => !d.wet);
  const lo = Math.min(0, ...dryHave.map((d) => d.lo));
  const hi = Math.max(0, ...dryHave.map((d) => d.hi));
  const pad = (hi - lo) * 0.08;
  const wet = runs(rounds, (d) => d.wet);
  const dry = have.filter((d) => !d.wet);
  const best = dry.reduce((a, b) => (b.v < a.v ? b : a), dry[0]);
  const worst = dry.reduce((a, b) => (b.v > a.v ? b : a), dry[0]);
  const rPx = (val) => mt + ((val - (lo - pad)) / (hi + pad - (lo - pad))) * (H - mt - mb);
  const xPx = linX(0.5, n + 0.5, 46, width - mr);
  const yIn = (v) => Math.max(lo - pad, Math.min(hi + pad, v));
  // 라벨 자리: 다른 대회의 점과 구간 막대, 오른쪽 "필드 중앙값" 글자와 겹치지 않게 고른다
  const obstacles = have.flatMap((d) => [dotBox(xPx(d.round), rPx(yIn(d.v))), box(xPx(d.round) - 2, rPx(yIn(d.lo)), xPx(d.round) + 2, rPx(yIn(d.hi)))]);
  obstacles.push(box(width - mr + 6, rPx(0) - 9, width, rPx(0) + 9));
  pts.filter((d) => d.v == null).forEach((d) => obstacles.push(box(xPx(d.round) - 14, rPx(0) - 18, xPx(d.round) + 14, rPx(0) - 2)));
  const bounds = box(46, mt, width - mr + 4, H - mb);
  const placed = [];
  const labTexts = (d) => (narrow ? [num(d.v, 2, { sign: true })] : [`${d.round}라운드 ${d.short} ${num(d.v, 2, { sign: true })}%`, `${num(d.v, 2, { sign: true })}%`]);
  const labMark = (d) => {
    if (!d) return null;
    const p = placeLabel({ x: xPx(d.round), y: rPx(d.v), texts: labTexts(d), obstacles, placed, bounds, preferLeft: d.round > n * 0.75 });
    return p ? Plot.text([d], { x: "round", y: "v", dx: p.dx, dy: p.dy, textAnchor: p.textAnchor, text: () => p.text, fill: C.ink, fontWeight: 600, stroke: C.paper, strokeWidth: 3 }) : null;
  };
  const bestMark = labMark(best);
  const worstMark = worst && worst !== best ? labMark(worst) : null;
  const railM = railMarks(rail, (width - 46 - mr) / n);
  const svg = plot({
    width, height: H, marginLeft: 46, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [0.5, n + 0.5] },
    y: { domain: [lo - pad, hi + pad], reverse: true },
    marks: [
      Plot.rect(wet, { x1: (d) => d.from - 0.5, x2: (d) => d.to + 0.5, y1: lo - pad, y2: hi + pad, fill: C.paper3 }),
      bandEdges(wet, { y1: lo - pad, y2: hi + pad }),
      Plot.text(wet, { x: (d) => (d.from + d.to) / 2, frameAnchor: "top", dy: -14, text: () => "우천", fill: C.ink2, fontSize: 11, fontWeight: 600 }),
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 5 }),
      Plot.ruleY([0], { stroke: C.ink3 }),
      Plot.text([0], { y: 0, frameAnchor: "right", dx: 8, textAnchor: "start", text: () => "필드 중앙값", fill: C.ink2 }),
      Plot.ruleX(have.filter((d) => !d.wet), { x: "round", y1: "lo", y2: "hi", stroke: C.s1, strokeWidth: 2, strokeLinecap: "round" }),
      Plot.ruleX(have.filter((d) => d.wet), { x: "round", y1: "lo", y2: "hi", stroke: C.ctx, strokeWidth: 1.5, clip: true }),
      Plot.dot(have.filter((d) => !d.wet), { x: "round", y: "v", r: 4, fill: C.s1, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.dot(have.filter((d) => d.wet && d.v >= lo - pad && d.v <= hi + pad), { x: "round", y: "v", r: 4, fill: C.paper, stroke: C.s1, strokeWidth: 1.5 }),
      Plot.text(pts.filter((d) => d.v == null), { x: "round", y: 0, dy: -10, text: () => "결측", fill: C.ink3, fontSize: 11 }),
      bestMark,
      worstMark,
      ...railM.marks,
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 5, label: null, tickFormat: (d) => (d === 0 ? "0" : `${num(d, 1, { sign: true })}%`) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: Array.from({ length: n }, (_, i) => i + 1), tickFormat: roundTick(narrow, n) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const railBy = new Map(rail.map((r) => [r.round, r.n]));
  const stops = pts.map((d) => {
    const rows = d.v == null
      ? [{ value: "결측", label: "레이스 지수" }]
      : [
          { value: `${num(d.v, 2, { sign: true })}%`, label: "레이스 지수", key: { type: "dot", color: C.s1 } },
          { value: `${num(d.lo, 2, { sign: true })} ~ ${num(d.hi, 2, { sign: true })}`, label: "95% 구간", key: { type: "line", color: d.wet ? C.ctx : C.s1 } },
          { value: `${d.laps}랩`, label: "클린 랩" },
        ];
    if (railBy.get(d.round)) rows.push({ value: `${railBy.get(d.round)}건`, label: "업그레이드 신고", key: { type: "tri" } });
    let note = null;
    if (d.wet) note = "우천 결승이라 기본 분석에서 뺐다.";
    else if (d.v == null) note = "클린 랩이 8개 미만이라 지수를 내지 않았다.";
    else if (d.lo <= 0 && d.hi >= 0) note = "구간이 0에 걸쳐 필드 중앙값과 구별되지 않는다.";
    return { px: xs.apply(d.round), py: d.v == null ? ys.apply(0) : ys.apply(d.v), top: mt, bottom: H - mb, head: `${d.round}라운드 ${d.short} (${d.date})`, rows, note };
  });
  const clipped = have.some((d) => d.wet && (d.lo < lo - pad || d.hi > hi + pad));
  const notes = [];
  if (clipped) notes.push(el("p", "axis-note", "우천 결승의 구간은 축 범위에서 잘라 그렸다. 값은 표에 있다."));
  if (railM.note) notes.push(el("p", "axis-note", railM.note));
  const w = frameOf(svg, notes);
  readout(w, svg, stops, { axis: "x", label: label || `${team} 레이스 지수와 95% 구간` });
  return w;
}

/* ------------------------------------------------------------------ 시대 띠 라벨 (긴 흐름 차트 공통) */

/**
 * 시대 이름을 그림 위 여백에 줄을 나눠 놓는다. 앞 이름과 겹치지 않는 가장 위 줄을 고르고(최대 3줄),
 * 세 줄 모두 막히면 그 이름은 빼고 위의 계보 목록에 맡긴다. 줄 수는 그림 위 여백(marginTop) 계산에 쓴다.
 */
function eraLayout(eras, from, to, xPx, maxRows = 3) {
  const xMax = xPx(to + 0.5);
  const vis = eras.filter((e) => e.to >= from && e.from <= to).map((e) => ({ ...e, a: Math.max(e.from, from), b: Math.min(e.to, to), end: to + 0.5 }));
  const ends = [];
  for (const e of vis) {
    const tw = textWidth(e.team, 12) + 8;
    let x0 = xPx(e.a - 0.5) + 3;
    // 오른쪽 끝 가까이에서 시작하는 이름이 그림 영역을 넘으면 영역 오른쪽 끝에 맞춰 적는다(좁은 화면)
    e.flip = x0 + tw > xMax;
    if (e.flip) x0 = xMax - tw;
    const x1 = x0 + tw;
    let row = ends.findIndex((end) => end <= x0);
    if (row < 0 && ends.length < maxRows) { row = ends.length; ends.push(0); }
    if (row >= 0) ends[row] = x1;
    e.row = row;
  }
  return { vis, rows: Math.max(1, ends.length) };
}
/** base: 가장 아래 시대 줄의 중심이 그림 틀 위에서 떨어진 거리(px). 줄 사이는 15px. */
function eraMarks(layout, rowsY, base = 15) {
  const { vis, rows } = layout;
  return [
    Plot.ruleX(vis.slice(1), { x: (e) => e.a - 0.5, stroke: C.axis }),
    ...Array.from({ length: rows }, (_, k) => Plot.text(vis.filter((e) => e.row === k && !e.flip), { x: (e) => e.a - 0.5, frameAnchor: "top", dy: -(base + 15 * (rows - 1 - k)), dx: 3, textAnchor: "start", text: "team", fill: C.ink, fontWeight: 600, fontSize: 12 })),
    ...Array.from({ length: rows }, (_, k) => Plot.text(vis.filter((e) => e.row === k && e.flip), { x: (e) => e.end, frameAnchor: "top", dy: -(base + 15 * (rows - 1 - k)), dx: 0, textAnchor: "end", text: "team", fill: C.ink, fontWeight: 600, fontSize: 12 })),
    Plot.tickX(vis, { x: (e) => e.a - 0.5, y1: rowsY[0], y2: rowsY[1], stroke: C.axis }),
  ];
}

/* ------------------------------------------------------------------ 시즌 평균 퀄리파잉 지수 (긴 흐름) */

/**
 * seasons: [{season, team, q, ref, field:{q1,med,q3}}], eras: [{team, from, to}]
 * 참고용 시즌(2003-2005)은 빈 고리로만 찍고 선에 잇지 않는다.
 */
export function seasonTrend(seasons, { width, eras, from, to, teamLabel, label = "시즌 평균 퀄리파잉 지수" }) {
  const narrow = width < 560;
  const data = seasons.filter((d) => d.season >= from && d.season <= to && d.q != null);
  const mb = 30;
  const ml = 40;
  const mr = narrow ? 56 : 112;
  const xPx = linX(from - 0.5, to + 0.5, ml, width - mr);
  const eraL = eraLayout(eras, from, to, xPx);
  const mt = 14 + 15 + 15 * (eraL.rows - 1);
  const H = (narrow ? 280 : 320) + (mt - 44);
  const ymax = Math.max(...data.map((d) => Math.max(d.q, d.field ? d.field.q3 : 0))) * 1.08;
  const line = data.map((d) => ({ season: d.season, y: d.ref ? NaN : d.q }));
  const fieldS = data.filter((d) => d.field).map((d) => ({ season: d.season, q1: d.field.q1, q3: d.field.q3, med: d.field.med }));
  const solid = data.filter((d) => !d.ref);
  const best = solid.reduce((a, b) => (b.q < a.q ? b : a), solid[0]);
  const worst = solid.reduce((a, b) => (b.q > a.q ? b : a), solid[0]);
  const ref = data.filter((d) => d.ref);
  const last = data[data.length - 1];
  const right = (d) => d.season > to - (to - from) * 0.25;
  const tickStep = to - from > 20 ? (narrow ? 10 : 4) : narrow ? 2 : 1;
  const ticks = [];
  for (let y = from; y <= to; y++) if ((y - from) % tickStep === 0 || y === to) ticks.push(y);
  if (ticks.length > 1 && ticks[ticks.length - 1] - ticks[ticks.length - 2] < tickStep * 0.6) ticks.splice(ticks.length - 2, 1);
  // 가장 좋은 해, 가장 나쁜 해 라벨: 다른 해의 점과 끝 이름을 피해 놓는다
  const yPx = (v) => mt + (v / ymax) * (H - mt - mb);
  const obstacles = data.map((d) => dotBox(xPx(d.season), yPx(d.q)));
  const endText = last ? (narrow ? teamLabel : `${teamLabel} ${num(last.q, 3)}%`) : "";
  if (last) obstacles.push(box(xPx(last.season) + 6, yPx(last.q) - 9, xPx(last.season) + 10 + textWidth(endText), yPx(last.q) + 9));
  const placed = [];
  const bounds = box(ml, mt, width, H - mb);
  const labTexts = (d) => [`${d.season}년 ${num(d.q, 3)}%`, `${num(d.q, 3)}%`];
  const labMark = (d) => {
    if (!d) return null;
    const p = placeLabel({ x: xPx(d.season), y: yPx(d.q), texts: labTexts(d), obstacles, placed, bounds, preferLeft: right(d) });
    return p ? Plot.text([d], { x: "season", y: "q", dx: p.dx, dy: p.dy, textAnchor: p.textAnchor, text: () => p.text, fill: C.ink, fontWeight: 600, stroke: C.paper, strokeWidth: 3 }) : null;
  };
  const bestMark = labMark(best);
  const worstMark = worst && worst !== best ? labMark(worst) : null;
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { domain: [0, ymax], reverse: true },
    marks: [
      ref.length ? Plot.rect([0], { x1: Math.min(...ref.map((d) => d.season)) - 0.5, x2: Math.max(...ref.map((d) => d.season)) + 0.5, y1: 0, y2: ymax, fill: C.paper2 }) : null,
      ref.length ? Plot.text(["참고용"], { x: (Math.min(...ref.map((d) => d.season)) + Math.max(...ref.map((d) => d.season))) / 2, y: ymax, dy: -8, fill: C.ink2, fontWeight: 600, fontSize: 11 }) : null,
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 5 }),
      ...eraMarks(eraL, [0, ymax]).slice(0, -1),
      Plot.areaY(fieldS, { x: "season", y1: "q1", y2: "q3", fill: C.band }),
      Plot.lineY(fieldS, { x: "season", y: "med", stroke: C.ctx, strokeWidth: 1.5 }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.lineY(line, { x: "season", y: "y", stroke: C.s1, strokeWidth: 2 }),
      Plot.dot(solid, { x: "season", y: "q", r: 3.5, fill: C.s1, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.dot(ref, { x: "season", y: "q", r: 3.5, fill: C.paper, stroke: C.s1, strokeWidth: 1.5 }),
      bestMark,
      worstMark,
      last ? Plot.text([last], { x: "season", y: "q", dx: 8, textAnchor: "start", text: () => endText, fill: C.ink, fontWeight: 700 }) : null,
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 5, label: null, tickFormat: (d) => (d === 0 ? "0" : `${Number.isInteger(d) ? d : num(d, 1)}%`) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks, tickFormat: (d) => String(d) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const segs = [];
  if (from <= 2022) segs.push({ from: Math.max(from, 1996), to: Math.min(2022, to), text: narrow ? "우천 미분류" : `우천 여부 미분류 (${Math.max(from, 1996)}-${Math.min(2022, to)})`, pad: 6 });
  if (to >= 2023) segs.push({ from: Math.max(2023, from), to, text: narrow ? "우천 제외" : "우천 예선 제외", pad: 6 });
  const stops = data.map((d) => ({
    px: xs.apply(d.season), py: ys.apply(d.q), top: mt, bottom: H - mb,
    head: `${d.season} ${d.team}`,
    rows: [
      { value: `${num(d.q, 3)}%`, label: "시즌 평균", key: { type: d.ref ? "ring" : "line", color: C.s1 } },
      ...(d.field ? [{ value: `${num(d.field.med, 3)}%`, label: "필드 중앙값", key: { type: "line", color: C.ctx } }, { value: `${num(d.field.q1, 3)} ~ ${num(d.field.q3, 3)}`, label: "가운데 절반", key: { type: "band", color: C.band } }] : []),
      { value: `${d.qn}개`, label: "평균에 넣은 예선" },
    ],
    note: d.ref ? "참고용 예선 형식(원랩, 합산)이라 선에 잇지 않는다." : d.season <= 2022 ? "우천 여부 미분류 시즌이다." : d.qwet ? `우천 예선 ${d.qwet}개를 뺐다.` : null,
  }));
  const w = frameOf(svg, [bracketStrip(xs, segs, ml)]);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 시즌 최종 컨스트럭터 순위 (계단) */

/** seasons: [{season, team, pos, pts, wins}] 위가 1위다. 순위가 없는 시즌에서 선을 끊는다. */
export function standingsSteps(seasons, { width, eras, from, to, label = "시즌 최종 컨스트럭터 순위" }) {
  const narrow = width < 560;
  const data = seasons.filter((d) => d.season >= from && d.season <= to);
  const mb = 30;
  const ml = 40;
  const mr = narrow ? 16 : 40;
  const maxPos = Math.max(10, ...data.map((d) => d.pos || 0));
  const line = data.map((d) => ({ season: d.season, y: d.pos ?? NaN }));
  const xPx = linX(from - 0.5, to + 0.5, ml, width - mr);
  // 우승 해: 이어진 해를 묶어 한 번만 적는다. 1위 선 위의 따로 둔 줄에 놓아 계단선이 글자를 지나지 않는다.
  const champs = [];
  for (const d of data) {
    if (d.pos !== 1) continue;
    const prev = champs[champs.length - 1];
    if (prev && prev.to === d.season - 1) { prev.to = d.season; prev.text += `·${narrow ? String(d.season).slice(2) : d.season}`; }
    else champs.push({ from: d.season, to: d.season, text: String(d.season) });
  }
  // 우승 라벨끼리 겹치면(좁은 화면) 라벨을 빼고 그림 아래에 한 줄로 적는다
  const cbox = champs.map((c) => { const cx = xPx((c.from + c.to) / 2); const w = textWidth(`${c.text} 우승`) + 8; return [cx - w / 2, cx + w / 2]; });
  const champClash = cbox.some((b, i) => i > 0 && b[0] < cbox[i - 1][1]) || cbox.some((b) => b[0] < ml - 4 || b[1] > width);
  const champRow = champs.length && !champClash;
  const eraL = eraLayout(eras, from, to, xPx);
  const eraBase = champRow ? 31 : 15;
  const mt = 14 + eraBase + 15 * (eraL.rows - 1);
  const H = (narrow ? 230 : 250) + (mt - 44);
  const tickStep = to - from > 20 ? (narrow ? 10 : 5) : 1;
  const ticks = [];
  for (let y = Math.ceil(from / tickStep) * tickStep; y <= to; y += tickStep) ticks.push(y);
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { domain: [1, maxPos], reverse: true },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: [1, 5, 10] }),
      ...eraMarks(eraL, [1, maxPos], eraBase).slice(0, -1),
      Plot.lineY(line, { x: "season", y: "y", stroke: C.s1, strokeWidth: 2, curve: "step" }),
      Plot.dot(data.filter((d) => d.pos), { x: "season", y: "pos", r: 3, fill: C.s1, stroke: C.paper, strokeWidth: 1.5 }),
      champRow ? Plot.text(champs, { x: (d) => (d.from + d.to) / 2, frameAnchor: "top", dy: -13, text: (d) => `${d.text} 우승`, fill: C.ink, fontWeight: 600 }) : null,
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: [1, 5, 10], label: null, tickFormat: (d) => `${d}위` }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks, tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = data.map((d) => ({
    px: xs.apply(d.season), py: d.pos ? ys.apply(d.pos) : H / 2, top: mt, bottom: H - mb,
    head: `${d.season} ${d.team}`,
    rows: [
      { value: d.pos ? `${d.pos}위` : "미부여", label: "최종 순위", key: { type: "line", color: C.s1 } },
      { value: `${int(d.pts)}점`, label: "점수" },
      { value: `${d.wins}승`, label: "우승" },
    ],
    note: d.pos ? null : "Jolpica 컨스트럭터 순위표에 순위가 없는 시즌이다.",
  }));
  const allTitles = data.filter((d) => d.pos === 1).map((d) => d.season);
  const w = frameOf(svg, champs.length && !champRow ? [el("p", "axis-note", `컨스트럭터 챔피언 시즌: ${allTitles.join(", ")}`)] : []);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 순위 추이 (누적 점수, 강조 최대 3) */

/**
 * series: [{id, label, team, pts: [라운드별 누적]}], highlight: id 배열(최대 3, 슬롯 1~3 순서).
 * 끝 라벨이 겹치면 위아래로 밀고 짧은 연결선을 단다.
 */
export function pointsRace(series, { width, rounds, highlight = [], unit = "점", label = "누적 점수 추이" }) {
  const narrow = width < 560;
  const n = series[0].pts.length;
  const H = narrow ? 280 : 340;
  const mt = 12;
  const mb = 30;
  const flat = [];
  for (const s of series) s.pts.forEach((p, i) => flat.push({ id: s.id, round: i + 1, p }));
  const hi = highlight.map((id, k) => ({ ...series.find((s) => s.id === id), color: SLOTS[k] })).filter((s) => s.id);
  const endText = (s) => (narrow ? `${s.short || s.label}` : `${s.label} ${int(s.pts[n - 1])}${unit}`);
  // 오른쪽 여백은 가장 긴 끝 라벨에 맞춘다(연결선 25px + 글자). 좁은 화면에서는 폭의 40%를 넘기지 않는다
  const need = Math.max(0, ...hi.map((s) => textWidth(endText(s), 12.5))) + 30;
  const mr = narrow ? Math.min(Math.max(64, need), Math.round(width * 0.4)) : Math.max(150, need);
  const max = Math.max(...flat.map((d) => d.p ?? 0));
  const yPx = (p) => mt + (1 - p / (max * 1.04)) * (H - mt - mb);
  const ends = hi.map((s) => ({ ...s, end: s.pts[n - 1], y: yPx(s.pts[n - 1]) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 16) ends[i].y = ends[i - 1].y + 16;
  const svg = plot({
    width, height: H, marginLeft: 44, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [1, n] },
    y: { domain: [0, max * 1.04] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 5 }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.lineY(flat.filter((d) => !highlight.includes(d.id)), { x: "round", y: "p", z: "id", stroke: C.ctx, strokeOpacity: 0.55, strokeWidth: 1 }),
      ...hi.map((s) => Plot.lineY(s.pts.map((p, i) => ({ round: i + 1, p })), { x: "round", y: "p", stroke: s.color, strokeWidth: 2 })),
      Plot.dot(hi, { x: () => n, y: (s) => s.pts[n - 1], r: 4, fill: (s) => s.color, stroke: C.paper, strokeWidth: 2 }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 5, label: null, tickFormat: (d, i, a) => (i === a.length - 1 ? `${d}${unit}` : d) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: Array.from({ length: n }, (_, i) => i + 1), tickFormat: (r) => (r % (narrow ? 4 : 2) === 1 || r === n ? r : "") }),
    ],
  });
  // 끝 라벨은 SVG 위에 직접 그린다 (밀어낸 위치와 연결선)
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const g = document.createElementNS(SVGNS, "g");
  for (const e of ends) {
    const x0 = xs.apply(n);
    const y0 = ys.apply(e.end);
    const ln = document.createElementNS(SVGNS, "path");
    ln.setAttribute("d", `M${x0 + 6},${y0}L${x0 + 16},${e.y}L${x0 + 22},${e.y}`);
    ln.setAttribute("fill", "none");
    ln.setAttribute("stroke", C.ink3);
    const t = document.createElementNS(SVGNS, "text");
    t.setAttribute("x", x0 + 25);
    t.setAttribute("y", e.y);
    t.setAttribute("dy", "0.32em");
    t.setAttribute("fill", C.ink);
    t.setAttribute("text-anchor", "start");
    t.setAttribute("font-weight", "650");
    t.textContent = endText(e);
    g.append(ln, t);
  }
  svg.append(g);
  const stops = Array.from({ length: n }, (_, i) => {
    const r = i + 1;
    const lead = series.reduce((a, b) => ((b.pts[i] ?? -1) > (a.pts[i] ?? -1) ? b : a));
    const rows = hi.map((s) => ({ value: `${int(s.pts[i])}${unit}`, label: s.label, key: { type: "line", color: s.color } }));
    if (!highlight.includes(lead.id)) rows.push({ value: `${int(lead.pts[i])}${unit}`, label: `${lead.label} (선두)` });
    return { px: xs.apply(r), py: ys.apply(hi[0] ? hi[0].pts[i] : lead.pts[i]), top: mt, bottom: H - mb, head: rounds ? `${r}라운드 ${rounds[i].short} 종료` : `${r}라운드 종료`, rows, note: "전체 값은 표에 있다." };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 작은 다중 차트 (팀 10개) */

/** kind "quali": rounds는 quali 표, kind "race": race 표. teams: [{cid, team}] */
export function paceMultiples(rounds, { width, teams, kind = "quali", label }) {
  const cols = width >= 900 ? 5 : width >= 520 ? 3 : 2;
  const gap = 16;
  const pw = Math.floor((width - gap * (cols - 1)) / cols);
  const n = Math.max(...rounds.map((d) => d.round));
  const wet = runs(rounds, (d) => (kind === "quali" ? d.wet === "wet" : d.wet));
  let lo = 0;
  let hi = 0;
  for (const d of rounds) for (const t of teams) {
    const x = d.teams[t.cid];
    if (x == null) continue;
    if (kind === "quali") { if (d.wet !== "wet") hi = Math.max(hi, x); }
    else if (!d.wet) { lo = Math.min(lo, x[1]); hi = Math.max(hi, x[2]); }
  }
  hi *= 1.06;
  lo *= 1.06;
  // 우천 띠 위 "우천" 글자: 글자끼리 겹칠 만큼 가까운 띠는 한 무리로 묶고 무리 가운데에 글자를 하나 둔다
  const H = 150;
  const mt = wet.length ? 20 : 8;
  const xPx = linX(0.5, n + 0.5, 34, pw - 6);
  const wetLab = [];
  for (const r of wet) {
    const g = wetLab[wetLab.length - 1];
    if (g && xPx((r.from + r.to) / 2) - xPx((g.from + g.lastTo) / 2) < textWidth("우천", 10) + 6) { g.to = r.to; g.lastTo = r.to; }
    else wetLab.push({ from: r.from, to: r.to, lastTo: r.to });
  }
  // 참고용 형식(2003-2005)은 선으로 잇지 않고 빈 고리만, 우천 판정이 없는 시즌(2022년 이전)은 평균에 모든 예선을 넣는다
  const refRound = (d) => kind === "quali" && d.ref;
  const grid = el("div", "multiples");
  grid.style.setProperty("--cols", cols);
  for (const t of teams) {
    const series = rounds.map((d) => ({ round: d.round, short: d.short, ref: refRound(d), unc: kind === "quali" && d.wet === "unclassified", wet: kind === "quali" ? d.wet === "wet" : d.wet, x: d.teams[t.cid], med: d.field ? d.field.med : null }));
    const dry = series.filter((d) => !d.wet && d.x != null);
    const mean = !dry.length ? null : kind === "quali" ? dry.reduce((a, d) => a + d.x, 0) / dry.length : dry.reduce((a, d) => a + d.x[0], 0) / dry.length;
    const marks = [
      Plot.rect(wet, { x1: (d) => d.from - 0.5, x2: (d) => d.to + 0.5, y1: kind === "quali" ? 0 : lo, y2: hi, fill: C.paper3 }),
      bandEdges(wet, { y1: kind === "quali" ? 0 : lo, y2: hi }),
      Plot.text(wetLab, { x: (d) => (d.from + d.to) / 2, frameAnchor: "top", dy: -10, text: () => "우천", fill: C.ink2, fontSize: 10, fontWeight: 600 }),
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 3 }),
    ];
    if (kind === "quali") {
      marks.push(
        Plot.lineY(series.map((d) => ({ round: d.round, y: d.wet ? NaN : d.med })), { x: "round", y: "y", stroke: C.ctx, strokeWidth: 1.2 }),
        Plot.ruleY([0], { stroke: C.axis }),
        Plot.lineY(series.map((d) => ({ round: d.round, y: d.wet || d.ref || d.x == null ? NaN : d.x })), { x: "round", y: "y", stroke: C.s1, strokeWidth: 2 }),
        Plot.dot(series.filter((d) => (d.wet || d.ref) && d.x != null && d.x <= hi), { x: "round", y: "x", r: 2.6, fill: C.paper, stroke: C.s1, strokeWidth: 1.3 }),
      );
    } else {
      marks.push(
        Plot.ruleY([0], { stroke: C.ink3 }),
        Plot.ruleX(series.filter((d) => !d.wet && d.x), { x: "round", y1: (d) => d.x[1], y2: (d) => d.x[2], stroke: C.s1, strokeWidth: 1.5 }),
        Plot.dot(series.filter((d) => !d.wet && d.x), { x: "round", y: (d) => d.x[0], r: 2.4, fill: C.s1 }),
        Plot.dot(series.filter((d) => d.wet && d.x && d.x[0] >= lo && d.x[0] <= hi), { x: "round", y: (d) => d.x[0], r: 2.4, fill: C.paper, stroke: C.s1, strokeWidth: 1.2 }),
      );
    }
    marks.push(
      Plot.axisY({ tickSize: 0, tickPadding: 4, ticks: 3, label: null, fontSize: 11, tickFormat: (d) => (d === 0 ? "0" : num(d, 1, { sign: kind === "race" })) }),
      Plot.axisX({ tickSize: 0, tickPadding: 4, label: null, fontSize: 11, ticks: [1, Math.round(n / 2), n] }),
    );
    const svg = plot({
      width: pw, height: H + mt - 8, marginLeft: 34, marginRight: 6, marginTop: mt, marginBottom: 22,
      x: { domain: [0.5, n + 0.5] },
      y: { domain: kind === "quali" ? [0, hi] : [lo, hi], reverse: true },
      marks,
    });
    const xs = svg.scale("x");
    const stops = series.map((d) => {
      const rows = [];
      if (kind === "quali") {
        rows.push({ value: d.x == null ? "결측" : `${num(d.x, 3)}%`, label: t.team, key: { type: d.ref ? "ring" : "line", color: C.s1 } });
        if (d.med != null) rows.push({ value: `${num(d.med, 3)}%`, label: "필드 중앙값", key: { type: "line", color: C.ctx } });
      } else if (d.x) {
        rows.push({ value: `${num(d.x[0], 2, { sign: true })}%`, label: t.team, key: { type: "dot", color: C.s1 } });
        rows.push({ value: `${num(d.x[1], 2, { sign: true })} ~ ${num(d.x[2], 2, { sign: true })}`, label: "95% 구간" });
      } else rows.push({ value: "결측", label: t.team });
      const note = d.wet ? (kind === "quali" ? "우천 예선, 평균에서 뺐다." : "우천 결승, 기본 분석에서 뺐다.")
        : [d.ref ? "참고용 예선 형식이라 선에 잇지 않는다." : null, d.unc ? "우천 여부 미분류 예선이다." : null].filter(Boolean).join(" ") || null;
      return { px: xs.apply(d.round), py: 20, top: mt, bottom: H + mt - 8 - 22, head: `${d.round}라운드 ${d.short}`, rows, note };
    });
    const cell = el("div", "mini");
    const h = el("p", "mini-head");
    const meanText = mean == null ? "평균 결측" : kind === "quali" ? `평균 ${num(mean, 3)}%` : `평균 ${num(mean, 2, { sign: true })}%`;
    h.append(el("b", null, t.team), el("span", null, meanText));
    const w = frameOf(svg);
    readout(w, svg, stops, { axis: "x", label: `${t.team} ${label || ""}` });
    cell.append(h, w);
    grid.append(cell);
  }
  let off = 0;
  for (const d of rounds) for (const t of teams) {
    const x = d.teams[t.cid];
    if (x == null) continue;
    if (kind === "quali" && d.wet === "wet" && x > hi) off++;
    if (kind === "race" && d.wet && (x[0] < lo || x[0] > hi)) off++;
  }
  if (!off) return grid;
  const outer = el("div");
  outer.append(grid, el("p", "axis-note", `우천 ${kind === "quali" ? "예선" : "결승"} 값 ${off}개는 공통 세로축 범위를 넘어 그리지 않았다. 표에 있다.`));
  return outer;
}

/* ------------------------------------------------------------------ 변경 사유 비율 (얇은 나눔 막대 + 목록) */

/** counts: {performance, circuit_specific, reliability, other}. 숫자는 옆 목록이 맡는다. */
export function reasonShare(counts, { label = "변경 사유 비율" } = {}) {
  const total = CAT_ORDER.reduce((a, c) => a + (counts[c] || 0), 0);
  const box = el("div", "share");
  const bar = el("div", "seg-bar");
  bar.setAttribute("role", "img");
  bar.setAttribute("aria-label", `${label}: ` + CAT_ORDER.filter((c) => counts[c]).map((c) => `${CATS[c].label} ${counts[c]}건`).join(", "));
  for (const c of CAT_ORDER) {
    if (!counts[c]) continue;
    const s = el("span", "seg-part");
    s.dataset.cat = c;
    s.style.flexGrow = counts[c];
    bar.append(s);
  }
  const list = el("ul", "share-list");
  for (const c of CAT_ORDER) {
    const li = el("li");
    const share = total ? (counts[c] || 0) / total * 100 : 0;
    li.append(catGlyph(c), el("span", "share-name", CATS[c].label), el("b", "share-n", `${(counts[c] || 0).toLocaleString("ko-KR")}건`), el("span", "share-p", total ? (share < 1 && share > 0 ? "1% 미만" : `${Math.round(share)}%`) : ""));
    list.append(li);
  }
  box.append(bar, list);
  return box;
}

/* ------------------------------------------------------------------ 묶음별 항목 수 (쌓은 막대) */

/**
 * groups: [{key, label, cats:{...}, total, sub}]
 * orient "h": 많은 순 가로 막대(팀, 부품 영역). "v": 시간 순 세로 막대(대회).
 */
export function groupedReasons(groups, { width, orient = "h", label = "묶음별 항목 수", onSelect }) {
  if (!groups.length) return el("p", "fig-fallback", "조건에 맞는 항목이 0건이라 그릴 막대가 없다.");
  const narrow = width < 560;
  const flat = [];
  for (const g of groups) {
    let acc = 0;
    for (const c of CAT_ORDER) {
      const n = g.cats[c] || 0;
      if (n) flat.push({ key: g.key, label: g.label, cat: c, x1: acc, x2: acc + n, n });
      acc += n;
    }
  }
  const max = Math.max(1, ...groups.map((g) => g.total));
  const fill = (d) => CATS[d.cat].color;
  // 기타는 면을 칠하지 않는다: 종이색 채움 + 1.5px 맥락 회색 테두리. 맥락 회색 면이 신뢰성 청록 바로 옆에 붙으면
  // 정상 시각에서도 두 조각이 구별되지 않아서다(palette-validation.txt의 4색 기록). 범주 기호 ×와 같은 "빈 모양"이다.
  const solid = flat.filter((d) => d.cat !== "other");
  const hollow = flat.filter((d) => d.cat === "other");
  let svg;
  if (orient === "h") {
    const rowH = 26;
    const ml = Math.min(narrow ? 120 : 170, Math.max(...groups.map((g) => textWidth(g.label, 13))) + 14);
    svg = plot({
      width, height: groups.length * rowH + 40, marginLeft: ml, marginRight: 44, marginTop: 4, marginBottom: 32,
      x: { domain: [0, max * 1.02] },
      y: { type: "band", domain: groups.map((g) => g.label), padding: 0 },
      marks: [
        Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: narrow ? 3 : 5 }),
        Plot.rectX(solid, { x1: "x1", x2: "x2", y: "label", fill, insetTop: (rowH - 14) / 2, insetBottom: (rowH - 14) / 2, insetRight: 1, insetLeft: 1 }),
        Plot.rectX(hollow, { x1: "x1", x2: "x2", y: "label", fill: C.paper, stroke: C.ctx, strokeWidth: 1.5, insetTop: (rowH - 14) / 2 + 0.75, insetBottom: (rowH - 14) / 2 + 0.75, insetRight: 1.75, insetLeft: 1.75 }),
        Plot.ruleX([0], { stroke: C.axis }),
        Plot.text(groups, { x: "total", y: "label", dx: 6, textAnchor: "start", text: (g) => g.total.toLocaleString("ko-KR"), fill: C.ink2, fontVariant: "tabular-nums" }),
        Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 13, label: null }),
        Plot.axisX({ tickSize: 0, tickPadding: 6, ticks: narrow ? 3 : 5, label: null, tickFormat: (d, i, a) => (i === a.length - 1 ? `${d}건` : d) }),
      ],
    });
    const ys = svg.scale("y");
    const xs = svg.scale("x");
    const stops = groups.map((g) => ({
      py: ys.apply(g.label) + rowH / 2, px: xs.apply(g.total),
      head: g.label, rows: [{ value: `${g.total}건`, label: "합계" }, ...CAT_ORDER.filter((c) => g.cats[c]).map((c) => ({ value: `${g.cats[c]}건`, label: CATS[c].label, key: { type: "glyph", cat: c } }))],
      note: g.sub || null, group: g,
    }));
    const w = frameOf(svg);
    readout(w, svg, stops, { axis: "y", label, rowH, onSelect: onSelect ? (s) => onSelect(s.group) : null });
    return w;
  }
  // 세로: 대회 순서, 시즌 경계 라벨
  const keys = groups.map((g) => g.key);
  const step = (width - 52) / keys.length;
  const inset = Math.max(0.5, (step - Math.min(14, step * 0.7)) / 2);
  const seasonsStart = groups.filter((g, i) => i === 0 || g.season !== groups[i - 1].season);
  svg = plot({
    width, height: narrow ? 200 : 230, marginLeft: 40, marginRight: 8, marginTop: 10, marginBottom: 34,
    x: { type: "band", domain: keys, padding: 0, axis: null },
    y: { domain: [0, max * 1.06] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 4 }),
      Plot.rectY(solid, { x: "key", y1: "x1", y2: "x2", fill, insetLeft: inset, insetRight: inset, insetTop: 0.5, insetBottom: 0.5 }),
      Plot.rectY(hollow, { x: "key", y1: "x1", y2: "x2", fill: C.paper, stroke: C.ctx, strokeWidth: 1.5, insetLeft: inset + 0.75, insetRight: inset + 0.75, insetTop: 1.25, insetBottom: 1.25 }),
      Plot.dot(groups.filter((g) => g.total === 0), { x: "key", y: 0, r: 2.5, fill: C.paper, stroke: C.ink3 }),
      Plot.dot(groups.filter((g) => g.review), { x: "key", y: (g) => g.total, dy: -9, symbol: "triangle", r: 5.5, fill: C.warn, stroke: C.warnInk, strokeWidth: 1 }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.ruleX(seasonsStart.slice(1), { x: "key", stroke: C.axis, dx: -step / 2 }),
      Plot.text(seasonsStart, { x: "key", frameAnchor: "bottom", dy: 20, textAnchor: "start", dx: -step / 2 + 2, text: (g) => String(g.season), fill: C.ink2, fontWeight: 600 }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 4, label: null, tickFormat: (d, i, a) => (i === a.length - 1 ? `${d}건` : d) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = groups.map((g) => ({
    px: xs.apply(g.key) + xs.bandwidth / 2, py: ys.apply(g.total) - 8, top: 10, bottom: (narrow ? 200 : 230) - 34,
    head: g.label, rows: [{ value: `${g.total}건`, label: "합계" }, ...CAT_ORDER.filter((c) => g.cats[c]).map((c) => ({ value: `${g.cats[c]}건`, label: CATS[c].label, key: { type: "glyph", cat: c } }))],
    note: g.review ? "검수 대기 문서다." : g.total === 0 ? "조건에 맞는 항목이 0건이다." : null, group: g,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label, onSelect: onSelect ? (s) => onSelect(s.group) : null });
  return w;
}

/* ------------------------------------------------------------------ PU 구성요소 누적 (표본 값 전용) */

export const PU_ELEMENTS = ["ICE", "TC", "MGU-H", "MGU-K", "ES", "CE", "EX"];
const puSeries = (d, element) => (d.by ? d.by[element] : d[element.toLowerCase().replace("-", "")]) || [];

/**
 * PU 구성요소 누적 사용 개수 (계단선).
 * rows: [{label, by: {ICE: [라운드별 누적 | null], TC: [...], ...}}] (이전 형식 {label, ice: [...]}도 받는다)
 * opts.rounds: 그 시즌 라운드 수(데이터에서 받는다. 2020년 17, 2021-2023년 22, 2024-2025년 24). 없으면 가장 긴 줄의 길이.
 * opts.element: PU_ELEMENTS 가운데 하나. 값이 모두 null인 드라이버(한 번도 출전하지 않은 사람)는 그리지 않고 툴팁에만 "미출전"으로 남긴다.
 * 색: 드라이버 셋까지 슬롯 1~3. 넷째부터는 맥락 회색 1.5px 선 + 직접 라벨(엔진 페이지의 팀 칸은 드라이버가 셋을 넘는 일이 드물다).
 */
export function puSteps(rows, { width, rounds, element = "ICE", sample = false, label } = {}) {
  const narrow = width < 560;
  const lines = rows.map((d) => ({ label: d.label, s: puSeries(d, element) }));
  const n = rounds || Math.max(1, ...lines.map((d) => d.s.length));
  const drawn = lines.filter((d) => d.s.some((c) => c != null));
  const colorOf = (k) => SLOTS[k] || C.ctx;
  const flat = drawn.flatMap((d, k) => d.s.slice(0, n).map((c, i) => ({ id: d.label, k, round: i + 1, c })).filter((p) => p.c != null));
  const max = Math.max(1, ...flat.map((d) => d.c));
  const H = 200;
  const ttl = label || `${element} 누적 사용 개수${sample ? " (표본 값)" : ""}`;
  const ticks = [1, ...[6, 12, 18, 24].filter((t) => t < n - 2), n];
  const svg = plot({
    width, height: H, marginLeft: 34, marginRight: narrow ? 70 : 110, marginTop: 10, marginBottom: 28,
    x: { domain: [0.5, n + 0.5] },
    y: { domain: [0, max + 0.5] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: max }),
      Plot.ruleY([0], { stroke: C.axis }),
      ...drawn.map((d, k) => Plot.lineY(flat.filter((p) => p.k === k), { x: "round", y: "c", stroke: colorOf(k), strokeWidth: k < 3 ? 2 : 1.5, curve: "step-after" })),
      ...drawn.map((d, k) => {
        const pts = flat.filter((p) => p.k === k);
        const inside = pts.at(-1).round < n;
        const at = inside ? pts[0] : pts.at(-1);
        return Plot.text([at], { x: "round", y: "c", dx: inside ? 0 : 8, dy: inside ? -11 : 0, textAnchor: "start", text: () => d.label, fill: C.ink, fontWeight: 600, stroke: C.paper, strokeWidth: 3 });
      }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: max, label: null, tickFormat: (d, i, a) => (i === a.length - 1 ? `${d}개` : d) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = Array.from({ length: n }, (_, i) => ({
    px: xs.apply(i + 1), py: ys.apply(max / 2), top: 10, bottom: H - 28,
    head: `${i + 1}라운드 종료${sample ? " (표본 값)" : ""}`,
    rows: lines.map((d) => {
      const k = drawn.indexOf(d);
      return { value: d.s[i] == null ? "미출전" : `${d.s[i]}개`, label: d.label, key: k >= 0 ? { type: "line", color: colorOf(k) } : null };
    }),
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label: ttl });
  return w;
}

/**
 * 새 ICE 투입 점 행렬 (엔진 페이지). 행은 드라이버, 열은 라운드. 누적 개수가 앞 라운드보다 늘어난 라운드에 채운 점,
 * 출전하지 않은 라운드는 비워 두고 출전한 라운드는 기준선 색 작은 점. 오른쪽 끝에 시즌 누적 개수를 숫자로 적는다.
 * 키보드: ←/→ 라운드, ↑/↓ 드라이버, Home/End 그 드라이버의 처음과 끝 라운드. 표 보기는 드라이버 × 라운드.
 * rows: [{label, team, ice: [라운드별 누적 | null]}], opts.rounds: 그 시즌 라운드 수
 */
export function newIce(rows, { width, rounds, sample = false, label } = {}) {
  const narrow = width < 560;
  const n = rounds || Math.max(1, ...rows.map((d) => d.ice.length));
  const rowH = 24;
  const ml = Math.min(narrow ? 92 : 150, Math.max(...rows.map((d) => textWidth(d.label))) + 14);
  const mr = 44;
  const cells = [];
  rows.forEach((d, ri) => {
    for (let i = 0; i < n; i++) {
      const c = d.ice[i];
      const prev = i === 0 ? 0 : d.ice.slice(0, i).reduce((a, x) => (x == null ? a : x), 0);
      cells.push({ row: ri, label: d.label, team: d.team, round: i + 1, c, raced: c != null, fresh: c != null && c > prev });
    }
  });
  const svg = plot({
    width, height: rows.length * rowH + 40, marginLeft: ml, marginRight: mr, marginTop: 4, marginBottom: 30,
    x: { domain: [0.5, n + 0.5] },
    y: { type: "band", domain: rows.map((d) => d.label), padding: 0 },
    marks: [
      Plot.gridY(rows.map((d) => d.label), { stroke: C.grid, strokeOpacity: 1 }),
      Plot.dot(cells.filter((c) => c.raced && !c.fresh), { x: "round", y: "label", r: 1.6, fill: C.axis }),
      Plot.dot(cells.filter((c) => c.fresh), { x: "round", y: "label", r: 4.5, fill: C.s1, stroke: C.paper, strokeWidth: 2 }),
      Plot.text(rows, { y: "label", frameAnchor: "right", dx: mr - 4, textAnchor: "end", fill: C.ink2, fontVariant: "tabular-nums", text: (d) => { const last = d.ice.filter((x) => x != null).at(-1); return last == null ? "결측" : `${last}개`; } }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 13, label: null }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: Array.from({ length: n }, (_, i) => i + 1), tickFormat: roundTick(narrow, n) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = cells.map((c) => ({
    px: xs.apply(c.round), py: ys.apply(c.label) + rowH / 2,
    head: `${c.label}${c.team ? ` (${c.team})` : ""} · ${c.round}라운드${sample ? " (표본 값)" : ""}`,
    rows: [{ value: c.c == null ? "미출전" : `${c.c}개`, label: "ICE 누적", key: c.fresh ? { type: "dot", color: C.s1 } : null }],
    note: c.fresh ? "이 라운드에 새 ICE를 투입했다." : null,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "grid", cols: n, rowH, label: label || `새 ICE 투입${sample ? " (표본 값)" : ""}` });
  return w;
}
