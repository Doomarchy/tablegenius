"""Small football-data.org client with on-disk caching and rate limiting.

Free tier: 10 requests per minute. We space calls ~6.5 s apart and cache responses
locally so repeated local runs do not burn the quota.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"


class FootballDataClient:
    def __init__(self, token: str, cache_dir: Path, cache_ttl_seconds: int = 600, min_interval: float = 6.5):
        if not token:
            raise ValueError("A football-data.org token is required")
        self.token = token
        self.cache_dir = cache_dir / "football-data-org"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl_seconds
        self.min_interval = min_interval
        self._last_request = 0.0
        self.calls_made = 0

    def _cache_path(self, path: str, params: dict[str, Any] | None) -> Path:
        key = json.dumps([path, params or {}], sort_keys=True)
        return self.cache_dir / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        cache = self._cache_path(path, params)
        if self.cache_ttl > 0 and cache.exists() and time.time() - cache.stat().st_mtime < self.cache_ttl:
            log.info("cache hit  %s %s", path, params or "")
            return json.loads(cache.read_text(encoding="utf-8"))

        wait = self.min_interval - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        url = BASE_URL + path
        resp = None
        for attempt in range(2):
            self._last_request = time.time()
            self.calls_made += 1
            resp = requests.get(url, headers={"X-Auth-Token": self.token}, params=params, timeout=30)
            if resp.status_code == 429 and attempt == 0:
                log.warning("rate limited by football-data.org; sleeping 61 s")
                time.sleep(61)
                continue
            break
        assert resp is not None
        if resp.status_code != 200:
            raise RuntimeError(f"football-data.org {resp.status_code} for {path} {params}: {resp.text[:300]}")
        remaining = resp.headers.get("X-Requests-Available-Minute")
        log.info("fetched    %s %s (remaining this minute: %s)", path, params or "", remaining)
        data = resp.json()
        cache.write_text(json.dumps(data), encoding="utf-8")
        return data

    def matches(self, competition: str, season: int) -> dict[str, Any]:
        return self.get(f"/competitions/{competition}/matches", {"season": season})

    def standings(self, competition: str, season: int) -> dict[str, Any]:
        return self.get(f"/competitions/{competition}/standings", {"season": season})
