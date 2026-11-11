// 차트 모듈의 브라우저 진입점. BaseLayout이 페이지에 figure.fig가 있으면 이 모듈을 동적으로 불러
// mountAll()을 부른다. 페이지는 마크업과 JSON만 내보내면 된다(Figure 컴포넌트가 만든다):
//
//   <figure class="fig" id="f-quali">
//     ...
//     <div class="viz" data-chart="qualifyingRank" data-chart-opts='{"label":"..."}'></div>
//     <script type="application/json" class="chart-data">[...]</script>
//     <div class="twin">정적 표</div>
//   </figure>
//
// data-chart가 있는 .viz는 자동으로 그린다. 조작에 따라 다시 그리거나 onSelect 같은 함수 옵션이 필요한
// 차트는 페이지 스크립트가 ready를 기다려 handles에서 손잡이를 받아 redraw()하거나, data-chart 없이
// 둔 .viz에 mount()를 직접 부른다.
import * as charts from './charts.js';
import { puTeamSteps } from '../../components/engines/pu-charts.js';
import { figureFallback, initFigures, mount } from './core.js';

export * from './core.js';
export * from './charts.js';
export * from './items.js';

export interface ChartHandle {
  /** 자료나 옵션을 바꿔 다시 그린다. data가 null이면 자료는 그대로다. 초점과 읽던 자리는 유지된다. */
  redraw: (data?: unknown, opts?: Record<string, unknown>) => void;
}

/** data-chart 값으로 쓸 수 있는 차트 함수 이름 */
export const REGISTRY = {
  qualifyingRank: charts.qualifyingRank,
  raceIntervals: charts.raceIntervals,
  gridToFinish: charts.gridToFinish,
  roundCounts: charts.roundCounts,
  upgradeUnits: charts.upgradeUnits,
  paceTrend: charts.paceTrend,
  raceTrend: charts.raceTrend,
  seasonTrend: charts.seasonTrend,
  standingsSteps: charts.standingsSteps,
  pointsRace: charts.pointsRace,
  paceMultiples: charts.paceMultiples,
  // reasonShare는 width를 쓰지 않지만 mount()로 그리면 칸 너비가 바뀔 때 함께 다시 그린다.
  reasonShare: (data: unknown, opts: Record<string, unknown>) => charts.reasonShare(data, opts),
  groupedReasons: charts.groupedReasons,
  puSteps: charts.puSteps,
  // 팀 페이지 PU 절: 엔진 페이지와 같은 계단선(약어 끝 라벨, 겹침 시 세로 밀기, 허용 개수 선, 미수집 라운드).
  // 허용 개수는 구성요소마다 달라 opts.allowedBy[element]에서 고른다.
  puTeamSteps: (data: unknown, opts: Record<string, any>) =>
    puTeamSteps(data, { ...opts, allowed: opts.allowedBy?.[opts.element] ?? null }),
  newIce: charts.newIce,
} as const;

export type ChartName = keyof typeof REGISTRY;

/** 그린 차트의 손잡이. 키는 figure의 id(없으면 .viz의 id)다. */
export const handles = new Map<string, ChartHandle>();

let resolveReady: (h: Map<string, ChartHandle>) => void = () => {};
/** mountAll()이 끝나면 풀린다. 페이지 스크립트는 여기서 손잡이를 받는다. */
export const ready: Promise<Map<string, ChartHandle>> = new Promise((r) => {
  resolveReady = r;
});

/** id로 <script type="application/json">을 읽는다. 페이지 전체 자료(JsonData 컴포넌트)에 쓴다. */
export function readJson<T = unknown>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`JSON 자료가 없다: #${id}`);
  return JSON.parse(node.textContent || 'null') as T;
}

function dataFor(viz: HTMLElement): unknown {
  const ref = viz.dataset.chartData;
  if (ref) return readJson(ref);
  const fig = viz.closest('figure.fig');
  const node = fig?.querySelector<HTMLScriptElement>('script.chart-data');
  if (!node) throw new Error('차트 자료(script.chart-data)가 없다');
  return JSON.parse(node.textContent || 'null');
}

let mounted = false;

/** 차트/표 전환을 잇고 data-chart가 있는 그림을 모두 그린다. 한 번만 돈다. */
export function mountAll(root: Document | HTMLElement = document): Map<string, ChartHandle> {
  if (mounted) return handles;
  mounted = true;
  initFigures(root);
  root.querySelectorAll<HTMLElement>('.viz[data-chart]').forEach((viz) => {
    try {
      const name = viz.dataset.chart as ChartName;
      const fn = REGISTRY[name];
      if (!fn) throw new Error(`알 수 없는 차트 함수: ${name}`);
      const opts = viz.dataset.chartOpts ? JSON.parse(viz.dataset.chartOpts) : {};
      const handle = mount(viz, fn, dataFor(viz), opts) as ChartHandle;
      const key = viz.closest('figure.fig')?.id || viz.id;
      if (key) handles.set(key, handle);
    } catch (err) {
      figureFallback(viz, err);
    }
  });
  resolveReady(handles);
  return handles;
}
