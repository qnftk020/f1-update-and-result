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
  teams: () => url('/teams/'),
  team: (lineageId: string) => url(`/teams/${lineageId}/`),
  upgrades: () => url('/upgrades/'),
  engines: () => url('/engines/'),
  regulations: () => url('/regulations/'),
  about: () => url('/about/'),
};
