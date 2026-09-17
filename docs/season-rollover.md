# Season rollover

Once a year, when the new season's fixtures are published (usually June or July), run:

```
cd pipeline
..\.venv\Scripts\python -m tablegenius.newseason --season 2027-28
```

It copies each league's rule file from the previous season, bumps the season fields, clears
cup winners, points deductions and the extra-place probability, and prints the checklist
below. Then work through the checklist; the copied rules are a starting point, not the truth.

1. Verify every league's rules for the new season against official sources: number of
   teams, relegation and play-off places, tiebreak order, European places, cup rules. Update
   `config/leagues/<season>/<CODE>.json` and its `rule_sources`.
2. Set `european_places` and `extra_ucl_place` if UEFA's access list changed; leave
   `extra_ucl_probability` at 0 until the coefficient race is worth tracking.
3. After the first API run of the new season, run `python -m tablegenius.names --season <season>`
   and check the low-confidence lines it prints; newly promoted clubs need name mappings.
4. Re-estimate the promoted-team prior once the previous season's CSVs are final:
   `python -m tablegenius.calibrate --seasons <three most recent seasons>`, then update
   `promoted_prior` and `promoted_prior_by_league` in `config/model.json`.
5. Run the backtest on the season just finished (the yearly workflow does this on 1 August;
   you can also trigger it from the Actions tab) and read the About page afterwards.
6. Change `--season` in `.github/workflows/update-and-deploy.yml`.
7. Decide what to do with the previous season's data folder under `site/public/data/`.
8. Run the pipeline locally, check the site, commit and push.

## During the season

- When a domestic cup is decided, set its `winner` in the league config (club name as shown
  on the site, its football-data.org id, or `"external"` for a club outside the league).
- When points are deducted, add an entry to `points_deductions` with the date applied.
- If the league is in the running for the extra Champions League place, set
  `extra_ucl_probability` from the UEFA association ranking race (0 to 1).
- The next scheduled run picks the change up; probabilities are recomputed because the rules
  hash changed even if no result did.
