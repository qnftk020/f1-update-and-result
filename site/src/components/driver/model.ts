// 드라이버 쪽(/drivers/<id>/)의 문장, 타일, 표, 차트 자료를 driver/<id>.json 하나에서 빌드 때 만든다.
// 모든 수치는 그 파일(Jolpica 결과, 예선, 순위를 pipeline/site_drivers.py가 센 값)에서 온다.
// 반환하는 문장은 HTML 문자열이고 데이터에서 온 글자는 esc()를 거친다. 라틴 이름 뒤에는 조사를 붙이지 않는다.
import { formatPoints, n0, num } from '../../lib/format.ts';
import type { DriverFile, DriverRace, DriverSeasonRow } from '../../lib/drivers-data.ts';
import { aside, b, en, esc, nw } from '../../lib/typeset.ts';

export const pts = (x: number | null | undefined) => (x == null ? '미상' : formatPoints(Math.round(x * 100) / 100));
export const span = (a: number, z: number) => (a === z ? String(a) : `${a}-${z}`);
const pc = (a: number, n: number, d = 1) => (n ? `${num((a / n) * 100, d)}%` : '');

/** 연도 목록을 이어진 구간으로 줄인다: [2014, 2015, 2017, 2018, 2019, 2020] -> '2014-2015, 2017-2020' */
export function yearsText(years: number[]): string {
  const out: string[] = [];
  let a = years[0];
  let z = years[0];
  for (const y of years.slice(1)) {
    if (y === z + 1) z = y;
    else {
      out.push(span(a, z));
      a = z = y;
    }
  }
  if (years.length) out.push(span(a, z));
  return out.join(', ');
}

/** 시즌 행의 팀 이름(시즌 명칭). 한 시즌에 팀이 여럿이면 쉼표로 잇는다. */
export const teamNames = (r: DriverSeasonRow) => r.teams.map((t) => t.name).join(', ');

export interface Stint {
  key: string;
  c: string;
  names: string[];
  lineage: string | null;
  from: number;
  to: number;
  seasons: { s: number; champ: boolean }[];
  e: number;
  w: number;
  p: number;
}

export function buildDriver(d: DriverFile) {
  const rows = d.season_rows;
  const titleSet = new Set(d.title_seasons);
  const last = rows[rows.length - 1];
  const nameHtml = en(esc(d.name));

  // ---------------------------------------------------------------- 대회별 집계(팀 이력)
  // 같은 대회에 행이 여럿(차량 공유)이어도 그 팀의 출전 한 번으로 센다.
  const byTeamSeason = new Map<string, { e: Set<number>; w: Set<number>; p: Set<number> }>();
  for (const r of d.races) {
    const k = `${r.s}|${r.c}`;
    let g = byTeamSeason.get(k);
    if (!g) byTeamSeason.set(k, (g = { e: new Set(), w: new Set(), p: new Set() }));
    g.e.add(r.r);
    if (r.p === 1 && r.o === 'F') g.w.add(r.r);
    if (r.o === 'F' && r.p <= 3) g.p.add(r.r);
  }
  // 같은 constructor_id로 이어진 시즌을 한 구간으로 묶는다(빠진 해가 있으면 새 구간).
  const stints: Stint[] = [];
  for (const r of rows) {
    for (const t of r.teams) {
      const prev = [...stints].reverse().find((x) => x.c === t.id);
      const g = byTeamSeason.get(`${r.s}|${t.id}`);
      const add = { e: g?.e.size ?? 0, w: g?.w.size ?? 0, p: g?.p.size ?? 0 };
      if (prev && prev.to === r.s - 1) {
        prev.to = r.s;
        prev.seasons.push({ s: r.s, champ: titleSet.has(r.s) });
        if (!prev.names.includes(t.name)) prev.names.push(t.name);
        if (!prev.lineage && t.lineage_id) prev.lineage = t.lineage_id;
        prev.e += add.e;
        prev.w += add.w;
        prev.p += add.p;
      } else {
        stints.push({
          key: `${t.id}-${r.s}`,
          c: t.id,
          names: [t.name],
          lineage: t.lineage_id,
          from: r.s,
          to: r.s,
          seasons: [{ s: r.s, champ: titleSet.has(r.s) }],
          ...add,
        });
      }
    }
  }
  // 차트 줄은 팀(constructor_id)마다 하나: 처음 나온 순서
  const teamRows: { key: string; name: string; seasons: { s: number; champ: boolean }[]; span: string; e: number; w: number; p: number }[] = [];
  for (const st of stints) {
    let row = teamRows.find((x) => x.key === st.c);
    if (!row) teamRows.push((row = { key: st.c, name: st.names[st.names.length - 1], seasons: [], span: '', e: 0, w: 0, p: 0 }));
    row.seasons.push(...st.seasons);
    row.e += st.e;
    row.w += st.w;
    row.p += st.p;
  }
  for (const r of teamRows) r.span = yearsText(r.seasons.map((x) => x.s));

  // ---------------------------------------------------------------- 팀 동료
  const mateSeason = rows.map((r) => {
    const ms = r.mates.map((m) => ({ id: m.id, name: m.name, n: m.n, ra: m.ra, rb: m.rc - m.ra, qa: m.qa, qb: m.qc - m.qa, rc: m.rc, qc: m.qc }));
    const sum = (k: 'ra' | 'rb' | 'qa' | 'qb') => ms.reduce((a, m) => a + m[k], 0);
    return { s: r.s, team: teamNames(r), ra: sum('ra'), rb: sum('rb'), qa: sum('qa'), qb: sum('qb'), mates: ms };
  });
  const mateTotals = new Map<string, { id: string; name: string; seasons: number[]; n: number; ra: number; rc: number; qa: number; qc: number }>();
  for (const r of rows) {
    for (const m of r.mates) {
      let t = mateTotals.get(m.id);
      if (!t) mateTotals.set(m.id, (t = { id: m.id, name: m.name, seasons: [], n: 0, ra: 0, rc: 0, qa: 0, qc: 0 }));
      if (!t.seasons.includes(r.s)) t.seasons.push(r.s);
      t.n += m.n;
      t.ra += m.ra;
      t.rc += m.rc;
      t.qa += m.qa;
      t.qc += m.qc;
    }
  }
  const mates = [...mateTotals.values()].sort((a, z) => z.n - a.n || a.name.localeCompare(z.name));
  const tot = mates.reduce((a, m) => ({ ra: a.ra + m.ra, rc: a.rc + m.rc, qa: a.qa + m.qa, qc: a.qc + m.qc }), { ra: 0, rc: 0, qa: 0, qc: 0 });

  // ---------------------------------------------------------------- 차트 자료(시즌 행, 작게)
  const chartRows = rows.map((r) => ({
    s: r.s,
    pos: r.pos,
    pts: r.pts,
    cp: r.champ_pts,
    team: teamNames(r),
    champ: titleSet.has(r.s),
    ex: r.excluded,
    share: r.pts != null && r.champ_pts ? Math.round((r.pts / r.champ_pts) * 1000) / 10 : null,
    e: r.entries,
    w: r.wins,
    p: r.podiums,
  }));
  const ranked = rows.filter((r) => r.pos != null);

  // ---------------------------------------------------------------- 머리
  const teamList = d.teams.map((t) => `<span lang="en" class="nw">${esc(t.name)}</span>`).join(', ');
  const facts: [string, string][] = [
    ['국적', esc(d.nationality_ko)],
    ['생년월일', d.dob ? nw(d.dob) : '미상'],
    ['결승', `${nw(span(d.first_season, d.last_season))}, ${d.seasons}개 시즌`],
    ['팀', teamList || '미상'],
  ];
  if (d.code) facts.push(['약어', `<span class="mono">${esc(d.code)}</span>`]);
  if (d.indy_only) facts.push(['비고', '결승 기록은 모두 챔피언십에 포함된 인디애나폴리스 500이다']);
  const ex = rows.filter((r) => r.excluded);
  if (ex.length) facts.push(['실격 시즌', `${ex.map((r) => r.s).join(', ')} (점수 ${pts(ex[0].pts)}점은 남는다)`]);

  const tiles = [
    {
      label: '드라이버 챔피언',
      value: `${d.titles}번`,
      who: d.titles ? yearsText(d.title_seasons) : d.best != null ? `최고 순위 ${d.best}위${d.best_n > 1 ? `, ${d.best_n}번` : ''}` : '순위 미부여',
    },
    { label: '우승', value: `${d.wins}번`, who: d.starts ? `출발 대비 ${pc(d.wins, d.starts)}` : undefined },
    { label: '포디움', value: `${d.podiums}번`, who: `폴 포지션 ${d.poles}번` },
    { label: '출발', value: `${n0(d.starts)}회`, who: d.entries !== d.starts ? `출전 ${n0(d.entries)}회` : `${d.seasons}개 시즌` },
  ];

  return {
    rows,
    last,
    facts,
    tiles,
    stints,
    teamRows,
    mateSeason,
    mates,
    tot,
    chartRows,
    ranked,
    titleSet,
  };
}

/** 결과 칸: 완주 분류는 순위, 그 밖은 상태 분류 */
export function outcome(r: DriverRace): string {
  if (r.o === 'F') return `${r.p}위`;
  if (r.o === 'D') return '실격';
  if (r.o === 'N') return '출발 안 함';
  return '리타이어';
}

/** 출발 칸: Jolpica가 0으로 적은 경우(피트 레인 출발이나 기록 없음)는 0 그대로 두고 풀이를 단다 */
export function gridCell(g: number): string {
  return g === 0 ? '<span title="Jolpica 기록 0: 피트 레인 출발 또는 기록 없음">0</span>' : String(g);
}
