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
}

export interface RegChange {
  clause_no: string | null;
  top_article: string | null;
  top_title: string | null;
  heading: string | null;
  change: 'added' | 'removed' | 'modified' | string;
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
  changes: RegChange[];
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
