// 드라이버 쪽(/drivers/, /drivers/<id>/) 차트 함수. charts.js와 같은 약속을 따른다:
// (data, {width, ...})를 받아 요소를 돌려주고, width < 560이면 좁은 모양으로 그린다. 색은 CSS 변수다.
// 범주 색은 s1, s2, s3 순서로만 쓰고, 핑크(s2)는 눈여겨볼 표식(챔피언 시즌, 2025 그리드, 가장 작은 점수 차, 우승)이다.
// 세로축은 하나만 둔다. 자료 모양은 각 함수 위 주석에 있고, 페이지(pages/drivers/)가 빌드 때 만든다.
import * as Plot from "@observablehq/plot";
import { C, el, frameOf, int, num, plot, readout, textWidth } from "./core.js";
import { formatPoints } from "../format.ts";
import { initialSurname } from "../names.ts";

const pt = (v) => formatPoints(v);

/* ------------------------------------------------------------------ 공통 */

/** 연도 눈금: 기간이 길수록 성기게. 짧은 기간은 첫해부터 센다. */
function yearTicks(from, to, narrow) {
  const span = to - from;
  if (span <= 0) return [from];
  if (span <= 14) {
    const step = span <= 6 ? (narrow && span > 4 ? 2 : 1) : narrow ? 4 : 2;
    const t = [];
    for (let y = from; y <= to; y += step) t.push(y);
    if (t[t.length - 1] !== to && to - t[t.length - 1] >= step * 0.6) t.push(to);
    return t;
  }
  const step = span <= 30 ? (narrow ? 10 : 5) : narrow ? 20 : 10;
  const t = [];
  for (let y = Math.ceil(from / step) * step; y <= to; y += step) t.push(y);
  return t;
}

/** 한 해 막대의 반폭(자료 단위). 그림 폭이 넓고 해가 적으면 28px을 넘지 않게 줄인다. */
function halfBar(width, ml, mr, from, to, maxPx = 28) {
  const per = (width - ml - mr) / (to - from + 1);
  return Math.min(0.4, maxPx / 2 / per);
}

const pctText = (v, d = 1) => `${num(v, d)}%`;
/** 성과 이름 첫 글자: "Michael Schumacher" -> "M. Schumacher" (lib/names.ts) */
export const shortLabel = initialSurname;
/** 글자 폭이 px를 넘으면 끝을 줄인다 */
function clip(text, px, size = 12) {
  if (textWidth(text, size) <= px) return text;
  let s = String(text);
  while (s.length > 2 && textWidth(`${s}…`, size) > px) s = s.slice(0, -1);
  return `${s}…`;
}

/* ------------------------------------------------------------------ 통산 순위 막대 (타이틀, 우승) */

/**
 * data: [{id, name, v, active, sub}] 많은 순. active(2025 시즌 출전)는 핑크, 나머지는 블루.
 * 동률은 자료 순서(Jolpica 기준 정렬)를 그대로 둔다.
 */
export function rankBars(data, { width, unit = "번", label = "통산 순위" }) {
  const narrow = width < 560;
  const rowH = 24;
  const rows = data.map((d, i) => ({ ...d, k: String(i), lab: narrow ? shortLabel(d.name) : d.name }));
  const ml = Math.min(narrow ? 118 : 170, Math.max(...rows.map((d) => textWidth(d.lab, 12.5))) + 12);
  const max = Math.max(1, ...rows.map((d) => d.v));
  const H = rows.length * rowH + 34;
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: 40, marginTop: 4, marginBottom: 30,
    x: { domain: [0, max * 1.04] },
    y: { type: "band", domain: rows.map((d) => d.k), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: narrow ? 3 : 5 }),
      Plot.rect(rows, { x1: 0, x2: "v", y: "k", fill: (d) => (d.active ? C.s2 : C.s1), insetTop: 5, insetBottom: 5 }),
      Plot.ruleX([0], { stroke: C.axis }),
      Plot.text(rows, { x: "v", y: "k", dx: 6, textAnchor: "start", text: (d) => int(d.v), fill: C.ink2, fontVariant: "tabular-nums" }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 12.5, label: null, tickFormat: (k) => clip(rows[Number(k)].lab, ml - 12, 12.5) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, ticks: narrow ? 3 : 5, label: null, tickFormat: (d, i, a) => (Number.isInteger(d) ? (i === a.length - 1 ? `${d}${unit}` : d) : "") }),
    ],
  });
  const ys = svg.scale("y");
  const xs = svg.scale("x");
  const stops = rows.map((d) => ({
    py: ys.apply(d.k) + rowH / 2, px: xs.apply(d.v),
    head: d.name,
    rows: [
      { value: `${int(d.v)}${unit}`, label: label.replace(/^통산 /, ""), key: { type: "rect", color: d.active ? C.s2 : C.s1 } },
      ...(d.sub || []).map((s) => ({ value: s.value, label: s.label })),
    ],
    note: d.active ? "2025 시즌에 출전했다." : null,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "y", label, rowH });
  return w;
}

/* ------------------------------------------------------------------ 시즌별 챔피언의 우승 비율 */

/**
 * data: [{s, d1, w, n, pct, hi, note}] 챔피언이 그 시즌 대회 n개 가운데 w번 우승했다(pct = w / n × 100).
 * hi(비율이 가장 높은 몇 시즌)는 핑크다.
 */
export function championWins(data, { width, label = "시즌별 챔피언의 우승 비율" }) {
  const narrow = width < 560;
  const from = data[0].s;
  const to = data[data.length - 1].s;
  const ml = 40;
  const mr = narrow ? 8 : 16;
  const H = narrow ? 220 : 250;
  const mt = 10;
  const mb = 30;
  const hb = halfBar(width, ml, mr, from, to, 14);
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { domain: [0, 100] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: [0, 25, 50, 75, 100] }),
      Plot.rect(data, { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y1: 0, y2: "pct", fill: (d) => (d.hi ? C.s2 : C.s1) }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: [0, 25, 50, 75, 100], label: null, tickFormat: (d) => `${d}%` }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: yearTicks(from, to, narrow), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = data.map((d) => ({
    px: xs.apply(d.s), py: ys.apply(d.pct), top: mt, bottom: H - mb,
    head: `${d.s} 챔피언 ${d.d1}`,
    rows: [
      { value: pctText(d.pct), label: "우승 비율", key: { type: "rect", color: d.hi ? C.s2 : C.s1 } },
      { value: `${d.w}번`, label: "우승" },
      { value: `${d.n}개`, label: "그 시즌 대회" },
    ],
    note: d.note || null,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 드라이버: 시즌 최종 순위 (계단) */

/**
 * rows: [{s, pos, pts, cp, team, champ, ex}] 시즌 순. 위가 1위다. 순위가 없는 시즌(미부여, 실격)은
 * 그림 맨 아래 "미부여" 줄에 빈 고리로 찍고 선을 끊는다. 출전하지 않은 해도 선을 끊는다.
 */
export function driverSteps(rows, { width, label = "시즌 최종 드라이버 순위" }) {
  const narrow = width < 560;
  const from = rows[0].s;
  const to = rows[rows.length - 1].s;
  const by = new Map(rows.map((d) => [d.s, d]));
  const all = [];
  for (let y = from; y <= to; y++) all.push({ s: y, y: by.get(y)?.pos ?? NaN });
  const maxPos = Math.max(10, ...rows.map((d) => d.pos || 0));
  const unr = rows.filter((d) => d.pos == null);
  const U = unr.length ? maxPos + Math.max(2, Math.round(maxPos * 0.12)) : maxPos;
  const base = maxPos <= 12 ? [1, 5, 10] : maxPos <= 24 ? [1, 5, 10, 15, 20] : [1, 10, 20, 30, 40, 50];
  const yTicks = base.filter((t) => t <= maxPos);
  const ml = 46;
  const mr = narrow ? 10 : 20;
  const mt = 14;
  const mb = 30;
  const H = narrow ? 230 : 260;
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { domain: [1, U], reverse: true },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: yTicks }),
      unr.length ? Plot.ruleY([U], { stroke: C.grid }) : null,
      Plot.lineY(all, { x: "s", y: "y", stroke: C.s1, strokeWidth: 2, curve: "step" }),
      Plot.dot(rows.filter((d) => d.pos && !d.champ), { x: "s", y: "pos", r: 3, fill: C.s1, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.dot(rows.filter((d) => d.champ), { x: "s", y: "pos", r: 5.5, fill: C.s2, stroke: C.paper, strokeWidth: 1.5 }),
      Plot.dot(unr, { x: "s", y: U, r: 3.5, fill: C.paper, stroke: C.ctx, strokeWidth: 1.5 }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: unr.length ? [...yTicks, U] : yTicks, label: null, tickFormat: (d) => (d === U && unr.length ? "미부여" : `${d}위`) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: yearTicks(from, to, narrow), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((d) => ({
    px: xs.apply(d.s), py: ys.apply(d.pos ?? U), top: mt, bottom: H - mb,
    head: `${d.s} ${d.team}`,
    rows: [
      {
        value: d.pos ? `${d.pos}위` : d.ex ? "실격" : "미부여",
        label: d.champ ? "최종 순위 (챔피언)" : "최종 순위",
        key: d.champ ? { type: "dot", color: C.s2 } : d.pos ? { type: "line", color: C.s1 } : { type: "ring", color: C.ctx },
      },
      ...(d.pts != null ? [{ value: `${pt(d.pts)}점`, label: "시즌 점수" }] : []),
      { value: `${pt(d.cp)}점`, label: "그 시즌 1위 점수" },
    ],
    note: d.ex ? "시즌 결과에서 실격 처리되어 순위가 없다." : d.pos ? null : "Jolpica 드라이버 순위표에 순위가 없는 시즌이다.",
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 드라이버: 1위 점수 대비 비율 */

/** rows: [{s, share, pts, cp, pos, champ, ex, team}] share는 %이고 순위표 점수가 없으면 null이다. */
export function driverShare(rows, { width, label = "시즌 점수의 1위 점수 대비 비율" }) {
  const narrow = width < 560;
  const from = rows[0].s;
  const to = rows[rows.length - 1].s;
  const ml = 44;
  const mr = narrow ? 10 : 20;
  const mt = 12;
  const mb = 30;
  const H = narrow ? 210 : 240;
  const hb = halfBar(width, ml, mr, from, to);
  const have = rows.filter((d) => d.share != null && !d.ex);
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { domain: [0, 100] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: [0, 25, 50, 75, 100] }),
      Plot.rect(have, { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y1: 0, y2: "share", fill: (d) => (d.champ ? C.s2 : C.s1) }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: [0, 25, 50, 75, 100], label: null, tickFormat: (d) => `${d}%` }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: yearTicks(from, to, narrow), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((d) => ({
    px: xs.apply(d.s), py: ys.apply(d.share != null && !d.ex ? d.share : 0), top: mt, bottom: H - mb,
    head: `${d.s} ${d.team}`,
    rows: [
      { value: d.share != null && !d.ex ? pctText(d.share) : "계산 안 함", label: "1위 점수 대비", key: { type: "rect", color: d.champ ? C.s2 : C.s1 } },
      ...(d.pts != null ? [{ value: `${pt(d.pts)}점`, label: "시즌 점수" }] : []),
      { value: `${pt(d.cp)}점`, label: "그 시즌 1위 점수" },
      { value: d.pos ? `${d.pos}위` : d.ex ? "실격" : "미부여", label: "최종 순위" },
    ],
    note: d.ex ? "실격 시즌이라 비율을 계산하지 않는다." : d.pts == null ? "순위표 점수가 없는 시즌이다." : null,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 드라이버: 시즌별 우승과 포디움 */

/** rows: [{s, e, w, p, team}] e 출전, w 우승, p 포디움(우승 포함). 출전은 옅은 띠, 그 위에 2·3위(블루)와 우승(핑크)을 쌓는다. */
export function driverPodiums(rows, { width, label = "시즌별 우승과 포디움" }) {
  const narrow = width < 560;
  const from = rows[0].s;
  const to = rows[rows.length - 1].s;
  const ml = 40;
  const mr = narrow ? 10 : 20;
  const mt = 12;
  const mb = 30;
  const H = narrow ? 210 : 240;
  const hb = halfBar(width, ml, mr, from, to);
  const max = Math.max(1, ...rows.map((d) => d.e));
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { domain: [0, max * 1.04] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 4 }),
      Plot.rect(rows, { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y1: 0, y2: "e", fill: C.band }),
      Plot.rect(rows.filter((d) => d.p > d.w), { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y1: "w", y2: "p", fill: C.s1 }),
      Plot.rect(rows.filter((d) => d.w > 0), { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y1: 0, y2: "w", fill: C.s2 }),
      Plot.ruleY([0], { stroke: C.axis }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 4, label: null, tickFormat: (d, i, a) => (Number.isInteger(d) ? (i === a.length - 1 ? `${d}회` : d) : "") }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: yearTicks(from, to, narrow), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((d) => ({
    px: xs.apply(d.s), py: ys.apply(Math.max(d.p, 0.5)), top: mt, bottom: H - mb,
    head: `${d.s} ${d.team}`,
    rows: [
      { value: `${d.w}번`, label: "우승", key: { type: "rect", color: C.s2 } },
      { value: `${d.p - d.w}번`, label: "2·3위", key: { type: "rect", color: C.s1 } },
      { value: `${d.e}회`, label: "출전 대회", key: { type: "rect", color: C.band } },
    ],
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 드라이버: 팀 동료 비교 (위아래로 나눈 막대) */

/**
 * rows: [{s, ra, rb, qa, qb, team, mates: [{name, ra, rb, qa, qb}]}]. kind "race"면 결승, "quali"면 예선.
 * 앞선 횟수는 0선 위(블루), 뒤진 횟수는 0선 아래(맥락 회색)다. 한 대회에 동료가 여럿이면 동료마다 센다. 비교가 0번인 시즌은 비운다.
 * from, to를 주면 두 그림(결승, 예선)의 가로축을 맞춘다.
 */
export function mateBars(rows, { width, kind = "race", from, to, label }) {
  const narrow = width < 560;
  const A = kind === "race" ? "ra" : "qa";
  const B = kind === "race" ? "rb" : "qb";
  const data = rows.filter((d) => d[A] + d[B] > 0);
  if (!data.length) return el("p", "fig-fallback", "비교가 0번이라 그릴 막대가 없다.");
  const f = from ?? data[0].s;
  const t = to ?? data[data.length - 1].s;
  const ml = 40;
  const mr = narrow ? 10 : 20;
  const mt = 10;
  const mb = 30;
  const H = narrow ? 220 : 250;
  const hb = halfBar(width, ml, mr, f, t);
  const M = Math.max(1, ...data.map((d) => Math.max(d[A], d[B])));
  const what = kind === "race" ? "결승" : "예선";
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [f - 0.5, t + 0.5] },
    y: { domain: [-M * 1.22, M * 1.22] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 5 }),
      Plot.rect(data.filter((d) => d[A] > 0), { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y1: 0, y2: A, fill: C.s1 }),
      Plot.rect(data.filter((d) => d[B] > 0), { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y1: (d) => -d[B], y2: 0, fill: C.ctx }),
      Plot.ruleY([0], { stroke: C.ink2 }),
      Plot.text(["앞섬"], { frameAnchor: "top-left", dx: 4, dy: 2, fill: C.ink2, fontWeight: 600, fontSize: 11 }),
      Plot.text(["뒤짐"], { frameAnchor: "bottom-left", dx: 4, dy: -2, fill: C.ink2, fontWeight: 600, fontSize: 11 }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 5, label: null, tickFormat: (d) => (Number.isInteger(d) ? String(Math.abs(d)) : "") }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: yearTicks(f, t, narrow), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = data.map((d) => ({
    px: xs.apply(d.s), py: ys.apply(d[A] >= d[B] ? d[A] : -d[B]), top: mt, bottom: H - mb,
    head: `${d.s} ${d.team}`,
    rows: [
      { value: `${d[A]}번`, label: `${what}에서 앞섬`, key: { type: "rect", color: C.s1 } },
      { value: `${d[B]}번`, label: `${what}에서 뒤짐`, key: { type: "rect", color: C.ctx } },
      ...(d.mates.length > 1 ? d.mates.filter((m) => m[A] + m[B] > 0).map((m) => ({ value: `${m[A]}:${m[B]}`, label: m.name })) : []),
    ],
    note: d.mates.length === 1 ? `동료: ${d.mates[0].name}` : null,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label: label || `팀 동료와의 ${what} 비교` });
  return w;
}

/* ------------------------------------------------------------------ 드라이버: 팀 이력 (줄마다 팀) */

/**
 * rows: [{key, name, seasons: [{s, champ}], span, e, w, p}] 처음 나온 순. 한 해 칸은 블루, 챔피언 시즌은 핑크.
 */
export function driverTeams(rows, { width, from, to, label = "팀 이력" }) {
  const narrow = width < 560;
  const rowH = 26;
  const ml = Math.min(narrow ? 110 : 170, Math.max(...rows.map((d) => textWidth(d.name, 12.5))) + 12);
  const mr = narrow ? 10 : 20;
  const H = rows.length * rowH + 34;
  const hb = halfBar(width, ml, mr, from, to, 30);
  const cells = rows.flatMap((d) => d.seasons.map((x) => ({ key: d.key, s: x.s, champ: x.champ })));
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: 4, marginBottom: 30,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { type: "band", domain: rows.map((d) => d.key), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: yearTicks(from, to, narrow) }),
      Plot.rect(cells, { x1: (d) => d.s - hb, x2: (d) => d.s + hb, y: "key", fill: (d) => (d.champ ? C.s2 : C.s1), insetTop: 6, insetBottom: 6 }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 12.5, label: null, tickFormat: (k) => clip(rows.find((d) => d.key === k)?.name ?? k, ml - 12, 12.5) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: yearTicks(from, to, narrow), tickFormat: String }),
    ],
  });
  const ys = svg.scale("y");
  const xs = svg.scale("x");
  const stops = rows.map((d) => ({
    py: ys.apply(d.key) + rowH / 2, px: xs.apply(d.seasons[d.seasons.length - 1].s),
    head: d.name,
    rows: [
      { value: d.span, label: "기간", key: { type: "rect", color: C.s1 } },
      { value: `${d.seasons.length}개`, label: "시즌" },
      { value: `${d.e}회`, label: "출전" },
      { value: `${d.w}번`, label: "우승" },
      { value: `${d.p}번`, label: "포디움" },
    ],
    note: d.seasons.some((x) => x.champ) ? `챔피언 시즌: ${d.seasons.filter((x) => x.champ).map((x) => x.s).join(", ")}` : null,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "y", label, rowH, band: ml });
  return w;
}
