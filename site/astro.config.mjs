// @ts-check
import { defineConfig } from 'astro/config';

// GitHub Pages 프로젝트 사이트로 배포한다.
export default defineConfig({
  site: 'https://qnftk020.github.io',
  base: '/f1-update-and-result',
  // 개발 서버 화면 아래의 도구 막대가 머리 없는 스크린숏을 가리지 않게 끈다.
  devToolbar: { enabled: false },
});
