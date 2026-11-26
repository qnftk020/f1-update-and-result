// GitHub Pages의 base 경로를 붙인 사이트 내부 주소를 만든다.
const base = import.meta.env.BASE_URL.replace(/\/$/, '');

/** 사이트 내부 경로. url('/seasons/2025/') -> '/f1-update-and-result/seasons/2025/' */
export function url(path = '/'): string {
  const clean = path.startsWith('/') ? path : `/${path}`;
  return `${base}${clean}`;
}

export const routes = {
  home: () => url('/'),
  seasons: () => url('/seasons/'),
  season: (year: number) => url(`/seasons/${year}/`),
  drivers: () => url('/drivers/'),
  driver: (driverId: string) => url(`/drivers/${driverId}/`),
  teams: () => url('/teams/'),
  team: (lineageId: string) => url(`/teams/${lineageId}/`),
  constructors: () => url('/constructors/'),
  constructorPage: (constructorId: string) => url(`/constructors/${constructorId}/`),
  constructorSeason: (constructorId: string, season: number) => url(`/constructors/${constructorId}/${season}/`),
  /**
   * 목록 쪽의 비교 절. compare('d', ['senna', 'prost']) -> '/…/drivers/?cmp=senna,prost#compare'.
   * ID 없이 compare('c')면 컨스트럭터 목록의 처음 비교(그 시즌 1-3위)로 간다.
   */
  compare: (kind: 'd' | 'c', ids: string[] = []) => `${url(kind === 'd' ? '/drivers/' : '/constructors/')}${ids.length ? `?cmp=${ids.join(',')}` : ''}#compare`,
  /** 비교 자료 파일 /data/compare/<d|c>/<id>.json */
  compareData: (kind: 'd' | 'c', id: string) => url(`/data/compare/${kind}/${id}.json`),
  upgrades: () => url('/upgrades/'),
  engines: () => url('/engines/'),
  regulations: () => url('/regulations/'),
  /** 체코지수(결승 관전 지수). 대회 행은 #s<연도>r<라운드> */
  chekoji: () => url('/chekoji/'),
  about: () => url('/about/'),
  search: () => url('/search/'),
  /** 전역 검색 색인(빌드 때 만든다, pages/data/search.json.ts) */
  searchIndex: () => url('/data/search.json'),
};

/** 데이터와 방법론 하위 쪽 */
export const aboutRoutes = {
  intro: () => url('/about/'),
  methodology: () => url('/about/methodology/'),
  sources: () => url('/about/sources/'),
  license: () => url('/about/license/'),
};

export type NavKey = 'home' | 'seasons' | 'drivers' | 'constructors' | 'teams' | 'upgrades' | 'engines' | 'regulations' | 'about' | 'search' | 'chekoji';

/** 주 메뉴 아홉 칸(2026-11-26). 홈은 사이트 이름 링크가 맡고, 컨스트럭터 목록과 체코지수를 메뉴에 올렸다. */
export const NAV: { key: NavKey; label: string; href: string }[] = [
  { key: 'seasons', label: '시즌', href: routes.seasons() },
  { key: 'drivers', label: '드라이버', href: routes.drivers() },
  { key: 'constructors', label: '컨스트럭터', href: routes.constructors() },
  { key: 'teams', label: '팀 계보', href: routes.teams() },
  { key: 'upgrades', label: '업그레이드', href: routes.upgrades() },
  { key: 'engines', label: '엔진', href: routes.engines() },
  { key: 'regulations', label: '규정', href: routes.regulations() },
  { key: 'chekoji', label: '체코지수', href: routes.chekoji() },
  { key: 'about', label: '방법론', href: routes.about() },
];

/** 업그레이드 탐색기 조건 링크: upgradesWith({ team: 'enstone', season: 2025 }) -> '/…/upgrades/#team=enstone&season=2025' */
export function upgradesWith(params: Record<string, string | number>): string {
  const q = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
  return `${routes.upgrades()}${q ? `#${q}` : ''}`;
}
