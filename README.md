# TableGenius

Live league tables for the Premier League, LaLiga, Serie A, Bundesliga and Ligue 1, with
model-driven probabilities for the title, European places and relegation.

No server runs continuously. A GitHub Actions job fetches results a few times a day (hourly
around match days), rebuilds the tables, runs the model and commits static JSON files. A
static React site reads those files and is hosted on GitHub Pages.

## Layout

```
config/leagues/<season>/<CODE>.json   league rules: teams, tiebreakers, European and relegation zones
config/model.json                     model parameters (time decay, priors, simulation count)
config/team_names.json                football-data.co.uk team names -> football-data.org ids
pipeline/                             Python: fetch data, build tables, fit the model, simulate, backtest
pipeline/history/                     past-season results CSVs from football-data.co.uk (committed)
site/                                 Vite + React + TypeScript frontend
site/public/data/                     generated JSON the site reads (committed by the pipeline)
.github/workflows/update-and-deploy.yml   the scheduled job
```

## Running locally

Requirements: Python 3.12+, Node 20+.

1. Copy `.env.example` to `.env` and paste your football-data.org token after the `=`.
2. Pipeline (creates a virtual environment the first time):

   ```
   python -m venv .venv
   .venv\Scripts\pip install -r pipeline\requirements.txt
   cd pipeline
   ..\.venv\Scripts\python -m tablegenius.run --season 2026-27
   ```

   Useful flags: `--source csv` builds tables from football-data.co.uk without a token
   (no fixtures, crests or probabilities); `--leagues PL,PD` limits the leagues;
   `--no-model` skips the ratings and simulation; `--force-model` re-runs the model even
   when no result has changed (otherwise the previous probabilities are kept so they do
   not jitter between result updates); `--sims 20000` changes the simulation count.

3. Site:

   ```
   cd site
   npm install
   npm run dev
   ```

   Then open the printed localhost address.

4. Tests: `cd pipeline` then `..\.venv\Scripts\python -m pytest`.

## Model commands

All from the `pipeline` folder with `..\.venv\Scripts\python`:

- `-m tablegenius.names --season 2026-27` proposes name mappings for any new teams and
  updates `config/team_names.json` (check the low-confidence lines it prints).
- `-m tablegenius.calibrate` re-estimates the promoted-team prior from past seasons.
- `-m tablegenius.backtest --season 2025-26` re-runs the model at ten points of a past
  season, scores it, and writes `site/public/data/backtest.json` for the About page.
  Options: `--sims`, `--xi`, `--prior-strength`, `--draws`, `--leagues`.

## How the model works

Dixon-Coles attack/defence ratings fitted on this season plus the two previous ones with
exponential time decay (half-life about a year), a ridge prior towards the league average,
and a calibrated prior for promoted teams. Rating uncertainty from the fit (Laplace
approximation) is propagated by sampling 100 rating sets, and 10,000 seasons are simulated
per league with each league's real tiebreakers. See the About page for the plain-language
version and the backtest results.

## Data sources

- [football-data.org](https://www.football-data.org) free tier: standings, fixtures and results
  for all five leagues, 10 requests per minute. The pipeline makes 2 requests per league per run.
- [football-data.co.uk](https://www.football-data.co.uk): CSV results for past seasons, used for
  team-strength fitting and the backtest (including bookmaker odds for the match-level comparison).

## League rules

Each `config/leagues/<season>/<CODE>.json` file records the number of teams, the tiebreak order,
which positions qualify for which competition, relegation and play-off places, and the
assumptions made (cup places passing down the table, no extra coefficient-based Champions League
place). Change the season's rules there, never in code.
