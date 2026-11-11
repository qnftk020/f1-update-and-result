// F1 업그레이드와 성능 추이: 챔피언십 역사 차트 (시즌 목록 /seasons/, 팀 목록 /teams/)
// 각 함수는 (data, opts)를 받아 요소를 돌려준다. opts.width는 mount()가 넘긴다. 자료는 빌드 때
// lib/history.ts가 만든다. 색은 CSS 변수다. 순위 칸의 단계 색(--hist-r1~r5)은 styles/history.css에 있다.
import * as Plot from "@observablehq/plot";
import { C, el, frameOf, plot, readout, textWidth } from "./core.js";

const decadeTicks = (from, to, step = 10) => {
  const out = [];
  for (let y = Math.ceil(from / step) * step; y <= to; y += step) out.push(y);
  return out;
};

/** 좁은 칸에 들어가지 않는 글자는 끝을 줄이고 말줄임표를 단다(전체 글자는 툴팁과 표 보기에 있다). */
function fit(text, maxW, px = 12) {
  if (textWidth(text, px) <= maxW) return text;
  let t = String(text);
  while (t.length > 1 && textWidth(`${t}…`, px) > maxW) t = t.slice(0, -1);
  return t.length > 1 ? `${t}…` : "";
}

/* ------------------------------------------------------------------ 시즌별 막대 (단일 계열, 강조 핑크, 중앙값 선) */

/**
 * data: {unit, yLabel, median, rows: [{s, v, hl, head, tip: [[값, 이름]], note}], marks: [{s, text}]}
 * 또는 {d: 그 모양, c: 그 모양}이고 opts.kind로 고른다(드라이버, 컨스트럭터 전환).
 * 강조(hl) 막대는 핑크이고 marks의 글자를 막대 위에 단다. 글자가 겹치면 위로 한 줄씩 올린다.
 */
export function seasonBars(input, { width, kind = "d", label = "시즌별 값" }) {
  const d = input.rows ? input : input[kind] || input.d;
  const narrow = width < 560;
  const rows = d.rows;
  const from = Math.min(...rows.map((r) => r.s));
  const to = Math.max(...rows.map((r) => r.s));
  const H = narrow ? 220 : 260;
  const ml = 40;
  const mr = narrow ? 6 : 10;
  const mb = 28;
  const vmax = Math.max(...rows.map((r) => r.v));
  // 강조 글자 자리: 가로로 겹치면 한 줄 위로 올린다
  const xPx = (s) => ml + ((s - from + 0.5) / (to - from + 1)) * (width - ml - mr);
  const placed = [];
  const marks = [...d.marks].sort((a, b) => a.s - b.s).map((m) => {
    const w = textWidth(m.text, 12) + 6;
    const x = xPx(m.s);
    const anchor = x - w / 2 < ml ? "start" : x + w / 2 > width - mr ? "end" : "middle";
    const x0 = anchor === "start" ? x - 4 : anchor === "end" ? x - w + 4 : x - w / 2;
    let level = 0;
    while (placed.some((p) => p.level === level && !(x0 + w < p.x0 || x0 > p.x1))) level++;
    placed.push({ x0, x1: x0 + w, level });
    // 글자는 그 글자가 덮는 시즌들의 가장 높은 막대 위에 놓고, 막대 끝에서 글자까지 가는 선을 긋는다
    const v = rows.find((r) => r.s === m.s)?.v ?? 0;
    const top = Math.max(v, ...rows.filter((r) => xPx(r.s) + 3 >= x0 && xPx(r.s) - 3 <= x0 + w).map((r) => r.v));
    return { ...m, v, top, anchor, level };
  });
  const levels = Math.max(0, ...marks.map((m) => m.level)) + 1;
  const mt = 10;
  const ymax = vmax * (1.1 + 0.1 * levels);
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { domain: [0, ymax] },
    marks: [
      Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: 4 }),
      Plot.rect(rows, { x1: (r) => r.s - 0.42, x2: (r) => r.s + 0.42, y1: 0, y2: "v", fill: (r) => (r.hl ? C.s2 : C.s1) }),
      Plot.ruleY([0], { stroke: C.axis }),
      d.median != null ? Plot.ruleY([d.median], { stroke: C.ink3, strokeWidth: 1, strokeDasharray: "4 3" }) : null,
      Plot.ruleX(marks.filter((m) => m.top > m.v || m.level > 0), { x: "s", y1: "v", y2: (m) => m.top + ymax * 0.015, stroke: C.ink3, strokeWidth: 1 }),
      // dx, dy, textAnchor는 상수만 받으므로 줄과 맞춤마다 마크를 나눈다
      ...[...new Set(marks.map((m) => `${m.level}|${m.anchor}`))].map((k) => {
        const [lv, anchor] = k.split("|");
        return Plot.text(marks.filter((m) => `${m.level}|${m.anchor}` === k), {
          x: "s", y: "top", dy: -7 - Number(lv) * 15, textAnchor: anchor, dx: anchor === "start" ? -4 : anchor === "end" ? 4 : 0,
          text: "text", fill: C.ink, fontWeight: 600, fontSize: 12, stroke: C.paper, strokeWidth: 3,
        });
      }),
      Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: 4, label: null, tickFormat: (v, i, a) => (i === a.length - 1 ? `${v}${d.unit}` : String(v)) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: decadeTicks(from, to), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((r) => ({
    px: xs.apply(r.s), py: ys.apply(r.v), top: mt, bottom: H - mb,
    head: r.head,
    rows: r.tip.map(([value, lab], i) => ({ value, label: lab, key: i === r.tip.length - 1 ? { type: "rect", color: r.hl ? C.s2 : C.s1 } : null })),
    note: r.note || null,
  }));
  const fmt = (v) => (d.unit === "%" ? `${v.toFixed(v < 10 ? 2 : 1)}%` : `${v}${d.unit}`);
  const w = frameOf(svg, d.median != null ? [el("p", "axis-note", `점선은 ${from}-${to}년 중앙값 ${fmt(d.median)}이다.`)] : []);
  readout(w, svg, stops, { axis: "x", label });
  return w;
}

/* ------------------------------------------------------------------ 타이틀 시즌 점 줄 (행: 드라이버나 팀, 가로: 시즌) */

/**
 * data: {from, to, rows: [{key, name, short, n, seasons, sub}]} 타이틀이 많은 순.
 * 행마다 첫 타이틀부터 마지막 타이틀까지 가는 선을 긋고 타이틀 시즌에 점을 찍는다. 오른쪽에 횟수를 적는다.
 */
export function titleDots(input, { width, label = "타이틀 시즌" }) {
  const { from, to, rows } = input;
  const narrow = width < 560;
  const rowH = narrow ? 20 : 22;
  const nameOf = (r) => (narrow ? r.short : r.name);
  const ml = Math.min(narrow ? 104 : 180, Math.max(...rows.map((r) => textWidth(nameOf(r), 12))) + 12);
  const mr = 36;
  const mb = 26;
  const step = (width - ml - mr) / (to - from + 1);
  const r = Math.max(2, Math.min(4.5, step * 0.5));
  const H = rows.length * rowH + mb + 4;
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: 4, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { type: "band", domain: rows.map((d) => d.key), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: decadeTicks(from, to) }),
      Plot.ruleY(rows.filter((d) => d.seasons.length > 1), { y: "key", x1: (d) => Math.min(...d.seasons), x2: (d) => Math.max(...d.seasons), stroke: C.axis, strokeWidth: 1 }),
      Plot.dot(rows.flatMap((d) => d.seasons.map((s) => ({ key: d.key, s }))), { x: "s", y: "key", r, fill: C.s1, stroke: C.paper, strokeWidth: r > 3 ? 1.5 : 0.75 }),
      Plot.text(rows, { y: "key", frameAnchor: "right", dx: mr - 2, textAnchor: "end", fill: C.ink2, fontVariant: "tabular-nums", text: (d) => `${d.n}회` }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 12, label: null, tickFormat: (k) => nameOf(rows.find((d) => d.key === k)) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: decadeTicks(from, to, narrow ? 20 : 10), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((d) => ({
    py: ys.apply(d.key) + rowH / 2, px: xs.apply(Math.max(...d.seasons)),
    head: d.name,
    rows: [{ value: `${d.n}회`, label: "타이틀", key: { type: "dot", color: C.s1 } }],
    note: `${d.seasons.join(", ")}. ${d.sub}`,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "y", label, rowH });
  return w;
}

/* ------------------------------------------------------------------ 해마다의 1위 격자 (행: 연대, 열: 끝자리) */

const CAT_FILL = { s1: C.s1, s2: C.s2, s3: C.s3, ctx: C.ctx, out: C.paper3 };

/**
 * data: {cats: [{key, label}], rows: [{s, d: {name, short, teams, lin, cat, pts}, c: {name, lin, cat, pts} | null, split}]}
 * 칸 하나가 한 시즌이다. 위 띠는 드라이버 1위의 팀, 아래 띠는 컨스트럭터 1위의 계보 색이다.
 * 칸이 넓으면(64px 이상) 띠 대신 색 견본과 이름을 적는다. 드라이버 1위의 팀이 컨스트럭터 1위가 아닌 시즌은 잉크 테두리다.
 */
export function titleGrid(input, { width, label = "해마다의 드라이버 1위와 컨스트럭터 1위" }) {
  const rows = input.rows;
  const catLabel = Object.fromEntries(input.cats.map((c) => [c.key, c.label]));
  const from = Math.floor(Math.min(...rows.map((r) => r.s)) / 10) * 10;
  const to = Math.max(...rows.map((r) => r.s));
  const nDec = Math.floor(to / 10) - from / 10 + 1;
  const ml = 40;
  const mr = 2;
  const cw = (width - ml - mr) / 10;
  const wide = cw >= 64;
  const cellH = wide ? 62 : 36;
  const mt = 18;
  const H = nDec * cellH + mt + 4;
  const cells = rows.map((r) => ({ ...r, col: r.s % 10, row: Math.floor(r.s / 10) - from / 10 }));
  const gx = 2 / cw; // 칸 사이 2px
  const textW = cw - 22;
  const marks = [
    // 칸 바탕
    Plot.rect(cells, { x1: (c) => c.col + gx, x2: (c) => c.col + 1 - gx, y1: (c) => c.row + 0.03, y2: (c) => c.row + 0.97, fill: C.paper2 }),
    // 연대 이름과 끝자리
    Plot.text(Array.from({ length: nDec }, (_, i) => i), { x: 0, y: (i) => i + 0.5, dx: -6, textAnchor: "end", fill: C.ink2, fontSize: 12, fontVariant: "tabular-nums", text: (i) => `${from + i * 10}` }),
    Plot.text(Array.from({ length: 10 }, (_, i) => i), { x: (i) => i + 0.5, y: 0, dy: -9, fill: C.ink3, fontSize: 11, text: (i) => `+${i}` }),
  ];
  if (wide) {
    const sw = 8 / cw; // 견본 8px
    const yy = (k) => (c) => c.row + k;
    marks.push(
      Plot.text(cells, { x: (c) => c.col + gx, y: yy(0.2), dx: 6, textAnchor: "start", fill: C.ink3, fontSize: 11, fontVariant: "tabular-nums", text: (c) => String(c.s) }),
      Plot.rect(cells, { x1: (c) => c.col + gx + 6 / cw, x2: (c) => c.col + gx + 6 / cw + sw, y1: (c) => c.row + 0.43, y2: (c) => c.row + 0.43 + 8 / cellH, fill: (c) => CAT_FILL[c.d.cat], stroke: (c) => (c.d.cat === "out" ? C.ink3 : "none") }),
      Plot.text(cells, { x: (c) => c.col + gx, y: yy(0.5), dx: 18, textAnchor: "start", fill: C.ink, fontSize: 12, fontWeight: 600, text: (c) => fit(textWidth(c.d.name, 12) <= textW ? c.d.name : c.d.short, textW) }),
      Plot.rect(cells.filter((c) => c.c), { x1: (c) => c.col + gx + 6 / cw, x2: (c) => c.col + gx + 6 / cw + sw, y1: (c) => c.row + 0.69, y2: (c) => c.row + 0.69 + 8 / cellH, fill: (c) => CAT_FILL[c.c.cat], stroke: (c) => (c.c.cat === "out" ? C.ink3 : "none") }),
      Plot.text(cells.filter((c) => c.c), { x: (c) => c.col + gx, y: yy(0.76), dx: 18, textAnchor: "start", fill: C.ink2, fontSize: 12, text: (c) => fit(c.c.name, textW) }),
    );
  } else {
    const pad = Math.min(4, cw * 0.12) / cw;
    marks.push(
      Plot.rect(cells, { x1: (c) => c.col + gx + pad, x2: (c) => c.col + 1 - gx - pad, y1: (c) => c.row + 0.12, y2: (c) => c.row + 0.47, fill: (c) => CAT_FILL[c.d.cat], stroke: (c) => (c.d.cat === "out" ? C.ink3 : "none") }),
      Plot.rect(cells.filter((c) => c.c), { x1: (c) => c.col + gx + pad, x2: (c) => c.col + 1 - gx - pad, y1: (c) => c.row + 0.53, y2: (c) => c.row + 0.88, fill: (c) => CAT_FILL[c.c.cat], stroke: (c) => (c.c.cat === "out" ? C.ink3 : "none") }),
    );
  }
  // 갈린 시즌: 칸 전체에 잉크 테두리
  marks.push(Plot.rect(cells.filter((c) => c.split), { x1: (c) => c.col + gx, x2: (c) => c.col + 1 - gx, y1: (c) => c.row + 0.03, y2: (c) => c.row + 0.97, fill: "none", stroke: C.ink, strokeWidth: 2 }));
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: 4,
    x: { domain: [0, 10], axis: null },
    y: { domain: [nDec, 0], axis: null },
    marks,
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = cells.map((c) => ({
    px: xs.apply(c.col + 0.5), py: ys.apply(c.row + 0.5),
    head: `${c.s}년`,
    rows: [
      { value: c.d.name, label: `드라이버 1위 · ${c.d.teams}`, key: { type: "rect", color: CAT_FILL[c.d.cat] } },
      ...(c.c ? [{ value: c.c.name, label: "컨스트럭터 1위", key: { type: "rect", color: CAT_FILL[c.c.cat] } }] : []),
    ],
    note: [
      c.c ? null : "컨스트럭터 순위는 1958년부터 있다",
      c.d.lin ? `드라이버 팀 계보: ${c.d.lin}` : `드라이버 팀: ${catLabel.out}`,
      c.c ? (c.c.lin ? `컨스트럭터 계보: ${c.c.lin}` : `컨스트럭터: ${catLabel.out}`) : null,
      c.split ? "드라이버 1위의 팀이 컨스트럭터 1위가 아니다." : null,
    ].filter(Boolean).join(". "),
  }));
  const w = frameOf(svg);
  // 칸 순번은 시즌 순서(연대 행 우선)라서 ←/→는 앞뒤 해, ↑/↓는 10년 앞뒤다
  readout(w, svg, stops, { axis: "grid", cols: 10, label });
  return w;
}

/* ------------------------------------------------------------------ 계보별 시즌 최종 순위 (열지도, 좁으면 이름을 줄 위로 올린 칸 줄) */

const RAMP = { 1: C.s2, 2: "var(--hist-r5)", 3: "var(--hist-r4)", 4: "var(--hist-r3)", 6: "var(--hist-r2)", 11: "var(--hist-r1)" };
/** 순위 단계: 1위 핑크, 2위, 3위, 4~5위, 6~10위, 11위 이하 블루 단계 */
export function rankFill(pos) {
  if (pos == null) return null;
  if (pos === 1) return RAMP[1];
  if (pos === 2) return RAMP[2];
  if (pos === 3) return RAMP[3];
  if (pos <= 5) return RAMP[4];
  if (pos <= 10) return RAMP[6];
  return RAMP[11];
}

function heatStop(row, c, s) {
  if (!c) return { head: `${row.short} · ${s}년`, rows: [], note: "이 계보는 이 시즌에 출전하지 않았다." };
  return {
    head: `${row.short} · ${s}년`,
    rows: [
      { value: c.pos ? `${c.pos}위` : "순위 없음", label: c.names, key: c.pos ? { type: "rect", color: rankFill(c.pos) } : null },
      ...(c.pts != null ? [{ value: `${c.pts}점`, label: "최종 점수" }] : []),
      { value: `${c.wins}승`, label: `우승 (출전 ${c.entered}개 대회)` },
    ],
    note: c.note || null,
  };
}

/**
 * data: {from, to, rows: [{id, name, short, titles, cells: [{s, pos, names, pts, wins, entered, note}]}]}
 * 넓으면(640px 이상) 행 = 계보, 열 = 시즌인 열지도. 좁으면 계보 이름을 줄 위로 올리고 칸 줄이 전체 폭을 쓴다.
 */
export function lineageHeat(input, { width, label = "계보별 시즌 최종 순위" }) {
  return width >= 640 ? heatWide(input, width, label) : heatSmall(input, width, label);
}

function heatWide({ from, to, rows }, width, label) {
  const rowH = 24;
  const ml = Math.max(...rows.map((r) => textWidth(r.short, 13))) + 14;
  const mr = 40;
  const mb = 26;
  const H = rows.length * rowH + mb + 4;
  const cells = rows.flatMap((r) => r.cells.map((c) => ({ ...c, id: r.id })));
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: 4, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { type: "band", domain: rows.map((r) => r.id), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: decadeTicks(from, to) }),
      Plot.rect(cells.filter((c) => c.pos != null), { x1: (c) => c.s - 0.5, x2: (c) => c.s + 0.5, y: "id", fill: (c) => rankFill(c.pos), inset: 0.5, insetTop: 2, insetBottom: 2 }),
      Plot.rect(cells.filter((c) => c.pos == null), { x1: (c) => c.s - 0.5, x2: (c) => c.s + 0.5, y: "id", fill: C.paper, stroke: C.ink3, strokeWidth: 1, inset: 1.5, insetTop: 3, insetBottom: 3 }),
      Plot.text(rows, { y: "id", frameAnchor: "right", dx: mr - 2, textAnchor: "end", fill: C.ink2, fontVariant: "tabular-nums", text: (r) => `${r.titles}회` }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 13, label: null, tickFormat: (id) => rows.find((r) => r.id === id).short }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: decadeTicks(from, to), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const n = to - from + 1;
  const stops = [];
  for (const r of rows) {
    const by = new Map(r.cells.map((c) => [c.s, c]));
    for (let s = from; s <= to; s++) stops.push({ px: xs.apply(s), py: ys.apply(r.id) + rowH / 2, ...heatStop(r, by.get(s), s) });
  }
  const w = frameOf(svg, [el("p", "axis-note", "오른쪽 숫자는 계보의 컨스트럭터 타이틀 수다.")]);
  readout(w, svg, stops, { axis: "grid", cols: n, rowH, label });
  return w;
}

function heatSmall({ from, to, rows }, width, label) {
  // 좁은 화면: 같은 칸 색을 쓰되 계보 이름을 줄 위에 적어 칸 줄이 전체 폭을 쓴다(범례가 그대로 맞는다)
  const rowH = 42;
  const ml = 2;
  const mr = 2;
  const mb = 24;
  const H = rows.length * rowH + mb + 2;
  const cells = rows.flatMap((r, i) => r.cells.map((c) => ({ ...c, i })));
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: 2, marginBottom: mb,
    x: { domain: [from - 0.5, to + 0.5] },
    y: { domain: [rows.length, 0], axis: null },
    marks: [
      Plot.text(rows, { x: from - 0.5, y: (r, i) => i + 0.26, textAnchor: "start", fill: C.ink, fontWeight: 700, fontSize: 12, text: "short" }),
      Plot.text(rows, { x: to + 0.5, y: (r, i) => i + 0.26, textAnchor: "end", fill: C.ink2, fontSize: 11, fontVariant: "tabular-nums", text: (r) => `타이틀 ${r.titles}회` }),
      Plot.rect(rows, { x1: from - 0.5, x2: to + 0.5, y1: (r, i) => i + 0.47, y2: (r, i) => i + 0.93, fill: C.paper2 }),
      Plot.rect(cells.filter((c) => c.pos != null), { x1: (c) => c.s - 0.5, x2: (c) => c.s + 0.5, y1: (c) => c.i + 0.47, y2: (c) => c.i + 0.93, fill: (c) => rankFill(c.pos) }),
      Plot.rect(cells.filter((c) => c.pos == null), { x1: (c) => c.s - 0.5, x2: (c) => c.s + 0.5, y1: (c) => c.i + 0.47, y2: (c) => c.i + 0.93, fill: C.paper, stroke: C.ink3, strokeWidth: 1, inset: 0.5 }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: decadeTicks(from, to, 20), tickFormat: String }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = [];
  rows.forEach((r, i) => {
    const by = new Map(r.cells.map((c) => [c.s, c]));
    for (let s = from; s <= to; s++) stops.push({ px: xs.apply(s), py: ys.apply(i + 0.7), ...heatStop(r, by.get(s), s) });
  });
  const w = frameOf(svg, [el("p", "axis-note", "칸을 누르고 옆으로 끌면 시즌을 차례로 읽는다.")]);
  readout(w, svg, stops, { axis: "grid", cols: to - from + 1, rowH: rowH * 0.46, label });
  return w;
}

/* ------------------------------------------------------------------ 계보별 가로 막대 (단일 계열) */

/** data: {unit, rows: [{key, name, v, tip: [[값, 이름]], note}]} 큰 순. v가 0이면 막대 없이 점과 0을 적는다. */
export function lineageBars(input, { width, label = "계보별 값" }) {
  const { unit, rows } = input;
  const narrow = width < 480;
  const rowH = 26;
  const ml = Math.max(...rows.map((d) => textWidth(d.name, 13))) + 14;
  const mr = narrow ? 44 : 56;
  const max = Math.max(1, ...rows.map((d) => d.v));
  const svg = plot({
    width, height: rows.length * rowH + 30, marginLeft: ml, marginRight: mr, marginTop: 2, marginBottom: 28,
    x: { domain: [0, max * 1.02], nice: false },
    y: { type: "band", domain: rows.map((d) => d.key), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: narrow ? 3 : 4 }),
      Plot.barX(rows.filter((d) => d.v > 0), { x: "v", y: "key", fill: C.s1, insetTop: (rowH - 12) / 2, insetBottom: (rowH - 12) / 2, rx2: 3 }),
      Plot.dot(rows.filter((d) => d.v === 0), { x: 0, y: "key", r: 3.5, fill: C.paper, stroke: C.ink3, strokeWidth: 1.5 }),
      Plot.ruleX([0], { stroke: C.ink3 }),
      Plot.text(rows, { x: "v", y: "key", dx: 7, textAnchor: "start", fill: C.ink2, fontVariant: "tabular-nums", text: (d) => `${d.v}${unit}` }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 13, label: null, tickFormat: (k) => rows.find((d) => d.key === k).name }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, ticks: narrow ? 3 : 4, label: null, tickFormat: (v, i, a) => (i === a.length - 1 ? `${v}${unit}` : String(v)) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.map((d) => ({
    py: ys.apply(d.key) + rowH / 2, px: xs.apply(d.v),
    head: d.name,
    rows: d.tip.map(([value, lab], i) => ({ value, label: lab, key: i === 0 ? { type: "rect", color: C.s1 } : null })),
    note: d.note || null,
  }));
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "y", label, rowH });
  return w;
}
