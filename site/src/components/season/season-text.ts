// 시즌 쪽(/seasons/, /seasons/<year>/)의 문장, 사실 줄, 배지, 출처 줄을 시즌 JSON에서 만든다.
// DESIGN.md "시즌" 와이어프레임의 연도별 규칙 표와 design/final/src/build.py의 build_season()을 옮겼다.
// 모든 수치는 시즌 JSON에서 집계한다. 반환값은 HTML 문자열이고, 데이터에서 온 글자는 esc()를 거친다.
import type { BadgeKind } from '../../lib/markup.ts';
import { badgeHtml } from '../../lib/markup.ts';
import { meta } from '../../lib/data.ts';
import { formatPoints, n0, num, pct, roundsText } from '../../lib/format.ts';
import { F1DB, JOLPICA, OPENF1, OPENF1_LICENSE, OPENMETEO, asofJolpica, asofQualiIndex, asofRaceIndex, asofRaceIndexJolpica } from '../../lib/sources.ts';
import type { DriverSeason, Round, Season } from '../../lib/types.ts';
import { surname } from '../../lib/names.ts';
import { aside, b, esc, nw } from '../../lib/typeset.ts';

/** 우천 판정(OpenF1)이 있는 첫 시즌. 그 전 예선은 우천 여부 미분류다. */
export const WET_FROM = 2023;
export const QUALI_FROM = 1950;
export const RACE_FROM = 2014;
/** 레이스 지수의 OpenF1 계열이 시작하는 해. 그 전(2014-2022)은 Jolpica 계열이다. */
export const RACE_OPENF1_FROM = 2023;

export const EMPTY = {
  constructors: '컨스트럭터 순위는 1958년부터 있다.',
  quali: `퀄리파잉 지수는 ${QUALI_FROM}년부터 계산한다.`,
  race: `레이스 지수는 ${RACE_FROM}년부터 계산한다.`,
};

/** 이름의 마지막 낱말(약어가 없는 옛 드라이버의 짧은 이름, lib/names.ts) */
export { surname };

/** 드라이버 짧은 이름: 세 글자 약어가 있으면 약어, 없으면 성 */
export function shortName(d: { code: string | null; name: string }): string {
  return d.code ?? surname(d.name);
}

/** 점수 차이 등 소수가 생길 수 있는 점수 표기(1950년대 공유 점수). 소수 둘째 자리까지 */
export function pts(x: number | null | undefined): string {
  return x == null ? '미상' : formatPoints(Math.round(x * 100) / 100);
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


/** 캘린더 표시 칸 배지 목록: 스프린트, 참고용, 우천 예선, 우천 결승 또는 결승 미분류.
 *  예선 미분류는 2023년 이전 모든 대회에 해당해 행마다 달지 않고 요약 줄 "우천 여부"로만 표기한다. */
export function roundBadges(r: Round): [BadgeKind, string][] {
  const out: [BadgeKind, string][] = [];
  if (r.has_sprint) out.push(['sprint', '스프린트']);
  if (r.quali?.reference) out.push(['ref', '참고용']);
  if (r.quali?.wet === 'wet') out.push(['wet', '우천 예선']);
  if (r.race?.wet) out.push(['wet', '우천 결승']);
  else if (r.race?.unclassified) out.push(['unclassified', '결승 미분류']);
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



/** 누적 점수 칸: 아직 순위표에 오르지 않은 라운드는 빈 칸 */
export function pointsCell(p: number | null | undefined): string {
  return p == null ? '' : formatPoints(p);
}

/** 드라이버 순위 칸 */
export function posCell(d: DriverSeason | { position: number | null }): string {
  return d.position == null ? '<span class="nw">순위 미부여</span>' : String(d.position);
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

export function raceSource(season: number): { source: string; asof: string } {
  if (season < RACE_OPENF1_FROM) {
    return { source: `${JOLPICA} 결승 랩과 피트스톱, ${OPENMETEO}, 이 사이트 계산`, asof: asofRaceIndexJolpica() };
  }
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

/** 팀별 퀄리파잉 지수 각주 문장(참고용, 미분류). 해당이 없으면 null. badges는 예전 안내 상자용으로 남겨 둔다 */
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
        : `예선 ${x.refs.length}개 대회는 ${esc(x.refFormats.join(', '))} 형식이라 참고용이다.`,
    );
  }
  if (x.unc.length) {
    badges.push(['unclassified', '미분류']);
    txt.push(`${WET_FROM}년 이전은 우천 여부가 미분류라 평균에 우천 예선이 포함되었을 수 있다.`);
  }
  return { badges, text: txt.join(' ') };
}

export { n0, num, pct };
