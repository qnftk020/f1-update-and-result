// 시즌 상세와 결과 분포 차트: 드라이버 쪽 "시즌 상세"(/drivers/<id>/), 컨스트럭터 쪽(/constructors/<id>/,
// /constructors/<id>/<시즌>/). charts.js와 같은 약속을 따른다: (data, {width, ...})를 받아 요소를 돌려주고,
// width < 560이면 좁은 모양으로 그린다. 색은 CSS 변수이고 범주 색은 s1, s2, s3 순서로만 쓴다.
// 출발은 블루 빈 원, 결과는 핑크 채운 원이다(홈의 출발 순위와 결승 순위 덤벨과 같다). 완주로 분류되지
// 않은 결과는 맨 아래 "완주 못 함" 줄에 ×(리타이어, 출발 안 함)나 빈 네모(실격)로 찍는다.
// 자료 모양은 각 함수 위 주석에 있고, 페이지가 빌드 때 만든다.
import * as Plot from "@observablehq/plot";
import { C, MINUS, el, frameOf, int, plot, readout, roundTick, textWidth } from "./core.js";
import { formatPoints } from "../format.ts";

const pt = (v) => formatPoints(v);

/** 리타이어 원인 분류(pipeline/site_drivers.retire_cause) */
export const CAUSE = {
  acc: "사고·충돌",
  mech: "차량 문제",
  unk: "원인 미기재",
  nc: "완주 미분류",
  oth: "그 밖",
};

/** 결과 글: 완주 분류는 순위, 그 밖은 분류 이름 */
export function outcomeText(d) {
  if (d.o === "F") return `${d.p}위`;
  if (d.o === "D") return "실격";
  if (d.o === "N") return "출발 안 함";
  return d.rc ? `리타이어 (${CAUSE[d.rc]})` : "리타이어";
}

/** 순위 축의 위쪽 끝과 눈금. 아래에 "완주 못 함" 줄(U)을 둔다. */
function posScale(maxPos) {
  const top = maxPos <= 10 ? 10 : maxPos <= 20 ? 20 : Math.ceil(maxPos / 5) * 5;
  const ticks = top <= 10 ? [1, 5, 10] : top <= 20 ? [1, 5, 10, 15, 20] : top <= 30 ? [1, 10, 20, 30] : [1, 10, 20, 30, 40];
  const U = top + Math.max(2.5, Math.round(top * 0.14));
  return { top, ticks: ticks.filter((t) => t <= top), U };
}

/** 같은 라운드의 여러 표식을 옆으로 벌리는 px 간격. 한 라운드 폭의 30%를 넘지 않는다. */
const spread = (width, ml, mr, n, want) => Math.min(want, ((width - ml - mr) / Math.max(n, 1)) * 0.3);

/* ------------------------------------------------------------------ 드라이버 한 시즌: 대회별 출발과 결과 */

/**
 * rows: [{r, n, g, q, p, o, st, pts, rc, mates: [{name, o, p, rc}]}] 한 드라이버의 한 시즌 결승 행(라운드 순).
 * 한 라운드에 행이 여럿(차량 공유)이면 모두 찍는다. rounds: 그 시즌 대회 수.
 * 출발은 블루 빈 원, 결과는 핑크 채운 원이고 둘을 회색 선으로 잇는다. 동료의 결과는 오른쪽에 작은 회색 점이다.
 */
export function raceStrip(rows, { width, rounds, label = "대회별 출발과 결과" }) {
  const narrow = width < 560;
  const n = rounds;
  const fin = rows.filter((d) => d.o === "F");
  const out = rows.filter((d) => d.o !== "F");
  const mates = rows.flatMap((d) => (d.mates || []).map((m) => ({ ...m, r: d.r })));
  const maxPos = Math.max(10, ...rows.map((d) => d.g || 0), ...fin.map((d) => d.p), ...mates.filter((m) => m.o === "F").map((m) => m.p));
  const { ticks, U } = posScale(maxPos);
  const ml = narrow ? 64 : 74;
  const mr = narrow ? 8 : 16;
  const mt = 10;
  const mb = 30;
  const H = narrow ? 300 : 340;
  const r0 = narrow ? 3.6 : 4.6;
  const off = spread(width, ml, mr, n, 7);
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [0.5, n + 0.5] },
    y: { domain: [0.5, U + 0.8], reverse: true },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks }),
      Plot.ruleY([(U + ticks[ticks.length - 1]) / 2 + 0.6], { stroke: C.axis, strokeDasharray: "3,3" }),
      // 동료: 결과(작은 회색 점)와 완주 못 함(작은 회색 ×), 오른쪽으로 비켜 찍는다
      Plot.dot(mates.filter((m) => m.o === "F"), { x: "r", y: "p", dx: off, r: narrow ? 2.4 : 3, fill: C.ctx }),
      Plot.dot(mates.filter((m) => m.o !== "F"), { x: "r", y: U, dx: off, r: narrow ? 2.6 : 3.2, symbol: "times", stroke: C.ctx, strokeWidth: 1.5 }),
      // 출발에서 결과까지
      Plot.link(fin.filter((d) => d.g > 0 && d.g !== d.p), { x1: "r", x2: "r", y1: "g", y2: "p", stroke: C.ctx, strokeWidth: 2 }),
      Plot.dot(rows.filter((d) => d.g > 0), { x: "r", y: "g", r: r0, fill: C.paper, stroke: C.s1, strokeWidth: 2 }),
      Plot.dot(fin, { x: "r", y: "p", r: r0, fill: C.s2, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.dot(out.filter((d) => d.o !== "D"), { x: "r", y: U, r: r0 + 0.6, symbol: "times", stroke: C.s2, strokeWidth: 2.2 }),
      Plot.dot(out.filter((d) => d.o === "D"), { x: "r", y: U, r: r0 + 0.4, symbol: "square", fill: C.paper, stroke: C.s2, strokeWidth: 2 }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: [...ticks, U], label: null, tickFormat: (d) => (d === U ? "완주 못 함" : `${d}위`) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: Array.from({ length: n }, (_, i) => i + 1), tickFormat: roundTick(narrow, n) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const byRound = new Map();
  for (const d of rows) {
    if (!byRound.has(d.r)) byRound.set(d.r, []);
    byRound.get(d.r).push(d);
  }
  const stops = [...byRound.entries()].map(([r, list]) => {
    const d = list[0];
    const rowsOut = [];
    for (const x of list) {
      if (x.q != null) rowsOut.push({ value: `${x.q}위`, label: "예선" });
      rowsOut.push({ value: x.g > 0 ? `${x.g}위` : "0 (피트 레인 또는 기록 없음)", label: "출발", key: { type: "ring", color: C.s1 } });
      rowsOut.push({ value: outcomeText(x), label: "결과", key: x.o === "F" ? { type: "dot", color: C.s2 } : { type: x.o === "D" ? "hollow" : "times", color: C.s2 } });
      rowsOut.push({ value: `${pt(x.pts)}점`, label: "득점" });
    }
    for (const m of d.mates || []) rowsOut.push({ value: outcomeText(m), label: `동료 ${m.name}`, key: { type: m.o === "F" ? "dot" : "times", color: C.ctx } });
    return {
      px: xs.apply(r), py: ys.apply(d.o === "F" ? d.p : U), top: mt, bottom: H - mb,
      head: `${r}라운드 ${d.n}`,
      rows: rowsOut,
      note: list.length > 1 ? "한 대회에 결과 행이 여럿이다(차량 공유 또는 교대)." : d.o !== "F" && d.st ? `Jolpica 상태: ${d.st}` : null,
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 라운드 뒤 순위 (드라이버, 컨스트럭터) */

/**
 * rows: [{r, n, pos, pts, lp}] 그 시즌 모든 라운드. pos와 pts는 그 라운드 뒤 순위와 누적 점수(없으면 null),
 * lp는 그 라운드 뒤 1위의 누적 점수다. 1위였던 라운드는 핑크 점이다.
 */
export function roundSteps(rows, { width, label = "라운드 뒤 순위" }) {
  const narrow = width < 560;
  const n = rows.length;
  const have = rows.filter((d) => d.pos != null);
  if (!have.length) return el("p", "fig-fallback", "이 시즌은 라운드별 순위가 없다.");
  const maxPos = Math.max(5, ...have.map((d) => d.pos));
  const top = maxPos <= 5 ? 5 : maxPos <= 10 ? 10 : maxPos <= 20 ? 20 : Math.ceil(maxPos / 10) * 10;
  const ticks = (top <= 5 ? [1, 3, 5] : top <= 10 ? [1, 5, 10] : top <= 20 ? [1, 5, 10, 15, 20] : [1, 10, 20, 30, 40]).filter((t) => t <= top);
  const ml = narrow ? 64 : 74;
  const mr = narrow ? 8 : 16;
  const mt = 10;
  const mb = 30;
  const H = narrow ? 190 : 210;
  const line = rows.map((d) => ({ r: d.r, y: d.pos ?? NaN }));
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [0.5, n + 0.5] },
    y: { domain: [0.5, top + 0.5], reverse: true },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks }),
      Plot.lineY(line, { x: "r", y: "y", stroke: C.s1, strokeWidth: 2, curve: "step" }),
      Plot.dot(have.filter((d) => d.pos !== 1), { x: "r", y: "pos", r: 3, fill: C.s1, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.dot(have.filter((d) => d.pos === 1), { x: "r", y: "pos", r: 4.5, fill: C.s2, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks, label: null, tickFormat: (d) => `${d}위` }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: Array.from({ length: n }, (_, i) => i + 1), tickFormat: roundTick(narrow, n) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = have.map((d) => {
    const gap = d.lp != null && d.pts != null ? Math.round((d.lp - d.pts) * 100) / 100 : null;
    return {
      px: xs.apply(d.r), py: ys.apply(d.pos), top: mt, bottom: H - mb,
      head: `${d.r}라운드 ${d.n} 뒤`,
      rows: [
        { value: `${d.pos}위`, label: "순위", key: { type: "dot", color: d.pos === 1 ? C.s2 : C.s1 } },
        ...(d.pts != null ? [{ value: `${pt(d.pts)}점`, label: "누적 점수" }] : []),
        ...(gap != null ? [{ value: gap > 0 ? `${MINUS}${pt(gap)}점` : "선두", label: "1위와 차이" }] : []),
      ],
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 완주 순위 분포 */

/** rows: [{k, n}] k는 1부터의 순위(정수)이고 마지막 칸은 "21+" 같은 묶음일 수 있다. 1위는 핑크다. */
export function posBars(rows, { width, unit = "번", what = "완주 결과", label = "완주 순위 분포" }) {
  const narrow = width < 560;
  const keys = rows.map((d) => String(d.k));
  const total = rows.reduce((a, d) => a + d.n, 0);
  const max = Math.max(1, ...rows.map((d) => d.n));
  const ml = 40;
  const mr = narrow ? 6 : 12;
  const mt = 16;
  const mb = 30;
  const H = narrow ? 200 : 230;
  const every = narrow ? 5 : keys.length > 22 ? 2 : 1;
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { type: "band", domain: keys, paddingInner: 0.18, paddingOuter: 0.1 },
    y: { domain: [0, max * 1.08] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 4 }),
      Plot.barY(rows, { x: (d) => String(d.k), y: "n", fill: (d) => (d.k === 1 ? C.s2 : C.s1), rx1: 2 }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 4, label: null, tickFormat: (d, i, a) => (Number.isInteger(d) ? (i === a.length - 1 ? `${d}${unit}` : d) : "") }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, tickFormat: (k, i) => (k === "1" || (i + 1) % every === 0 || i === keys.length - 1 ? (/^\d+$/.test(k) ? `${k}위` : k) : "") }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((d) => ({
    px: xs.apply(String(d.k)) + xs.bandwidth / 2, py: ys.apply(d.n), top: mt, bottom: H - mb,
    head: /^\d+$/.test(String(d.k)) ? `${d.k}위` : `${d.k}`,
    rows: [
      { value: `${int(d.n)}${unit}`, label: what, key: { type: "rect", color: d.k === 1 ? C.s2 : C.s1 } },
      { value: total ? `${((d.n / total) * 100).toFixed(1)}%` : "", label: `${what} 가운데` },
    ],
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 컨스트럭터 한 시즌: 차마다 대회별 결과 */

const SLOT = [C.s1, C.s2, C.s3];
const SYMBOL = ["circle", "square", "triangle", "diamond"];
const KEY = ["dot", "sq", "tri-c", "diamond"];
/** 드라이버 순번(그 시즌 출전이 많은 순)의 색과 모양. 넷째부터는 맥락 회색 마름모다. */
export const driverStyle = (i) => ({ color: SLOT[i] ?? C.ctx, symbol: SYMBOL[Math.min(i, 3)], key: KEY[Math.min(i, 3)] });

/**
 * rows: [{r, n, d, g, q, p, o, st, pts, rc}] 한 컨스트럭터의 한 시즌 결승 행(차마다 한 줄).
 * drivers: [{id, name}] 그 시즌 출전이 많은 순. rounds: 그 시즌 대회 수.
 * 드라이버마다 색과 모양이 다른 점으로 결과를 찍고 옅은 선으로 잇는다. 완주 못 한 결과는 맨 아래 줄이다.
 */
export function teamStrip(rows, { width, rounds, drivers, label = "대회별 결과" }) {
  const narrow = width < 560;
  const n = rounds;
  const idx = new Map(drivers.map((d, i) => [d.id, i]));
  const name = new Map(drivers.map((d) => [d.id, d.name]));
  const data = rows.map((d) => ({ ...d, i: idx.get(d.d) ?? 3 }));
  const fin = data.filter((d) => d.o === "F");
  const out = data.filter((d) => d.o !== "F");
  const maxPos = Math.max(10, ...fin.map((d) => d.p));
  const { ticks, U } = posScale(maxPos);
  const ml = narrow ? 64 : 74;
  const mr = narrow ? 8 : 16;
  const mt = 10;
  const mb = 30;
  const H = narrow ? 300 : 340;
  const r0 = narrow ? 3.8 : 4.8;
  const off = spread(width, ml, mr, n, 6);
  // 한 라운드에 완주 못 한 차가 여럿이면 맨 아래 줄에서 옆으로 벌린다(px 간격을 라운드 단위로 바꿔 x에 더한다)
  const perRound = (width - ml - mr) / Math.max(n, 1);
  const seen = new Map();
  for (const d of out) {
    const k = seen.get(d.r) ?? 0;
    const many = out.filter((x) => x.r === d.r).length;
    d.xr = d.r + ((k - (many - 1) / 2) * off * 1.6) / perRound;
    seen.set(d.r, k + 1);
  }
  const lines = drivers.slice(0, 3).map((dr, i) => {
    const by = new Map(fin.filter((d) => d.d === dr.id).map((d) => [d.r, d.p]));
    return Array.from({ length: n }, (_, k) => ({ r: k + 1, y: by.get(k + 1) ?? NaN, i }));
  });
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [0.5, n + 0.5] },
    y: { domain: [0.5, U + 0.8], reverse: true },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks }),
      Plot.ruleY([(U + ticks[ticks.length - 1]) / 2 + 0.6], { stroke: C.axis, strokeDasharray: "3,3" }),
      ...lines.map((l, i) => Plot.lineY(l, { x: "r", y: "y", stroke: SLOT[i], strokeWidth: 1.5, strokeOpacity: 0.45 })),
      Plot.dot(fin, { x: "r", y: "p", r: r0, symbol: (d) => SYMBOL[Math.min(d.i, 3)], fill: (d) => SLOT[d.i] ?? C.ctx, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.dot(out.filter((d) => d.o !== "D"), { x: "xr", y: U, r: r0 + 0.4, symbol: "times", stroke: (d) => SLOT[d.i] ?? C.ctx, strokeWidth: 2.2 }),
      Plot.dot(out.filter((d) => d.o === "D"), { x: "xr", y: U, r: r0 + 0.2, symbol: "square", fill: C.paper, stroke: (d) => SLOT[d.i] ?? C.ctx, strokeWidth: 2 }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: [...ticks, U], label: null, tickFormat: (d) => (d === U ? "완주 못 함" : `${d}위`) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: Array.from({ length: n }, (_, i) => i + 1), tickFormat: roundTick(narrow, n) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const byRound = new Map();
  for (const d of data) {
    if (!byRound.has(d.r)) byRound.set(d.r, []);
    byRound.get(d.r).push(d);
  }
  const stops = [...byRound.entries()].map(([r, list]) => {
    const best = list.filter((d) => d.o === "F").sort((a, b) => a.p - b.p)[0];
    const sum = list.reduce((a, d) => a + d.pts, 0);
    return {
      px: xs.apply(r), py: ys.apply(best ? best.p : U), top: mt, bottom: H - mb,
      head: `${r}라운드 ${list[0].n}`,
      rows: [
        ...list.map((d) => ({
          value: `${outcomeText(d)}${d.g > 0 ? `, 출발 ${d.g}위` : ""}`,
          label: name.get(d.d) ?? d.d,
          key: { type: d.o === "F" ? KEY[Math.min(d.i, 3)] : d.o === "D" ? "hollow" : "times", color: SLOT[d.i] ?? C.ctx },
        })),
        { value: `${pt(Math.round(sum * 100) / 100)}점`, label: "팀 득점(결승)" },
      ],
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 시즌별 결과 구성 (100% 쌓은 막대) */

const PARTS = [
  { k: "F", label: "완주 분류", color: C.s1 },
  { k: "mech", label: "차량 문제", color: C.s3 },
  { k: "acc", label: "사고·충돌", color: C.s2 },
  { k: "other", label: "그 밖 (원인 미기재, 완주 미분류, 실격, 출발 안 함 등)", short: "그 밖", color: C.ctx },
];

/** rows: [{s, n, F, mech, acc, other}] n은 그 시즌 결과 행(차) 수. 막대는 비율이고 툴팁에 수가 있다. */
export function outcomeShare(rows, { width, from, to, label = "시즌별 결과 구성" }) {
  const narrow = width < 560;
  const f = from ?? rows[0].s;
  const t = to ?? rows[rows.length - 1].s;
  const ml = 44;
  const mr = narrow ? 8 : 16;
  const mt = 10;
  const mb = 30;
  const H = narrow ? 210 : 240;
  const per = (width - ml - mr) / (t - f + 1);
  const hb = Math.min(0.42, 14 / per);
  const stack = [];
  for (const d of rows) {
    let acc = 0;
    for (const p of PARTS) {
      const v = d.n ? (d[p.k] / d.n) * 100 : 0;
      if (v > 0) stack.push({ s: d.s, y1: acc, y2: acc + v, color: p.color });
      acc += v;
    }
  }
  const span = t - f;
  const step = span <= 14 ? (narrow ? 4 : 2) : span <= 30 ? (narrow ? 10 : 5) : narrow ? 20 : 10;
  const xt = [];
  for (let y = span <= 14 ? f : Math.ceil(f / step) * step; y <= t; y += step) xt.push(y);
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [f - 0.5, t + 0.5] },
    y: { domain: [0, 100] },
    marks: [
      Plot.rect(stack, { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y1: "y1", y2: "y2", fill: "color" }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: [0, 50, 100], label: null, tickFormat: (d) => `${d}%` }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: xt, tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((d) => ({
    px: xs.apply(d.s), py: ys.apply(d.n ? (d.F / d.n) * 100 : 0), top: mt, bottom: H - mb,
    head: `${d.s} · 결과 ${int(d.n)}개`,
    rows: PARTS.map((p) => ({ value: `${d[p.k]}개 (${d.n ? Math.round((d[p.k] / d.n) * 100) : 0}%)`, label: p.short ?? p.label, key: { type: "rect", color: p.color } })),
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/** 범례용 결과 구성 항목(페이지가 같은 이름을 쓰게 한다) */
export const OUTCOME_PARTS = PARTS.map(({ k, label }) => ({ k, label }));
export { textWidth };
