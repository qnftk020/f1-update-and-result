// F1 업그레이드와 성능 추이: 체코지수 차트 (/chekoji/)
// 자료는 빌드 때 pages/chekoji.astro가 race_score.json과 시즌 자료로 만든다.
import * as Plot from "@observablehq/plot";
import { C, frameOf, plot, readout, textWidth } from "./core.js";

/**
 * data: {max, seasons: [{season, median, races: [{key, name, short, round, score}]}]}
 * 행이 시즌, 가로가 점수다. 점은 체코지수 빨강(--chekoji-red)이다. 시즌마다 중앙값에 세로 눈금을 두고 가장 높은 대회에 이름을 붙인다.
 */
export function scoreStrip(input, { width, label = "시즌별 체코지수 분포" }) {
  const rows = input.seasons;
  const narrow = width < 560;
  const ml = 44;
  const mr = 12;
  const rowH = narrow ? 40 : 44;
  const mt = 18;
  const mb = 26;
  const H = rows.length * rowH + mt + mb;
  const xMax = Math.max(10, Math.ceil(input.max / 10) * 10);
  const dots = rows.flatMap((s) => s.races.map((r) => ({ ...r, season: String(s.season) })));
  const tops = rows.map((s) => ({ ...s.races.reduce((a, b) => (b.score > a.score ? b : a)), season: String(s.season) }));
  const rad = narrow ? 4 : 5;
  const svg = plot({
    width, height: H, marginLeft: ml, marginRight: mr, marginTop: mt, marginBottom: mb,
    x: { domain: [0, xMax] },
    y: { type: "band", domain: rows.map((s) => String(s.season)), padding: 0 },
    marks: [
      Plot.gridX({ stroke: C.grid, strokeOpacity: 1, ticks: xMax / 10 }),
      Plot.tickX(rows, { x: "median", y: (s) => String(s.season), stroke: C.ink, strokeWidth: 2, inset: rowH * 0.22 }),
      Plot.dot(dots, { x: "score", y: "season", r: rad, fill: C.cz, fillOpacity: 0.85, stroke: C.paper, strokeWidth: 1 }),
      Plot.text(tops, {
        x: "score", y: "season", dy: -(rad + 7), fill: C.ink, fontSize: 11.5,
        textAnchor: "end", dx: rad,
        text: (d) => (textWidth(d.short, 11.5) + 8 < (width - ml - mr) * (d.score / xMax) ? d.short : ""),
      }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fill: C.ink, fontSize: 12, label: null }),
      Plot.axisX({ tickSize: 0, tickPadding: 6, label: null, ticks: narrow ? xMax / 20 : xMax / 10 }),
    ],
  });
  const xs = svg.scale("x");
  const ys = svg.scale("y");
  const stops = rows.flatMap((s) =>
    [...s.races].sort((a, b) => a.score - b.score).map((r) => ({
      px: xs.apply(r.score),
      py: ys.apply(String(s.season)) + rowH / 2,
      head: `${s.season} ${r.name}`,
      rows: [{ value: r.score.toFixed(2), label: "체코지수", key: { type: "dot", color: C.cz } }],
      note: `R${r.round} · ${s.season} 시즌 중앙값 ${s.median.toFixed(2)}`,
    })),
  );
  const w = frameOf(svg);
  readout(w, svg, stops, { axis: "grid", label, rowH, cols: stops.length });
  return w;
}
