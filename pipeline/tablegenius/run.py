"""Pipeline entry point.

    python -m tablegenius.run --season 2026-27                 # live data (needs FOOTBALL_DATA_TOKEN)
    python -m tablegenius.run --season 2026-27 --source csv    # preview from football-data.co.uk, no token

Writes site/public/data/<season>/<CODE>/standings.json and matches.json plus
site/public/data/index.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .config import LEAGUE_ORDER, load_league
from .fetch import FootballDataClient
from .history import fetch_season_csv
from .paths import CACHE_DIR, DATA_DIR, ENV_FILE
from .sources import normalize_csv_matches, normalize_org_matches, normalize_org_standings
from .standings import build_standings

log = logging.getLogger("tablegenius")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def league_meta(cfg: dict[str, Any]) -> dict[str, Any]:
    keys = ["code", "name", "country", "season", "team_count", "rounds", "tiebreakers", "zones",
            "assumptions", "domestic_cups", "extra_ucl_place", "tied_title_playoff", "tied_relegation_playoff"]
    return {k: cfg.get(k) for k in keys}


def compare_with_api(rows: list[dict[str, Any]], api_table: list[dict[str, Any]]) -> dict[str, Any]:
    """Cross-check our computed table against football-data.org's own standings."""
    if not api_table:
        return {"available": False}
    ours = {r["id"]: r for r in rows}
    diffs = []
    for api in api_table:
        mine = ours.get(api["team_id"])
        if mine is None:
            diffs.append({"team_id": api["team_id"], "issue": "missing from computed table"})
            continue
        if (mine["points"], mine["played"], mine["gd"]) != (api["points"], api["played"], api["goal_difference"]):
            diffs.append({"team": mine["name"], "issue": "totals differ",
                          "ours": [mine["played"], mine["points"], mine["gd"]],
                          "api": [api["played"], api["points"], api["goal_difference"]]})
        elif mine["position"] != api["position"]:
            diffs.append({"team": mine["name"], "issue": "position differs (tiebreak)",
                          "ours": mine["position"], "api": api["position"]})
    totals_match = not any(d["issue"] != "position differs (tiebreak)" for d in diffs)
    return {"available": True, "totals_match": totals_match, "diffs": diffs}


def process_league(cfg: dict[str, Any], source: str, client: FootballDataClient | None, out_dir: Path) -> dict[str, Any]:
    code = cfg["code"]
    src = cfg["sources"]
    if source == "api":
        assert client is not None
        comp, season_year = src["football_data_org"]["competition"], src["football_data_org"]["season"]
        matches, teams = normalize_org_matches(client.matches(comp, season_year))
        api_table = normalize_org_standings(client.standings(comp, season_year))
    else:
        text = fetch_season_csv(cfg["season"], src["football_data_co_uk"]["code"], force=True)
        matches, teams = normalize_csv_matches(text)
        api_table = []

    if len(teams) != cfg["team_count"]:
        log.warning("%s: found %d teams, config says %d", code, len(teams), cfg["team_count"])

    table = build_standings(matches, teams, cfg)
    check = compare_with_api(table["teams"], api_table)
    if check.get("available"):
        if check["totals_match"]:
            log.info("%s: totals match football-data.org (%d ordering diffs)", code, len(check["diffs"]))
        else:
            log.warning("%s: totals DIFFER from football-data.org: %s", code, check["diffs"])

    updated = now_iso()
    league_dir = out_dir / cfg["season"] / code
    standings = {
        "league": league_meta(cfg),
        "updated_at": updated,
        "source": "football-data.org" if source == "api" else "football-data.co.uk (preview)",
        "matchday": table["matchday"],
        "teams": table["teams"],
        "source_check": check,
    }
    write_json(league_dir / "standings.json", standings)
    write_json(league_dir / "matches.json", {
        "league": code,
        "season": cfg["season"],
        "updated_at": updated,
        "teams": list(teams.values()),
        "matches": matches,
    })
    log.info("%s: wrote %d teams, %d/%d matches played", code, len(table["teams"]),
             table["matchday"]["matches_played"], table["matchday"]["matches_total"])
    return {"code": code, "name": cfg["name"], "country": cfg["country"], "updated_at": updated,
            "matchday": table["matchday"]}


def write_index(season: str, out_dir: Path) -> None:
    """Rebuild index.json from whatever league files exist on disk."""
    leagues = []
    for code in LEAGUE_ORDER:
        path = out_dir / season / code / "standings.json"
        if not path.exists():
            continue
        s = json.loads(path.read_text(encoding="utf-8"))
        leagues.append({"code": code, "name": s["league"]["name"], "country": s["league"]["country"],
                        "updated_at": s["updated_at"], "matchday": s["matchday"], "source": s.get("source")})
    write_json(out_dir / "index.json", {
        "season": season,
        "updated_at": max((lg["updated_at"] for lg in leagues), default=now_iso()),
        "leagues": leagues,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TableGenius pipeline")
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--leagues", help="comma-separated codes, e.g. PL,PD (default: all)")
    parser.add_argument("--source", choices=["api", "csv"], default="api")
    parser.add_argument("--no-cache", action="store_true", help="ignore cached API responses")
    parser.add_argument("--out", type=Path, default=DATA_DIR)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv(ENV_FILE)

    codes = [c.strip().upper() for c in args.leagues.split(",")] if args.leagues else LEAGUE_ORDER
    client = None
    if args.source == "api":
        token = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
        if not token or token == "paste_your_token_here":
            print("Missing FOOTBALL_DATA_TOKEN. Copy .env.example to .env and paste your token, "
                  "or run with --source csv for a token-free preview.", file=sys.stderr)
            return 2
        client = FootballDataClient(token, CACHE_DIR, cache_ttl_seconds=0 if args.no_cache else 600)

    failures = 0
    for code in codes:
        cfg = load_league(args.season, code)
        try:
            process_league(cfg, args.source, client, args.out)
        except Exception as exc:  # keep going so one league does not block the others
            failures += 1
            log.error("%s failed: %s", code, exc, exc_info=args.verbose)
    write_index(args.season, args.out)
    if client:
        log.info("API calls made: %d", client.calls_made)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
