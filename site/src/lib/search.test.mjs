// search.ts 전역 검색 맞추기의 회귀 테스트. `node --test site/src/lib/search.test.mjs`로 돌린다.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { fold, groupResults, searchEntries } from './search.ts';

const E = [
  { k: 'driver', n: 'Max Verstappen', a: 'VER Dutch 네덜란드 max verstappen', m: '2015-2025', u: '/d/ver', w: 300 },
  { k: 'driver', n: 'Jos Verstappen', a: 'Dutch 네덜란드', m: '1994-2003', u: '/d/jos', w: 100 },
  { k: 'driver', n: 'Kimi Räikkönen', a: 'RAI Finnish 핀란드', m: '2001-2021', u: '/d/rai', w: 350 },
  { k: 'constructor', n: 'McLaren', a: 'British 영국', m: '1966-2025', u: '/c/mclaren', w: 1000 },
  { k: 'team', n: '워킹 (맥라렌)', a: 'woking Woking, United Kingdom McLaren', m: '1966-', u: '/t/woking', w: 1000 },
  { k: 'race', n: '1988 모나코 그랑프리', a: 'Monaco Grand Prix 모나코 Circuit de Monaco R4', m: '1988-05-15', u: '/s/1988#r4', w: 1988 },
  { k: 'race', n: '2025 모나코 그랑프리', a: 'Monaco Grand Prix 모나코 R8', m: '2025-05-25', u: '/s/2025#r8', w: 2025 },
  { k: 'engine', n: '2019 엔진', a: '2019 PU', m: 'PU 사용 현황', u: '/e/2019', w: 2019 },
];

test('fold: 발음 구별 기호와 문장부호를 지우고 소문자로', () => {
  assert.equal(fold('Kimi Räikkönen'), 'kimi raikkonen');
  assert.equal(fold('  Pérez-Mendoza  '), 'perez mendoza');
  assert.equal(fold('워킹 (맥라렌)'), '워킹 맥라렌');
});

test('이름 첫머리가 맞는 항목이 먼저 온다', () => {
  const r = searchEntries(E, 'verst');
  assert.deepEqual(r.map((x) => x.u), ['/d/ver', '/d/jos']);
});

test('약어와 그대로 같으면 이름 첫머리보다 먼저 온다', () => {
  const list = [...E, { k: 'driver', n: 'Vern Schuppan', a: 'Australian 호주', m: '1974-1977', u: '/d/vern', w: 9 }];
  assert.equal(searchEntries(list, 'ver')[0].u, '/d/ver');
  assert.equal(searchEntries(list, 'vern')[0].u, '/d/vern');
});

test('약어와 다른 이름으로도 찾는다', () => {
  assert.equal(searchEntries(E, 'VER')[0].u, '/d/ver');
  assert.equal(searchEntries(E, 'raikkonen')[0].u, '/d/rai');
  assert.equal(searchEntries(E, '워킹')[0].u, '/t/woking');
});

test('낱말은 모두 맞아야 한다: 연도와 대회명', () => {
  const r = searchEntries(E, '1988 모나코');
  assert.deepEqual(r.map((x) => x.u), ['/s/1988#r4']);
  assert.equal(searchEntries(E, '2019 엔진')[0].u, '/e/2019');
  assert.deepEqual(searchEntries(E, 'zzz'), []);
  assert.deepEqual(searchEntries(E, '   '), []);
});

test('종류별 묶음과 묶음 안 개수 제한', () => {
  const g = groupResults(searchEntries(E, '모나코'), 1);
  assert.equal(g.length, 1);
  assert.equal(g[0].kind, 'race');
  assert.equal(g[0].items.length, 1);
  assert.equal(g[0].more, 1);
  const g2 = groupResults(searchEntries(E, 'mclaren'));
  assert.deepEqual(g2.map((x) => x.kind), ['constructor', 'team']);
});
