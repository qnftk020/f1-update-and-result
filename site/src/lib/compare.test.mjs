// compare.ts 비교 계산의 회귀 테스트. 새 의존성 없이 `node --test site/src/lib/compare.test.mjs`로 돌린다.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MAX_PICK, ahead, bestPerRace, fold, headToHead, parseIds, seasonPoints, shortNames } from './compare.ts';

test('ahead: 완주로 분류된 쪽이 앞이고, 둘 다 분류되면 순위가 높은 쪽이 앞이다', () => {
  assert.equal(ahead(['F', 5], ['R', 1]), 1);
  assert.equal(ahead(['D', 1], ['F', 18]), -1);
  assert.equal(ahead(['F', 2], ['F', 3]), 1);
  assert.equal(ahead(['F', 4], ['F', 4]), 0); // 차량 공유
  assert.equal(ahead(['R', 3], ['N', 9]), 0); // 둘 다 분류되지 않으면 세지 않는다
});

test('bestPerRace: 한 대회에 행이 여럿이면 가장 앞선 행을 두고 인디 500을 뺀다', () => {
  const rows = [
    { s: 1950, r: 7, n: '이탈리아', o: 'R', p: 13 },
    { s: 1950, r: 7, n: '이탈리아', o: 'F', p: 2 },
    { s: 1950, r: 7, n: '이탈리아', o: 'R', p: 15 },
    { s: 1951, r: 2, n: '인디 500', o: 'F', p: 1 },
    { s: 1950, r: 1, n: '영국', o: 'F', p: 1 },
  ];
  assert.deepEqual(bestPerRace(rows), [
    [1950, 1, 'F', 1],
    [1950, 7, 'F', 2],
  ]);
});

test('headToHead: 같은 대회만 세고 앞뒤를 가린 대회를 따로 센다', () => {
  const a = [
    [1988, 1, 'F', 2],
    [1988, 2, 'R', 20],
    [1988, 3, 'F', 1],
    [1989, 1, 'R', 10],
    [1990, 1, 'F', 1],
  ];
  const b = [
    [1988, 1, 'F', 1],
    [1988, 2, 'F', 1],
    [1988, 3, 'F', 2],
    [1989, 1, 'N', 22],
  ];
  assert.deepEqual(headToHead(a, b), { both: 4, counted: 3, a: 1, b: 2, first: 1988, last: 1989 });
  assert.deepEqual(headToHead(a, []), { both: 0, counted: 0, a: 0, b: 0, first: null, last: null });
});

test('fold: 발음 구별 기호를 지워 목록 검색이 악센트 없이도 맞게 한다', () => {
  assert.equal(fold('Kimi  Räikkönen'), 'kimi raikkonen');
  assert.equal(fold('Sergio Pérez'), 'sergio perez');
  assert.equal(fold('Tom Belsø'), 'tom belso');
  assert.ok(fold('Kimi Räikkönen RAI 핀란드').includes(fold('raikk')));
  assert.ok(fold('Ayrton Senna 브라질').includes(fold('브라질')));
});

test('parseIds: 모르는 ID와 중복을 버리고 최대 개수까지만 둔다', () => {
  const known = new Set(['senna', 'prost', 'hamilton', 'schumacher']);
  assert.deepEqual(parseIds('senna,nobody,prost,senna,hamilton,schumacher', known), ['senna', 'prost', 'hamilton']);
  assert.equal(MAX_PICK, 3);
  assert.deepEqual(parseIds('', known), []);
  assert.equal(parseIds(null, known), null);
});

test('seasonPoints: 경력 햇수와 누적 우승', () => {
  const file = {
    first: 1984,
    s: [
      [1984, 9, 0, 3, 14, 'Toleman', 0, 0],
      [1985, 4, 2, 7, 16, 'Lotus', 0, 0],
      [1988, 1, 8, 11, 16, 'McLaren', 1, 0],
    ],
  };
  const pts = seasonPoints(file, 'career');
  assert.deepEqual(pts.map((p) => [p.x, p.cum, p.champ]), [
    [1, 0, false],
    [2, 2, false],
    [5, 10, true],
  ]);
  assert.deepEqual(seasonPoints(file, 'year').map((p) => p.x), [1984, 1985, 1988]);
});

test('shortNames: 성이 겹치면 전체 이름을 쓴다', () => {
  assert.deepEqual(shortNames(['Michael Schumacher', 'Ralf Schumacher', 'Ayrton Senna'], 'd'), ['Michael Schumacher', 'Ralf Schumacher', 'Senna']);
  assert.deepEqual(shortNames(['Red Bull', 'McLaren'], 'c'), ['Red Bull', 'McLaren']);
});
