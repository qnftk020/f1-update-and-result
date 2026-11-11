// 다른 쪽(시즌, 팀)의 드라이버 이름을 드라이버 쪽(/drivers/<id>/)으로 잇는다.
// 드라이버 쪽은 drivers.json의 행마다 하나씩 빌드된다(pages/drivers/[id].astro). 같은 목록으로 링크 여부를
// 정해, 생성 폴더에 낡은 driver/<id>.json이 남아 있어도 빌드되지 않는 쪽으로 링크하지 않는다. 빌드 때만 쓴다.
import { driverById } from './drivers-data.ts';
import { routes } from './paths.ts';

export function hasDriverPage(id: string | null | undefined): boolean {
  return Boolean(id) && driverById.has(id as string);
}

/** html은 이미 esc()를 거친 이름 조각이다. */
export function driverLink(id: string | null | undefined, html: string): string {
  return hasDriverPage(id) ? `<a href="${routes.driver(id as string)}">${html}</a>` : html;
}
