"""Maintain config/team_names.json: football-data.co.uk team names -> football-data.org ids.

    python -m tablegenius.names --season 2026-27

For each league it reads the current season's teams from the API data already on disk and
the current season's CSV, matches the two name lists one-to-one (Hungarian assignment on a
string-similarity score), keeps any entries already in the file, and prints the proposals
with a confidence score so low ones can be checked by hand.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from .config import LEAGUE_ORDER, load_league
from .dataset import MAPPING_FILE, load_mapping
from .history import fetch_season_csv
from .paths import DATA_DIR
from .sources import normalize_csv_matches

GENERIC = {"fc", "cf", "sc", "ac", "as", "ss", "us", "rc", "rcd", "afc", "cfc", "bc", "fsv", "vfl", "vfb",
           "tsg", "sv", "club", "calcio", "de", "di", "del", "la", "le", "les", "und", "e", "the", "1", "04",
           "05", "07", "09", "1846", "1899", "1901", "1903", "1907", "1909", "1910", "1913", "cd", "ud", "sd",
           "athletic", "atletico", "sporting", "stade", "olympique", "racing", "real", "deportivo", "balompie",
           "borussia", "eintracht", "hellas", "internazionale", "football"}

ALIASES = {
    "man": "manchester", "utd": "united", "nott'm": "nottingham", "forest": "nottingham",
    "wolves": "wolverhampton", "spurs": "tottenham", "psg": "paris", "ath": "athletic",
    "sociedad": "sociedad", "espanol": "espanyol", "vallecano": "rayo", "m'gladbach": "monchengladbach",
    "gladbach": "monchengladbach", "ein": "eintracht", "leverkusen": "leverkusen", "koln": "koln",
    "inter": "internazionale", "st": "sankt", "sg": "germain",
}


def norm_tokens(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("-", " ").replace(".", " ")
    toks = [t for t in re.split(r"[^a-z0-9']+", s) if t]
    out = []
    for t in toks:
        t = ALIASES.get(t, t)
        if t in GENERIC:
            continue
        out.append(t)
    return out or toks


def similarity(csv_name: str, api_name: str, api_short: str, api_tla: str | None) -> float:
    a = norm_tokens(csv_name)
    bs = set(norm_tokens(api_name)) | set(norm_tokens(api_short or ""))
    if not a or not bs:
        return 0.0
    best = 0.0
    for ta in a:
        for tb in bs:
            r = difflib.SequenceMatcher(None, ta, tb).ratio()
            if tb.startswith(ta) or ta.startswith(tb):
                r = max(r, 0.9)
            best = max(best, r)
    overlap = len(set(a) & bs) / len(set(a))
    whole = difflib.SequenceMatcher(None, " ".join(a), " ".join(sorted(bs))).ratio()
    score = 0.5 * best + 0.3 * overlap + 0.2 * whole
    if api_tla and csv_name.lower().replace(" ", "")[:3] == api_tla.lower():
        score += 0.05
    return score


def propose(cfg: dict[str, Any], season: str, mapping: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[tuple[str, str, float]]]:
    code = cfg["code"]
    csv_code = cfg["sources"]["football_data_co_uk"]["code"]
    matches_path = DATA_DIR / season / code / "matches.json"
    if not matches_path.exists():
        raise FileNotFoundError(f"Run the live pipeline first: {matches_path} is missing")
    api_teams = json.loads(matches_path.read_text(encoding="utf-8"))["teams"]
    _, csv_teams = normalize_csv_matches(fetch_season_csv(season, csv_code, force=True))

    existing = dict(mapping.get(csv_code, {}))
    used_ids = {v["id"] for v in existing.values()}
    csv_names = [n for n in csv_teams if n not in existing]
    api_free = [t for t in api_teams if t["id"] not in used_ids]
    report: list[tuple[str, str, float]] = []
    if csv_names and api_free:
        S = np.zeros((len(csv_names), len(api_free)))
        for i, cn in enumerate(csv_names):
            for j, t in enumerate(api_free):
                S[i, j] = similarity(cn, t["name"], t.get("short_name") or "", t.get("tla"))
        rows, cols = linear_sum_assignment(-S)
        for i, j in zip(rows, cols):
            t = api_free[j]
            existing[csv_names[i]] = {"id": t["id"], "name": t["name"]}
            report.append((csv_names[i], t["name"], float(S[i, j])))
    return existing, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--leagues")
    args = parser.parse_args(argv)
    codes = [c.strip().upper() for c in args.leagues.split(",")] if args.leagues else LEAGUE_ORDER
    mapping = load_mapping()
    for code in codes:
        cfg = load_league(args.season, code)
        csv_code = cfg["sources"]["football_data_co_uk"]["code"]
        entries, report = propose(cfg, args.season, mapping)
        mapping[csv_code] = dict(sorted(entries.items()))
        print(f"== {code} ({csv_code}): {len(report)} new proposals, {len(entries)} total")
        for csv_name, api_name, score in sorted(report, key=lambda r: r[2]):
            flag = "  <-- CHECK" if score < 0.6 else ""
            print(f"  {score:.2f}  {csv_name:<18} -> {api_name}{flag}")
    MAPPING_FILE.write_text(json.dumps(mapping, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {MAPPING_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
