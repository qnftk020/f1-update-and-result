// 홈 최신 대회 표의 도움 함수. 모든 수치는 home.json에서 센다. 서술 문장은 만들지 않는다(2026-11-26).
import type { ClassificationRow, Home } from '../../lib/types.ts';

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
  if (!c.time) return c.classified ? '미상' : '미완주';
  return c.time.startsWith('+') && !c.time.includes('랩') ? `${c.time}초` : c.time;
}

/** 머리 메타의 완주: '20대 (1랩 뒤진 차 4대)' */
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
