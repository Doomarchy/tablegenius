"""Prepare the rule files for a new season and print the rollover checklist.

    python -m tablegenius.newseason --season 2027-28

Copies each league's config from the previous season, bumps the season fields, clears
cup winners, deductions and the extra-place probability, and lists what must be checked
by hand (rules change every year; never trust the copy blindly).
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import LEAGUE_ORDER
from .dataset import previous_season
from .paths import LEAGUES_DIR

CHECKLIST = """
Season rollover checklist for {season}
=====================================
1. Verify every league's rules for {season} against official sources (number of teams,
   relegation and play-off places, tiebreak order, European places, cup rules). Update
   config/leagues/{season}/<CODE>.json and its rule_sources.
2. Set extra_ucl_place / european_places if UEFA's access list changed for this season,
   and extra_ucl_probability to 0 (it is a within-season race).
3. After the first API run of the new season, run
       python -m tablegenius.names --season {season}
   and check the low-confidence lines it prints (new promoted clubs need CSV name mappings).
4. Re-estimate the promoted-team prior once the previous season's CSVs are final:
       python -m tablegenius.calibrate --seasons {cal_seasons}
   then update config/model.json (promoted_prior, promoted_prior_by_league).
5. Run the backtest on the season just finished and commit site/public/data/backtest.json:
       python -m tablegenius.backtest --season {previous} --config-season {season}
   (the yearly backtest workflow does this automatically on 1 August).
6. Update the season in .github/workflows/update-and-deploy.yml (--season {season}).
7. Delete or archive site/public/data/{previous} if you do not want it served any more.
8. Run the pipeline once locally, check the site, commit and push.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", required=True, help="new season, e.g. 2027-28")
    parser.add_argument("--force", action="store_true", help="overwrite existing files for the new season")
    args = parser.parse_args(argv)
    season = args.season
    prev = previous_season(season)
    src_dir = LEAGUES_DIR / prev
    dst_dir = LEAGUES_DIR / season
    if not src_dir.exists():
        print(f"No configs for {prev} at {src_dir}", file=sys.stderr)
        return 1
    dst_dir.mkdir(parents=True, exist_ok=True)
    start_year = int(season.split("-")[0])
    for code in LEAGUE_ORDER:
        src = src_dir / f"{code}.json"
        dst = dst_dir / f"{code}.json"
        if not src.exists():
            continue
        if dst.exists() and not args.force:
            print(f"keeping existing {dst}")
            continue
        cfg = json.loads(src.read_text(encoding="utf-8"))
        cfg["season"] = season
        cfg["sources"]["football_data_org"]["season"] = start_year
        cfg["extra_ucl_probability"] = 0.0
        cfg["extra_ucl_place"] = False
        for cup in cfg.get("domestic_cups", []):
            cup["winner"] = None
        cfg["points_deductions"] = []
        cfg["rule_sources"] = []
        cfg["_todo"] = f"Copied from {prev}. Verify every rule for {season} and fill rule_sources before relying on it."
        dst.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {dst}")
    cal = f"{previous_season(previous_season(prev))},{previous_season(prev)},{prev}"
    print(CHECKLIST.format(season=season, previous=prev, cal_seasons=cal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
