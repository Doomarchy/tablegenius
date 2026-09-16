import { useEffect, useState } from 'react'
import { loadBacktest, loadStandings } from '../api'
import { dec2, pct1 } from '../format'
import type { Backtest, DataIndex, Standings } from '../types'

function ScoreTable({ bt }: { bt: Backtest }) {
  const keys = Object.keys(bt.outcome_scores)
  return (
    <div className="table-wrap plain">
      <table className="mini-table">
        <thead>
          <tr>
            <th scope="col">Forecast</th>
            <th scope="col" title="Brier score of the full model (lower is better)">Model</th>
            <th scope="col" title="Same simulation, but every team assumed equally strong">Table only</th>
            <th scope="col" title="Every team given the same chance">Same for all</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const s = bt.outcome_scores[k]
            return (
              <tr key={k}>
                <th scope="row">{s.label}</th>
                <td>{s.model.brier.toFixed(3)}</td>
                <td>{s.no_ratings.brier.toFixed(3)}</td>
                <td>{s.uniform.brier.toFixed(3)}</td>
              </tr>
            )
          })}
          {bt.match_scores.model && bt.match_scores.bookmaker && (
            <tr>
              <th scope="row">Match result (log loss, vs bookmakers)</th>
              <td>{bt.match_scores.model.log_loss.toFixed(3)}</td>
              <td>{bt.match_scores.bookmaker.log_loss.toFixed(3)}</td>
              <td>{bt.match_scores.uniform.log_loss.toFixed(3)}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function CalibrationTable({ bt }: { bt: Backtest }) {
  return (
    <div className="table-wrap plain">
      <table className="mini-table">
        <thead>
          <tr>
            <th scope="col">Model said</th>
            <th scope="col">Average forecast</th>
            <th scope="col">Actually happened</th>
            <th scope="col">Cases</th>
          </tr>
        </thead>
        <tbody>
          {bt.calibration.map((c) => (
            <tr key={c.bin}>
              <th scope="row">{c.bin}</th>
              <td>{pct1(c.predicted)}</td>
              <td>{pct1(c.observed)}</td>
              <td>{c.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ParamsTable({ leagues }: { leagues: Standings[] }) {
  return (
    <div className="table-wrap plain">
      <table className="mini-table">
        <thead>
          <tr>
            <th scope="col">League</th>
            <th scope="col" title="Expected goals per match for the home side and the away side when two average teams meet">Home / away goals</th>
            <th scope="col" title="The Dixon-Coles low-score correction; negative values mean more 0-0 and 1-1 draws than plain Poisson">Draw correction</th>
            <th scope="col">Matches used</th>
            <th scope="col">Promoted teams</th>
          </tr>
        </thead>
        <tbody>
          {leagues.map((s) => (
            <tr key={s.league.code}>
              <th scope="row">{s.league.name}</th>
              <td>{s.model ? `${dec2(s.model.avg_home_goals)} / ${dec2(s.model.avg_away_goals)}` : '–'}</td>
              <td>{s.model ? s.model.rho.toFixed(3) : '–'}</td>
              <td>{s.model ? `${s.model.fitted_matches.toLocaleString()} (${Math.round(s.model.effective_matches)} after decay)` : '–'}</td>
              <td>{s.model ? s.model.promoted_teams.join(', ') : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AboutPage({ index }: { index: DataIndex }) {
  const [leagues, setLeagues] = useState<Standings[]>([])
  const [backtest, setBacktest] = useState<Backtest | null>(null)

  useEffect(() => {
    document.title = 'About the model · TableGenius'
    Promise.all(index.leagues.map((l) => loadStandings(index.season, l.code)))
      .then(setLeagues)
      .catch(() => setLeagues([]))
    if (index.has_backtest) loadBacktest().then(setBacktest).catch(() => setBacktest(null))
  }, [index])

  const first = leagues.find((s) => s.model)?.model ?? null
  const halfLife = first ? Math.round(first.half_life_days) : 385

  return (
    <article className="prose">
      <h1>About TableGenius</h1>
      <p>
        TableGenius shows live league tables for the Premier League, LaLiga, Serie A, Bundesliga and Ligue 1,
        together with model-estimated chances of winning the title, qualifying for European competitions and
        being relegated. Season {index.season}.
      </p>

      <h2>Where the data comes from</h2>
      <p>
        Results, fixtures and crests come from <a href="https://www.football-data.org">football-data.org</a>. A
        scheduled job checks for new results several times a day and more often on match days, rebuilds every table
        and re-runs the model. Results from the two previous seasons, used to estimate team strength, come from{' '}
        <a href="https://www.football-data.co.uk">football-data.co.uk</a>.
      </p>
      <p>
        Tables are computed from the raw results using each league's own tiebreak rules (some leagues use
        head-to-head records before goal difference), then cross-checked against the provider's official table.
      </p>

      <h2>How the probabilities are made</h2>
      <p>
        <strong>1. Rate every team.</strong> Each team gets an attack rating and a defence rating, estimated from
        results with a Dixon-Coles model. That is a Poisson goals model with a small correction for the fact that
        low-scoring draws happen a little more often than plain Poisson predicts. Recent matches count more than
        old ones: a result loses half its weight after about {halfLife} days, so this season matters most, last
        season still counts and the season before that only a little. Home advantage and the draw correction are
        estimated separately for every league.
      </p>
      <p>
        <strong>2. Be sensible about newcomers.</strong> Promoted teams have no recent top-flight results, so
        they start from a prior taken from the last three seasons of promoted teams: on average a newcomer is
        about {first ? Math.abs(first.promoted_prior.attack).toFixed(2) : '0.27'} weaker in attack and{' '}
        {first ? Math.abs(first.promoted_prior.defence).toFixed(2) : '0.23'} weaker in defence (on the model's log scale)
        than an average established team. As they play, their own results take over. Every team's rating is also
        gently shrunk towards the league average, which stops a few freak results from swinging the numbers.
      </p>
      <p>
        <strong>3. Admit the ratings are estimates.</strong> Instead of treating the fitted ratings as exact, the
        model draws {first ? first.n_rating_draws : 100} plausible alternative rating sets from the statistical
        uncertainty of the fit. A team that has played four games has much wider uncertainty than one with
        seventy in the books, and the forecasts reflect that.
      </p>
      <p>
        <strong>4. Play the season out, many times.</strong> Every remaining fixture is simulated{' '}
        {first ? first.n_sims.toLocaleString() : '10,000'} times per league, spread across those rating sets. Each
        simulated season is ranked with the league's real tiebreakers, and the share of simulations in which a team
        finishes in a given place becomes its probability. Expected points and expected position are the averages
        across all simulated seasons. No language model is involved anywhere in this process.
      </p>
      {leagues.length > 0 && (
        <>
          <h3>Fitted values right now</h3>
          <ParamsTable leagues={leagues} />
        </>
      )}

      <h2>How good is the model?</h2>
      {backtest ? (
        <>
          {backtest.summary.map((line, i) => (
            <p key={i}>{line}</p>
          ))}
          <h3>Scores by forecast type</h3>
          <p className="muted small">
            Brier score: the average squared gap between a forecast and what happened, so lower is better and 0 would
            be perfect. “Table only” uses the same simulation but treats every team as equally strong. “Same for
            all” gives every team an identical chance.
          </p>
          <ScoreTable bt={backtest} />
          <h3>Calibration</h3>
          <p className="muted small">
            For every forecast the model made during the backtest, grouped by how confident it was: a well-calibrated
            model's “actually happened” column should track its “average forecast” column.
          </p>
          <CalibrationTable bt={backtest} />
          <p className="muted small">
            Backtest of the {backtest.season} season, generated {new Date(backtest.generated_at).toLocaleDateString(undefined, { dateStyle: 'medium' })},{' '}
            {backtest.n_sims.toLocaleString()} simulations per checkpoint.
          </p>
        </>
      ) : (
        <p>The backtest report has not been generated yet.</p>
      )}

      <h2>Assumptions to be aware of</h2>
      <ul>
        <li>
          Domestic cup winners earn European places. Because a cup winner usually also qualifies through the league,
          those places are assumed to pass down the table. Each league page lists the resulting positions.
        </li>
        <li>
          The extra Champions League places UEFA awards to the two best-performing associations each season are not
          modelled; they are decided at the end of the European season.
        </li>
        <li>
          Relegation play-offs in the Bundesliga and Ligue 1 are shown as their own outcome. The play-off itself is not
          simulated. Serie A's play-offs for a tie on points for first place or the last relegation spot are treated
          as a coin flip.
        </li>
        <li>
          The model only sees results. Injuries, transfers, fixture congestion, cup runs and managerial changes are
          invisible to it, which is the main reason bookmakers' match odds are a little sharper.
        </li>
        <li>
          Ties that the data cannot separate (for example when the rules reach fair-play points or a drawing of
          lots) are split at random in the simulations and marked with an equals sign in the live table.
        </li>
      </ul>
    </article>
  )
}
