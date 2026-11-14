// typeset.ts 조판 함수의 회귀 테스트. 새 의존성 없이 `node --test site/src/lib/typeset.test.mjs`로 돌린다.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { glueParticles, typeset } from './typeset.ts';

test('glueParticles: 영어 조각 뒤의 조사를 함께 묶는다', () => {
  assert.equal(glueParticles('자료는 <span lang="en">OpenF1</span>이다.'), '자료는 <span class="nw"><span lang="en">OpenF1</span>이다</span>.');
  assert.equal(
    glueParticles('예를 들어 <code lang="en">renault</code>에는 1977'),
    '예를 들어 <span class="nw"><code lang="en">renault</code>에는</span> 1977',
  );
});

test('glueParticles: 조사가 없거나 긴 한글 낱말이 이어지면 묶지 않는다', () => {
  assert.equal(glueParticles('<span lang="en">Red Bull</span> 팀'), '<span lang="en">Red Bull</span> 팀');
  assert.equal(glueParticles('<span lang="en">Alpine</span>엔스톤계보'), '<span lang="en">Alpine</span>엔스톤계보');
});

test('glueParticles: script와 style 안은 건드리지 않는다', () => {
  const s = '<script>const x = \'<span lang="en">A</span>의\';</script>';
  assert.equal(glueParticles(s), s);
});

test('typeset: 조사 묶기와 기존 연도 범위 묶기가 함께 적용된다', () => {
  assert.equal(
    typeset('<span lang="en">Toleman</span>은 1981-1985'),
    '<span class="nw"><span lang="en">Toleman</span>은</span> <span class="nw">1981-1985</span>',
  );
});
