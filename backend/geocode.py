"""Best-effort reverse geocoding of a flight's start position.

Resolves a GPS coordinate to the 시/군/구 (second-level administrative area,
e.g. "영월군", "강동구") using OpenStreetMap Nominatim (free, no key).

Design notes:
- Network calls are isolated from log parsing: this runs as a separate pass
  after a scan and never breaks it (any failure -> location stays NULL).
- Results are cached in the DB keyed by coordinates rounded to ~1 km, so many
  flights from the same field cost a single lookup. The Nominatim usage policy
  (max 1 req/s, identifying User-Agent) is respected via throttling below.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "DroneFlightLogbook/1.0 (local demo)"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_MIN_INTERVAL_S = 1.1  # Nominatim: <= 1 request/second
_last_call = 0.0
_CACHE_PRECISION = 2  # decimal places (~1.1 km) for the coordinate cache key


def _cache_key(lat: float, lon: float) -> str:
    return f"{round(lat, _CACHE_PRECISION)},{round(lon, _CACHE_PRECISION)}"


def sigungu_from_display(display_name: str | None) -> str | None:
    """Extract the second administrative component (시/군/구) from a Nominatim
    ``display_name`` (which is ordered specific -> general)."""
    if not display_name:
        return None
    parts = [p.strip() for p in display_name.split(",")]
    # Drop empty tokens and numeric postcodes.
    parts = [p for p in parts if p and not p.replace(" ", "").isdigit()]
    if not parts:
        return None
    parts = parts[:-1]  # drop the country (last token)
    parts = parts[::-1]  # now general -> specific: [province, 시군구, ...]
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else None


def _http_reverse(lat: float, lon: float) -> str | None:
    """Call Nominatim (throttled) and return the 시군구 name, or None."""
    global _last_call
    wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    params = urllib.parse.urlencode(
        {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "json", "accept-language": "ko"}
    )
    req = urllib.request.Request(f"{NOMINATIM}?{params}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - network/parse failure is non-fatal
        return None
    finally:
        _last_call = time.monotonic()
    name = sigungu_from_display(data.get("display_name"))
    if name:
        return name
    # structured fallback
    addr = data.get("address") or {}
    for k in ("county", "borough", "city_district", "city", "town", "municipality"):
        if addr.get(k):
            return addr[k]
    return None


def lookup(conn, lat: float, lon: float) -> str | None:
    """Cached reverse lookup. Returns the 시군구 name or None."""
    key = _cache_key(lat, lon)
    row = conn.execute("SELECT name FROM geocode WHERE key = ?", (key,)).fetchone()
    if row is not None:
        return row["name"]
    name = _http_reverse(lat, lon)
    conn.execute(
        "INSERT OR REPLACE INTO geocode (key, name, fetched_at) VALUES (?,?,?)",
        (key, name, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return name


def backfill(conn, limit: int | None = None) -> int:
    """Fill ``start_location`` for flights that have a track but no location yet.

    Returns the number of flights updated. Safe to call repeatedly; coordinate
    caching keeps the number of actual network calls small.
    """
    rows = conn.execute(
        "SELECT id, track_geojson FROM flights "
        "WHERE (start_location IS NULL OR start_location = '') "
        "AND track_geojson IS NOT NULL"
    ).fetchall()
    updated = 0
    for r in rows:
        if limit is not None and updated >= limit:
            break
        try:
            geo = json.loads(r["track_geojson"])
            lon, lat = geo["coordinates"][0]  # GeoJSON is [lon, lat]
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        name = lookup(conn, lat, lon)
        if name:
            conn.execute(
                "UPDATE flights SET start_location = ? WHERE id = ?", (name, r["id"])
            )
            conn.commit()
            updated += 1
    return updated
