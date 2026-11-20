// 비교 화면 자료를 빌드 때 만든다. 드라이버와 컨스트럭터 쪽이 읽는 JSON(driver/<id>.json, constructor/<id>.json)을
// 줄인 것이라 수치는 그 쪽들과 같다. 검색 목록은 /compare/ 쪽에 싣고, 고른 대상의 자료 파일은
// /data/compare/<d|c>/<id>.json(pages/data/compare/[kind]/[id].json.ts)을 브라우저가 받아 온다.
import { span } from '../components/driver/model.ts';
import { bestPerRace, fold, type CompareFile, type IndexRow } from './compare.ts';
import { constructors, getConstructor } from './constructors-data.ts';
import { drivers, getDriver } from './drivers-data.ts';

export function driverIndex(): IndexRow[] {
  return drivers.map((d) => [
    d.id,
    d.name,
    fold([d.name, d.code ?? '', d.nationality_ko ?? '', d.nationality ?? ''].join(' ')),
    d.titles,
    d.wins,
    d.starts,
    d.last_season,
    [d.nationality_ko, span(d.first_season, d.last_season)].filter(Boolean).join(' · '),
  ]);
}

export function constructorIndex(): IndexRow[] {
  return constructors.map((c) => [
    c.id,
    c.name,
    fold([c.name, ...c.names, c.id.replace(/_/g, ' '), c.nationality_ko ?? '', c.nationality ?? ''].join(' ')),
    c.titles,
    c.wins,
    c.entries,
    c.last_season,
    [c.nationality_ko, span(c.first_season, c.last_season)].filter(Boolean).join(' · '),
  ]);
}

export async function driverCompare(id: string): Promise<CompareFile> {
  const d = await getDriver(id);
  const mates = new Map<string, NonNullable<CompareFile['m']>[number]>();
  for (const row of d.season_rows) {
    for (const m of row.mates) {
      const team = row.teams.find((t) => t.id === m.c)?.name ?? m.c;
      const cur = mates.get(m.id) ?? [m.id, m.name, 0, 0, 0, 0, 0, [], ''];
      cur[2] += m.n;
      cur[3] += m.rc;
      cur[4] += m.ra;
      cur[5] += m.qc;
      cur[6] += m.qa;
      if (!cur[7].includes(row.s)) cur[7].push(row.s);
      if (!cur[8].split(', ').includes(team)) cur[8] = cur[8] ? `${cur[8]}, ${team}` : team;
      mates.set(m.id, cur);
    }
  }
  return {
    k: 'd',
    id: d.id,
    name: d.name,
    nat: d.nationality_ko,
    first: d.first_season,
    last: d.last_season,
    t: {
      seasons: d.seasons,
      entries: d.entries,
      starts: d.starts,
      wins: d.wins,
      podiums: d.podiums,
      poles: d.poles,
      titles: d.titles,
      best: d.best,
      best_n: d.best_n,
      indy: d.indy_only ? 1 : 0,
    },
    s: d.season_rows.map((r) => [
      r.s,
      r.pos,
      r.wins,
      r.podiums,
      r.starts,
      r.teams.map((t) => t.name).join(', '),
      d.title_seasons.includes(r.s) ? 1 : 0,
      r.excluded ? 1 : 0,
    ]),
    r: bestPerRace(d.races.map((x) => ({ s: x.s, r: x.r, n: x.n, o: x.o, p: x.p }))),
    m: [...mates.values()],
  };
}

export async function constructorCompare(id: string): Promise<CompareFile> {
  const c = await getConstructor(id);
  return {
    k: 'c',
    id: c.id,
    name: c.name,
    nat: c.nationality_ko,
    first: c.first_season,
    last: c.last_season,
    t: {
      seasons: c.seasons,
      entries: c.entries,
      cars: c.cars,
      wins: c.wins,
      podiums: c.podiums,
      one_two: c.one_two,
      titles: c.titles,
      driver_titles: c.driver_titles,
      best: c.best,
      best_n: c.best_n,
      drivers_n: c.drivers_n,
    },
    s: c.season_rows.map((r) => [
      r.s,
      r.pos,
      r.wins,
      r.podiums,
      r.entries,
      r.engine ?? '',
      c.title_seasons.includes(r.s) ? 1 : 0,
      r.excluded ? 1 : 0,
    ]),
    r: bestPerRace(c.races.map((x) => ({ s: x.s, r: x.r, n: x.n, o: x.o, p: x.p }))),
  };
}

export const compareIds = { d: drivers.map((d) => d.id), c: constructors.map((c) => c.id) };
