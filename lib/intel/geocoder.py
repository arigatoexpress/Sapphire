"""Free geocoding for Houston lead addresses.

Uses Nominatim (OpenStreetMap public endpoint, 1 req/sec cap, no API key).
Results are cached on disk in ``data/leads/geocache.json`` so repeated runs
over the same address never re-hit Nominatim.

Public API:
    geocode(address)       -> (lat, lng) | (None, None)
    geocode_unmapped()     -> int   (count of leads geocoded)
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from threading import Lock
from typing import Any

from lib.intel.houston_leads import LEADS_DIR, load_leads, save_leads

log = logging.getLogger(__name__)

GEOCACHE_FILE = LEADS_DIR / "geocache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL_SECS = 1.1  # Nominatim TOS = 1 req/sec, leave headroom

_lock = Lock()
_last_request_ts: float = 0.0


def _load_cache() -> dict[str, dict[str, Any]]:
    if not GEOCACHE_FILE.exists():
        return {}
    try:
        return json.loads(GEOCACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(cache: dict[str, dict[str, Any]]) -> None:
    LEADS_DIR.mkdir(parents=True, exist_ok=True)
    GEOCACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))


def _normalize(address: str) -> str:
    return " ".join(address.lower().split())


def _rate_limited_get(params: dict[str, str], timeout: int = 10) -> Any | None:
    """Issue one Nominatim request, sleeping to stay under 1 req/sec."""
    global _last_request_ts
    with _lock:
        now = time.time()
        elapsed = now - _last_request_ts
        if elapsed < MIN_INTERVAL_SECS:
            time.sleep(MIN_INTERVAL_SECS - elapsed)
        _last_request_ts = time.time()
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{qs}",
        headers={
            # Nominatim requires a real UA per their usage policy.
            "User-Agent": "Sapphire-Lead-Pipeline/1.0 (https://github.com/arigatoexpress)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        log.warning("nominatim request failed: %s", e)
        return None


def geocode(address: str, *, cache: dict | None = None) -> tuple[float | None, float | None]:
    """Return (lat, lng) for an address, or (None, None) on failure.

    Cache is read once and shared if passed in — useful when bulk-geocoding to
    avoid disk I/O per call.
    """
    addr = (address or "").strip()
    if not addr:
        return None, None

    own_cache = cache is None
    cache = cache if cache is not None else _load_cache()
    key = _normalize(addr)
    hit = cache.get(key)
    if hit is not None:
        lat, lng = hit.get("lat"), hit.get("lng")
        return (
            float(lat) if lat is not None else None,
            float(lng) if lng is not None else None,
        )

    payload = _rate_limited_get({"q": addr, "format": "json", "limit": "1"})
    if not payload or not isinstance(payload, list) or not payload:
        # Negative-cache the miss so we don't spam Nominatim every run.
        cache[key] = {"lat": None, "lng": None, "miss": True}
        if own_cache:
            _save_cache(cache)
        return None, None

    first = payload[0]
    try:
        lat = float(first["lat"])
        lng = float(first["lon"])
    except (KeyError, TypeError, ValueError):
        cache[key] = {"lat": None, "lng": None, "miss": True}
        if own_cache:
            _save_cache(cache)
        return None, None

    cache[key] = {"lat": lat, "lng": lng, "display": first.get("display_name")}
    if own_cache:
        _save_cache(cache)
    return lat, lng


def geocode_unmapped(limit: int | None = None) -> int:
    """Geocode every lead in the JSONL store missing lat/lng. Returns count."""
    leads = load_leads()
    if not leads:
        return 0

    cache = _load_cache()
    geocoded = 0
    for lead in leads:
        if lead.get("lat") is not None and lead.get("lng") is not None:
            continue
        addr = lead.get("address") or ""
        if not addr:
            continue
        lat, lng = geocode(addr, cache=cache)
        if lat is not None and lng is not None:
            lead["lat"] = lat
            lead["lng"] = lng
            geocoded += 1
        if limit and geocoded >= limit:
            break

    _save_cache(cache)
    if geocoded:
        save_leads(leads)
    return geocoded


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--address", help="Geocode a single address and print the result")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    if args.address:
        lat, lng = geocode(args.address)
        print(json.dumps({"address": args.address, "lat": lat, "lng": lng}, indent=2))
    else:
        n = geocode_unmapped(limit=args.limit)
        print(json.dumps({"geocoded": n, "cache": str(GEOCACHE_FILE)}, indent=2))
