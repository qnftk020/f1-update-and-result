// 생성된 JSON을 차트 함수(lib/charts/charts.js)가 받는 자료 모양으로 바꾼다. 빌드 때(프런트매터) 부르고
// 결과를 Figure의 data로 넘긴다. 모양은 briefs/site_impl_contract.md의 차트 표와 같다.
import type { Home, Season, Team, UpgradeItem } from './types.ts';
import { getSeason } from './data.ts';

/** 퀄리파잉 지수 순위(qualifyingRank): 빠른 순 [{team, v, gap, ms}] */
export function qualiRankData(home: Home) {
  return home.quali.map((q) => ({ team: q.constructor, cid: q.constructor_id, v: q.v, gap: q.gap_s, ms: q.team_best_ms }));
}

/** 레이스 지수와 구간(raceIntervals): 빠른 순 [{team, v, lo, hi, laps}] */
export function raceIntervalData(home: Home) {
  return home.race_index.map((r) => ({ team: r.constructor, cid: r.constructor_id, v: r.v, lo: r.lo, hi: r.hi, laps: r.laps }));
}

/** 출발과 결승(gridToFinish): 결승 순서 [{code, name, team, grid, pos}]. 출발 기록(grid)이 0인 차(피트 출발)는 뺀다. */
export function gridFinishData(home: Home) {
  return home.classification
    .filter((c) => c.position != null && c.grid != null && c.grid > 0)
    .map((c) => ({ code: c.code ?? c.name.slice(0, 3).toUpperCase(), name: c.name, team: c.constructor, grid: c.grid, pos: c.position }));
}

/** 라운드별 항목 수(roundCounts): 문서가 있는 라운드만 [{round, short, n, doc, review}]. opts.rounds는 home.rounds_in_season */
export function roundCountData(home: Home) {
  return home.round_counts.map((r) => ({ round: r.round, short: r.short_ko, n: r.n, doc: true, review: r.review }));
}

/**
 * 퀄리파잉 라운드 표(paceTrend, paceMultiples kind "quali"):
 * [{round, short, date, wet: 'wet'|'dry'|'unclassified', ref, field: {q1, med, q3} | null, teams: {cid: v | null}}]
 * 예선 지수가 없는 라운드는 빠진다.
 */
export function qualiRounds(season: Season) {
  return season.rounds.flatMap((r, i) => {
    if (!r.quali) return [];
    const teams: Record<string, number | null> = {};
    for (const c of season.constructors) if (c.quali_index) teams[c.id] = c.quali_index[i];
    return [{ round: r.round, short: r.short_ko, date: r.date, wet: r.quali.wet, ref: r.quali.reference, field: r.quali.field, teams }];
  });
}

/**
 * 레이스 라운드 표(raceTrend, paceMultiples kind "race"):
 * [{round, short, date, wet: boolean, teams: {cid: [v, lo, hi, cleanLaps] | null}}]
 */
export function raceRounds(season: Season) {
  return season.rounds.flatMap((r, i) => {
    if (!r.race) return [];
    const teams: Record<string, [number, number | null, number | null, number] | null> = {};
    for (const c of season.constructors) {
      if (!c.race_index) continue;
      const x = c.race_index[i];
      teams[c.id] = x ? [x.v, x.lo, x.hi, x.n] : null;
    }
    return [{ round: r.round, short: r.short_ko, date: r.date, wet: r.race.wet, teams }];
  });
}

/** 작은 다중의 칸 순서(paceMultiples opts.teams): 컨스트럭터 최종 순위 순, 예선 지수가 있는 팀만 [{cid, team}] */
export function multipleTeams(season: Season) {
  return season.constructors.filter((c) => c.quali_index).map((c) => ({ cid: c.id, team: c.name }));
}

/** 누적 점수(pointsRace) 드라이버 계열: 최종 순위 순 [{id, label, short, team, pts}] */
export function driverPoints(season: Season) {
  return season.drivers.map((d) => ({ id: d.id, label: d.name, short: d.code ?? d.name, team: d.team, pts: d.points }));
}

/** 누적 점수(pointsRace) 컨스트럭터 계열: [{id, label, pts}]. 1958년 이전은 빈 배열 */
export function constructorPoints(season: Season) {
  return season.constructors.filter((c) => c.points).map((c) => ({ id: c.id, label: c.name, short: c.name, pts: c.points as (number | null)[] }));
}

/** pointsRace opts.rounds: [{short}] */
export function roundLabels(season: Season) {
  return season.rounds.map((r) => ({ short: r.short_ko }));
}

/** 업그레이드 단위 차트(upgradeUnits): {시즌: [{round, short, status, doc_review, cats, n}]} */
export function unitData(team: Team) {
  return team.upgrades.timeline;
}

/** 업그레이드 신고 줄(paceTrend, raceTrend opts.rail): 그 시즌 신고가 있는 라운드 [{round, n}] */
export function railData(team: Team, season: number) {
  return (team.upgrades.timeline[String(season)] ?? []).filter((r) => r.n > 0).map((r) => ({ round: r.round, n: r.n }));
}

/** 계보 시대 띠(seasonTrend, standingsSteps opts.eras): [{team, from, to}] */
export function eraData(team: Team) {
  return team.segments.map((s) => ({ team: s.team_name, from: s.from, to: s.to }));
}

/**
 * 시즌 평균 퀄리파잉 지수(seasonTrend): [{season, team, q, ref, field, qn, qwet}]
 * q는 시즌 평균, ref는 참고용 형식(2003-2005), qn은 평균에 넣은 예선 수, qwet은 뺀 우천 예선 수.
 */
export function seasonTrendData(team: Team) {
  return team.seasons.map((s) => ({
    season: s.season,
    team: s.team_name,
    q: s.quali_index_mean,
    ref: s.quali_reference,
    field: s.quali_field,
    qn: s.quali_rounds,
    qwet: s.quali_wet_rounds,
  }));
}

/** 시즌 최종 컨스트럭터 순위(standingsSteps): [{season, team, pos, pts, wins}] */
export function standingsData(team: Team) {
  return team.seasons.map((s) => ({ season: s.season, team: s.team_name, pos: s.position, pts: s.points, wins: s.race_wins }));
}

/** 변경 사유 비율(reasonShare): {performance, circuit_specific, reliability, other} */
export function reasonCounts(items: UpgradeItem[]) {
  const out = { performance: 0, circuit_specific: 0, reliability: 0, other: 0 };
  for (const i of items) out[i.category] += 1;
  return out;
}

/**
 * 묶음별 항목 수(groupedReasons). by "team"(계보), "area"(부품 영역): 많은 순. by "event": 시간 순(문서가 있는 대회 모두, 0건 포함).
 * [{key, label, cats, total, season?, review?}]
 */
export function groupData(
  items: UpgradeItem[],
  by: 'team' | 'area' | 'event',
  names: { team?: Record<string, string>; area?: Record<string, string>; events?: { season: number; round: number; short: string; review: boolean }[] } = {},
) {
  const groups = new Map<string, { key: string; label: string; cats: Record<string, number>; total: number; season?: number; review?: boolean }>();
  const make = (key: string, label: string, extra = {}) => {
    if (!groups.has(key)) groups.set(key, { key, label, cats: { performance: 0, circuit_specific: 0, reliability: 0, other: 0 }, total: 0, ...extra });
    return groups.get(key)!;
  };
  if (by === 'event') for (const e of names.events ?? []) make(`${e.season}-${e.round}`, `${e.season} ${e.round}라운드 ${e.short}`, { season: e.season, review: e.review });
  for (const i of items) {
    const key = by === 'team' ? (i.lineage_id ?? i.constructor_id) : by === 'area' ? i.area : `${i.season}-${i.round}`;
    const label =
      by === 'team' ? (names.team?.[key] ?? i.team) : by === 'area' ? (names.area?.[key] ?? key) : `${i.season} ${i.round}라운드 ${i.event_short_ko}`;
    const g = make(key, label, by === 'event' ? { season: i.season, review: i.review } : {});
    g.cats[i.category] += 1;
    g.total += 1;
  }
  const list = [...groups.values()];
  return by === 'event' ? list : list.sort((a, b) => b.total - a.total);
}

/** 시즌 JSON을 직접 읽는다(팀 페이지가 2023-2025 시즌 표를 만들 때). */
export function seasonData(year: number): Season {
  return getSeason(year);
}
