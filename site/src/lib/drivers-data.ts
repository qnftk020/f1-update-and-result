// 드라이버 쪽(/drivers/, /drivers/<id>/)이 읽는 빌드 시점 JSON. pipeline/site_drivers.py가 만든다.
// 모양과 정의는 docs/methodology.md "드라이버 통계와 챔피언십 분석"에 있다. 이 모듈은 드라이버 쪽만 쓴다.
// driver/<id>.json은 페이지마다 하나만 읽도록 지연 import로 둔다(817개 파일을 한 번에 싣지 않는다).
import driversJson from '../data/generated/drivers.json';

export interface TeamRef {
  id: string;
  name: string;
}

export interface DriverSummary {
  id: string;
  name: string;
  code: string | null;
  nationality: string;
  nationality_ko: string;
  dob: string | null;
  first_season: number;
  last_season: number;
  seasons: number;
  entries: number;
  starts: number;
  wins: number;
  podiums: number;
  classified: number;
  grid_one: number;
  poles: number;
  points: number;
  sprint_points: number;
  sprint_wins: number;
  titles: number;
  title_seasons: number[];
  best: number | null;
  best_n: number;
  teams: TeamRef[];
  last_team: TeamRef;
  lineages: string[];
  in_2025: boolean;
  indy_only: boolean;
}

export interface Mate {
  id: string;
  name: string;
  c: string;
  n: number;
  rc: number;
  ra: number;
  qc: number;
  qa: number;
}

export interface DriverSeasonRow {
  s: number;
  rounds: number;
  teams: { id: string; name: string; lineage_id: string | null }[];
  entries: number;
  starts: number;
  wins: number;
  podiums: number;
  grid_one: number;
  poles: number;
  q_cov: number;
  rpts: number;
  spts: number;
  pos: number | null;
  pts: number | null;
  excluded: boolean;
  champ_id: string;
  champ_pts: number;
  round_pos: (number | null)[];
  round_pts: (number | null)[];
  mates: Mate[];
}

/** 결과 한 줄. o: F 완주 분류, D 실격, N 출발하지 않음, R 그 밖의 미분류(리타이어) */
export interface DriverRace {
  s: number;
  r: number;
  n: string;
  c: string;
  g: number;
  p: number;
  o: 'F' | 'D' | 'N' | 'R';
  st: string;
  pts: number;
  /** 최종 예선 순위(1994년부터, 결승 행만) */
  q?: number;
  /** 리타이어 원인 분류(o가 R일 때): acc 사고·충돌, mech 차량 문제, unk 원인 미기재, nc 완주 미분류, oth 그 밖 */
  rc?: 'acc' | 'mech' | 'unk' | 'nc' | 'oth';
  /** 같은 대회 같은 컨스트럭터 동료의 결과 [드라이버 ID, 결과 분류, position] (결승 행만, 동료 3명 이하) */
  m?: [string, 'F' | 'D' | 'N' | 'R', number][];
  x?: 1;
}

export interface DriverFile extends DriverSummary {
  season_rows: DriverSeasonRow[];
  races: DriverRace[];
  sprints: DriverRace[];
}

export const drivers = driversJson as unknown as DriverSummary[];
// history.json 타입과 로더는 lib/history.ts 한 곳에 둔다.
export { history } from './history.ts';
export const driverById = new Map(drivers.map((d) => [d.id, d]));

const files = import.meta.glob<{ default: DriverFile }>('../data/generated/driver/*.json');

export async function getDriver(id: string): Promise<DriverFile> {
  const load = files[`../data/generated/driver/${id}.json`];
  if (!load) throw new Error(`드라이버 데이터가 없다: ${id}`);
  return (await load()).default;
}
