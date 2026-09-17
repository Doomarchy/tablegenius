import numpy as np

from tablegenius.clinch import ALIVE, CLINCHED, ELIMINATED, current_statuses, outcome_ranges, scenarios, status_arrays

CFG = {
    "team_count": 4, "rounds": 2,
    "zones": {
        "ucl": {"positions": [1, 2]}, "ucl_qualifying": {"positions": None}, "uel": {"positions": [3, 3]},
        "uecl": {"positions": None}, "relegation_playoff": {"positions": None}, "relegation": {"positions": [4, 4]},
    },
}
TEAMS = ["A", "B", "C", "D"]
NAMES = {t: t for t in TEAMS}


def fixture(mid, home, away, matchday=10, date="2027-05-22T14:00:00Z"):
    return {"id": mid, "utc_date": date, "matchday": matchday, "status": "TIMED",
            "home_id": home, "away_id": away, "home_goals": None, "away_goals": None}


def test_outcome_ranges():
    r = outcome_ranges(CFG)
    assert r["title"] == (1, 1) and r["ucl"] == (1, 2) and r["europe"] == (1, 3) and r["relegation"] == (4, 4)


def test_status_arrays_are_conservative_about_ties():
    pts = np.array([[30.0, 27.0, 20.0, 10.0]])
    maxp = np.array([[33.0, 30.0, 23.0, 13.0]])   # one match left each
    cl, el = status_arrays(pts, maxp, 1, 1)
    assert not cl[0, 0]          # B could still draw level, and ties count against A
    assert el[0].tolist() == [False, False, True, True]
    cl2, el2 = status_arrays(pts, maxp, 4, 4)     # relegation spot
    assert cl2[0, 3] and not el2[0, 3]            # D is down: three teams are beyond its reach
    assert el2[0, 0] and el2[0, 1]                 # A and B are safe


def test_current_statuses_and_magic_numbers():
    points = {"A": 30, "B": 27, "C": 20, "D": 10}
    remaining = {"A": 1, "B": 1, "C": 1, "D": 1}
    s = current_statuses(CFG, TEAMS, points, remaining)
    assert s["A"]["status"]["title"] == ALIVE and s["C"]["status"]["title"] == ELIMINATED
    assert s["A"]["status"]["ucl"] == CLINCHED and s["B"]["status"]["ucl"] == CLINCHED
    assert s["D"]["status"]["relegation"] == CLINCHED and s["A"]["status"]["relegation"] == ELIMINATED
    assert s["A"]["magic"]["title"] == 1          # one more point puts A beyond B's reach
    assert s["B"]["magic"]["title"] is None       # B cannot guarantee the title alone
    assert s["C"]["magic"]["safety"] == 0


def test_scenarios_phrase_the_simplest_condition():
    points = {"A": 30, "B": 27, "C": 20, "D": 10}
    remaining = {"A": 1, "B": 1, "C": 1, "D": 1}
    matches = [fixture(1, "A", "B"), fixture(2, "C", "D")]
    statuses = current_statuses(CFG, TEAMS, points, remaining)
    sc = scenarios(CFG, TEAMS, NAMES, points, remaining, matches, statuses)
    assert sc["matchday"] == 10 and sc["label"] == "this weekend"
    a_lines = [x["text"] for x in sc["teams"]["A"]]
    assert "Clinch the title this weekend by avoiding defeat." in a_lines
    b_lines = [x["text"] for x in sc["teams"]["B"]]
    assert any(t.startswith("Are out of the title race this weekend") and "fail to win" in t for t in b_lines)


def test_scenario_with_rival_condition_and_non_playing_team():
    # A (30) and B (28) chase the title; A do not play this round, B play C.
    points = {"A": 30, "B": 28, "C": 20, "D": 10}
    remaining = {"A": 1, "B": 1, "C": 1, "D": 2}
    matches = [fixture(1, "B", "C"), fixture(2, "A", "D", matchday=11, date="2027-05-29T14:00:00Z"),
               fixture(3, "D", "C", matchday=11, date="2027-05-29T14:00:00Z")]
    statuses = current_statuses(CFG, TEAMS, points, remaining)
    sc = scenarios(CFG, TEAMS, NAMES, points, remaining, matches, statuses)
    assert sc["fixtures"] == [1]
    a_lines = [x["text"] for x in sc["teams"]["A"]]
    # A cannot clinch on their own (they do not play), but any dropped point by B leaves B's maximum below 30.
    assert "Clinch the title this weekend if B fail to win." in a_lines
    b_lines = [x["text"] for x in sc["teams"]["B"]]
    # A draw or a defeat both leave B short of 30, so the weakest phrasing is "fail to win".
    assert "Are out of the title race this weekend if they fail to win." in b_lines
