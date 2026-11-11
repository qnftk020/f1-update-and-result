// 홈 부문별 요약의 자료와 계산. 빌드 때만 돈다(드라이버 목록 drivers.json은 브라우저로 보내지 않는다).
// history.json, drivers.json은 pipeline/site_drivers.py가 만든다. history.json 타입은 lib/history.ts에 있다.
// 모든 수치는 생성 JSON에서 센다. 화면에 올리는 계산은 합계, 순위, 비율뿐이다.
import driversJson from '../../data/generated/drivers.json';
import { history } from '../../lib/history.ts';
import { competitionRanks } from '../../lib/rank.ts';
import { getSeason, home, labels, meta, teamSummaryById, teams, upgrades } from '../../lib/data.ts';
import type { ReasonCategory, Season } from '../../lib/types.ts';
import { engines } from '../engines/engines-data.ts';
import { regulations, type RegComparison, type RegDocument, type Section } from '../regulations/reg-data.ts';

// ---------------------------------------------------------------- 타입

// history.json 타입과 로더는 lib/history.ts 한 곳에 둔다.
export type { HistPerson, HistSeason, History } from '../../lib/history.ts';

export interface DriverListRow {
  id: string;
  name: string;
  wins: number;
  titles: number;
  podiums: number;
  starts: number;
  in_2025: boolean;
  indy_only: boolean;
}

export { history };
export const driverList = driversJson as unknown as DriverListRow[];

// ---------------------------------------------------------------- 머리

export const latestSeason: Season = getSeason(meta.last_season);

export const counts = {
  seasons: meta.counts.seasons,
  races: meta.counts.races,
  drivers: driverList.length,
  winners: driverList.filter((d) => d.wins > 0).length,
  champions: history.driver_titles.length,
  entrants2025: driverList.filter((d) => d.in_2025).length,
  upgradeItems: meta.counts.upgrade_items,
  upgradeDocs: meta.counts.upgrade_documents,
};

// ---------------------------------------------------------------- 연도별

/** 고르기와 차트에 싣는 시즌 요약(브라우저로 간다). 이름은 원자료 그대로, 팀 페이지 연결용 계보 ID를 붙인다 */
export const seasonCards = history.seasons.map((s) => ({
  s: s.season,
  r: s.rounds,
  w: s.winners,
  lc: s.lead_change,
  d1: { id: s.d1.id, n: s.d1.name, p: s.d1.pts, w: s.d1.wins, t: s.d1.teams, f: s.d1.f1db_pts ?? null },
  d2: { id: s.d2.id, n: s.d2.name, p: s.d2.pts },
  m: s.margin,
  mp: s.margin_pct,
  c1: s.c1 ? { n: s.c1.name, l: s.c1.lineage_id && teamSummaryById.has(s.c1.lineage_id) ? s.c1.lineage_id : null, p: s.c1.pts, w: s.c1.wins, f: s.c1.f1db_pts ?? null } : null,
  c2: s.c2 ? { n: s.c2.name, p: s.c2.pts } : null,
  cm: s.c_margin,
  cmp: s.c_margin_pct,
  ex: s.excluded.map((e) => ({ n: e.name, p: e.pts })),
  ca: s.c_adjusted.map((c) => ({ n: c.name, k: c.kind, p: c.pts, pos: c.pos })),
}));
export type SeasonCard = (typeof seasonCards)[number];

export const closest = [...history.seasons].sort((a, b) => a.margin_pct - b.margin_pct)[0];
export const widest = [...history.seasons].sort((a, b) => b.margin_pct - a.margin_pct)[0];
/** 1위와 2위 점수 차이가 1위 점수의 5% 미만인 시즌 */
export const tightSeasons = history.seasons.filter((s) => s.margin_pct < 5);
export const maxWinners = [...history.seasons].sort((a, b) => b.winners - a.winners || b.season - a.season)[0];

/** 차트(seasonMargins) 자료 */
export const marginData = history.seasons.map((s) => ({
  s: s.season,
  d: s.margin_pct,
  dm: s.margin,
  d1: s.d1.name,
  d1p: s.d1.pts,
  d2: s.d2.name,
  d2p: s.d2.pts,
  c: s.c_margin_pct,
  cm: s.c_margin,
  c1: s.c1?.name ?? null,
  c1p: s.c1?.pts ?? null,
  c2: s.c2?.name ?? null,
  c2p: s.c2?.pts ?? null,
}));

// ---------------------------------------------------------------- 드라이버

/** 최종 순위 상위 10명과 라운드별 순위(정적 SVG 작은 선) */
export const top10 = latestSeason.drivers.filter((d) => d.position != null).slice(0, 10).map((d) => {
  const pos = d.positions as (number | null)[];
  const known = pos.filter((p): p is number => p != null);
  return {
    id: d.id,
    name: d.name,
    code: d.code,
    team: d.team,
    position: d.position as number,
    points: d.final_points as number,
    wins: d.wins as number,
    positions: pos,
    best: Math.min(...known),
    worst: Math.max(...known),
    led: pos.filter((p) => p === 1).length,
  };
});

/** 작은 선 하나: 라운드별 순위, 위가 1위. 세로축은 10명이 같은 범위를 쓴다(1위부터 maxPos위) */
export function sparkSvg(positions: (number | null)[], maxPos: number, w = 104, h = 30): string {
  const n = positions.length;
  const pad = 3;
  const x = (i: number) => pad + (i / Math.max(1, n - 1)) * (w - pad * 2);
  const y = (p: number) => pad + ((p - 1) / Math.max(1, maxPos - 1)) * (h - pad * 2);
  const segs: string[] = [];
  let cur = '';
  positions.forEach((p, i) => {
    if (p == null) {
      if (cur) segs.push(cur);
      cur = '';
      return;
    }
    cur += `${cur ? 'L' : 'M'}${x(i).toFixed(1)},${y(Math.min(p, maxPos)).toFixed(1)}`;
  });
  if (cur) segs.push(cur);
  const lastI = positions.length - 1;
  const last = positions[lastI];
  const top = `<line x1="${pad}" x2="${w - pad}" y1="${y(1).toFixed(1)}" y2="${y(1).toFixed(1)}" class="sp-ref" />`;
  const dot = last == null ? '' : `<circle cx="${x(lastI).toFixed(1)}" cy="${y(Math.min(last, maxPos)).toFixed(1)}" r="2.6" class="sp-end" />`;
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true" focusable="false">${top}<path d="${segs.join('')}" class="sp-line" />${dot}</svg>`;
}

export const sparkMax = Math.max(...top10.flatMap((d) => d.positions.filter((p): p is number => p != null)));

/** 순위가 같은 값은 같은 등수(1, 1, 3) */
function ranked<T>(rows: T[], value: (r: T) => number, n: number): (T & { rank: number })[] {
  const sorted = [...rows].sort((a, b) => value(b) - value(a));
  const cut = sorted[n - 1] ? value(sorted[n - 1]) : -Infinity;
  const kept = sorted.filter((r, i) => i < n || value(r) >= cut);
  const ranks = competitionRanks(kept, value);
  return kept.map((r, i) => ({ ...r, rank: ranks[i] }));
}

export const titleLeaders = ranked(history.driver_titles, (d) => d.titles, 5);
export const winLeaders = ranked(history.wins, (d) => d.wins ?? 0, 5);

// ---------------------------------------------------------------- 팀

export const teamRows = home.constructors.map((c) => {
  const t = c.lineage_id ? teamSummaryById.get(c.lineage_id) : undefined;
  return {
    id: c.id,
    name: c.name,
    lineage_id: c.lineage_id,
    name_ko: t?.name_ko ?? null,
    position: c.position,
    points: c.points,
    wins: c.wins,
    q: t?.last?.quali_index_mean ?? null,
    qRank: t?.last?.quali_rank ?? null,
  };
});

export const lineageTitles = [...history.lineages].filter((l) => l.titles > 0).sort((a, b) => b.titles - a.titles || a.name_ko.localeCompare(b.name_ko, 'ko'));

/** 컨스트럭터 누적 점수(pointsRace) 자료 */
export const teamPoints = latestSeason.constructors
  .filter((c) => c.points)
  .map((c) => ({ id: c.id, label: c.name, short: c.name, pos: c.position, pts: c.points as (number | null)[] }));

// ---------------------------------------------------------------- 업그레이드

const items = upgrades.items;
export const catOrder = labels.category_order as ReasonCategory[];
export const catCounts = Object.fromEntries(catOrder.map((c) => [c, items.filter((i) => i.category === c).length])) as Record<ReasonCategory, number>;
export const upgradeSeasons = [...new Set(items.map((i) => i.season))].sort();
export const perSeason = upgradeSeasons.map((s) => ({ season: s, n: items.filter((i) => i.season === s).length, docs: upgrades.documents.filter((d) => d.season === s).length }));

function topLineage(list: typeof items) {
  const m = new Map<string, number>();
  for (const i of list) if (i.lineage_id) m.set(i.lineage_id, (m.get(i.lineage_id) ?? 0) + 1);
  const best = [...m.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!best) return null;
  const tied = [...m.values()].filter((v) => v === best[1]).length;
  return { lineage_id: best[0], name_ko: teamSummaryById.get(best[0])?.name_ko ?? best[0], n: best[1], tied };
}
export const mostActive = topLineage(items);
export const mostActiveLatest = topLineage(items.filter((i) => i.season === meta.last_season));

// ---------------------------------------------------------------- 엔진

export const engineSeason = engines ? engines.seasons[String(engines.last_season)] : null;
export const engineSummary = engineSeason
  ? (() => {
      // 시즌 중 팀을 옮긴 드라이버(2025 Tsunoda)는 팀마다 행이 있어 드라이버 ID로 묶어 센다.
      const rows = engineSeason.teams.flatMap((t) => t.drivers);
      const ids = (pred: (d: (typeof rows)[number]) => boolean) => new Set(rows.filter(pred).map((d) => d.driver_id)).size;
      return {
        season: engineSeason.season,
        suppliers: [...engineSeason.suppliers].sort((a, b) => b.teams.length - a.teams.length),
        teams: engineSeason.suppliers.reduce((a, p) => a + p.teams.length, 0),
        drivers: ids(() => true),
        iceAllowed: engineSeason.allocation.ICE?.allowed ?? null,
        iceOver: ids((d) => d.exceed.includes('ICE')),
        anyOver: ids((d) => d.exceed.length > 0),
        iceEvents: engineSeason.ice_events.length,
        parsed: engineSeason.parsed_rounds.length,
        rounds: engineSeason.rounds,
        docs: Object.values(engineSeason.documents).reduce((a, t) => a + (t.ok ?? 0), 0),
      };
    })()
  : null;
export const engineAsOf = engines?.as_of ?? null;

// ---------------------------------------------------------------- 규정

const SECTIONS: Section[] = ['technical', 'sporting'];
export const regSummary = regulations
  ? (() => {
      const R = regulations;
      const year = R.last_year;
      const docs = R.documents[String(year)] ?? [];
      const latest = SECTIONS.map((sec) => {
        const list = docs.filter((d) => d.section === sec);
        const doc: RegDocument | undefined = [...list].sort((a, b) => (a.version_key ?? a.version ?? '').localeCompare(b.version_key ?? b.version ?? '')).at(-1);
        const cmp: RegComparison | undefined = R.comparisons.find((c) => c.kind === 'season' && c.section === sec && c.to_season === year);
        return { section: sec, doc: doc ?? null, issues: list.length, cmp: cmp ?? null };
      });
      return { year, first: R.first_year, last: R.last_year, years: R.years.length, asOf: R.as_of, latest };
    })()
  : null;

export const changed = (c: RegComparison) => (c.added ?? 0) + (c.removed ?? 0) + (c.modified ?? 0);

export { teams };
