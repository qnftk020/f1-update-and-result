// 업그레이드 탐색기의 빌드 때 자료(서버 전용). upgrades.json을 대회별 묶음으로 나누고, 정적 문장과 표, 선택지,
// 항목 HTML을 만든다. 브라우저는 이 HTML의 data 속성과 작은 JSON(ex-meta)만 읽고 큰 JSON은 싣지 않는다.
import { labels, teams, upgrades } from '../../lib/data.ts';
import { badgeHtml } from '../../lib/markup.ts';
import type { UpgradeDocument, UpgradeItem } from '../../lib/types.ts';
import { esc } from '../../lib/typeset.ts';
import { CAT_ORDER, PAGE, type Cat, docScope, eventLabel, leadHtml, topOf } from './explorer-text.ts';

export const AREA = labels.component_areas;
export const CAT: Record<Cat, string> = Object.fromEntries(
  CAT_ORDER.map((c) => [c, labels.reason_categories[c]]),
) as Record<Cat, string>;

const items = upgrades.items;
const docs = upgrades.documents;
export const TOTAL = items.length;
export const DOCS = docs.length;

const seasonsAll = [...new Set(items.map((i) => i.season))].sort((a, b) => a - b);
export const YEARS = `${seasonsAll[0]}-${seasonsAll[seasonsAll.length - 1]}`;
export const SEASONS = [...seasonsAll].reverse();

/** 계보 -> 2025 이름(teams.json) */
export const TEAM25: Record<string, string> = Object.fromEntries(teams.map((t) => [t.lineage_id, t.constructor.name]));
const lin = (i: UpgradeItem) => i.lineage_id ?? i.constructor_id;
const teamName = (id: string) => TEAM25[id] ?? id;

/** 팀 선택지: 2025 이름 순, 옛 이름은 괄호로("Racing Bulls (AlphaTauri, RB)") */
export const TEAM_OPTIONS = (() => {
  const names = new Map<string, Set<string>>();
  for (const i of items) {
    const k = lin(i);
    if (!names.has(k)) names.set(k, new Set());
    names.get(k)!.add(i.team);
  }
  return [...names.entries()]
    .map(([k, set]) => {
      const now = teamName(k);
      const old = [...set].filter((n) => n !== now).sort((a, b) => a.localeCompare(b, 'en'));
      return { value: k, label: old.length ? `${now} (${old.join(', ')})` : now, name: now };
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'en'));
})();

export const catCounts: Record<Cat, number> = { performance: 0, circuit_specific: 0, reliability: 0, other: 0 };
export const areaCounts: Record<string, number> = {};
for (const i of items) {
  catCounts[i.category as Cat] += 1;
  areaCounts[i.area] = (areaCounts[i.area] ?? 0) + 1;
}
/** 부품 영역 키를 건수 순으로(같으면 labels 순서) */
export const AREA_ORDER = Object.keys(AREA).sort((a, b) => (areaCounts[b] ?? 0) - (areaCounts[a] ?? 0));
/** 원문 부품 표기의 가짓수(부품 영역 주석) */
export const COMPONENT_SPELLINGS = new Set(items.map((i) => i.component)).size;

export const lead = leadHtml({
  total: TOTAL,
  n: TOTAL,
  docs: DOCS,
  allDocs: DOCS,
  years: YEARS,
  area: (() => {
    const t = topOf(areaCounts, AREA_ORDER);
    return t ? [AREA[t[0]], t[1]] : null;
  })(),
  cat: (() => {
    const t = topOf(catCounts, [...CAT_ORDER]);
    return t ? [CAT[t[0] as Cat], t[1]] : null;
  })(),
  filtered: false,
});

/** 시즌별 문서 범위. 2023년이 fia.com 공개분뿐이라는 사실은 data_inventory와 methodology에 적힌 것이다.
 * 다른 시즌은 문서 부재 대회(missing_events)를 이름으로 적는다. */
export const scopeText = docScope(
  seasonsAll.map((y) => {
    const n = docs.filter((d) => d.season === y).length;
    const missing = upgrades.missing_events.filter((m) => m.season === y);
    const note =
      y === 2023 ? 'fia.com 공개분' : missing.length ? `${missing.map((m) => m.event_short_ko).join(', ')} 문서 부재` : '';
    return [y, n, note] as [number, number, string];
  }),
);

/** 검수 대기 문서: 읽지 못한 팀(2025 이름)과 읽은 팀 수 */
export function reviewTeams(d: UpgradeDocument): { bad: string[]; ok: number } {
  const bad = d.teams.filter((t) => t.status === 'needs_review').map((t) => teamName(t.lineage_id ?? t.constructor_id));
  return { bad, ok: d.teams.length - bad.length };
}
export const REVIEW_DOCS = docs.filter((d) => d.review);

/** 팀별 묶음(정적 표 보기): 많은 순 */
export const teamGroups = (() => {
  const by = new Map<string, { label: string; total: number; cats: Record<Cat, number> }>();
  for (const i of items) {
    const k = lin(i);
    if (!by.has(k)) by.set(k, { label: teamName(k), total: 0, cats: { performance: 0, circuit_specific: 0, reliability: 0, other: 0 } });
    const g = by.get(k)!;
    g.total += 1;
    g.cats[i.category as Cat] += 1;
  }
  return [...by.values()].sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'en'));
})();

/** 브라우저가 쓰는 작은 자료: 문서별 팀 상태(빈 상태 까닭), 이름표 */
export const clientMeta = {
  total: TOTAL,
  years: YEARS,
  page: PAGE,
  areas: AREA,
  cats: CAT,
  teams: TEAM25,
  /** 항목에 적힌 그 시즌 팀 이름 -> 계보 */
  byName: Object.fromEntries(items.map((i) => [i.team, lin(i)])),
  docs: docs.map((d) => ({
    k: `${d.season}-${d.round}`,
    s: d.season,
    r: d.round,
    short: d.event_short_ko,
    n: d.items,
    review: d.review,
    st: Object.fromEntries(d.teams.map((t) => [t.lineage_id ?? t.constructor_id, t.status])),
  })),
};

// ------------------------------------------------------------------ 대회별 묶음과 항목 HTML

export interface EventGroup {
  key: string;
  season: number;
  round: number;
  label: string;
  doc: UpgradeDocument;
  items: UpgradeItem[];
  /** 이 묶음의 첫 항목이 전체 목록에서 몇 번째인지(처음 PAGE건만 스크립트가 있을 때 보인다) */
  offset: number;
}

const order = new Map(items.map((i, k) => [i, k]));
export const GROUPS: EventGroup[] = (() => {
  const sorted = [...docs].sort((a, b) => b.season - a.season || b.round - a.round);
  let offset = 0;
  return sorted.map((d) => {
    const list = items
      .filter((i) => i.season === d.season && i.round === d.round)
      .sort((a, b) => a.team.localeCompare(b.team, 'en') || order.get(a)! - order.get(b)!);
    const g = { key: `${d.season}-${d.round}`, season: d.season, round: d.round, label: eventLabel(d.season, d.round, d.event_short_ko), doc: d, items: list, offset };
    offset += list.length;
    return g;
  });
})();

/** 스크립트가 있을 때 처음에 숨겨 둘 묶음: 앞 PAGE건 안에 든 항목이 없거나, 항목 0건 문서가 PAGE건 뒤에 있으면 */
export function groupBeyond(g: EventGroup): boolean {
  return g.offset >= PAGE;
}

const CLAMP = 260;

/**
 * 항목 한 건의 HTML. 공용 UpgradeItem과 같은 세 칸(어디, 무엇, 내용)이지만 855건을 모두 정적으로 싣는 무게를
 * 줄이려고 마크업을 덜어 냈다. 대회 이름과 FIA 원문 링크는 대회 묶음 머리가 맡고, 어디 칸은 팀, 항목 번호, 문서 쪽이다.
 * 칸은 짧은 클래스(w, c, t)이고 모양은 페이지의 .ex-list 규칙이 공용 .item 모양과 같게 맞춘다. 공백과 따옴표가
 * 필요 없는 속성 값은 따옴표를 생략한다(HTML 문법상 같은 값이다).
 * 거르기 값은 따로 싣지 않는다. 브라우저가 팀 이름(.w b), 부품 영역 이름(.c small), 범주 기호(.rk의 data-cat)를
 * 같은 이름표(ex-meta)로 되짚는다. 긴 설명에는 공용 boot.ts의 "전체 보기"가 찾는 .item-text를 함께 단다.
 * 범주 기호는 글자가 없는 빈 칸이라 낭독되지 않는다.
 */
export function itemHtml(i: UpgradeItem, page: number | undefined, index: number, groupOut = false): string {
  const long = (i.description || '').length > CLAMP;
  const where = `<p class=w><b>${esc(i.team)}</b> <span>항목 ${esc(i.no)}${page ? ` · ${page}쪽` : ''}</span></p>`;
  const comp =
    `<div class=c><b lang=en>${esc(i.component)}</b><small>${esc(AREA[i.area] ?? i.area)}</small>` +
    `<p><span><span class=rk data-cat=${i.category}></span>${esc(CAT[i.category as Cat])}</span><span lang=en>${esc(i.reason)}</span></p>` +
    `${i.review ? badgeHtml('review', '검수 대기 문서') : ''}</div>`;
  const text =
    `<div class=${long ? '"t item-text"' : 't'}><p><small>형상 차이</small> <span lang=en>${esc(i.geometry ?? '')}</span></p>` +
    `<p${long ? ' class=clamp' : ''}><small>설명</small> <span lang=en>${esc(i.description ?? '')}</span></p>` +
    (long ? '<p class="item-actions"><button class="linkbtn" type="button" aria-expanded="false" data-clamp-toggle data-js-only>전체 보기</button></p>' : '') +
    '</div>';
  // 처음 PAGE건 밖의 항목은 스크립트가 있을 때 숨긴다. 묶음 전체가 밖이면 묶음(.ex-ev.ex-x)이 숨기므로 항목에는 달지 않는다.
  return `<article${index >= PAGE && !groupOut ? ' class=ex-x' : ''}>${where}${comp}${text}</article>`;
}

/** 묶음의 팀별 문서 쪽 */
export function pagesOf(d: UpgradeDocument): Map<string, number> {
  return new Map(d.teams.map((t) => [t.constructor_id, t.page]));
}
