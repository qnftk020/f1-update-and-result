// 배지, 아이콘, 범주 기호, 외부 링크의 HTML 문자열. 서버(.astro, DataTable의 render 함수)와
// 브라우저(차트 모듈의 icon(), badge())가 같은 SVG 문자열을 쓴다. 아이콘은 모두 고정 문자열이다.
import type { ReasonCategory } from './types.ts';
import { esc } from './typeset.ts';

export const ICONS = {
  wet: '<path d="M8 2.2c2.4 3 4 5.1 4 7.1a4 4 0 0 1-8 0c0-2 1.6-4.1 4-7.1Z" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  ref: '<path d="M8 2.5a5.5 5.5 0 1 1 0 11Z" fill="currentColor"/><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  unclassified:
    '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2 1.6"/><path d="M6.4 6.6a1.7 1.7 0 1 1 2.3 1.6c-.5.2-.7.5-.7 1v.3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="11.2" r=".8" fill="currentColor"/>',
  review:
    '<path d="M8 1.8 14.6 13.6H1.4Z" fill="var(--warn)" stroke="var(--warn-ink)" stroke-width="1.2" stroke-linejoin="round"/><path d="M8 6v3.6" stroke="var(--warn-ink)" stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="11.6" r=".9" fill="var(--warn-ink)"/>',
  sample:
    '<rect x="2.5" y="2.5" width="11" height="11" rx="1" fill="none" stroke="currentColor" stroke-width="1.4" stroke-dasharray="2.2 1.6"/>',
  external:
    '<path d="M6 3.5H3.5v9h9V10M9 3.5h3.5V7M12.3 3.7 7.5 8.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
  sprint:
    '<path d="M2.5 11.5h4l2-7 2 7h3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
  // 규정 아카이브: 등급 B(원본 미검증)와 등급 C(스캔본)
  unverified:
    '<rect x="2.5" y="2.5" width="11" height="11" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6 6.6a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6.9v.3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="8" cy="11.3" r=".75" fill="currentColor"/>',
  scan: '<rect x="3" y="2" width="10" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M1.5 8h13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  // PU 허용 초과(위험색 원 + 흰 느낌표). 허용 개수 자료가 생긴 뒤에만 쓴다.
  exceed:
    '<circle cx="8" cy="8" r="6.4" fill="var(--danger)" stroke="var(--warn-ink)" stroke-width="1.1"/><path d="M8 4.6v4.2" stroke="#fff" stroke-width="1.7" stroke-linecap="round"/><circle cx="8" cy="11.3" r=".95" fill="#fff"/>',
} as const;

export type IconName = keyof typeof ICONS;

/** 배지 종류. DESIGN.md "배지" 표: 우천, 참고용, 미분류, 검수 대기, 스프린트, 표본 값, 원본 미검증, 스캔본, 허용 초과 */
export type BadgeKind = IconName;

/** 13px 아이콘 SVG 문자열 */
export function iconSvg(name: IconName, cls = 'ic'): string {
  return `<svg class="${cls}" viewBox="0 0 16 16" aria-hidden="true">${ICONS[name]}</svg>`;
}

/**
 * 배지 HTML. badgeHtml('wet', '우천 예선'), badgeHtml('review', '검수 대기'), badgeHtml('ref', '참고용'),
 * badgeHtml('unclassified', '미분류'), badgeHtml('sprint', '스프린트'), badgeHtml('sample', '표본 값 (디자인용)').
 */
export function badgeHtml(kind: BadgeKind, text: string): string {
  return `<span class="badge badge-${kind}">${iconSvg(kind)}<span>${esc(text)}</span></span>`;
}

/** 여러 배지를 한 줄로: <span class="badges">…</span>. 비면 빈 문자열 */
export function badgesHtml(list: [BadgeKind, string][]): string {
  return list.length ? `<span class="badges">${list.map(([k, t]) => badgeHtml(k, t)).join('')}</span>` : '';
}

/** 변경 사유 범주 기호(■ □ ▲ ×)의 HTML. 색과 모양은 base.css의 [data-cat]이 정한다. */
export function glyphHtml(cat: ReasonCategory): string {
  return `<span class="rk" data-cat="${cat}" aria-hidden="true"></span>`;
}

/** FIA 원문 같은 외부 문서 링크. 아이콘과 낭독용 꼬리말이 붙는다. */
export function extHtml(url: string, text = 'FIA 원문 PDF'): string {
  return `<a class="ext" href="${esc(url)}" rel="noopener">${esc(text)}${iconSvg('external')}<span class="sr-only"> (외부 문서)</span></a>`;
}

/** 페이지 데이터 JSON을 <script type="application/json"> 안에 안전하게 넣는 문자열. '<' 문자를 유니코드 이스케이프로 바꾼다. */
export function jsonScript(data: unknown): string {
  // U+2028, U+2029(줄 구분자)도 막는다. 문자 그대로 쓰면 편집기와 도구가 줄바꿈으로 읽어 코드에서는 코드값으로 쓴다.
  const ls = String.fromCharCode(0x2028);
  const ps = String.fromCharCode(0x2029);
  return JSON.stringify(data ?? null)
    .replace(/</g, '\\u003c')
    .split(ls)
    .join('\\u2028')
    .split(ps)
    .join('\\u2029');
}
