// 팀 페이지(/teams/<계보>/)가 빌드 때 쓰는 계산. 문장, 표, 차트 자료를 모두 생성 JSON에서 만든다.
// 문장 틀은 design/final/src/build.py의 build_team(), team_sentences()를 따른다. 수치를 고정 문자열로 두지 않는다.
import { getSeason, labels, meta, upgrades } from '../../lib/data.ts';
import { qualiRounds, raceRounds, railData } from '../../lib/chart-data.ts';
import { formatPoints, hasBatchim, josa, n0, num, pct } from '../../lib/format.ts';
import { aside, b, en, esc } from '../../lib/typeset.ts';
import { driverLink } from '../../lib/driver-links.ts';
import type { ReasonCategory, Team, TeamSeasonRow, TimelineRound, UpgradeItem } from '../../lib/types.ts';

export const CATS: ReasonCategory[] = ['performance', 'circuit_specific', 'reliability', 'other'];

/** 한글이나 숫자 뒤의 "로/으로". ㄹ 받침 뒤에는 "로"다. 라틴 이름 뒤에는 쓰지 않는다. */
export function ro(word: string): string {
  const ch = word.trim().slice(-1);
  let rieul = false;
  if (ch >= '가' && ch <= '힣') rieul = (ch.charCodeAt(0) - 0xac00) % 28 === 8;
  else if (/\d/.test(ch)) rieul = '178'.includes(ch);
  return word + (hasBatchim(word) && !rieul ? '으로' : '로');
}

/** "엔스톤 (알핀)" -> "엔스톤" */
export function lineageShort(nameKo: string): string {
  return nameKo.replace(/\s*\(.*\)\s*$/, '');
}

/** 이름으로 묶은 계보 구간(계보 띠와 시대 경계). 같은 이름이 겹치거나 바로 이어지면 한 칸으로 합친다. */
export interface Era {
  team: string;
  from: number;
  to: number;
  ids: string[];
  link: string;
  current: boolean;
}

export function eraGroups(team: Team, cur: { team: string; from: number; to: number }): Era[] {
  const sorted = [...team.segments].sort((a, b2) => a.from - b2.from || a.to - b2.to);
  const out: Era[] = [];
  for (const s of sorted) {
    const prev = out[out.length - 1];
    if (prev && prev.team === s.team_name && s.from <= prev.to + 1) {
      prev.to = Math.max(prev.to, s.to);
      if (!prev.ids.includes(s.constructor_id)) prev.ids.push(s.constructor_id);
      continue;
    }
    out.push({ team: s.team_name, from: s.from, to: s.to, ids: [s.constructor_id], link: s.link_type_ko, current: false });
  }
  for (const e of out) e.current = e.team === cur.team && e.from <= cur.from && e.to >= cur.to;
  return out;
}

export interface Totals {
  seasons: number;
  races: number;
  wins: number;
  podiums: number;
  titles: number[];
  best: number | null;
}

/** 시즌 행에서 합계를 센다(team.totals와 같은 방법이다: 시즌 수, 결승 출전, 우승, 포디움, 1위 시즌). */
export function totalsOf(rows: TeamSeasonRow[]): Totals {
  const pos = rows.map((r) => r.position).filter((p): p is number => p != null);
  return {
    seasons: new Set(rows.map((r) => r.season)).size,
    races: rows.reduce((a, r) => a + r.entered, 0),
    wins: rows.reduce((a, r) => a + r.race_wins, 0),
    podiums: rows.reduce((a, r) => a + r.podiums, 0),
    titles: [...new Set(rows.filter((r) => r.position === 1).map((r) => r.season))].sort((a, c) => a - c),
    best: pos.length ? Math.min(...pos) : null,
  };
}

/** 한 시즌에 Jolpica ID가 여럿인 계보(초기 McLaren, 2006 Midland/Spyker MF1)에서 시즌 대표 행을 고른다. */
function mainRow(rows: TeamSeasonRow[], by: 'standing' | 'quali'): TeamSeasonRow {
  if (rows.length === 1) return rows[0];
  const sorted = [...rows].sort((a, c) => {
    if (by === 'quali') return c.quali_rounds - a.quali_rounds || c.entered - a.entered;
    if (a.position != null && c.position != null) return a.position - c.position;
    if (a.position != null) return -1;
    if (c.position != null) return 1;
    return c.entered - a.entered;
  });
  return sorted[0];
}

function groupBySeason(rows: TeamSeasonRow[]): Map<number, TeamSeasonRow[]> {
  const m = new Map<number, TeamSeasonRow[]>();
  for (const r of rows) {
    if (!m.has(r.season)) m.set(r.season, []);
    m.get(r.season)!.push(r);
  }
  return m;
}

function rangeText(a: number, c: number): string {
  return a === c ? String(a) : `${a}-${c}`;
}

/** 이름 목록: "AlphaTauri, RB, Racing Bulls" */
function listNames(names: string[]): string {
  return names.map((n) => en(esc(n))).join(', ');
}

export function buildTeam(team: Team) {
  const C = team.constructor.name;
  const Ce = en(esc(C));
  const short = lineageShort(team.name_ko);
  const last = meta.last_season;
  const first = Math.min(...team.segments.map((s) => s.from));
  const lastTo = Math.max(...team.segments.map((s) => s.to));

  // 현재 컨스트럭터 구간: 마지막 시즌까지 이어진 현재 Jolpica ID 구간 가운데 가장 이른 것.
  const curSeg =
    team.segments
      .filter((s) => s.constructor_id === team.constructor.id && s.to === lastTo)
      .sort((a, c) => a.from - c.from)[0] ?? team.segments[team.segments.length - 1];
  const curFrom = Math.min(curSeg.from, team.current_from);
  const eras = eraGroups(team, { team: curSeg.team_name, from: curSeg.from, to: curSeg.to });
  const hasSwitch = curFrom > first;

  const bySeason = groupBySeason(team.seasons);
  const seasonsAsc = [...bySeason.keys()].sort((a, c) => a - c);
  const totLin = totalsOf(team.seasons);
  const totCur = totalsOf(team.seasons.filter((r) => r.season >= curFrom));

  // ---------------------------------------------------------------- 머리
  const lastRows = bySeason.get(last) ?? [];
  const row25 = lastRows.find((r) => r.constructor_id === team.constructor.id) ?? mainRow(lastRows, 'standing');
  let lead = '';
  if (row25) {
    lead = `${Ce} 팀은 ${last} 시즌을 컨스트럭터 순위 ${b(`${row25.position ?? '미부여'}${row25.position ? '위' : ''}`)}${aside(`${formatPoints(row25.points)}점`)}로 마쳤다.`;
    if (row25.quali_index_mean != null) {
      lead +=
        ` 마른 예선 ${row25.quali_rounds}개 대회에서 팀 최고 랩은 세션 최고 랩보다 평균 ${b(pct(row25.quali_index_mean))} 느렸고, ` +
        (row25.quali_rank === 1
          ? `이 평균은 ${row25.quali_teams}개 팀 가운데 가장 작다.`
          : `이 평균은 ${row25.quali_teams}개 팀 가운데 ${row25.quali_rank}번째다.`);
    }
  }
  const baseCity = team.base.split(',')[0].trim();
  const latin = `${baseCity} · ${C}`;
  const facts: [string, string][] = [
    [`${last} 컨스트럭터`, Ce],
    ['참가 명칭', team.entrant ? en(esc(team.entrant)) : '결측'],
    ['거점', en(esc(team.base))],
    [`PU 공급사 (${last})`, team.pu ? en(esc(team.pu.name)) : '결측'],
    [
      `${last} 드라이버`,
      team.drivers_last.map((d) => `<span lang="en" class="nw">${driverLink(d.id, esc(d.name))}</span>`).join(', ') || '결측',
    ],
  ];

  // ---------------------------------------------------------------- 범위 막대
  const nameCount = eras.length > 1 ? `이름 ${eras.length}개 구간` : `Jolpica ID ${team.segments.length}개 구간`;
  const idNote = eras.length > 1 ? '' : ` (Jolpica ID <span class="mono">${esc(team.constructor.id)}</span> 구간)`;
  const scopeOn = hasSwitch
    ? `보는 범위: <b>${esc(short)} 계보 전체 ${first}-${lastTo}</b>, ${nameCount}. 계보 띠, 긴 흐름 차트, 시즌별 기록에 적용된다.`
    : `보는 범위: <b>${Ce} ${first}-${lastTo}</b>. 계보 전체가 한 컨스트럭터라 계보 보기 전환을 두지 않는다.`;
  const paceYears = Object.keys(team.upgrades.timeline).map(Number).sort((a, c) => a - c);
  const py0 = paceYears[0];
  const pyN = paceYears[paceYears.length - 1];
  const paceNames = [...new Set(team.seasons.filter((r) => r.season >= py0).map((r) => r.team_name))];
  const scopeOff =
    `보는 범위: <b>현재 컨스트럭터 ${Ce} ${rangeText(curFrom, lastTo)}</b>${idNote}. ` +
    (curFrom <= py0
      ? `업그레이드와 시즌 안의 페이스는 원래 ${Ce} 시기다.`
      : `업그레이드와 시즌 안의 페이스(${py0}-${pyN})는 이 전환과 관계없이 앞 이름(${listNames(paceNames.filter((n) => n !== C))}) 시기를 함께 싣는다.`);

  // ---------------------------------------------------------------- 계보
  const changes = eras.length - 1;
  let linRead =
    changes > 0
      ? `${esc(short)} 계보는 ${first}년 ${en(esc(eras[0].team))}에서 출발해 이름이 ${changes}번 바뀌며 ${lastTo}년 ${Ce}까지 이어진다. `
      : `${esc(short)} 계보는 ${first}년부터 ${lastTo}년까지 ${Ce} 이름 하나로 이어진다. `;
  linRead +=
    totLin.wins > 0
      ? `${totLin.seasons}개 시즌 동안 ${n0(totLin.races)}개 대회에 나가 ${totLin.wins}번 우승했고, `
      : `${totLin.seasons}개 시즌 동안 ${n0(totLin.races)}개 대회에 나갔고 우승은 0번이다. `;
  if (totLin.titles.length === 0) {
    linRead += `컨스트럭터 순위의 가장 높은 자리는 ${totLin.best}위다.`;
  } else if (totLin.titles.length <= 6) {
    linRead += `컨스트럭터 챔피언은 ${totLin.titles.join(', ')}년 ${totLin.titles.length}번이다.`;
  } else {
    linRead += `컨스트럭터 챔피언은 ${totLin.titles.length}번이고 마지막은 ${totLin.titles[totLin.titles.length - 1]}년이다.`;
  }
  const segNotes = [...new Set(team.segments.map((s) => s.note).filter((n): n is string => Boolean(n)))];
  const linNotes: { head: string; body: string; caution?: boolean }[] = [
    {
      head: '읽는 법',
      body:
        `칸 너비는 시즌 수에 비례한다. 파란 윗줄이 ${last} 컨스트럭터다.` +
        (hasSwitch ? ` 계보 보기를 끄면 ${Ce} 시기(${rangeText(curFrom, lastTo)})만 남는다.` : ''),
    },
  ];
  if (segNotes.length) {
    linNotes.push({ head: '주의', body: segNotes.map((n) => `${esc(n)}.`).join(' '), caution: true });
  }
  const evidenceDates = team.evidence.map((e) => e.verified_on).sort();
  const evidenceOn = evidenceDates[evidenceDates.length - 1] ?? null;

  // ---------------------------------------------------------------- 업그레이드
  const items: UpgradeItem[] = upgrades.items.filter((i) => i.lineage_id === team.lineage_id);
  const cats = Object.fromEntries(CATS.map((c) => [c, items.filter((i) => i.category === c).length])) as Record<ReasonCategory, number>;
  const tl = team.upgrades.timeline;
  const tlRows: (TimelineRound & { season: number })[] = paceYears.flatMap((s) => (tl[String(s)] ?? []).map((r) => ({ ...r, season: s })));
  const withItems = tlRows.filter((r) => r.n > 0);
  const maxN = Math.max(0, ...withItems.map((r) => r.n));
  const tops = withItems.filter((r) => r.n === maxN);
  const who = curFrom <= py0 ? `${Ce} 팀이` : `${esc(short)} 계보가`;
  let upRead = '';
  if (items.length) {
    const catParts = CATS.filter((c) => cats[c] > 0).map((c, k) =>
      k === 0 ? `${labels.reason_categories[c]} 범주가 ${cats[c]}건` : `${josa(labels.reason_categories[c], '이', '가')} ${cats[c]}건`,
    );
    const topText = tops.map((r) => `${r.season}년 ${r.round}라운드 ${esc(r.short)}`).join(', ');
    upRead =
      `${who} ${py0}-${pyN}년 FIA 문서에 신고한 항목은 ${b(`${items.length}건`)}이고 ${withItems.length}개 대회에 걸쳐 있다. ` +
      `${catParts.join(', ')}이다. ` +
      `한 대회 최다는 ${maxN}건으로 ${josa(topText, '이다', '다')}.`;
    if (curFrom > py0) upRead += ` 이 기간의 이름은 ${listNames(paceNames)}다.`;
  } else {
    upRead = `${who} ${py0}-${pyN}년 FIA 문서에 신고한 항목은 0건이다.`;
  }
  const upMeta = curFrom <= py0 ? `${py0}-${pyN} · ${Ce} 시기만` : `${py0}-${pyN} · ${listNames(paceNames)}`;
  const docs = upgrades.documents;
  const docYears = paceYears.map((y) => ({ y, n: docs.filter((d) => d.season === y).length, rounds: (tl[String(y)] ?? []).length }));
  const partial = docYears.filter((d) => d.n > 0 && d.n < d.rounds * 0.5);
  const missingLate = upgrades.missing_events.filter((m) => !partial.some((p) => p.y === m.season));
  let scopeNote = 'FIA가 공개한 문서만 싣는다. ';
  scopeNote += partial.map((p) => `${p.y}년은 ${p.n}개 대회 문서만 있고`).join(', ');
  if (missingLate.length) {
    scopeNote += `${partial.length ? ' ' : ''}${missingLate.map((m) => `${m.season}년 ${m.round}라운드 ${esc(m.event_short_ko)}`).join(', ')} 문서는 찾지 못했다. `;
  } else if (partial.length) {
    scopeNote += ' 나머지 대회는 문서가 있다. ';
  }
  scopeNote += '회색 띠가 공개 문서가 없는 대회, 바닥의 짧은 선이 변경 0건이다.';
  const reviewDocs = docs.filter((d) => d.review && d.season >= py0);
  const reviewNote = reviewDocs.length
    ? reviewDocs
        .map((d) => {
          const who2 = d.teams.filter((t) => t.status === 'needs_review').map((t) => en(esc(t.team)));
          const mine = d.teams.find((t) => t.lineage_id === team.lineage_id);
          const mineText = mine?.status === 'needs_review' ? ' 이 팀 쪽이 그 대상이라 이 대회의 항목 수를 0으로 세지 않고 비워 둔다.' : '';
          return `${d.season}년 ${d.round}라운드 ${esc(d.event_short_ko)} 문서는 ${who2.join(', ') || '일부 팀'} 쪽 표가 그림으로만 들어 있어 문서 전체를 검수 대기로 둔다.${mineText}`;
        })
        .join(' ') + ' 읽지 못한 칸을 추측으로 채우지 않는다.'
    : '';

  // 대회 고르기: 신고가 있는 대회, 최근 먼저. 처음 고른 대회는 마지막 시즌의 마지막 신고 대회.
  const evOptions = [...withItems]
    .sort((a, c) => c.season - a.season || c.round - a.round)
    .map((r) => ({ value: `${r.season}-${r.round}`, label: `${r.season} ${r.round}라운드 ${r.short} (${r.n}건${r.doc_review ? ', 검수 대기 문서' : ''})` }));
  const sel = evOptions.length ? withItems.find((r) => `${r.season}-${r.round}` === evOptions[0].value)! : null;
  const selItems = sel ? items.filter((i) => i.season === sel.season && i.round === sel.round) : [];
  const options = evOptions.map((o, k) => ({ ...o, selected: k === 0 }));

  // ---------------------------------------------------------------- 시즌 안의 페이스
  const pace: Record<string, PaceYear> = {};
  for (const y of paceYears) pace[String(y)] = paceYear(team, y, bySeason.get(y) ?? []);

  // ---------------------------------------------------------------- 긴 흐름
  const stepsData = seasonsAsc.map((s) => {
    const r = mainRow(bySeason.get(s)!, 'standing');
    return { season: s, team: r.team_name, pos: r.position, pts: r.points ?? 0, wins: r.race_wins };
  });
  const trendRows = seasonsAsc
    .map((s) => mainRow(bySeason.get(s)!, 'quali'))
    .filter((r) => r.quali_index_mean != null);
  const trendData = trendRows.map((r) => ({
    season: r.season,
    team: r.team_name,
    q: r.quali_index_mean,
    ref: r.quali_reference,
    field: r.quali_field,
    qn: r.quali_rounds,
    qwet: r.quali_wet_rounds,
  }));
  const qFirst = trendRows.length ? trendRows[0].season : Math.max(1996, first);
  const qCur = Math.max(qFirst, curFrom);
  const solid = trendRows.filter((r) => !r.quali_reference);
  const refRows = trendRows.filter((r) => r.quali_reference);
  const refRange = refRows.length ? rangeText(refRows[0].season, refRows[refRows.length - 1].season) : '';
  const extreme = (list: TeamSeasonRow[]) => {
    if (!list.length) return null;
    const best = list.reduce((a, c) => (c.quali_index_mean! < a.quali_index_mean! ? c : a), list[0]);
    const worst = list.reduce((a, c) => (c.quali_index_mean! > a.quali_index_mean! ? c : a), list[0]);
    return { best, worst };
  };
  const exOn = extreme(solid);
  let longOn = '';
  if (exOn) {
    const lbl = hasSwitch ? `${esc(short)} 계보의` : `${Ce} 팀의`;
    longOn =
      exOn.best === exOn.worst
        ? `${qFirst}-${lastTo}년 ${lbl} 시즌 평균은 ${b(pct(exOn.best.quali_index_mean))}다.`
        : `${qFirst}-${lastTo}년 ${lbl} 시즌 평균이 가장 작았던(빨랐던) 해는 ${b(`${exOn.best.season}년`)}${aside(`${esc(exOn.best.team_name)}, ${pct(exOn.best.quali_index_mean)}`)}이고, ` +
          `가장 컸던 해는 ${b(`${exOn.worst.season}년`)}${aside(`${esc(exOn.worst.team_name)}, ${pct(exOn.worst.quali_index_mean)}`)}이다.`;
    if (refRows.length) longOn += ` 참고용 형식인 ${refRange}년은 이 비교에서 뺐다.`;
  }
  const exOff = extreme(solid.filter((r) => r.season >= curFrom));
  let longOff = longOn;
  if (hasSwitch && exOff) {
    const span = rangeText(qCur, lastTo);
    longOff =
      exOff.best === exOff.worst
        ? `${Ce} 시기(${span})의 시즌 평균은 ${b(pct(exOff.best.quali_index_mean))}다.`
        : `${Ce} 시기(${span})의 시즌 평균이 가장 작았던 해는 ${b(`${exOff.best.season}년`)}${aside(pct(exOff.best.quali_index_mean))}이고, 가장 컸던 해는 ${b(`${exOff.worst.season}년`)}${aside(pct(exOff.worst.quali_index_mean))}이다.`;
  }
  const chartEras = eras.map((e) => ({ team: e.team, from: e.from, to: e.to }));
  const linScope = {
    steps: { on: `${first}-${lastTo} · ${short} 계보 전체`, off: `${rangeText(curFrom, lastTo)} · ${C} 시기만` },
    trend: {
      on: `${qFirst}-${lastTo} · ${hasSwitch ? `${short} 계보 전체` : C}${qFirst > first ? ` (예선 지수는 ${qFirst}년부터)` : ''}`,
      off: `${rangeText(qCur, lastTo)} · ${C} 시기만`,
    },
    meta: { on: `범위: ${short} 계보 전체`, off: `범위: ${C} 시기 (${rangeText(curFrom, lastTo)})` },
  };
  if (!hasSwitch) {
    linScope.steps.on = `${first}-${lastTo} · ${C}`;
    linScope.meta.on = `범위: ${C} ${first}-${lastTo}`;
  }

  // ---------------------------------------------------------------- 시즌별 기록
  const eraStarts = new Set(eras.map((e) => e.from));
  const recordRows = [...team.seasons].sort((a, c) => c.season - a.season || a.constructor_id.localeCompare(c.constructor_id));
  const dupSeasons = new Set([...bySeason].filter(([, v]) => v.length > 1).map(([k]) => k));
  const firstRest = recordRows[10];
  const restSeasons = firstRest ? new Set(recordRows.slice(10).map((r) => r.season)).size : 0;

  // ---------------------------------------------------------------- PU 공급사 구간
  const puSpans: { from: number; to: number; pu: string; teams: string[] }[] = [];
  for (const s of seasonsAsc) {
    const rows = bySeason.get(s)!;
    const pu = [...new Set(rows.map((r) => r.pu?.name ?? '결측'))].join(' · ');
    const names = [...new Set(rows.map((r) => r.team_name))];
    const prev = puSpans[puSpans.length - 1];
    if (prev && prev.pu === pu && prev.to === s - 1) {
      prev.to = s;
      for (const n of names) if (!prev.teams.includes(n)) prev.teams.push(n);
    } else puSpans.push({ from: s, to: s, pu, teams: names });
  }
  puSpans.reverse();

  return {
    C,
    Ce,
    short,
    last,
    first,
    lastTo,
    curFrom,
    hasSwitch,
    eras,
    chartEras,
    lead,
    latin,
    facts,
    scopeOn,
    scopeOff,
    totLin,
    totCur,
    linRead,
    linNotes,
    evidenceOn,
    items,
    cats,
    tlRows,
    upRead,
    upMeta,
    scopeNote,
    reviewNote,
    options,
    sel,
    selItems,
    paceYears,
    pace,
    stepsData,
    trendData,
    qFirst,
    qCur,
    refRows: refRows.length,
    refRange,
    longOn,
    longOff,
    linScope,
    eraStarts,
    recordRows,
    dupSeasons,
    restSeasons,
    firstRest: firstRest?.season ?? null,
    puSpans,
  };
}

export interface PaceYear {
  year: number;
  cid: string;
  team: string;
  quali: ReturnType<typeof qualiRounds>;
  race: ReturnType<typeof raceRounds>;
  rail: { round: number; n: number }[];
  /** 라운드 -> 신고 건수 */
  railBy: Record<number, number>;
  q: string;
  r: string;
  src: string;
  f1dbRounds: number[];
}

function paceYear(team: Team, year: number, rows: TeamSeasonRow[]): PaceYear {
  const season = getSeason(year);
  const ids = new Set(season.constructors.map((c) => c.id));
  const row = rows.find((r) => ids.has(r.constructor_id)) ?? rows[0];
  const cid = row?.constructor_id ?? team.constructor.id;
  const name = row?.team_name ?? team.constructor.name;
  const N = en(esc(name));
  const quali = qualiRounds(season);
  const race = raceRounds(season);
  const rail = railData(team, year);
  const railBy = Object.fromEntries(rail.map((r) => [r.round, r.n]));

  const qs = quali.filter((r) => r.wet !== 'wet' && r.teams[cid] != null);
  let q = `${year} 시즌 ${N}의 예선 지수는 0개 대회에 있다.`;
  if (qs.length) {
    const vals = qs.map((r) => r.teams[cid] as number);
    const mean = vals.reduce((a, c) => a + c, 0) / vals.length;
    const faster = qs.filter((r) => r.field && (r.teams[cid] as number) < r.field.med).length;
    const best = qs.reduce((a, c) => ((c.teams[cid] as number) < (a.teams[cid] as number) ? c : a), qs[0]);
    const bv = best.teams[cid] as number;
    const sorted = Object.values(best.teams).filter((x): x is number => x != null).sort((a, c) => a - c);
    const rank = sorted.indexOf(bv) + 1;
    q =
      `${year} 시즌 마른 예선 ${qs.length}개 대회의 평균은 ${b(pct(mean))}다. 그 대회의 필드 중앙값보다 빨랐던 예선은 ${faster}번이다. ` +
      (rank === 1
        ? `팀 최고 랩이 그 세션의 최고 랩이었던 예선(지수 0)은 ${qs.filter((r) => (r.teams[cid] as number) <= bv).length}번이고, 처음은 ${best.round}라운드 ${josa(best.short, '이다', '다')}.`
        : `가장 좋았던 예선은 ${best.round}라운드 ${ro(best.short)}, 지수 ${pct(bv)}에 ${sorted.length}개 팀 중 ${rank}번째였다.`);
  }
  const rs = race.filter((r) => !r.wet && r.teams[cid]);
  const slow = rs.filter((r) => (r.teams[cid]![1] ?? -Infinity) > 0).length;
  const fast = rs.filter((r) => (r.teams[cid]![2] ?? Infinity) < 0).length;
  const mid = rs.length - slow - fast;
  const missing = race.filter((r) => !r.wet && !r.teams[cid]).length;
  let rr: string;
  if (!rs.length) {
    rr = `${year} 시즌 ${N}의 레이스 지수가 있는 마른 결승은 0개다.`;
  } else if (!slow && !fast) {
    rr = `${year} 시즌 마른 결승 ${rs.length}개 대회 모두 95% 구간이 0에 걸쳐 필드 중앙값과 구별되지 않는다.`;
  } else {
    // 많은 쪽을 먼저 굵게 적고, 반대쪽과 0에 걸친 대회 수를 잇는다.
    const main = slow >= fast ? { n: slow, side: '느린' } : { n: fast, side: '빠른' };
    const other = slow >= fast ? { n: fast, side: '빠른' } : { n: slow, side: '느린' };
    const otherText = other.n === 0 ? `구간 전체가 ${other.side} 쪽에 있던 대회는 없` : `구간 전체가 ${other.side} 쪽에 있던 대회는 ${other.n}개이`;
    rr =
      `${year} 시즌 마른 결승 ${rs.length}개 대회 가운데 ${b(`${main.n}개 대회`)}에서 95% 구간 전체가 필드 중앙값보다 ${main.side} 쪽에 있었다. ` +
      (mid > 0
        ? `${otherText}고, 나머지 ${mid}개 대회는 구간이 0에 걸쳐 필드 중앙값과 구별되지 않는다.`
        : `${otherText}다.`);
  }
  if (rs.length && missing) rr += ` 클린 랩이 모자라 지수가 없는 마른 대회는 ${missing}개다.`;
  const f1dbRounds = season.rounds.filter((r) => r.quali?.source === 'f1db').map((r) => r.round);
  return { year, cid, team: name, quali, race, rail, railBy, q, r: rr, src: '', f1dbRounds };
}

export { num, pct, n0, formatPoints };
