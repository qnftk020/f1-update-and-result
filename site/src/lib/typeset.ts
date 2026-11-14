// 한글 조판 도우미. design/final/src/build.py의 e(), glue(), keep_names(), typeset()을 옮겼다.
// 모두 HTML 문자열을 받아 HTML 문자열을 돌려준다. 데이터에서 온 글자는 먼저 esc()로 막는다.

/** HTML 특수 문자 막기. 데이터에서 온 이름, 영어 원문은 문장에 넣기 전에 반드시 거친다. */
export function esc(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const GLUE =
  /(<b>[^<]{1,40}<\/b>|[^\s<>()]{1,24})(<span class="aside">\([^<]{1,60}\)<\/span>)([가-힣]{0,3})/g;

/**
 * 이름이나 수치, 바로 뒤의 괄호 보조 정보(.aside), 그 뒤 조사를 한 덩어리로 묶는다.
 * 예: '<b>Max Verstappen</b><span class="aside">(Red Bull)</span>의', '529건<span class="aside">(62%)</span>으로'
 */
export function glue(html: string): string {
  return html.replace(GLUE, (_m, a: string, b: string, c: string) => `<span class="nw">${a}${b}${c}</span>`);
}

const LATIN = /(?<![\w/-])([A-Z][A-Za-zÀ-ſ.'-]*(?: [A-Z][A-Za-zÀ-ſ.'-]*)+)/g;

/** 태그는 그대로 두고 글 조각에만 fn을 적용한다. skipTags 안의 내용은 건드리지 않는다. */
function mapText(html: string, fn: (text: string) => string, skipTags: string[]): string {
  const open = new RegExp(`^<(${skipTags.join('|')})\\b`, 'i');
  const close = new RegExp(`^</(${skipTags.join('|')})>`, 'i');
  let skip = 0;
  // script, style, 주석은 안에 '<'가 있을 수 있어 통째로 한 조각으로 떼어 둔다.
  return html
    .split(/(<script\b[\s\S]*?<\/script>|<style\b[\s\S]*?<\/style>|<!--[\s\S]*?-->)/i)
    .map((chunk, i) => {
      if (i % 2 === 1) return chunk;
      return chunk
        .split(/(<[^>]+>)/)
        .map((part) => {
          if (part.startsWith('<')) {
            if (open.test(part) && !part.endsWith('/>')) skip += 1;
            else if (close.test(part)) skip = Math.max(0, skip - 1);
            return part;
          }
          return skip || !part ? part : fn(part);
        })
        .join('');
    })
    .join('');
}

/**
 * 리드와 절 문장 조판: glue()를 하고, 라틴 이름(대문자로 시작하는 낱말 둘 이상)을
 * <span class="nw" lang="en">으로 묶어 줄 끝에서 갈리지 않게 한다. 리드와 절 첫 문장에만 쓴다.
 */
export function keepNames(html: string): string {
  return mapText(
    glue(html),
    (text) => text.replace(LATIN, (_m, name: string) => `<span class="nw" lang="en">${name}</span>`),
    ['script', 'style', 'option', 'title', 'textarea'],
  );
}

const TYPE: RegExp[] = [
  /\(?CC BY(?:-NC-SA)? 4\.0\)?/g,
  /\(이 사이트 계산\)/g,
  /(?<![\d.-])(?:19|20)\d\d-(?:(?:19|20)\d\d|\d\d)(?![\d-])/g,
  /\(?[−+]?\d[\d.,]* ~ [−+]?\d[\d.,]*\)?/g,
];

// 영어 조각(<span lang="en">, <code lang="en">, <b lang="en">)과 바로 뒤의 한글 조사(1~3자)
const EN_PARTICLE = /(<(span|code|b)\b[^>]*\blang="en"[^>]*>[^<]{1,40}<\/\2>)([가-힣]{1,3})(?![가-힣])/g;

/**
 * 영어 조각과 뒤따르는 조사를 .nw로 묶는다. 'OpenF1 / 이다'처럼 조사만 다음 줄로 넘어가지 않게 한다.
 * script, style, 주석 안은 건드리지 않는다.
 */
export function glueParticles(html: string): string {
  return html
    .split(/(<script\b[\s\S]*?<\/script>|<style\b[\s\S]*?<\/style>|<!--[\s\S]*?-->)/i)
    .map((chunk, i) => (i % 2 === 1 ? chunk : chunk.replace(EN_PARTICLE, (_m, a: string, _t: string, p: string) => `<span class="nw">${a}${p}</span>`)))
    .join('');
}

/**
 * 마지막 조판 단계: 글 조각의 라이선스 이름, 연도 범위(1996-2025, 1981-85), 구간 값(−0.39 ~ +0.06),
 * "(이 사이트 계산)"을 .nw로 묶고, 영어 조각과 뒤의 조사를 붙인다(glueParticles).
 * 태그 속성과 script, style, option, title, textarea 안은 건드리지 않는다.
 * BaseLayout이 본문(main)과 꼬리말 전체에 한 번 적용한다. 페이지에서 따로 부를 일은 없다.
 */
export function typeset(html: string): string {
  return mapText(
    glueParticles(html),
    (text) => {
      let out = text;
      for (const rx of TYPE) out = out.replace(rx, (m) => `<span class="nw">${m}</span>`);
      return out;
    },
    ['script', 'style', 'option', 'title', 'textarea'],
  );
}

/** 굵은 값 + 괄호 보조 정보: b('0.201초') + aside('0.245%') 꼴의 문장 조각을 만든다. */
export function b(html: string): string {
  return `<b>${html}</b>`;
}
export function aside(html: string): string {
  return `<span class="aside">(${html})</span>`;
}
/** 영어 원문 조각: <span lang="en">. 이름을 문장에 넣을 때는 en(esc(name)) */
export function en(html: string): string {
  return `<span lang="en">${html}</span>`;
}
/** 줄바꿈 금지 조각 */
export function nw(html: string): string {
  return `<span class="nw">${html}</span>`;
}
