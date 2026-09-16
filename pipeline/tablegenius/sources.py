"""Turn raw source payloads into one normalised match/team shape.

A normalised match is:
  {id, utc_date, matchday, status, home_id, away_id, home_goals, away_goals}
A normalised team is:
  {id, name, short_name, tla, crest}
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def normalize_org_matches(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """football-data.org /competitions/{code}/matches payload -> (matches, teams)."""
    teams: dict[int, dict[str, Any]] = {}
    matches: list[dict[str, Any]] = []
    for m in payload.get("matches", []):
        for side in ("homeTeam", "awayTeam"):
            t = m[side]
            if t.get("id") is None:
                continue
            teams[t["id"]] = {
                "id": t["id"],
                "name": t.get("name") or t.get("shortName") or str(t["id"]),
                "short_name": t.get("shortName") or t.get("name"),
                "tla": t.get("tla"),
                "crest": t.get("crest"),
            }
        full_time = (m.get("score") or {}).get("fullTime") or {}
        matches.append({
            "id": m["id"],
            "utc_date": m["utcDate"],
            "matchday": m.get("matchday"),
            "status": m["status"],
            "home_id": m["homeTeam"].get("id"),
            "away_id": m["awayTeam"].get("id"),
            "home_goals": full_time.get("home"),
            "away_goals": full_time.get("away"),
        })
    return matches, teams


def normalize_org_standings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """football-data.org standings payload -> rows of the TOTAL table."""
    for block in payload.get("standings", []):
        if block.get("type") == "TOTAL":
            return [
                {
                    "team_id": row["team"]["id"],
                    "position": row["position"],
                    "played": row.get("playedGames"),
                    "points": row.get("points"),
                    "goal_difference": row.get("goalDifference"),
                }
                for row in block["table"]
            ]
    return []


def normalize_csv_matches(csv_text: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """football-data.co.uk season CSV -> (matches, teams). Team names are used as ids.

    Only played matches exist in these files, so every match is FINISHED.
    """
    df = pd.read_csv(io.StringIO(csv_text.lstrip("﻿")))
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    teams: dict[str, dict[str, Any]] = {}
    matches: list[dict[str, Any]] = []
    for i, row in enumerate(df.itertuples(index=False)):
        home, away = str(row.HomeTeam).strip(), str(row.AwayTeam).strip()
        for name in (home, away):
            teams.setdefault(name, {"id": name, "name": name, "short_name": name, "tla": None, "crest": None})
        date = datetime.strptime(str(row.Date), "%d/%m/%Y")
        time_str = getattr(row, "Time", None)
        if isinstance(time_str, str) and ":" in time_str:
            hh, mm = time_str.split(":")[:2]
            date = date.replace(hour=int(hh), minute=int(mm))
        matches.append({
            "id": f"csv-{i}",
            "utc_date": date.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "matchday": None,
            "status": "FINISHED",
            "home_id": home,
            "away_id": away,
            "home_goals": int(row.FTHG),
            "away_goals": int(row.FTAG),
        })
    return matches, teams
