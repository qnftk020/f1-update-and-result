// 빌드 시점에 생성된 JSON을 읽는 한 곳. 페이지와 컴포넌트는 여기서만 데이터를 가져온다.
import homeJson from '../data/generated/home.json';
import labelsJson from '../data/generated/labels.json';
import metaJson from '../data/generated/meta.json';
import seasonsJson from '../data/generated/seasons.json';
import teamsJson from '../data/generated/teams.json';
import upgradesJson from '../data/generated/upgrades.json';
import type { Home, Labels, Meta, Season, SeasonSummary, Team, TeamSummary, Upgrades } from './types';

export const meta = metaJson as unknown as Meta;
export const labels = labelsJson as unknown as Labels;
export const home = homeJson as unknown as Home;
export const seasons = seasonsJson as unknown as SeasonSummary[];
export const teams = teamsJson as unknown as TeamSummary[];
export const upgrades = upgradesJson as unknown as Upgrades;

const seasonFiles = import.meta.glob<{ default: Season }>('../data/generated/season/*.json', {
  eager: true,
});
const teamFiles = import.meta.glob<{ default: Team }>('../data/generated/team/*.json', {
  eager: true,
});

function byName<T>(files: Record<string, { default: T }>): Map<string, T> {
  const out = new Map<string, T>();
  for (const [path, mod] of Object.entries(files)) {
    const name = path.slice(path.lastIndexOf('/') + 1, -'.json'.length);
    out.set(name, mod.default);
  }
  return out;
}

const seasonByYear = byName(seasonFiles);
const teamById = byName(teamFiles);

export function getSeason(year: number): Season {
  const season = seasonByYear.get(String(year));
  if (!season) throw new Error(`시즌 데이터가 없다: ${year}`);
  return season;
}

export function getTeam(lineageId: string): Team {
  const team = teamById.get(lineageId);
  if (!team) throw new Error(`팀 데이터가 없다: ${lineageId}`);
  return team;
}

export const seasonYears: number[] = [...seasonByYear.keys()].map(Number).sort((a, b) => b - a);
export const lineageIds: string[] = teams.map((t) => t.lineage_id);

/** T6, T8 산출물처럼 있을 수도 없을 수도 있는 JSON을 읽는다. 없으면 null이다. */
const optionalFiles = import.meta.glob<{ default: unknown }>(
  ['../data/generated/engines.json', '../data/generated/regulations.json'],
  { eager: true },
);

export function getOptional<T>(name: 'engines' | 'regulations'): T | null {
  const mod = optionalFiles[`../data/generated/${name}.json`];
  return mod ? (mod.default as T) : null;
}

/** 계보 ID로 팀 요약(teams.json)을 찾는다. */
export const teamSummaryById = new Map(teams.map((t) => [t.lineage_id, t]));

/** 대회 영문 이름의 한국어 이름과 짧은 이름 */
export function gpName(name: string): { ko: string; short: string } {
  return labels.grand_prix[name] ?? { ko: name, short: name };
}

/** 머리말 상태 줄에 쓰는 값 */
export const status = {
  lastRace: { ...meta.last_race, short_ko: gpName(meta.last_race.name).short },
  reviewDocuments: meta.review_documents,
};
