// 모든 페이지의 공통 스크립트(BaseLayout이 번들로 싣는다). 차트 모듈이 없어도 동작한다.
// 테마 세 칸 전환(자동, 밝게, 어둡게), 좁은 화면 메뉴, 긴 설명 펼치기, 차트 전체 실패 대체.
// 저장된 테마를 첫 칠 전에 붙이는 일은 BaseLayout <head>의 인라인 스크립트가 맡는다.

declare global {
  interface Window {
    chartFallback: (err: unknown) => void;
  }
}

export function boot(): void {
  const d = document.documentElement;
  const btns = document.querySelectorAll<HTMLButtonElement>('[data-theme-set]');
  const current = () => d.dataset.theme || 'auto';
  const paint = () =>
    btns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.themeSet === current())));
  btns.forEach((b) =>
    b.addEventListener('click', () => {
      const t = b.dataset.themeSet || 'auto';
      if (t === 'auto') delete d.dataset.theme;
      else d.dataset.theme = t;
      try {
        localStorage.setItem('theme', t);
      } catch {
        /* 저장이 막혀도 이번 화면에서는 바뀐다 */
      }
      paint();
    }),
  );
  paint();

  const menuBtn = document.querySelector<HTMLButtonElement>('.menu-btn');
  const menu = document.getElementById('site-menu');
  if (menuBtn && menu) {
    menuBtn.addEventListener('click', () => {
      const open = menuBtn.getAttribute('aria-expanded') !== 'true';
      menuBtn.setAttribute('aria-expanded', String(open));
      menu.classList.toggle('is-open', open);
    });
  }

  // 정적으로 실은 업그레이드 항목의 "전체 보기" 단추(UpgradeItem.astro)
  document.addEventListener('click', (e) => {
    const b = (e.target as Element | null)?.closest<HTMLButtonElement>('[data-clamp-toggle]');
    const box = b?.closest('.item-text');
    if (!b || !box) return;
    const open = !box.classList.contains('open');
    box.classList.toggle('open', open);
    b.textContent = open ? '줄여 보기' : '전체 보기';
    b.setAttribute('aria-expanded', String(open));
  });

  // 차트 모듈(Observable Plot)을 불러오지 못하거나 페이지 스크립트가 멈추면 차트 자리에 안내를 적고
  // 숨겨 둔 표 보기를 모두 다시 보인다(전환 단추와 범례는 .no-plot이 숨긴다).
  // 그림 하나의 오류는 차트 모듈의 mount()가 그 그림만 따로 처리한다.
  window.chartFallback = (err: unknown) => {
    d.classList.add('no-plot');
    document.querySelectorAll<HTMLElement>('figure.fig .viz').forEach((v) => {
      v.textContent = '';
      v.hidden = false;
      const p = document.createElement('p');
      p.className = 'fig-fallback';
      p.textContent = '차트를 불러오지 못해 표로 보여 준다.';
      v.appendChild(p);
    });
    document.querySelectorAll<HTMLElement>('figure.fig .twin').forEach((t) => {
      t.hidden = false;
    });
    console.warn(err);
  };
}
