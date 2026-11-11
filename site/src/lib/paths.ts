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
  upgrades: () => url('/upgrades/'),
  engines: () => url('/engines/'),
  regulations: () => url('/regulations/'),
  about: () => url('/about/'),
};

/** 데이터와 방법론 하위 쪽 */
export const aboutRoutes = {
  intro: () => url('/about/'),
  methodology: () => url('/about/methodology/'),
  sources: () => url('/about/sources/'),
  license: () => url('/about/license/'),
};

export type NavKey = 'home' | 'seasons' | 'drivers' | 'teams' | 'upgrades' | 'engines' | 'regulations' | 'about';

/** 주 메뉴 여덟 칸 (2026-11-11에 드라이버를 더했다). */
export const NAV: { key: NavKey; label: string; href: string }[] = [
  { key: 'home', label: '홈', href: routes.home() },
  { key: 'seasons', label: '시즌', href: routes.seasons() },
  { key: 'drivers', label: '드라이버', href: routes.drivers() },
  { key: 'teams', label: '팀', href: routes.teams() },
  { key: 'upgrades', label: '업그레이드 탐색기', href: routes.upgrades() },
  { key: 'engines', label: '엔진', href: routes.engines() },
  { key: 'regulations', label: '규정 아카이브', href: routes.regulations() },
  { key: 'about', label: '데이터와 방법론', href: routes.about() },
];

/** 업그레이드 탐색기 조건 링크: upgradesWith({ team: 'enstone', season: 2025 }) -> '/…/upgrades/#team=enstone&season=2025' */
export function upgradesWith(params: Record<string, string | number>): string {
  const q = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
  return `${routes.upgrades()}${q ? `#${q}` : ''}`;
}
