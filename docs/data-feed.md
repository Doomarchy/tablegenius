# TableGenius data feed

Everything the site shows is a static JSON file you can fetch directly. Files are rebuilt a
few times a day (hourly around match days) by the GitHub Actions job and served from GitHub
Pages with permissive CORS, so they work from a browser, a spreadsheet, or a script.

Base URL: `https://doomarchy.github.io/tablegenius/data/`

| File | What it holds |
|---|---|
| `index.json` | Season, list of leagues, last update time per league, matchday info |
| `<season>/<CODE>/standings.json` | The table with, per team: record, form, home/away splits, probabilities, clinch statuses, magic numbers, next-round scenarios; plus the model's fitted values and the rule settings in force |
| `<season>/<CODE>/matches.json` | Every match of the season: results, fixtures, the model's win/draw/loss forecast and expected goals for unplayed matches, bookmaker odds for the coming round where available |
| `<season>/<CODE>/history.json` | Probabilities by matchday (pre-season plus one point per completed matchday, and the matchday in progress) |
| `backtest.json` | The latest backtest report shown on the About page |

League codes: `PL` Premier League, `PD` LaLiga, `SA` Serie A, `BL1` Bundesliga, `FL1` Ligue 1.
Team ids are football-data.org ids and are stable across seasons.

## Example

```
https://doomarchy.github.io/tablegenius/data/2026-27/PL/standings.json
```

```js
const r = await fetch('https://doomarchy.github.io/tablegenius/data/2026-27/PL/standings.json')
const s = await r.json()
for (const t of s.teams) console.log(t.position, t.short_name, Math.round(t.probs.title * 100) + '%')
```

## Fields worth knowing

- `probs.title`, `probs.ucl`, `probs.uel`, `probs.uecl`, `probs.europe`, `probs.relegation`,
  `probs.relegation_playoff` are shares of simulated seasons (0 to 1). `probs.relegation_total`
  adds the play-off risk using the historical survival rate in the league config.
- `probs.positions` is the full finishing-position distribution, index 0 = 1st.
- `status.<outcome>` is `alive`, `clinched` or `eliminated`, decided on points alone.
- `magic.title`, `magic.ucl`, `magic.europe`, `magic.safety` are points still needed to
  guarantee the outcome whatever rivals do (null if impossible alone).
- `scenarios[]` are the plain-English next-round lines.
- `model` describes the fit: matches used, home advantage, draw correction, simulation count,
  the results hash the probabilities were computed for, and when.
- `rules` lists cup winners entered, points deductions applied, the extra Champions League
  place probability and the play-off survival rate.

## Terms

Free to use with attribution to TableGenius and the upstream sources
(football-data.org for results and fixtures, football-data.co.uk for historical results and odds).
Probabilities are model estimates, not predictions of fact.
