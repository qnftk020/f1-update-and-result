// 컨스트럭터 쪽(/constructors/, /constructors/<id>/, /constructors/<id>/<시즌>/)이 읽는 빌드 시점 JSON.
// pipeline/site_constructors.py가 만든다. 정의는 docs/methodology.md "컨스트럭터 통계"에 있다.
// constructor/<id>.json은 페이지마다 하나만 읽도록 지연 import로 둔다(203개 파일을 한 번에 싣지 않는다).
import constructorsJson from '../data/generated/constructors.json';
import { routes } from './paths.ts';

export type Cause = 'acc' | 'mech' | 'unk' | 'nc' | 'oth';

export interface ConstructorSummary {
  id: string;
  name: string;
  nationality: string | null;
  nationality_ko: string | null;
  first_season: number;
  last_season: number;
  seasons: number;
  years: number[];
  entries: number;
  cars: number;
  wins: number;
  podiums: number;
  one_two: number;
  titles: number;
  title_seasons: number[];
  driver_titles: number;
  driver_title_seasons: number[];
  best: number | null;
  best_n: number;
  names: string[];
  lineages: string[];
  drivers_n: number;
  in_2025: boolean;
}

export interface ConstructorSeasonDriver {
  id: string;
  name: string;
  n: number;
  w: number;
  p: number;
  pts: number;
  best: number | null;
}

/** 참가 팀(entrant) 하나가 그 시즌 이 컨스트럭터로 등록한 섀시(c)와 엔진(g). F1DB 전체 이름, 이름순. */
export interface ConstructorKit {
  e: string;
  c: string[];
  g: string[];
}

export interface ConstructorSeasonRow {
  s: number;
  rounds: number;
  name: string;
  lineage_id: string | null;
  engine: string | null;
  /** null: 싣지 않는 시즌(2010-2021). []: F1DB 기록과 맞추지 못한 시즌. */
  kit: ConstructorKit[] | null;
  entries: number;
  cars: number;
  wins: number;
  podiums: number;
  one_two: number;
  classified: number;
  dsq: number;
  dns: number;
  causes: Record<Cause, number>;
  rpts: number;
  pos: number | null;
  pts: number | null;
  excluded: boolean;
  deducted: boolean;
  champ_id: string | null;
  champ_pts: number | null;
  driver_champ: string | null;
  round_pos: (number | null)[] | null;
  round_pts: (number | null)[] | null;
  quali_mean: number | null;
  quali_n: number;
  drivers: ConstructorSeasonDriver[];
}

/** 결과 한 줄(차마다). o: F 완주 분류, D 실격, N 출발하지 않음, R 리타이어. q 최종 예선 순위, rc 리타이어 원인 */
export interface ConstructorRace {
  s: number;
  r: number;
  n: string;
  d: string;
  g: number;
  p: number;
  o: 'F' | 'D' | 'N' | 'R';
  st: string;
  pts: number;
  q?: number;
  rc?: Cause;
  x?: 1;
}

export interface ConstructorCareerDriver {
  id: string;
  name: string;
  seasons: number[];
  n: number;
  w: number;
  p: number;
  pts: number;
}

export interface ConstructorFile extends ConstructorSummary {
  season_rows: ConstructorSeasonRow[];
  drivers: ConstructorCareerDriver[];
  races: ConstructorRace[];
}

export const constructors = constructorsJson as unknown as ConstructorSummary[];
export const constructorById = new Map(constructors.map((c) => [c.id, c]));

const files = import.meta.glob<{ default: ConstructorFile }>('../data/generated/constructor/*.json');

export async function getConstructor(id: string): Promise<ConstructorFile> {
  const load = files[`../data/generated/constructor/${id}.json`];
  if (!load) throw new Error(`컨스트럭터 데이터가 없다: ${id}`);
  return (await load()).default;
}

/** 컨스트럭터 쪽이 있으면 링크를 단다. html은 이미 esc()를 거친 이름 조각이다. season을 주면 그 시즌 쪽으로 잇는다. */
export function constructorLink(id: string | null | undefined, html: string, season?: number): string {
  if (!id || !constructorById.has(id)) return html;
  return `<a href="${season ? routes.constructorSeason(id, season) : routes.constructorPage(id)}">${html}</a>`;
}

/** 리타이어 원인 이름(lib/charts/detail.js CAUSE와 같다) */
export const CAUSE_KO: Record<Cause, string> = {
  acc: '사고·충돌',
  mech: '차량 문제',
  unk: '원인 미기재',
  nc: '완주 미분류',
  oth: '그 밖',
};
