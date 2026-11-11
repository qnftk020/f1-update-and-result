// 업그레이드 탐색기의 문장 틀. 서버(빌드 때 정적 리드)와 브라우저(조건이 바뀔 때 다시 쓴 리드)가 같은 함수를 쓴다.
// 자료 모듈(lib/data.ts)을 불러오지 않는다. 브라우저 번들에 생성 JSON이 들어가지 않게 하려는 것이다.
import { josa, n0 } from '../../lib/format.ts';

export const CAT_ORDER = ['performance', 'circuit_specific', 'reliability', 'other'] as const;
export type Cat = (typeof CAT_ORDER)[number];

/** 한 페이지에 처음 보이는 항목 수와 "더 보기" 한 번에 더 보이는 수 */
export const PAGE = 20;

export interface LeadInput {
  /** 전체 항목 수(855) */
  total: number;
  /** 조건에 맞는 항목 수 */
  n: number;
  /** 조건에 맞는 항목이 걸친 문서 수 */
  docs: number;
  /** 전체 문서 수(54) */
  allDocs: number;
  /** "2023-2025" */
  years: string;
  /** 가장 많은 부품 영역 [한국어 이름, 건수] */
  area: [string, number] | null;
  /** 가장 많은 변경 사유 범주 [한국어 이름, 건수] */
  cat: [string, number] | null;
  /** 조건이 하나라도 걸려 있는지 */
  filtered: boolean;
}

/**
 * 리드 문장 HTML(조판 전). 서버는 PageHead가 keepNames(), 레이아웃이 typeset()을 거치고,
 * 브라우저는 typeset(keepNames(leadHtml(...)))로 같은 마크업을 만든다. 데이터 글자는 들어가지 않는다
 * (부품 영역과 범주 이름은 labels.json의 고정 한국어 이름이다).
 */
export function leadHtml(s: LeadInput): string {
  if (!s.n || !s.area || !s.cat) return '고른 조건에 맞는 항목은 0건이다.';
  const first = s.filtered
    ? `고른 조건에 맞는 항목은 ${n0(s.total)}건 가운데 <b>${n0(s.n)}건</b>이고 문서 ${n0(s.docs)}건에 걸쳐 있다. `
    : `${s.years}년 FIA 문서 ${n0(s.allDocs)}건에서 읽은 업그레이드 항목은 <b>${n0(s.total)}건</b>이다. `;
  const [al, an] = s.area;
  const [cl, cn] = s.cat;
  const share = Math.round((cn / s.n) * 100);
  return (
    first +
    `부품 영역은 ${josa(al, '이', '가')} ${n0(an)}건으로 가장 많고, ` +
    `변경 사유는 ${cl} 범주가 ${n0(cn)}건<span class="aside">(${share}%)</span>으로 가장 많다.`
  );
}

/** 가장 많은 키와 건수. 같으면 먼저 나온 키(order 순서)를 쓴다. */
export function topOf(counts: Record<string, number>, order: string[]): [string, number] | null {
  let best: [string, number] | null = null;
  for (const k of order) {
    const v = counts[k] ?? 0;
    if (v > 0 && (!best || v > best[1])) best = [k, v];
  }
  return best;
}

/** 대회 이름: "2025 20라운드 멕시코시티" */
export function eventLabel(season: number | string, round: number | string, short: string): string {
  return `${season} ${round}라운드 ${short}`;
}

/** 시즌별 문서 범위 문장: "2023년 7개 대회(fia.com 공개분), 2024년 23개 대회(바레인 문서 부재), 2025년 24개 대회" */
export function docScope(bySeason: [number, number, string][]): string {
  return bySeason.map(([y, n, note]) => `${y}년 ${n}개 대회${note ? `(${note})` : ''}`).join(', ');
}
