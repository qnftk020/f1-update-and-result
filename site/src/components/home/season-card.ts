// 홈 "연도별" 시즌 요약 칸. 빌드 때(정적 기본값, 최신 시즌)와 브라우저(시즌 고르기)가 같은 함수로 그린다.
// 자료는 home-data.ts의 seasonCards 한 행이다(history.json에서 온다). 이름은 모두 esc()를 거친다.
import { formatPoints, n0 } from '../../lib/format.ts';
import { routes } from '../../lib/paths.ts';
import { esc } from '../../lib/typeset.ts';

export interface CardRow {
  s: number;
  r: number;
  w: number;
  lc: number | null;
  d1: { id: string; n: string; p: number; w: number; t: string[]; f: number | null };
  d2: { id: string; n: string; p: number };
  m: number;
  mp: number;
  c1: { n: string; l: string | null; p: number; w: number; f: number | null } | null;
  c2: { n: string; p: number } | null;
  cm: number | null;
  cmp: number | null;
  ex: { n: string; p: number }[];
  ca: { n: string; k: 'excluded' | 'deducted'; p: number; pos: number | null }[];
}

const pts = (v: number) => `${formatPoints(v)}점`;
const pc = (v: number | null) => (v == null ? '결측' : `${formatPoints(v)}%`);
const en = (s: string) => `<span lang="en">${esc(s)}</span>`;
const nwe = (s: string) => `<span class="nw" lang="en">${esc(s)}</span>`;

export function seasonCardHtml(c: CardRow, constructorFirst: number): string {
  const lead =
    c.lc == null ? '' : c.lc === 1 ? ' · 드라이버 선두 교체 없음(1라운드부터)' : ` · 드라이버 선두가 마지막으로 바뀐 라운드 <b>${c.lc}</b>`;
  const head =
    `<div class="hm-card-head"><p class="hm-year"><b>${c.s}</b> 시즌</p>` +
    `<p class="hm-card-meta">대회 <b>${n0(c.r)}</b>개 · 서로 다른 우승자 <b>${n0(c.w)}</b>명${lead}</p></div>`;

  const driver =
    `<div class="hm-champ">` +
    `<p class="hm-lab">드라이버 1위</p>` +
    `<p class="hm-name"><a href="${routes.driver(c.d1.id)}" lang="en">${esc(c.d1.n)}</a></p>` +
    `<p class="hm-team">${c.d1.t.map(en).join(', ')} · 우승 ${n0(c.d1.w)}회</p>` +
    `<p class="hm-big">${formatPoints(c.d1.p)}<span>점</span></p>` +
    `<p class="hm-vs">2위 <a href="${routes.driver(c.d2.id)}">${nwe(c.d2.n)}</a> ${pts(c.d2.p)}<br>차이 <b>${pts(c.m)}</b>, 1위 점수의 ${pc(c.mp)}</p>` +
    `</div>`;

  const team = c.c1
    ? `<div class="hm-champ">` +
      `<p class="hm-lab">컨스트럭터 1위</p>` +
      `<p class="hm-name">${c.c1.l ? `<a href="${routes.team(c.c1.l)}" lang="en">${esc(c.c1.n)}</a>` : en(c.c1.n)}</p>` +
      `<p class="hm-team">우승 ${n0(c.c1.w)}회</p>` +
      `<p class="hm-big">${formatPoints(c.c1.p)}<span>점</span></p>` +
      (c.c2 && c.cm != null
        ? `<p class="hm-vs">2위 ${nwe(c.c2.n)} ${pts(c.c2.p)}<br>차이 <b>${pts(c.cm)}</b>, 1위 점수의 ${pc(c.cmp)}</p>`
        : '') +
      `</div>`
    : `<div class="hm-champ hm-none"><p class="hm-lab">컨스트럭터 1위</p><p class="hm-vs">컨스트럭터 챔피언십은 ${constructorFirst}년에 시작했다. 이 시즌에는 컨스트럭터 순위가 없다.</p></div>`;

  const notes: string[] = [];
  for (const e of c.ex) notes.push(`실격으로 드라이버 순위에서 빠진 기록: ${nwe(e.n)} ${pts(e.p)}.`);
  if (c.ex.length && c.lc != null) notes.push('선두가 마지막으로 바뀐 라운드는 순위에서 빠진 기록의 그 시점 점수를 넣어 센 값이다.');
  for (const a of c.ca) {
    notes.push(
      a.k === 'excluded'
        ? `컨스트럭터 순위에서 제외된 팀: ${nwe(a.n)} (${pts(a.p)}).`
        : `점수가 깎인 팀: ${nwe(a.n)} (${pts(a.p)}${a.pos ? `, ${a.pos}위` : ''}).`,
    );
  }
  if (c.d1.f != null) notes.push(`F1DB는 드라이버 1위 점수를 ${pts(c.d1.f)}으로 적는다. 이 쪽은 Jolpica 값을 적었다.`);
  if (c.c1?.f != null) notes.push(`F1DB는 컨스트럭터 1위 점수를 ${pts(c.c1.f)}으로 적는다. 이 쪽은 Jolpica 값을 적었다.`);

  return (
    head +
    `<div class="hm-duo">${driver}${team}</div>` +
    (notes.length ? `<p class="hm-note">${notes.join(' ')}</p>` : '') +
    `<p class="hm-more"><a href="${routes.season(c.s)}">${c.s} 시즌 캘린더와 순위 추이 보기</a></p>`
  );
}
