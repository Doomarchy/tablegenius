"""Probability history: one snapshot per matchday, re-created "as of" the end of each
past matchday so a team's chances can be charted through the season.

history.json per league:
  {"league", "season", "model_version", "updated_at",
   "snapshots": [{"matchday", "label", "as_of", "complete", "teams": {id: {...}}}, ...]}

Matchday 0 is the pre-season view (history and priors only). Snapshots of completed
matchdays are frozen once written; the snapshot of the matchday in progress is replaced
on every update with the live probabilities, so the last point of the chart always
agrees with the table.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .dataset import assemble_live, parse_date
from .model import ModelParams, fit, sample_ratings
from .simulate import simulate, team_probabilities
from .standings import build_standings, is_finished

log = logging.getLogger(__name__)

SNAPSHOT_KEYS = ("title", "ucl", "uel", "uecl", "europe", "relegation_playoff", "relegation",
                 "expected_points", "expected_position")
GRACE = timedelta(hours=3)


def model_version(model_cfg: dict[str, Any]) -> str:
    keys = ("time_decay_xi_per_day", "prior_strength", "promoted_prior", "history_seasons", "rating_uncertainty",
            "n_rating_draws", "max_goals", "rho_bounds")
    return hashlib.sha1(json.dumps({k: model_cfg.get(k) for k in keys}, sort_keys=True).encode()).hexdigest()[:10]


def matchday_ends(matches: list[dict[str, Any]], now: datetime) -> dict[int, datetime]:
    """Matchdays whose playable matches are all finished, with the time the last one ended."""
    ends: dict[int, datetime] = {}
    by_md: dict[int, list[dict[str, Any]]] = {}
    for m in matches:
        if m.get("matchday") and m["status"] not in ("POSTPONED", "CANCELLED", "SUSPENDED"):
            by_md.setdefault(m["matchday"], []).append(m)
    for md, ms in by_md.items():
        if all(is_finished(m) for m in ms):
            end = max(parse_date(m["utc_date"]) for m in ms) + GRACE
            if end <= now:
                ends[md] = end
    return ends


def live_matchday(matches: list[dict[str, Any]]) -> int:
    finished = [m["matchday"] for m in matches if is_finished(m) and m.get("matchday")]
    return max(finished) if finished else 0


def snapshot_from_probs(probs: dict[Any, dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in rows:
        p = probs.get(r["id"])
        if not p:
            continue
        rec = {k: round(float(p[k]), 4) for k in SNAPSHOT_KEYS}
        rec["position"] = r["position"]
        rec["points"] = r["points"]
        rec["played"] = r["played"]
        rec["attack"] = round(float(p.get("attack", 0.0)), 4)
        rec["defence"] = round(float(p.get("defence", 0.0)), 4)
        out[str(r["id"])] = rec
    return out


def compute_snapshot(cfg: dict[str, Any], matches: list[dict[str, Any]], teams: dict[Any, dict[str, Any]],
                     as_of: datetime, params: ModelParams, model_cfg: dict[str, Any], n_sims: int, seed: int) -> dict[str, Any]:
    """Re-run the model as if `as_of` were now."""
    played_matches = [m for m in matches if is_finished(m) and parse_date(m["utc_date"]) < as_of]
    table = build_standings(played_matches, teams, cfg)
    team_ids = [r["id"] for r in table["teams"]]
    data = assemble_live(cfg, played_matches, team_ids, as_of, params, int(model_cfg.get("history_seasons", 2)))
    ratings = fit(data, params)
    n_draws = int(model_cfg.get("n_rating_draws", 100)) if model_cfg.get("rating_uncertainty", True) else 1
    draws = sample_ratings(ratings, n_draws, np.random.default_rng(seed + 1), params.rho_bounds)
    played = [(m["home_id"], m["away_id"], m["home_goals"], m["away_goals"]) for m in played_matches]
    fixtures = [(m["home_id"], m["away_id"]) for m in matches
                if m["status"] != "CANCELLED" and not (is_finished(m) and parse_date(m["utc_date"]) < as_of)]
    sim = simulate(cfg, ratings, team_ids, played, fixtures, n_sims=n_sims, seed=seed, max_goals=params.max_goals,
                   ratings_draws=draws)
    probs = team_probabilities(cfg, sim, ratings)
    return snapshot_from_probs(probs, table["teams"])


def update_history(cfg: dict[str, Any], matches: list[dict[str, Any]], teams: dict[Any, dict[str, Any]],
                   rows: list[dict[str, Any]], live_probs: dict[Any, dict[str, Any]] | None,
                   model_cfg: dict[str, Any], path: Path, now: datetime | None = None) -> dict[str, Any]:
    """Bring history.json up to date: backfill missing completed matchdays, refresh the live point."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    version = model_version(model_cfg)
    params = ModelParams.from_dict(model_cfg)
    n_sims = int(model_cfg.get("history_simulations", 5000))
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    snaps: dict[int, dict[str, Any]] = {}
    if existing.get("model_version") == version:
        for s in existing.get("snapshots", []):
            snaps[int(s["matchday"])] = s
    else:
        if existing:
            log.info("%s: model parameters changed, rebuilding the whole history", cfg["code"])

    dates = [parse_date(m["utc_date"]) for m in matches]
    season_start = min(dates) if dates else now
    ends = matchday_ends(matches, now)
    live = live_matchday(matches)
    total_days = cfg["rounds"] * (cfg["team_count"] - 1)
    computed = 0

    # Pre-season point.
    if 0 not in snaps:
        as_of = season_start - timedelta(days=1)
        snaps[0] = {"matchday": 0, "label": "Pre-season", "as_of": as_of.isoformat() + "Z", "complete": True,
                    "teams": compute_snapshot(cfg, matches, teams, as_of, params, model_cfg, n_sims, seed=7)}
        computed += 1

    # Completed matchdays other than the live one are frozen once written.
    for md, end in sorted(ends.items()):
        if md == live:
            continue
        if md in snaps and snaps[md].get("complete"):
            continue
        snaps[md] = {"matchday": md, "label": f"Matchday {md}", "as_of": end.isoformat() + "Z", "complete": True,
                     "teams": compute_snapshot(cfg, matches, teams, end, params, model_cfg, n_sims, seed=1000 + md)}
        computed += 1

    # The live point: the matchday in progress (or just completed), from the live model.
    if live > 0 and live_probs:
        snaps[live] = {"matchday": live, "label": f"Matchday {live}", "as_of": now.isoformat() + "Z",
                       "complete": live in ends, "teams": snapshot_from_probs(live_probs, rows)}

    ordered = [snaps[k] for k in sorted(snaps)]
    payload = {
        "league": cfg["code"], "season": cfg["season"], "model_version": version,
        "updated_at": now.replace(microsecond=0).isoformat() + "Z", "total_matchdays": total_days,
        "snapshots": ordered,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    log.info("%s: history has %d snapshots (%d computed this run)", cfg["code"], len(ordered), computed)
    return payload
