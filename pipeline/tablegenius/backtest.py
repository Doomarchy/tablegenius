"""Backtest the model on a completed season.

    python -m tablegenius.backtest --season 2025-26 [--leagues PL,PD] [--sims 3000]
                                   [--xi 0.0018] [--prior-strength 3.0]

At ten checkpoints through the season (0%, 10%, ... 90% of matches played) the model is
fitted using only the results known at that time, the rest of the season is simulated and
the probabilities are scored against what actually happened. Two baselines are scored the
same way: "uniform" (every team gets the same chance) and "no ratings" (the same
simulation, but every team assumed equally strong, so only points already won matter).
Match-level forecasts between checkpoints are scored against bookmaker odds from the CSVs.

Writes site/public/data/backtest.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from .config import LEAGUE_ORDER, load_league
from .dataset import build_fit_data, history_rows, previous_season, seasons_before
from .model import ModelParams, fit, predict_outcomes, sample_ratings
from .paths import CONFIG_DIR, DATA_DIR
from .simulate import simulate, team_probabilities
from .sources import normalize_csv_matches
from .standings import build_standings

log = logging.getLogger("tablegenius.backtest")

CHECKPOINTS = [i / 10 for i in range(10)]
EPS = 0.005
CAL_EDGES = [0.0, 0.05, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0000001]

OUTCOME_LABELS = {
    "title": "Win the title",
    "ucl": "Champions League place",
    "europe": "Any European place",
    "relegation": "Relegated",
}


def outcome_ranges(cfg: dict[str, Any]) -> dict[str, list[tuple[int, int]]]:
    z = cfg["zones"]

    def rng(key: str) -> list[tuple[int, int]]:
        p = z.get(key, {}).get("positions")
        return [(p[0], p[1])] if p else []

    return {
        "title": [(1, 1)],
        "ucl": rng("ucl") + rng("ucl_qualifying"),
        "europe": rng("ucl") + rng("ucl_qualifying") + rng("uel") + rng("uecl"),
        "relegation": rng("relegation"),
    }


def in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= pos <= b for a, b in ranges)


def prob_from_positions(positions: list[float], ranges: list[tuple[int, int]]) -> float:
    return float(sum(sum(positions[a - 1:b]) for a, b in ranges))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def scores(p: np.ndarray, y: np.ndarray) -> dict[str, float]:
    return {"brier": round(brier(p, y), 4), "log_loss": round(log_loss(p, y), 4), "n": int(len(p))}


def run_league(cfg: dict[str, Any], season: str, params: ModelParams, n_sims: int, history_seasons: int,
               n_draws: int = 100) -> dict[str, Any]:
    code = cfg["code"]
    csv_code = cfg["sources"]["football_data_co_uk"]["code"]
    hist_seasons = seasons_before(season, history_seasons)
    rows, season_teams = history_rows(csv_code, [season] + hist_seasons, mapping={})
    cur = sorted((r for r in rows if r["season"] == season), key=lambda r: r["date"])
    hist = [r for r in rows if r["season"] != season]
    teams = sorted(season_teams[season])
    prev_ids = season_teams.get(previous_season(season), set())

    # Actual final table.
    from .history import fetch_season_csv
    all_matches, team_meta = normalize_csv_matches(fetch_season_csv(season, csv_code))
    final = build_standings(all_matches, team_meta, cfg)
    final_pos = {r["id"]: r["position"] for r in final["teams"]}
    ranges = outcome_ranges(cfg)

    M = len(cur)
    cutoffs: list[datetime] = []
    for frac in CHECKPOINTS:
        m = int(round(M * frac))
        as_of = cur[0]["date"].replace(hour=0, minute=0, second=0) if m == 0 else \
            (cur[m - 1]["date"].replace(hour=0, minute=0, second=0) + timedelta(days=1))
        cutoffs.append(as_of)
    cutoffs.append(cur[-1]["date"] + timedelta(days=1))  # end of season

    outcome_records: list[dict[str, Any]] = []
    match_records: list[dict[str, Any]] = []
    for k, frac in enumerate(CHECKPOINTS):
        as_of, next_as_of = cutoffs[k], cutoffs[k + 1]
        played_rows = [r for r in cur if r["date"] < as_of]
        played = [(r["home"], r["away"], r["x"], r["y"]) for r in played_rows]
        fixtures = [(r["home"], r["away"]) for r in cur if r["date"] >= as_of]
        data = build_fit_data(played_rows + hist, teams, prev_ids, as_of, params, [season] + hist_seasons)
        ratings = fit(data, params)
        seed = 1000 * k + 7
        draws = sample_ratings(ratings, n_draws, np.random.default_rng(seed + 1), params.rho_bounds)
        sim_model = simulate(cfg, ratings, teams, played, fixtures, n_sims=n_sims, seed=seed, max_goals=params.max_goals,
                             ratings_draws=draws)
        sim_flat = simulate(cfg, ratings.with_flat_teams(), teams, played, fixtures, n_sims=n_sims, seed=seed, max_goals=params.max_goals)
        pm = team_probabilities(cfg, sim_model)
        pf = team_probabilities(cfg, sim_flat)
        n = len(teams)
        for t in teams:
            for outcome, rr in ranges.items():
                if not rr:
                    continue
                size = sum(b - a + 1 for a, b in rr)
                outcome_records.append({
                    "league": code, "checkpoint": frac, "team": str(t), "outcome": outcome,
                    "model": prob_from_positions(pm[t]["positions"], rr),
                    "no_ratings": prob_from_positions(pf[t]["positions"], rr),
                    "uniform": size / n,
                    "actual": 1.0 if in_ranges(final_pos[t], rr) else 0.0,
                })
        # Match-level forecasts for the matches before the next checkpoint.
        window = [r for r in cur if as_of <= r["date"] < next_as_of]
        if window:
            probs = predict_outcomes(draws, [r["home"] for r in window], [r["away"] for r in window], params.max_goals)
            for r, p in zip(window, probs):
                actual = 0 if r["x"] > r["y"] else (1 if r["x"] == r["y"] else 2)
                rec = {"league": code, "checkpoint": frac, "model": [float(v) for v in p], "actual": actual}
                if r.get("odds"):
                    rec["bookmaker"] = [r["odds"]["home"], r["odds"]["draw"], r["odds"]["away"]]
                match_records.append(rec)
        log.info("%s checkpoint %.0f%%: %d played, %d to simulate, %d matches scored", code, frac * 100,
                 len(played), len(fixtures), len(window))
    return {"outcomes": outcome_records, "matches": match_records}


def three_way_scores(records: list[dict[str, Any]], key: str) -> dict[str, float] | None:
    recs = [r for r in records if key in r]
    if not recs:
        return None
    P = np.array([r[key] for r in recs])
    Y = np.zeros_like(P)
    Y[np.arange(len(recs)), [r["actual"] for r in recs]] = 1
    p_act = np.clip(P[np.arange(len(recs)), [r["actual"] for r in recs]], EPS, 1)
    return {"brier": round(float(np.mean(np.sum((P - Y) ** 2, axis=1))), 4),
            "log_loss": round(float(-np.mean(np.log(p_act))), 4), "n": int(len(recs))}


def summarise(season: str, leagues: list[str], outcomes: list[dict[str, Any]], matches: list[dict[str, Any]],
              params: ModelParams, n_sims: int, n_draws: int = 100) -> dict[str, Any]:
    by_outcome: dict[str, Any] = {}
    for outcome in OUTCOME_LABELS:
        recs = [r for r in outcomes if r["outcome"] == outcome]
        if not recs:
            continue
        y = np.array([r["actual"] for r in recs])
        by_outcome[outcome] = {
            "label": OUTCOME_LABELS[outcome],
            "model": scores(np.array([r["model"] for r in recs]), y),
            "no_ratings": scores(np.array([r["no_ratings"] for r in recs]), y),
            "uniform": scores(np.array([r["uniform"] for r in recs]), y),
        }
    by_checkpoint = []
    for frac in CHECKPOINTS:
        recs = [r for r in outcomes if r["checkpoint"] == frac]
        y = np.array([r["actual"] for r in recs])
        by_checkpoint.append({
            "fraction": frac,
            "model": scores(np.array([r["model"] for r in recs]), y),
            "no_ratings": scores(np.array([r["no_ratings"] for r in recs]), y),
            "uniform": scores(np.array([r["uniform"] for r in recs]), y),
        })
    # Calibration of the model's outcome probabilities.
    p_all = np.array([r["model"] for r in outcomes])
    y_all = np.array([r["actual"] for r in outcomes])
    calibration = []
    for lo, hi in zip(CAL_EDGES[:-1], CAL_EDGES[1:]):
        sel = (p_all >= lo) & (p_all < hi)
        if sel.sum() == 0:
            continue
        calibration.append({"bin": f"{int(lo * 100)}–{int(min(hi, 1) * 100)}%", "n": int(sel.sum()),
                            "predicted": round(float(p_all[sel].mean()), 3), "observed": round(float(y_all[sel].mean()), 3)})
    match_scores = {
        "model": three_way_scores(matches, "model"),
        "bookmaker": three_way_scores(matches, "bookmaker"),
        "uniform": {"brier": round(2 / 3, 4), "log_loss": round(float(np.log(3)), 4), "n": len(matches)},
        "n_with_bookmaker": sum(1 for r in matches if "bookmaker" in r),
    }
    # Plain-language summary.
    lines: list[str] = []
    all_y = y_all
    all_model = np.array([r["model"] for r in outcomes])
    all_uni = np.array([r["uniform"] for r in outcomes])
    all_flat = np.array([r["no_ratings"] for r in outcomes])
    skill_uni = 1 - brier(all_model, all_y) / brier(all_uni, all_y)
    skill_flat = 1 - brier(all_model, all_y) / brier(all_flat, all_y)
    lines.append(
        f"We re-ran the model at ten points during the {season} season in all five leagues, each time using only "
        f"the results known at that moment, and compared its title, Champions League, European and relegation "
        f"probabilities with what actually happened ({len(outcomes)} team-outcome forecasts in total)."
    )
    lines.append(
        f"Measured by the Brier score (lower is better, 0 is perfect), the model's forecasts were "
        f"{skill_uni * 100:.0f}% better than giving every team the same chance, and {skill_flat * 100:.0f}% better "
        f"than a version that knows the current table but treats every team as equally strong. That second "
        f"number is the value the team ratings add on top of the points already won."
    )
    t = by_outcome.get("title")
    if t:
        lines.append(
            f"Title forecasts scored {t['model']['brier']:.3f} against {t['no_ratings']['brier']:.3f} for the "
            f"table-only version; relegation forecasts scored {by_outcome['relegation']['model']['brier']:.3f} "
            f"against {by_outcome['relegation']['no_ratings']['brier']:.3f}."
        )
    good_bins = [c for c in calibration if c["n"] >= 30 and 0.2 <= c["predicted"] <= 0.8]
    if good_bins:
        c = max(good_bins, key=lambda c: c["n"])
        lines.append(
            f"Calibration check: when the model gave something a chance in the {c['bin']} range (on average "
            f"{c['predicted'] * 100:.0f}%), it happened {c['observed'] * 100:.0f}% of the time across {c['n']} cases."
        )
    mb = match_scores["bookmaker"]
    mm = match_scores["model"]
    if mb and mm:
        rel = (mm["log_loss"] - mb["log_loss"]) / mb["log_loss"] * 100
        lines.append(
            f"On individual matches, the model's win/draw/loss forecasts had a log loss of {mm['log_loss']:.3f} "
            f"versus {mb['log_loss']:.3f} for the bookmakers' pre-match odds over {mb['n']} matches, i.e. "
            f"{abs(rel):.1f}% {'worse' if rel > 0 else 'better'} than the market, which uses far more information "
            f"(injuries, line-ups, transfers) than results alone."
        )
    return {
        "season": season,
        "leagues": leagues,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "n_sims": n_sims,
        "n_rating_draws": n_draws,
        "checkpoints": CHECKPOINTS,
        "model_params": {"xi": params.xi, "half_life_days": round(params.half_life_days, 1),
                         "prior_strength": params.prior_strength,
                         "promoted_prior": {"attack": params.promoted_attack, "defence": params.promoted_defence}},
        "outcome_scores": by_outcome,
        "by_checkpoint": by_checkpoint,
        "calibration": calibration,
        "match_scores": match_scores,
        "skill_vs_uniform": round(skill_uni, 4),
        "skill_vs_no_ratings": round(skill_flat, 4),
        "summary": lines,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--config-season", default="2026-27")
    parser.add_argument("--leagues")
    parser.add_argument("--sims", type=int, default=3000)
    parser.add_argument("--xi", type=float)
    parser.add_argument("--prior-strength", type=float)
    parser.add_argument("--history-seasons", type=int)
    parser.add_argument("--draws", type=int, help="rating draws per simulation batch (1 = ignore rating uncertainty)")
    parser.add_argument("--out", default=str(DATA_DIR / "backtest.json"))
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    model_cfg = json.loads((CONFIG_DIR / "model.json").read_text(encoding="utf-8"))
    params = ModelParams.from_dict(model_cfg)
    if args.xi is not None:
        params.xi = args.xi
    if args.prior_strength is not None:
        params.prior_strength = args.prior_strength
    history_seasons = args.history_seasons or int(model_cfg.get("history_seasons", 2))
    n_draws = args.draws if args.draws is not None else (
        int(model_cfg.get("n_rating_draws", 100)) if model_cfg.get("rating_uncertainty", True) else 1)
    codes = [c.strip().upper() for c in args.leagues.split(",")] if args.leagues else LEAGUE_ORDER

    outcomes: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    for code in codes:
        cfg = load_league(args.config_season, code)
        res = run_league(cfg, args.season, params, args.sims, history_seasons, n_draws)
        outcomes.extend(res["outcomes"])
        matches.extend(res["matches"])
    report = summarise(args.season, codes, outcomes, matches, params, args.sims, n_draws)
    print(json.dumps({k: report[k] for k in ("outcome_scores", "match_scores", "calibration",
                                              "skill_vs_uniform", "skill_vs_no_ratings")}, indent=1))
    print("\n".join(report["summary"]))
    if not args.no_write:
        out = __import__("pathlib").Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
