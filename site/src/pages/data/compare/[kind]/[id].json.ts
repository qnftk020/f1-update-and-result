// 비교 화면이 받아 오는 자료 파일: /data/compare/d/<드라이버 ID>.json, /data/compare/c/<컨스트럭터 ID>.json.
// 모양은 lib/compare.ts의 CompareFile, 만드는 법은 lib/compare-data.ts에 있다.
import type { APIRoute, GetStaticPaths } from 'astro';
import { compareIds, constructorCompare, driverCompare } from '../../../../lib/compare-data.ts';

export const getStaticPaths: GetStaticPaths = () => [
  ...compareIds.d.map((id) => ({ params: { kind: 'd', id } })),
  ...compareIds.c.map((id) => ({ params: { kind: 'c', id } })),
];

export const GET: APIRoute = async ({ params }) => {
  const id = String(params.id);
  const file = params.kind === 'd' ? await driverCompare(id) : await constructorCompare(id);
  return new Response(JSON.stringify(file), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
};
