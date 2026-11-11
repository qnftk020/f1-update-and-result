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
  } | null;
  race: { wet: boolean; laps: number | null } | null;
}

export interface RaceIndexPoint {
  v: number;
  lo: number | null;
  hi: number | null;
  n: number;
}

export interface DriverSeason extends PersonRef {
  constructor_ids: string[];
  constructors: string[];
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
  quali_index: (number | null)[] | null;
  race_index: (RaceIndexPoint | null)[] | null;
}

export interface Season {
  season: number;
  rounds: Round[];
  drivers: DriverSeason[];
  constructors: ConstructorSeason[];
  has_constructor_standings: boolean;
  has_quali_index: boolean;
  has_race_index: boolean;
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
}

export interface Team extends Omit<TeamSummary, 'since' | 'names'> {
  segments: TeamSegment[];
  evidence: TeamEvidence[];
  seasons: TeamSeasonRow[];
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
  drivers_top: (PersonRef & { constructors: string[]; position: number; final_points: number; wins: number })[];
  constructors_top: { id: string; name: string; lineage_id: string | null; position: number; final_points: number; wins: number }[];
}

export interface SourceInfo {
  name: string;
  url: string;
  license: string;
  version: string;
  as_of: string;
}

export interface Meta {
  generated_at: string;
  generated_on: string;
  first_season: number;
  last_season: number;
  last_race: { season: number; round: number; name: string; name_ko: string; date: string };
  sources: Record<'jolpica' | 'f1db' | 'openf1' | 'fia', SourceInfo>;
  counts: Record<string, number>;
  available: string[];
}

export interface Labels {
  component_areas: Record<string, string>;
  reason_categories: Record<ReasonCategory, string>;
  link_types: Record<string, string>;
  quali_formats: Record<string, string>;
  grand_prix: Record<string, { ko: string; short: string }>;
}
