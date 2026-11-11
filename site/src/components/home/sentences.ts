// 홈 문장 틀. design/final/src/build.py의 build_home(), finish_fact(), round_note(), caution_example()을 옮겼다.
// 모든 수치는 home.json에서 센다. 돌려주는 값은 HTML 조각이고, 데이터에서 온 이름은 esc()를 거친다.
import { ivl, josa, n0, num, pct } from '../../lib/format.ts';
import type { ClassificationRow, Home, HomeRace, UpgradeWeekend } from '../../lib/types.ts';
import { aside, b, esc, nw } from '../../lib/typeset.ts';

const EN_NO_UPDATES = '<span lang="en">No updates submitted</span>';

/** 최종전인지: 라운드가 시즌 라운드 수와 같다 */
export function isFinal(h: Home): boolean {
  return h.race.round === h.rounds_in_season;
}

/** 순위가 있는 결과 행(결승 순서) */
export function ranked(h: Home): ClassificationRow[] {
  return h.classification.filter((c) => c.position != null).sort((a, z) => (a.position ?? 0) - (z.position ?? 0));
}

/** 결과 표의 기록 칸: 차이에는 '초'를 붙인다(랩 차이와 우승 기록은 그대로). 기록이 없으면 '미완주' */
export function timeText(c: ClassificationRow): string {
  if (!c.time) return c.classified ? '결측' : '미완주';
  return c.time.startsWith('+') && !c.time.includes('랩') ? `${c.time}초` : c.time;
}

/** 사실 줄 완주: '20대 (1랩 뒤진 차 4대)' */
export function finishFact(h: Home): string {
  const cl = ranked(h);
  const fin = cl.filter((c) => c.classified);
  const leaderLaps = cl[0]?.laps ?? 0;
  const lapped = new Map<number, number>();
  for (const c of fin) {
    const down = leaderLaps - (c.laps ?? leaderLaps);
    if (down > 0) lapped.set(down, (lapped.get(down) ?? 0) + 1);
  }
  const tail = [...lapped.entries()]
    .sort((a, z) => a[0] - z[0])
    .map(([k, n]) => `${k}랩 뒤진 차 ${n}대`)
    .join(', ');
  return `${fin.length}대${tail ? ` (${tail})` : ''}`;
}

/** 페이지 리드: 우승자와 출발 위치, 예선 1위 팀과 2위 팀의 차이 */
export function homeLead(h: Home): string {
  const race = h.race;
  const win = ranked(h)[0];
  const where = isFinal(h) ? `${h.season} 시즌 최종전` : `${h.season} 시즌 ${race.round}라운드`;
  const start = win.grid === 1 ? '폴 포지션에서' : win.grid ? `${win.grid}번 그리드에서` : '피트 레인에서';
  let out =
    `${where} ${josa(esc(race.name_ko), '은', '는')} ${start} 출발한 ` +
    `${b(esc(win.name))}${aside(esc(win.constructor))}의 우승으로 끝났다.`;
  const [q1, q2] = h.quali.filter((q) => q.v != null);
  if (q1 && q2 && h.quali_meta) {
    const same = q1.constructor_id === win.constructor_id;
    out +=
      ` 예선${same ? '에서도' : '에서는'} ${esc(q1.constructor)} 팀의 랩(${b(esc(h.quali_meta.session_best))})이 가장 빨랐고, ` +
      `두 번째로 빠른 ${esc(q2.constructor)} 팀과의 차이는 ${b(`${num(q2.gap_s, 3)}초`)}${aside(pct(q2.v))}다.`;
  }
  return out;
}

/** 출발 순위보다 가장 많이 오른 차(피트 레인 출발 제외). 같은 폭이면 앞 순위 */
export function biggestGain(h: Home): ClassificationRow | null {
  let best: ClassificationRow | null = null;
  for (const c of ranked(h)) {
    if (!c.grid || c.position == null) continue;
    const g = c.grid - c.position;
    if (g > 0 && (!best || g > (best.grid ?? 0) - (best.position ?? 0))) best = c;
  }
  return best;
}

/** 결승 결과 절 문장: 1, 2위 차이와 가장 많이 오른 차 */
export function resultsRead(h: Home): string {
  const cl = ranked(h);
  const second = cl[1];
  const parts: string[] = [];
  if (second?.time) {
    const gap = second.time.replace(/^\+/, '');
    parts.push(`우승자와 2위의 차이는 ${b(gap.includes('랩') ? gap : `${gap}초`)}다.`);
  }
  const gain = biggestGain(h);
  if (gain) {
    parts.push(
      `출발 순위보다 가장 많이 오른 차는 ${gain.grid}번 그리드에서 출발해 ${gain.position}위로 들어온 ` +
        `${b(esc(gain.name))}${aside(esc(gain.constructor))}다.`,
    );
  }
  return parts.join(' ');
}

/** 팀 이름 순(화면의 팀 상태 격자) */
export function teamsByName(w: UpgradeWeekend) {
  return [...w.teams].sort((a, z) => a.team.localeCompare(z.team, 'en'));
}

function filedTeams(w: UpgradeWeekend) {
  return w.teams.filter((t) => t.items > 0);
}

/** 제출된 업그레이드 절 문장 */
export function upgradesRead(h: Home): string {
  const now = h.upgrades_this_weekend;
  const last = h.upgrades_latest;
  const parts: string[] = [];
  if (now) {
    const filed = filedTeams(now);
    const where = `${now.round}라운드 ${esc(now.event_short_ko)} 문서에는`;
    parts.push(
      filed.length === 0
        ? `${where} ${now.teams.length}개 팀 모두 ${EN_NO_UPDATES}로 적혀 있다.`
        : `${where} ${filed.length}개 팀이 항목 ${n0(now.items)}건을 신고했다.`,
    );
  }
  if (last && (!now || last.round !== now.round || last.season !== now.season)) {
    const filed = filedTeams(last);
    const who = filed.length === 1 ? `${esc(filed[0].team)} 팀이` : `${filed.length}개 팀이`;
    parts.push(
      `가장 최근에 항목이 신고된 대회는 ${last.round}라운드 ${esc(last.event_short_ko)}이고, ${who} ${n0(last.items)}건을 냈다.`,
    );
  }
  return parts.join(' ');
}

/** 이번 대회 블록의 한 줄 */
export function thisWeekendLine(h: Home): string {
  const now = h.upgrades_this_weekend;
  if (!now) return '';
  const filed = filedTeams(now);
  if (filed.length === 0) {
    const tail = isFinal(h) && now.round === h.race.round ? ' 시즌 마지막 대회라 신고된 항목이 0건이다.' : ' 신고된 항목이 0건이다.';
    return `${now.teams.length}개 팀 모두 <span lang="en">"No updates submitted"</span>로 제출했다.${tail}`;
  }
  return `${filed.length}개 팀이 항목 ${n0(now.items)}건을 신고했다. 나머지 ${now.teams.length - filed.length}개 팀은 ${EN_NO_UPDATES}로 제출했다.`;
}

/** 최근 신고 블록 아래 한 줄 */
export function latestLine(w: UpgradeWeekend): string {
  const filed = filedTeams(w);
  const who = filed.map((t) => `${esc(t.team)} 팀 ${n0(t.items)}건`).join(', ');
  const rest = w.teams.length - filed.length;
  const restTxt = rest > 0 ? ` 나머지 ${rest}개 팀은 ${EN_NO_UPDATES}로 제출했다.` : '';
  return `${who}.${restTxt} 영문은 FIA 문서에 적힌 그대로다.`;
}

/** 라운드별 항목 수 주석: 가장 많은 대회, 전반과 후반의 합, 마지막 네 라운드의 신고 */
export function roundNote(h: Home): string {
  const counts = h.round_counts;
  if (counts.length === 0) return '';
  const n = h.rounds_in_season;
  const half = Math.ceil(n / 2);
  const sum = (f: (r: number) => boolean) => counts.filter((c) => f(c.round)).reduce((s, c) => s + c.n, 0);
  const first = sum((r) => r <= half);
  const second = sum((r) => r > half);
  const top = counts.reduce((a, c) => (c.n > a.n ? c : a));
  const from = Math.max(1, n - 3);
  const filed = counts.filter((c) => c.round >= from && c.n > 0);
  let tail: string;
  if (filed.length) {
    const parts = filed.map((c) => `${c.round}라운드 ${n0(c.n)}건`);
    const lastPart = parts[parts.length - 1];
    const joined =
      parts.length > 1 ? `${parts.slice(0, -2).map((p) => `${p}, `).join('')}${josa(parts[parts.length - 2], '과', '와')} ${lastPart}` : lastPart;
    tail = `${from}라운드부터 ${n}라운드까지 신고는 ${josa(joined, '이다', '다')}.`;
  } else {
    tail = `${from}라운드부터 ${n}라운드까지 신고는 0건이다.`;
  }
  return (
    `가장 많은 대회는 ${top.round}라운드 ${esc(top.short_ko)}의 ${n0(top.n)}건이다. ` +
    `1~${half}라운드에 ${n0(first)}건, ${half + 1}~${n}라운드에 ${n0(second)}건이 신고됐다. ${tail}`
  );
}

/** 값이 있는 레이스 지수 행 */
export function raceRows(h: Home): HomeRace[] {
  return h.race_index.filter((r) => r.v != null);
}

function crossesZero(r: HomeRace): boolean {
  return r.lo != null && r.hi != null && r.lo <= 0 && r.hi >= 0;
}

/** 페이스 절 문장: 두 지수의 1위, 구간이 0에 걸친 팀 수 */
export function paceRead(h: Home): string {
  const q = h.quali.find((x) => x.v != null);
  const rr = raceRows(h);
  const parts: string[] = [];
  if (q && rr[0]) {
    parts.push(
      `예선 한 랩 기준으로는 ${esc(q.constructor)} 팀이, 결승 클린 랩 중앙값 기준으로는 ${esc(rr[0].constructor)} 팀이 가장 빨랐다.`,
    );
  } else if (q) {
    parts.push(`예선 한 랩 기준으로는 ${esc(q.constructor)} 팀이 가장 빨랐다.`);
  }
  if (rr.length) {
    const cross = rr.filter(crossesZero).length;
    parts.push(
      cross > 0
        ? `레이스 지수는 ${rr.length}개 팀 가운데 ${cross}개 팀의 95% 구간이 0에 걸쳐 필드 중앙값과 구별되지 않는다.`
        : `레이스 지수는 ${rr.length}개 팀 모두 95% 구간이 0의 한쪽에 있다.`,
    );
  }
  parts.push('두 지수는 기준점이 달라 값을 서로 견주지 않는다.');
  return parts.join(' ');
}

/** 레이스 지수 주의: 구간이 0에 걸친 팀 가운데 결승 순위가 가장 낮은 팀을 예로 든다 */
export function cautionExample(h: Home): string {
  const base = '레이스 지수는 타이어 전략, 트래픽, 페이스 관리를 보정하지 않는다.';
  const cl = ranked(h);
  const cross = raceRows(h).filter(crossesZero);
  const bestPos = (cid: string) => Math.min(...cl.filter((c) => c.constructor_id === cid).map((c) => c.position ?? 99));
  const worst = cross.reduce<HomeRace | null>((a, r) => (!a || bestPos(r.constructor_id) > bestPos(a.constructor_id) ? r : a), null);
  if (!worst) return base;
  const cars = cl.filter((c) => c.constructor_id === worst.constructor_id);
  const leaderLaps = cl[0]?.laps ?? 0;
  const downs = new Set(cars.map((c) => leaderLaps - (c.laps ?? leaderLaps)));
  const one = [...downs][0];
  const lapTxt = cars.length === 2 && downs.size === 1 && one > 0 ? `두 대 모두 ${one}랩 뒤진 ` : '';
  const pos = cars.map((c) => c.position).join(', ');
  return (
    `${base} 예를 들어 ${esc(worst.constructor)} 팀은 ${lapTxt}${pos}위였지만 ` +
    `레이스 지수는 ${nw(ivl(worst.v, worst.lo, worst.hi))}로 필드 중앙값과 구별되지 않는다.`
  );
}

/** 최종 순위 절 문장 */
export function standingsRead(h: Home): string {
  const [d1, d2] = h.drivers;
  const c1 = h.constructors[0];
  const parts: string[] = [];
  if (d1) {
    let s = `드라이버 순위 1위 ${b(esc(d1.name))}${d1.team ? aside(esc(d1.team)) : ''}의 점수는 ${b(`${n0(d1.points)}점`)}`;
    if (d2) s += `으로, 2위 ${esc(d2.name)}보다 ${n0(d1.points - d2.points)}점 많다.`;
    else s += '이다.';
    parts.push(s);
  }
  if (c1) parts.push(`컨스트럭터 순위는 ${esc(c1.name)} 팀이 ${n0(c1.points)}점으로 1위다.`);
  return parts.join(' ');
}

/** 예선 노면 사실 줄 값 */
export function qualiSurface(h: Home): string {
  const w = h.quali_meta?.wet ?? h.race.quali?.wet;
  if (w === 'wet') return '우천 (OpenF1 판정)';
  if (w === 'dry') return '마른 노면 (OpenF1 판정)';
  return '우천 여부 미분류';
}

/** 차트 범위 줄의 노면 표기 */
export function qualiSurfaceShort(h: Home): string {
  const w = h.quali_meta?.wet ?? h.race.quali?.wet;
  return w === 'wet' ? '우천' : w === 'dry' ? '마른 노면' : '우천 미분류';
}
