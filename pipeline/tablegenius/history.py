"""Historical results from football-data.co.uk CSV files (used for team-strength fitting
and the backtest). Past seasons never change, so they are stored under pipeline/history/
and committed; only missing files are downloaded.
"""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from .paths import HISTORY_DIR

log = logging.getLogger(__name__)

BASE_URL = "https://football-data.co.uk/mmz4281"


def season_slug(season: str) -> str:
    """'2026-27' -> '2627'."""
    start, end = season.split("-")
    return start[-2:] + end[-2:]


def csv_path(season: str, code: str) -> Path:
    return HISTORY_DIR / f"{season}_{code}.csv"


def fetch_season_csv(season: str, code: str, force: bool = False) -> str:
    """Return the CSV text for one league-season, downloading it if not stored."""
    path = csv_path(season, code)
    if path.exists() and not force:
        return path.read_text(encoding="utf-8-sig")
    url = f"{BASE_URL}/{season_slug(season)}/{code}.csv"
    log.info("downloading %s", url)
    resp = requests.get(url, timeout=60, allow_redirects=True)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig", errors="replace")
    if "HomeTeam" not in text.splitlines()[0]:
        raise RuntimeError(f"Unexpected CSV header from {url}: {text[:120]!r}")
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text
