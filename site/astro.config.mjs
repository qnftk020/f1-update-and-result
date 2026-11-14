// @ts-check
import { defineConfig } from 'astro/config';
import pretendardPreload from './scripts/pretendard-preload.mjs';

/**
 * Pretendard 동적 서브셋 CSS의 font-display를 swap에서 optional로 바꾼다.
 * swap이면 대체 글꼴로 먼저 그린 뒤 Pretendard가 도착할 때 줄바꿈이 바뀌어 화면이 흔들린다(390px 측정에서 CLS 0.23까지).
 * optional은 처음 약 100ms 안에 받은 글꼴만 쓰고 그 뒤에는 바꾸지 않는다. 받은 조각은 캐시되어 다음 쪽부터 Pretendard로 그린다.
 * 쪽마다 필요한 서브셋은 scripts/pretendard-preload.mjs가 미리 받기 링크로 넣어 그 100ms 안에 도착하도록 돕는다.
 * @returns {import('vite').Plugin}
 */
function pretendardOptional() {
  return {
    name: 'pretendard-font-display-optional',
    enforce: 'pre',
    transform(code, id) {
      if (!id.includes('pretendard') || !id.split('?')[0].endsWith('.css')) return null;
      return { code: code.replaceAll('font-display: swap', 'font-display: optional'), map: null };
    },
  };
}

// GitHub Pages 프로젝트 사이트로 배포한다.
export default defineConfig({
  site: 'https://qnftk020.github.io',
  base: '/f1-update-and-result',
  // 개발 서버 화면 아래의 도구 막대가 머리 없는 스크린숏을 가리지 않게 끈다.
  devToolbar: { enabled: false },
  vite: { plugins: [pretendardOptional()] },
  integrations: [pretendardPreload()],
});
