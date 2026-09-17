"""Load per-league, per-season rule files from config/leagues/<season>/<CODE>.json."""
from __future__ import annotations

import json
from typing import Any

from .paths import LEAGUES_DIR

# Display order on the site.
LEAGUE_ORDER = ["PL", "PD", "SA", "BL1", "FL1", "DED", "PPL"]

# Zone keys in the order they appear top-to-bottom of a table. `european_playoff` is a
# domestic play-off for a European place (the Eredivisie's); like the relegation play-off,
# the play-off itself is not simulated.
ZONE_KEYS = ["ucl", "ucl_qualifying", "uel", "uecl", "european_playoff", "relegation_playoff", "relegation"]


def load_league(season: str, code: str) -> dict[str, Any]:
    path = LEAGUES_DIR / season / f"{code}.json"
    if not path.exists():
        raise FileNotFoundError(f"No league config at {path}")
    with path.open(encoding="utf-8") as fh:
        cfg = json.load(fh)
    _validate(cfg)
    return cfg


def load_leagues(season: str, codes: list[str] | None = None) -> list[dict[str, Any]]:
    codes = codes or LEAGUE_ORDER
    return [load_league(season, c) for c in codes]


def zone_for_position(cfg: dict[str, Any], position: int) -> str | None:
    """Return the zone key ('ucl', 'uel', ...) a league position falls in, or None."""
    for key in ZONE_KEYS:
        rng = cfg["zones"].get(key, {}).get("positions")
        if rng and rng[0] <= position <= rng[1]:
            return key
    return None


def _validate(cfg: dict[str, Any]) -> None:
    required = ["code", "name", "season", "team_count", "rounds", "tiebreakers", "zones", "sources"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"League config {cfg.get('code')} missing keys: {missing}")
    if cfg["tiebreakers"][0] != "points":
        raise ValueError(f"{cfg['code']}: tiebreakers must start with 'points'")
    n = cfg["team_count"]
    for key, zone in cfg["zones"].items():
        rng = zone.get("positions")
        if rng is not None and not (1 <= rng[0] <= rng[1] <= n):
            raise ValueError(f"{cfg['code']}: zone {key} has positions {rng} outside 1..{n}")
