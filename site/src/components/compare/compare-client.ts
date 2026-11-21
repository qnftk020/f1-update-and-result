// 드라이버·컨스트럭터 목록 쪽 비교 절(ComparePanel.astro)의 브라우저 동작: 목록 표의 체크 칸으로 고르기, 고른 목록(칩),
// 통산 기록 표, 시즌별 두 그림과 표 보기, 결승 맞대결. 고른 조합은 주소(?cmp=senna,prost)에 남는다.
// 계열 색과 표식은 고른 순서가 아니라 대상에 붙는다: 하나를 빼도 남은 대상의 색은 그대로다(빈 자리를 다음에 고른 대상이 쓴다).
// 데이터에서 온 글자는 esc()를 거친 뒤에만 HTML 문자열에 넣는다.
import { MAX_PICK, headToHead, parseIds, seasonPoints, shortNames, type CompareFile, type Kind } from '../../lib/compare.ts';
import { n0, num } from '../../lib/format.ts';
import { routes } from '../../lib/paths.ts';
import { en, esc } from '../../lib/typeset.ts';
import { span, yearsText } from '../driver/model.ts';

interface ChartHandle {
  redraw: (data?: unknown, opts?: Record<string, unknown>) => void;
}
type Mode = 'year' | 'career';

/** 계열 모양(lib/charts/compare.js SERIES와 같은 순서): 범례 열쇠 종류와 색 토큰 */
const KEYS = [
  { key: 'dot', color: 'var(--s1)' },
  { key: 'sq', color: 'var(--s2)' },
  { key: 'tri-c', color: 'var(--s3)' },
];
// 두 이름 모두 모음으로 끝나 조사는 '가', '를'이다
const NOUN: Record<Kind, { pick: string; unit: string }> = { d: { pick: '드라이버', unit: '명' }, c: { pick: '컨스트럭터', unit: '곳' } };

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T | null;
const keyHtml = (slot: number) => `<span class="key key-${KEYS[slot].key}" style="--k: ${KEYS[slot].color}" aria-hidden="true"></span>`;
const pctOf = (a: number, n: number) => (n ? (a / n) * 100 : null);

export function start(): void {
  const root = $('cmp');
  if (!root) return;
  const kind = (root.dataset.kind === 'c' ? 'c' : 'd') as Kind;
  const def = (root.dataset.def ?? '').split(',').filter(Boolean);
  // 목록 표: 행마다 data-id와 체크 칸(input.cmp-box). 이름은 행의 첫 링크 글자다.
  const tbody = document.querySelector<HTMLTableSectionElement>('[data-cmp-table] tbody');
  const rows = tbody ? [...tbody.querySelectorAll<HTMLTableRowElement>('tr[data-id]')] : [];
  const rowById = new Map(rows.map((r) => [r.dataset.id ?? '', r]));
  const boxById = new Map(rows.map((r) => [r.dataset.id ?? '', r.querySelector<HTMLInputElement>('input.cmp-box')]));
  const nameById = new Map(rows.map((r) => [r.dataset.id ?? '', r.querySelector('a')?.textContent?.trim() ?? r.dataset.id ?? '']));
  const known = new Set(rowById.keys());

  const state = {
    picks: [] as string[],
    slots: new Map<string, number>(),
    touched: false,
    mode: 'year' as Mode,
  };

  const chips = $('cmp-chips');
  const count = $('cmp-count');
  const line = $('cmp-line');
  const toList = $('cmp-to-list');
  const totals = $('cmp-totals');
  const totalsNote = $('cmp-totals-note');
  const h2h = $('cmp-h2h');
  const figPos = $('f-cmp-pos');
  const figWins = $('f-cmp-wins');

  /* ---------------------------------------------------------------- 상태 */

  const assignSlots = () => {
    const slots = state.slots;
    for (const id of [...slots.keys()]) if (!state.picks.includes(id)) slots.delete(id);
    for (const id of state.picks) {
      if (slots.has(id)) continue;
      const used = new Set(slots.values());
      let s = 0;
      while (used.has(s)) s += 1;
      slots.set(id, s);
    }
  };

  // 주소: ?cmp=a,b. 사람이 고르기 전(처음 비교)에는 주소를 바꾸지 않는다. 쪽 안 링크(#list 등)는 그대로 둔다.
  const fromUrl = (): string[] | null => parseIds(new URLSearchParams(location.search).get('cmp'), known);
  const writeUrl = () => {
    if (!state.touched) return;
    const next = `${location.pathname}?cmp=${state.picks.join(',')}${location.hash}`;
    if (`${location.pathname}${location.search}${location.hash}` !== next) history.replaceState(null, '', next);
  };

  /* ---------------------------------------------------------------- 자료 */

  const cache = new Map<string, Promise<CompareFile>>();
  const load = (kind: Kind, id: string): Promise<CompareFile> => {
    const k = `${kind}/${id}`;
    let p = cache.get(k);
    if (!p) {
      p = fetch(routes.compareData(kind, id)).then((r) => {
        if (!r.ok) throw new Error(`비교 자료를 받지 못했다: ${k} (${r.status})`);
        return r.json() as Promise<CompareFile>;
      });
      p.catch(() => cache.delete(k));
      cache.set(k, p);
    }
    return p;
  };

  /* ---------------------------------------------------------------- 고르기 */

  const syncBoxes = () => {
    const full = state.picks.length >= MAX_PICK;
    for (const [id, box] of boxById) {
      if (!box) continue;
      const on = state.picks.includes(id);
      box.checked = on;
      box.disabled = !on && full;
      rowById.get(id)?.classList.toggle('cmp-on', on);
    }
  };

  const renderChips = () => {
    const ids = state.picks;
    const N = NOUN[kind];
    if (count) count.textContent = `${ids.length}/${MAX_PICK}`;
    if (chips) {
      chips.innerHTML = ids.length
        ? ids
            .map((id) => {
              const name = nameById.get(id) ?? id;
              const href = kind === 'd' ? routes.driver(id) : routes.constructorPage(id);
              return `<li>${keyHtml(state.slots.get(id) ?? 0)}<a href="${href}" lang="en">${esc(name)}</a><button type="button" data-remove="${esc(id)}" aria-label="${esc(name)} 빼기">×</button></li>`;
            })
            .join('')
        : `<li class="empty-chip">아직 고른 ${N.pick}가 없다</li>`;
    }
    if (line) {
      const names = ids.map((id) => nameById.get(id) ?? id).join(', ');
      line.textContent = !ids.length
        ? `비교에 고른 ${N.pick}가 없다. 첫 칸을 체크하면 위 비교에 들어간다.`
        : ids.length >= MAX_PICK
          ? `비교에 고른 ${N.pick} ${ids.length}/${MAX_PICK}: ${names}. 최대 ${MAX_PICK}${N.unit}까지다. 하나를 빼면 다른 ${N.pick}를 고를 수 있다.`
          : `비교에 고른 ${N.pick} ${ids.length}/${MAX_PICK}: ${names}.`;
    }
  };

  const toggle = (id: string, on: boolean) => {
    const ids = state.picks;
    if (on && !ids.includes(id) && ids.length < MAX_PICK) ids.push(id);
    if (!on) state.picks = ids.filter((x) => x !== id);
    state.touched = true;
    void update();
  };

  /* ---------------------------------------------------------------- 통산 기록 */

  type Better = 'max' | 'min' | null;
  type Metric = [string, (f: CompareFile) => number | null, (v: number | null, f: CompareFile) => string, Better];
  const plain = (unit: string) => (v: number | null) => (v == null ? '결측' : `${n0(v)}${unit}`);
  const pctText = (v: number | null) => (v == null ? '결측' : `${num(v, 1)}%`);
  const bestText = (v: number | null, f: CompareFile) => (v == null ? '순위 없음' : `${v}위 <span class="sub-line">${f.t.best_n}번</span>`);
  const T = (k: string) => (f: CompareFile) => (f.t[k] as number | null) ?? null;

  const METRICS: Record<Kind, Metric[]> = {
    d: [
      ['시즌', T('seasons'), plain(''), 'max'],
      ['출전', T('entries'), plain('회'), 'max'],
      ['출발', T('starts'), plain('회'), 'max'],
      ['우승', T('wins'), plain('번'), 'max'],
      ['포디움', T('podiums'), plain('번'), 'max'],
      ['폴', T('poles'), plain('번'), 'max'],
      ['드라이버 타이틀', T('titles'), plain('번'), 'max'],
      ['최고 순위', T('best'), bestText, 'min'],
      ['출발 대비 우승', (f) => pctOf(f.t.wins ?? 0, f.t.starts ?? 0), pctText, 'max'],
      ['출발 대비 포디움', (f) => pctOf(f.t.podiums ?? 0, f.t.starts ?? 0), pctText, 'max'],
    ],
    c: [
      ['시즌', T('seasons'), plain(''), 'max'],
      ['출전 대회', T('entries'), plain('회'), 'max'],
      ['출전 차량', T('cars'), plain('대'), 'max'],
      ['우승', T('wins'), plain('번'), 'max'],
      ['포디움', T('podiums'), plain('번'), 'max'],
      ['1-2 피니시', T('one_two'), plain('번'), 'max'],
      ['컨스트럭터 타이틀', T('titles'), plain('번'), 'max'],
      ['드라이버 타이틀', T('driver_titles'), plain('번'), 'max'],
      ['최고 순위', T('best'), bestText, 'min'],
      ['거쳐 간 드라이버', T('drivers_n'), plain('명'), 'max'],
      ['출전 대비 우승', (f) => pctOf(f.t.wins ?? 0, f.t.entries ?? 0), pctText, 'max'],
    ],
  };
  const NOTE: Record<Kind, string> = {
    d: '출전은 결승 결과가 있는 대회 수, 출발은 그 가운데 출발하지 않은 대회를 뺀 수다. 우승, 포디움, 타이틀에는 1950-1960년 챔피언십에 들어 있던 인디애나폴리스 500이 포함된다. 최고 순위 아래 숫자는 그 순위를 한 시즌 수다. 통산 점수는 점수 체계가 시대마다 달라 싣지 않는다.',
    c: '목록은 Jolpica 컨스트럭터 ID 단위다(이름이 바뀌어 이어진 조직의 흐름은 팀 계보 쪽에 있다). 출전 대회는 결승 결과가 있는 대회 수, 출전 차량은 결과 행 수, 포디움은 3위 이내로 분류된 차의 수다. 컨스트럭터 챔피언십은 1958년부터다. 1950-1960년대에는 섀시와 엔진 조합이 따로 ID를 가진다(Cooper-Climax 등). 통산 점수는 점수 체계가 시대마다 달라 싣지 않는다.',
  };

  const emptyHtml = (text: string) => `<p class="empty-line">${text}</p>`;

  const renderTotals = (files: CompareFile[], kind: Kind) => {
    if (!totals) return;
    if (totalsNote) totalsNote.textContent = NOTE[kind];
    if (!files.length) {
      totals.innerHTML = emptyHtml(`비교할 ${NOUN[kind].pick}를 고르면 통산 기록이 나온다.`);
      return;
    }
    const slot = (f: CompareFile) => state.slots.get(f.id) ?? 0;
    const href = (f: CompareFile) => (kind === 'd' ? routes.driver(f.id) : routes.constructorPage(f.id));
    const head = files.map((f) => `<th scope="col">${keyHtml(slot(f))}<a href="${href(f)}" lang="en">${esc(f.name)}</a></th>`).join('');
    const info = [
      `<tr><th scope="row" class="stick">국적</th>${files.map((f) => `<td>${esc(f.nat ?? '결측')}</td>`).join('')}</tr>`,
      `<tr><th scope="row" class="stick">활동 기간</th>${files.map((f) => `<td>${span(f.first, f.last)}</td>`).join('')}</tr>`,
    ];
    const body = METRICS[kind].map(([label, get, fmt, better]) => {
      const vals = files.map(get);
      let lead: number | null = null;
      const nums = vals.filter((v): v is number => v != null);
      if (files.length > 1 && better && nums.length > 1 && new Set(nums.map((v) => Math.round(v * 1000))).size > 1) {
        lead = better === 'max' ? Math.max(...nums) : Math.min(...nums);
        if (better === 'max' && lead <= 0) lead = null;
      }
      const tds = files
        .map((f, i) => {
          const v = vals[i];
          const top = lead != null && v != null && Math.abs(v - lead) < 1e-9;
          return `<td class="num${top ? ' lead-v' : ''}">${fmt(v, f)}</td>`;
        })
        .join('');
      return `<tr><th scope="row" class="stick">${label}</th>${tds}</tr>`;
    });
    totals.innerHTML =
      `<div class="tbl-wrap" role="region" tabindex="0" aria-label="통산 기록 비교"><table class="dt">` +
      `<caption class="sr-only">고른 ${NOUN[kind].pick}의 통산 기록</caption>` +
      `<thead><tr><th scope="col" class="stick">항목</th>${head}</tr></thead><tbody>${[...info, ...body].join('')}</tbody></table></div>`;
  };

  /* ---------------------------------------------------------------- 시즌별 그림 */

  let chartMod: { mod: any; charts: any } | null = null;
  let handles: { pos: ChartHandle; wins: ChartHandle } | null = null;
  let lastFiles: CompareFile[] = [];
  let lastKind: Kind = 'd';

  const chartInput = (files: CompareFile[], kind: Kind, short: string[]) => ({
    kind,
    mode: state.mode,
    series: files.map((f, i) => ({ name: f.name, short: short[i], slot: state.slots.get(f.id) ?? 0, pts: seasonPoints(f, state.mode) })),
  });

  const renderLegend = (fig: HTMLElement | null, files: CompareFile[], kind: Kind) => {
    if (!fig || !chartMod) return;
    fig.querySelector('.legend.cmp-legend')?.remove();
    if (!files.length) return;
    const ul = chartMod.mod.legend(
      files.map((f) => {
        const k = KEYS[state.slots.get(f.id) ?? 0];
        return { type: k.key, color: k.color, label: f.name };
      }),
    ) as HTMLElement;
    ul.classList.add('cmp-legend');
    ul.querySelectorAll('li > span:last-child').forEach((s) => s.setAttribute('lang', 'en'));
    fig.querySelector('.fig-body')?.before(ul);
  };

  const renderTwins = (input: ReturnType<typeof chartInput>) => {
    if (!chartMod) return;
    const xs = [...new Set(input.series.flatMap((s) => s.pts.map((p) => p.x)))].sort((a, b) => a - b);
    const xLabel = state.mode === 'year' ? '시즌' : '데뷔 뒤 햇수';
    const xFmt = (x: number) => (state.mode === 'year' ? String(x) : `${x}년차`);
    const rows = xs.map((x) => {
      const r: Record<string, string> = { x: xFmt(x) };
      input.series.forEach((s, i) => {
        const p = s.pts.find((q) => q.x === x);
        if (!p) {
          r[`p${i}`] = '';
          r[`w${i}`] = '';
          return;
        }
        const when = state.mode === 'career' ? ` (${p.s})` : '';
        const pos = input.kind === 'c' && p.s < 1958 ? '순위 없음' : p.pos ? `${p.pos}위` : p.ex ? '제외' : '미부여';
        r[`p${i}`] = `${pos}${p.champ ? ', 챔피언' : ''}${when}`;
        r[`w${i}`] = `${p.cum} (그 시즌 ${p.wins})${when}`;
      });
      return r;
    });
    const cols = (prefix: string) => [{ key: 'x', label: xLabel }, ...input.series.map((s, i) => ({ key: `${prefix}${i}`, label: s.short }))];
    const posTwin = figPos?.querySelector('.twin');
    const winTwin = figWins?.querySelector('.twin');
    posTwin?.replaceChildren(chartMod.mod.tableTwin({ caption: '시즌 최종 순위 비교', columns: cols('p'), rows }));
    winTwin?.replaceChildren(chartMod.mod.tableTwin({ caption: '누적 결승 우승 비교 (괄호 안은 그 시즌 우승)', columns: cols('w'), rows }));
  };

  const renderCharts = async (files: CompareFile[], kind: Kind) => {
    lastFiles = files;
    lastKind = kind;
    try {
      if (!chartMod) {
        const mod = await import('../../lib/charts/mount.ts');
        await mod.ready;
        const charts = await import('../../lib/charts/compare.js');
        chartMod = { mod, charts };
      }
      if (files !== lastFiles) return;
      const short = shortNames(files.map((f) => f.name), kind);
      const input = chartInput(files, kind, short);
      if (!handles) {
        const vp = figPos?.querySelector<HTMLElement>('.viz');
        const vw = figWins?.querySelector<HTMLElement>('.viz');
        if (!vp || !vw) return;
        handles = {
          pos: chartMod.mod.mount(vp, chartMod.charts.compareSeasons, input, { metric: 'pos', label: '시즌 최종 순위' }),
          wins: chartMod.mod.mount(vw, chartMod.charts.compareSeasons, input, { metric: 'cum', label: '누적 결승 우승' }),
        };
      } else {
        handles.pos.redraw(input);
        handles.wins.redraw(input);
      }
      renderLegend(figPos, files, kind);
      renderLegend(figWins, files, kind);
      renderTwins(input);
    } catch (err) {
      if (window.console) console.warn(err);
    }
  };

  /* ---------------------------------------------------------------- 맞대결 */

  const renderH2h = (files: CompareFile[], kind: Kind, short: string[]) => {
    if (!h2h) return;
    if (files.length < 2) {
      h2h.innerHTML = emptyHtml(`맞대결은 ${NOUN[kind].pick}를 둘 이상 고르면 나온다.`);
      return;
    }
    const slotOf = (i: number) => state.slots.get(files[i].id) ?? 0;
    const tag = (i: number) => `<span class="nw">${keyHtml(slotOf(i))}<span lang="en">${esc(short[i])}</span></span>`;
    // 점수 줄: "● Senna 62 : 68 ■ Prost"와 두 몫 막대(앞선 비율, 그림은 글을 되풀이할 뿐이라 낭독에서 뺀다)
    const score = (i: number, a: number, j: number, b: number) => {
      const t = a + b;
      const bar = t
        ? `<span class="h2h-bar" aria-hidden="true"><span style="width:${((a / t) * 100).toFixed(2)}%;background:${KEYS[slotOf(i)].color}"></span><span style="width:${((b / t) * 100).toFixed(2)}%;background:${KEYS[slotOf(j)].color}"></span></span>`
        : '';
      return `<span class="h2h-score"><span class="nw">${tag(i)} <b>${a}</b></span> : <span class="nw"><b>${b}</b> ${tag(j)}</span></span>${bar}`;
    };
    const cards: string[] = [];
    for (let i = 0; i < files.length; i++) {
      for (let j = i + 1; j < files.length; j++) {
        const a = files[i];
        const b = files[j];
        const h = headToHead(a.r, b.r);
        const race = !h.both
          ? '<p class="h2h-none">함께 나선 결승이 없다.</p>'
          : `${h.counted ? score(i, h.a, j, h.b) : ''}<p class="h2h-sub">함께 나선 결승 ${n0(h.both)}번(<span class="nw">${span(h.first ?? 0, h.last ?? 0)}</span>), 앞뒤를 가린 대회 ${n0(h.counted)}번</p>`;
        let mate = '';
        if (kind === 'd') {
          const m = a.m?.find((x) => x[0] === b.id);
          mate = m
            ? `<div class="h2h-part"><p class="h2h-head">팀 동료였던 시즌 <span class="nw">${yearsText(m[7])}</span> <span lang="en">${esc(m[8])}</span></p>` +
              `<p class="h2h-sub">결승</p>${m[3] ? score(i, m[4], j, m[3] - m[4]) : ''}<p class="h2h-sub">앞뒤를 가린 대회 ${n0(m[3])}번</p>` +
              (m[5]
                ? `<p class="h2h-sub">예선</p>${score(i, m[6], j, m[5] - m[6])}<p class="h2h-sub">비교한 대회 ${n0(m[5])}번</p>`
                : '<p class="h2h-sub">예선: 이 시기 예선 기록이 없다(1994년부터).</p>') +
              '</div>'
            : '<div class="h2h-part"><p class="h2h-sub">팀 동료였던 적이 없다.</p></div>';
        }
        cards.push(
          `<article class="h2h-pair"><h3 class="h2h-title">${tag(i)} · ${tag(j)}</h3>` +
            `<div class="h2h-part"><p class="h2h-head">같은 대회 결승</p>${race}</div>${mate}</article>`,
        );
      }
    }
    h2h.innerHTML = `<div class="h2h-grid">${cards.join('')}</div>`;
  };

  /* ---------------------------------------------------------------- 갱신 */

  let ticket = 0;
  const update = async () => {
    assignSlots();
    writeUrl();
    syncBoxes();
    renderChips();
    const my = ++ticket;
    let files: CompareFile[];
    try {
      files = await Promise.all(state.picks.map((id) => load(kind, id)));
    } catch (err) {
      if (window.console) console.warn(err);
      if (line) line.textContent = '자료를 받지 못했다. 잠시 뒤 다시 고르거나 쪽을 새로 불러온다.';
      return;
    }
    if (my !== ticket) return;
    renderTotals(files, kind);
    renderH2h(files, kind, shortNames(files.map((f) => f.name), kind));
    void renderCharts(files, kind);
  };

  /* ---------------------------------------------------------------- 연결 */

  tbody?.addEventListener('change', (e) => {
    const t = e.target as HTMLInputElement;
    if (t?.classList.contains('cmp-box')) toggle(t.value, t.checked);
  });
  chips?.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-remove]');
    if (!btn) return;
    const id = btn.dataset.remove ?? '';
    const at = state.picks.indexOf(id);
    toggle(id, false);
    // 뺀 칩 자리에 있던 다음 칩의 빼기 단추로, 없으면 목록으로 가는 링크로 초점을 옮긴다
    const next = chips.querySelectorAll<HTMLButtonElement>('[data-remove]')[Math.min(at, state.picks.length - 1)];
    (next ?? toList)?.focus();
  });
  document.querySelectorAll<HTMLButtonElement>('#cmp-mode [data-mode]').forEach((b) =>
    b.addEventListener('click', () => {
      const m = b.dataset.mode as Mode;
      if (m === state.mode) return;
      state.mode = m;
      document.querySelectorAll<HTMLButtonElement>('#cmp-mode [data-mode]').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.mode === m)));
      void renderCharts(lastFiles, lastKind);
    }),
  );

  const fromAddress = fromUrl();
  state.picks = fromAddress ?? def.filter((id) => known.has(id));
  state.touched = fromAddress != null;
  void update();
}
