import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { loadHistory, loadMatches, loadStandings } from '../api'
import { ChancesChart, PositionChart, PositionHistoryChart, ordinal } from '../components/charts'
import Form from '../components/Form'
import { formatPct, signed } from '../format'
import type { DataIndex, History, MatchRecord, MatchesFile, OutcomeKey, Standings, TeamRow } from '../types'

const OUTCOMES: { key: OutcomeKey; label: string }[] = [
  { key: 'title', label: 'Title' },
  { key: 'ucl', label: 'Champions League' },
  { key: 'europe', label: 'Europe' },
  { key: 'drop_zone', label: 'Relegation risk' },
  { key: 'relegation', label: 'Relegation' },
]

function probFor(row: TeamRow, key: OutcomeKey): number | null {
  const p = row.probs
  if (!p) return null
  switch (key) {
    case 'title':
      return p.title
    case 'ucl':
      return p.ucl
    case 'europe':
      return p.europe
    case 'relegation':
      return p.relegation
    case 'drop_zone':
      return p.relegation_total ?? p.relegation + p.relegation_playoff
  }
}

function StatusChips({ row, hasPlayoff }: { row: TeamRow; hasPlayoff: boolean }) {
  return (
    <ul className="chips" aria-label="Season status">
      {OUTCOMES.filter((o) => o.key !== 'drop_zone' || hasPlayoff).map((o) => {
        const st = row.status?.[o.key] ?? 'alive'
        const p = probFor(row, o.key)
        const negative = o.key === 'relegation' || o.key === 'drop_zone'
        let word: string
        let cls = 'chip'
        if (st === 'clinched') {
          word = negative ? (o.key === 'relegation' ? 'Relegated' : 'In the zone') : 'Clinched'
          cls += negative ? ' chip-no' : ' chip-yes'
        } else if (st === 'eliminated') {
          word = negative ? 'Safe' : 'Out'
          cls += negative ? ' chip-yes' : ' chip-no'
        } else {
          word = p === null ? 'In play' : `${formatPct(p)}%`
        }
        const magicKey = o.key === 'relegation' ? 'safety' : o.key === 'drop_zone' ? null : o.key
        const magic = st === 'alive' && magicKey ? row.magic?.[magicKey as 'title' | 'ucl' | 'europe' | 'safety'] : null
        return (
          <li key={o.key} className={cls}>
            <span className="chip-label">{o.label}</span>
            <span className="chip-value">{word}</span>
            {typeof magic === 'number' && magic > 0 && magic <= 18 && (
              <small>{magic} more pt{magic === 1 ? '' : 's'} to {negative ? 'be safe' : 'guarantee'}</small>
            )}
            {st === 'alive' && p !== null && !negative && <small>chance now</small>}
            {st === 'alive' && p !== null && o.key === 'relegation' && <small>automatic, risk now</small>}
            {st === 'alive' && p !== null && o.key === 'drop_zone' && <small>incl. play-off, risk now</small>}
          </li>
        )
      })}
    </ul>
  )
}

function WdlBar({ w, d, l }: { w: number; d: number; l: number }) {
  return (
    <span className="wdl" title={`Win ${Math.round(w * 100)}% · Draw ${Math.round(d * 100)}% · Loss ${Math.round(l * 100)}%`}>
      <i className="wdl-w" style={{ width: `${w * 100}%` }} />
      <i className="wdl-d" style={{ width: `${d * 100}%` }} />
      <i className="wdl-l" style={{ width: `${l * 100}%` }} />
    </span>
  )
}

function dateLabel(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}

export default function TeamPage({ index }: { index: DataIndex }) {
  const { code = '', teamId = '' } = useParams()
  const [standings, setStandings] = useState<Standings | null>(null)
  const [matches, setMatches] = useState<MatchesFile | null>(null)
  const [history, setHistory] = useState<History | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setStandings(null)
    setMatches(null)
    setHistory(null)
    setError(null)
    loadStandings(index.season, code).then(setStandings).catch((e: Error) => setError(e.message))
    loadMatches(index.season, code).then(setMatches).catch(() => setMatches(null))
    loadHistory(index.season, code).then(setHistory).catch(() => setHistory(null))
  }, [index.season, code])

  const row = useMemo(() => standings?.teams.find((t) => String(t.id) === teamId) ?? null, [standings, teamId])

  useEffect(() => {
    document.title = row ? `${row.short_name} · ${standings?.league.name} · TableGenius` : 'TableGenius'
  }, [row, standings])

  const { results, fixtures, names } = useMemo(() => {
    const names = new Map<string, string>()
    matches?.teams.forEach((t) => names.set(String(t.id), t.short_name))
    const mine = (matches?.matches ?? []).filter((m) => String(m.home_id) === teamId || String(m.away_id) === teamId)
    const finished = (m: MatchRecord) => (m.status === 'FINISHED' || m.status === 'AWARDED') && m.home_goals !== null
    const results = mine.filter(finished).sort((a, b) => b.utc_date.localeCompare(a.utc_date))
    const fixtures = mine.filter((m) => !finished(m) && m.status !== 'CANCELLED').sort((a, b) => a.utc_date.localeCompare(b.utc_date))
    return { results, fixtures, names }
  }, [matches, teamId])

  if (error) return <p className="notice error">{error}</p>
  if (!standings) return <p className="notice">Loading…</p>
  if (!row) return <p className="notice error">No team with id {teamId} in this league. <Link to={`/league/${code}`}>Back to the table</Link>.</p>

  const { league } = standings
  const p = row.probs
  const hasPlayoff = !!league.zones.relegation_playoff?.positions
  const nextRound = standings.next_round
  const scenarios = row.scenarios ?? []
  const ratings = standings.teams.filter((t) => t.probs?.attack !== undefined).map((t) => ({ id: t.id, att: t.probs!.attack!, def: t.probs!.defence! }))
  const attRank = ratings.filter((r) => r.att > (p?.attack ?? 0)).length + 1
  const defRank = ratings.filter((r) => r.def > (p?.defence ?? 0)).length + 1
  const attMin = Math.min(...ratings.map((r) => r.att), 0)
  const attMax = Math.max(...ratings.map((r) => r.att), 0)
  const defMin = Math.min(...ratings.map((r) => r.def), 0)
  const defMax = Math.max(...ratings.map((r) => r.def), 0)
  const scale = (v: number, lo: number, hi: number) => (hi === lo ? 50 : ((v - lo) / (hi - lo)) * 100)

  return (
    <section className="team">
      <p className="crumbs"><Link to={`/league/${code}`}>{league.name}</Link> / {row.short_name}</p>
      <div className="band band-team">
        <div className="band-title">
          {row.crest && <img className="crest-big" src={row.crest} alt="" width={56} height={56} />}
          <h1>{row.name}</h1>
        </div>
        <div className="band-pos">
          <span className="pos-big">{row.position}<sup>{ordinal(row.position)}</sup></span>
        </div>
      </div>
      <p className="meta">
        <span><b>{row.points}</b> pts from <b>{row.played}</b></span>
        <span>W <b>{row.won}</b> D <b>{row.drawn}</b> L <b>{row.lost}</b></span>
        <span>GD <b>{signed(row.gd)}</b></span>
        <span>Home <b>{row.home.won}-{row.home.drawn}-{row.home.lost}</b> · Away <b>{row.away.won}-{row.away.drawn}-{row.away.lost}</b></span>
        <span className="meta-form">Form <Form results={row.form} /></span>
      </p>

      {p && (
        <>
          <StatusChips row={row} hasPlayoff={hasPlayoff} />
          {nextRound && nextRound.matchday !== null && (
            <div className="round-box">
              <h2>{nextRound.label === 'this weekend' ? 'This weekend' : 'This midweek'}</h2>
              {fixtures[0] && (
                <p className="muted small">
                  Next: {String(fixtures[0].home_id) === teamId ? `${names.get(String(fixtures[0].away_id))} at home` : `${names.get(String(fixtures[0].home_id))} away`}, {dateLabel(fixtures[0].utc_date)}
                  {fixtures[0].forecast && (
                    <> · win {Math.round((String(fixtures[0].home_id) === teamId ? fixtures[0].forecast.home : fixtures[0].forecast.away) * 100)}%, draw {Math.round(fixtures[0].forecast.draw * 100)}%</>
                  )}
                </p>
              )}
              {scenarios.length > 0 ? (
                <ul className="scenario-list">
                  {scenarios.map((s, i) => (
                    <li key={i} className={s.kind === 'clinch' ? 'good' : 'bad'}>{s.text}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">Nothing can be mathematically settled for {row.short_name} {nextRound.label}.</p>
              )}
            </div>
          )}
        </>
      )}

      {history && p && (
        <>
          <h2>Chances through the season</h2>
          <p className="muted small">Each point is the model's forecast at the end of that matchday, re-run with only the results known at the time.</p>
          <ChancesChart history={history} teamId={teamId} totalMatchdays={history.total_matchdays} />
        </>
      )}

      {p && (
        <div className="two-col">
          <div>
            <h2>Where they could finish</h2>
            <p className="muted small">Share of simulated seasons ending in each position. Expected finish {p.expected_position.toFixed(1)}, expected points {p.expected_points.toFixed(0)} (5th–95th percentile {p.points_p5.toFixed(0)}–{p.points_p95.toFixed(0)}).</p>
            <PositionChart positions={p.positions} league={league} current={row.position} />
          </div>
          {history && (
            <div>
              <h2>Position by matchday</h2>
              <p className="muted small">League position after each completed matchday.</p>
              <PositionHistoryChart history={history} teamId={teamId} teamCount={league.team_count} />
            </div>
          )}
        </div>
      )}

      {p && p.attack !== undefined && p.defence !== undefined && (
        <>
          <h2>Ratings</h2>
          <p className="muted small">The model's attack and defence ratings on its log scale: 0 is an average established team in this league, +0.3 means about 35% more goals scored (attack) or fewer conceded (defence). Ranks are within the league.</p>
          <div className="ratings">
            <div className="rating">
              <span className="rating-label">Attack</span>
              <span className="rating-track"><i style={{ left: `${scale(0, attMin, attMax)}%` }} className="rating-zero" /><b style={{ left: `${scale(p.attack, attMin, attMax)}%` }} /></span>
              <span className="rating-value">{signed(Number(p.attack.toFixed(2)))} · {attRank}{ordinal(attRank)}</span>
            </div>
            <div className="rating">
              <span className="rating-label">Defence</span>
              <span className="rating-track"><i style={{ left: `${scale(0, defMin, defMax)}%` }} className="rating-zero" /><b style={{ left: `${scale(p.defence, defMin, defMax)}%` }} /></span>
              <span className="rating-value">{signed(Number(p.defence.toFixed(2)))} · {defRank}{ordinal(defRank)}</span>
            </div>
          </div>
        </>
      )}

      <div className="two-col">
        <div>
          <h2>Fixtures</h2>
          {fixtures.length === 0 ? (
            <p className="muted">No fixtures left.</p>
          ) : (
            <ol className="matchlist">
              {fixtures.slice(0, 8).map((m) => {
                const home = String(m.home_id) === teamId
                const opp = names.get(String(home ? m.away_id : m.home_id)) ?? '?'
                const f = m.forecast
                const mk = m.market
                return (
                  <li key={m.id} title={mk ? `Bookmakers (${mk.source}): win ${Math.round((home ? mk.home : mk.away) * 100)}%, draw ${Math.round(mk.draw * 100)}%` : undefined}>
                    <span className="ml-date">{dateLabel(m.utc_date)}</span>
                    <span className="ml-opp"><b>{home ? 'H' : 'A'}</b> {opp}</span>
                    {f ? <WdlBar w={home ? f.home : f.away} d={f.draw} l={home ? f.away : f.home} /> : <span />}
                    {f && (
                      <span className="ml-pct">
                        {Math.round((home ? f.home : f.away) * 100)}% win
                        {mk && <small> · mkt {Math.round((home ? mk.home : mk.away) * 100)}%</small>}
                      </span>
                    )}
                  </li>
                )
              })}
            </ol>
          )}
        </div>
        <div>
          <h2>Results</h2>
          {results.length === 0 ? (
            <p className="muted">No results yet.</p>
          ) : (
            <ol className="matchlist">
              {results.slice(0, 8).map((m) => {
                const home = String(m.home_id) === teamId
                const opp = names.get(String(home ? m.away_id : m.home_id)) ?? '?'
                const gf = home ? m.home_goals! : m.away_goals!
                const ga = home ? m.away_goals! : m.home_goals!
                const res = gf > ga ? 'W' : gf === ga ? 'D' : 'L'
                return (
                  <li key={m.id}>
                    <span className="ml-date">{dateLabel(m.utc_date)}</span>
                    <span className="ml-opp"><b>{home ? 'H' : 'A'}</b> {opp}</span>
                    <span className="ml-score">{gf}–{ga}</span>
                    <span className={`form-pip form-${res}`}>{res}</span>
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      </div>
      <p className="muted small">Chances and forecasts from the model described on the <Link to="/about">About page</Link>. Settled outcomes are decided on points alone and treat any tie on points conservatively.</p>
    </section>
  )
}
