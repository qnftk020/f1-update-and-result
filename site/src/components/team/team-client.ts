// 팀 페이지의 브라우저 동작. 차트는 BaseLayout의 mountAll()이 그리고(f-tq, f-tr, f-steps, f-season),
// 이 스크립트는 손잡이를 받아 다시 그린다. 업그레이드 단위 차트(f-units)는 onSelect가 필요해 여기서 직접 그린다.
// 문장은 빌드 때 만든 HTML을 바꿔 끼우고(innerHTML), 데이터에서 온 글자는 textContent로만 넣는다.
import { badge, el, icon, mount, readJson, ready, upgradeItemNode, upgradeUnits } from '../../lib/charts/mount.ts';
import type { UpgradeItem } from '../../lib/types.ts';

interface TimelineRow {
  round: number;
  short: string;
  name: string;
  status: string;
  doc_review: boolean;
  url: string | null;
  published_at: string | null;
  n: number;
}

interface PaceData {
  quali: unknown;
  race: unknown;
  cid: string;
  team: string;
  rail: { round: number; n: number }[];
  q: string;
  r: string;
  src: string;
}

interface PageData {
  timeline: Record<string, TimelineRow[]>;
  items: UpgradeItem[];
  labels: { component_areas: Record<string, string>; reason_categories: Record<string, string> };
  selected: { season: number; round: number } | null;
  unitsLabel: string;
  pace: Record<string, PaceData>;
  lin: {
    has: boolean;
    first: number;
    curFrom: number;
    qFirst: number;
    qCur: number;
    C: string;
    scopeOn: string;
    scopeOff: string;
    longOn: string;
    longOff: string;
    steps: { on: string; off: string };
    trend: { on: string; off: string };
    meta: { on: string; off: string };
    refOff: boolean;
    legend: { on: string; off: string };
    statsOn: string[];
    statsOff: string[];
  };
}

const $ = <T extends Element = HTMLElement>(sel: string) => document.querySelector<T>(sel);
const $$ = <T extends Element = HTMLElement>(sel: string) => [...document.querySelectorAll<T>(sel)];

function h(tag: string, cls: string | null, text?: string | null, attrs?: Record<string, string>) {
  const n = el(tag, cls, text) as HTMLElement;
  if (attrs) for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

function extLink(url: string): HTMLElement {
  const a = h('a', 'ext', 'FIA 원문 PDF', { href: url, rel: 'noopener' });
  a.append(icon('external'), h('span', 'sr-only', ' (외부 문서)'));
  return a;
}

export function initTeamPage(): void {
  const D = readJson<PageData>('team-page');

  ready
    .then((handles) => {
      initUpgrades(D);
      initPace(D, handles);
      initLineage(D, handles);
      initPu(handles);
    })
    .catch((err) => window.chartFallback(err));
}

/* ---------------------------------------------------------------- 업그레이드: 단위 차트와 대회 고르기 */
function initUpgrades(D: PageData): void {
  const slot = $('#f-units .viz');
  if (!slot) return;
  let selected = D.selected;
  const units = mount(slot, upgradeUnits, D.timeline, {
    selected,
    label: D.unitsLabel,
    onSelect: (s: number, r: number) => pick(s, r, true),
  });
  const sel = $<HTMLSelectElement>('#ev-select');
  const prev = $<HTMLButtonElement>('#ev-prev');
  const next = $<HTMLButtonElement>('#ev-next');
  if (!sel || !prev || !next) return;
  const opts = [...sel.options].map((o) => o.value);

  function pick(s: number, r: number, scroll = false): void {
    const row = (D.timeline[String(s)] || []).find((d) => d.round === r);
    const its = D.items.filter((i) => i.season === s && i.round === r);
    selected = { season: s, round: r };
    units.redraw(null, { selected });
    if (!row || !its.length || !sel || !prev || !next) return;
    const key = `${s}-${r}`;
    sel.value = key;
    const title = $('#ev-title');
    if (title) {
      const left = h('span', null, `${s} ${r}라운드 ${row.short} `);
      left.append(h('span', 'muted', row.name, { lang: 'en', style: 'font-weight:400' }));
      const right = h('span', 'sec-meta', `${its.length}건 · 문서 게시 `);
      right.append(h('span', 'nw', (row.published_at || '').slice(0, 10)), document.createTextNode(' · '));
      if (row.doc_review) right.append(badge('review', '검수 대기 문서'), document.createTextNode(' '));
      if (row.url) right.append(extLink(row.url));
      title.replaceChildren(left, right);
    }
    $('#ev-items')?.replaceChildren(...its.map((i) => upgradeItemNode(i, D.labels, { showTeam: false })));
    const idx = opts.indexOf(key);
    // 끝에 닿아도 disabled 대신 aria-disabled: 초점이 단추에 남는다. 목록은 최근 대회가 먼저다.
    prev.setAttribute('aria-disabled', String(idx >= opts.length - 1));
    next.setAttribute('aria-disabled', String(idx <= 0));
    if (scroll) {
      const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
      $('#event-pick')?.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' });
    }
  }

  sel.addEventListener('change', () => {
    const [s, r] = sel.value.split('-').map(Number);
    pick(s, r);
  });
  const step = (btn: HTMLButtonElement, d: number) =>
    btn.addEventListener('click', () => {
      if (btn.getAttribute('aria-disabled') === 'true') return;
      const i = opts.indexOf(sel.value) + d;
      if (i >= 0 && i < opts.length) {
        const [s, r] = opts[i].split('-').map(Number);
        pick(s, r);
      }
    });
  step(prev, 1);
  step(next, -1);
  if (selected) pick(selected.season, selected.round);
}

/* ---------------------------------------------------------------- 시즌 안의 페이스: 시즌 전환 */
function initPace(D: PageData, handles: Map<string, { redraw: (d?: unknown, o?: Record<string, unknown>) => void }>): void {
  const tq = handles.get('f-tq');
  const tr = handles.get('f-tr');
  const btns = $$<HTMLButtonElement>('[data-season]');
  const show = (yr: string) => {
    const p = D.pace[yr];
    if (!p) return;
    tq?.redraw(p.quali, { cid: p.cid, team: p.team, rail: p.rail, label: `${p.team} 퀄리파잉 지수와 필드` });
    tr?.redraw(p.race, { cid: p.cid, team: p.team, rail: p.rail, label: `${p.team} 레이스 지수와 95% 구간` });
    const qRead = $('#pace-read');
    const rRead = $('#pace-race-read');
    if (qRead) qRead.innerHTML = p.q; // 빌드 때 만든 문장
    if (rRead) rRead.innerHTML = p.r;
    const qs = $('#tq-scope');
    const rs = $('#tr-scope');
    if (qs) qs.textContent = `${yr} · 라운드별 · 위가 빠르다`;
    if (rs) rs.textContent = `${yr} · 결승 클린 랩 · 95% 구간`;
    const src = $('#tq-src');
    if (src) src.innerHTML = p.src; // 빌드 때 만든 출처 줄
    $$('#pace .tname').forEach((n) => (n.textContent = p.team));
    $$('[data-pace-year]').forEach((n) => (n.hidden = n.dataset.paceYear !== yr));
    btns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.season === yr)));
  };
  btns.forEach((b) => b.addEventListener('click', () => show(b.dataset.season || '')));
}

/* ---------------------------------------------------------------- 계보 보기 */
function initLineage(D: PageData, handles: Map<string, { redraw: (d?: unknown, o?: Record<string, unknown>) => void }>): void {
  const sw = $<HTMLButtonElement>('#lineage-switch');
  const L = D.lin;
  if (!sw || !L.has) return;
  const steps = handles.get('f-steps');
  const trend = handles.get('f-season');
  let lineage = true;
  sw.addEventListener('click', () => {
    lineage = sw.getAttribute('aria-checked') !== 'true';
    sw.setAttribute('aria-checked', String(lineage));
    const scope = $('#scope-text');
    if (scope) scope.innerHTML = lineage ? L.scopeOn : L.scopeOff;
    steps?.redraw(null, { from: lineage ? L.first : L.curFrom });
    trend?.redraw(null, { from: lineage ? L.qFirst : L.qCur, teamLabel: lineage ? '계보' : L.C });
    const long = $('#long-read');
    if (long) long.innerHTML = lineage ? L.longOn : L.longOff;
    const k = lineage ? 'on' : 'off';
    $$('[data-lin-scope]').forEach((s) => {
      const which = s.dataset.linScope as 'steps' | 'trend' | 'meta';
      s.textContent = L[which][k];
    });
    $$('.ribbon .era').forEach((e) => e.classList.toggle('is-out', !lineage && !e.classList.contains('is-current')));
    $$('.era-list li').forEach((e) => (e.hidden = !lineage && !e.classList.contains('is-current')));
    $$('tr.lin-only').forEach((r) => (r.hidden = !lineage));
    // 접힌 표의 행이 모두 계보 앞 시기면 펼침 단추째 숨긴다
    $$('#record details.more').forEach((d) => {
      const rows = [...d.querySelectorAll('tbody tr')];
      d.hidden = !lineage && rows.length > 0 && rows.every((r) => r.classList.contains('lin-only'));
    });
    $$<HTMLElement>('#lin-stats dd').forEach((dd, i) => (dd.textContent = (lineage ? L.statsOn : L.statsOff)[i] ?? ''));
    const lg = $('[data-lin-legend]');
    if (lg) lg.textContent = L.legend[k];
    const refKey = $('#f-season [data-ref-key]');
    if (refKey) refKey.closest('li')!.hidden = !lineage && !L.refOff;
  });
}

/* ---------------------------------------------------------------- PU: 구성요소 전환 */
function initPu(handles: Map<string, { redraw: (d?: unknown, o?: Record<string, unknown>) => void }>): void {
  const pu = handles.get('f-pu');
  const btns = $$<HTMLButtonElement>('button[data-pu-el]');
  if (!pu || !btns.length) return;
  const team = ($('#f-pu .fig-scope [lang="en"]')?.textContent || '').trim();
  btns.forEach((b) =>
    b.addEventListener('click', () => {
      const el = b.dataset.puEl || 'ICE';
      pu.redraw(null, { element: el, label: `${team} ${el} 누적 사용 개수` });
      $$('#f-pu .pu-el').forEach((n) => (n.textContent = el));
      $$('#f-pu div[data-pu-el]').forEach((n) => (n.hidden = n.dataset.puEl !== el));
      btns.forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    }),
  );
}
