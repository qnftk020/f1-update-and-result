// 출처와 기준일. DESIGN.md "자료 표기":
//   그림과 표는 source/asof를 받지만 화면에 줄로 내지 않는다. FigureFrame과 SourceLine이 citeKeys()로 데이터원 키만
//   표시해 두면 빌드 뒤 scripts/page-sources.mjs가 그 페이지에 쓰인 데이터원만 꼬리말 "자료" 줄에 남긴다.
// 날짜는 모두 meta.json에서 온다. Jolpica 기준일은 언제나 덤프 날짜다(빌드일, 추출일을 쓰지 않는다).
// 화면에는 "덤프", "API" 같은 수집 방식 낱말을 쓰지 않는다. 덤프와 API 반영의 구분은 /about/sources/에서 설명한다.
import { meta } from './data.ts';
import { n0 } from './format.ts';
import { nw } from './typeset.ts';

const S = meta.sources;

/** 'Jolpica-F1 (CC BY-NC-SA 4.0)'. 뒤에 자료 종류를 붙여 쓴다: `${JOLPICA} 예선 기록(Q1~Q3), 이 사이트 계산` */
export const JOLPICA = `${S.jolpica.name} (${S.jolpica.license})`;
export const F1DB = `${S.f1db.name} (${S.f1db.license})`;
export const OPENF1_LICENSE = S.openf1.license;
/** 'OpenF1 랩, 스틴트, 레이스 컨트롤 (CC BY-NC-SA 4.0)' 꼴로 쓴다 */
export const OPENF1 = S.openf1.name;
export const FIA_CP = 'FIA Car Presentation Submissions';
/** 2014-2022년 결승 우천 판정에 쓴 재분석 강수량 */
export const OPENMETEO = 'Open-Meteo ERA5 강수량 (CC BY 4.0)';

/** Jolpica 기준일: '2026-10-27' (덤프 뒤에 API로 대회를 더 반영했으면 ', 2025 R24는 2026-11-11 반영'이 붙는다) */
export function asofJolpica(): string {
  const j = S.jolpica;
  const base = nw(j.dump ?? j.version.slice(0, 10));
  return j.api ? `${base}, ${nw(j.api)}는 ${nw(j.as_of)} 반영` : base;
}

/** 퀄리파잉 지수: '2026-10-27, 2025 R24는 2026-11-11 반영, 지수 2026-11-11 계산' */
export function asofQualiIndex(): string {
  return `${asofJolpica()}, 지수 ${nw(S.pace.as_of)} 계산`;
}

/** 레이스 지수: 'OpenF1 2026-11-11 수집, 지수 2026-11-11 계산' */
export function asofRaceIndex(): string {
  return `${S.openf1.name} ${nw(S.openf1.as_of)} 수집, 지수 ${nw(S.pace.as_of)} 계산`;
}

/** 레이스 지수 Jolpica 계열(2014-2022): '2026-10-27, 지수 2026-11-25 계산' */
export function asofRaceIndexJolpica(): string {
  return `${nw(S.jolpica.dump ?? S.jolpica.version.slice(0, 10))}, 지수 ${nw(S.pace.as_of)} 계산`;
}

/** OpenF1 자료(우천 판정 등): '2026-11-11 수집' */
export function asofOpenF1(): string {
  return `${nw(S.openf1.as_of)} 수집`;
}

/** FIA 문서: '2026-11-11 수집' */
export function asofFia(): string {
  return `${nw(S.fia.as_of)} 수집`;
}

/** F1DB: 'v2026.20.0 (2026-11-11 확인)' */
export function asofF1db(): string {
  return `${S.f1db.version} (${nw(S.f1db.as_of)} 확인)`;
}

/** 지수 계산일만: '2026-11-11' */
export const computedOn = S.pace.as_of;

export const SAMPLE_SOURCE = '표본 값 (디자인용)';
export const SAMPLE_ASOF = '표본 값이라 기준일이 없다';

/** 꼬리말의 데이터 기준일 표. 데이터원, 쓰는 범위, 기준일, 라이선스. */
export function footerRows(): { src: string; latin: boolean; use: string; asof: string; license: string }[] {
  const c = meta.counts;
  return [
    {
      src: S.jolpica.name,
      latin: true,
      use: `결승 결과, 예선 기록, 순위 (${meta.first_season}-${meta.last_season})`,
      asof: asofJolpica(),
      license: S.jolpica.license,
    },
    {
      src: `${S.f1db.name} ${S.f1db.version}`,
      latin: true,
      use: '예선 형식, 1950-2005 예선 기록, 엔진 제조사, 섀시와 엔진 모델',
      asof: `${nw(S.f1db.as_of)} 확인`,
      license: S.f1db.license,
    },
    {
      src: S.openf1.name,
      latin: true,
      use: `${S.openf1.version} 랩, 스틴트, 날씨, 레이스 컨트롤`,
      asof: asofOpenF1(),
      license: S.openf1.license,
    },
    {
      src: FIA_CP,
      latin: true,
      use: `업그레이드 항목 ${n0(c.upgrade_items)}건 (문서 ${n0(c.upgrade_documents)}건)`,
      asof: asofFia(),
      license: 'FIA 저작물, 원문 링크와 추출 정보만 싣는다',
    },
    {
      src: S.pace.name,
      latin: false,
      use: S.pace.version.replace('퀄리파잉', '퀄리파잉 지수').replace('레이스', '레이스 지수'),
      asof: `${nw(S.pace.as_of)} 계산`,
      license: '데이터와 방법론 참고',
    },
  ];
}

/** 꼬리말 "자료" 줄의 데이터원 키. 순서가 표기 순서다 */
export const CITE_KEYS = ['jolpica', 'f1db', 'openf1', 'openmeteo', 'fia', 'site'] as const;
export type CiteKey = (typeof CITE_KEYS)[number];

/** 그림·표의 source/asof 문구에서 데이터원 키를 고른다 */
export function citeKeys(...parts: (string | undefined)[]): CiteKey[] {
  const s = parts.filter(Boolean).join(' ').replace(/<[^>]+>/g, '');
  const keys: CiteKey[] = [];
  if (/Jolpica/.test(s)) keys.push('jolpica');
  if (/F1DB/.test(s)) keys.push('f1db');
  if (/OpenF1/.test(s)) keys.push('openf1');
  if (/Open-Meteo/.test(s)) keys.push('openmeteo');
  if (/FIA|fia\.com/.test(s)) keys.push('fia');
  if (/이 사이트|계산|집계|계보/.test(s)) keys.push('site');
  return keys;
}

/** 꼬리말 "자료" 줄의 항목(HTML). 빌드 뒤 그 페이지에 쓰이지 않은 항목은 지워진다 */
export function citeItems(): [CiteKey, string][] {
  return [
    ['jolpica', `<span lang="en">${S.jolpica.name}</span> (${S.jolpica.license}), ${nw(S.jolpica.dump ?? S.jolpica.version.slice(0, 10))} 기준${S.jolpica.api ? `(${nw(S.jolpica.api)}는 ${nw(S.jolpica.as_of)} 추가)` : ''}`],
    ['f1db', `<span lang="en">${S.f1db.name} ${S.f1db.version}</span> (${S.f1db.license})`],
    ['openf1', `<span lang="en">${S.openf1.name}</span> (${S.openf1.license}), ${nw(S.openf1.as_of)} 수집`],
    ['openmeteo', `<span lang="en">Open-Meteo</span> ERA5 강수량 (CC BY 4.0)`],
    ['fia', `FIA 공개 문서, ${nw(S.fia.as_of)} 수집 (원문 링크만 제공)`],
    ['site', `지수와 집계는 이 사이트에서 계산(${nw(S.pace.as_of)})`],
  ];
}
