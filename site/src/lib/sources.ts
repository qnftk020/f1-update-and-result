// 출처 줄과 기준일 문구. DESIGN.md "출처 줄 형식":
//   출처 {데이터원} {자료 종류} ({라이선스}){, 이 사이트 계산(방법)} · 기준일 {날짜} {덤프|수집|확인}{, 지수 {날짜} 계산}
// 날짜는 모두 meta.json에서 온다. Jolpica 기준일은 언제나 덤프 날짜다(빌드일, 추출일을 쓰지 않는다).
// 돌려주는 값은 HTML 조각이다(날짜를 .nw로 묶는다). Figure, SourceLine의 source/asof 속성에 그대로 넘긴다.
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

/** Jolpica 기준일: '2026-10-27 덤프' (API로 대회를 더 반영했으면 ', API 2025 R24 2026-12-08 수집'이 붙는다) */
export function asofJolpica(): string {
  const j = S.jolpica;
  const base = `${nw(j.dump ?? j.version.slice(0, 10))} 덤프`;
  return j.api ? `${base}, API ${j.api} ${nw(j.as_of)} 수집` : base;
}

/** 퀄리파잉 지수: '2026-10-27 덤프, 지수 2026-11-11 계산' */
export function asofQualiIndex(): string {
  return `${asofJolpica()}, 지수 ${nw(S.pace.as_of)} 계산`;
}

/** 레이스 지수: 'OpenF1 2026-11-11 수집, 지수 2026-11-11 계산' */
export function asofRaceIndex(): string {
  return `${S.openf1.name} ${nw(S.openf1.as_of)} 수집, 지수 ${nw(S.pace.as_of)} 계산`;
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
      use: '예선 형식, 1996-2005 예선 기록, 엔진 제조사',
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
