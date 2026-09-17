"""Sanity checks run before any league file is written. A failure keeps the previous files
in place and fails the run, which the workflow turns into a GitHub issue."""
from __future__ import annotations

import math
from typing import Any

from .standings import is_finished

TOL = 0.02


def _finite01(v: Any) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v) and -1e-9 <= v <= 1 + 1e-9


def validate_league_output(cfg: dict[str, Any], standings: dict[str, Any], matches: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    rows = standings.get("teams", [])
    n = cfg["team_count"]
    if len(rows) != n:
        problems.append(f"{len(rows)} teams in the table, config says {n}")
    positions = sorted(r["position"] for r in rows)
    if positions != list(range(1, len(rows) + 1)):
        problems.append("positions are not 1..n")
    for r in rows:
        if r["played"] != r["won"] + r["drawn"] + r["lost"]:
            problems.append(f"{r['name']}: played != W+D+L")
        if r["points"] != 3 * r["won"] + r["drawn"] - r.get("deduction", 0):
            problems.append(f"{r['name']}: points do not match record")
        if r["gd"] != r["gf"] - r["ga"]:
            problems.append(f"{r['name']}: goal difference inconsistent")
    played = sum(1 for m in matches if is_finished(m))
    total = cfg["rounds"] * n * (n - 1) // 2
    if matches and len(matches) < total * 0.9:
        problems.append(f"only {len(matches)} of {total} matches in the fixture list")
    if played > total:
        problems.append(f"{played} finished matches exceeds {total}")

    probs = [r.get("probs") for r in rows]
    if any(probs):
        if not all(probs):
            problems.append("some teams have probabilities and others do not")
        else:
            for r in rows:
                p = r["probs"]
                for key in ("title", "ucl", "uel", "uecl", "europe", "relegation", "relegation_playoff", "expected_position"):
                    v = p.get(key)
                    if key == "expected_position":
                        if not (isinstance(v, (int, float)) and math.isfinite(v) and 1 - 1e-6 <= v <= n + 1e-6):
                            problems.append(f"{r['name']}: expected position {v} out of range")
                    elif not _finite01(v):
                        problems.append(f"{r['name']}: {key} = {v} is not a probability")
                if abs(sum(p.get("positions", [])) - 1) > TOL:
                    problems.append(f"{r['name']}: position distribution does not sum to 1")
            title_sum = sum(r["probs"]["title"] for r in rows)
            if abs(title_sum - 1) > TOL:
                problems.append(f"title probabilities sum to {title_sum:.3f}")
            rel = cfg["zones"].get("relegation", {}).get("positions")
            if rel:
                rel_sum = sum(r["probs"]["relegation"] for r in rows)
                expected = rel[1] - rel[0] + 1
                if abs(rel_sum - expected) > TOL * expected:
                    problems.append(f"relegation probabilities sum to {rel_sum:.3f}, expected {expected}")
            for r in rows:
                if r["probs"].get("expected_points", 0) < r["points"] - 1e-6:
                    problems.append(f"{r['name']}: expected points below current points")
    return problems
