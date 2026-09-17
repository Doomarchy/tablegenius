export type ZoneKey = 'ucl' | 'ucl_qualifying' | 'uel' | 'uecl' | 'relegation_playoff' | 'relegation'

export interface Zone {
  label: string
  positions: [number, number] | null
}

export interface LeagueMeta {
  code: string
  name: string
  country: string
  season: string
  team_count: number
  rounds: number
  tiebreakers: string[]
  zones: Record<ZoneKey, Zone>
  assumptions: string[]
  domestic_cups: { name: string; grants: string }[]
  extra_ucl_place: boolean
  tied_title_playoff: boolean
  tied_relegation_playoff: boolean
}

export type FormResult = 'W' | 'D' | 'L'

export interface SplitRecord {
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  points: number
}

export interface TeamProbs {
  title: number
  ucl: number
  ucl_direct: number
  ucl_qualifying: number
  uel: number
  uecl: number
  europe: number
  relegation_playoff: number
  relegation: number
  expected_points: number
  expected_position: number
  points_p5: number
  points_p50: number
  points_p95: number
  max_points: number
  matches_remaining: number
  positions: number[]
  attack?: number
  defence?: number
}

export type OutcomeKey = 'title' | 'ucl' | 'europe' | 'relegation' | 'drop_zone'
export type Status = 'alive' | 'clinched' | 'eliminated'

export interface Scenario {
  outcome: OutcomeKey
  kind: 'clinch' | 'eliminate'
  text: string
}

export interface TeamRow {
  id: number | string
  name: string
  short_name: string
  tla: string | null
  crest: string | null
  position: number
  zone: ZoneKey | null
  played: number
  won: number
  drawn: number
  lost: number
  gf: number
  ga: number
  gd: number
  points: number
  form: FormResult[]
  home: SplitRecord
  away: SplitRecord
  tied: boolean
  separated_by: string | null
  probs?: TeamProbs | null
  status?: Partial<Record<OutcomeKey, Status>>
  magic?: Partial<Record<'title' | 'ucl' | 'europe' | 'safety', number | null>>
  remaining?: number
  scenarios?: Scenario[]
}

export interface MatchdayInfo {
  current: number | null
  total: number
  matches_played: number
  matches_total: number
}

export interface ModelInfo {
  as_of: string
  results_hash: string
  n_sims: number
  n_rating_draws: number
  fitted_matches: number
  effective_matches: number
  seasons: string[]
  home_advantage: number
  intercept: number
  avg_home_goals: number
  avg_away_goals: number
  rho: number
  xi: number
  half_life_days: number
  prior_strength: number
  promoted_prior: { attack: number; defence: number }
  promoted_teams: string[]
  fixtures_remaining: number
  converged: boolean
  runtime_seconds: number
}

export interface NextRound {
  matchday: number | null
  label: string
  fixtures: (number | string)[]
}

export interface Standings {
  league: LeagueMeta
  updated_at: string
  source: string
  matchday: MatchdayInfo
  model: ModelInfo | null
  next_round?: NextRound | null
  history?: { snapshots: number; updated_at: string } | null
  teams: TeamRow[]
  source_check: { available: boolean; totals_match?: boolean; diffs?: unknown[] }
}

export interface Forecast {
  home: number
  draw: number
  away: number
  xg_home: number
  xg_away: number
}

export interface MatchRecord {
  id: number | string
  utc_date: string
  matchday: number | null
  status: string
  home_id: number | string
  away_id: number | string
  home_goals: number | null
  away_goals: number | null
  forecast?: Forecast
}

export interface TeamInfo {
  id: number | string
  name: string
  short_name: string
  tla: string | null
  crest: string | null
}

export interface MatchesFile {
  league: string
  season: string
  updated_at: string
  teams: TeamInfo[]
  matches: MatchRecord[]
}

export interface SnapshotTeam {
  title: number
  ucl: number
  uel: number
  uecl: number
  europe: number
  relegation_playoff: number
  relegation: number
  expected_points: number
  expected_position: number
  position: number
  points: number
  played: number
  attack: number
  defence: number
}

export interface Snapshot {
  matchday: number
  label: string
  as_of: string
  complete: boolean
  teams: Record<string, SnapshotTeam>
}

export interface History {
  league: string
  season: string
  model_version: string
  updated_at: string
  total_matchdays: number
  snapshots: Snapshot[]
}

export interface IndexLeague {
  code: string
  name: string
  country: string
  updated_at: string
  matchday: MatchdayInfo
  source?: string
  has_probabilities?: boolean
  model_as_of?: string | null
  has_history?: boolean
}

export interface DataIndex {
  season: string
  updated_at: string
  has_backtest?: boolean
  leagues: IndexLeague[]
}

export interface Score {
  brier: number
  log_loss: number
  n: number
}

export interface Backtest {
  season: string
  leagues: string[]
  generated_at: string
  n_sims: number
  n_rating_draws?: number
  checkpoints: number[]
  model_params: {
    xi: number
    half_life_days: number
    prior_strength: number
    promoted_prior: { attack: number; defence: number }
  }
  outcome_scores: Record<string, { label: string; model: Score; no_ratings: Score; uniform: Score }>
  by_checkpoint: { fraction: number; model: Score; no_ratings: Score; uniform: Score }[]
  calibration: { bin: string; n: number; predicted: number; observed: number }[]
  match_scores: {
    model: Score | null
    bookmaker: Score | null
    uniform: Score
    n_with_bookmaker: number
  }
  skill_vs_uniform: number
  skill_vs_no_ratings: number
  summary: string[]
}
