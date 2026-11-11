// pipeline/build_site_data.py 가 만드는 JSON의 모양. 내보내기 코드를 바꾸면 여기도 함께 고친다.

export interface PersonRef {
  id: string;
  name: string;
  code: string | null;
}

export interface EntryRef extends PersonRef {
  constructor_id: string;
  constructor: string;
}

export interface PuRef {
  id: string;
  name: string;
}

export type WetFlag = 'wet' | 'dry' | 'unclassified';

export interface Round {
  round: number;
  name: string;
  name_ko: string;
  short_ko: string;
  date: string;
  circuit: string;
  locality: string;
  country: string;
  has_sprint: boolean;
  winners: EntryRef[];
  pole: EntryRef[];
  quali: {
    format: string;
    format_ko: string;
    reference: boolean;
    wet: WetFlag;
    source: string;
    best_ms: number | null;
    /** 그 대회 필드(지수가 있는 모든 팀)의 사분위. 팀이 넷 미만이면 null. 소수 아홉째 자리. */
    field: Quartiles | null;
    /** 지수가 있는 팀 수 */
    teams: number;
  } | null;
  race: { wet: boolean; laps: number | null } | null;
}

export interface Quartiles {
  q1: number;
  med: number;
  q3: number;
}

/** 레이스 지수 한 점. 값은 소수 여섯째 자리(원자료가 넷째 자리라 사실상 넷째 자리)다. */
export interface RaceIndexPoint {
  v: number;
  lo: number | null;
  hi: number | null;
  n: number;
}

export interface DriverSeason extends PersonRef {
  constructor_ids: string[];
  constructors: string[];
  /** 마지막으로 결승에 나간 팀 이름 */
  team: string | null;
  position: number | null;
  final_points: number | null;
  wins: number;
  positions: (number | null)[];
  points: (number | null)[];
}

export interface ConstructorSeason {
  id: string;
  name: string;
  lineage_id: string | null;
  pu: PuRef | null;
  position: number | null;
  final_points: number | null;
  wins: number | null;
  positions: (number | null)[] | null;
  points: (number | null)[] | null;
  /** 라운드 순서의 퀄리파잉 지수(%), ms 기록에서 다시 계산한 소수 아홉째 자리 값 */
  quali_index: (number | null)[] | null;
  race_index: (RaceIndexPoint | null)[] | null;
  /** 우천 예선(2023년부터)을 뺀 예선의 평균. 2022년 이전은 미분류라 모든 예선이 들어간다. */
  quali_mean: number | null;
  quali_n: number;
  /** 우천 결승을 뺀 레이스 지수 평균 */
  race_mean: number | null;
  race_n: number;
}

export interface LeadChange {
  /** 순위표 1위가 마지막으로 바뀐 라운드(바뀐 적이 없으면 첫 라운드) */
  round: number;
  leader_id: string;
  first_round: number;
}

export interface SeasonFacts {
  races: number;
  /** 스프린트가 열린 라운드 번호 */
  sprints: number[];
  /** 우승한 드라이버 수 */
  winners: number;
  quali_rounds: number;
  quali_wet: number[];
  quali_unclassified: number[];
  quali_reference: number[];
  /** 참고용 예선 형식의 한국어 이름(원랩, 합산) */
  quali_reference_formats: string[];
  race_index_rounds: number;
  race_wet: number[];
  driver_lead: LeadChange | null;
  constructor_lead: LeadChange | null;
}

export interface Season {
  season: number;
  rounds: Round[];
  drivers: DriverSeason[];
  constructors: ConstructorSeason[];
  has_constructor_standings: boolean;
  has_quali_index: boolean;
  has_race_index: boolean;
  facts: SeasonFacts;
}

export interface SeasonSummary {
  season: number;
  rounds: number;
  champion_driver: { id: string; name: string; constructors: string[]; final_points: number } | null;
  champion_constructor: { id: string; name: string; final_points: number } | null;
  has_quali_index: boolean;
  has_race_index: boolean;
}

export interface TeamSegment {
  constructor_id: string;
  team_name: string;
  from: number;
  to: number;
  link_type: string;
  link_type_ko: string;
  note: string | null;
}

export interface TeamEvidence {
  constructor_id: string;
  season_from: number;
  kind: string;
  url: string;
  quote: string;
  verified_on: string;
}

export interface TeamSeasonRow {
  season: number;
  constructor_id: string;
  team_name: string;
  entrant: string | null;
  pu: PuRef | null;
  position: number | null;
  points: number | null;
  wins: number | null;
  races: number;
  quali_index_median: number | null;
  quali_rounds: number;
  quali_rounds_all: number;
  quali_wet_unclassified: boolean;
  quali_reference: boolean;
  race_index_median: number | null;
  race_rounds: number;
  /** 시즌 평균 퀄리파잉 지수(마른 예선, 2022년 이전은 미분류 포함). 화면은 이 값을 쓴다. */
  quali_index_mean: number | null;
  quali_wet_rounds: number;
  /** 그 시즌 필드(예선 절반 이상에 지수가 있는 팀들)의 시즌 평균 사분위 */
  quali_field: Quartiles | null;
  /** 필드 가운데 평균이 작은 순서(1이 가장 빠름) */
  quali_rank: number | null;
  quali_teams: number;
  /** 결승 출전 대회 수 */
  entered: number;
  /** 결승 우승 수(결과에서 센 값) */
  race_wins: number;
  podiums: number;
}

export interface LineageTotals {
  seasons: number;
  races: number;
  wins: number;
  podiums: number;
  best_position: number | null;
  titles: number[];
}

export type TeamRoundStatus = 'updates' | 'no_updates' | 'needs_review' | 'nodoc';

export interface TimelineRound {
  round: number;
  short: string;
  name: string;
  status: TeamRoundStatus;
  doc_review: boolean;
  url: string | null;
  published_at: string | null;
  cats: Record<ReasonCategory, number>;
  n: number;
}

export interface TeamSummary {
  lineage_id: string;
  name_ko: string;
  base: string;
  constructor: { id: string; name: string };
  entrant: string | null;
  pu: PuRef | null;
  since: number;
  names: string[];
  segments_n: number;
  last: { position: number | null; points: number | null; quali_index_mean: number | null; quali_rank: number | null } | null;
  upgrade_items: number;
}

export interface Team extends Omit<TeamSummary, 'since' | 'names' | 'segments_n' | 'last' | 'upgrade_items'> {
  segments: TeamSegment[];
  evidence: TeamEvidence[];
  seasons: TeamSeasonRow[];
  /** 마지막 계보 구간(현재 컨스트럭터)의 첫 시즌. 계보 보기를 끈 범위 */
  current_from: number;
  totals: LineageTotals;
  totals_current: LineageTotals;
  /** 마지막 시즌에 현재 컨스트럭터로 결승에 나간 드라이버(처음 나간 순서) */
  drivers_last: PersonRef[];
  upgrades: {
    items: number;
    events: number;
    by_category: Record<ReasonCategory, number>;
    /** 시즌(문자열 키) -> 라운드 순서의 상태 */
    timeline: Record<string, TimelineRound[]>;
  };
}

export type ReasonCategory = 'performance' | 'circuit_specific' | 'reliability' | 'other';

export interface UpgradeItem {
  season: number;
  round: number;
  event: string;
  event_ko: string;
  event_short_ko: string;
  constructor_id: string;
  team: string;
  lineage_id: string | null;
  no: string;
  no_inferred: boolean;
  component: string;
  area: string;
  reason: string;
  category: ReasonCategory;
  category_inferred: boolean;
  detail: string;
  geometry: string;
  description: string;
  description_shared: boolean;
  review: boolean;
  url: string;
}

export interface UpgradeTeamStatus {
  constructor_id: string;
  team: string;
  lineage_id: string | null;
  status: 'updates' | 'no_updates' | 'needs_review';
  items: number;
  page: number;
}

export interface UpgradeDocument {
  season: number;
  round: number;
  event: string;
  event_ko: string;
  event_short_ko: string;
  published_at: string | null;
  url: string;
  items: number;
  review: boolean;
  problems: string | null;
  teams: UpgradeTeamStatus[];
}

export interface Upgrades {
  items: UpgradeItem[];
  documents: UpgradeDocument[];
  missing_events: { season: number; round: number; event: string; event_ko: string; event_short_ko: string }[];
}

export interface ClassificationRow extends PersonRef {
  position: number | null;
  classified: boolean;
  number: number | null;
  constructor_id: string;
  constructor: string;
  lineage_id: string | null;
  grid: number | null;
  laps: number | null;
  time: string | null;
  status: string;
  points: number | null;
  fastest_lap: boolean;
}

export interface UpgradeWeekend {
  season: number;
  round: number;
  event: string;
  event_ko: string;
  event_short_ko: string;
  url: string;
  items: number;
  review: boolean;
  published_at: string | null;
  teams: UpgradeTeamStatus[];
  list: UpgradeItem[];
}

export interface Home {
  season: number;
  race: Round;
  classification: ClassificationRow[];
  session_best: (PersonRef & { constructor: string; session: string; time: string }) | null;
  pace: {
    constructor_id: string;
    constructor: string;
    lineage_id: string | null;
    quali: number | null;
    race: RaceIndexPoint | null;
  }[];
  upgrades_this_weekend: UpgradeWeekend | null;
  upgrades_latest: UpgradeWeekend | null;
  /** 순위표 기준 라운드(이 대회 종료 뒤) */
  standings_round: number;
  drivers: (PersonRef & { team: string | null; position: number; points: number; wins: number })[];
  constructors: { id: string; name: string; lineage_id: string | null; position: number; points: number; wins: number }[];
  /** 빠른 순. v는 ms에서 다시 계산한 지수, gap_s는 세션 최고 랩과의 차이(초) */
  quali: HomeQuali[];
  quali_meta: {
    wet: WetFlag;
    reference: boolean;
    format: string;
    source: string;
    session_best_ms: number;
    session_best: string;
  } | null;
  /** 빠른 순(v가 null인 팀은 끝) */
  race_index: HomeRace[];
  race_meta: { wet: boolean; laps: number | null } | null;
  pole: (EntryRef & { session: string | null; time: string | null }) | null;
  /** 결승 패스티스트 랩. 시각과 랩 번호는 OpenF1 랩에서 읽는다(2023년부터) */
  fastest_lap: (EntryRef & { lap: number; time: string; source: 'openf1' }) | null;
  rounds_in_season: number;
  /** 그 시즌 Car Presentation 문서가 있는 라운드별 항목 수. 없는 라운드는 문서 부재다 */
  round_counts: { round: number; name_ko: string; short_ko: string; n: number; review: boolean }[];
}

export interface HomeQuali {
  constructor_id: string;
  constructor: string;
  lineage_id: string | null;
  v: number | null;
  gap_s: number | null;
  team_best_ms: number | null;
}

export interface HomeRace {
  constructor_id: string;
  constructor: string;
  lineage_id: string | null;
  v: number | null;
  lo: number | null;
  hi: number | null;
  laps: number | null;
}

export interface SourceInfo {
  name: string;
  url: string;
  license: string;
  version: string;
  /** 수집일(KST). 페이스 지수는 계산일 */
  as_of: string;
  /** Jolpica만: 덤프 날짜와 API로 더 반영한 범위 */
  dump?: string;
  api?: string | null;
}

export interface ReviewDocument {
  season: number;
  round: number;
  event: string;
  event_ko: string;
  event_short_ko: string;
  url: string;
}

export interface Meta {
  generated_at: string;
  generated_on: string;
  first_season: number;
  last_season: number;
  last_race: { season: number; round: number; name: string; name_ko: string; date: string };
  sources: Record<'jolpica' | 'f1db' | 'openf1' | 'fia' | 'pace', SourceInfo>;
  /** 검수 대기 Car Presentation 문서 */
  review_documents: ReviewDocument[];
  counts: Record<string, number>;
  available: string[];
}

export interface Labels {
  component_areas: Record<string, string>;
  reason_categories: Record<ReasonCategory, string>;
  category_order: ReasonCategory[];
  team_status: Record<TeamRoundStatus, string>;
  link_types: Record<string, string>;
  quali_formats: Record<string, string>;
  grand_prix: Record<string, { ko: string; short: string }>;
}
