"""Pipeline entry point.

    python -m tablegenius.run --season 2026-27                 # live data (needs FOOTBALL_DATA_TOKEN)
    python -m tablegenius.run --season 2026-27 --source csv    # preview from football-data.co.uk, no token
    python -m tablegenius.run --no-model                       # tables only
    python -m tablegenius.run --force-model                    # re-run the model even if no result changed

Writes, per league, site/public/data/<season>/<CODE>/standings.json (table, probabilities,
clinch statuses, scenarios), matches.json (results, fixtures and match forecasts) and
history.json (probabilities by matchday), plus site/public/data/index.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv

from .clinch import current_statuses, scenarios
from .config import LEAGUE_ORDER, load_league
from .dataset import assemble_live
from .europe import resolve_cups
from .fetch import FootballDataClient
from .history import fetch_season_csv
from .model import ModelParams, Ratings, fit, sample_ratings, score_matrix, outcome_probs
from .odds import market_odds
from .paths import CACHE_DIR, CONFIG_DIR, DATA_DIR, ENV_FILE
from .simulate import simulate, team_probabilities
from .snapshots import update_history
from .sources import normalize_csv_matches, normalize_org_matches, normalize_org_standings
from .standings import build_standings, is_finished, point_deductions
from .validate import validate_league_output

log = logging.getLogger("tablegenius")

MODEL_CONFIG = CONFIG_DIR / "model.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any | None:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def league_meta(cfg: dict[str, Any]) -> dict[str, Any]:
    keys = ["code", "name", "country", "season", "team_count", "rounds", "tiebreakers", "zones",
            "assumptions", "domestic_cups", "extra_ucl_place", "tied_title_playoff", "tied_relegation_playoff"]
    return {k: cfg.get(k) for k in keys}


def results_hash(matches: list[dict[str, Any]]) -> str:
    finished = sorted((str(m["id"]), int(m["home_goals"]), int(m["away_goals"])) for m in matches if is_finished(m))
    return hashlib.sha1(json.dumps(finished).encode()).hexdigest()


def compare_with_api(rows: list[dict[str, Any]], api_table: list[dict[str, Any]]) -> dict[str, Any]:
    """Cross-check our computed table against football-data.org's own standings."""
    if not api_table:
        return {"available": False}
    ours = {r["id"]: r for r in rows}
    diffs = []
    for api in api_table:
        mine = ours.get(api["team_id"])
        if mine is None:
            diffs.append({"team_id": api["team_id"], "issue": "missing from computed table"})
            continue
        if (mine["points"], mine["played"], mine["gd"]) != (api["points"], api["played"], api["goal_difference"]):
            diffs.append({"team": mine["name"], "issue": "totals differ",
                          "ours": [mine["played"], mine["points"], mine["gd"]],
                          "api": [api["played"], api["points"], api["goal_difference"]]})
        elif mine["position"] != api["position"]:
            diffs.append({"team": mine["name"], "issue": "position differs (tiebreak)",
                          "ours": mine["position"], "api": api["position"]})
    totals_match = not any(d["issue"] != "position differs (tiebreak)" for d in diffs)
    return {"available": True, "totals_match": totals_match, "diffs": diffs}


def fixture_forecasts(draws: list[Ratings], matches: list[dict[str, Any]], max_goals: int) -> dict[Any, dict[str, float]]:
    """Win/draw/loss chances and expected goals for every unfinished fixture, averaged over rating draws."""
    pending = [m for m in matches if not is_finished(m) and m["status"] != "CANCELLED"
               and m["home_id"] in draws[0].index and m["away_id"] in draws[0].index]
    if not pending:
        return {}
    home = [m["home_id"] for m in pending]
    away = [m["away_id"] for m in pending]
    acc = np.zeros((len(pending), 3))
    xg = np.zeros((len(pending), 2))
    for r in draws:
        lam, mu = r.expected_goals(home, away)
        acc += outcome_probs(score_matrix(lam, mu, r.rho, max_goals))
        xg += np.stack([lam, mu], axis=1)
    acc /= len(draws)
    xg /= len(draws)
    return {m["id"]: {"home": round(float(acc[i, 0]), 4), "draw": round(float(acc[i, 1]), 4), "away": round(float(acc[i, 2]), 4),
                      "xg_home": round(float(xg[i, 0]), 2), "xg_away": round(float(xg[i, 1]), 2)}
            for i, m in enumerate(pending)}


def rules_hash(cfg: dict[str, Any]) -> str:
    """Hash of the rule settings that change probabilities without a new result."""
    keys = ("zones", "european_places", "extra_ucl_probability", "domestic_cups", "points_deductions",
            "relegation_playoff_survival", "tiebreakers", "tied_title_playoff", "tied_relegation_playoff")
    return hashlib.sha1(json.dumps({k: cfg.get(k) for k in keys}, sort_keys=True, default=str).encode()).hexdigest()[:12]


def run_model(cfg: dict[str, Any], matches: list[dict[str, Any]], teams: dict[Any, dict[str, Any]],
              rows: list[dict[str, Any]], previous: dict[str, Any] | None, previous_matches: dict[str, Any] | None,
              model_cfg: dict[str, Any], force: bool, n_sims_override: int | None = None
              ) -> tuple[dict[Any, dict[str, Any]], dict[str, Any], dict[Any, dict[str, float]]]:
    """Fit ratings and simulate the season; reuse the previous run when nothing changed."""
    code = cfg["code"]
    h = results_hash(matches)
    rh = rules_hash(cfg)
    prev_model = (previous or {}).get("model")
    if (prev_model and prev_model.get("results_hash") == h and prev_model.get("rules_hash") == rh
            and prev_model.get("model_version") == model_version_of(model_cfg)
            and not force and n_sims_override is None
            and previous and all("probs" in r for r in previous.get("teams", []))):
        log.info("%s: no new results or rule changes since the last model run; keeping its probabilities", code)
        prev_forecasts = {m["id"]: m["forecast"] for m in (previous_matches or {}).get("matches", []) if m.get("forecast")}
        return {r["id"]: r["probs"] for r in previous["teams"]}, prev_model, prev_forecasts

    t0 = time.time()
    params = ModelParams.for_league(model_cfg, code)
    as_of = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    team_ids = [r["id"] for r in rows]
    data = assemble_live(cfg, matches, team_ids, as_of, params, int(model_cfg.get("history_seasons", 2)),
                         xg_weight=float(model_cfg.get("xg_weight", 0.0) or 0.0))
    ratings = fit(data, params)
    if not ratings.converged:
        log.warning("%s: optimiser did not report convergence", code)
    played = [(m["home_id"], m["away_id"], m["home_goals"], m["away_goals"]) for m in matches if is_finished(m)]
    fixtures = [(m["home_id"], m["away_id"]) for m in matches if not is_finished(m) and m["status"] != "CANCELLED"]
    n_sims = n_sims_override or int(model_cfg.get("n_simulations", 10000))
    seed = int(h[:8], 16)
    n_draws = int(model_cfg.get("n_rating_draws", 100)) if model_cfg.get("rating_uncertainty", True) else 1
    draws = sample_ratings(ratings, n_draws, np.random.default_rng(seed + 1), params.rho_bounds)
    deductions = point_deductions(cfg, teams)
    cups = resolve_cups(cfg, teams)
    sim = simulate(cfg, ratings, team_ids, played, fixtures, n_sims=n_sims, seed=seed, max_goals=params.max_goals,
                   ratings_draws=draws, point_adjustments={t: -p for t, p in deductions.items()})
    probs = team_probabilities(cfg, sim, ratings, cups=cups)
    forecasts = fixture_forecasts(draws, matches, params.max_goals)
    names = {r["id"]: r["short_name"] for r in rows}
    promoted = [names[t] for i, t in enumerate(team_ids) if not data.established[i]]
    model_block = {
        "as_of": as_of.isoformat() + "Z",
        "results_hash": h,
        "rules_hash": rh,
        "model_version": model_version_of(model_cfg),
        "xg_weight": float(model_cfg.get("xg_weight", 0.0) or 0.0),
        "xg_matches": int(getattr(data, "xg_matches", 0)),
        "n_sims": n_sims,
        "n_rating_draws": len(draws),
        "seed": seed,
        "fitted_matches": ratings.n_matches,
        "effective_matches": round(ratings.effective_matches, 1),
        "seasons": data.seasons,
        "home_advantage": round(ratings.home_advantage, 4),
        "intercept": round(ratings.intercept, 4),
        "avg_home_goals": round(math.exp(ratings.intercept + ratings.home_advantage), 3),
        "avg_away_goals": round(math.exp(ratings.intercept), 3),
        "rho": round(ratings.rho, 4),
        "xi": params.xi,
        "half_life_days": round(params.half_life_days, 1),
        "prior_strength": params.prior_strength,
        "promoted_prior": {"attack": params.promoted_attack, "defence": params.promoted_defence},
        "promoted_teams": promoted,
        "fixtures_remaining": len(fixtures),
        "converged": ratings.converged,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    log.info("%s: model fitted on %d matches (%.0f effective), %d fixtures simulated x %d in %.1fs; home adv %.3f, rho %.3f",
             code, ratings.n_matches, ratings.effective_matches, len(fixtures), n_sims, time.time() - t0,
             ratings.home_advantage, ratings.rho)
    return probs, model_block, forecasts


def model_version_of(model_cfg: dict[str, Any]) -> str:
    from .snapshots import model_version
    return model_version(model_cfg)


def rules_state(cfg: dict[str, Any], teams: dict[Any, dict[str, Any]]) -> dict[str, Any]:
    """The rule settings in force, in a form the site can display."""
    names = {tid: t.get("short_name") or t.get("name") for tid, t in teams.items()}
    cups = []
    for c in resolve_cups(cfg, teams):
        w = c["winner"]
        cups.append({"name": c["name"], "grants": c["grants"],
                     "winner": None if w is None else ("a club outside the league" if w == "external" else names.get(w, str(w)))})
    deductions = []
    for tid, pts in point_deductions(cfg, teams).items():
        reasons = [d.get("reason") for d in cfg.get("points_deductions", []) if str(d.get("team")) in (str(tid), teams[tid].get("name"), teams[tid].get("short_name"), teams[tid].get("tla"))]
        deductions.append({"team": names.get(tid), "points": pts, "reason": next((r for r in reasons if r), None)})
    return {
        "cups": cups,
        "deductions": deductions,
        "extra_ucl_probability": float(cfg.get("extra_ucl_probability", 0.0) or 0.0),
        "relegation_playoff_survival": cfg.get("relegation_playoff_survival"),
    }


def settle(cfg: dict[str, Any], rows: list[dict[str, Any]], matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Clinched/eliminated statuses, magic numbers and next-round scenarios for every team."""
    team_ids = [r["id"] for r in rows]
    points = {r["id"]: r["points"] for r in rows}
    remaining: dict[Any, int] = {t: 0 for t in team_ids}
    for m in matches:
        if not is_finished(m) and m["status"] != "CANCELLED":
            for side in ("home_id", "away_id"):
                if m[side] in remaining:
                    remaining[m[side]] += 1
    statuses = current_statuses(cfg, team_ids, points, remaining)
    names = {r["id"]: r["short_name"] for r in rows}
    sc = scenarios(cfg, team_ids, names, points, remaining, matches, statuses)
    for r in rows:
        r["status"] = statuses[r["id"]]["status"]
        r["magic"] = statuses[r["id"]]["magic"]
        r["remaining"] = remaining[r["id"]]
        r["scenarios"] = sc["teams"].get(r["id"], [])
    return {"matchday": sc["matchday"], "label": sc["label"], "fixtures": sc["fixtures"]}


def process_league(cfg: dict[str, Any], source: str, client: FootballDataClient | None, out_dir: Path,
                   model_cfg: dict[str, Any] | None, force_model: bool, n_sims: int | None,
                   skip_history: bool = False) -> dict[str, Any]:
    code = cfg["code"]
    src = cfg["sources"]
    if source == "api":
        assert client is not None
        comp, season_year = src["football_data_org"]["competition"], src["football_data_org"]["season"]
        matches, teams = normalize_org_matches(client.matches(comp, season_year))
        api_table = normalize_org_standings(client.standings(comp, season_year))
    else:
        text = fetch_season_csv(cfg["season"], src["football_data_co_uk"]["code"], force=True)
        matches, teams = normalize_csv_matches(text)
        api_table = []

    if len(teams) != cfg["team_count"]:
        log.warning("%s: found %d teams, config says %d", code, len(teams), cfg["team_count"])

    table = build_standings(matches, teams, cfg)
    check = compare_with_api(table["teams"], api_table)
    if check.get("available"):
        if check["totals_match"]:
            log.info("%s: totals match football-data.org (%d ordering diffs)", code, len(check["diffs"]))
        else:
            log.warning("%s: totals DIFFER from football-data.org: %s", code, check["diffs"])

    league_dir = out_dir / cfg["season"] / code
    previous = read_json(league_dir / "standings.json")
    previous_matches = read_json(league_dir / "matches.json")
    model_block = None
    probs: dict[Any, dict[str, Any]] | None = None
    forecasts: dict[Any, dict[str, float]] = {}
    if model_cfg is not None and source == "api":
        try:
            probs, model_block, forecasts = run_model(cfg, matches, teams, table["teams"], previous, previous_matches,
                                                      model_cfg, force_model, n_sims)
            for row in table["teams"]:
                row["probs"] = probs.get(row["id"])
        except Exception as exc:
            log.error("%s: model failed, writing table without probabilities: %s", code, exc, exc_info=True)
            model_block = None
            probs = None

    next_round = settle(cfg, table["teams"], matches) if source == "api" else None
    market: dict[Any, dict[str, Any]] = {}
    if source == "api":
        try:
            market = market_odds(cfg, matches, teams, CACHE_DIR)
        except Exception as exc:
            log.warning("%s: market odds unavailable: %s", code, exc)

    history_summary = None
    if model_cfg is not None and source == "api" and not skip_history:
        try:
            hist = update_history(cfg, matches, teams, table["teams"], probs, model_cfg, league_dir / "history.json")
            history_summary = {"snapshots": len(hist["snapshots"]), "updated_at": hist["updated_at"]}
        except Exception as exc:
            log.error("%s: history update failed: %s", code, exc, exc_info=True)

    updated = now_iso()
    standings = {
        "league": league_meta(cfg),
        "updated_at": updated,
        "source": "football-data.org" if source == "api" else "football-data.co.uk (preview)",
        "matchday": table["matchday"],
        "model": model_block,
        "rules": rules_state(cfg, teams) if source == "api" else None,
        "next_round": next_round,
        "history": history_summary,
        "teams": table["teams"],
        "source_check": check,
    }
    problems = validate_league_output(cfg, standings, matches)
    if problems:
        raise RuntimeError(f"{code}: output failed validation, previous files kept: " + "; ".join(problems))
    write_json(league_dir / "standings.json", standings)
    for m in matches:
        fc = forecasts.get(m["id"])
        if fc:
            m["forecast"] = fc
        mk = market.get(m["id"])
        if mk:
            m["market"] = mk
    write_json(league_dir / "matches.json", {
        "league": code,
        "season": cfg["season"],
        "updated_at": updated,
        "results_hash": results_hash(matches),
        "teams": list(teams.values()),
        "matches": matches,
    })
    log.info("%s: wrote %d teams, %d/%d matches played", code, len(table["teams"]),
             table["matchday"]["matches_played"], table["matchday"]["matches_total"])
    return {"code": code, "name": cfg["name"], "country": cfg["country"], "updated_at": updated,
            "matchday": table["matchday"]}


def write_index(season: str, out_dir: Path) -> None:
    """Rebuild index.json from whatever league files exist on disk."""
    leagues = []
    for code in LEAGUE_ORDER:
        path = out_dir / season / code / "standings.json"
        if not path.exists():
            continue
        s = json.loads(path.read_text(encoding="utf-8"))
        model = s.get("model") or {}
        leagues.append({"code": code, "name": s["league"]["name"], "country": s["league"]["country"],
                        "updated_at": s["updated_at"], "matchday": s["matchday"], "source": s.get("source"),
                        "has_probabilities": bool(model), "model_as_of": model.get("as_of"),
                        "has_history": (out_dir / season / code / "history.json").exists()})
    write_json(out_dir / "index.json", {
        "season": season,
        "updated_at": max((lg["updated_at"] for lg in leagues), default=now_iso()),
        "has_backtest": (out_dir / "backtest.json").exists(),
        "leagues": leagues,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TableGenius pipeline")
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--leagues", help="comma-separated codes, e.g. PL,PD (default: all)")
    parser.add_argument("--source", choices=["api", "csv"], default="api")
    parser.add_argument("--no-cache", action="store_true", help="ignore cached API responses")
    parser.add_argument("--no-model", action="store_true", help="tables only, skip ratings and simulation")
    parser.add_argument("--force-model", action="store_true", help="re-run the model even if no result changed")
    parser.add_argument("--no-history", action="store_true", help="skip the matchday history backfill")
    parser.add_argument("--sims", type=int, help="override the number of simulations")
    parser.add_argument("--out", type=Path, default=DATA_DIR)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv(ENV_FILE)

    codes = [c.strip().upper() for c in args.leagues.split(",")] if args.leagues else LEAGUE_ORDER
    client = None
    if args.source == "api":
        token = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
        if not token or token == "paste_your_token_here":
            print("Missing FOOTBALL_DATA_TOKEN. Copy .env.example to .env and paste your token, "
                  "or run with --source csv for a token-free preview.", file=sys.stderr)
            return 2
        client = FootballDataClient(token, CACHE_DIR, cache_ttl_seconds=0 if args.no_cache else 600)

    model_cfg = None if args.no_model else json.loads(MODEL_CONFIG.read_text(encoding="utf-8"))

    failures = 0
    for code in codes:
        cfg = load_league(args.season, code)
        try:
            process_league(cfg, args.source, client, args.out, model_cfg, args.force_model, args.sims, args.no_history)
        except Exception as exc:  # keep going so one league does not block the others
            failures += 1
            log.error("%s failed: %s", code, exc, exc_info=args.verbose)
    write_index(args.season, args.out)
    if client:
        log.info("API calls made: %d", client.calls_made)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
