"""Assemble the matches used to fit team ratings.

Current-season results come from football-data.org (team ids are integers). Previous
seasons come from football-data.co.uk CSVs, whose team names are mapped to the same ids
through config/team_names.json. Teams that only appear in past seasons (relegated sides)
keep their CSV name as their id; they still matter because their results inform the ratings
of everybody they played.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Hashable

import numpy as np
import pandas as pd

from .history import fetch_season_csv
from .model import FitData, ModelParams
from .paths import CONFIG_DIR
from .sources import normalize_csv_matches
from .standings import is_finished

log = logging.getLogger(__name__)

MAPPING_FILE = CONFIG_DIR / "team_names.json"


def previous_season(season: str) -> str:
    start = int(season.split("-")[0])
    return f"{start - 1}-{str(start)[-2:]}"


def seasons_before(season: str, count: int) -> list[str]:
    """Most recent first: seasons_before('2026-27', 2) -> ['2025-26', '2024-25']."""
    out = []
    s = season
    for _ in range(count):
        s = previous_season(s)
        out.append(s)
    return out


def load_mapping() -> dict[str, dict[str, Any]]:
    if MAPPING_FILE.exists():
        return json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    return {}


def csv_team_id(csv_code: str, name: str, mapping: dict[str, dict[str, Any]]) -> Hashable:
    entry = mapping.get(csv_code, {}).get(name)
    return entry["id"] if entry else name


def parse_date(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def history_rows(csv_code: str, seasons: list[str], mapping: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, set]]:
    """Past-season matches as rows with canonical ids, plus the team set per season."""
    rows: list[dict[str, Any]] = []
    season_teams: dict[str, set] = {}
    for season in seasons:
        text = fetch_season_csv(season, csv_code)
        matches, teams = normalize_csv_matches(text)
        season_teams[season] = {csv_team_id(csv_code, name, mapping) for name in teams}
        for m in matches:
            rows.append({
                "home": csv_team_id(csv_code, m["home_id"], mapping),
                "away": csv_team_id(csv_code, m["away_id"], mapping),
                "x": m["home_goals"], "y": m["away_goals"],
                "date": parse_date(m["utc_date"]), "season": season,
                "odds": m.get("odds"),
            })
    return rows, season_teams


def current_rows(matches: list[dict[str, Any]], season: str) -> list[dict[str, Any]]:
    return [
        {"home": m["home_id"], "away": m["away_id"], "x": m["home_goals"], "y": m["away_goals"],
         "date": parse_date(m["utc_date"]), "season": season}
        for m in matches if is_finished(m)
    ]


def build_fit_data(
    rows: list[dict[str, Any]],
    current_team_ids: list,
    previous_team_ids: set,
    as_of: datetime,
    params: ModelParams,
    seasons: list[str],
) -> FitData:
    """Turn match rows into arrays. Matches on or after `as_of` are excluded."""
    rows = [r for r in rows if r["date"] < as_of]
    other_ids = sorted({r[k] for r in rows for k in ("home", "away")} - set(current_team_ids), key=str)
    team_ids = list(current_team_ids) + other_ids
    index = {t: i for i, t in enumerate(team_ids)}
    n = len(team_ids)

    home = np.array([index[r["home"]] for r in rows], dtype=int)
    away = np.array([index[r["away"]] for r in rows], dtype=int)
    x = np.array([r["x"] for r in rows], dtype=float)
    y = np.array([r["y"] for r in rows], dtype=float)
    if rows:
        days = np.array([(as_of - r["date"]).total_seconds() / 86400.0 for r in rows])
        weights = np.exp(-params.xi * np.clip(days, 0.0, None))
    else:
        weights = np.zeros(0)

    promoted = np.zeros(n, dtype=bool)
    if previous_team_ids:
        for i, t in enumerate(current_team_ids):
            if t not in previous_team_ids:
                promoted[i] = True
    prior_attack = np.where(promoted, params.promoted_attack, 0.0)
    prior_defence = np.where(promoted, params.promoted_defence, 0.0)
    established = np.zeros(n, dtype=bool)
    established[: len(current_team_ids)] = ~promoted[: len(current_team_ids)]
    if not established.any():
        established[:] = True

    return FitData(team_ids=team_ids, home=home, away=away, x=x, y=y, weights=weights,
                   prior_attack=prior_attack, prior_defence=prior_defence, established=established,
                   n_current=len(current_team_ids), seasons=list(seasons))


def blend_xg(rows: list[dict[str, Any]], cfg: dict[str, Any], mapping: dict[str, dict[str, Any]], weight: float) -> int:
    """Replace goals with a blend of goals and expected goals for current-season matches that
    football-data.co.uk has published xG for. Returns the number of matches blended.

    Off by default: it cannot be validated until a season with xG data has been completed
    (the 2025-26 files have no xG), at which point the rolling backtest can judge it.
    """
    if weight <= 0:
        return 0
    csv_code = cfg["sources"]["football_data_co_uk"]["code"]
    try:
        text = fetch_season_csv(cfg["season"], csv_code, force=True)
    except Exception as exc:  # the live CSV is optional
        log.warning("%s: xG unavailable (%s)", cfg["code"], exc)
        return 0
    csv_matches, _ = normalize_csv_matches(text)
    by_pair = {}
    for m in csv_matches:
        if m.get("xg"):
            by_pair[(csv_team_id(csv_code, m["home_id"], mapping), csv_team_id(csv_code, m["away_id"], mapping))] = m["xg"]
    blended = 0
    for r in rows:
        if r["season"] != cfg["season"]:
            continue
        xg = by_pair.get((r["home"], r["away"]))
        if xg:
            r["x"] = (1 - weight) * r["x"] + weight * xg["home"]
            r["y"] = (1 - weight) * r["y"] + weight * xg["away"]
            blended += 1
    return blended


def assemble_live(cfg: dict[str, Any], matches: list[dict[str, Any]], team_ids: list, as_of: datetime,
                  params: ModelParams, history_seasons: int, xg_weight: float = 0.0) -> FitData:
    """Fit data for the live site: API results this season plus CSV history."""
    mapping = load_mapping()
    csv_code = cfg["sources"]["football_data_co_uk"]["code"]
    seasons = seasons_before(cfg["season"], history_seasons)
    hist, season_teams = history_rows(csv_code, seasons, mapping)
    current = current_rows(matches, cfg["season"])
    xg_matches = blend_xg(current, cfg, mapping, xg_weight)
    rows = current + hist
    prev = season_teams.get(previous_season(cfg["season"]), set())
    unmapped = [t for t in team_ids if t not in {v["id"] for v in mapping.get(csv_code, {}).values()}]
    if unmapped:
        log.warning("%s: %d current teams have no CSV name mapping (treated as promoted): %s",
                    cfg["code"], len(unmapped), unmapped)
    data = build_fit_data(rows, team_ids, prev, as_of, params, [cfg["season"]] + seasons)
    data.xg_matches = xg_matches
    return data


def to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows)
