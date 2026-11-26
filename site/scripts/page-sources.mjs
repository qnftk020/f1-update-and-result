// 페이지별 자료 표기 통합(DESIGN.md "자료 표기").
// 그림과 표는 화면에 출처 줄을 내지 않고 <template data-cite="jolpica site"> 표시만 남긴다(lib/sources.ts citeKeys).
// 빌드가 끝나면 페이지마다 그 표시를 모아 꼬리말 "자료" 줄에서 쓰이지 않은 데이터원을 지우고, 표시는 걷어 낸다.
// 표시가 하나도 없는 페이지(소개 글 등)는 "자료" 줄을 통째로 지운다.
// pretendard-preload보다 먼저 돌아야 남은 글자로 글꼴 조각을 고른다(astro.config.mjs의 integrations 순서).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith('.html')) out.push(p);
  }
  return out;
}

export function applyPageSources(html) {
  const used = new Set();
  let out = html.replace(/<template data-cite(?:="([^"]*)")?><\/template>/g, (_m, keys = '') => {
    for (const k of keys.split(/\s+/).filter(Boolean)) used.add(k);
    return '';
  });
  out = out.replace(/<p class="foot-src"[^>]*data-page-sources[^>]*>[\s\S]*?<\/p>/, (block) => {
    if (!used.size) return '';
    return block.replace(/<span data-prov="([a-z0-9]+)">[\s\S]*?<\/span>(?=<span data-prov|<\/p>)/g, (item, k) => (used.has(k) ? item : ''));
  });
  return out;
}

export default function pageSources() {
  return {
    name: 'page-sources',
    hooks: {
      'astro:build:done': async ({ dir, logger }) => {
        const root = fileURLToPath(dir);
        let n = 0;
        for (const file of walk(root)) {
          const html = fs.readFileSync(file, 'utf8');
          if (!html.includes('data-page-sources') && !html.includes('data-cite')) continue;
          const out = applyPageSources(html);
          if (out !== html) {
            fs.writeFileSync(file, out);
            n++;
          }
        }
        logger.info(`자료 줄 ${n}개 페이지`);
      },
    },
  };
}
