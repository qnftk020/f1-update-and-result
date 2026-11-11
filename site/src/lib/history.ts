// 챔피언십 역사 자료(history.json)의 타입과 로더(홈, 드라이버 쪽도 여기서 읽는다). 이 자료를 읽고 시즌 목록(/seasons/)과 팀 목록(/teams/)의 분석 절에 쓸 모양으로 만든다.
// 모든 수치는 history.json에서 온다(Jolpica 결과와 순위, 계보 묶음은 이 사이트의 계보 테이블).
// 계산은 빌드 때만 돈다. 차트 함수(lib/charts/history.js)에 넘기는 자료는 JSON으로 넘길 수 있는 값만 담는다.
import historyJson from '../data/generated/history.json';
import { surname } from './names.ts';

/* ------------------------------------------------------------------ 자료 모양 */

export interface HistPerson {
  id: string;
  name: string;
  pts: number;
}
export interface HistSeason {
  season: number;
  rounds: number;
  d1: HistPerson & { wins: number; led: number; teams: string[]; f1db_pts?: number };
  d2: HistPerson;
  margin: number;
  margin_pct: number;
  c1: (HistPerson & { lineage_id: string | null; wins: number; f1db_pts?: number }) | null;
  c2: (HistPerson & { lineage_id: string | null }) | null;
  c_margin: number | null;
  c_margin_pct: number | null;
  winners: number;
  lead_change: number | null;
  c_lead_change: number | null;
  excluded: HistPerson[];
  c_adjusted: { id: string; name: string; kind: 'excluded' | 'deducted'; pts: number; pos: number | null }[];
}
export interface HistDriverTitles {
  id: string;
  name: string;
  nationality_ko: string;
  first_season: number;
  last_season: number;
  titles: number;
  seasons: number[];
}
export interface HistWinRow {
  id: string;
  name: string;
  nationality_ko: string;
  first_season: number;
  last_season: number;
  wins: number;
  starts: number;
  titles: number;
}
export interface HistConstructorTitles {
  id: string;
  name: string;
  titles: number;
  seasons: number[];
}
export interface HistLineageSeason {
  s: number;
  c: string;
  name: string;
  pos: number | null;
  pts: number | null;
  entered: number;
  wins: number;
  podiums: number;
}
export interface HistLineage {
  lineage_id: string;
  name_ko: string;
  titles: number;
  title_seasons: number[];
  wins: number;
  entered: number;
  podiums: number;
  seasons: HistLineageSeason[];
}
export interface History {
  first_season: number;
  last_season: number;
  constructor_first_season: number;
  seasons: HistSeason[];
  driver_titles: HistDriverTitles[];
  wins: HistWinRow[];
  constructor_titles: HistConstructorTitles[];
  lineages: HistLineage[];
}

export const history = historyJson as unknown as History;

/* ------------------------------------------------------------------ 작은 도우미 */

/** "마라넬로 (페라리)" -> "마라넬로" */
export const lineageShortKo = (nameKo: string) => nameKo.replace(/\s*\(.*\)\s*$/, '');
/** 좁은 칸의 짧은 이름(lib/names.ts). 툴팁과 표에는 전체 이름을 쓴다 */
export { surname };

export function median(xs: number[]): number {
  const a = [...xs].sort((p, q) => p - q);
  const m = Math.floor(a.length / 2);
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}
/** 소수 둘째 자리까지, 정수면 정수로 */
export const r2 = (x: number) => Math.round(x * 100) / 100;

const lineageById = new Map(history.lineages.map((l) => [l.lineage_id, l]));
export const lineageName = (id: string | null | undefined) => (id ? lineageById.get(id)?.name_ko ?? id : null);

/**
 * 시즌과 팀 이름으로 계보를 찾는다. 계보 시즌 행의 name은 그 시즌 컨스트럭터 이름(Jolpica)이고
 * 드라이버 1위의 teams도 같은 이름이라 이름으로 맞춘다. 2025 그리드 10개 계보 밖이면 null이다.
 */
export function lineageOf(season: number, teamNames: string[]): string | null {
  for (const name of teamNames) {
    for (const l of history.lineages) {
      if (l.seasons.some((x) => x.s === season && x.name === name)) return l.lineage_id;
    }
  }
  return null;
}

/* ------------------------------------------------------------------ 계보 색 */

/**
 * 계보 색: 컨스트럭터 타이틀이 많은 순서(동률이면 우승 수)로 앞 세 계보에 범주 1~3(블루, 핑크, 올리브)을 준다.
 * 나머지 2025 계보는 맥락 회색, 10개 계보 밖의 팀(Lotus, Brabham, Cooper 등)은 빈 칸이다.
 */
export const topLineages = [...history.lineages]
  .filter((l) => l.titles > 0)
  .sort((a, b) => b.titles - a.titles || b.wins - a.wins)
  .slice(0, 3)
  .map((l) => l.lineage_id);
export type LinCat = 's1' | 's2' | 's3' | 'ctx' | 'out';
export function linCat(lineageId: string | null): LinCat {
  if (!lineageId) return 'out';
  const i = topLineages.indexOf(lineageId);
  return i >= 0 ? (['s1', 's2', 's3'] as const)[i] : 'ctx';
}
export const linCats = [
  ...topLineages.map((id, i) => ({ key: (['s1', 's2', 's3'] as const)[i], label: lineageName(id) as string })),
  { key: 'ctx' as const, label: '그 밖의 2025 계보' },
  { key: 'out' as const, label: '2025 그리드 밖의 팀' },
];

/* ------------------------------------------------------------------ 시즌 목록: 챔피언십 추이 */

const S = history.seasons;
const C_FROM = history.constructor_first_season;
export const seasonsWithC = S.filter((s) => s.c1);

export interface BarRow {
  s: number;
  v: number;
  hl?: boolean;
  head: string;
  tip: [string, string][];
  note?: string;
}
export interface BarSeries {
  unit: string;
  yLabel: string;
  median?: number;
  rows: BarRow[];
  marks: { s: number; text: string }[];
}

const pctText = (x: number) => `${x.toFixed(x < 10 ? 2 : 1)}%`;
const ptsText = (x: number) => `${r2(x)}점`;

/** 1위와 2위의 점수 차(1위 점수 대비 %). kind d는 드라이버, c는 컨스트럭터(1958-). */
export function marginSeries(kind: 'd' | 'c'): BarSeries {
  const list = kind === 'd' ? S : seasonsWithC;
  const val = (s: HistSeason) => (kind === 'd' ? s.margin_pct : (s.c_margin_pct as number));
  const lo = list.reduce((a, b) => (val(b) < val(a) ? b : a));
  const hi = list.reduce((a, b) => (val(b) > val(a) ? b : a));
  const rows: BarRow[] = list.map((s) => {
    const a = kind === 'd' ? s.d1 : (s.c1 as HistPerson);
    const z = kind === 'd' ? s.d2 : (s.c2 as HistPerson);
    const notes: string[] = [];
    if (kind === 'd' && s.excluded.length) notes.push(`순위 제외: ${s.excluded.map((e) => e.name).join(', ')}. 2위는 순위표의 다음 드라이버다.`);
    if (kind === 'c' && s.c_adjusted.length)
      notes.push(s.c_adjusted.map((c) => (c.kind === 'excluded' ? `순위 제외: ${c.name}.` : `감점: ${c.name} (${c.pos}위).`)).join(' '));
    return {
      s: s.season,
      v: val(s),
      hl: s === lo || s === hi,
      head: `${s.season}년`,
      tip: [
        [ptsText(a.pts), `1위 ${a.name}`],
        [ptsText(z.pts), `2위 ${z.name}`],
        [`${ptsText(kind === 'd' ? s.margin : (s.c_margin as number))} (${pctText(val(s))})`, '점수 차'],
      ],
      note: notes.join(' ') || undefined,
    };
  });
  const who = (s: HistSeason) => (kind === 'd' ? surname(s.d1.name) : (s.c1 as HistPerson).name);
  return {
    unit: '%',
    yLabel: '1위 점수 대비 (%)',
    median: r2(median(list.map(val))),
    rows,
    marks: [
      { s: lo.season, text: `${lo.season} ${who(lo)} ${pctText(val(lo))}` },
      { s: hi.season, text: `${hi.season} ${who(hi)} ${pctText(val(hi))}` },
    ],
  };
}

export const marginD = marginSeries('d');
export const marginC = marginSeries('c');

/** 시즌별 서로 다른 우승자 수 */
export function winnersSeries(): BarSeries {
  const max = Math.max(...S.map((s) => s.winners));
  return {
    unit: '명',
    yLabel: '우승자 (명)',
    median: median(S.map((s) => s.winners)),
    rows: S.map((s) => ({
      s: s.season,
      v: s.winners,
      hl: s.winners === max,
      head: `${s.season}년`,
      tip: [
        [`${s.winners}명`, '서로 다른 우승자'],
        [`${s.rounds}개`, '대회'],
        [`${s.d1.wins}승`, `1위 ${s.d1.name}의 우승`],
      ],
    })),
    marks: S.filter((s) => s.winners === max).map((s) => ({ s: s.season, text: `${s.season} ${s.winners}명` })),
  };
}

/** 최종 1위가 드라이버 순위 선두였던 라운드의 비율 */
export function ledSeries(): BarSeries {
  const share = (s: HistSeason) => r2((s.d1.led / s.rounds) * 100);
  const last = S.filter((s) => s.d1.led === 1);
  return {
    unit: '%',
    yLabel: '전체 라운드 대비 (%)',
    median: r2(median(S.map(share))),
    rows: S.map((s) => ({
      s: s.season,
      v: share(s),
      hl: s.d1.led === 1,
      head: `${s.season}년 ${s.d1.name}`,
      tip: [
        [`${s.d1.led}/${s.rounds}라운드`, '선두였던 라운드'],
        [pctText(share(s)), '비율'],
      ],
      note: s.excluded.length
        ? `시즌 뒤 순위에서 제외된 ${s.excluded.map((e) => e.name).join(', ')}의 그 시점 점수를 넣어 센 값이다.`
        : s.d1.led === 1
          ? '마지막 라운드가 끝난 뒤에 처음 선두가 되었다.'
          : s.d1.led === s.rounds
            ? '첫 라운드부터 끝까지 선두였다.'
            : undefined,
    })),
    marks: last.map((s) => ({ s: s.season, text: `${s.season} ${surname(s.d1.name)}` })),
  };
}

/* ------------------------------------------------------------------ 시즌 목록: 드라이버 1위와 컨스트럭터 1위 */

export interface ChampCell {
  s: number;
  d: { name: string; short: string; teams: string; lin: string | null; cat: LinCat; pts: number };
  c: { name: string; lin: string | null; cat: LinCat; pts: number } | null;
  split: boolean;
}
export const champCells: ChampCell[] = S.map((s) => {
  const dl = s.c1 && s.d1.teams.includes(s.c1.name) ? s.c1.lineage_id : lineageOf(s.season, s.d1.teams);
  return {
    s: s.season,
    d: { name: s.d1.name, short: surname(s.d1.name), teams: s.d1.teams.join(', '), lin: lineageName(dl), cat: linCat(dl), pts: s.d1.pts },
    c: s.c1 ? { name: s.c1.name, lin: lineageName(s.c1.lineage_id), cat: linCat(s.c1.lineage_id), pts: s.c1.pts } : null,
    split: Boolean(s.c1 && !s.d1.teams.includes(s.c1.name)),
  };
});
export const splitSeasons = champCells.filter((c) => c.split);

/* ------------------------------------------------------------------ 타이틀 순위 */

export interface TitleRow {
  key: string;
  name: string;
  short: string;
  n: number;
  seasons: number[];
  sub: string;
}
// 성이 겹치면(Hill 셋, Rosberg 둘) 이름 첫 글자를 붙인다: "G. Hill"
const dupSurname = (n: string) => history.driver_titles.filter((x) => surname(x.name) === surname(n)).length > 1;
const shortName = (n: string) => (dupSurname(n) ? `${n.trim()[0]}. ${surname(n)}` : surname(n));
export const driverTitleRows: TitleRow[] = history.driver_titles.map((d) => ({
  key: d.id,
  name: d.name,
  short: shortName(d.name),
  n: d.titles,
  seasons: d.seasons,
  sub: `${d.nationality_ko} · ${d.first_season}-${d.last_season} 출전`,
}));
export const constructorTitleRows: TitleRow[] = history.constructor_titles.map((c) => ({
  key: c.id,
  name: c.name,
  short: c.name,
  n: c.titles,
  seasons: c.seasons,
  sub: `컨스트럭터 ID ${c.id}`,
}));
export const lineageTitleRows: TitleRow[] = [...history.lineages]
  .filter((l) => l.titles > 0)
  .sort((a, b) => b.titles - a.titles || b.wins - a.wins)
  .map((l) => ({
    key: l.lineage_id,
    name: l.name_ko,
    short: lineageShortKo(l.name_ko),
    n: l.titles,
    seasons: l.title_seasons,
    sub: `이 계보의 시즌별 이름: ${[...new Set(l.seasons.filter((x) => l.title_seasons.includes(x.s) && x.pos === 1).map((x) => x.name))].join(', ')}`,
  }));
export const lineagesWithoutTitle = history.lineages.filter((l) => l.titles === 0);

/* ------------------------------------------------------------------ 팀 목록: 계보별 최종 순위 */

export interface HeatCell {
  s: number;
  pos: number | null;
  names: string;
  pts: number | null;
  wins: number;
  entered: number;
  note?: string;
}
export interface HeatRow {
  id: string;
  name: string;
  short: string;
  titles: number;
  cells: HeatCell[];
}

/** 한 시즌에 컨스트럭터가 둘 이상인 계보(1966-1970 워킹, 2006 실버스톤)는 가장 높은 순위를 칸에 쓰고 이름을 모두 적는다. */
export function heatRows(order: string[]): HeatRow[] {
  return order.map((id) => {
    const l = lineageById.get(id) as HistLineage;
    const by = new Map<number, HistLineageSeason[]>();
    for (const x of l.seasons) {
      if (x.s < C_FROM) continue;
      by.set(x.s, [...(by.get(x.s) ?? []), x]);
    }
    const cells: HeatCell[] = [...by.entries()].map(([s, xs]) => {
      const ranked = xs.filter((x) => x.pos != null).sort((a, b) => (a.pos as number) - (b.pos as number));
      const best = ranked[0] ?? xs[0];
      const adj = S.find((q) => q.season === s)?.c_adjusted.find((c) => xs.some((x) => x.c === c.id));
      let note: string | undefined;
      if (adj?.kind === 'excluded') note = `컨스트럭터 순위 제외: ${adj.name}.`;
      else if (adj?.kind === 'deducted') note = `감점: ${adj.name} (${adj.pos}위).`;
      else if (best.pos == null) note = 'Jolpica 컨스트럭터 순위표에 순위가 없다.';
      if (xs.length > 1) note = [`이 시즌 이름 ${xs.length}개 가운데 가장 높은 순위를 칸에 썼다.`, note].filter(Boolean).join(' ');
      return {
        s,
        pos: best.pos,
        names: xs.map((x) => x.name).join(', '),
        pts: best.pts,
        wins: xs.reduce((a, x) => a + x.wins, 0),
        entered: Math.max(...xs.map((x) => x.entered)),
        note,
      };
    });
    return { id, name: l.name_ko, short: lineageShortKo(l.name_ko), titles: l.titles, cells };
  });
}

/** 1위가 이어진 가장 긴 구간: {lineage, from, to, n} */
export function longestTitleRun() {
  let best = { id: '', from: 0, to: 0, n: 0 };
  for (const l of history.lineages) {
    const ys = [...l.title_seasons].sort((a, b) => a - b);
    let from = ys[0];
    for (let i = 0; i < ys.length; i++) {
      if (i > 0 && ys[i] !== ys[i - 1] + 1) from = ys[i];
      const n = ys[i] - from + 1;
      if (n > best.n) best = { id: l.lineage_id, from, to: ys[i], n };
    }
  }
  return { ...best, name: lineageName(best.id) as string };
}
