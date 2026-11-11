// 시즌 쪽(/seasons/, /seasons/<year>/)의 문장, 사실 줄, 배지, 출처 줄을 시즌 JSON에서 만든다.
// DESIGN.md "시즌" 와이어프레임의 연도별 규칙 표와 design/final/src/build.py의 build_season()을 옮겼다.
// 모든 수치는 시즌 JSON에서 센다. 반환값은 HTML 문자열이고, 데이터에서 온 글자는 esc()를 거친다.
import type { BadgeKind } from '../../lib/markup.ts';
import { badgeHtml } from '../../lib/markup.ts';
import { meta } from '../../lib/data.ts';
import { formatPoints, n0, num, pct, roundsText } from '../../lib/format.ts';
import { F1DB, JOLPICA, OPENF1, OPENF1_LICENSE, asofJolpica, asofQualiIndex, asofRaceIndex } from '../../lib/sources.ts';
import type { DriverSeason, Round, Season } from '../../lib/types.ts';
import { aside, b, esc, nw } from '../../lib/typeset.ts';

/** 우천 판정(OpenF1)이 있는 첫 시즌. 그 전 예선은 우천 여부 미분류다. */
export const WET_FROM = 2023;
export const QUALI_FROM = 1996;
export const RACE_FROM = 2023;
export const CONSTRUCTORS_FROM = 1958;

export const EMPTY = {
  constructors: '컨스트럭터 순위는 1958년부터 있다.',
  quali: '퀄리파잉 지수는 1996년부터 계산한다.',
  race: '레이스 지수는 2023년부터 계산한다.',
};

/** 이름의 마지막 낱말(약어가 없는 옛 드라이버의 짧은 이름). 'Juan Fangio' -> 'Fangio' */
export function surname(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts[parts.length - 1] ?? name;
}

/** 드라이버 짧은 이름: 세 글자 약어가 있으면 약어, 없으면 성 */
export function shortName(d: { code: string | null; name: string }): string {
  return d.code ?? surname(d.name);
}

/** 점수 차이 등 소수가 생길 수 있는 점수 표기(1950년대 공유 점수). 소수 둘째 자리까지 */
export function pts(x: number | null | undefined): string {
  return x == null ? '결측' : formatPoints(Math.round(x * 100) / 100);
}

/** 시즌 자료에서 고른 연도별 규칙 */
export function seasonFlags(s: Season) {
  const f = s.facts;
  const year = s.season;
  return {
    year,
    hasQ: s.has_quali_index,
    hasR: s.has_race_index,
    hasC: s.has_constructor_standings,
    wetJudged: year >= WET_FROM,
    refs: f.quali_reference,
    refFormats: f.quali_reference_formats,
    unc: f.quali_unclassified,
  };
}

/** 리드: 대회 수, 우승자 수, 두 순위 1위 */
export function leadHtml(s: Season): string {
  const [d1, d2] = s.drivers;
  const f = s.facts;
  let out = `${s.season} 시즌은 ${f.races}개 대회로 치러졌고, 우승한 드라이버는 ${b(`${f.winners}명`)}이다.`;
  if (d1 && d1.final_points != null) {
    const diff = d2?.final_points != null ? d1.final_points - d2.final_points : null;
    const cmp =
      diff == null ? '' : diff === 0 ? '으로 2위와 같' : `으로 2위보다 ${pts(diff)}점 많`;
    const c1 = s.has_constructor_standings ? s.constructors.find((c) => c.position === 1) : undefined;
    const tail = c1
      ? `고, 컨스트럭터 순위는 ${esc(c1.name)} 팀이 ${pts(c1.final_points)}점으로 1위다.`
      : '다.';
    out +=
      ` 드라이버 순위 1위 ${b(esc(d1.name))}${d1.team ? aside(esc(d1.team)) : ''}의 점수는 ${pts(d1.final_points)}점` +
      (cmp ? `${cmp}${tail}` : `이다.${c1 ? ` 컨스트럭터 순위는 ${esc(c1.name)} 팀이 ${pts(c1.final_points)}점으로 1위다.` : ''}`);
  }
  return out;
}

/** 사실 줄: 연도별 규칙 표의 "사실 줄" 행 */
export function factsList(s: Season): [string, string][] {
  const f = s.facts;
  const x = seasonFlags(s);
  const out: [string, string][] = [
    ['대회', `${f.races}개`],
    ['스프린트 주말', `${f.sprints.length}개`],
    ['우승한 드라이버', `${f.winners}명`],
  ];
  if (x.wetJudged && x.hasQ) {
    out.push(['우천 예선', roundsText(f.quali_wet)]);
    if (x.hasR) out.push(['우천 결승', roundsText(f.race_wet)]);
  } else if (x.hasQ) {
    out.push(['우천 여부', `미분류 (판정 자료는 ${WET_FROM}년부터)`]);
  }
  if (x.refs.length) out.push(['예선 형식', `${esc(x.refFormats.join(', '))}, 참고용 (${x.refs.length}개 대회)`]);
  if (!x.hasR) out.push(['레이스 지수', `${RACE_FROM}년부터`]);
  return out;
}

/** 캘린더 문장 */
export function calendarRead(s: Season): string {
  const f = s.facts;
  const x = seasonFlags(s);
  const parts = [`스프린트가 열린 주말은 ${f.sprints.length}개다.`];
  if (x.wetJudged && x.hasQ) {
    parts.push(
      `우천으로 판정된 예선은 ${roundsText(f.quali_wet)}` +
        (x.hasR ? `, 결승은 ${roundsText(f.race_wet)}` : '') +
        '이며 기본 페이스 분석에서 뺀다.',
    );
  } else if (x.hasQ && x.unc.length) {
    parts.push(
      x.unc.length === f.quali_rounds
        ? `${s.season}년은 우천 판정 자료가 없어 ${x.unc.length}개 대회의 예선 모두 우천 여부가 미분류다.`
        : `${s.season}년은 우천 판정 자료가 없어 예선 ${x.unc.length}개 대회의 우천 여부가 미분류다.`,
    );
  }
  if (x.refs.length) {
    parts.push(`예선 ${x.refs.length}개 대회는 ${esc(x.refFormats.join(', '))} 형식이라 지수를 참고용으로만 싣는다.`);
  }
  if (!x.hasR) parts.push(EMPTY.race);
  return parts.join(' ');
}

/** 캘린더 표시 칸 배지 목록: 스프린트, 참고용, 우천 예선 또는 미분류, 우천 결승 */
export function roundBadges(r: Round): [BadgeKind, string][] {
  const out: [BadgeKind, string][] = [];
  if (r.has_sprint) out.push(['sprint', '스프린트']);
  if (r.quali?.reference) out.push(['ref', '참고용']);
  if (r.quali?.wet === 'wet') out.push(['wet', '우천 예선']);
  else if (r.quali?.wet === 'unclassified') out.push(['unclassified', '미분류']);
  if (r.race?.wet) out.push(['wet', '우천 결승']);
  return out;
}

export function badgeList(list: [BadgeKind, string][]): string {
  return list.map(([k, t]) => badgeHtml(k, t)).join('');
}

/** 대회 이름: "그랑프리" 접미어는 좁은 화면에서 숨긴다(영문 줄에 Grand Prix가 있다) */
export function gpNameHtml(ko: string): string {
  const suffix = ' 그랑프리';
  return ko.endsWith(suffix) ? `${esc(ko.slice(0, -suffix.length))}<span class="gp">${suffix}</span>` : esc(ko);
}

/** 캘린더 출처와 기준일 */
export function calendarSource(s: Season): { source: string; asof: string } {
  const x = seasonFlags(s);
  let source = `${JOLPICA} 대회와 결과`;
  if (x.wetJudged && x.hasQ) source += `, 우천 판정은 ${OPENF1} (이 사이트 판정)`;
  else if (x.refs.length) source += `, 예선 형식은 ${F1DB}`;
  const asof = asofJolpica() + (x.wetJudged && x.hasQ ? `, 판정 ${nw(meta.sources.openf1.as_of)}` : '');
  return { source, asof };
}

/** 순위 추이 문장: 1위가 마지막으로 바뀐 라운드 */
export function driverLeadRead(s: Season): string {
  const lead = s.facts.driver_lead;
  if (!lead) return '';
  const who = s.drivers.find((d) => d.id === lead.leader_id);
  const name = who ? esc(who.name) : esc(lead.leader_id);
  const n = s.rounds.length;
  let first: string;
  if (lead.round === lead.first_round) {
    first = `드라이버 순위 1위는 ${lead.first_round}라운드부터 마지막 라운드까지 ${b(name)}의 자리였다.`;
  } else if (lead.round === n) {
    first = `순위표 1위는 마지막 ${b(`${n}라운드`)}에서 바뀌어 ${name}의 1위로 끝났다.`;
  } else {
    first = `순위표 1위가 마지막으로 바뀐 것은 ${b(`${lead.round}라운드`)}이고, 그 뒤로는 ${name}의 1위가 이어졌다.`;
  }
  const hl = Math.min(3, s.drivers.length);
  return `${first} 강조한 ${hl === 3 ? '세 명은 최종 순위 상위 3명' : `${hl}명은 최종 순위 상위 ${hl}명`}이며, 칩으로 바꿀 수 있다.`;
}

export function constructorLeadRead(s: Season): string {
  const lead = s.facts.constructor_lead;
  if (!lead) return '';
  const who = s.constructors.find((c) => c.id === lead.leader_id);
  const name = who ? esc(who.name) : esc(lead.leader_id);
  if (lead.round === lead.first_round) {
    return `컨스트럭터 순위는 ${lead.first_round}라운드부터 ${name} 팀이 1위였고 끝까지 바뀌지 않았다.`;
  }
  if (lead.round === s.rounds.length) {
    return `컨스트럭터 순위 1위는 마지막 ${lead.round}라운드에서 바뀌어 ${name} 팀의 1위로 끝났다.`;
  }
  return `컨스트럭터 순위 1위가 마지막으로 바뀐 것은 ${lead.round}라운드이고, 그 뒤로는 ${name} 팀의 1위가 이어졌다.`;
}

/** 누적 점수 칸: 아직 순위표에 오르지 않은 라운드는 빈 칸 */
export function pointsCell(p: number | null | undefined): string {
  return p == null ? '' : formatPoints(p);
}

/** 드라이버 순위 칸 */
export function posCell(d: DriverSeason | { position: number | null }): string {
  return d.position == null ? '<span class="nw">순위 미부여</span>' : String(d.position);
}

/** 퀄리파잉 작은 다중 문장: 평균이 가장 작은 팀과 큰 팀 */
export function qualiRead(s: Season): string {
  const teams = s.constructors.filter((c) => c.quali_index && c.quali_mean != null);
  if (!teams.length) return '';
  const sorted = [...teams].sort((a, z) => (a.quali_mean as number) - (z.quali_mean as number));
  const lo = sorted[0];
  const hi = sorted[sorted.length - 1];
  const f = s.facts;
  const wetJudged = s.season >= WET_FROM;
  const n = f.quali_rounds - (wetJudged ? f.quali_wet.length : 0);
  const kind = wetJudged ? '마른 예선' : '예선';
  return (
    `${kind} ${n}개 대회에서 평균 지수가 가장 작은 팀은 ${b(esc(lo.name))} 팀${aside(`평균 ${pct(lo.quali_mean)}`)}이고, ` +
    `가장 큰 팀은 ${esc(hi.name)} 팀${aside(`평균 ${pct(hi.quali_mean)}`)}이다. ` +
    '칸마다 같은 세로축을 쓰고, 칸 순서는 컨스트럭터 최종 순위다.'
  );
}

/** 레이스 작은 다중 문장 */
export function raceRead(s: Season): string {
  const teams = s.constructors.filter((c) => c.race_index && c.race_mean != null);
  if (!teams.length) return '';
  const lo = [...teams].sort((a, z) => (a.race_mean as number) - (z.race_mean as number))[0];
  const n = s.facts.race_index_rounds - s.facts.race_wet.length;
  return `마른 결승 ${n}개 대회에서 레이스 지수 평균이 가장 낮은(빠른) 팀은 ${esc(lo.name)} 팀${aside(`평균 ${pct(lo.race_mean, 2, { sign: true })}`)}이다.`;
}

/** 퀄리파잉 지수 출처: 라운드마다 원자료(Jolpica 또는 F1DB)를 센다 */
export function qualiSource(s: Season): { source: string; asof: string } {
  const qs = s.rounds.filter((r) => r.quali);
  const f1db = qs.filter((r) => r.quali?.source === 'f1db').map((r) => r.round);
  const jol = qs.length - f1db.length;
  const wet = s.season >= WET_FROM ? `. 우천 판정 ${OPENF1}` : '';
  const f1dbAsof = `${meta.sources.f1db.name} ${nw(meta.sources.f1db.as_of)} 확인`;
  if (jol === 0) {
    return {
      source: `${F1DB} 예선 기록, 지수는 이 사이트 계산`,
      asof: `${f1dbAsof}, 지수 ${nw(meta.sources.pace.as_of)} 계산`,
    };
  }
  const extra = f1db.length ? `, ${f1db.map((r) => `R${r}`).join(', ')}는 ${F1DB}` : '';
  return {
    source: `${JOLPICA} 예선 기록${extra}${wet}. 지수는 이 사이트 계산`,
    asof: f1db.length
      ? `${asofJolpica()}, ${f1dbAsof}, 지수 ${nw(meta.sources.pace.as_of)} 계산`
      : asofQualiIndex(),
  };
}

export function raceSource(): { source: string; asof: string } {
  return { source: `${OPENF1} 랩, 스틴트, 날씨, 레이스 컨트롤 (${OPENF1_LICENSE}), 이 사이트 계산`, asof: asofRaceIndex() };
}

/** 퀄리파잉 표 보기의 표시 칸 */
export function qualiFlagCell(r: { ref?: boolean; wet: string }): string {
  const list: [BadgeKind, string][] = [];
  if (r.ref) list.push(['ref', '참고용']);
  if (r.wet === 'wet') list.push(['wet', '우천']);
  else if (r.wet === 'unclassified') list.push(['unclassified', '미분류']);
  return list.length ? `<span class="badges">${badgeList(list)}</span>` : '';
}

/** 작은 다중 부제 */
export function qualiSub(s: Season): string {
  const x = seasonFlags(s);
  const bits = ['칸마다 그 팀의 지수(파란 선)와 그 대회 필드 중앙값(회색 선)이다.'];
  if (x.wetJudged) bits.push('우천 예선은 회색 띠와 빈 고리로 남기고 선을 끊는다.');
  if (x.refs.length) bits.push('참고용 형식 예선은 선으로 잇지 않고 빈 고리로만 찍는다.');
  if (!x.refs.length && x.wetJudged) bits.push(`${x.year} 시즌에는 참고용 형식과 미분류 대회가 0개다.`);
  return bits.join(' ');
}

/** 작은 다중 위 안내 상자 문장(참고용, 미분류). 해당이 없으면 null */
export function qualiNotice(s: Season): { badges: [BadgeKind, string][]; text: string } | null {
  const x = seasonFlags(s);
  if (!x.refs.length && !x.unc.length) return null;
  const badges: [BadgeKind, string][] = [];
  const txt: string[] = [];
  if (x.refs.length) {
    badges.push(['ref', '참고용']);
    txt.push(
      x.refs.length === s.facts.quali_rounds
        ? `${x.year} 시즌 예선은 ${x.refs.length}개 대회 모두 ${esc(x.refFormats.join(', '))} 형식이라 참고용이다.`
        : `예선 ${x.refs.length}개 대회가 참고용 형식이다.`,
    );
  }
  if (x.unc.length) {
    badges.push(['unclassified', '미분류']);
    txt.push(
      x.refs.length
        ? `${WET_FROM - 1}년 이전이라 우천 여부도 미분류이고, 우천 예선이 평균에 섞여 있을 수 있다.`
        : `${WET_FROM - 1}년 이전이라 우천 여부가 미분류이고, 우천 예선이 평균에 섞여 있을 수 있다.`,
    );
  }
  return { badges, text: txt.join(' ') };
}

export { n0, num, pct };
