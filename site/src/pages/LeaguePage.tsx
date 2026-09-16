import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { loadStandings } from '../api'
import LeagueTable from '../components/LeagueTable'
import ZoneLegend from '../components/ZoneLegend'
import { formatUpdated } from '../format'
import type { DataIndex, Standings } from '../types'

function describeCriterion(c: string): string {
  return c.replaceAll('h2h', 'head-to-head').replaceAll('_', ' ')
}

export default function LeaguePage({ index }: { index: DataIndex }) {
  const { code = '' } = useParams()
  const [standings, setStandings] = useState<Standings | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setStandings(null)
    setError(null)
    loadStandings(index.season, code).then(setStandings).catch((e: Error) => setError(e.message))
  }, [index.season, code])

  useEffect(() => {
    const league = index.leagues.find((l) => l.code === code)
    document.title = league ? `${league.name} table · TableGenius` : 'TableGenius'
  }, [index, code])

  if (error) return <p className="notice error">{error}</p>
  if (!standings) return <p className="notice">Loading table…</p>

  const { league, matchday } = standings
  return (
    <section>
      <div className="league-head">
        <h1>{league.name}</h1>
        <p className="league-sub">
          {league.country} · {league.season}
          {matchday.current !== null && ` · Matchday ${matchday.current} of ${matchday.total}`}
          {` · ${matchday.matches_played}/${matchday.matches_total} matches played`}
        </p>
      </div>
      <LeagueTable standings={standings} />
      <ZoneLegend league={league} />
      {standings.source_check.available && standings.source_check.totals_match === false && (
        <p className="notice error">Warning: computed totals differ from the data provider. Check the pipeline logs.</p>
      )}
      <details className="assumptions">
        <summary>Rules and assumptions for this league</summary>
        <ul>
          <li>Tiebreakers, in order: {league.tiebreakers.map(describeCriterion).join(', ')}.</li>
          {league.assumptions.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </details>
      <p className="muted small">
        Data: {standings.source}. Updated {formatUpdated(standings.updated_at)}.
      </p>
    </section>
  )
}
