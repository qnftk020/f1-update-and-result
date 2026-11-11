// 순위 표의 등수. 같은 값은 같은 등수를 받고 다음 등수는 그만큼 건너뛴다(1, 1, 3). 드라이버, 시즌, 홈의 순위 표가 함께 쓴다.

/** 값이 큰 순서로 이미 정렬된 행의 경쟁 순위. 반환 배열의 i번째가 rows[i]의 등수다 */
export function competitionRanks<T>(rows: readonly T[], value: (r: T) => number): number[] {
  const out: number[] = [];
  rows.forEach((r, i) => out.push(i > 0 && value(r) === value(rows[i - 1]) ? out[i - 1] : i + 1));
  return out;
}
