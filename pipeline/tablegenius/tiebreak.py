"""Rank teams that are level on points using a league's real tiebreak criteria.

Criteria names (as used in the league config files):
  points, goal_difference, goals_for, wins, away_wins, away_goals,
  h2h_points, h2h_goal_difference, h2h_goals_for, h2h_away_goals,
  fair_play, playoff, drawing_of_lots

`fair_play`, `playoff` and `drawing_of_lots` cannot be computed from results, so a tie
that reaches one of them is handed to the `final` callback (alphabetical for display,
random for simulations) and the teams are flagged as tied.
"""
from __future__ import annotations

from typing import Callable, Hashable, Iterable, Sequence

TeamId = Hashable
Result = tuple[TeamId, TeamId, int, int]  # home, away, home_goals, away_goals

H2H_CRITERIA = {"h2h_points", "h2h_goal_difference", "h2h_goals_for", "h2h_away_goals"}
TERMINAL_CRITERIA = {"fair_play", "playoff", "drawing_of_lots"}
OVERALL_CRITERIA = {"points", "goal_difference", "goals_for", "wins", "away_wins", "away_goals"}


def h2h_table(group: Iterable[TeamId], results: Iterable[Result]) -> dict[TeamId, dict[str, int]]:
    """Mini-league among `group` using only the matches they played against each other."""
    members = set(group)
    table = {t: {"points": 0, "goal_difference": 0, "goals_for": 0, "away_goals": 0, "played": 0} for t in members}
    for home, away, hg, ag in results:
        if home not in members or away not in members:
            continue
        th, ta = table[home], table[away]
        th["played"] += 1
        ta["played"] += 1
        th["goals_for"] += hg
        ta["goals_for"] += ag
        ta["away_goals"] += ag
        th["goal_difference"] += hg - ag
        ta["goal_difference"] += ag - hg
        if hg > ag:
            th["points"] += 3
        elif hg < ag:
            ta["points"] += 3
        else:
            th["points"] += 1
            ta["points"] += 1
    return table


def rank(
    team_ids: Sequence[TeamId],
    stats: dict[TeamId, dict[str, int]],
    results: Sequence[Result],
    criteria: Sequence[str],
    rounds: int = 2,
    h2h_requires_all_played: bool = True,
    final: Callable[[list[TeamId]], list[TeamId]] | None = None,
) -> tuple[list[TeamId], set[TeamId], dict[TeamId, str]]:
    """Order teams best-first.

    Returns (ordered_ids, still_tied_ids, resolved_by) where resolved_by maps a team to
    the first criterion that separated it from the teams it was level with on points.
    """
    unknown = set(criteria) - H2H_CRITERIA - TERMINAL_CRITERIA - OVERALL_CRITERIA
    if unknown:
        raise ValueError(f"Unknown tiebreak criteria: {sorted(unknown)}")
    final = final or (lambda group: sorted(group, key=str))
    resolved_by: dict[TeamId, str] = {}
    tied: set[TeamId] = set()

    def resolve(group: list[TeamId]) -> list[TeamId]:
        if len(group) == 1:
            return group
        h2h = None
        for crit in criteria:
            if crit in TERMINAL_CRITERIA:
                break
            if crit in H2H_CRITERIA:
                if h2h is None:
                    h2h = h2h_table(group, results)
                needed = rounds * (len(group) - 1)
                if h2h_requires_all_played and any(h2h[t]["played"] < needed for t in group):
                    continue
                metric = crit[len("h2h_"):]
                values = {t: h2h[t][metric] for t in group}
            else:
                values = {t: stats[t].get(crit, 0) for t in group}
            distinct = sorted(set(values.values()), reverse=True)
            if len(distinct) > 1:
                ordered: list[TeamId] = []
                for v in distinct:
                    sub = [t for t in group if values[t] == v]
                    for t in sub:
                        resolved_by.setdefault(t, crit)
                    # Restart the criteria for the sub-group (head-to-head is recomputed
                    # among the teams that are still level).
                    ordered.extend(resolve(sub))
                return ordered
        tied.update(group)
        return final(list(group))

    by_points: dict[int, list[TeamId]] = {}
    for t in team_ids:
        by_points.setdefault(stats[t]["points"], []).append(t)
    ordered: list[TeamId] = []
    for pts in sorted(by_points, reverse=True):
        ordered.extend(resolve(by_points[pts]))
    return ordered, tied, resolved_by
