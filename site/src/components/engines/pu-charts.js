// 엔진 페이지 전용 차트 두 개. 공용 charts.js의 puSteps, newIce를 바탕으로 하되 실제 자료에 필요한 것을 더했다.
//  - puTeamSteps: 팀 한 칸의 PU 구성요소 누적 계단선. 모든 칸이 같은 세로축(yMax), 허용 개수 가로선(allowed),
//    누적 문서를 받지 않은 라운드(missing)는 선을 끊고 툴팁에 "문서 미수집"으로 적는다.
//  - newIceMatrix: 새 ICE 투입 점 행렬. 점은 FIA 선언 문서의 투입 이벤트(fresh)에서 찍는다(누적 값의 증가로
//    추정하지 않는다). 허용 개수를 넘은 투입은 잉크 고리를 더한다. 팀 경계에 헤어라인.
// 공용 차트 모듈의 틀(plot, frameOf, readout, 토큰)을 그대로 쓴다. 데이터에서 온 글자는 Plot이 textContent로 넣는다.
import * as Plot from "@observablehq/plot";
import { C, SLOTS, frameOf, plot, readout, roundTick, textWidth } from "../../lib/charts/core.js";

const xTicks = (n) => [1, ...[6, 12, 18, 24].filter((t) => t < n - 2), n];

/**
 * rows: [{label, code, by: {ICE: [라운드별 누적 | null], ...}}]
 * opts: rounds, element, yMax, allowed(허용 개수 또는 null), missing(누적 문서가 없는 라운드), unknown(선언 문서가 없는 라운드),
 *       roundNames(라운드별 짧은 대회 이름), team(칸 이름, 툴팁 머리)
 */
export function puTeamSteps(rows, { width, rounds, element = "ICE", yMax, allowed = null, missing = [], unknown = [], roundNames = [], team = "", label } = {}) {
  const narrow = width < 380;
  const n = rounds;
  const miss = new Set(missing);
  const unk = new Set(unknown);
  const lines = rows.map((d) => ({ label: d.code || d.label, full: d.label, s: (d.by && d.by[element]) || [] }));
  const drawn = lines.filter((d) => d.s.some((c) => c != null));
  const colorOf = (k) => SLOTS[k] || C.ctx;
  const localMax = Math.max(1, ...drawn.flatMap((d) => d.s.filter((c) => c != null)));
  const max = Math.max(yMax || 0, localMax, allowed || 0);
  const H = 170;
  const mt = 14;
  const mb = 26;
  const pts = (d) => Array.from({ length: n }, (_, i) => ({ round: i + 1, c: d.s[i] ?? null }));
  // 끝 라벨: 마지막 값 자리. 같은 높이면 위아래로 띄운다.
  const ends = drawn.map((d, k) => {
    const list = pts(d).filter((p) => p.c != null);
    const last = list.at(-1);
    return { k, label: d.label, round: last.round, c: last.c };
  });
  const svg0 = { y: (v) => mt + (1 - v / (max + 0.5)) * (H - mt - mb) };
  const sorted = [...ends].sort((a, b) => svg0.y(a.c) - svg0.y(b.c));
  let prevY = -Infinity;
  for (const e of sorted) {
    let y = svg0.y(e.c);
    if (y - prevY < 13) y = prevY + 13;
    e.dy = y - svg0.y(e.c);
    prevY = y;
  }
  const marks = [
    Plot.gridY({ stroke: C.grid, strokeOpacity: 1, ticks: Math.min(max, 8) }),
    Plot.ruleY([0], { stroke: C.axis }),
  ];
  if (allowed != null) {
    marks.push(Plot.ruleY([allowed], { stroke: C.ink3, strokeWidth: 1 }));
    marks.push(Plot.text([allowed], { y: (d) => d, frameAnchor: "left", dx: 2, dy: -7, textAnchor: "start", text: () => `허용 ${allowed}개`, fill: C.ink2, fontSize: 11, stroke: C.paper, strokeWidth: 3 }));
  }
  // 같은 값의 선이 서로 덮지 않게 계열마다 세로로 2px씩 띄운다(값은 툴팁과 표에 있다).
  const off = (k) => (k - (drawn.length - 1) / 2) * 2;
  drawn.forEach((d, k) => {
    const p = pts(d);
    marks.push(Plot.lineY(p, { x: "round", y: "c", dy: off(k), stroke: colorOf(k), strokeWidth: k < 3 ? 2 : 1.5, curve: "step-after" }));
    // 앞뒤가 비어 선이 되지 못하는 값은 점으로 찍는다.
    const lone = p.filter((q, i) => q.c != null && (p[i - 1]?.c ?? null) == null && (p[i + 1]?.c ?? null) == null);
    if (lone.length) marks.push(Plot.dot(lone, { x: "round", y: "c", dy: off(k), r: 2.5, fill: colorOf(k) }));
  });
  for (const e of ends) {
    marks.push(Plot.text([e], { x: "round", y: "c", dx: 6, dy: e.dy, textAnchor: "start", text: (p) => p.label, fill: C.ink, fontWeight: 600, fontSize: 11, stroke: C.paper, strokeWidth: 3 }));
  }
  if (missing.length) {
    marks.push(Plot.dot(missing.filter((r) => r <= n), { x: (r) => r, y: 0, r: 2, fill: C.paper, stroke: C.ink3, strokeWidth: 1 }));
  }
  marks.push(
    Plot.axisY({ tickSize: 0, tickPadding: 6, ticks: Math.min(max, 8), label: null, tickFormat: (v, i, a) => (i === a.length - 1 ? `${v}개` : v) }),
    Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: narrow ? Array.from({ length: n }, (_, i) => i + 1) : xTicks(n), tickFormat: narrow ? roundTick(true, n) : (r) => r }),
  );
  const svg = plot({
    width, height: H, marginLeft: 30, marginRight: 40, marginTop: mt, marginBottom: mb,
    x: { domain: [0.5, n + 0.5] },
    y: { domain: [0, max + 0.5] },
    marks,
  });
  const xs = svg.scale("x");
  const stops = Array.from({ length: n }, (_, i) => {
    const r = i + 1;
    const name = roundNames[i] ? ` ${roundNames[i]}` : "";
    return {
      px: xs.apply(r), py: H / 2, top: mt, bottom: H - mb,
      head: `${team ? `${team} · ` : ""}${r}라운드${name} 종료`,
      rows: lines.map((d) => {
        const k = drawn.indexOf(d);
        const c = d.s[i];
        const value = c != null ? `${c}개` : miss.has(r) ? "문서 미수집" : "미출전";
        return { value, label: d.full, key: k >= 0 ? { type: "line", color: colorOf(k) } : null };
      }),
      note: miss.has(r)
        ? "이 라운드의 누적 문서를 받지 않았거나 검수 대기다."
        : unk.has(r)
          ? "선언 문서가 없어 대회 시작 전 누적 값이다."
          : allowed != null && lines.some((d) => d.s[i] != null && d.s[i] > allowed)
            ? `허용 ${allowed}개를 넘은 값이 있다.`
            : null,
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "x", label: label || `${team} ${element} 누적 사용 개수` });
  return w;
}

/**
 * rows: [{id(고유), label, code, team, ice: [라운드별 누적 | null], fresh: [투입한 ICE 번호 | null], over: [허용 초과 투입 여부], teamStart}]
 * opts: rounds, missing, allowed, roundNames
 */
export function newIceMatrix(rows, { width, rounds, missing = [], allowed = null, roundNames = [], label } = {}) {
  const narrow = width < 560;
  const n = rounds;
  const miss = new Set(missing);
  const rowH = 24;
  const lab = (d) => (narrow ? d.code || d.label : d.label);
  const ml = Math.min(narrow ? 56 : 170, Math.max(...rows.map((d) => textWidth(lab(d), 13))) + 14);
  const mr = 44;
  const cells = [];
  rows.forEach((d, ri) => {
    for (let i = 0; i < n; i++) {
      const c = d.ice[i];
      cells.push({ row: ri, key: d.id, name: d.label, team: d.team, round: i + 1, c, raced: c != null, fresh: d.fresh[i], over: d.over[i] });
    }
  });
  const H = rows.length * rowH + 34;
  const breaks = rows.filter((d, i) => i > 0 && d.teamStart).map((d) => d.id);
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: 4, marginBottom: 30,
    x: { domain: [0.5, n + 0.5] },
    y: { type: "band", domain: rows.map((d) => d.id), padding: 0 },
    marks: [
      Plot.gridY(rows.map((d) => d.id), { stroke: C.grid, strokeOpacity: 1 }),
      Plot.ruleY(breaks, { y: (d) => d, stroke: C.ink3, strokeWidth: 1, dy: -rowH / 2 }),
      Plot.dot(cells.filter((c) => c.raced && !c.fresh), { x: "round", y: "key", r: 1.6, fill: C.axis }),
      Plot.dot(cells.filter((c) => c.fresh && c.over), { x: "round", y: "key", r: 7.5, fill: "none", stroke: C.ink, strokeWidth: 1.5 }),
      Plot.dot(cells.filter((c) => c.fresh), { x: "round", y: "key", r: 4.5, fill: C.s1, stroke: C.paper, strokeWidth: 2 }),
      Plot.text(rows, { y: "id", frameAnchor: "right", dx: mr - 4, textAnchor: "end", fill: C.ink2, fontVariant: "tabular-nums", text: (d) => { const last = d.ice.filter((x) => x != null).at(-1); return last == null ? "결측" : `${last}개`; } }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 13, label: null, tickFormat: (k) => lab(rows.find((d) => d.id === k)) }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: Array.from({ length: n }, (_, i) => i + 1), tickFormat: roundTick(narrow, n) }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = cells.map((c) => {
    const name = roundNames[c.round - 1] ? ` ${roundNames[c.round - 1]}` : "";
    const value = c.c != null ? `${c.c}개` : miss.has(c.round) ? "문서 미수집" : "미출전";
    let note = null;
    if (c.fresh) note = `이 라운드에 ${c.fresh}번째 ICE를 투입했다.${c.over && allowed != null ? ` 허용 ${allowed}개를 넘었다.` : ""}`;
    else if (miss.has(c.round)) note = "이 라운드의 누적 문서를 받지 않았거나 검수 대기다.";
    return {
      px: xs.apply(c.round), py: ys.apply(c.key) + rowH / 2,
      head: `${c.name}${c.team ? ` (${c.team})` : ""} · ${c.round}라운드${name}`,
      rows: [{ value, label: "ICE 누적", key: c.fresh ? { type: "dot", color: C.s1 } : null }],
      note,
    };
  });
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "grid", cols: n, rowH, label: label || "새 ICE 투입" });
  return w;
}
