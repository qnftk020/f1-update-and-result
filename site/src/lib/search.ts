// 전역 검색(DESIGN.md "전역 검색"): 색인 항목의 모양, 글자 맞추기(fold), 점수와 묶기.
// 색인은 빌드 때 pages/data/search.json.ts가 만들고, 브라우저는 components/search/search-client.ts가 처음 초점 때 받는다.
// 새 의존성 없이 접두 일치 > 낱말 접두 > 포함 순으로 점수를 매긴다. 검색어의 낱말은 모두 맞아야 한다.

export type SearchKind = 'driver' | 'constructor' | 'team' | 'season' | 'race' | 'engine' | 'regulation';

/** 색인 항목. 키를 짧게 둔다(색인 크기). */
export interface SearchEntry {
  /** 종류 */
  k: SearchKind;
  /** 보이는 이름 */
  n: string;
  /** 다른 이름(약어, 영문, 한국어 이름, 국적). 보이지 않고 맞추기에만 쓴다 */
  a?: string;
  /** 오른쪽 작은 글(기간, 팀 등) */
  m?: string;
  /** 주소 */
  u: string;
  /** 같은 점수일 때 앞에 둘 무게(출전 수, 최근 시즌 등) */
  w?: number;
}

export const KIND_ORDER: SearchKind[] = ['driver', 'constructor', 'team', 'season', 'race', 'engine', 'regulation'];
export const KIND_LABEL: Record<SearchKind, string> = {
  driver: '드라이버',
  constructor: '컨스트럭터',
  team: '팀 계보',
  season: '시즌',
  race: '대회',
  engine: '엔진',
  regulation: '규정',
};

/** 검색용 글자: 소문자, 발음 구별 기호 제거(Räikkönen -> raikkonen), 공백 하나로. */
export function fold(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ø/gi, 'o')
    .replace(/ß/g, 'ss')
    .normalize('NFC')
    .toLowerCase()
    .replace(/[\s\-_.,·()]+/g, ' ')
    .trim();
}

/** 한 낱말이 글에 얼마나 잘 맞는지: 낱말 하나와 같음 4, 첫머리 3, 낱말 첫머리 2, 포함 1, 없으면 0 */
function tokenScore(token: string, text: string): number {
  if (!text) return 0;
  if (` ${text} `.includes(` ${token} `)) return 4;
  if (text.startsWith(token)) return 3;
  if (text.includes(` ${token}`)) return 2;
  return text.includes(token) ? 1 : 0;
}

export interface ScoredEntry extends SearchEntry {
  score: number;
}

/**
 * 검색어로 색인을 고른다. 검색어의 낱말은 모두 이름이나 다른 이름에 맞아야 한다.
 * 이름에 맞으면 다른 이름보다 점수를 높게 주되, 다른 이름의 낱말과 그대로 같으면(약어) 이름 첫머리보다 높다.
 * 같은 점수면 무게, 이름 순이다.
 */
export function searchEntries(entries: SearchEntry[], query: string): ScoredEntry[] {
  const tokens = fold(query).split(' ').filter(Boolean);
  if (!tokens.length) return [];
  const out: ScoredEntry[] = [];
  for (const e of entries) {
    const name = fold(e.n);
    const alias = fold(`${e.a ?? ''} ${e.m ?? ''}`);
    let total = 0;
    let ok = true;
    for (const t of tokens) {
      // 이름에 맞으면 두 배. 다른 이름(약어 VER 등)과 낱말 하나가 그대로 같으면 이름 첫머리보다 높게 둔다
      const al = tokenScore(t, alias);
      const s = Math.max(tokenScore(t, name) * 2, al === 4 ? 7 : al);
      if (!s) {
        ok = false;
        break;
      }
      total += s;
    }
    if (ok) out.push({ ...e, score: total + (fold(query) === name ? 10 : 0) });
  }
  return out.sort((x, y) => y.score - x.score || (y.w ?? 0) - (x.w ?? 0) || x.n.localeCompare(y.n));
}

/** 종류별로 묶고 묶음마다 limit개까지 남긴다. 묶음 순서는 가장 높은 점수 순, 같으면 KIND_ORDER 순. */
export function groupResults(results: ScoredEntry[], limit = 6): { kind: SearchKind; items: ScoredEntry[]; more: number }[] {
  const by = new Map<SearchKind, ScoredEntry[]>();
  for (const r of results) {
    const list = by.get(r.k) ?? [];
    list.push(r);
    by.set(r.k, list);
  }
  return [...by.entries()]
    .map(([kind, list]) => ({ kind, items: list.slice(0, limit), more: Math.max(0, list.length - limit), top: list[0].score }))
    .sort((a, b) => b.top - a.top || KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind))
    .map(({ kind, items, more }) => ({ kind, items, more }));
}
