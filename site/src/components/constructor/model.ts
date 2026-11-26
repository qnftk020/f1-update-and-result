// 컨스트럭터 쪽(/constructors/<id>/, /constructors/<id>/<시즌>/)의 문장, 타일, 표, 차트 자료를
// constructor/<id>.json 하나(와 시즌 JSON)에서 빌드 때 만든다. 모든 수치는 그 파일(Jolpica 결과와 순위를
// pipeline/site_constructors.py가 센 값)에서 온다. 반환하는 문장은 HTML 문자열이고 데이터에서 온 글자는
// esc()를 거친다. 라틴 이름 뒤에는 받침에 따라 갈리는 조사를 붙이지 않는다.
import { span, yearsText } from '../driver/model.ts';
import type { ConstructorFile, ConstructorRace, ConstructorSeasonRow } from '../../lib/constructors-data.ts';
import { CAUSE_KO } from '../../lib/constructors-data.ts';
import { formatPoints, n0, num } from '../../lib/format.ts';
import { aside, b, en, esc, nw } from '../../lib/typeset.ts';

export const pts = (x: number | null | undefined) => (x == null ? '미상' : formatPoints(Math.round(x * 100) / 100));
const pc = (a: number, n: number, d = 1) => (n ? `${num((a / n) * 100, d)}%` : '');
/** 연도 목록 글: 구간마다 줄바꿈하지 않게 묶고, 구간 사이에서는 줄을 바꿀 수 있게 둔다 */
const yearsHtml = (years: number[]) => yearsText(years).split(', ').map(nw).join(', ');
export const STANDINGS_FROM = 1958;
/** 드라이버 차트(teamStrip)의 순번별 범례 모양: 원, 네모, 세모, 마름모(넷째부터 맥락 회색) */
export const DRIVER_KEYS = [
  { type: 'dot' as const, color: 's1' },
  { type: 'sq' as const, color: 's2' },
  { type: 'tri-c' as const, color: 's3' },
  { type: 'diamond' as const, color: 'ctx' },
];

/** 결과 칸: 완주 분류는 순위, 그 밖은 분류 이름(리타이어는 원인) */
export function outcomeCell(r: { o: string; p: number; rc?: string }): string {
  if (r.o === 'F') return `${r.p}위`;
  if (r.o === 'D') return '실격';
  if (r.o === 'N') return '출발 안 함';
  return r.rc ? `리타이어<span class="sub-line">${CAUSE_KO[r.rc as keyof typeof CAUSE_KO]}</span>` : '리타이어';
}

/** 시즌 행의 "그 밖" 결과 수: 원인 미기재, 완주 미분류, 그 밖의 리타이어, 실격, 출발 안 함 */
const otherOf = (r: ConstructorSeasonRow) => r.causes.unk + r.causes.nc + r.causes.oth + r.dsq + r.dns;

/** 완주 순위 분포 자료: 1위부터 20위까지와 21위 이하 묶음 */
export function posDist(list: { o: string; p: number }[]) {
  const fin = list.filter((r) => r.o === 'F');
  const max = Math.max(0, ...fin.map((r) => r.p));
  const top = Math.min(20, Math.max(10, max));
  const rows: { k: number | string; n: number }[] = [];
  for (let k = 1; k <= top; k++) rows.push({ k, n: fin.filter((r) => r.p === k).length });
  const rest = fin.filter((r) => r.p > top).length;
  if (rest) rows.push({ k: `${top + 1}위 이하`, n: rest });
  return rows;
}

/** 완주 못 한 결과의 원인별 수(rankBars 자료). 0인 분류는 뺀다. */
export function causeBars(list: { o: string; rc?: string }[]) {
  const count = (f: (r: { o: string; rc?: string }) => boolean) => list.filter(f).length;
  const items = [
    { id: 'acc', name: CAUSE_KO.acc, v: count((r) => r.rc === 'acc') },
    { id: 'mech', name: CAUSE_KO.mech, v: count((r) => r.rc === 'mech') },
    { id: 'unk', name: CAUSE_KO.unk, v: count((r) => r.rc === 'unk') },
    { id: 'nc', name: CAUSE_KO.nc, v: count((r) => r.rc === 'nc') },
    { id: 'oth', name: '그 밖의 리타이어', v: count((r) => r.rc === 'oth') },
    { id: 'dsq', name: '실격', v: count((r) => r.o === 'D') },
    { id: 'dns', name: '출발 안 함', v: count((r) => r.o === 'N') },
  ];
  return items.filter((x) => x.v > 0).map((x) => ({ ...x, active: false }));
}

export function buildConstructor(c: ConstructorFile) {
  const rows = c.season_rows;
  const last = rows[rows.length - 1];

  // ---------------------------------------------------------------- 머리
  const engines = [...new Set(rows.map((r) => r.engine).filter(Boolean))] as string[];
  const facts: [string, string][] = [
    ['국적', c.nationality_ko ? esc(c.nationality_ko) : '미상'],
    ['결승', `${nw(span(c.first_season, c.last_season))}, ${c.seasons}개 시즌`],
    ['드라이버', `${c.drivers_n}명`],
  ];
  if (c.names.length > 1 || c.names[0] !== c.name) facts.push(['시즌 명칭', c.names.map((n) => `<span lang="en" class="nw">${esc(n)}</span>`).join(', ')]);
  const ex = rows.filter((r) => r.excluded);
  if (ex.length) facts.push(['순위 제외', `${ex.map((r) => r.s).join(', ')} (시즌 결과에서 제외)`]);
  const ded = rows.filter((r) => r.deducted);
  if (ded.length) facts.push(['감점 반영', ded.map((r) => r.s).join(', ')]);
  if (engines.length) facts.push(['엔진', engines.slice(-6).map((e) => `<span lang="en" class="nw">${esc(e)}</span>`).join(', ') + (engines.length > 6 ? ` 외 ${engines.length - 6}개` : '')]);

  const tiles = [
    {
      label: '컨스트럭터 챔피언',
      value: `${c.titles}번`,
      who: c.titles ? yearsText(c.title_seasons) : c.best != null ? `최고 순위 ${c.best}위${c.best_n > 1 ? `, ${c.best_n}번` : ''}` : c.last_season < STANDINGS_FROM ? '1958년 이전' : '순위 미부여',
    },
    { label: '우승', value: `${n0(c.wins)}번`, who: c.entries ? `출전 대회 대비 ${pc(c.wins, c.entries)}` : undefined },
    { label: '포디움', value: `${n0(c.podiums)}번`, who: `원투 ${c.one_two}번` },
    { label: '출전 대회', value: `${n0(c.entries)}개`, who: `결과 ${n0(c.cars)}개 (차 기준)` },
  ];

  // ---------------------------------------------------------------- 차트 자료
  const stepRows = rows
    .filter((r) => r.s >= STANDINGS_FROM)
    .map((r) => ({ s: r.s, pos: r.pos, pts: r.pts, cp: r.champ_pts, team: r.name, champ: r.pos === 1, ex: r.excluded }));
  const podRows = rows.map((r) => ({ s: r.s, e: r.cars, w: r.wins, p: r.podiums, team: r.name }));
  const outcomeRows = rows.map((r) => ({ s: r.s, n: r.cars, F: r.classified, mech: r.causes.mech, acc: r.causes.acc, other: otherOf(r), team: r.name }));
  const champOf = new Map(rows.filter((r) => r.driver_champ).map((r) => [r.s, r.driver_champ]));
  const roster = c.drivers.map((d) => ({
    key: d.id,
    name: d.name,
    seasons: d.seasons.map((s) => ({ s, champ: champOf.get(s) === d.id })),
    span: yearsText(d.seasons),
    e: d.n,
    w: d.w,
    p: d.p,
  }));

  return {
    rows,
    last,
    facts,
    tiles,
    stepRows,
    podRows,
    outcomeRows,
    roster,
  };
}

/** 시즌 쪽: 그 시즌 결과 행과 드라이버 순번, 요약 표 */
export function buildConstructorSeason(c: ConstructorFile, row: ConstructorSeasonRow) {
  const races = c.races.filter((r) => r.s === row.s);
  const drivers = [...row.drivers].sort((a, z) => z.n - a.n || (a.best ?? 99) - (z.best ?? 99));
  const fin = races.filter((r) => r.o === 'F').length;

  const tiles = [
    { label: '컨스트럭터 순위', value: row.pos ? `${row.pos}위` : row.excluded ? '제외' : '없음', who: row.pts != null ? `${pts(row.pts)}점` : row.s < STANDINGS_FROM ? '1958년 이전' : '순위 미부여' },
    { label: '우승', value: `${row.wins}번`, who: `${row.entries}개 대회 출전` },
    { label: '포디움', value: `${row.podiums}번`, who: `원투 ${row.one_two}번` },
    { label: '완주', value: pc(fin, races.length, 0) || '0%', who: `결과 ${races.length}개 중 ${fin}개` },
  ];

  const raceRows = races.map((r) => ({ ...r, name: drivers.find((d) => d.id === r.d)?.name ?? r.d }));
  return { races, raceRows, drivers, tiles };
}

export type { ConstructorRace };
