// 드라이버·컨스트럭터 목록의 비교 절 계산. 빌드(자료 파일 만들기)와 브라우저(맞대결, 목록 검색, 누적 우승)가 함께 쓴다.
// DOM을 쓰지 않는 순수 함수만 둔다. 회귀 테스트는 compare.test.mjs다.
// 결과를 가르는 규칙은 팀 동료 비교(docs/methodology.md "팀 동료 비교")와 같다: 완주로 분류된 쪽이
// 분류되지 않은 쪽보다 앞이고, 둘 다 분류되면 position이 작은 쪽이 앞이며, 같거나 둘 다 분류되지 않으면 세지 않는다.

export type Outcome = 'F' | 'D' | 'N' | 'R';
export type Kind = 'd' | 'c';

/** 대회 한 줄: [시즌, 라운드, 결과 분류, position]. 한 대회에 한 줄(가장 앞선 결과)만 둔다. */
export type RaceKey = [number, number, Outcome, number];

/** 비교에 고를 수 있는 최대 수. 계열 색(s1, s2, s3)과 표식(원, 네모, 세모)이 셋이다. */
export const MAX_PICK = 3;

/** 인디애나폴리스 500(1950-1960)의 짧은 대회 이름. 비교에서 뺀다. */
export const INDY_SHORT = '인디 500';

/** 비교 자료 파일 한 개. 드라이버(k: d)와 컨스트럭터(k: c)가 같은 틀이고 t와 s의 칸만 다르다. */
export interface CompareFile {
  k: Kind;
  id: string;
  name: string;
  nat: string | null;
  first: number;
  last: number;
  t: Record<string, number | null>;
  /** 시즌 줄: [시즌, 최종 순위(없으면 null), 우승, 포디움, 출발(드라이버) 또는 출전(컨스트럭터), 팀 또는 엔진, 챔피언 1/0, 실격·제외 1/0] */
  s: [number, number | null, number, number, number, string, number, number][];
  r: RaceKey[];
  /** 드라이버만: 팀 동료 [ID, 이름, 함께 나선 대회, 결승 비교, 결승 앞섬, 예선 비교, 예선 앞섬, 시즌 목록, 팀 이름] */
  m?: [string, string, number, number, number, number, number, number[], string][];
}

/** 두 결과 비교. a가 앞이면 1, b가 앞이면 -1, 세지 않으면 0. */
export function ahead(a: [Outcome, number], b: [Outcome, number]): 1 | -1 | 0 {
  const af = a[0] === 'F';
  const bf = b[0] === 'F';
  if (af && !bf) return 1;
  if (!af && bf) return -1;
  if (!af && !bf) return 0;
  if (a[1] < b[1]) return 1;
  if (a[1] > b[1]) return -1;
  return 0;
}

/**
 * 대회마다 가장 앞선 결과 한 줄만 남긴다(1950년대 차량 공유처럼 한 대회에 행이 여럿인 경우).
 * 인디애나폴리스 500은 뺀다. 순서는 시즌, 라운드 순이다.
 */
export function bestPerRace(rows: { s: number; r: number; n: string; o: Outcome; p: number }[]): RaceKey[] {
  const best = new Map<string, RaceKey>();
  for (const x of rows) {
    if (x.n === INDY_SHORT) continue;
    const key = `${x.s}-${x.r}`;
    const cur = best.get(key);
    const cand: RaceKey = [x.s, x.r, x.o, x.p];
    // 둘 다 분류되지 않은 행끼리는 앞뒤를 가리지 않으므로(맞대결에서 세지 않는다) 먼저 온 행을 둔다
    if (!cur || ahead([cand[2], cand[3]], [cur[2], cur[3]]) > 0) best.set(key, cand);
  }
  return [...best.values()].sort((x, y) => x[0] - y[0] || x[1] - y[1]);
}

export interface HeadToHead {
  /** 두 쪽 모두 결과 줄이 있는 대회 */
  both: number;
  /** 그 가운데 앞뒤를 가린 대회 */
  counted: number;
  a: number;
  b: number;
  first: number | null;
  last: number | null;
}

/** 같은 대회 결승 맞대결. a와 b는 bestPerRace의 결과다. */
export function headToHead(a: RaceKey[], b: RaceKey[]): HeadToHead {
  const bm = new Map(b.map((x) => [`${x[0]}-${x[1]}`, x]));
  const out: HeadToHead = { both: 0, counted: 0, a: 0, b: 0, first: null, last: null };
  for (const x of a) {
    const y = bm.get(`${x[0]}-${x[1]}`);
    if (!y) continue;
    out.both += 1;
    out.first ??= x[0];
    out.last = x[0];
    const v = ahead([x[2], x[3]], [y[2], y[3]]);
    if (v === 0) continue;
    out.counted += 1;
    if (v > 0) out.a += 1;
    else out.b += 1;
  }
  return out;
}

/** 검색용 글자 맞추기는 lib/search.ts에 있다(전역 검색과 같은 규칙). */
export { fold } from './search.ts';

/**
 * 주소의 고른 목록(?cmp=senna,prost)을 읽는다. 알 수 없는 ID와 중복은 버리고 MAX_PICK개까지만 둔다.
 * raw가 null이면(주소에 cmp가 없으면) null을 돌려 처음 비교를 쓰게 한다.
 */
export function parseIds(raw: string | null, known: Set<string>): string[] | null {
  if (raw == null) return null;
  return [...new Set(raw.split(',').map((x) => x.trim()).filter((x) => known.has(x)))].slice(0, MAX_PICK);
}

/** 시즌 줄에서 차트 점을 만든다. x는 연도 또는 데뷔 해를 1로 센 경력 햇수다. 누적 우승은 그 시즌까지의 합이다. */
export function seasonPoints(file: CompareFile, mode: 'year' | 'career') {
  let cum = 0;
  return file.s.map(([s, pos, wins, , , team, champ, ex]) => {
    cum += wins;
    return { s, x: mode === 'year' ? s : s - file.first + 1, pos, wins, cum, team, champ: champ === 1, ex: ex === 1 };
  });
}

/** 좁은 칸의 이름표: 드라이버는 성만, 같은 성이 겹치면 전체 이름. 컨스트럭터는 이름 그대로. */
export function shortNames(names: string[], kind: Kind): string[] {
  if (kind === 'c') return [...names];
  const sur = names.map((n) => n.trim().split(/\s+/).pop() ?? n);
  return names.map((n, i) => (sur.filter((x) => x === sur[i]).length > 1 ? n : sur[i]));
}
