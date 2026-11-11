// 규정 아카이브 자료(regulations.json, pipeline/site_data_extra.py build_regulations)의 타입과 도우미.
import { getOptional } from '../../lib/data.ts';
import { badgeHtml } from '../../lib/markup.ts';
import { url } from '../../lib/paths.ts';

export type Section = 'technical' | 'sporting';
export type Grade = 'A' | 'B' | 'C';

export interface RegCell {
  found: boolean;
  count: number;
  url: string | null;
  scan: boolean;
  parsed: number;
  review: number;
  note: string | null;
}

export interface RegYear {
  year: number;
  grade: Grade;
  technical: RegCell;
  sporting: RegCell;
  summaries: number;
}

export interface RegDocument {
  section: Section;
  title: string | null;
  language: string | null;
  issue: string | null;
  version: string | null;
  variant: string | null;
  published_at: string | null;
  url: string;
  host: string | null;
  format: string | null;
  grade: Grade;
  status: 'linked' | 'parsed' | 'listed' | 'needs_review' | string;
  note_ko: string | null;
  pages: number | null;
  clauses: number | null;
  version_key: string | null;
  /** 검수 대기 판: 파서가 적은 문제 */
  problems: string[];
  /** 검수 대기 판: 사람이 읽을 한국어 설명 */
  review_reasons: string[];
}

export interface RegChange {
  clause_no: string | null;
  top_article: string | null;
  top_title: string | null;
  heading: string | null;
  change: 'added' | 'removed' | 'modified' | string;
  renumbered: boolean;
  from_clause_no: string | null;
  page_from: number | null;
  page_to: number | null;
}

export interface RegComparison {
  kind: string;
  section: Section;
  from_season: number;
  from_version: string;
  from_issue: string | null;
  from_url: string | null;
  to_season: number;
  to_version: string;
  to_issue: string | null;
  to_url: string | null;
  clauses_from: number | null;
  clauses_to: number | null;
  added: number | null;
  removed: number | null;
  modified: number | null;
  unchanged: number | null;
  renumbered: number | null;
  /** 비교가 건너뛴 판(검수 대기, 받지 않음). 하나라도 있으면 review가 참이다 */
  skipped_versions: SkippedVersion[];
  review: boolean;
  changes: RegChange[];
}

export interface SkippedVersion {
  season: number;
  version: string;
  issue: string | null;
  url: string | null;
  status: string | null;
  review_reasons: string[];
}

export interface FinalIssue {
  issue: string | null;
  version: string | null;
  status: string;
  url: string | null;
  review_reasons: string[];
}

/** 규정에서 읽은 수치(pu_allocation_rules.csv, fuel_rules.csv). 인용문은 싣지 않는다 */
export interface RegFact {
  kind: 'pu_allocation' | 'fuel';
  section: Section;
  rule: string;
  element: string | null;
  value: string;
  clause_no: string | null;
  page: number | null;
  url: string | null;
  version_key: string | null;
  issue: string | null;
  is_final_issue: boolean | null;
  final_issue: FinalIssue | null;
}

export interface Regulations {
  first_year: number;
  last_year: number;
  as_of: string | null;
  summaries_verified_on: string | null;
  years: RegYear[];
  documents: Record<string, RegDocument[]>;
  summaries: Record<string, { section: Section; summary_ko: string; source_url: string | null; source_host: string | null; verified_on: string | null }[]>;
  comparisons: RegComparison[];
  facts: Record<string, RegFact[]>;
}

export const regulations = getOptional<Regulations>('regulations');

export const SECTIONS: Section[] = ['technical', 'sporting'];
export const SECTION_KO: Record<Section, string> = { technical: '기술 규정', sporting: '스포팅 규정' };
/** 등급 모양: 색으로 등급을 나타내지 않는다(DESIGN.md "규정 아카이브의 등급 행렬") */
export const GRADE_SHAPE: Record<Grade, string> = { A: '■', B: '◧', C: '□' };
export const GRADE_RANGE: Record<Grade, string> = { A: '2008-', B: '2001-2007', C: '1982-2000' };
export const CHANGE_KO: Record<string, { mark: string; label: string }> = {
  added: { mark: '+', label: '추가' },
  removed: { mark: '−', label: '삭제' },
  modified: { mark: 'Δ', label: '수정' },
};

export const yearHref = (y: number) => url(`/regulations/${y}/`);

export function gradeHtml(g: Grade): string {
  return `<span class="rg"><span class="rg-shape" aria-hidden="true">${GRADE_SHAPE[g]}</span> <span class="rg-letter">${g}</span><span class="sr-only">등급</span></span>`;
}

/** 등급 배지: B는 원본 미검증, C는 스캔본(스캔이 아닌 사본은 원본 미검증) */
export function gradeBadge(g: Grade, scan: boolean): string {
  if (g === 'B') return badgeHtml('unverified', '원본 미검증');
  if (g === 'C') return scan ? badgeHtml('scan', '스캔본') : badgeHtml('unverified', '원본 미검증');
  return '';
}

export function docBadge(d: RegDocument): string {
  if (d.grade === 'C') return d.format === 'scan' ? badgeHtml('scan', '스캔본') : badgeHtml('unverified', '원본 미검증');
  if (d.grade === 'B') return badgeHtml('unverified', '원본 미검증');
  return '';
}

export const decadeGroups = (years: number[], current?: number) => {
  const groups = new Map<number, number[]>();
  for (const y of [...years].sort((a, b) => a - b)) {
    const dec = Math.floor(y / 10) * 10;
    if (!groups.has(dec)) groups.set(dec, []);
    groups.get(dec)!.push(y);
  }
  return [...groups.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([dec, ys]) => ({ label: `${dec}년대`, links: ys.map((y) => ({ href: yearHref(y), text: String(y), current: y === current })) }));
};

/** 판 이름: "Issue 5 (2025-04-30)", Issue 번호가 없으면 판 날짜 */
export const issueName = (issue: string | null, version: string | null) =>
  issue ? `Issue ${issue}${version ? ` (${version})` : ''}` : version ? `${version} 판` : '판';

/** 비교가 건너뛴 판 목록 문장(HTML). 판마다 원문 링크와 상태를 적는다 */
export function skippedHtml(c: RegComparison, esc: (s: string) => string): string {
  if (!c.skipped_versions.length) return '';
  const items = c.skipped_versions.map((k) => {
    const name = esc(`${k.season} ${issueName(k.issue, k.version)}`);
    const linked = k.url ? `<a href="${esc(k.url)}" rel="noopener">${name}</a>` : name;
    const state = k.status === 'needs_review' ? '검수 대기' : k.status === 'listed' ? '받지 않음' : esc(k.status ?? '상태 기록 없음');
    return `${linked}(${state})`;
  });
  // 판의 상태를 그대로 적는다. 검수 대기 판은 조항을 읽었지만 확인을 마치지 않은 판이라 "파싱하지 못한 판"이 아니다
  const statuses = new Set(c.skipped_versions.map((k) => k.status));
  const kinds = [statuses.has('needs_review') && '검수 대기', statuses.has('listed') && '받지 않은'].filter(Boolean);
  const known = [...statuses].every((s) => s === 'needs_review' || s === 'listed');
  const kind = !known
    ? '비교에 넣지 않은'
    : kinds.length === 2
      ? '검수 대기이거나 받지 않은'
      : kinds[0] === '검수 대기'
        ? '검수 대기인'
        : '받지 않은';
  const n = c.skipped_versions.length;
  const those = n === 1 ? '그 판에서' : '그 판들에서';
  return `이 비교는 ${kind} 판 ${n}개를 건너뛰었다: ${items.join(', ')}. ${those} 바뀐 내용은 앞뒤 두 판의 차이로 한꺼번에 나온다.`;
}

export const FACT_KO: Record<string, string> = {
  pu_allocation: 'PU 구성요소 할당 수',
  race_fuel_mass: '결승 연료 질량 상한',
  max_fuel_mass_flow: '최대 연료 유량',
};
