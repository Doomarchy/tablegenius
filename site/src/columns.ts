import type { LeagueMeta, TeamRow } from './types'

export type ColumnGroup = 'core' | 'std' | 'prob' | 'exp'

/** Ink used for a probability bar: scarlet for the European end, black for the drop. */
export type BarInk = 'scarlet' | 'ink' | 'ink-soft'

export interface Column {
  key: string
  label: string
  /** Short explanation shown as a tooltip and in the column guide. */
  description: string
  group: ColumnGroup
  ink?: BarInk
  /** Footnote number shown as a superscript after the label. */
  note?: number
  /** Sort ascending by default (positions); everything else sorts descending. */
  ascending?: boolean
  value: (t: TeamRow) => number | null
  /** Probability columns are rendered as a figure with an ink bar. */
  kind: 'int' | 'signed' | 'prob' | 'dec1'
}

export interface Footnote {
  n: number
  text: string
}

const prob = (f: (p: NonNullable<TeamRow['probs']>) => number) => (t: TeamRow) => (t.probs ? f(t.probs) : null)

function range(p: [number, number]) {
  return p[0] === p[1] ? `${p[0]}` : `${p[0]}–${p[1]}`
}

export function buildFootnotes(league: LeagueMeta, rules?: { cups: { name: string; winner: string | null }[]; extra_ucl_probability: number } | null): Footnote[] {
  const notes: Footnote[] = []
  if (league.zones.uel?.positions) {
    const decided = (rules?.cups ?? []).filter((c) => c.winner)
    const undecided = (rules?.cups ?? []).filter((c) => !c.winner)
    let text = 'Cup winners’ European places are assumed to pass down the table.'
    if (decided.length) {
      text = decided.map((c) => `${c.name}: ${c.winner}`).join('; ') + (undecided.length ? `; ${undecided.map((c) => c.name).join(' and ')} undecided (assumed to pass down)` : '') + '. Chances account for where the cup winner finishes.'
    }
    if (rules && rules.extra_ucl_probability > 0) {
      text += ` An extra Champions League place is included with a ${Math.round(rules.extra_ucl_probability * 100)}% chance.`
    }
    notes.push({ n: 1, text })
  }
  if (league.zones.ucl_qualifying?.positions) {
    notes.push({ n: 2, text: `Includes position ${range(league.zones.ucl_qualifying.positions)}, which enters the Champions League qualifying rounds rather than the league phase.` })
  }
  return notes
}

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

  const ucl = z.ucl.positions!
  const uel = z.uel.positions!
  const uecl = z.uecl.positions!
  const hasQ = !!z.ucl_qualifying?.positions

  cols.push(
    { key: 'title', label: 'Title', description: 'Chance of finishing 1st and winning the league', group: 'prob', ink: 'scarlet', value: prob((p) => p.title), kind: 'prob' },
    { key: 'ucl', label: 'UCL', description: `Chance of a Champions League place (positions ${range(ucl)}${hasQ ? ` plus ${range(z.ucl_qualifying.positions!)}, which enters the qualifying rounds` : ''})`, group: 'prob', ink: 'scarlet', note: hasQ ? 2 : undefined, value: prob((p) => p.ucl), kind: 'prob' },
    { key: 'uel', label: 'UEL', description: `Chance of a Europa League place (positions ${range(uel)}, assuming the cup winner's place passes down the table)`, group: 'prob', ink: 'scarlet', note: 1, value: prob((p) => p.uel), kind: 'prob' },
    { key: 'uecl', label: 'UECL', description: `Chance of the Conference League play-off place (position ${range(uecl)})`, group: 'prob', ink: 'scarlet', note: 1, value: prob((p) => p.uecl), kind: 'prob' },
    { key: 'europe', label: 'Europe', description: 'Chance of any UEFA competition: Champions League, Europa League or Conference League', group: 'prob', ink: 'scarlet', value: prob((p) => p.europe), kind: 'prob' },
  )
  if (z.relegation_playoff?.positions) {
    cols.push({ key: 'relegation_playoff', label: 'Play-off', description: `Chance of finishing ${range(z.relegation_playoff.positions)} and entering the relegation play-off. Combined with automatic relegation and the historical survival rate, the overall relegation risk is shown on the team page.`, group: 'prob', ink: 'ink-soft', value: prob((p) => p.relegation_playoff), kind: 'prob' })
  }
  cols.push(
    { key: 'relegation', label: 'Rel.', description: `Chance of automatic relegation (positions ${range(z.relegation.positions!)})`, group: 'prob', ink: 'ink', value: prob((p) => p.relegation), kind: 'prob' },
    { key: 'expected_points', label: 'xPts', description: 'Expected final points: the average over all simulated seasons', group: 'exp', value: prob((p) => p.expected_points), kind: 'dec1' },
    { key: 'expected_position', label: 'xPos', description: 'Expected final position: the average over all simulated seasons', group: 'exp', ascending: true, value: prob((p) => p.expected_position), kind: 'dec1' },
  )
  return cols
}
