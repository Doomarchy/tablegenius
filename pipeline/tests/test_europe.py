import numpy as np

from tablegenius.europe import NONE, UCL, UCLQ, UECL, UEL, allocate, base_places, european_probabilities, resolve_cups

CFG = {
    "code": "T", "team_count": 8, "rounds": 2,
    # England-like: one league Europa place plus the Cup, and the Conference place only via the League Cup.
    "european_places": {"ucl": 2, "ucl_qualifying": 0, "uel": 1, "uecl": 0},
    "domestic_cups": [{"name": "Cup", "grants": "uel", "winner": None}, {"name": "League Cup", "grants": "uecl", "winner": None}],
    "zones": {"ucl": {"positions": [1, 2]}, "ucl_qualifying": {"positions": None}, "uel": {"positions": [3, 4]},
              "uecl": {"positions": [5, 5]}, "relegation_playoff": {"positions": None}, "relegation": {"positions": [8, 8]}},
}
TEAMS = list("ABCDEFGH")
POS = np.array([[1, 2, 3, 4, 5, 6, 7, 8]])  # A first ... H last


def cups(**winners):
    out = []
    for c in CFG["domestic_cups"]:
        out.append(dict(c, winner=winners.get(c["name"])))
    return out


def codes(comp):
    return {t: int(comp[0, i]) for i, t in enumerate(TEAMS)}


def test_base_places_derived_from_zones_when_not_given():
    cfg = dict(CFG)
    del cfg["european_places"]
    assert base_places(cfg) == {"ucl": 2, "ucl_qualifying": 0, "uel": 1, "uecl": 0}


def test_undecided_cups_pass_down_like_the_site_assumption():
    c = codes(allocate(CFG, POS, TEAMS, cups()))
    assert c == {"A": UCL, "B": UCL, "C": UEL, "D": UEL, "E": UECL, "F": NONE, "G": NONE, "H": NONE}


def test_cup_winner_outside_the_places_takes_the_place():
    # G (7th) win the cup: they take the UEL place, so only 3rd gets UEL via the league,
    # and the League Cup (undecided) still passes down: UECL goes to 4th.
    c = codes(allocate(CFG, POS, TEAMS, cups(Cup="G")))
    assert c["G"] == UEL and c["C"] == UEL and c["D"] == UECL and c["E"] == NONE


def test_cup_winner_already_in_champions_league_passes_down():
    c = codes(allocate(CFG, POS, TEAMS, cups(Cup="A")))
    assert c == codes(allocate(CFG, POS, TEAMS, cups()))


def test_league_cup_winner_in_uel_places_passes_uecl_down():
    # D (4th) win the League Cup but D already get UEL via the league (with the cup passing down).
    c = codes(allocate(CFG, POS, TEAMS, cups(**{"Cup": None, "League Cup": "D"})))
    assert c["D"] == UEL and c["E"] == UECL


def test_external_winner_removes_a_place():
    c = codes(allocate(CFG, POS, TEAMS, cups(Cup="external")))
    assert c["C"] == UEL and c["D"] == UECL and c["E"] == NONE


def test_extra_champions_league_place_mixing():
    probs = european_probabilities(CFG, POS, TEAMS, cups(), extra_ucl_probability=0.5)
    assert abs(probs["ucl"][2] - 0.5) < 1e-9          # C: UCL only in the extra-place world
    assert abs(probs["uel"][2] - 0.5) < 1e-9
    assert abs(probs["uel"][4] - 0.5) < 1e-9          # E: UEL when places shift, UECL otherwise
    assert abs(probs["uecl"][5] - 0.5) < 1e-9


def test_qualifying_round_places():
    cfg = dict(CFG, european_places={"ucl": 3, "ucl_qualifying": 1, "uel": 1, "uecl": 1})
    c = codes(allocate(cfg, POS, TEAMS, cups()))
    assert c["C"] == UCL and c["D"] == UCLQ and c["E"] == UEL and c["F"] == UEL and c["G"] == UECL


def test_resolve_cups_by_name_or_id():
    teams = {1: {"name": "Alpha FC", "short_name": "Alpha", "tla": "ALP"}, 2: {"name": "Beta", "short_name": "Beta", "tla": "BET"}}
    cfg = {"code": "T", "domestic_cups": [{"name": "Cup", "grants": "uel", "winner": "Alpha"}, {"name": "LC", "grants": "uecl", "winner": 2},
                                          {"name": "X", "grants": "uel", "winner": "external"}, {"name": "Y", "grants": "uel", "winner": None}]}
    r = resolve_cups(cfg, teams)
    assert [c["winner"] for c in r] == [1, 2, "external", None]
