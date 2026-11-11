// F1 업그레이드와 성능 추이: 차트 모듈의 공통 부분 (design/final/charts.js에서 옮겼다)
// 토큰, 형식, DOM 조각(배지, 아이콘, 범주 기호, 표 보기), 그리기 틀(mount, 대체, 차트/표 전환),
// 읽기 층(툴팁, 십자선, 키보드, 낭독), 라벨 자리 고르기, 범례. 차트 함수는 charts.js에 있다.
// 데이터에서 온 글자는 textContent로만 넣는다. 브라우저 전용이다(document를 쓴다). 서버에서 부르지 않는다.
import * as Plot from "@observablehq/plot";
import { MINUS, formatLapTime, n0, num, pct } from "../format.ts";
import { ICONS } from "../markup.ts";

/* ------------------------------------------------------------------ 토큰과 형식 */

const v = (name) => `var(--${name})`;
export const C = {
  s1: v("s1"), s2: v("s2"), s3: v("s3"), ctx: v("ctx"), band: v("band"),
  ink: v("ink"), ink2: v("ink-2"), ink3: v("ink-3"), paper: v("paper"), paper2: v("paper-2"), paper3: v("paper-3"),
  grid: v("grid"), axis: v("axis"), warn: v("warn"), warnInk: v("warn-ink"),
};
export const SLOTS = [C.s1, C.s2, C.s3];

export const CATS = {
  performance: { label: "성능", color: C.s1, symbol: "square", hollow: false },
  circuit_specific: { label: "서킷 대응", color: C.s2, symbol: "square", hollow: true },
  reliability: { label: "신뢰성", color: C.s3, symbol: "triangle", hollow: false },
  other: { label: "기타", color: C.ctx, symbol: "times", hollow: true },
};
export const CAT_ORDER = ["performance", "circuit_specific", "reliability", "other"];

export { MINUS, num, pct };
/** 정수와 천 단위 쉼표. 값이 없으면 "결측" */
export const int = n0;
/** 밀리초를 "1:22.207"로 */
export const lap = (ms) => formatLapTime(ms);
/** 좁은 화면의 라운드 눈금: 1, 5, 9 ... 그리고 마지막 라운드(앞 눈금과 3칸 이상 떨어질 때만) */
export const roundTick = (narrow, n) => (r) => (!narrow || r % 4 === 1 || (r === n && (n - 1) % 4 >= 2) ? r : "");

/* ------------------------------------------------------------------ DOM 조각 */

export function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}
export const SVGNS = "http://www.w3.org/2000/svg";

/** 범주 기호: 성능 ■, 서킷 대응 □, 신뢰성 ▲, 기타 ×. 차트, 표, 필터에서 같은 모양이다. */
export function catGlyph(cat) {
  const s = el("span", "rk");
  s.dataset.cat = cat;
  s.setAttribute("aria-hidden", "true");
  return s;
}

export function icon(name, cls = "ic") {
  const s = document.createElementNS(SVGNS, "svg");
  s.setAttribute("viewBox", "0 0 16 16");
  s.setAttribute("class", cls);
  s.setAttribute("aria-hidden", "true");
  s.innerHTML = ICONS[name]; // 고정 문자열만 넣는다
  return s;
}
export function badge(kind, text) {
  const b = el("span", `badge badge-${kind}`);
  b.append(icon(kind), el("span", null, text));
  return b;
}

/** 표 보기 쌍둥이. columns: [{key, label, num, fmt}], rows: 객체 배열. */
export function tableTwin({ caption, columns, rows, rowClass }) {
  const wrap = el("div", "tbl-wrap");
  wrap.setAttribute("role", "region");
  wrap.setAttribute("tabindex", "0");
  wrap.setAttribute("aria-label", caption);
  const t = el("table", "dt dt-compact");
  const cap = el("caption", "sr-only", caption);
  const thead = el("thead");
  const hr = el("tr");
  for (const c of columns) {
    const th = el("th", c.num ? "num" : null, c.label);
    th.scope = "col";
    hr.append(th);
  }
  thead.append(hr);
  const tb = el("tbody");
  for (const r of rows) {
    const tr = el("tr", rowClass ? rowClass(r) : null);
    for (const c of columns) {
      const td = el("td", c.num ? "num" : null);
      const val = c.fmt ? c.fmt(r[c.key], r) : r[c.key];
      if (val instanceof Node) td.append(val);
      else td.textContent = val ?? "";
      tr.append(td);
    }
    tb.append(tr);
  }
  t.append(cap, thead, tb);
  wrap.append(t);
  return wrap;
}

/* ------------------------------------------------------------------ 그리기와 틀 */

export const STYLE = { fontFamily: "inherit", fontSize: "12px", color: C.ink3, background: "transparent", overflow: "visible" };

export function plot(o) {
  const node = Plot.plot({ style: STYLE, ...o });
  // Plot은 마크 묶음 <g>에 aria-label("rule", "line" 등)을 붙이는데 role이 없어 접근성 검사에 걸린다.
  // 그림의 접근 가능한 이름은 감싸개(role=group, aria-label)와 표 보기가 맡으므로 지운다.
  node.querySelectorAll("g[aria-label]").forEach((g) => g.removeAttribute("aria-label"));
  return node;
}

/**
 * 너비를 재서 그리고, 너비가 바뀌면 다시 그린다.
 * 다시 그릴 때 초점이 있던 그림(slot 안 .plot의 순번)과 읽던 자리(data-idx)를 새 그림에 되돌린다.
 * 그리다가 오류가 나면 그 그림 하나만 대체 문구와 표 보기로 되돌린다.
 */
export function mount(slot, fn, data, opts = {}) {
  let w = 0;
  let failed = false;
  const draw = (force) => {
    if (failed) return;
    const nw = Math.round(slot.clientWidth);
    if (!nw || (!force && Math.abs(nw - w) < 2)) return;
    w = nw;
    const plots = [...slot.querySelectorAll(".plot")];
    const fi = plots.indexOf(document.activeElement);
    const fidx = fi >= 0 ? plots[fi].dataset.idx : undefined;
    let node;
    try {
      node = fn(data, { ...opts, width: nw });
    } catch (err) {
      failed = true;
      figureFallback(slot, err);
      return;
    }
    slot.replaceChildren(node);
    if (fi >= 0) {
      const np = slot.querySelectorAll(".plot")[fi] || slot.querySelector(".plot");
      if (np) {
        if (fidx !== undefined) np.dataset.idx = fidx;
        np.focus();
      }
    }
  };
  new ResizeObserver(() => draw()).observe(slot);
  draw();
  return { redraw: (d, o) => { data = d ?? data; Object.assign(opts, o || {}); draw(true); } };
}

/** 그림 하나의 실패 처리: 차트 자리에 안내를 적고, 그 그림의 표 보기를 보이게 하고, 전환 단추와 범례를 숨긴다. */
export function figureFallback(slot, err) {
  const fig = slot.closest("figure.fig");
  slot.replaceChildren(el("p", "fig-fallback", "차트를 불러오지 못해 표로 보여 준다."));
  if (fig) {
    fig.classList.add("no-plot");
    const twin = fig.querySelector(".twin");
    if (twin) twin.hidden = false;
    slot.hidden = false;
  }
  if (window.console) console.warn(err);
}

/** 차트 틀: 차트/표 전환 단추를 잇고 표를 숨긴다. 스크립트가 없으면 표가 그대로 보인다. */
export function initFigure(fig) {
  const twin = fig.querySelector(".twin");
  const viz = fig.querySelector(".viz");
  const btns = fig.querySelectorAll("[data-view]");
  const set = (view) => {
    if (viz) viz.hidden = view !== "chart";
    if (twin) twin.hidden = view !== "table";
    btns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === view)));
  };
  btns.forEach((b) => b.addEventListener("click", () => set(b.dataset.view)));
  set("chart");
  fig.classList.add("is-live");
  return set;
}
export function initFigures(root = document) {
  root.querySelectorAll("figure.fig").forEach(initFigure);
}

/* ------------------------------------------------------------------ 읽기 층 (hover, 키보드, 낭독) */

/**
 * stops: [{px, py, head, rows: [{value, label, key}], note, onSelect}]
 * axis "x": 세로 십자선이 가장 가까운 x로 붙는다. axis "y": 가장 가까운 행에 옅은 띠가 깔린다.
 * axis "grid": 행 × 열 행렬(cols 필요, stops는 행 우선 순서). ←/→는 같은 행의 열, ↑/↓는 같은 열의 행, Home/End는 그 행의 처음과 끝.
 * 읽던 자리는 wrap.dataset.idx에 남아 다시 그린 뒤에도 이어진다(mount 참고).
 */
export function readout(wrap, svg, stops, { axis = "x", label, onSelect, band = 0, rowH = 24, cols = 1 } = {}) {
  wrap.classList.add("plot");
  wrap.tabIndex = 0;
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-roledescription", "차트");
  if (label) wrap.setAttribute("aria-label", `${label}. 화살표 키로 값을 차례로 읽는다.`);
  const tip = el("div", "tip");
  tip.hidden = true;
  const cross = el("div", axis === "x" ? "cross cross-x" : "cross cross-y");
  cross.hidden = true;
  const live = el("p", "sr-only");
  live.setAttribute("aria-live", "polite");
  wrap.append(cross, tip, live);
  let idx = -1;
  const grid = axis === "grid";

  const render = (s) => {
    tip.replaceChildren();
    tip.append(el("p", "tip-head", s.head));
    for (const r of s.rows || []) {
      const row = el("p", "tip-row");
      if (r.key) {
        const k = el("span", `key key-${r.key.type || "line"}`);
        if (r.key.cat) k.dataset.cat = r.key.cat;
        else k.style.setProperty("--k", r.key.color);
        row.append(k);
      }
      row.append(el("b", "tip-val", r.value), el("span", "tip-lab", r.label));
      tip.append(row);
    }
    if (s.note) tip.append(el("p", "tip-note", s.note));
  };
  const scale = () => {
    const r = svg.getBoundingClientRect();
    return { r, k: r.width / (svg.width?.baseVal?.value || r.width) };
  };
  const show = (i, announce) => {
    if (i < 0 || i >= stops.length) return;
    idx = i;
    wrap.dataset.idx = String(i);
    const s = stops[i];
    render(s);
    const { r, k } = scale();
    const wr = wrap.getBoundingClientRect();
    const ox = r.left - wr.left;
    const oy = r.top - wr.top;
    tip.hidden = false;
    cross.hidden = false;
    if (axis === "x") {
      cross.style.left = `${ox + s.px * k}px`;
      cross.style.top = `${oy + (s.top ?? 0) * k}px`;
      cross.style.height = `${(s.bottom ?? r.height / k) * k - (s.top ?? 0) * k}px`;
    } else {
      cross.style.top = `${oy + (s.py - rowH / 2) * k}px`;
      cross.style.height = `${rowH * k}px`;
      cross.style.left = `${ox + band * k}px`;
      cross.style.width = `${r.width - band * k}px`;
    }
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    let x = ox + (s.px ?? r.width / k / 2) * k + 14;
    if (x + tw > wr.width) x = ox + (s.px ?? 0) * k - tw - 14;
    if (x < 0) x = Math.max(0, wr.width - tw);
    let y = oy + (s.py ?? 0) * k - th / 2;
    y = Math.max(0, Math.min(y, wr.height - th));
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
    if (announce) {
      live.textContent = [s.head, ...(s.rows || []).map((r) => `${r.label} ${r.value}`), s.note].filter(Boolean).join(". ");
    }
  };
  const hide = () => {
    tip.hidden = true;
    cross.hidden = true;
  };
  const nearest = (e) => {
    const { r, k } = scale();
    const ex = (e.clientX - r.left) / k;
    const ey = (e.clientY - r.top) / k;
    let best = -1;
    let bd = Infinity;
    stops.forEach((s, i) => {
      const d = grid ? Math.hypot(s.px - ex, s.py - ey) : Math.abs((axis === "x" ? s.px : s.py) - (axis === "x" ? ex : ey));
      if (d < bd) { bd = d; best = i; }
    });
    return best;
  };
  svg.addEventListener("pointermove", (e) => show(nearest(e), false));
  // 터치: 누르면 그 자리 값을 띄우고, 가로로 끌면 따라간다(세로 끌기는 페이지 스크롤로 남긴다).
  // 손을 떼도 툴팁을 남기고, 그림 밖을 누르면 닫는다.
  svg.style.touchAction = "pan-y";
  svg.addEventListener("pointerdown", (e) => { if (e.pointerType !== "mouse") show(nearest(e), false); });
  svg.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && document.activeElement !== wrap) hide(); });
  const outside = (e) => {
    if (!wrap.isConnected) { document.removeEventListener("pointerdown", outside); return; } // 다시 그려 떨어져 나간 그림
    if (e.pointerType !== "mouse" && !wrap.contains(e.target) && document.activeElement !== wrap) hide();
  };
  document.addEventListener("pointerdown", outside, { passive: true });
  svg.addEventListener("click", (e) => {
    const i = nearest(e);
    if (onSelect && stops[i]) onSelect(stops[i], i);
  });
  wrap.addEventListener("focus", () => {
    const saved = Number(wrap.dataset.idx);
    show(idx >= 0 ? idx : Number.isInteger(saved) && saved >= 0 && saved < stops.length ? saved : 0, true);
  });
  wrap.addEventListener("blur", hide);
  wrap.addEventListener("keydown", (e) => {
    const cur = Math.max(0, idx);
    if (grid) {
      const row = Math.floor(cur / cols);
      const col = cur % cols;
      const rowsN = Math.ceil(stops.length / cols);
      const to = {
        ArrowRight: row * cols + Math.min(cols - 1, col + 1), ArrowLeft: row * cols + Math.max(0, col - 1),
        ArrowDown: Math.min(rowsN - 1, row + 1) * cols + col, ArrowUp: Math.max(0, row - 1) * cols + col,
        Home: row * cols, End: row * cols + cols - 1,
      }[e.key];
      if (to !== undefined) { e.preventDefault(); show(Math.min(stops.length - 1, to), true); return; }
    }
    const next = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (next) { e.preventDefault(); show(Math.max(0, Math.min(stops.length - 1, cur + next)), true); }
    else if (e.key === "Home") { e.preventDefault(); show(0, true); }
    else if (e.key === "End") { e.preventDefault(); show(stops.length - 1, true); }
    else if (e.key === "Escape") hide();
    else if (e.key === "Enter" && onSelect && stops[idx]) { e.preventDefault(); onSelect(stops[idx], idx); }
  });
  if (onSelect) svg.style.cursor = "pointer";
}

export function frameOf(svg, children) {
  const wrap = el("div");
  wrap.append(svg, ...(children || []));
  return wrap;
}

/** 축 아래 주석 띠 (괄호선). segments: [{from, to, text}] (x 값, 양 끝 포함) */
export function bracketStrip(xs, segments, marginLeft) {
  const strip = el("div", "bracket-strip");
  for (const s of segments) {
    const x1 = xs.apply(s.from) - (s.pad ?? 0);
    const x2 = xs.apply(s.to) + (s.pad ?? 0);
    const b = el("div", "bracket");
    b.style.left = `${x1}px`;
    b.style.width = `${Math.max(8, x2 - x1)}px`;
    b.append(el("span", null, s.text));
    strip.append(b);
  }
  strip.style.setProperty("--ml", `${marginLeft}px`);
  return strip;
}

/* 같은 값이 이어지는 구간 묶기 (우천 띠, 문서 없는 대회) */
export function runs(list, test) {
  const out = [];
  let cur = null;
  for (const d of list) {
    if (test(d)) {
      if (cur && d.round === cur.to + 1) cur.to = d.round;
      else { cur = { from: d.round, to: d.round }; out.push(cur); }
    } else cur = null;
  }
  return out;
}

export const textWidth = (s, px = 12) => [...String(s)].reduce((w, ch) => w + (/[ㄱ-힝]/.test(ch) ? px * 0.95 : /[A-Z0-9]/.test(ch) ? px * 0.64 : px * 0.55), 0);

/* 픽셀 좌표 (Plot과 같은 선형 눈금). reverse면 정의역의 작은 값이 위다. */
export const linX = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
export const box = (x0, y0, x1, y1) => ({ x0, y0, x1, y1 });
export const hit = (a, b) => !(a.x1 <= b.x0 || a.x0 >= b.x1 || a.y1 <= b.y0 || a.y0 >= b.y1);

/**
 * 직접 라벨의 자리를 고른다. 후보 자리(옆, 옆 위, 옆 아래를 양쪽으로) 가운데 다른 표식, 이미 놓은 라벨,
 * 그림 경계와 겹치지 않는 첫 자리를 돌려준다. 맞는 자리가 없으면 null이고, 그 값은 툴팁과 표 보기에 맡긴다.
 */
export function placeLabel({ x, y, texts, obstacles = [], placed = [], bounds, size = 12, preferLeft = false }) {
  const h = size + 4;
  const right = [{ dx: 9, dy: 0, a: "start" }, { dx: 9, dy: -13, a: "start" }, { dx: 9, dy: 13, a: "start" }];
  const left = [{ dx: -9, dy: 0, a: "end" }, { dx: -9, dy: -13, a: "end" }, { dx: -9, dy: 13, a: "end" }];
  const cands = preferLeft ? [...left, ...right] : [...right, ...left];
  // 긴 글(라운드와 대회 이름 + 값)이 들어갈 자리가 없으면 값만 적은 짧은 글로 다시 찾는다
  for (const text of texts) {
    const w = textWidth(text, size) + 4;
    for (const c of cands) {
      const x0 = c.a === "start" ? x + c.dx : x + c.dx - w;
      const b = box(x0, y + c.dy - h / 2, x0 + w, y + c.dy + h / 2);
      if (b.x0 < bounds.x0 || b.x1 > bounds.x1 || b.y0 < bounds.y0 || b.y1 > bounds.y1) continue;
      if (obstacles.some((o) => hit(b, o)) || placed.some((o) => hit(b, o))) continue;
      placed.push(b);
      return { dx: c.dx, dy: c.dy, textAnchor: c.a, text };
    }
  }
  return null;
}
/** 점 표식의 충돌 상자 (반지름 + 고리) */
export const dotBox = (x, y, r = 5) => box(x - r, y - r, x + r, y + r);

/** 우천 띠와 문서 없는 띠의 양옆 선: 띠 면이 종이와 대비가 낮아 1px 기준선 색 선으로 경계를 준다. */
export function bandEdges(runsList, { y1, y2 } = {}) {
  const xs = runsList.flatMap((r) => [r.from - 0.5, r.to + 0.5]);
  return Plot.ruleX(xs, { x: (d) => d, y1, y2, stroke: C.axis, strokeWidth: 1 });
}

/* ------------------------------------------------------------------ 범례 */

/** items: [{type: line|dot|ring|rect|band|tri|glyph|wet|ref|nodoc|zero|hollow|review, color, cat, label}]. color는 C.s1 같은 CSS 값 */
export function legend(items) {
  const ul = el("ul", "legend");
  for (const it of items) {
    const li = el("li");
    const k = el("span", `key key-${it.type}`);
    if (it.cat) k.dataset.cat = it.cat;
    if (it.color) k.style.setProperty("--k", it.color);
    if (it.type === "review") k.append(icon("review"));
    k.setAttribute("aria-hidden", "true");
    li.append(k, el("span", null, it.label));
    ul.append(li);
  }
  return ul;
}
