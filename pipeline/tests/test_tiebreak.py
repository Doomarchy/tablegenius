from tablegenius.standings import build_standings
from tablegenius.tiebreak import rank

PL_CRITERIA = ["points", "goal_difference", "goals_for", "h2h_points", "h2h_away_goals", "playoff"]
LALIGA_CRITERIA = ["points", "h2h_points", "h2h_goal_difference", "goal_difference", "goals_for", "fair_play", "playoff"]
BUNDESLIGA_CRITERIA = ["points", "goal_difference", "goals_for", "h2h_goal_difference", "h2h_away_goals", "away_goals", "playoff"]


def stats(**teams):
    """stats(A=(pts, gd, gf), ...) -> stats dict."""
    return {name: {"points": p, "goal_difference": gd, "goals_for": gf, "wins": 0, "away_wins": 0, "away_goals": 0}
            for name, (p, gd, gf) in teams.items()}


def test_goal_difference_before_head_to_head_in_premier_league():
    s = stats(A=(10, 5, 20), B=(10, 8, 15))
    results = [("A", "B", 2, 0), ("B", "A", 0, 1)]  # A won both meetings
    order, tied, by = rank(["A", "B"], s, results, PL_CRITERIA)
    assert order == ["B", "A"]
    assert by["A"] == "goal_difference"


def test_head_to_head_before_goal_difference_in_laliga():
    s = stats(A=(10, 5, 20), B=(10, 8, 15))
    results = [("A", "B", 2, 0), ("B", "A", 0, 1)]
    order, tied, by = rank(["A", "B"], s, results, LALIGA_CRITERIA)
    assert order == ["A", "B"]
    assert by["A"] == "h2h_points"
    assert not tied


def test_head_to_head_skipped_until_both_matches_played():
    s = stats(A=(10, 5, 20), B=(10, 8, 15))
    results = [("A", "B", 2, 0)]  # only one meeting so far
    order, _, by = rank(["A", "B"], s, results, LALIGA_CRITERIA, h2h_requires_all_played=True)
    assert order == ["B", "A"]
    assert by["B"] == "goal_difference"


def test_three_way_tie_restarts_criteria_for_subgroup():
    # LaLiga: mini-league among A, B, C. A beats both; B and C are level in the
    # mini-league, so B vs C is resolved by their own head-to-head after the restart.
    s = stats(A=(10, 0, 10), B=(10, 3, 10), C=(10, 2, 10))
    results = [
        ("A", "B", 1, 0), ("B", "A", 0, 1),
        ("A", "C", 1, 0), ("C", "A", 0, 1),
        ("B", "C", 0, 2), ("C", "B", 1, 1),   # C wins the pair
    ]
    order, tied, _ = rank(["A", "B", "C"], s, results, LALIGA_CRITERIA)
    assert order == ["A", "C", "B"]
    assert not tied


def test_bundesliga_uses_aggregate_score_then_h2h_away_goals():
    s = stats(A=(10, 4, 12), B=(10, 4, 12))
    # Aggregate 2-2 across both meetings; A scored 2 away, B scored 0 away.
    results = [("A", "B", 0, 0), ("B", "A", 2, 2)]
    order, tied, by = rank(["A", "B"], s, results, BUNDESLIGA_CRITERIA)
    assert order == ["A", "B"]
    assert by["A"] == "h2h_away_goals"


def test_unresolvable_tie_is_flagged_and_uses_final_callback():
    s = stats(A=(10, 4, 12), B=(10, 4, 12))
    results = [("A", "B", 1, 1), ("B", "A", 1, 1)]
    order, tied, _ = rank(["A", "B"], s, results, PL_CRITERIA, final=lambda g: sorted(g, reverse=True))
    assert order == ["B", "A"]
    assert tied == {"A", "B"}


def test_build_standings_end_to_end():
    cfg = {
        "code": "T", "team_count": 3, "rounds": 2, "tiebreakers": PL_CRITERIA,
        "h2h_requires_all_matches_played": True,
        "zones": {"ucl": {"positions": [1, 1]}, "relegation": {"positions": [3, 3]}},
    }
    teams = {1: {"name": "Alpha"}, 2: {"name": "Beta"}, 3: {"name": "Gamma"}}
    matches = [
        {"id": 1, "utc_date": "2026-08-01T14:00:00Z", "matchday": 1, "status": "FINISHED", "home_id": 1, "away_id": 2, "home_goals": 2, "away_goals": 1},
        {"id": 2, "utc_date": "2026-08-08T14:00:00Z", "matchday": 2, "status": "FINISHED", "home_id": 3, "away_id": 1, "home_goals": 0, "away_goals": 0},
        {"id": 3, "utc_date": "2026-08-15T14:00:00Z", "matchday": 3, "status": "TIMED", "home_id": 2, "away_id": 3, "home_goals": None, "away_goals": None},
    ]
    out = build_standings(matches, teams, cfg)
    rows = out["teams"]
    assert [r["name"] for r in rows] == ["Alpha", "Gamma", "Beta"]
    assert rows[0]["points"] == 4 and rows[0]["form"] == ["W", "D"] and rows[0]["zone"] == "ucl"
    assert rows[2]["zone"] == "relegation"
    assert out["matchday"]["current"] == 3 and out["matchday"]["matches_played"] == 2
