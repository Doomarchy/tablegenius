import { useEffect } from 'react'
import type { DataIndex } from '../types'

export default function AboutPage({ index }: { index: DataIndex }) {
  useEffect(() => {
    document.title = 'About the model · TableGenius'
  }, [])

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
        and re-runs the model. Historical results from previous seasons, used to estimate team strength, come from{' '}
        <a href="https://www.football-data.co.uk">football-data.co.uk</a>.
      </p>
      <p>
        Tables are computed from the raw results using each league's own tiebreak rules (some leagues use
        head-to-head records before goal difference), then cross-checked against the provider's official table.
      </p>

      <h2>How the probabilities are made</h2>
      <p>
        <em>Probability columns arrive in the next release.</em> The method: each team gets an attack rating and a
        defence rating, estimated from recent results with a Dixon-Coles model, a variant of the Poisson model that
        fixes the well-known under-prediction of low-scoring draws. Recent matches count more than old ones, and
        promoted teams start from a prior based on how promoted teams have done in the past.
      </p>
      <p>
        Every remaining fixture is then simulated at least 10,000 times. Each simulated season is ranked with the
        league's real tiebreakers, and the share of simulations in which a team finishes in a given place becomes its
        probability. No language model is involved anywhere in this process.
      </p>

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
          simulated.
        </li>
      </ul>

      <h2>How good is the model?</h2>
      <p>
        Once the model is live, this section will report its accuracy on the previous season using proper scoring
        rules (Brier score and log loss), in plain language.
      </p>
    </article>
  )
}
