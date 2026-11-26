// 체코지수 자료(race_score.json)와 대회 이름을 잇는 도우미. 자료가 없으면 raceScore는 null이다.
import { getOptional, getSeason } from '../../lib/data.ts';
import { routes } from '../../lib/paths.ts';
import { asofOpenF1 } from '../../lib/sources.ts';
import type { RaceScore, RaceScoreRow, Round } from '../../lib/types.ts';

export const raceScore = getOptional<RaceScore>('race_score');

const key = (season: number, round: number) => `${season}-${round}`;
const byRace = new Map<string, RaceScoreRow>((raceScore?.races ?? []).map((r) => [key(r.season, r.round), r]));

/** 그 대회의 체코지수 행. 계산 대상이 아니면 undefined */
export function scoreOf(season: number, round: number): RaceScoreRow | undefined {
  return byRace.get(key(season, round));
}

/** 체코지수가 있는 시즌인가(캘린더 열을 둘지) */
export function seasonHasScore(season: number): boolean {
  return (raceScore?.races ?? []).some((r) => r.season === season);
}

/** 체코지수 페이지의 대회 행 주소 */
export function scoreHref(season: number, round: number): string {
  return `${routes.chekoji()}#s${season}r${round}`;
}

/** 대회 행에 시즌 자료의 이름과 날짜를 붙인다 */
export function withRound(r: RaceScoreRow): RaceScoreRow & { info: Round } {
  const info = getSeason(r.season).rounds.find((x) => x.round === r.round);
  if (!info) throw new Error(`시즌 자료에 없는 대회다: ${r.season} R${r.round}`);
  return { ...r, info };
}

/** Jolpica 계열(랩 순위와 랩 시간으로 추정)로 계산한 대회인가 */
export function isEstimated(r: RaceScoreRow): boolean {
  return r.inputs.method === 'jolpica';
}

const SRC_OPENF1 = 'OpenF1 랩·스틴트·레이스 컨트롤, Jolpica-F1 결승 결과와 순위표로 이 사이트 계산';
const SRC_JOLPICA = 'Jolpica-F1 결승 결과·랩 순위와 랩 시간·피트스톱·순위표로 이 사이트 계산';

/** 꼬리말 자료 줄 판정에 쓰는 출처 글. season을 주면 그 시즌 계열의 데이터원만 */
export function scoreSourceFor(season?: number): string {
  const j = raceScore?.methods.jolpica;
  const o = raceScore?.methods.openf1;
  const inJ = j && (season === undefined || (season >= j[0] && season <= j[1]));
  const inO = o && (season === undefined || (season >= o[0] && season <= o[1]));
  return [inO ? SRC_OPENF1 : '', inJ ? SRC_JOLPICA : ''].filter(Boolean).join('. ');
}
export const scoreSource = scoreSourceFor();
export const scoreAsof = () => raceScore?.as_of ?? asofOpenF1();

/** 점수를 내지 못한 까닭(화면 문구) */
export function missingReason(r: RaceScoreRow): string {
  if (r.inputs.order_status === 'laps_missing') {
    const pct = Math.round(Number(r.inputs.order_coverage ?? 0) * 100);
    return `랩 기록이 일부 구간에만 있어(완주 랩의 ${pct}%) 순위 변동, 선두 교체, DNF 순위대를 집계하지 못했다.`;
  }
  if (r.inputs.method === 'jolpica' && r.missing.includes('rain')) {
    return '결승이 세이프티 카 뒤 주행만으로 끝나 한 랩으로 판정되어, 랩 시간으로 노면을 추정하지 못했다.';
  }
  return '일부 항목을 계산하지 못했다.';
}
