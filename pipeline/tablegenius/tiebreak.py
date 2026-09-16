"""Rank teams that are level on points using a league's real tiebreak criteria.

Criteria names (as used in the league config files):
  points, goal_difference, goals_for, wins, away_wins, away_goals,
  h2h_points, h2h_goal_difference, h2h_goals_for, h2h_away_goals,
  fair_play, playoff, drawing_of_lots

`fair_play`, `playoff` and `drawing_of_lots` cannot be computed from results, so a tie
that reaches one of them is handed to the `final` callback (alphabetical for display,
random for simulations) and the teams are flagged as tied.

`resolve_group` is the generic engine: it only needs a `metric(criterion, group)` callback,
so the live table (dict-based stats) and the Monte Carlo simulation (numpy arrays) share
exactly the same resolution logic.
"""
from __future__ import annotations

from typing import Callable, Hashable, Iterable, Sequence

TeamId = Hashable
Result = tuple[TeamId, TeamId, int, int]  # home, away, home_goals, away_goals

H2H_CRITERIA = {"h2h_points", "h2h_goal_difference", "h2h_goals_for", "h2h_away_goals"}
TERMINAL_CRITERIA = {"fair_play", "playoff", "drawing_of_lots"}
OVERALL_CRITERIA = {"points", "goal_difference", "goals_for", "wins", "away_wins", "away_goals"}


def validate_criteria(criteria: Sequence[str]) -> None:
    unknown = set(criteria) - H2H_CRITERIA - TERMINAL_CRITERIA - OVERALL_CRITERIA
    if unknown:
        raise ValueError(f"Unknown tiebreak criteria: {sorted(unknown)}")


def leading_overall_criteria(criteria: Sequence[str]) -> list[str]:
    """The overall (non head-to-head) criteria that come before the first head-to-head or
    terminal criterion. These can be applied in bulk before any group resolution."""
    out: list[str] = []
    for c in criteria:
        if c in OVERALL_CRITERIA:
            out.append(c)
        else:
            break
    return out


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


def resolve_group(
    group: list[TeamId],
    criteria: Sequence[str],
    metric: Callable[[str, list[TeamId]], dict[TeamId, float]],
    h2h_complete: Callable[[list[TeamId]], bool],
    final: Callable[[list[TeamId]], list[TeamId]],
    resolved_by: dict[TeamId, str] | None = None,
    tied: set[TeamId] | None = None,
) -> list[TeamId]:
    """Order a group of teams that are level on the leading criteria.

    Criteria are applied in order; when one separates the group, each resulting sub-group
    is resolved again from the first criterion (head-to-head is then recomputed among the
    teams still level, which is how the leagues apply it). A group that reaches a
    terminal criterion is handed to `final`.
    """
    if len(group) == 1:
        return list(group)
    for crit in criteria:
        if crit in TERMINAL_CRITERIA:
            break
        if crit in H2H_CRITERIA and not h2h_complete(group):
            continue
        values = metric(crit, group)
        distinct = sorted(set(values.values()), reverse=True)
        if len(distinct) > 1:
            ordered: list[TeamId] = []
            for v in distinct:
                sub = [t for t in group if values[t] == v]
                if resolved_by is not None:
                    for t in sub:
                        resolved_by.setdefault(t, crit)
                ordered.extend(resolve_group(sub, criteria, metric, h2h_complete, final, resolved_by, tied))
            return ordered
    if tied is not None:
        tied.update(group)
    return final(list(group))


def rank(
    team_ids: Sequence[TeamId],
    stats: dict[TeamId, dict[str, int]],
    results: Sequence[Result],
    criteria: Sequence[str],
    rounds: int = 2,
    h2h_requires_all_played: bool = True,
    final: Callable[[list[TeamId]], list[TeamId]] | None = None,
) -> tuple[list[TeamId], set[TeamId], dict[TeamId, str]]:
    """Order teams best-first from per-team stats and the list of results.

    Returns (ordered_ids, still_tied_ids, resolved_by) where resolved_by maps a team to
    the first criterion that separated it from the teams it was level with on points.
    """
    validate_criteria(criteria)
    final = final or (lambda group: sorted(group, key=str))
    resolved_by: dict[TeamId, str] = {}
    tied: set[TeamId] = set()
    cache: dict[frozenset, dict] = {}

    def h2h_for(group: list[TeamId]) -> dict:
        key = frozenset(group)
        if key not in cache:
            cache[key] = h2h_table(group, results)
        return cache[key]

    def metric(crit: str, group: list[TeamId]) -> dict[TeamId, float]:
        if crit in H2H_CRITERIA:
            table = h2h_for(group)
            name = crit[len("h2h_"):]
            return {t: table[t][name] for t in group}
        return {t: stats[t].get(crit, 0) for t in group}

    def h2h_complete(group: list[TeamId]) -> bool:
        if not h2h_requires_all_played:
            return True
        table = h2h_for(group)
        needed = rounds * (len(group) - 1)
        return all(table[t]["played"] >= needed for t in group)

    by_points: dict[int, list[TeamId]] = {}
    for t in team_ids:
        by_points.setdefault(stats[t]["points"], []).append(t)
    ordered: list[TeamId] = []
    for pts in sorted(by_points, reverse=True):
        ordered.extend(resolve_group(by_points[pts], criteria, metric, h2h_complete, final, resolved_by, tied))
    return ordered, tied, resolved_by
