import type { LeagueMeta, TeamRow, ZoneKey } from './types'

export type ColumnGroup = 'core' | 'std' | 'prob' | 'exp'

export interface Column {
  key: string
  label: string
  /** Short explanation shown as a tooltip and in the column guide. */
  description: string
  group: ColumnGroup
  /** Zone hue used to shade probability cells. */
  hue?: ZoneKey
  /** Sort ascending by default (positions); everything else sorts descending. */
  ascending?: boolean
  value: (t: TeamRow) => number | null
  /** Probability columns are rendered as shaded percentages. */
  kind: 'int' | 'signed' | 'prob' | 'dec1'
}

const prob = (f: (p: NonNullable<TeamRow['probs']>) => number) => (t: TeamRow) => (t.probs ? f(t.probs) : null)

export function buildColumns(league: LeagueMeta, hasProbs: boolean): Column[] {
  const z = league.zones
  const cols: Column[] = [
    { key: 'played', label: 'P', description: 'Matches played', group: 'core', value: (t) => t.played, kind: 'int' },
    { key: 'won', label: 'W', description: 'Matches won', group: 'std', value: (t) => t.won, kind: 'int' },
    { key: 'drawn', label: 'D', description: 'Matches drawn', group: 'std', value: (t) => t.drawn, kind: 'int' },
    { key: 'lost', label: 'L', description: 'Matches lost', group: 'std', value: (t) => t.lost, kind: 'int' },
    { key: 'gf', label: 'GF', description: 'Goals scored', group: 'std', value: (t) => t.gf, kind: 'int' },
    { key: 'ga', label: 'GA', description: 'Goals conceded', group: 'std', value: (t) => t.ga, kind: 'int' },
    { key: 'gd', label: 'GD', description: 'Goal difference', group: 'std', value: (t) => t.gd, kind: 'signed' },
    { key: 'points', label: 'Pts', description: 'Points', group: 'core', value: (t) => t.points, kind: 'int' },
  ]
  if (!hasProbs) return cols

  const uclNote = z.ucl_qualifying?.positions
    ? ` Includes ${z.ucl_qualifying.positions[0] === z.ucl_qualifying.positions[1] ? `${z.ucl_qualifying.positions[0]}th` : 'the qualifying'} place, which enters the qualifying rounds rather than the league phase.`
    : ''
  const ucl = z.ucl.positions!
  const uel = z.uel.positions!
  const uecl = z.uecl.positions!
  const range = (p: [number, number]) => (p[0] === p[1] ? `${p[0]}` : `${p[0]}–${p[1]}`)

  cols.push(
    { key: 'title', label: 'Title', description: 'Chance of finishing 1st and winning the league', group: 'prob', hue: 'ucl', value: prob((p) => p.title), kind: 'prob' },
    { key: 'ucl', label: 'UCL', description: `Chance of a Champions League place (positions ${range(ucl)}${z.ucl_qualifying?.positions ? ` plus ${range(z.ucl_qualifying.positions)}` : ''}).${uclNote}`, group: 'prob', hue: 'ucl', value: prob((p) => p.ucl), kind: 'prob' },
    { key: 'uel', label: 'UEL', description: `Chance of a Europa League place (positions ${range(uel)}, assuming the cup winner's place passes down the table)`, group: 'prob', hue: 'uel', value: prob((p) => p.uel), kind: 'prob' },
    { key: 'uecl', label: 'UECL', description: `Chance of the Conference League play-off place (position ${range(uecl)})`, group: 'prob', hue: 'uecl', value: prob((p) => p.uecl), kind: 'prob' },
    { key: 'europe', label: 'Europe', description: 'Chance of any UEFA competition: Champions League, Europa League or Conference League', group: 'prob', hue: 'ucl', value: prob((p) => p.europe), kind: 'prob' },
  )
  if (z.relegation_playoff?.positions) {
    cols.push({ key: 'relegation_playoff', label: 'Play-off', description: `Chance of finishing ${range(z.relegation_playoff.positions)} and entering the relegation play-off (the play-off itself is not simulated)`, group: 'prob', hue: 'relegation_playoff', value: prob((p) => p.relegation_playoff), kind: 'prob' })
  }
  cols.push(
    { key: 'relegation', label: 'Rel.', description: `Chance of automatic relegation (positions ${range(z.relegation.positions!)})`, group: 'prob', hue: 'relegation', value: prob((p) => p.relegation), kind: 'prob' },
    { key: 'expected_points', label: 'xPts', description: 'Expected final points: the average over all simulated seasons', group: 'exp', value: prob((p) => p.expected_points), kind: 'dec1' },
    { key: 'expected_position', label: 'xPos', description: 'Expected final position: the average over all simulated seasons', group: 'exp', ascending: true, value: prob((p) => p.expected_position), kind: 'dec1' },
  )
  return cols
}
