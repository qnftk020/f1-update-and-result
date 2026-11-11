// 숫자, 날짜, 지수의 화면 표기. 서버(빌드)와 브라우저에서 같은 결과가 나오도록 로캘을 고정한다.

const integer = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 });

/** 1,234 */
export function formatInteger(value: number | null | undefined): string {
  return value == null ? '' : integer.format(value);
}

/** 점수: 정수면 그대로, 반점이 있으면 소수 첫째 자리까지. */
export function formatPoints(value: number | null | undefined): string {
  if (value == null) return '';
  return Number.isInteger(value) ? integer.format(value) : value.toFixed(1);
}

/** 퀄리파잉 지수: 0 이상인 값. '+0.245%' (0은 '0.000%'). */
export function formatQualiIndex(value: number | null | undefined, digits = 3): string {
  if (value == null) return '';
  return value === 0 ? `${(0).toFixed(digits)}%` : `+${value.toFixed(digits)}%`;
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
