"""Stage 2b — CISA KEV + FIRST EPSS enrichment (T02). Feed failures never fail the scan (RISKS N12)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import BACKEND_DIR, get_settings
from app.models.domain import RawVuln

logger = logging.getLogger("patchpilot.threat_intel")

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"
TIMEOUT_S = 10
KEV_TTL_S = 24 * 3600
EPSS_TTL_S = 24 * 3600
EPSS_BATCH = 100
FIXTURES = BACKEND_DIR / "tests" / "fixtures"


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=True)


def _cache_dir() -> Path:
    d = get_settings().work_path / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, str] | None = None) -> Any:
    """10 s timeout, one retry."""
    last: Exception | None = None
    for _ in range(2):
        try:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            last = e
    raise last  # type: ignore[misc]


def _kev_index(feed: dict[str, Any]) -> dict[str, str]:
    return {v["cveID"]: v.get("dateAdded", "") for v in feed.get("vulnerabilities", []) if v.get("cveID")}


async def _load_kev(client: httpx.AsyncClient | None, mock: bool) -> dict[str, str] | None:
    """cveID -> dateAdded; None when no data at all could be had. Daily cache; a stale cache beats no data."""
    if mock:
        return _kev_index(json.loads((FIXTURES / "kev_sample.json").read_text(encoding="utf-8")))
    cache = _cache_dir() / "kev.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < KEV_TTL_S:
        try:
            return _kev_index(json.loads(cache.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    assert client is not None
    try:
        feed = await _get_json(client, KEV_URL)
        index = _kev_index(feed)
        _write_atomic(cache, feed)
        return index
    except (httpx.HTTPError, ValueError, KeyError, OSError) as e:
        logger.warning("KEV feed unavailable: %s", type(e).__name__)
    if cache.exists():
        try:
            return _kev_index(json.loads(cache.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return None


EpssMap = dict[str, tuple[float, float]]


async def _load_epss(client: httpx.AsyncClient | None, cves: list[str], mock: bool) -> tuple[EpssMap, bool]:
    """(cve -> (epss, percentile) for the CVEs the feed knows, feed_ok). feed_ok is False if any lookup failed."""
    if mock:
        data = json.loads((FIXTURES / "epss_sample.json").read_text(encoding="utf-8"))
        return {r["cve"]: (float(r["epss"]), float(r["percentile"])) for r in data["data"] if r["cve"] in cves}, True
    cache_path = _cache_dir() / "epss.json"
    try:
        cache: dict[str, Any] = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    now = time.time()
    fresh = {c: cache[c] for c in cves if c in cache and now - cache[c].get("at", 0) < EPSS_TTL_S}
    missing = [c for c in cves if c not in fresh]
    ok = True
    assert client is not None or not missing
    for i in range(0, len(missing), EPSS_BATCH):
        batch = missing[i:i + EPSS_BATCH]
        try:
            data = await _get_json(client, EPSS_URL, {"cve": ",".join(batch)})  # type: ignore[arg-type]
            got = {r["cve"]: r for r in data.get("data", [])}
            for c in batch:  # CVEs the feed has no data for are cached as "none" too
                row = got.get(c)
                cache[c] = {"epss": float(row["epss"]), "percentile": float(row["percentile"]), "at": now} if row \
                    else {"epss": None, "percentile": None, "at": now}
                fresh[c] = cache[c]
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning("EPSS feed unavailable: %s", type(e).__name__)
            ok = False
    if missing:
        try:
            _write_atomic(cache_path, cache)
        except OSError:
            pass
    result = {c: (v["epss"], v["percentile"]) for c, v in fresh.items() if v.get("epss") is not None}
    return result, ok


async def enrich(vulns: list[RawVuln]) -> list[RawVuln]:
    """Set `kev`, `kev_date_added`, `epss`, `epss_percentile` on every vuln.

    `THREAT_INTEL=live|mock|off`. Feed down -> `kev=False`, `epss=None`.
    """
    mode = get_settings().threat_intel
    if mode == "off" or not vulns:
        return vulns
    mock = mode == "mock"
    cves = sorted({c for v in vulns for c in (v.cve_id, *v.aliases) if c.startswith("CVE-")})
    kev: dict[str, str] | None
    if mock:
        kev, (epss, epss_ok) = await _load_kev(None, True), await _load_epss(None, cves, True)
    else:
        async with _http_client() as client:
            kev, (epss, epss_ok) = await asyncio.gather(_load_kev(client, False), _load_epss(client, cves, False))
    for v in vulns:
        ids = [v.cve_id, *v.aliases]
        if kev is None or not epss_ok:
            v.threat_feed_unavailable = True
        if kev:
            hit = next((i for i in ids if i in kev), None)
            if hit:
                v.kev, v.kev_date_added = True, kev[hit] or None
        if epss:
            hit = next((i for i in ids if i in epss), None)
            if hit:
                v.epss, v.epss_percentile = epss[hit]
    return vulns
