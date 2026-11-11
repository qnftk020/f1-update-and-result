// 드라이버 이름을 좁은 칸에 맞게 줄이는 도우미. 시즌 쪽, 챔피언십 분석, 드라이버 차트가 함께 쓴다.
// 툴팁과 표에는 전체 이름을 쓴다.

/** 이름의 마지막 낱말: "Michael Schumacher" -> "Schumacher" */
export function surname(name: string): string {
  const parts = String(name).trim().split(/\s+/);
  return parts[parts.length - 1] ?? name;
}

/** 이름 첫 글자와 나머지: "Michael Schumacher" -> "M. Schumacher", "Juan Manuel Fangio" -> "J. Manuel Fangio" */
export function initialSurname(name: string): string {
  const parts = String(name).trim().split(/\s+/);
  if (parts.length < 2) return name;
  return `${parts[0][0]}. ${parts.slice(1).join(' ')}`;
}
