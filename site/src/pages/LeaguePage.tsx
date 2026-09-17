import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { loadStandings } from '../api'
import { buildColumns, buildFootnotes } from '../columns'
import ColumnGuide from '../components/ColumnGuide'
import LeagueTable, { type TableView } from '../components/LeagueTable'
import ZoneLegend from '../components/ZoneLegend'
import { formatUpdated } from '../format'
import type { DataIndex, Standings } from '../types'

function describeCriterion(c: string): string {
  return c.replaceAll('h2h', 'head-to-head').replaceAll('_', ' ')
}

function initialView(): TableView {
  try {
    const saved = localStorage.getItem('tg-view') as TableView | null
    if (saved === 'table' || saved === 'chances' || saved === 'both') return saved
  } catch {
    /* ignore */
  }
  return window.matchMedia('(max-width: 720px)').matches ? 'chances' : 'both'
}

const VIEWS: { key: TableView; label: string }[] = [
  { key: 'table', label: 'Table' },
  { key: 'chances', label: 'Chances' },
  { key: 'both', label: 'Both' },
]

export default function LeaguePage({ index }: { index: DataIndex }) {
  const { code = '' } = useParams()
  const [standings, setStandings] = useState<Standings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<TableView>(initialView)

  useEffect(() => {
    setStandings(null)
    setError(null)
    loadStandings(index.season, code).then(setStandings).catch((e: Error) => setError(e.message))
  }, [index.season, code])

  useEffect(() => {
    const league = index.leagues.find((l) => l.code === code)
    document.title = league ? `${league.name} table · TableGenius` : 'TableGenius'
  }, [index, code])

  const chooseView = (v: TableView) => {
    setView(v)
    try {
      localStorage.setItem('tg-view', v)
    } catch {
      /* ignore */
    }
  }

  const hasProbs = !!standings?.model && standings.teams.some((t) => t.probs)
  const columns = useMemo(() => (standings ? buildColumns(standings.league, hasProbs) : []), [standings, hasProbs])
  const footnotes = useMemo(() => (standings && hasProbs ? buildFootnotes(standings.league, standings.rules) : []), [standings, hasProbs])

  if (error) return <p className="notice error">{error}</p>
  if (!standings) return <p className="notice">Loading table…</p>

  const { league, matchday, model } = standings
  return (
    <section>
      <div className="band">
        <h1>{league.name}</h1>
        {hasProbs && (
          <div className="view-switch" role="group" aria-label="Columns to show">
            {VIEWS.map((v) => (
              <button key={v.key} type="button" className={`seg${view === v.key ? ' active' : ''}`} onClick={() => chooseView(v.key)} aria-pressed={view === v.key}>
                {v.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="meta">
        <span>{league.country} · {league.season}</span>
        {matchday.current !== null && <span>Matchday <b>{matchday.current}</b> of {matchday.total}</span>}
        <span><b>{matchday.matches_played}</b>/{matchday.matches_total} played</span>
        {hasProbs && model && <span>n = <b>{model.n_sims.toLocaleString()}</b> seasons × {model.n_rating_draws} rating sets</span>}
        <span>Updated <b>{formatUpdated(standings.updated_at)}</b></span>
      </p>
      <LeagueTable standings={standings} view={hasProbs ? view : 'table'} />
      {footnotes.length > 0 && (
        <p className="footnotes">
          {footnotes.map((f) => (
            <span key={f.n}><sup>{f.n}</sup> {f.text}</span>
          ))}
          {hasProbs && <span>✓ settled · ✗ out of reach, on points alone. Click a club for its season page.</span>}
          {standings.rules?.deductions?.length ? (
            <span>* Points deducted: {standings.rules.deductions.map((d) => `${d.team} ${d.points}${d.reason ? ` (${d.reason})` : ''}`).join(', ')}.</span>
          ) : null}
        </p>
      )}
      <ZoneLegend league={league} />
      {hasProbs && standings.next_round && standings.next_round.matchday !== null && (
        <div className="round-box">
          <h2>{standings.next_round.label === 'this weekend' ? 'This weekend' : 'This midweek'}: what could be settled</h2>
          {standings.teams.some((t) => (t.scenarios ?? []).length > 0) ? (
            <ul className="scenario-list">
              {standings.teams.flatMap((t) =>
                (t.scenarios ?? []).map((s, i) => (
                  <li key={`${t.id}-${i}`} className={s.kind === 'clinch' ? 'good' : 'bad'}>
                    <Link to={`/league/${league.code}/team/${t.id}`}>{t.short_name}</Link>: {s.text.charAt(0).toLowerCase() + s.text.slice(1)}
                  </li>
                )),
              )}
            </ul>
          ) : (
            <p className="muted">Matchday {standings.next_round.matchday}: nothing can be mathematically settled yet. Settled outcomes are decided on points alone, treating ties conservatively.</p>
          )}
        </div>
      )}
      {standings.source_check.available && standings.source_check.totals_match === false && (
        <p className="notice error">Warning: computed totals differ from the data provider. Check the pipeline logs.</p>
      )}
      {hasProbs && model && (
        <p className="muted small model-line">
          Chances from {model.n_sims.toLocaleString()} simulated seasons, ratings fitted on {model.fitted_matches.toLocaleString()} matches as of{' '}
          {new Date(model.as_of).toLocaleDateString(undefined, { dateStyle: 'medium' })}. <Link to="/about">How the model works</Link>.
        </p>
      )}
      <ColumnGuide columns={columns} hasProbs={hasProbs} />
      <details className="assumptions">
        <summary>Rules and assumptions for this league</summary>
        <ul>
          <li>Tiebreakers, in order: {league.tiebreakers.map(describeCriterion).join(', ')}.</li>
          {league.assumptions.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </details>
      <p className="muted small">Data: {standings.source}.</p>
    </section>
  )
}
