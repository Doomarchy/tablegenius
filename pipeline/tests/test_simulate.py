import numpy as np

from tablegenius.model import Ratings
from tablegenius.simulate import simulate, team_probabilities

CFG = {
    "code": "T", "team_count": 4, "rounds": 2,
    "tiebreakers": ["points", "h2h_points", "h2h_goal_difference", "goal_difference", "goals_for", "drawing_of_lots"],
    "zones": {
        "ucl": {"positions": [1, 1]}, "ucl_qualifying": {"positions": None}, "uel": {"positions": [2, 2]},
        "uecl": {"positions": None}, "relegation_playoff": {"positions": None}, "relegation": {"positions": [4, 4]},
    },
}
TEAMS = ["A", "B", "C", "D"]


def flat_ratings(attack=None):
    att = np.array(attack if attack else [0, 0, 0, 0], dtype=float)
    return Ratings(TEAMS, att, np.zeros(4), intercept=np.log(1.3), home_advantage=0.2, rho=-0.1,
                   n_matches=0, effective_matches=0, converged=True)


def test_no_fixtures_left_reproduces_the_final_table_exactly():
    # A beat everyone, D lost everything; B and C level on points, B won the head-to-head.
    played = [("A", "B", 2, 0), ("A", "C", 1, 0), ("A", "D", 3, 0), ("B", "C", 1, 0), ("C", "B", 1, 1),
              ("B", "D", 1, 0), ("C", "D", 2, 0), ("B", "A", 0, 1), ("C", "A", 0, 2), ("D", "A", 0, 1),
              ("D", "B", 0, 1), ("D", "C", 0, 1)]
    sim = simulate(CFG, flat_ratings(), TEAMS, played, [], n_sims=200, seed=1)
    probs = team_probabilities(CFG, sim)
    assert probs["A"]["title"] == 1.0 and probs["A"]["ucl"] == 1.0
    assert probs["B"]["uel"] == 1.0 and probs["C"]["uel"] == 0.0   # head-to-head decides B over C
    assert probs["D"]["relegation"] == 1.0
    assert abs(probs["A"]["expected_points"] - 18) < 1e-9 and probs["A"]["matches_remaining"] == 0


def test_probabilities_are_distributions_and_respond_to_strength():
    fixtures = [(h, a) for h in TEAMS for a in TEAMS if h != a]
    sim = simulate(CFG, flat_ratings([0.8, 0.0, 0.0, -0.8]), TEAMS, [], fixtures, n_sims=4000, seed=7)
    assert np.allclose(sim.position_probs.sum(axis=1), 1.0)
    assert np.allclose(sim.position_probs.sum(axis=0), 1.0)
    probs = team_probabilities(CFG, sim)
    assert probs["A"]["title"] > 0.6 > probs["B"]["title"] > probs["D"]["title"]
    assert probs["D"]["relegation"] > 0.5
    assert abs(sum(p["title"] for p in probs.values()) - 1.0) < 1e-9
    assert all(p["matches_remaining"] == 6 for p in probs.values())
    assert probs["A"]["expected_points"] > probs["D"]["expected_points"]


def test_unresolvable_ties_are_split_randomly():
    # Two identical teams, both matches drawn 0-0: the drawing of lots must give ~50/50.
    cfg = dict(CFG, team_count=2, zones={"ucl": {"positions": [1, 1]}, "relegation": {"positions": [2, 2]},
                                          "ucl_qualifying": {"positions": None}, "uel": {"positions": None},
                                          "uecl": {"positions": None}, "relegation_playoff": {"positions": None}})
    r = Ratings(["A", "B"], np.zeros(2), np.zeros(2), np.log(1.3), 0.2, -0.1, 0, 0, True)
    sim = simulate(cfg, r, ["A", "B"], [("A", "B", 0, 0), ("B", "A", 0, 0)], [], n_sims=2000, seed=3)
    p = team_probabilities(cfg, sim)
    assert 0.45 < p["A"]["title"] < 0.55


def test_serie_a_style_title_playoff_is_a_coin_flip_even_with_head_to_head_edge():
    cfg = dict(CFG, tied_title_playoff=True)
    # A and B both finish on 12 points; A won both meetings, so head-to-head alone gives A the title.
    played = [("A", "B", 1, 0), ("B", "A", 0, 1), ("A", "C", 0, 1), ("C", "A", 1, 0), ("B", "C", 1, 0), ("C", "B", 0, 1),
              ("A", "D", 1, 0), ("D", "A", 0, 1), ("B", "D", 1, 0), ("D", "B", 0, 1), ("C", "D", 0, 0), ("D", "C", 0, 0)]
    plain = team_probabilities(CFG, simulate(CFG, flat_ratings(), TEAMS, played, [], n_sims=100, seed=5))
    assert plain["A"]["title"] == 1.0 and plain["B"]["title"] == 0.0
    sim = simulate(cfg, flat_ratings(), TEAMS, played, [], n_sims=2000, seed=5)
    p = team_probabilities(cfg, sim)
    assert 0.45 < p["A"]["title"] < 0.55 and 0.45 < p["B"]["title"] < 0.55


def test_serie_a_style_relegation_playoff_is_a_coin_flip():
    cfg = dict(CFG, tied_relegation_playoff=True)
    # C and D both finish on 6 points; D won both meetings, so head-to-head alone relegates C.
    played = [("A", "B", 1, 0), ("B", "A", 0, 1), ("A", "C", 0, 1), ("C", "A", 1, 0), ("B", "C", 1, 0), ("C", "B", 0, 1),
              ("A", "D", 1, 0), ("D", "A", 0, 1), ("B", "D", 1, 0), ("D", "B", 0, 1), ("C", "D", 0, 1), ("D", "C", 1, 0)]
    plain = team_probabilities(CFG, simulate(CFG, flat_ratings(), TEAMS, played, [], n_sims=100, seed=5))
    assert plain["C"]["relegation"] == 1.0 and plain["D"]["relegation"] == 0.0
    p = team_probabilities(cfg, simulate(cfg, flat_ratings(), TEAMS, played, [], n_sims=2000, seed=5))
    assert 0.45 < p["C"]["relegation"] < 0.55 and 0.45 < p["D"]["relegation"] < 0.55
