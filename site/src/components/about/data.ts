// 데이터와 방법론 쪽에서 쓰는 수치와 목록. 원고(briefs/about_copy.md)의 {...} 자리는 모두 여기서 meta.json,
// 시즌·팀·업그레이드 JSON에서 센다. 선행 작업 목록은 references.json(prior_work.csv를 옮긴 것)에서 읽는다.
import { getOptional, getSeason, labels, meta, teams, upgrades } from '../../lib/data.ts';
import { formatLapTime, n0 } from '../../lib/format.ts';

const c = meta.counts;

/** 원고 자리값 */
export const V = {
  first: meta.first_season,
  last: meta.last_season,
  seasons: n0(c.seasons),
  races: n0(c.races),
  docs: n0(c.upgrade_documents),
  items: n0(c.upgrade_items),
  qualiRaces: n0(c.quali_index_races),
  raceRaces: n0(c.race_index_races),
  gridTeams: teams.length,
};

export const hasEngines = getOptional('engines') !== null;
export const hasRegulations = getOptional('regulations') !== null;

/** 원고의 반각 줄표(U+2013) 연도 범위를 붙임표로 맞춘다 */
export function dash(s: string): string {
  return s.replace(/–/g, '-');
}

/**
 * 퀄리파잉 지수 계산 예: 2025년 1라운드 호주 Red Bull. 세션 최고 랩(ms)과 지수에서 팀 최고 랩을 되돌려 적는다.
 * docs/methodology.md의 "계산 예"(1:15.096, 1:15.481, 0.513%)와 같은 값이 나와야 한다.
 */
export function qualiExample() {
  const s = getSeason(2025);
  const r = s.rounds[0];
  const rb = s.constructors.find((x) => x.id === 'red_bull');
  const best = r.quali?.best_ms ?? null;
  const v = rb?.quali_index?.[0] ?? null;
  if (best == null || v == null) return null;
  const team = Math.round(best * (1 + v / 100));
  return {
    season: s.season,
    round: r.round,
    gp: r.short_ko,
    team: rb!.name,
    bestLap: formatLapTime(best),
    teamLap: formatLapTime(team),
    bestS: (best / 1000).toFixed(3),
    teamS: (team / 1000).toFixed(3),
    v,
  };
}

/** 부품 영역 규칙: 원문 표기 수, 영역별 표기 수와 항목 수, 예외 1건(Floor Corner -> 프런트 코너) */
export function areaRules() {
  const items = upgrades.items;
  const spellings = new Set(items.map((i) => i.component));
  const byArea = Object.keys(labels.component_areas).map((key) => {
    const own = items.filter((i) => i.area === key);
    return { key, label: labels.component_areas[key], spellings: new Set(own.map((i) => i.component)).size, items: own.length };
  });
  const others = items.filter((i) => i.area === 'other').map((i) => i.component);
  const exception = items.find((i) => i.component === 'Floor Corner' && i.area === 'front_corner') ?? null;
  return { spellings: spellings.size, areas: byArea, others, exception };
}

export interface PriorWork {
  kind: 'data_project' | 'tool' | 'paper' | 'method';
  title: string;
  authors: string | null;
  year: number | null;
  venue: string | null;
  url: string;
  relation_ko: string;
  verified_on: string;
}

const refFiles = import.meta.glob<{ default: { prior_work: PriorWork[] } }>('../../data/generated/references.json', { eager: true });
export const priorWork: PriorWork[] = Object.values(refFiles)[0]?.default.prior_work ?? [];

export const KIND_LABEL: Record<PriorWork['kind'], string> = {
  data_project: '데이터 프로젝트',
  tool: '도구',
  paper: '논문',
  method: '방법론 문헌',
};

/**
 * 화면 표기 정리: 사이트 안에서만 쓰는 작업 번호 "(T15)"는 뺀다. 연도 범위는 붙임표로 맞춘다.
 * UI 문구 규칙상 "실시간"을 쓰지 않으므로 OpenF1의 유료 구간은 "라이브"로 적는다(원자료 CSV는 그대로다).
 */
export function relationText(s: string): string {
  return dash(s.replace(/\s?\(T\d+\)/g, '')).replace(/실시간/g, '라이브');
}
