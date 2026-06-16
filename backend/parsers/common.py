"""Shared helpers for the PX4 / ArduPilot log parsers."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Log-format detection (by magic bytes, NOT file extension).
# A `.bin` file can be either a PX4 ULog or an ArduPilot DataFlash log.
# ---------------------------------------------------------------------------
ULOG_MAGIC = b"ULog\x01\x12\x35"
DATAFLASH_MAGIC = b"\xa3\x95"


def detect_stack(path: str) -> str | None:
    """Return 'px4', 'ardupilot', or None by sniffing the file header."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return None
    if head.startswith(ULOG_MAGIC):
        return "px4"
    if head.startswith(DATAFLASH_MAGIC):
        return "ardupilot"
    return None


# ---------------------------------------------------------------------------
# Geo / math helpers
# ---------------------------------------------------------------------------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def track_distance_m(points: list[tuple[float, float]]) -> float:
    """Sum of haversine distances along a list of (lat, lon) points."""
    total = 0.0
    for (la1, lo1), (la2, lo2) in zip(points, points[1:]):
        total += haversine_m(la1, lo1, la2, lo2)
    return total


def downsample(points: list, max_points: int = 400) -> list:
    """Evenly downsample a list to at most ``max_points`` while keeping the
    first and last sample."""
    n = len(points)
    if n <= max_points:
        return points
    step = n / max_points
    out = [points[int(i * step)] for i in range(max_points)]
    out[-1] = points[-1]
    return out


def to_geojson_linestring(points: list[tuple[float, float]]) -> dict | None:
    """Build a GeoJSON LineString from (lat, lon) points -> [lon, lat] order."""
    pts = [(lat, lon) for lat, lon in points if _valid_latlon(lat, lon)]
    if len(pts) < 2:
        return None
    coords = [[round(lon, 7), round(lat, 7)] for lat, lon in pts]
    return {"type": "LineString", "coordinates": coords}


def _valid_latlon(lat, lon) -> bool:
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    if lat == 0.0 and lon == 0.0:
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
# GPS epoch is 1980-01-06 00:00:00 UTC. GPS time does not count leap seconds;
# as of 2017 onward there are 18 leap seconds between GPS and UTC.
GPS_EPOCH_UNIX = 315964800  # 1980-01-06 in unix seconds
GPS_LEAP_SECONDS = 18


def gps_week_ms_to_utc(week: int, ms: int) -> datetime | None:
    """Convert ArduPilot GPS week + milliseconds-of-week to a UTC datetime."""
    try:
        week = int(week)
        ms = int(ms)
    except (TypeError, ValueError):
        return None
    if week <= 0:
        return None
    unix = GPS_EPOCH_UNIX + week * 7 * 86400 + ms / 1000.0 - GPS_LEAP_SECONDS
    try:
        return datetime.fromtimestamp(unix, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def usec_to_utc(usec: int) -> datetime | None:
    """Convert a PX4 ``time_utc_usec`` value to a UTC datetime."""
    try:
        usec = int(usec)
    except (TypeError, ValueError):
        return None
    if usec <= 0:
        return None
    try:
        return datetime.fromtimestamp(usec / 1e6, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def tilt_deg_from_rp(roll_rad: float, pitch_rad: float) -> float:
    """Tilt angle from vertical given roll/pitch in radians."""
    c = math.cos(roll_rad) * math.cos(pitch_rad)
    c = max(-1.0, min(1.0, c))
    return math.degrees(math.acos(c))


def ms_to_kmh(v: float) -> float:
    return v * 3.6


# PX4 ULog log levels follow syslog numeric severities (sent as ASCII digits
# in older logs, here already decoded to ints by pyulog as the byte value).
_PX4_LEVEL = {
    0: "EMERG", 1: "ALERT", 2: "CRIT", 3: "ERR",
    4: "WARNING", 5: "NOTICE", 6: "INFO", 7: "DEBUG",
    # pyulog exposes the raw ASCII byte ('0'..'7' => 48..55)
    48: "EMERG", 49: "ALERT", 50: "CRIT", 51: "ERR",
    52: "WARNING", 53: "NOTICE", 54: "INFO", 55: "DEBUG",
}


def px4_level_name(level) -> str:
    return _PX4_LEVEL.get(level, str(level))


# PX4 sets a real syslog severity; ArduPilot logs every message as INFO, so for
# ArduPilot we infer severity from the message text instead. The single source
# of truth is message_severity() below.
ERROR_LEVELS = {"EMERG", "ALERT", "CRIT", "ERR"}
WARNING_LEVELS = {"WARNING"}

# "PreArm:" lines are arming checks (the vehicle never even armed) -> warnings,
# even when the text contains the word "error" (e.g. "GPS speed error").
_PREARM_RE = re.compile(r"prearm", re.IGNORECASE)
# Genuine failures during operation.
_ERROR_TEXT_RE = re.compile(
    r"\b(error|fail(ure|safe|ed)?|failsafe|emergency|critical|crash|unhealthy|"
    r"glitch|thrust loss)\b",
    re.IGNORECASE,
)
# Less-severe conditions / pre-flight checks / denials.
_WARN_TEXT_RE = re.compile(
    r"\b(warn(ing)?|denied|reject(ed)?|inconsisten\w*|degraded|marginal|timeout|disabled)\b",
    re.IGNORECASE,
)


def message_severity(level, msg) -> str:
    """Return 'error', 'warn', or 'info' for a logged message.

    PX4 carries a syslog level; ArduPilot (always INFO) is classified by text.
    """
    if level in ERROR_LEVELS:
        return "error"
    if level in WARNING_LEVELS:
        return "warn"
    text = msg or ""
    # Arming checks are warnings regardless of the words inside them.
    if _PREARM_RE.search(text):
        return "warn"
    if _ERROR_TEXT_RE.search(text):
        return "error"
    if _WARN_TEXT_RE.search(text):
        return "warn"
    return "info"


def message_is_error(level, msg) -> bool:
    return message_severity(level, msg) == "error"


def message_is_warning(level, msg) -> bool:
    return message_severity(level, msg) == "warn"


def count_error_messages(messages) -> int:
    return sum(
        1 for m in (messages or []) if message_severity(m.get("level"), m.get("msg")) == "error"
    )


def count_warning_messages(messages) -> int:
    return sum(
        1 for m in (messages or []) if message_severity(m.get("level"), m.get("msg")) == "warn"
    )
