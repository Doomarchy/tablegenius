"""Monte Carlo simulation of the rest of a season.

Every remaining fixture is sampled from the fitted Dixon-Coles score distribution, each
simulated final table is ranked with the league's real tiebreakers (the same engine used for
the live table), and the share of simulations in which a team finishes in each position
becomes its probability. When several rating draws are supplied, the simulations are split
between them so that uncertainty about the ratings themselves widens the forecasts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Hashable, Sequence

import numpy as np

from .config import ZONE_KEYS
from .model import Ratings, score_matrix
from .tiebreak import H2H_CRITERIA, leading_overall_criteria, resolve_group, validate_criteria

log = logging.getLogger(__name__)

TeamId = Hashable
KEY_OFFSET = 512
KEY_BASE = 1024


@dataclass
class SimulationResult:
    team_ids: list
    n_sims: int
    position_probs: np.ndarray       # (n, n): P(team i finishes in position j + 1)
    expected_points: np.ndarray
    expected_position: np.ndarray
    points_p5: np.ndarray
    points_p50: np.ndarray
    points_p95: np.ndarray
    current_points: np.ndarray
    max_points: np.ndarray
    matches_remaining: np.ndarray
    positions: np.ndarray | None = None   # (N, n) final position per simulation, for place allocation

    def zone_probs(self, cfg: dict[str, Any]) -> dict[str, np.ndarray]:
        out = {}
        for key in ZONE_KEYS:
            rng_ = cfg["zones"].get(key, {}).get("positions")
            if rng_:
                out[key] = self.position_probs[:, rng_[0] - 1:rng_[1]].sum(axis=1)
            else:
                out[key] = np.zeros(len(self.team_ids))
        return out


def simulate(
    cfg: dict[str, Any],
    ratings: Ratings,
    team_ids: Sequence[TeamId],
    played_results: Sequence[tuple[TeamId, TeamId, int, int]],
    fixtures: Sequence[tuple[TeamId, TeamId]],
    n_sims: int = 10000,
    seed: int = 0,
    max_goals: int = 10,
    ratings_draws: Sequence[Ratings] | None = None,
    point_adjustments: dict[TeamId, int] | None = None,
) -> SimulationResult:
    criteria = list(cfg["tiebreakers"])
    validate_criteria(criteria)
    team_ids = list(team_ids)
    n = len(team_ids)
    idx = {t: i for i, t in enumerate(team_ids)}
    rng = np.random.default_rng(seed)

    # ---- Current state from played matches ----
    base = {k: np.zeros(n) for k in ("points", "goals_for", "goals_against", "wins", "away_wins", "away_goals")}
    for t, adj in (point_adjustments or {}).items():
        if t in idx:
            base["points"][idx[t]] += adj      # points deductions (negative) or awards
    h2h_base = {k: np.zeros((n, n), dtype=np.int16) for k in ("points", "goal_difference", "goals_for", "away_goals")}
    for h, a, hg, ag in played_results:
        i, j = idx[h], idx[a]
        base["goals_for"][i] += hg
        base["goals_for"][j] += ag
        base["goals_against"][i] += ag
        base["goals_against"][j] += hg
        base["away_goals"][j] += ag
        h2h_base["goal_difference"][i, j] += hg - ag
        h2h_base["goal_difference"][j, i] += ag - hg
        h2h_base["goals_for"][i, j] += hg
        h2h_base["goals_for"][j, i] += ag
        h2h_base["away_goals"][j, i] += ag
        if hg > ag:
            base["points"][i] += 3
            base["wins"][i] += 1
            h2h_base["points"][i, j] += 3
        elif hg < ag:
            base["points"][j] += 3
            base["wins"][j] += 1
            base["away_wins"][j] += 1
            h2h_base["points"][j, i] += 3
        else:
            base["points"][i] += 1
            base["points"][j] += 1
            h2h_base["points"][i, j] += 1
            h2h_base["points"][j, i] += 1

    fixtures = [(h, a) for h, a in fixtures if h in idx and a in idx]
    F = len(fixtures)
    hi = np.array([idx[h] for h, _ in fixtures], dtype=int)
    ai = np.array([idx[a] for _, a in fixtures], dtype=int)
    remaining = np.bincount(hi, minlength=n) + np.bincount(ai, minlength=n)

    # ---- Sample every remaining fixture in every simulation ----
    K1 = max_goals + 1
    x = np.zeros((F, n_sims), dtype=np.int16)
    y = np.zeros((F, n_sims), dtype=np.int16)
    if F > 0:
        draws = list(ratings_draws) if ratings_draws else [ratings]
        home_ids = [h for h, _ in fixtures]
        away_ids = [a for _, a in fixtures]
        bounds = np.linspace(0, n_sims, len(draws) + 1).astype(int)
        for b, r in enumerate(draws):
            lo, hi_ = int(bounds[b]), int(bounds[b + 1])
            if hi_ <= lo:
                continue
            lam, mu = r.expected_goals(home_ids, away_ids)
            P = score_matrix(lam, mu, r.rho, max_goals).reshape(F, -1)
            cum = np.cumsum(P, axis=1)
            cum[:, -1] = 1.0
            u = rng.random((F, hi_ - lo))
            for f in range(F):
                flat = np.searchsorted(cum[f], u[f], side="right")
                x[f, lo:hi_] = flat // K1
                y[f, lo:hi_] = flat % K1
    hw = x > y
    dr = x == y
    aw = x < y
    hpts = (3 * hw + dr).astype(np.int16)
    apts = (3 * aw + dr).astype(np.int16)

    Hm = np.zeros((F, n))
    Am = np.zeros((F, n))
    if F > 0:
        Hm[np.arange(F), hi] = 1.0
        Am[np.arange(F), ai] = 1.0

    def acc(home_vals: np.ndarray, away_vals: np.ndarray) -> np.ndarray:
        return home_vals.T.astype(float) @ Hm + away_vals.T.astype(float) @ Am

    pts = base["points"] + acc(hpts, apts)
    gf = base["goals_for"] + acc(x, y)
    ga = base["goals_against"] + acc(y, x)
    overall = {
        "points": pts,
        "goal_difference": gf - ga,
        "goals_for": gf,
        "wins": base["wins"] + acc(hw, aw),
        "away_wins": base["away_wins"] + aw.T.astype(float) @ Am,
        "away_goals": base["away_goals"] + y.T.astype(float) @ Am,
    }

    need_h2h = any(c in H2H_CRITERIA for c in criteria)
    H: dict[str, np.ndarray] = {}
    if need_h2h:
        for k, v in h2h_base.items():
            H[k] = np.broadcast_to(v, (n_sims, n, n)).copy()
        for f in range(F):
            i, j = hi[f], ai[f]
            H["points"][:, i, j] += hpts[f]
            H["points"][:, j, i] += apts[f]
            d = x[f] - y[f]
            H["goal_difference"][:, i, j] += d
            H["goal_difference"][:, j, i] -= d
            H["goals_for"][:, i, j] += x[f]
            H["goals_for"][:, j, i] += y[f]
            H["away_goals"][:, j, i] += y[f]

    # ---- Rank each simulated table ----
    lead = leading_overall_criteria(criteria)
    key = np.zeros((n_sims, n))
    for c in lead:
        key = key * KEY_BASE + (overall[c] + KEY_OFFSET)
    order = np.argsort(-key, axis=1, kind="stable")
    sorted_key = np.take_along_axis(key, order, axis=1)
    has_tie = (np.diff(sorted_key, axis=1) == 0).any(axis=1)

    def final(group: list) -> list:
        return [int(v) for v in rng.permutation(group)]

    def h2h_complete(_: list) -> bool:
        return True

    for s in np.flatnonzero(has_tie):
        row = order[s]
        k = sorted_key[s]

        def metric(crit: str, group: list, s=s) -> dict:
            if crit in H2H_CRITERIA:
                A = H[crit[len("h2h_"):]][s]
                g = np.asarray(group)
                return {t: int(A[t, g].sum()) for t in group}
            arr = overall[crit][s]
            return {t: float(arr[t]) for t in group}

        i = 0
        while i < n:
            j = i
            while j + 1 < n and k[j + 1] == k[i]:
                j += 1
            if j > i:
                group = [int(t) for t in row[i:j + 1]]
                row[i:j + 1] = resolve_group(group, criteria, metric, h2h_complete, final)
            i = j + 1

    # Special end-of-season play-offs (Serie A): ties on points for 1st, or across the
    # relegation line, are decided by a play-off, which we treat as a coin flip.
    if cfg.get("tied_title_playoff") or cfg.get("tied_relegation_playoff"):
        pts_sorted = np.take_along_axis(pts, order, axis=1)
        rel = cfg["zones"].get("relegation", {}).get("positions")
        title_ties = np.flatnonzero(pts_sorted[:, 0] == pts_sorted[:, 1]) if cfg.get("tied_title_playoff") else []
        for s in title_ties:
            top = pts_sorted[s, 0]
            k_top = int(np.searchsorted(-pts_sorted[s], -top, side="right"))
            order[s, :k_top] = rng.permutation(order[s, :k_top])
        if cfg.get("tied_relegation_playoff") and rel and rel[0] >= 2:
            a, c = rel[0] - 2, rel[0] - 1
            for s in np.flatnonzero(pts_sorted[:, a] == pts_sorted[:, c]):
                v = pts_sorted[s, a]
                lo, hi_ = a, c
                while lo > 0 and pts_sorted[s, lo - 1] == v:
                    lo -= 1
                while hi_ + 1 < n and pts_sorted[s, hi_ + 1] == v:
                    hi_ += 1
                order[s, lo:hi_ + 1] = rng.permutation(order[s, lo:hi_ + 1])

    positions = np.empty((n_sims, n), dtype=np.int32)
    np.put_along_axis(positions, order, np.broadcast_to(np.arange(1, n + 1), (n_sims, n)), axis=1)

    position_probs = np.zeros((n, n))
    for t in range(n):
        position_probs[t] = np.bincount(positions[:, t] - 1, minlength=n) / n_sims
    q5, q50, q95 = np.percentile(pts, [5, 50, 95], axis=0)
    return SimulationResult(
        team_ids=team_ids, n_sims=n_sims, position_probs=position_probs,
        expected_points=pts.mean(axis=0), expected_position=positions.mean(axis=0),
        points_p5=q5, points_p50=q50, points_p95=q95,
        current_points=base["points"], max_points=base["points"] + 3 * remaining,
        matches_remaining=remaining.astype(float), positions=positions.astype(np.int16),
    )


def team_probabilities(cfg: dict[str, Any], sim: SimulationResult, ratings: Ratings | None = None,
                       cups: Sequence[dict[str, Any]] | None = None) -> dict[TeamId, dict[str, Any]]:
    """Per-team probability dict ready for JSON.

    European places are allocated inside each simulated season (cup winners, pass-down,
    optional extra Champions League place) when the per-simulation positions are
    available; otherwise they fall back to the configured zones.
    """
    zones = sim.zone_probs(cfg)
    euro = None
    if sim.positions is not None:
        from .europe import european_probabilities  # local import keeps module dependencies one-way
        euro = european_probabilities(cfg, sim.positions, sim.team_ids, cups if cups is not None else cfg.get("domestic_cups", []),
                                      float(cfg.get("extra_ucl_probability", 0.0) or 0.0))
    survival = float(cfg.get("relegation_playoff_survival", 0.5))
    out: dict[TeamId, dict[str, Any]] = {}
    for i, t in enumerate(sim.team_ids):
        if euro is not None:
            ucl_direct, ucl_q, uel, uecl = (float(euro[k][i]) for k in ("ucl", "ucl_qualifying", "uel", "uecl"))
        else:
            ucl_direct, ucl_q, uel, uecl = (float(zones[k][i]) for k in ("ucl", "ucl_qualifying", "uel", "uecl"))
        playoff = float(zones["relegation_playoff"][i])
        relegation = float(zones["relegation"][i])
        d: dict[str, Any] = {
            "title": float(sim.position_probs[i, 0]),
            "ucl": ucl_direct + ucl_q,
            "ucl_direct": ucl_direct,
            "ucl_qualifying": ucl_q,
            "uel": uel,
            "uecl": uecl,
            "europe": ucl_direct + ucl_q + uel + uecl,
            "relegation_playoff": playoff,
            "relegation": relegation,
            "relegation_total": relegation + playoff * (1.0 - survival),
            "expected_points": float(sim.expected_points[i]),
            "expected_position": float(sim.expected_position[i]),
            "points_p5": float(sim.points_p5[i]),
            "points_p50": float(sim.points_p50[i]),
            "points_p95": float(sim.points_p95[i]),
            "max_points": float(sim.max_points[i]),
            "matches_remaining": int(sim.matches_remaining[i]),
            "positions": [round(float(p), 5) for p in sim.position_probs[i]],
        }
        if ratings is not None and t in ratings.index:
            d.update(ratings.team_rating(t))
        out[t] = d
    return out
