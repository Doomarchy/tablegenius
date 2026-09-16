# TableGenius

Live league tables for the Premier League, LaLiga, Serie A, Bundesliga and Ligue 1, with
model-driven probabilities for the title, European places and relegation.

No server runs continuously. A GitHub Actions job fetches results a few times a day (hourly
around match days), rebuilds the tables, runs the model and commits static JSON files. A
static React site reads those files and is hosted on GitHub Pages.

## Layout

```
config/leagues/<season>/<CODE>.json   league rules: teams, tiebreakers, European and relegation zones
pipeline/                             Python: fetch data, build tables, (soon) fit the model and simulate
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

   Add `--source csv` to build tables from football-data.co.uk instead (no token needed,
   no fixtures or crests). Add `--leagues PL,PD` to limit the leagues.

3. Site:

   ```
   cd site
   npm install
   npm run dev
   ```

   Then open the printed localhost address.

4. Tests: `cd pipeline` then `..\.venv\Scripts\python -m pytest`.

## Data sources

- [football-data.org](https://www.football-data.org) free tier: standings, fixtures and results
  for all five leagues, 10 requests per minute. The pipeline makes 2 requests per league per run.
- [football-data.co.uk](https://www.football-data.co.uk): CSV results for past seasons, used for
  team-strength fitting and the backtest.

## League rules

Each `config/leagues/<season>/<CODE>.json` file records the number of teams, the tiebreak order,
which positions qualify for which competition, relegation and play-off places, and the
assumptions made (cup places passing down the table, no extra coefficient-based Champions League
place). Change the season's rules there, never in code.
