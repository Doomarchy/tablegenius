# TableGenius

Live league tables for the Premier League, LaLiga, Serie A, Bundesliga and Ligue 1, with
model-driven probabilities for the title, European places and relegation, team pages with
season charts, and clinch/elimination scenarios.

No server runs continuously. A GitHub Actions job fetches results a few times a day (hourly
around match days), rebuilds the tables, runs the model and commits static JSON files. A
static React site reads those files and is hosted on GitHub Pages.

Live site: https://doomarchy.github.io/tablegenius/

## Layout

```
config/leagues/<season>/<CODE>.json   league rules: teams, tiebreakers, zones, European places,
                                      cup winners, points deductions, play-off survival rate
config/model.json                     model parameters (time decay, priors, simulation counts, xG blend)
config/team_names.json                football-data.co.uk team names -> football-data.org ids
pipeline/                             Python: fetch, tables, model, simulation, clinching, history, backtest
pipeline/history/                     past-season results CSVs from football-data.co.uk (committed)
site/                                 Vite + React + TypeScript frontend
site/public/data/                     generated JSON the site reads (committed by the pipeline)
docs/                                 data feed guide, season rollover, custom domain
.github/workflows/update-and-deploy.yml   the scheduled job (opens a GitHub issue if it fails)
.github/workflows/backtest.yml            yearly backtest of the season just finished
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
   when nothing changed; `--no-history` skips the matchday history; `--sims 20000` changes
   the simulation count.

3. Site:

   ```
   cd site
   npm install
   npm run dev
   ```

4. Tests: `cd pipeline` then `..\.venv\Scripts\python -m pytest`.

## Commands

All from the `pipeline` folder with `..\.venv\Scripts\python`:

- `-m tablegenius.names --season 2026-27` proposes name mappings for new teams.
- `-m tablegenius.calibrate` re-estimates the promoted-team priors (pooled and per league).
- `-m tablegenius.backtest --season 2025-26` re-runs the model at ten points of a past
  season and writes `site/public/data/backtest.json`. Options: `--sims`, `--xi`,
  `--prior-strength`, `--draws`, `--leagues`.
- `-m tablegenius.newseason --season 2027-28` prepares the next season's rule files and
  prints the rollover checklist (see `docs/season-rollover.md`).

## During the season

Edit the league's rule file and push; the next run recomputes everything:

- `domestic_cups[].winner`: the cup winner once decided (club name, id, or `"external"`).
- `points_deductions`: `{"team", "points", "reason", "applied"}` entries.
- `extra_ucl_probability`: chance of the extra Champions League place, from the UEFA race.

## How the model works

Dixon-Coles attack/defence ratings fitted on this season plus the two previous ones with
exponential time decay (half-life about a year), a ridge prior towards the league average,
and calibrated priors for promoted teams. Rating uncertainty (Laplace approximation) is
propagated by sampling 100 rating sets, and 10,000 seasons are simulated per league with each
league's real tiebreakers; European places are allocated inside every simulated season,
including cup winners and the optional extra Champions League place. Clinching and
elimination are decided on points alone, conservatively. See the About page for the
plain-language version and the backtest.

## Data

- [football-data.org](https://www.football-data.org) free tier: standings, fixtures and results.
- [football-data.co.uk](https://www.football-data.co.uk): past-season CSVs (results, odds, and
  from 2026-27 expected goals) for fitting, the backtest and calibration.
- The site's own JSON is documented in `docs/data-feed.md`.

## Reliability

The scheduled workflow validates every league's output before writing it (team counts,
records, probabilities that sum to one); a failed check keeps the previous files and fails
the run, and a failing run opens a `pipeline-failure` GitHub issue that closes itself when a
run succeeds again. The API client retries network errors and rate limits.
