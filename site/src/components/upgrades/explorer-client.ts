// 업그레이드 탐색기의 브라우저 동작. 정적 HTML에 모두 실린 항목(대회 묶음 .ex-ev[data-ev] 안의 article)을 거른다.
// 항목의 팀, 부품 영역, 범주는 화면 글자(팀 이름, 부품 영역 이름)와 범주 기호의 data-cat을 이름표(ex-meta)로 되짚어 읽는다.
// 리드, 결과 줄과 결과 칩, 범주 칩 건수, 요약 두 그림과 표 보기, 대회 묶음, 빈 상태, 더 보기가 모두 같은 조건을 따른다.
// 조건은 주소 조각(#season=2025&team=enstone)에 남는다. 거르기는 차트 모듈 없이도 돈다(그림만 그 모듈을 쓴다).
// 데이터에서 온 글자는 textContent로만 넣는다. innerHTML은 고정 틀로 만든 리드 문장에만 쓴다.
import { n0 } from '../../lib/format.ts';
import { keepNames, typeset } from '../../lib/typeset.ts';
import { CAT_ORDER, type Cat, PAGE, eventLabel, leadHtml, topOf } from './explorer-text.ts';

interface Meta {
  total: number;
  years: string;
  areas: Record<string, string>;
  cats: Record<Cat, string>;
  teams: Record<string, string>;
  byName: Record<string, string>;
  docs: { k: string; s: number; r: number; short: string; n: number; review: boolean; st: Record<string, string> }[];
}

interface Row {
  el: HTMLElement;
  ev: string;
  s: string;
  t: string;
  a: string;
  c: Cat;
  text: string;
}

interface Group {
  el: HTMLElement;
  key: string;
  s: string;
  count: HTMLElement | null;
  rows: Row[];
}

type Key = 'season' | 'event' | 'team' | 'area' | 'q';
type GroupBy = 'team' | 'area' | 'event';

interface ChartHandle {
  redraw: (data?: unknown, opts?: Record<string, unknown>) => void;
}

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string | null, text?: string | null, attrs?: Record<string, string>) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  if (attrs) for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

/** 표 보기(정적 DataTable compact, 차트 모듈의 tableTwin과 같은 마크업) */
function twinTable(caption: string, columns: { label: string; num?: boolean }[], rows: (string | number)[][]): HTMLElement {
  const wrap = h('div', 'tbl-wrap', null, { role: 'region', tabindex: '0', 'aria-label': caption });
  const t = h('table', 'dt dt-compact');
  const head = h('tr');
  for (const c of columns) head.append(h('th', c.num ? 'num' : null, c.label, { scope: 'col' }));
  const thead = h('thead');
  thead.append(head);
  const tb = h('tbody');
  for (const r of rows) {
    const tr = h('tr');
    r.forEach((v, k) => tr.append(h('td', columns[k].num ? 'num' : null, String(v))));
    tb.append(tr);
  }
  t.append(h('caption', 'sr-only', caption), thead, tb);
  wrap.append(t);
  return wrap;
}

export function start(): void {
  const metaNode = document.getElementById('ex-meta');
  if (!metaNode) return;
  const M = JSON.parse(metaNode.textContent || '{}') as Meta;
  const CATS = [...CAT_ORDER] as Cat[];
  const AREA_KEYS = Object.keys(M.areas);
  const docsBy = new Map(M.docs.map((d) => [d.k, d]));
  const areaByName = Object.fromEntries(Object.entries(M.areas).map(([k, v]) => [v, k]));

  // 정적 항목을 읽어 둔다. 처음 20건 밖을 숨기던 .ex-x는 여기서 hidden으로 넘겨받는다.
  const groups: Group[] = [...document.querySelectorAll<HTMLElement>('#item-list .ex-ev')].map((g) => {
    const key = g.dataset.ev || '';
    const s = g.dataset.s || '';
    const rows = [...g.querySelectorAll<HTMLElement>('article')].map((el) => ({
      el,
      ev: key,
      s,
      t: M.byName[el.querySelector('.w b')?.textContent || ''] || '',
      a: areaByName[el.querySelector('.c small')?.textContent || ''] || '',
      c: (el.querySelector<HTMLElement>('.c .rk')?.dataset.cat || 'other') as Cat,
      text: [...el.querySelectorAll('[lang="en"]')].map((n) => n.textContent || '').join(' ').toLowerCase(),
    }));
    return { el: g, key, s, count: g.querySelector<HTMLElement>('.ex-ev-n'), rows };
  });
  const rows = groups.flatMap((g) => g.rows);
  const TOTAL = rows.length;

  const state = {
    season: '',
    event: '',
    team: '',
    area: '',
    q: '',
    cats: new Set<Cat>(CATS),
    group: 'team' as GroupBy,
    shown: PAGE,
  };

  const KEYS: Key[] = ['season', 'event', 'team', 'area', 'q'];
  const fromHash = () => {
    const p = new URLSearchParams(location.hash.slice(1));
    for (const k of KEYS) state[k] = p.get(k) ?? '';
    if (state.season && !M.docs.some((d) => String(d.s) === state.season)) state.season = '';
    if (state.event && !docsBy.has(state.event)) state.event = '';
    if (state.team && !M.teams[state.team]) state.team = '';
    if (state.area && !M.areas[state.area]) state.area = '';
    state.cats = p.has('cats') ? new Set(CATS.filter((c) => (p.get('cats') || '').split(',').includes(c))) : new Set(CATS);
  };
  const toHash = () => {
    const p = new URLSearchParams();
    for (const k of KEYS) if (state[k]) p.set(k, state[k]);
    if (state.cats.size < CATS.length) p.set('cats', [...state.cats].join(','));
    const s = p.toString();
    history.replaceState(null, '', s ? `#${s}` : location.pathname + location.search);
  };

  const anyItemFilter = () => Boolean(state.team || state.area || state.q.trim() || state.cats.size < CATS.length);
  const anyFilter = () => Boolean(state.season || state.event || anyItemFilter());
  const inScope = (s: string, ev: string) => (!state.season || s === state.season) && (!state.event || ev === state.event);

  function match(r: Row, skip?: 'cats'): boolean {
    const q = state.q.trim().toLowerCase();
    return (
      inScope(r.s, r.ev) &&
      (!state.team || r.t === state.team) &&
      (!state.area || r.a === state.area) &&
      (skip === 'cats' || state.cats.has(r.c)) &&
      (!q || r.text.includes(q))
    );
  }

  // ---------------------------------------------------------------- 선택지

  const evSel = $<HTMLSelectElement>('f-event');
  function eventOptions() {
    const docs = M.docs
      .filter((d) => !state.season || String(d.s) === state.season)
      .slice()
      .sort((a, b) => b.s - a.s || b.r - a.r);
    evSel.replaceChildren(
      h('option', null, `전체 대회 (${docs.length})`, { value: '' }),
      ...docs.map((d) => h('option', null, `${eventLabel(d.s, d.r, d.short)}${d.review ? ' (검수 대기)' : ''}`, { value: d.k })),
    );
    if (state.event && !docs.some((d) => d.k === state.event)) state.event = '';
    evSel.value = state.event;
  }

  // ---------------------------------------------------------------- 그림

  let share: ChartHandle | null = null;
  let grouped: ChartHandle | null = null;
  let lastCounts: Record<string, number> = {};
  let lastGroups: ReturnType<typeof groupsOf> = [];

  function groupsOf(list: Row[]) {
    const by = new Map<string, { key: string; label: string; cats: Record<string, number>; total: number; season?: number; review?: boolean }>();
    const add = (key: string, label: string, extra: Record<string, unknown> = {}) => {
      if (!by.has(key)) by.set(key, { key, label, cats: { performance: 0, circuit_specific: 0, reliability: 0, other: 0 }, total: 0, ...extra });
      return by.get(key)!;
    };
    if (state.group === 'event') {
      for (const d of M.docs) if (inScope(String(d.s), d.k)) add(d.k, eventLabel(d.s, d.r, d.short), { season: d.s, review: d.review });
    }
    for (const r of list) {
      const key = state.group === 'team' ? r.t : state.group === 'area' ? r.a : r.ev;
      const d = docsBy.get(r.ev);
      const label = state.group === 'team' ? M.teams[r.t] || r.t : state.group === 'area' ? M.areas[r.a] || r.a : d ? eventLabel(d.s, d.r, d.short) : r.ev;
      const g = add(key, label, state.group === 'event' && d ? { season: d.s, review: d.review } : {});
      g.cats[r.c] += 1;
      g.total += 1;
    }
    const arr = [...by.values()];
    if (state.group === 'event') return arr.sort((a, b) => a.key.localeCompare(b.key, 'en', { numeric: true }));
    return arr.sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'en'));
  }

  const TITLES: Record<GroupBy, string> = { team: '팀별 항목 수', area: '부품 영역별 항목 수', event: '대회별 항목 수' };
  const HEAD: Record<GroupBy, string> = { team: '팀', area: '부품 영역', event: '대회' };

  function drawCharts() {
    share?.redraw(lastCounts);
    grouped?.redraw(lastGroups, { orient: state.group === 'event' ? 'v' : 'h', label: TITLES[state.group] });
  }

  // ---------------------------------------------------------------- 결과 칩

  function activeChips(): number {
    const box = $('active');
    const out: HTMLButtonElement[] = [];
    // 칩을 지우면 칩 목록이 다시 만들어진다. 초점은 같은 자리(없으면 앞 자리) 칩으로, 칩이 다 사라지면 결과 줄로 옮긴다.
    const add = (lab: string, clear: () => void) => {
      const b = h('button', null, lab, { type: 'button', 'aria-label': `${lab} 조건 지우기` });
      b.addEventListener('click', () => {
        const k = out.indexOf(b);
        clear();
        sync();
        const cs = box.querySelectorAll<HTMLButtonElement>('button');
        (cs[k] || cs[k - 1] || $('result')).focus();
      });
      out.push(b);
    };
    if (state.season) add(`시즌: ${state.season}`, () => (state.season = ''));
    if (state.event) {
      const d = docsBy.get(state.event);
      add(`대회: ${d ? eventLabel(d.s, d.r, d.short) : state.event}`, () => (state.event = ''));
    }
    if (state.team) add(`팀: ${M.teams[state.team] || state.team}`, () => (state.team = ''));
    if (state.area) add(`부품 영역: ${M.areas[state.area] || state.area}`, () => (state.area = ''));
    if (state.cats.size < CATS.length) {
      const on = CATS.filter((c) => state.cats.has(c)).map((c) => M.cats[c]);
      add(`변경 사유: ${on.length ? on.join(', ') : '0개 범주'}`, () => (state.cats = new Set(CATS)));
    }
    if (state.q.trim()) add(`검색: ${state.q.trim()}`, () => (state.q = ''));
    box.replaceChildren(...out);
    return out.length;
  }

  // ---------------------------------------------------------------- 빈 상태

  function emptyWhy(): string {
    const d = state.event ? docsBy.get(state.event) : undefined;
    if (d && state.team) {
      const st = d.st[state.team];
      if (st === 'no_updates') return `${eventLabel(d.s, d.r, d.short)} 문서에는 이 팀이 No updates submitted로 적혀 있다.`;
      if (st === 'needs_review') return `${eventLabel(d.s, d.r, d.short)} 문서의 이 팀 쪽은 검수 대기다. 표가 그림으로만 들어 있어 읽지 않았다.`;
    } else if (d && d.n === 0) {
      return `${eventLabel(d.s, d.r, d.short)} 문서에는 ${Object.keys(d.st).length}개 팀 모두 No updates submitted로 적혀 있다.`;
    }
    return '고른 조건을 모두 만족하는 항목이 문서에 없다.';
  }

  // ---------------------------------------------------------------- 그리기

  function render() {
    const list = rows.filter((r) => match(r));
    const n = activeChips();
    $('result').querySelector('.result-n')!.textContent = n0(list.length);
    $('result').querySelector('.result-of')!.textContent = `${n0(TOTAL)}건 가운데 · 조건 ${n}개`;

    // 리드
    const areas: Record<string, number> = {};
    const cats: Record<string, number> = {};
    const docs = new Set<string>();
    for (const r of list) {
      areas[r.a] = (areas[r.a] || 0) + 1;
      cats[r.c] = (cats[r.c] || 0) + 1;
      docs.add(r.ev);
    }
    const ta = topOf(areas, Object.keys(areas).sort((a, b) => areas[b] - areas[a] || AREA_KEYS.indexOf(a) - AREA_KEYS.indexOf(b)));
    const tc = topOf(cats, CATS);
    $('ex-lead').innerHTML = typeset(
      keepNames(
        leadHtml({
          total: TOTAL,
          n: list.length,
          docs: docs.size,
          allDocs: M.docs.length,
          years: M.years,
          area: ta ? [M.areas[ta[0]] || ta[0], ta[1]] : null,
          cat: tc ? [M.cats[tc[0] as Cat], tc[1]] : null,
          filtered: anyFilter(),
        }),
      ),
    );

    // 범주 칩: 범주 조건만 빼고 센 건수
    const catAll: Record<string, number> = {};
    for (const r of rows) if (match(r, 'cats')) catAll[r.c] = (catAll[r.c] || 0) + 1;
    document.querySelectorAll<HTMLInputElement>('#f-cats input').forEach((inp) => {
      const c = inp.value as Cat;
      const lab = inp.closest('.cat-chip')!;
      lab.classList.toggle('on', state.cats.has(c));
      inp.checked = state.cats.has(c);
      lab.querySelector('.n')!.textContent = String(catAll[c] || 0);
    });
    for (const id of ['f-season', 'f-event', 'f-team', 'f-area']) {
      const sel = $<HTMLSelectElement>(id);
      sel.classList.toggle('is-set', Boolean(sel.value));
    }

    // 요약: 변경 사유
    lastCounts = Object.fromEntries(CATS.map((c) => [c, cats[c] || 0]));
    $('share-scope').textContent = `${n0(list.length)}건`;
    $('f-share').querySelector('.twin')!.replaceChildren(
      twinTable(
        '변경 사유 범주별 항목 수',
        [{ label: '범주' }, { label: '항목', num: true }, { label: '비율', num: true }],
        CATS.map((c) => [M.cats[c], `${n0(cats[c] || 0)}건`, list.length ? `${(((cats[c] || 0) / list.length) * 100).toFixed(1)}%` : '']),
      ),
    );
    // 요약: 묶음별 항목 수
    lastGroups = groupsOf(list);
    $('group-title').textContent = TITLES[state.group];
    $('f-group').querySelector('.seg-view')?.setAttribute('aria-label', `${TITLES[state.group]} 보기 방식`);
    $('group-scope').textContent = `${n0(list.length)}건 · ${state.group === 'event' ? '시간 순, 문서가 있는 대회' : '많은 순'}`;
    $('group-twin').replaceChildren(
      twinTable(
        TITLES[state.group],
        [{ label: HEAD[state.group] }, { label: '합계', num: true }, ...CATS.map((c) => ({ label: M.cats[c], num: true }))],
        lastGroups.map((g) => [g.label, g.total, ...CATS.map((c) => g.cats[c] || 0)]),
      ),
    );
    drawCharts();

    // 목록: 대회 묶음마다 맞는 항목을 세고, 앞에서부터 state.shown건까지만 보인다.
    const hit = new Set(list);
    const itemFilter = anyItemFilter();
    let remaining = state.shown;
    let firstHidden: Row | null = null;
    for (const g of groups) {
      const here = g.rows.filter((r) => hit.has(r));
      const startRemaining = remaining;
      let shownHere = 0;
      for (const r of g.rows) {
        const show = hit.has(r) && remaining > 0;
        r.el.hidden = !show;
        if (show) {
          remaining -= 1;
          shownHere += 1;
        } else if (hit.has(r) && !firstHidden) firstHidden = r;
      }
      // 항목 0건 문서는 항목 조건이 없고 시즌과 대회 범위에 들 때만, 앞에서 20건이 다 차지 않았으면 보인다.
      const zeroDoc = g.rows.length === 0 && !itemFilter && inScope(g.s, g.key) && startRemaining > 0;
      g.el.hidden = !(shownHere > 0 || zeroDoc);
      if (g.count) g.count.textContent = String(here.length);
    }
    $('items-meta').textContent = `${n0(list.length)}건`;
    const empty = list.length === 0 && !groups.some((g) => !g.el.hidden);
    $('ex-empty').hidden = !empty;
    if (empty) $('ex-empty-why').textContent = emptyWhy();
    const shown = Math.min(state.shown, list.length);
    $('more-line').hidden = list.length === 0;
    $('more-text').textContent =
      shown >= list.length ? `${n0(list.length)}건을 모두 보고 있다.` : `${n0(list.length)}건 가운데 ${n0(shown)}건을 보고 있다.`;
    const more = $<HTMLButtonElement>('more');
    more.hidden = shown >= list.length;
    more.textContent = `${n0(Math.min(PAGE, list.length - shown))}건 더 보기`;
  }

  function sync() {
    state.shown = PAGE;
    $<HTMLSelectElement>('f-season').value = state.season;
    eventOptions();
    $<HTMLSelectElement>('f-team').value = state.team;
    $<HTMLSelectElement>('f-area').value = state.area;
    $<HTMLInputElement>('f-q').value = state.q;
    toHash();
    render();
  }
  function reset() {
    Object.assign(state, { season: '', event: '', team: '', area: '', q: '', cats: new Set(CATS) });
    sync();
  }

  // ---------------------------------------------------------------- 조작

  // 정적 숨김(.ex-x)을 거두고 hidden으로 넘겨받는다
  document.querySelectorAll('#item-list .ex-x').forEach((n) => n.classList.remove('ex-x'));

  $('filters').addEventListener('submit', (e) => e.preventDefault());
  $<HTMLSelectElement>('f-season').addEventListener('change', (e) => {
    state.season = (e.target as HTMLSelectElement).value;
    sync();
  });
  evSel.addEventListener('change', () => {
    state.event = evSel.value;
    sync();
  });
  $<HTMLSelectElement>('f-team').addEventListener('change', (e) => {
    state.team = (e.target as HTMLSelectElement).value;
    sync();
  });
  $<HTMLSelectElement>('f-area').addEventListener('change', (e) => {
    state.area = (e.target as HTMLSelectElement).value;
    sync();
  });
  let timer: ReturnType<typeof setTimeout> | undefined;
  $<HTMLInputElement>('f-q').addEventListener('input', (e) => {
    clearTimeout(timer);
    const v = (e.target as HTMLInputElement).value;
    timer = setTimeout(() => {
      state.q = v;
      state.shown = PAGE;
      toHash();
      render();
    }, 180);
  });
  document.querySelectorAll<HTMLInputElement>('#f-cats input').forEach((inp) =>
    inp.addEventListener('change', () => {
      if (inp.checked) state.cats.add(inp.value as Cat);
      else state.cats.delete(inp.value as Cat);
      state.shown = PAGE;
      toHash();
      render();
    }),
  );
  $('f-reset').addEventListener('click', reset);
  // 빈 상태의 단추는 목록과 함께 사라지므로 초점을 결과 줄로 옮긴다
  $('ex-empty-reset').addEventListener('click', () => {
    reset();
    $('result').focus();
  });
  $('more').addEventListener('click', () => {
    const before = rows.filter((r) => !r.el.hidden).length;
    state.shown += PAGE;
    render();
    // 새로 보인 첫 항목으로 초점을 옮긴다(단추가 사라져도 초점이 body로 떨어지지 않는다)
    const next = rows.filter((r) => !r.el.hidden)[before];
    if (next) {
      next.el.tabIndex = -1;
      next.el.focus();
    }
  });
  document.querySelectorAll<HTMLButtonElement>('[data-group]').forEach((b) =>
    b.addEventListener('click', () => {
      state.group = b.dataset.group as GroupBy;
      document.querySelectorAll('[data-group]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      render();
    }),
  );
  // 다른 탐색기 링크로 주소 조각만 바뀌었을 때. "본문으로 건너뛰기"(#main) 같은 쪽 안 이동은 조건이 아니라 건너뛴다.
  window.addEventListener('hashchange', () => {
    const raw = location.hash.slice(1);
    if (raw && !raw.includes('=')) return;
    fromHash();
    sync();
  });

  fromHash();
  sync();

  // 그림은 차트 모듈이 있을 때만 그린다. 모듈을 못 불러오면 레이아웃의 chartFallback이 표 보기를 되살린다.
  import('../../lib/charts/mount.ts')
    .then(async (m) => {
      await m.ready;
      share = m.mount($('f-share').querySelector('.viz') as HTMLElement, m.REGISTRY.reasonShare, lastCounts, { label: '변경 사유 비율' }) as ChartHandle;
      grouped = m.mount($('f-group').querySelector('.viz') as HTMLElement, m.groupedReasons, lastGroups, {
        orient: state.group === 'event' ? 'v' : 'h',
        label: TITLES[state.group],
        onSelect: (g: { key: string; season?: number }) => {
          if (state.group === 'team') state.team = g.key;
          else if (state.group === 'area') state.area = g.key;
          else {
            state.event = g.key;
            state.season = String(g.season ?? '');
          }
          sync();
        },
      }) as ChartHandle;
    })
    .catch((err) => window.chartFallback?.(err));
}
