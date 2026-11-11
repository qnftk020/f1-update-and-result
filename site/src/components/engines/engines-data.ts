// 엔진 페이지 자료(engines.json, pipeline/site_data_extra.py build_engines)의 타입과 도우미.
// 공용 lib/types.ts에 엔진 타입이 아직 없어서 이 폴더에 둔다.
import { getOptional } from '../../lib/data.ts';

export interface FinalIssue {
  issue: string | null;
  version: string | null;
  status: string;
  url: string | null;
  review_reasons: string[];
}

export interface Allocation {
  allowed: number;
  basis: 'regulation' | 'document';
  clause_no: string | null;
  page: number | null;
  url: string | null;
  /** 규정 값을 읽은 판(basis가 regulation일 때) */
  version_key: string | null;
  issue: string | null;
  /** 시즌 마지막 판에서 읽었는가. 거짓이면 final_issue가 마지막 판이다 */
  is_final_issue: boolean | null;
  final_issue: FinalIssue | null;
}

/** FIA 선언 문서의 배정 문장이 밝힌 허용 개수(pu_allocations.csv) */
export interface AllocationStatement {
  allowed: number;
  first_round: number;
  documents: number;
  url: string | null;
}

export interface RoundLabel {
  round: number;
  name: string;
  name_ko: string;
  short_ko: string;
  date: string;
}

export interface PuDriver {
  driver_id: string;
  name: string;
  code: string | null;
  car_numbers: number[];
  rounds: number[];
  by: Record<string, (number | null)[]>;
  final: Record<string, number | null>;
  exceed: string[];
}

export interface PuTeam {
  constructor_id: string;
  team: string;
  lineage_id: string | null;
  pu: { id: string; name: string } | null;
  drivers: PuDriver[];
}

export interface IceEvent {
  round: number;
  driver_id: string | null;
  name: string | null;
  constructor_id: string | null;
  team: string | null;
  car_number: number | null;
  /** 문서끼리 어긋나면 null(순번 미확정) */
  ice_number: number | null;
  printed_previously_used: number | null;
  stated_ordinal: number | null;
  within_allocation: boolean | null;
  conflict: string | null;
  conflict_ko: string | null;
  url: string | null;
}

export interface EngineSeason {
  season: number;
  rounds: number;
  round_labels: RoundLabel[];
  suppliers: { id: string; name: string; teams: { constructor_id: string; team: string; lineage_id: string | null }[] }[];
  elements: string[];
  allocation: Record<string, Allocation | null>;
  allocation_statements: Record<string, AllocationStatement[]>;
  parsed_rounds: number[];
  missing_rounds: number[];
  partial_rounds: number[];
  unknown_new_rounds: number[];
  teams: PuTeam[];
  ice_events: IceEvent[];
  documents: Record<string, Record<string, number>>;
  review_documents: { round: number; event: string; event_ko: string; event_short_ko: string; doc_type: string; url: string | null }[];
  inconsistencies: number;
}

export interface Engines {
  first_season: number;
  last_season: number;
  elements: string[];
  as_of: string | null;
  seasons: Record<string, EngineSeason>;
  coverage: {
    season: number;
    rounds: number;
    parsed_rounds: number;
    missing_rounds: number[];
    partial_rounds: number[];
    unknown_new_rounds: number[];
    documents: Record<string, Record<string, number>>;
    review_documents: number;
    inconsistencies: number;
    ice_events: number;
    ice_unsure: number;
  }[];
}

export const engines = getOptional<Engines>('engines');

/** 엔진 페이지가 다루는 시즌(최근 먼저) */
export const engineYears: number[] = engines
  ? Object.keys(engines.seasons).map(Number).sort((a, b) => b - a)
  : [];

/** 문서 수: documents[doc_type][status]의 합 또는 한 상태 */
export function docCount(docs: Record<string, Record<string, number>>, type: string, status?: string): number {
  const t = docs[type] ?? {};
  if (status) return t[status] ?? 0;
  return Object.values(t).reduce((a, b) => a + b, 0);
}

/** 연속 라운드를 묶어 "1-3, 13" 꼴로 적는다 */
export function roundList(rounds: number[]): string {
  const out: string[] = [];
  let i = 0;
  while (i < rounds.length) {
    let j = i;
    while (j + 1 < rounds.length && rounds[j + 1] === rounds[j] + 1) j++;
    out.push(j - i >= 2 ? `${rounds[i]}-${rounds[j]}` : rounds.slice(i, j + 1).join(', '));
    i = j + 1;
  }
  return out.join(', ');
}

/** 행(드라이버) 순서: 팀 순서(최종 순위), 팀 안에서는 처음 나온 라운드 */
export function driverRows(s: EngineSeason) {
  return s.teams.flatMap((t, ti) =>
    t.drivers.map((d, di) => ({ ...d, team: t.team, constructor_id: t.constructor_id, teamIndex: ti, first: di === 0, last: di === t.drivers.length - 1 })),
  );
}
