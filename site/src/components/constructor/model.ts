// 컨스트럭터 쪽(/constructors/<id>/, /constructors/<id>/<시즌>/)의 문장, 타일, 표, 차트 자료를
// constructor/<id>.json 하나(와 시즌 JSON)에서 빌드 때 만든다. 모든 수치는 그 파일(Jolpica 결과와 순위를
// pipeline/site_constructors.py가 센 값)에서 온다. 반환하는 문장은 HTML 문자열이고 데이터에서 온 글자는
// esc()를 거친다. 라틴 이름 뒤에는 받침에 따라 갈리는 조사를 붙이지 않는다.
import { span, yearsText } from '../driver/model.ts';
import type { ConstructorFile, ConstructorRace, ConstructorSeasonRow } from '../../lib/constructors-data.ts';
import { CAUSE_KO } from '../../lib/constructors-data.ts';
import { formatPoints, n0, num } from '../../lib/format.ts';
import { aside, b, en, esc, nw } from '../../lib/typeset.ts';

export const pts = (x: number | null | undefined) => (x == null ? '결측' : formatPoints(Math.round(x * 100) / 100));
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
  const nameHtml = en(esc(c.name));
  const last = rows[rows.length - 1];
  const ranked = rows.filter((r) => r.pos != null);

  // ---------------------------------------------------------------- 머리
  const firstLast = c.first_season === c.last_season ? `${c.first_season}년 한 시즌` : `${c.first_season}년부터 ${c.last_season}년까지 ${c.seasons}개 시즌`;
  let lead = `${b(nameHtml)}${c.nationality_ko ? aside(esc(c.nationality_ko)) : ''}의 결승 기록은 ${firstLast}, 출전 대회 ${b(`${n0(c.entries)}개`)}다.`;
  if (c.titles) lead += ` 컨스트럭터 챔피언 ${b(`${c.titles}번`)}${aside(yearsHtml(c.title_seasons))}, 우승 ${n0(c.wins)}번, 포디움 ${n0(c.podiums)}번을 기록했다.`;
  else if (c.wins) lead += ` 우승 ${b(`${c.wins}번`)}, 포디움 ${c.podiums}번을 기록했고${c.best ? `, 가장 높은 컨스트럭터 순위는 ${c.best}위` : ''}다.`;
  else if (c.podiums) lead += ` 포디움은 ${b(`${c.podiums}번`)}이다.`;
  else if (c.best != null) lead += ` 가장 높은 컨스트럭터 순위는 ${b(`${c.best}위`)}다.`;
  if (c.driver_titles) lead += ` 그 시즌 드라이버 챔피언이 이 컨스트럭터로 나선 시즌은 ${c.driver_titles}개${aside(yearsHtml(c.driver_title_seasons))}다.`;
  if (c.in_2025 && last) lead += ` 2025 시즌에는 ${last.pos ? `컨스트럭터 순위 ${last.pos}위${aside(`${pts(last.pts)}점`)}로 마쳤다` : '컨스트럭터 순위를 받지 못했다'}.`;

  const engines = [...new Set(rows.map((r) => r.engine).filter(Boolean))] as string[];
  const facts: [string, string][] = [
    ['국적', c.nationality_ko ? esc(c.nationality_ko) : '결측'],
    ['결승', `${nw(span(c.first_season, c.last_season))}, ${c.seasons}개 시즌`],
    ['드라이버', `${c.drivers_n}명`],
  ];
  if (c.names.length > 1 || c.names[0] !== c.name) facts.push(['시즌 명칭', c.names.map((n) => `<span lang="en" class="nw">${esc(n)}</span>`).join(', ')]);
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

  // ---------------------------------------------------------------- 절 문장
  const n1 = ranked.filter((r) => r.pos === 1).length;
  const n3 = ranked.filter((r) => (r.pos as number) <= 3).length;
  const stRows = rows.filter((r) => r.s >= STANDINGS_FROM);
  let stRead = stRows.length
    ? ranked.length
      ? `컨스트럭터 순위가 있는 ${STANDINGS_FROM}년부터 ${stRows.length}개 시즌을 달렸고, 순위를 받은 ${ranked.length}개 시즌 가운데 1위는 ${b(`${n1}번`)}, 3위 안은 ${n3}번이다.`
      : `${STANDINGS_FROM}년부터 ${stRows.length}개 시즌을 달렸지만 컨스트럭터 순위를 받은 시즌은 0개다.`
    : '';
  const ex = rows.filter((r) => r.excluded);
  if (ex.length) stRead += ` ${ex.map((r) => r.s).join(', ')}년은 시즌 결과에서 제외되어 순위가 없다.`;
  const ded = rows.filter((r) => r.deducted);
  if (ded.length) stRead += ` ${ded.map((r) => r.s).join(', ')}년은 감점이 반영된 점수다.`;

  const topW = rows.reduce((a, r) => (r.wins > a.wins ? r : a), rows[0]);
  const topP = rows.reduce((a, r) => (r.podiums > a.podiums ? r : a), rows[0]);
  const winRead = c.wins
    ? `우승은 ${rows.filter((r) => r.wins).length}개 시즌에서 나왔다. 한 시즌 최다 우승은 ${b(`${topW.s}년 ${topW.wins}번`)}${aside(`${topW.entries}개 대회 출전`)}이고, 포디움이 가장 많은 시즌은 ${topP.s}년${aside(`${topP.podiums}번`)}이다.`
    : c.podiums
      ? `포디움은 ${rows.filter((r) => r.podiums).length}개 시즌에서 ${b(`${c.podiums}번`)}이다. 가장 많은 시즌은 ${topP.s}년${aside(`${topP.podiums}번`)}이다.`
      : '우승과 포디움은 0번이다.';

  const top = c.drivers[0];
  const winners = [...c.drivers].filter((d) => d.w > 0).sort((a, z) => z.w - a.w || z.n - a.n);
  let rosterRead = `결승에 나선 드라이버는 ${b(`${c.drivers_n}명`)}이다. 가장 많이 나선 드라이버는 ${en(esc(top.name))}${aside(`${top.n}개 대회, ${yearsHtml(top.seasons)}`)}다.`;
  if (winners.length) rosterRead += ` 이 컨스트럭터로 가장 많이 우승한 드라이버는 ${en(esc(winners[0].name))}${aside(`${winners[0].w}번`)}다.`;

  const cars = rows.reduce((a, r) => a + r.cars, 0);
  const fin = rows.reduce((a, r) => a + r.classified, 0);
  const mech = rows.reduce((a, r) => a + r.causes.mech, 0);
  const acc = rows.reduce((a, r) => a + r.causes.acc, 0);
  const relRead = `결과 ${n0(cars)}개 가운데 완주로 분류된 결과는 ${b(`${n0(fin)}개`)}${aside(pc(fin, cars))}다. 완주하지 못한 결과 가운데 차량 문제는 ${n0(mech)}개, 사고·충돌은 ${n0(acc)}개다.${
    c.last_season >= 2023 ? ' 2023년부터의 리타이어는 Jolpica가 원인을 적지 않아(Retired) 원인 미기재로 센다.' : ''
  }`;

  return {
    rows,
    last,
    lead,
    facts,
    tiles,
    stepRows,
    podRows,
    outcomeRows,
    roster,
    reads: { st: stRead, win: winRead, roster: rosterRead, rel: relRead },
  };
}

/** 시즌 쪽: 그 시즌 결과 행과 드라이버 순번, 문장 */
export function buildConstructorSeason(c: ConstructorFile, row: ConstructorSeasonRow) {
  const races = c.races.filter((r) => r.s === row.s);
  const drivers = [...row.drivers].sort((a, z) => z.n - a.n || (a.best ?? 99) - (z.best ?? 99));
  const nameHtml = en(esc(row.name));
  const fin = races.filter((r) => r.o === 'F').length;

  let lead = `${row.s} 시즌 ${b(nameHtml)}${row.engine ? aside(`엔진 ${esc(row.engine)}`) : ''}의 결승 기록이다. ${row.rounds}개 대회 가운데 ${b(`${row.entries}개`)}에 나섰다.`;
  if (row.pos != null) lead += ` 컨스트럭터 순위는 ${b(`${row.pos}위`)}${aside(`${pts(row.pts)}점${row.champ_pts && row.pos !== 1 ? `, 1위 ${pts(row.champ_pts)}점` : ''}`)}다.`;
  else if (row.excluded) lead += ' 시즌 결과에서 제외되어 컨스트럭터 순위가 없다.';
  else if (row.s >= STANDINGS_FROM) lead += ' 컨스트럭터 순위를 받지 못했다.';
  else lead += ` 컨스트럭터 순위는 ${STANDINGS_FROM}년부터다.`;
  if (row.wins) lead += ` 우승 ${row.wins}번, 포디움 ${row.podiums}번${row.one_two ? `, 원투 ${row.one_two}번` : ''}이다.`;
  else if (row.podiums) lead += ` 포디움은 ${row.podiums}번이다.`;

  const tiles = [
    { label: '컨스트럭터 순위', value: row.pos ? `${row.pos}위` : row.excluded ? '제외' : '없음', who: row.pts != null ? `${pts(row.pts)}점` : row.s < STANDINGS_FROM ? '1958년 이전' : '순위 미부여' },
    { label: '우승', value: `${row.wins}번`, who: `${row.entries}개 대회 출전` },
    { label: '포디움', value: `${row.podiums}번`, who: `원투 ${row.one_two}번` },
    { label: '완주', value: pc(fin, races.length, 0) || '0%', who: `결과 ${races.length}개 중 ${fin}개` },
  ];

  const outs = races.filter((r) => r.o !== 'F');
  const causeText = (['acc', 'mech', 'unk', 'nc', 'oth'] as const)
    .filter((k) => row.causes[k])
    .map((k) => `${CAUSE_KO[k]} ${row.causes[k]}개`)
    .concat(row.dsq ? [`실격 ${row.dsq}개`] : [], row.dns ? [`출발 안 함 ${row.dns}개`] : [])
    .join(', ');
  const stripRead = `${drivers.length}명이 ${races.length}개 결과를 냈다. 완주로 분류된 결과는 ${b(`${fin}개`)}이고, 완주하지 못한 결과는 ${outs.length}개${causeText ? aside(causeText) : ''}다.`;

  const raceRows = races.map((r) => ({ ...r, name: drivers.find((d) => d.id === r.d)?.name ?? r.d }));
  return { races, raceRows, drivers, lead, tiles, reads: { strip: stripRead } };
}

export type { ConstructorRace };
