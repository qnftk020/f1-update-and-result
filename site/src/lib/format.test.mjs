// format.ts 표기 함수의 회귀 테스트. 새 의존성 없이 `node --test site/src/lib/format.test.mjs`로 돌린다.
// Node 22.18 이상은 타입 표기를 지우고 .ts를 바로 읽는다.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { formatPoints, formatQualiIndex, formatSignedPercent } from './format.ts';

test('formatPoints: 정수는 그대로, 반점은 소수 첫째 자리까지 보인다', () => {
  assert.equal(formatPoints(8), '8');
  assert.equal(formatPoints(1234), '1,234');
  assert.equal(formatPoints(3.5), '3.5');
  assert.equal(formatPoints(0), '0');
  assert.equal(formatPoints(null), '');
  assert.equal(formatPoints(undefined), '');
});

test('formatPoints: 1950년대 공유 점수(1/7, 1/3)는 소수 둘째 자리까지 보인다', () => {
  // season/1954.json, season/1955.json에 실제로 있는 값이다.
  assert.equal(formatPoints(0.14), '0.14');
  assert.equal(formatPoints(1.1400000000000001), '1.14');
  assert.equal(formatPoints(4.14), '4.14');
  assert.equal(formatPoints(24.64), '24.64');
  assert.equal(formatPoints(25.14), '25.14');
  assert.equal(formatPoints(1.33), '1.33');
});

test('formatQualiIndex: 반올림해서 0이 되는 양수에는 더하기 부호를 붙이지 않는다', () => {
  assert.equal(formatQualiIndex(0), '0.000%');
  assert.equal(formatQualiIndex(0, 1), '0.0%');
  assert.equal(formatQualiIndex(0.04, 1), '0.0%');
  assert.equal(formatQualiIndex(0.0004), '0.000%');
  assert.equal(formatQualiIndex(-0.0004), '0.000%');
});

test('formatQualiIndex: 0보다 큰 값은 더하기 부호와 함께 보인다', () => {
  assert.equal(formatQualiIndex(0.245), '+0.245%');
  assert.equal(formatQualiIndex(0.04, 2), '+0.04%');
  assert.equal(formatQualiIndex(0.0005), '+0.001%');
  assert.equal(formatQualiIndex(null), '');
});

test('formatSignedPercent: 부호와 0 처리는 그대로다', () => {
  assert.equal(formatSignedPercent(-0.1234), '−0.123%');
  assert.equal(formatSignedPercent(0.1234), '+0.123%');
  assert.equal(formatSignedPercent(-0.0001), '0.000%');
});

test('num: 지수 표기 반올림, 빼기 기호, 부호', async () => {
  const { num, pct, ivl, josa, posChange, roundsText } = await import('./format.ts');
  assert.equal(num(0.244504726, 3), '0.245');
  assert.equal(num(0.2445, 3), '0.245');
  assert.equal(num(-1.4569, 2, { sign: true }), '−1.46');
  assert.equal(num(0.0004, 3, { sign: true }), '0.000');
  assert.equal(num(1e-7, 3), '0.000');
  assert.equal(num(null), '결측');
  assert.equal(pct(1.336836475), '1.337%');
  assert.equal(ivl(-0.184, -0.39, 0.06), '−0.18 (−0.39 ~ +0.06)');
  assert.equal(josa('플로어', '이', '가'), '플로어가');
  assert.equal(josa('70건', '이', '가'), '70건이');
  assert.equal(josa('23', '으로', '로'), '23으로');
  assert.equal(posChange(18, 9), '+9');
  assert.equal(posChange(3, 11), '−8');
  assert.equal(roundsText([17, 22]), '2개 (17, 22라운드)');
  assert.equal(roundsText([]), '0개');
});

test('typeset과 keepNames: 글 조각만 묶고 태그와 스크립트는 건드리지 않는다', async () => {
  const { keepNames, typeset } = await import('./typeset.ts');
  assert.equal(
    keepNames('<b>Max Verstappen</b><span class="aside">(Red Bull)</span>의 우승'),
    '<span class="nw"><b><span class="nw" lang="en">Max Verstappen</span></b><span class="aside">(<span class="nw" lang="en">Red Bull</span>)</span>의</span> 우승',
  );
  assert.equal(typeset('<p>1996-2025 기간</p>'), '<p><span class="nw">1996-2025</span> 기간</p>');
  assert.equal(typeset('<p>CC BY-NC-SA 4.0</p>'), '<p><span class="nw">CC BY-NC-SA 4.0</span></p>');
  assert.equal(typeset('<p>2026-10-27 덤프</p>'), '<p>2026-10-27 덤프</p>');
  const script = '<script type="application/json">{"r":"1996-2025","a":1<2}</script>';
  assert.equal(typeset(script), script);
  assert.equal(typeset('<a title="2003-2005">x</a>'), '<a title="2003-2005">x</a>');
});
