// 숫자, 날짜, 지수의 화면 표기. 서버(빌드)와 브라우저에서 같은 결과가 나오도록 로캘을 고정한다.

const integer = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 });
const points = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });

/** 1,234 */
export function formatInteger(value: number | null | undefined): string {
  return value == null ? '' : integer.format(value);
}

/**
 * 점수: 정수면 그대로, 소수가 있으면 소수 둘째 자리까지 보이고 끝의 0은 뺀다.
 * 반점(3.5)뿐 아니라 1950년대 공유 점수(1/7, 1/3에서 나온 0.14, 24.64, 1.33 등)도 원자료와 같게 보인다.
 */
export function formatPoints(value: number | null | undefined): string {
  if (value == null) return '';
  return points.format(value);
}

/**
 * 퀄리파잉 지수: 0 이상인 값. '+0.245%'.
 * 표시 자릿수로 반올림해서 0이 되는 값은 부호 없이 '0.000%'로 보인다.
 */
export function formatQualiIndex(value: number | null | undefined, digits = 3): string {
  if (value == null) return '';
  const fixed = value.toFixed(digits);
  return Number(fixed) === 0 ? `${(0).toFixed(digits)}%` : `+${fixed}%`;
}

/** 레이스 지수: 부호가 있는 값. 음수 부호는 유니코드 빼기 기호를 쓴다. */
export function formatSignedPercent(value: number | null | undefined, digits = 3): string {
  if (value == null) return '';
  const abs = Math.abs(value).toFixed(digits);
  if (Number(abs) === 0) return `${abs}%`;
  return `${value < 0 ? '−' : '+'}${abs}%`;
}

/** 밀리초를 '1:22.207' 로. */
export function formatLapTime(ms: number | null | undefined): string {
  if (ms == null) return '';
  const minutes = Math.floor(ms / 60000);
  const seconds = (ms - minutes * 60000) / 1000;
  return `${minutes}:${seconds.toFixed(3).padStart(6, '0')}`;
}

/** '2025-12-07' 을 '2025년 12월 7일' 로. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${y}년 ${m}월 ${d}일`;
}

/** '2025-12-07' 을 '12월 7일' 로. */
export function formatMonthDay(iso: string | null | undefined): string {
  if (!iso) return '';
  const [, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${m}월 ${d}일`;
}

// ---------------------------------------------------------------- 디자인 명세(DESIGN.md)의 수치 표기
// 서버(.astro)와 브라우저(차트 모듈)가 같은 함수를 쓴다. 차트 모듈의 num()도 이 함수다.

/** 빼기 기호 U+2212. 화면의 음수는 언제나 이 기호를 쓴다. */
export const MINUS = '−';

/**
 * 소수 d자리로 반올림한 문자열. 반올림은 지수 표기 문자열로 해서 이진 부동소수 오차를 피한다
 * (0.2445 -> '0.245'). 음수는 U+2212, sign이면 0보다 큰 값에 '+'를 붙인다. 값이 없으면 '결측'.
 * 퀄리파잉 지수는 num(v, 3), 레이스 지수와 구간은 num(v, 2, { sign: true }), 초 차이는 num(s, 3).
 */
export function num(x: number | null | undefined, d = 3, { sign = false }: { sign?: boolean } = {}): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '결측';
  const a = Math.abs(x);
  // 1e-6보다 작은 값은 문자열이 이미 지수 표기("1e-7")라 0으로 둔다.
  const r = a < 1e-6 ? 0 : Number(`${Math.round(Number(`${a}e${d}`))}e-${d}`);
  const s = r.toFixed(d);
  if (x < 0 && r !== 0) return MINUS + s;
  return (sign && r > 0 ? '+' : '') + s;
}

/** num() 뒤에 '%'. 퀄리파잉 지수는 부호 없이 pct(v), 레이스 지수는 pct(v, 2, { sign: true }). */
export function pct(x: number | null | undefined, d = 3, o?: { sign?: boolean }): string {
  return x === null || x === undefined ? '결측' : `${num(x, d, o)}%`;
}

/** 정수와 천 단위 쉼표: 1,149. 값이 없으면 '결측'. */
export function n0(x: number | null | undefined): string {
  return x === null || x === undefined ? '결측' : Math.round(x).toLocaleString('ko-KR');
}

/** 레이스 지수와 95% 구간: '−1.46 (−1.57 ~ −1.22)' */
export function ivl(v: number | null | undefined, lo: number | null | undefined, hi: number | null | undefined): string {
  return `${num(v, 2, { sign: true })} (${num(lo, 2, { sign: true })} ~ ${num(hi, 2, { sign: true })})`;
}

/** 구간만: '−1.57 ~ −1.22' */
export function range2(lo: number | null | undefined, hi: number | null | undefined): string {
  return `${num(lo, 2, { sign: true })} ~ ${num(hi, 2, { sign: true })}`;
}

/** 순위 변화: 출발보다 앞서면 '+9', 뒤지면 '−8', 같으면 '0' */
export function posChange(grid: number, pos: number): string {
  if (grid === pos) return '0';
  return grid > pos ? `+${grid - pos}` : `${MINUS}${pos - grid}`;
}

/** 라운드 번호 목록: '2개 (17, 22라운드)', 비면 '0개' */
export function roundsText(rounds: number[]): string {
  return `${rounds.length}개${rounds.length ? ` (${rounds.join(', ')}라운드)` : ''}`;
}

/** 받침이 있는지. 한글과 숫자로 끝나는 말만 판단하고, 그 밖(라틴 이름)은 false다. */
export function hasBatchim(word: string): boolean {
  const ch = word.trim().slice(-1);
  if (ch >= '가' && ch <= '힣') return (ch.charCodeAt(0) - 0xac00) % 28 !== 0;
  if (/\d/.test(ch)) return '013678'.includes(ch);
  return false;
}

/**
 * 말 뒤에 받침에 맞는 조사를 붙인다. josa('플로어', '이', '가') -> '플로어가', josa('70건', '이', '가').
 * a는 받침이 있을 때(이, 은, 을, 과, 으로), b는 없을 때(가, 는, 를, 와, 로).
 * 한글이나 숫자로 끝나는 말에만 쓴다. 라틴 이름 뒤에는 "의", "보다", 괄호, "팀" 같은 말을 둔다.
 */
export function josa(word: string, a: string, b: string): string {
  return word + (hasBatchim(word) ? a : b);
}

/**
 * 받침 유무에 맞는 조사를 고른다. particle('엔스톤', '은', '는') -> '은'
 * 한글로 끝나는 말에만 쓴다. 로마자 이름(드라이버, 팀)은 받침을 알 수 없으므로 조사를 붙이지 말고
 * "팀: McLaren"처럼 이름표 꼴로 적는다. 한글이 아닌 말이 들어오면 오류를 낸다.
 */
export function particle(word: string, withFinal: string, withoutFinal: string): string {
  const code = word.trim().slice(-1).charCodeAt(0);
  if (!(code >= 0xac00 && code <= 0xd7a3)) {
    throw new Error(`한글로 끝나지 않는 말에는 조사를 고를 수 없다: ${word}`);
  }
  return (code - 0xac00) % 28 === 0 ? withoutFinal : withFinal;
}
