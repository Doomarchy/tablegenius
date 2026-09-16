"""Estimate the "promoted team" prior from past seasons.

    python -m tablegenius.calibrate --seasons 2023-24,2024-25,2025-26

For every league-season, fits the model on that season alone (no time decay, a weak
neutral prior) and records the attack/defence ratings of the teams that had been promoted
into it. The averages are what a newly promoted team should be assumed to be before it
has played: they go into config/model.json as `promoted_prior`.
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta

import numpy as np

from .config import LEAGUE_ORDER, load_league
from .dataset import build_fit_data, history_rows, previous_season
from .model import ModelParams, fit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", default="2023-24,2024-25,2025-26")
    parser.add_argument("--config-season", default="2026-27", help="season whose league configs to use")
    args = parser.parse_args(argv)
    seasons = [s.strip() for s in args.seasons.split(",")]
    params = ModelParams(xi=0.0, prior_strength=0.5, promoted_attack=0.0, promoted_defence=0.0)

    rows_out: list[tuple[str, str, str, float, float]] = []
    for code in LEAGUE_ORDER:
        cfg = load_league(args.config_season, code)
        csv_code = cfg["sources"]["football_data_co_uk"]["code"]
        for season in seasons:
            prev = previous_season(season)
            rows, season_teams = history_rows(csv_code, [season, prev], mapping={})
            cur_rows = [r for r in rows if r["season"] == season]
            current_ids = sorted(season_teams[season])
            previous_ids = season_teams[prev]
            as_of = max(r["date"] for r in cur_rows) + timedelta(days=1)
            data = build_fit_data(cur_rows, current_ids, previous_ids, as_of, params, [season])
            r = fit(data, params)
            for i, t in enumerate(current_ids):
                if t not in previous_ids:
                    rows_out.append((code, season, str(t), float(r.attack[i]), float(r.defence[i])))
    att = np.array([r[3] for r in rows_out])
    dfn = np.array([r[4] for r in rows_out])
    print(f"{'league':<5} {'season':<8} {'team':<18} {'attack':>7} {'defence':>8}")
    for code, season, team, a, d in rows_out:
        print(f"{code:<5} {season:<8} {team:<18} {a:>7.3f} {d:>8.3f}")
    print(f"\npromoted teams: n={len(rows_out)}")
    print(f"attack : mean {att.mean():.3f}  sd {att.std(ddof=1):.3f}  (se {att.std(ddof=1)/np.sqrt(len(att)):.3f})")
    print(f"defence: mean {dfn.mean():.3f}  sd {dfn.std(ddof=1):.3f}  (se {dfn.std(ddof=1)/np.sqrt(len(dfn)):.3f})")
    for code in LEAGUE_ORDER:
        sel = [r for r in rows_out if r[0] == code]
        if sel:
            print(f"  {code}: attack {np.mean([r[3] for r in sel]):.3f}  defence {np.mean([r[4] for r in sel]):.3f}  (n={len(sel)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
