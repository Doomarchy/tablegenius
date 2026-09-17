"""European-place allocation evaluated inside every simulated season.

The league configs describe the *base* allocation (how many league places go to each
competition) and the domestic cups that add places. Given the final positions of one
simulated season, `allocate` hands out places the way the leagues do:

  1. The top `ucl` positions go to the Champions League league phase, then any
     `ucl_qualifying` positions to its qualifying rounds.
  2. Each cup winner takes the place its cup grants, unless it has already qualified for
     that competition or a higher one, in which case the place passes down the league
     table to the next best team without a European place.
  3. League places for the Europa League and then the Conference League are filled in
     table order, skipping teams that already hold a place.

A cup whose winner is not yet known is treated the way the site's assumption says: as if
the winner also qualified through the league, so its place passes down. A cup won by a
club outside the league ("external") gives nothing to the table. The optional extra
Champions League place (European Performance Spot) adds one league-phase place.
"""
from __future__ import annotations

from typing import Any, Hashable, Sequence

import numpy as np

TeamId = Hashable

NONE, UCL, UCLQ, UEL, UECL = 0, 1, 2, 3, 4
CODES = {UCL: "ucl", UCLQ: "ucl_qualifying", UEL: "uel", UECL: "uecl"}


def base_places(cfg: dict[str, Any]) -> dict[str, int]:
    """Base league places per competition, from `european_places` or derived from the
    (assumption-laden) zones by removing the passed-down cup places."""
    ep = cfg.get("european_places")
    if ep:
        return {"ucl": int(ep.get("ucl", 0)), "ucl_qualifying": int(ep.get("ucl_qualifying", 0)),
                "uel": int(ep.get("uel", 0)), "uecl": int(ep.get("uecl", 0))}
    z = cfg["zones"]

    def size(key: str) -> int:
        p = z.get(key, {}).get("positions")
        return p[1] - p[0] + 1 if p else 0

    cups = cfg.get("domestic_cups", [])
    uel_cups = sum(1 for c in cups if c.get("grants") == "uel")
    uecl_cups = sum(1 for c in cups if c.get("grants") == "uecl")
    return {"ucl": size("ucl"), "ucl_qualifying": size("ucl_qualifying"),
            "uel": max(size("uel") - uel_cups, 0), "uecl": max(size("uecl") - uecl_cups, 0)}


def resolve_cups(cfg: dict[str, Any], teams: dict[TeamId, dict[str, Any]]) -> list[dict[str, Any]]:
    """Cups with their winner resolved to a team id, "external", or None (undecided)."""
    out = []
    for cup in cfg.get("domestic_cups", []):
        winner = cup.get("winner")
        resolved: Any = None
        if winner in ("external", "non-league"):
            resolved = "external"
        elif winner is not None:
            for tid, t in teams.items():
                if winner == tid or str(winner) == str(tid) or winner in (t.get("name"), t.get("short_name"), t.get("tla")):
                    resolved = tid
                    break
            if resolved is None:
                raise ValueError(f"{cfg['code']}: cup winner {winner!r} for {cup.get('name')} is not a team in the league")
        out.append({"name": cup.get("name"), "grants": cup.get("grants"), "winner": resolved})
    return out


def allocate(cfg: dict[str, Any], positions: np.ndarray, team_ids: Sequence[TeamId],
             cups: Sequence[dict[str, Any]], extra_ucl: bool = False) -> np.ndarray:
    """European place per team for a batch of simulated seasons.

    positions: (N, n) final position (1-based) of each team index in each simulation.
    Returns (N, n) int8 codes: 0 none, 1 UCL, 2 UCL qualifying, 3 UEL, 4 UECL.
    """
    N, n = positions.shape
    idx = {t: i for i, t in enumerate(team_ids)}
    base = base_places(cfg)
    direct = base["ucl"] + (1 if extra_ucl else 0)
    qual = base["ucl_qualifying"]
    by_pos = np.argsort(positions, axis=1, kind="stable")          # (N, n): team index at each position
    comp = np.zeros((N, n), dtype=np.int8)
    rows = np.arange(N)

    for p in range(min(direct, n)):
        comp[rows, by_pos[:, p]] = UCL
    for p in range(direct, min(direct + qual, n)):
        comp[rows, by_pos[:, p]] = UCLQ
    next_pos = direct + qual

    def hand_out(grant: int, slots: np.ndarray) -> None:
        """Fill `slots[s]` league places of competition `grant` from position next_pos down."""
        remaining = slots.astype(int).copy()
        for p in range(next_pos, n):
            if not remaining.any():
                break
            team = by_pos[:, p]
            free = (comp[rows, team] == NONE) & (remaining > 0)
            comp[rows[free], team[free]] = grant
            remaining[free] -= 1

    for grant_code, grant_name in ((UEL, "uel"), (UECL, "uecl")):
        slots = np.full(N, base[grant_name], dtype=int)
        for cup in cups:
            if cup.get("grants") != grant_name:
                continue
            winner = cup.get("winner")
            if winner is None:
                slots += 1                      # undecided: assumed to pass down the table
            elif winner == "external":
                continue                        # taken by a club outside the league
            else:
                w = idx[winner]
                already = comp[:, w] != NONE
                slots[already] += 1             # passes down
                comp[~already, w] = grant_code  # the winner takes it
        hand_out(grant_code, slots)
    return comp


def european_probabilities(cfg: dict[str, Any], positions: np.ndarray, team_ids: Sequence[TeamId],
                           cups: Sequence[dict[str, Any]], extra_ucl_probability: float = 0.0) -> dict[str, np.ndarray]:
    """P(UCL direct), P(UCL qualifying), P(UEL), P(UECL) per team, mixing in the extra
    Champions League place with the given probability."""
    def probs(extra: bool) -> dict[str, np.ndarray]:
        comp = allocate(cfg, positions, team_ids, cups, extra_ucl=extra)
        return {name: (comp == code).mean(axis=0) for code, name in CODES.items()}

    p = float(np.clip(extra_ucl_probability, 0.0, 1.0))
    without = probs(False)
    if p <= 0:
        return without
    with_extra = probs(True)
    return {k: (1 - p) * without[k] + p * with_extra[k] for k in without}
