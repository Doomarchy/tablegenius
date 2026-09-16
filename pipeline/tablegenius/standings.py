"""Build a league table from a list of matches, applying the league's tiebreakers."""
from __future__ import annotations

from typing import Any

from .config import zone_for_position
from .tiebreak import rank

FINISHED_STATUSES = {"FINISHED", "AWARDED"}
FORM_LENGTH = 5


def is_finished(match: dict[str, Any]) -> bool:
    return (
        match["status"] in FINISHED_STATUSES
        and match["home_goals"] is not None
        and match["away_goals"] is not None
    )


def compute_stats(matches: list[dict[str, Any]], team_ids: list[Any]) -> tuple[dict[Any, dict[str, Any]], list[tuple]]:
    """Per-team totals plus the flat list of finished results used for head-to-head."""
    stats = {
        tid: {
            "played": 0, "won": 0, "drawn": 0, "lost": 0,
            "goals_for": 0, "goals_against": 0, "goal_difference": 0, "points": 0,
            "wins": 0, "away_wins": 0, "away_goals": 0,
            "home": {"played": 0, "won": 0, "drawn": 0, "lost": 0, "goals_for": 0, "goals_against": 0, "points": 0},
            "away": {"played": 0, "won": 0, "drawn": 0, "lost": 0, "goals_for": 0, "goals_against": 0, "points": 0},
            "results": [],  # chronological list of "W"/"D"/"L"
        }
        for tid in team_ids
    }
    results: list[tuple] = []
    finished = sorted((m for m in matches if is_finished(m)), key=lambda m: (m["utc_date"], str(m["id"])))
    for m in finished:
        h, a, hg, ag = m["home_id"], m["away_id"], m["home_goals"], m["away_goals"]
        if h not in stats or a not in stats:
            raise KeyError(f"Match {m['id']} references a team not in the league: {h} vs {a}")
        results.append((h, a, hg, ag))
        _apply(stats[h], stats[h]["home"], hg, ag, is_home=True)
        _apply(stats[a], stats[a]["away"], ag, hg, is_home=False)
    return stats, results


def _apply(total: dict[str, Any], split: dict[str, Any], gf: int, ga: int, is_home: bool) -> None:
    for d in (total, split):
        d["played"] += 1
        d["goals_for"] += gf
        d["goals_against"] += ga
    total["goal_difference"] = total["goals_for"] - total["goals_against"]
    if not is_home:
        total["away_goals"] += gf
    if gf > ga:
        outcome, pts = "W", 3
        total["won"] += 1
        split["won"] += 1
        total["wins"] += 1
        if not is_home:
            total["away_wins"] += 1
    elif gf == ga:
        outcome, pts = "D", 1
        total["drawn"] += 1
        split["drawn"] += 1
    else:
        outcome, pts = "L", 0
        total["lost"] += 1
        split["lost"] += 1
    total["points"] += pts
    split["points"] += pts
    total["results"].append(outcome)


def build_standings(matches: list[dict[str, Any]], teams: dict[Any, dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Return {'teams': [rows best-first], 'matchday': {...}} for one league."""
    team_ids = list(teams)
    stats, results = compute_stats(matches, team_ids)
    order, tied, resolved_by = rank(
        team_ids, stats, results, cfg["tiebreakers"],
        rounds=cfg["rounds"],
        h2h_requires_all_played=cfg.get("h2h_requires_all_matches_played", True),
        final=lambda group: sorted(group, key=lambda t: teams[t]["name"]),
    )
    rows = []
    for pos, tid in enumerate(order, start=1):
        s = stats[tid]
        t = teams[tid]
        rows.append({
            "id": tid,
            "name": t["name"],
            "short_name": t.get("short_name") or t["name"],
            "tla": t.get("tla"),
            "crest": t.get("crest"),
            "position": pos,
            "zone": zone_for_position(cfg, pos),
            "played": s["played"],
            "won": s["won"],
            "drawn": s["drawn"],
            "lost": s["lost"],
            "gf": s["goals_for"],
            "ga": s["goals_against"],
            "gd": s["goal_difference"],
            "points": s["points"],
            "form": s["results"][-FORM_LENGTH:],
            "home": s["home"],
            "away": s["away"],
            "tied": tid in tied,
            "separated_by": resolved_by.get(tid),
        })
    total_matches = cfg["rounds"] * cfg["team_count"] * (cfg["team_count"] - 1) // 2
    played = sum(1 for m in matches if is_finished(m))
    unfinished_days = [m["matchday"] for m in matches if not is_finished(m) and m.get("matchday")]
    total_days = cfg["rounds"] * (cfg["team_count"] - 1)
    if unfinished_days:
        current = min(unfinished_days)
    elif played >= total_matches:
        current = total_days  # season complete
    else:
        current = None  # no fixture list available (e.g. CSV preview), so unknown
    return {
        "teams": rows,
        "matchday": {
            "current": current,
            "total": total_days,
            "matches_played": played,
            "matches_total": max(len(matches), total_matches),
        },
    }
