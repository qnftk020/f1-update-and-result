// 전역 검색 색인(/data/search.json). 모양은 lib/search.ts의 SearchEntry다.
// 쪽이 있는 개체만 싣는다: 드라이버, 컨스트럭터, 팀 계보, 시즌, 대회(시즌 쪽 캘린더 행 #r<라운드>), 엔진 시즌, 규정 연도,
// 그리고 개체가 아닌 페이지(체코지수).
import type { APIRoute } from 'astro';
import { engineYears, engines } from '../../components/engines/engines-data.ts';
import { regulations } from '../../components/regulations/reg-data.ts';
import { raceScore } from '../../components/score/score-data.ts';
import { constructors } from '../../lib/constructors-data.ts';
import { getSeason, seasonYears, teams } from '../../lib/data.ts';
import { drivers } from '../../lib/drivers-data.ts';
import { routes, url } from '../../lib/paths.ts';
import type { SearchEntry } from '../../lib/search.ts';

const span = (a: number, b: number) => (a === b ? String(a) : `${a}-${b}`);

export const GET: APIRoute = () => {
  const out: SearchEntry[] = [];
  for (const d of drivers) {
    out.push({
      k: 'driver',
      n: d.name,
      a: [d.code, d.nationality, d.nationality_ko, d.id.replace(/_/g, ' ')].filter(Boolean).join(' '),
      m: span(d.first_season, d.last_season),
      u: routes.driver(d.id),
      w: d.starts + d.titles * 50 + (d.in_2025 ? 200 : 0),
    });
  }
  for (const c of constructors) {
    out.push({
      k: 'constructor',
      n: c.name,
      a: [c.nationality, c.nationality_ko, ...(c.names ?? []), c.id.replace(/[-_]/g, ' ')].filter(Boolean).join(' '),
      m: span(c.first_season, c.last_season),
      u: routes.constructorPage(c.id),
      w: c.entries + c.titles * 50 + (c.in_2025 ? 200 : 0),
    });
  }
  for (const t of teams) {
    out.push({
      k: 'team',
      n: t.name_ko,
      a: [t.lineage_id, t.base, ...(t.names ?? []), t.constructor?.name].filter(Boolean).join(' '),
      m: `${t.since}-`,
      u: routes.team(t.lineage_id),
      w: 1000,
    });
  }
  for (const year of seasonYears) {
    const s = getSeason(year);
    out.push({ k: 'season', n: `${year} 시즌`, a: String(year), m: `${s.rounds.length}개 대회`, u: routes.season(year), w: year });
    for (const r of s.rounds) {
      out.push({
        k: 'race',
        n: `${year} ${r.name_ko}`,
        a: [r.name, r.short_ko, r.circuit, r.locality, r.country, `R${r.round}`].filter(Boolean).join(' '),
        m: r.date,
        u: `${routes.season(year)}#r${r.round}`,
        w: year,
      });
    }
  }
  if (engines) {
    for (const y of engineYears) {
      out.push({
        k: 'engine',
        n: `${y} 엔진`,
        a: `${y} PU 파워 유닛 구성요소 power unit`,
        m: 'PU 사용 현황',
        u: y === engines.last_season ? routes.engines() : url(`/engines/${y}/`),
        w: y,
      });
    }
  }
  if (regulations) {
    for (const y of regulations.years) {
      out.push({
        k: 'regulation',
        n: `${y.year} 규정`,
        a: `${y.year} 기술 규정 스포팅 규정 technical sporting regulations`,
        m: `등급 ${y.grade}`,
        u: `${routes.regulations()}${y.year}/`,
        w: y.year,
      });
    }
  }
  if (raceScore) {
    out.push({
      k: 'page',
      n: '체코지수',
      a: 'chekoji 관전 지수 결승 점수 재미 race score',
      m: `${raceScore.reference_seasons.join('-')} 결승`,
      u: routes.chekoji(),
      w: 3000,
    });
  }
  return new Response(JSON.stringify(out), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
};
