// Pretendard 동적 서브셋 미리 받기(preload) 통합.
// 빌드가 끝난 뒤 쪽마다 HTML에 실제로 쓰인 글자를 모아, 그 글자를 담은 서브셋 파일만 <link rel="preload">로 <head>에 넣는다.
// 글꼴은 font-display: optional(astro.config.mjs)이라 처음 약 100ms 안에 도착한 서브셋만 쓰고 뒤늦게 바꾸지 않는다.
// 미리 받기로 그 안에 도착할 가능성을 높이고, 늦으면 그 쪽은 대체 글꼴로 흔들림 없이 그린다(받은 파일은 다음 쪽에서 캐시로 쓴다).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/** "U+ac00-ac0f, U+3131" 꼴의 unicode-range를 [시작, 끝] 목록으로 바꾼다 */
function parseRanges(text) {
  return text.split(',').map((part) => {
    const [a, b] = part.trim().replace(/^U\+/i, '').split('-');
    return [parseInt(a, 16), parseInt(b ?? a, 16)];
  });
}

/** 빌드 CSS에서 Pretendard 서브셋과 라틴 보조 글꼴 @font-face의 주소와 글자 범위를 읽는다 */
function readFaces(dir) {
  const faces = [];
  const extra = new Set(); // CSS content 속성으로 그리는 글자(" (현재)", "×" 등)
  for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.css'))) {
    const css = fs.readFileSync(path.join(dir, f), 'utf8');
    for (const m of css.matchAll(/@font-face\{[^}]*?\}/g)) {
      const block = m[0];
      if (!/Pretendard Variable|F1 Latin Supplement/.test(block)) continue;
      const url = /url\(([^)]+\.woff2)\)/.exec(block)?.[1];
      const range = /unicode-range:([^;}]+)/.exec(block)?.[1];
      if (url && range) faces.push({ url: url.replace(/^["']|["']$/g, ''), ranges: parseRanges(range) });
    }
    for (const m of css.matchAll(/content:\s*"((?:[^"\\]|\\.)*)"/g)) {
      const s = m[1].replace(/\\([0-9a-fA-F]{1,6})\s?/g, (_x, h) => String.fromCodePoint(parseInt(h, 16)));
      for (const ch of s) extra.add(ch.codePointAt(0));
    }
  }
  return { faces, extra };
}

/** 화면에 그려지는 글자: script, style, 태그를 빼고, 입력창의 placeholder는 넣는다 */
function pageChars(html) {
  const placeholders = [...html.matchAll(/placeholder="([^"]*)"/g)].map((m) => m[1]).join('');
  const text = html
    .replace(/<script\b[\s\S]*?<\/script>/gi, '')
    .replace(/<style\b[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/&#(\d+);/g, (_m, d) => String.fromCodePoint(+d))
    .replace(/&#x([0-9a-f]+);/gi, (_m, h) => String.fromCodePoint(parseInt(h, 16)));
  const set = new Set();
  for (const ch of text + placeholders) set.add(ch.codePointAt(0));
  return set;
}

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith('.html')) out.push(p);
  }
  return out;
}

/** @returns {import('astro').AstroIntegration} */
export default function pretendardPreload() {
  return {
    name: 'pretendard-preload',
    hooks: {
      'astro:build:done': ({ dir, logger }) => {
        const root = fileURLToPath(dir);
        const { faces, extra } = readFaces(path.join(root, '_astro'));
        if (!faces.length) {
          logger.warn('Pretendard 서브셋 @font-face를 찾지 못해 미리 받기를 넣지 않았다');
          return;
        }
        // 글자 코드 → 서브셋 번호
        const faceOf = new Map();
        faces.forEach((f, i) => { for (const [a, b] of f.ranges) for (let c = a; c <= b; c++) if (!faceOf.has(c)) faceOf.set(c, i); });
        let pages = 0, links = 0;
        for (const file of walk(root)) {
          const html = fs.readFileSync(file, 'utf8');
          if (!html.includes('</head>')) continue;
          const chars = pageChars(html);
          for (const c of extra) chars.add(c);
          const idx = new Set();
          for (const c of chars) if (faceOf.has(c)) idx.add(faceOf.get(c));
          const need = [...idx].sort((a, b) => a - b).map((i) => faces[i]);
          const tags = need.map((f) => `<link rel="preload" href="${f.url}" as="font" type="font/woff2" crossorigin>`).join('');
          fs.writeFileSync(file, html.replace('</head>', `${tags}</head>`));
          pages++;
          links += need.length;
        }
        logger.info(`Pretendard 서브셋 미리 받기: ${pages}쪽, 쪽당 평균 ${(links / Math.max(pages, 1)).toFixed(1)}개`);
      },
    },
  };
}
