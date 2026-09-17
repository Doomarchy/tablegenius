"""Bookmaker odds for upcoming fixtures, from football-data.co.uk's fixtures.csv.

Shown next to the model's own forecast on team pages ("model 46%, market 44%"). The
odds are not fed into the simulation: the backtest showed the market is only about 2%
sharper on single matches, and only the coming round has odds, so the season-level effect
would be negligible while making the model harder to explain.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .dataset import load_mapping
from .standings import is_finished

log = logging.getLogger(__name__)

FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
CACHE_TTL = 3600
_session_cache: dict[str, str | None] = {}


def fetch_fixtures_csv(cache_dir: Path, ttl: int = CACHE_TTL) -> str | None:
    """The upcoming-fixtures file, fetched at most once per run. football-data.co.uk
    currently redirects automated requests for it to localhost, so this usually returns
    None and the site simply shows no market odds; the code stays for when it works."""
    if "text" in _session_cache:
        return _session_cache["text"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "fixtures.csv"
    text: str | None = None
    if cache.exists() and time.time() - cache.stat().st_mtime < ttl:
        text = cache.read_text(encoding="utf-8-sig")
    else:
        try:
            resp = requests.get(FIXTURES_URL, timeout=30, allow_redirects=True, headers={"User-Agent": "TableGenius/1.0"})
            resp.raise_for_status()
            body = resp.content.decode("utf-8-sig", errors="replace")
            if "HomeTeam" in body.splitlines()[0]:
                cache.write_text(body, encoding="utf-8")
                text = body
            else:
                log.info("fixtures.csv has an unexpected header; market odds skipped")
        except requests.RequestException as exc:
            log.info("market odds skipped (fixtures.csv unavailable: %s)", str(exc).split("(Caused")[0].strip())
            text = cache.read_text(encoding="utf-8-sig") if cache.exists() else None
    _session_cache["text"] = text
    return text


def implied(h: float, d: float, a: float) -> dict[str, float] | None:
    if not all(isinstance(v, (int, float)) and v == v and v > 1 for v in (h, d, a)):
        return None
    inv = [1 / h, 1 / d, 1 / a]
    s = sum(inv)
    return {"home": round(inv[0] / s, 4), "draw": round(inv[1] / s, 4), "away": round(inv[2] / s, 4)}


def market_odds(cfg: dict[str, Any], matches: list[dict[str, Any]], teams: dict[Any, dict[str, Any]],
                cache_dir: Path) -> dict[Any, dict[str, Any]]:
    """Map bookmaker-implied outcome probabilities onto this league's upcoming matches by team ids."""
    text = fetch_fixtures_csv(cache_dir)
    if not text:
        return {}
    csv_code = cfg["sources"]["football_data_co_uk"]["code"]
    df = pd.read_csv(io.StringIO(text))
    df = df[df.get("Div") == csv_code] if "Div" in df.columns else df.iloc[0:0]
    if df.empty:
        return {}
    mapping = load_mapping().get(csv_code, {})
    name_to_id = {name: entry["id"] for name, entry in mapping.items()}
    pending = {(m["home_id"], m["away_id"]): m for m in matches if not is_finished(m)}
    cols = [c for c in (("AvgH", "AvgD", "AvgA"), ("B365H", "B365D", "B365A"), ("PSH", "PSD", "PSA")) if all(x in df.columns for x in c)]
    out: dict[Any, dict[str, Any]] = {}
    for row in df.itertuples(index=False):
        hid = name_to_id.get(str(getattr(row, "HomeTeam", "")).strip())
        aid = name_to_id.get(str(getattr(row, "AwayTeam", "")).strip())
        m = pending.get((hid, aid)) if hid is not None and aid is not None else None
        if m is None:
            continue
        for c in cols:
            probs = implied(*(getattr(row, x, None) for x in c))
            if probs:
                probs["source"] = "average of bookmakers" if c[0] == "AvgH" else ("Bet365" if c[0] == "B365H" else "Pinnacle")
                out[m["id"]] = probs
                break
    if out:
        log.info("%s: market odds attached to %d upcoming fixtures", cfg["code"], len(out))
    return out
