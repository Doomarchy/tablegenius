"""Clinching, elimination and next-matchday scenarios.

Everything here is decided on points alone and is deliberately conservative about
tiebreakers: when checking whether a team has clinched something, any rival that could
still draw level on points is assumed to win the tiebreak; when checking whether a team
is eliminated, the team is assumed to win any tie. A "clinched" or "eliminated" verdict
is therefore always certain, at the price of reporting a few outcomes that are really
settled on goal difference a little later than a human would.

Next-matchday scenarios enumerate every result combination of the coming round and
describe, in plain English, the simplest combinations that would settle an outcome.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Hashable, Sequence

import numpy as np

from .standings import is_finished

TeamId = Hashable

ALIVE, CLINCHED, ELIMINATED = "alive", "clinched", "eliminated"
MAX_ENUMERATED_FIXTURES = 11
PLAYABLE = {"SCHEDULED", "TIMED", "IN_PLAY", "PAUSED"}


def outcome_ranges(cfg: dict[str, Any]) -> dict[str, tuple[int, int]]:
    """Position ranges (1-based, inclusive) for the outcomes we track."""
    z = cfg["zones"]
    n = cfg["team_count"]

    def p(key: str):
        return z.get(key, {}).get("positions")

    ucl, uclq, uel, uecl, rel, po = p("ucl"), p("ucl_qualifying"), p("uel"), p("uecl"), p("relegation"), p("relegation_playoff")
    out: dict[str, tuple[int, int]] = {"title": (1, 1)}
    out["ucl"] = (1, max(x[1] for x in (ucl, uclq) if x))
    out["europe"] = (1, max(x[1] for x in (ucl, uclq, uel, uecl) if x))
    if rel:
        out["relegation"] = (rel[0], n)
    if po:
        out["drop_zone"] = (min(po[0], rel[0]) if rel else po[0], n)
    return out


def status_arrays(pts: np.ndarray, maxp: np.ndarray, lo: int, hi: int) -> tuple[np.ndarray, np.ndarray]:
    """For a batch of point states, whether each team has certainly finished within
    [lo, hi] (clinched) or certainly outside it (eliminated).

    pts, maxp: (C, n) current points and maximum possible points per team.
    Returns (clinched, eliminated), each (C, n) bool.
    """
    n = pts.shape[-1]
    eye = np.eye(n, dtype=bool)[None]
    could_be_above = ((maxp[:, None, :] >= pts[:, :, None]) & ~eye).sum(-1)   # rivals that might finish above (ties count)
    certainly_above = ((pts[:, None, :] > maxp[:, :, None]) & ~eye).sum(-1)   # rivals already beyond reach
    certainly_below = ((maxp[:, None, :] < pts[:, :, None]) & ~eye).sum(-1)   # rivals that cannot catch us
    clinched = (could_be_above <= hi - 1) & (certainly_above >= lo - 1)
    eliminated = (certainly_above >= hi) | (certainly_below >= n - lo + 1)
    return clinched, eliminated


def _points_needed(pts: np.ndarray, maxp: np.ndarray, remaining: np.ndarray, i: int, threshold: float) -> int | None:
    need = max(0, int(threshold - pts[i] + 1))
    return None if need > 3 * remaining[i] else need


def magic_points(pts: np.ndarray, maxp: np.ndarray, remaining: np.ndarray, i: int, lo: int, hi: int) -> int | None:
    """Points team i still needs to guarantee finishing within [lo, hi] whatever rivals do
    (None if it cannot guarantee it on its own). Defined for top ranges (lo == 1)."""
    others = [j for j in range(len(pts)) if j != i]
    rivals_max = np.sort(maxp[others])[::-1]
    threshold = rivals_max[hi - 1] if hi - 1 < len(rivals_max) else -1.0
    return _points_needed(pts, maxp, remaining, i, threshold)


def safety_points(pts: np.ndarray, maxp: np.ndarray, remaining: np.ndarray, i: int, zone_lo: int) -> int | None:
    """Points team i needs to be certain of staying above a bottom zone starting at zone_lo."""
    n = len(pts)
    others = [j for j in range(n) if j != i]
    k = n - zone_lo + 1                       # rivals that must be unable to catch us
    threshold = np.sort(maxp[others])[k - 1]
    return _points_needed(pts, maxp, remaining, i, threshold)


def current_statuses(cfg: dict[str, Any], team_ids: Sequence[TeamId], points: dict[TeamId, int],
                     remaining: dict[TeamId, int]) -> dict[TeamId, dict[str, Any]]:
    """Clinched / eliminated / alive per outcome, plus magic numbers, for every team."""
    ids = list(team_ids)
    pts = np.array([points[t] for t in ids], dtype=float)
    rem = np.array([remaining[t] for t in ids], dtype=float)
    maxp = pts + 3 * rem
    ranges = outcome_ranges(cfg)
    out: dict[TeamId, dict[str, Any]] = {t: {"status": {}, "magic": {}} for t in ids}
    for name, (lo, hi) in ranges.items():
        cl, el = status_arrays(pts[None], maxp[None], lo, hi)
        for i, t in enumerate(ids):
            out[t]["status"][name] = CLINCHED if cl[0, i] else ELIMINATED if el[0, i] else ALIVE
            if lo == 1:
                out[t]["magic"][name] = magic_points(pts, maxp, rem, i, lo, hi)
            elif name == "relegation":
                out[t]["magic"]["safety"] = safety_points(pts, maxp, rem, i, lo)
    return out


# ---------------------------------------------------------------------------
# Next-matchday scenarios
# ---------------------------------------------------------------------------

def next_round(matches: list[dict[str, Any]]) -> tuple[int | None, list[dict[str, Any]]]:
    """The coming round: unfinished, playable fixtures of the lowest matchday number."""
    pending = [m for m in matches if not is_finished(m) and m["status"] in PLAYABLE and m.get("matchday")]
    if not pending:
        return None, []
    md = min(m["matchday"] for m in pending)
    fixtures = sorted((m for m in pending if m["matchday"] == md), key=lambda m: m["utc_date"])
    return md, fixtures[:MAX_ENUMERATED_FIXTURES]


def round_label(fixtures: list[dict[str, Any]]) -> str:
    weekend = 0
    for m in fixtures:
        d = datetime.fromisoformat(m["utc_date"].replace("Z", "+00:00")).astimezone(timezone.utc)
        if d.weekday() in (5, 6):
            weekend += 1
    return "this weekend" if fixtures and weekend * 2 >= len(fixtures) else "in midweek"


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


@dataclass
class Cond:
    rival: str          # rival team id (as string) the condition is about
    fixture: int        # fixture index
    strength: int       # 0 = weak ("fail to win"), 1 = strong ("lose")
    with_phrase: str    # "... with a win and {with_phrase}"
    if_phrase: str      # "... if {if_phrase}"
    mask: np.ndarray


VERBS = {
    ("clinch", "title"): "Clinch the title",
    ("clinch", "ucl"): "Clinch a Champions League place",
    ("clinch", "europe"): "Clinch a European place",
    ("clinch", "relegation"): "Are relegated",
    ("clinch", "drop_zone"): "Are certain to finish in the relegation zone",
    ("eliminate", "title"): "Are out of the title race",
    ("eliminate", "ucl"): "Can no longer reach the Champions League places",
    ("eliminate", "europe"): "Are out of the European places",
    ("eliminate", "relegation"): "Are safe from automatic relegation",
    ("eliminate", "drop_zone"): "Are safe from the relegation zone",
}


def scenarios(cfg: dict[str, Any], team_ids: Sequence[TeamId], names: dict[TeamId, str],
              points: dict[TeamId, int], remaining: dict[TeamId, int], matches: list[dict[str, Any]],
              statuses: dict[TeamId, dict[str, Any]], max_lines: int = 3) -> dict[str, Any]:
    """Plain-English lines describing what the coming round can settle, per team."""
    md, fixtures = next_round(matches)
    label = round_label(fixtures)
    per_team: dict[TeamId, list[dict[str, str]]] = {t: [] for t in team_ids}
    result: dict[str, Any] = {"matchday": md, "label": label, "fixtures": [m["id"] for m in fixtures], "teams": per_team}
    if not fixtures:
        return result

    ids = list(team_ids)
    idx = {t: i for i, t in enumerate(ids)}
    n = len(ids)
    m = len(fixtures)
    combos = np.array(list(itertools.product((0, 1, 2), repeat=m)), dtype=np.int8)  # 0 home win, 1 draw, 2 away win
    C = len(combos)
    home_pts = np.array([3, 1, 0])
    away_pts = np.array([0, 1, 3])
    pts_now = np.array([points[t] for t in ids], dtype=float)
    rem_now = np.array([remaining[t] for t in ids], dtype=float)
    delta = np.zeros((C, n))
    plays = np.zeros(n)
    fixture_of: dict[TeamId, tuple[int, str]] = {}
    for f, mt in enumerate(fixtures):
        h, a = idx[mt["home_id"]], idx[mt["away_id"]]
        delta[:, h] += home_pts[combos[:, f]]
        delta[:, a] += away_pts[combos[:, f]]
        plays[h] = plays[a] = 1
        fixture_of[mt["home_id"]] = (f, "home")
        fixture_of[mt["away_id"]] = (f, "away")
    pts_after = pts_now[None] + delta
    maxp_after = pts_after + 3 * np.maximum(rem_now - plays, 0)[None]

    def side_mask(f: int, side: str, kind: str) -> np.ndarray:
        r = combos[:, f]
        win, loss = (0, 2) if side == "home" else (2, 0)
        return {"win": r == win, "draw": r == 1, "loss": r == loss, "not_win": r != win, "not_loss": r != loss}[kind]

    ranges = outcome_ranges(cfg)
    settled = {name: status_arrays(pts_after, maxp_after, lo, hi) for name, (lo, hi) in ranges.items()}

    for t in ids:
        i = idx[t]
        own = fixture_of.get(t)
        for name in ranges:
            if statuses[t]["status"][name] != ALIVE:
                continue
            for kind, target in (("clinch", settled[name][0][:, i]), ("eliminate", settled[name][1][:, i])):
                if not target.any():
                    continue
                for text in describe(target, own, fixtures, side_mask, names, kind, name, label)[:max_lines]:
                    per_team[t].append({"outcome": name, "kind": kind, "text": text})
    return result


def describe(target: np.ndarray, own: tuple[int, str] | None, fixtures: list[dict[str, Any]],
             side_mask: Callable[[int, str, str], np.ndarray], names: dict[TeamId, str],
             kind: str, outcome: str, label: str) -> list[str]:
    """Find the simplest sufficient result combinations for `target` and phrase them."""
    verb = VERBS[(kind, outcome)]
    if target.all():
        return [f"{verb} {label} whatever the results."]
    C = len(target)
    every = np.ones(C, dtype=bool)

    # Own-result bases from the weakest requirement to the strongest. Clinching is
    # monotone in the team's own points (more never hurts), elimination the reverse.
    if own is None:
        bases = [("any", every)]
    elif kind == "clinch":
        f, side = own
        bases = [("any", every), ("avoid_defeat", side_mask(f, side, "not_loss")), ("win", side_mask(f, side, "win"))]
    else:
        f, side = own
        bases = [("any", every), ("fail_to_win", side_mask(f, side, "not_win")), ("loss", side_mask(f, side, "loss"))]

    if kind == "clinch":
        rival_kinds = (("not_win", 0, "{X} failing to win", "{X} fail to win"), ("loss", 1, "a loss by {X}", "{X} lose"))
    else:
        rival_kinds = (("not_loss", 0, "{X} avoiding defeat", "{X} avoid defeat"), ("win", 1, "a win for {X}", "{X} win"))
    conds: list[Cond] = []
    for f, mt in enumerate(fixtures):
        if own is not None and f == own[0]:
            continue
        for side, tid in (("home", mt["home_id"]), ("away", mt["away_id"])):
            for k, strength, ph_with, ph_if in rival_kinds:
                conds.append(Cond(str(tid), f, strength, ph_with.format(X=names[tid]), ph_if.format(X=names[tid]),
                                  side_mask(f, side, k)))

    def sufficient(mask: np.ndarray) -> bool:
        return bool(mask.any()) and not bool((mask & ~target).any())

    lines: list[str] = []
    reported: list[frozenset] = []   # rival condition sets already reported at a weaker own base
    for base_key, base in bases:
        if not base.any():
            continue
        if sufficient(base):
            lines.append(_sentence(verb, label, base_key, [], own is not None))
            return lines   # anything stronger is implied
        # Single rival conditions, weakest phrasing per rival.
        best: dict[str, Cond] = {}
        for c in conds:
            if sufficient(base & c.mask) and (c.rival not in best or c.strength < best[c.rival].strength):
                best[c.rival] = c
        if best:
            for c in sorted(best.values(), key=lambda c: (c.strength, c.fixture)):
                key = frozenset([(c.rival, c.strength)])
                if any(key >= r for r in reported):
                    continue
                reported.append(key)
                lines.append(_sentence(verb, label, base_key, [c], own is not None))
                if len(lines) >= 3:
                    return lines
            continue
        # Pairs of rival conditions in different fixtures.
        for c1, c2 in itertools.combinations(sorted(conds, key=lambda c: (c.strength, c.fixture)), 2):
            if c1.fixture == c2.fixture:
                continue
            if sufficient(base & c1.mask & c2.mask):
                key = frozenset([(c1.rival, c1.strength), (c2.rival, c2.strength)])
                if not any(key >= r for r in reported):
                    reported.append(key)
                    lines.append(_sentence(verb, label, base_key, [c1, c2], own is not None))
                break
        if len(lines) >= 3:
            return lines
    return lines


def _sentence(verb: str, label: str, base_key: str, conds: list[Cond], plays: bool) -> str:
    with_parts = [c.with_phrase for c in conds]
    if_parts = [c.if_phrase for c in conds]
    if base_key == "any":
        tail = f"if {_join(if_parts)}" + (", whatever their own result" if plays else "")
    elif base_key == "avoid_defeat":
        tail = "by avoiding defeat" + (f" if {_join(if_parts)}" if conds else "")
    elif base_key == "win":
        tail = "with a win" + (f" and {_join(with_parts)}" if conds else "")
    elif base_key == "fail_to_win":
        tail = "if they fail to win" + (f" and {_join(if_parts)}" if conds else "")
    else:  # loss
        tail = "with a defeat" + (f" and {_join(with_parts)}" if conds else "")
    return f"{verb} {label} {tail}."
