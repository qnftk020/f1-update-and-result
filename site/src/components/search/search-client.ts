// 머리 띠 전역 검색 칸의 동작(DESIGN.md "전역 검색").
// 처음 초점(또는 처음 입력) 때 색인(/data/search.json)을 한 번 받는다. 결과는 종류별 묶음의 링크 목록이다.
// 키보드: "/" 로 칸에 초점, 위아래 화살표로 고르기, Enter로 이동, Esc로 닫기(한 번 더 누르면 글을 지운다).
// 접근성: 입력은 combobox, 목록은 listbox, 고른 항목은 aria-activedescendant로 알린다. 결과 수는 숨은 상태 줄이 읽는다.
import { KIND_LABEL, type SearchEntry, groupResults, searchEntries } from '../../lib/search.ts';

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);

export function initSearch(): void {
  const input = document.getElementById('gs-q') as HTMLInputElement | null;
  const list = document.getElementById('gs-list');
  const status = document.getElementById('gs-status');
  if (!input || !list || !status) return;
  const box = input.closest('.search-box') as HTMLElement;
  let index: SearchEntry[] | null = null;
  let loading: Promise<void> | null = null;
  let options: HTMLAnchorElement[] = [];
  let active = -1;
  let timer = 0;

  const load = () => {
    if (index || loading) return loading;
    loading = fetch(input.dataset.index as string)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: SearchEntry[]) => {
        index = data;
      })
      .catch(() => {
        index = [];
        status.textContent = '검색 색인을 불러오지 못했다.';
      });
    return loading;
  };

  const close = () => {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  };

  const select = (i: number) => {
    options.forEach((o, j) => o.setAttribute('aria-selected', String(j === i)));
    active = i;
    if (i >= 0 && options[i]) {
      input.setAttribute('aria-activedescendant', options[i].id);
      options[i].scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  };

  const render = () => {
    const q = input.value.trim();
    box.classList.toggle('has-q', Boolean(q));
    if (!q || !index) {
      close();
      return;
    }
    const groups = groupResults(searchEntries(index, q));
    const total = groups.reduce((n, g) => n + g.items.length + g.more, 0);
    let k = 0;
    list.innerHTML = groups.length
      ? groups
          .map(
            (g) =>
              `<div class="search-group" role="group" aria-label="${KIND_LABEL[g.kind]}"><h3>${KIND_LABEL[g.kind]}${g.more ? ` · 외 ${g.more}개` : ''}</h3>` +
              g.items
                .map(
                  (e) =>
                    `<a class="search-opt" role="option" id="gs-o${k++}" href="${esc(e.u)}" aria-selected="false"><span>${esc(e.n)}</span>${e.m ? `<span class="meta">${esc(e.m)}</span>` : ''}</a>`,
                )
                .join('') +
              '</div>',
          )
          .join('')
      : `<p class="search-empty">"${esc(q)}" 검색 결과는 0건이다.</p>`;
    options = [...list.querySelectorAll<HTMLAnchorElement>('.search-opt')];
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    select(options.length ? 0 : -1);
    status.textContent = `결과 ${total}개`;
  };

  input.addEventListener('focus', () => {
    load();
    if (input.value.trim() && index) render();
  });
  input.addEventListener('input', () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      await load();
      render();
    }, 60);
  });
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown' && options.length) {
      ev.preventDefault();
      select((active + 1) % options.length);
    } else if (ev.key === 'ArrowUp' && options.length) {
      ev.preventDefault();
      select((active - 1 + options.length) % options.length);
    } else if (ev.key === 'Enter') {
      if (active >= 0 && options[active]) {
        ev.preventDefault();
        window.location.href = options[active].href;
      }
    } else if (ev.key === 'Escape') {
      if (!list.hidden) close();
      else {
        input.value = '';
        box.classList.remove('has-q');
      }
    }
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== '/' || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const t = ev.target as HTMLElement;
    if (t.closest('input, textarea, select, [contenteditable="true"]')) return;
    ev.preventDefault();
    input.focus();
  });
  document.addEventListener('click', (ev) => {
    if (!box.contains(ev.target as Node)) close();
  });
}
