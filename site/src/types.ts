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
}

export interface MatchdayInfo {
  current: number | null
  total: number
  matches_played: number
  matches_total: number
}

export interface Standings {
  league: LeagueMeta
  updated_at: string
  source: string
  matchday: MatchdayInfo
  teams: TeamRow[]
  source_check: { available: boolean; totals_match?: boolean; diffs?: unknown[] }
}

export interface IndexLeague {
  code: string
  name: string
  country: string
  updated_at: string
  matchday: MatchdayInfo
  source?: string
}

export interface DataIndex {
  season: string
  updated_at: string
  leagues: IndexLeague[]
}
