"""ArduPilot DataFlash (.bin) parser built on pymavlink's DFReader.

Verified against pymavlink 2.4.49 with real ArduCopter 4.6.3 logs.

ArduPilot logs lack a clean vehicle UUID (unlike PX4's ``sys_uuid``). We derive
a stable id from the board's CPU unique-id printed in the boot banner when
available; otherwise a weak board+firmware id is used and the UI exposes manual
re-assignment (see spec §6.4 / §7).
"""
from __future__ import annotations

import math
import re

from pymavlink import mavutil

from . import common

# Boot banner line:  "ROTOM-ASCEND 00430039 31335110 38353636"
_BOARD_UID_RE = re.compile(
    r"^([A-Za-z0-9_\-\.]+)\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s*$"
)
# "Frame: QUAD/X"
_FRAME_RE = re.compile(r"Frame:\s*(.+)", re.IGNORECASE)
# "ArduCopter V4.6.3 (fa4f2044)"
_FW_RE = re.compile(r"(Arar?du\w+|ArduCopter|ArduPlane|ArduRover|ArduSub|Rover|Blimp)\s+V?\S+", re.IGNORECASE)


def parse(path: str) -> dict:
    """Parse an ArduPilot DataFlash log into a flight-summary dict."""
    mlog = mavutil.mavlink_connection(path, dialect="ardupilotmega")
    result: dict = {"stack": "ardupilot", "parse_status": "ok", "parse_error": None}

    ver: dict | None = None
    msg_texts: list[tuple[float, str]] = []  # (TimeUS, text)
    board_name = board_uid = None
    frame = None
    fw_banner = None
    has_xkf = has_nkf = False

    gps_track: list[tuple[float, float]] = []
    gps_alts: list[float] = []
    gps_speeds: list[float] = []
    gps_vz: list[float] = []
    first_gps_utc = None
    first_gps_timeus = None

    tilts: list[float] = []

    min_tus = None
    max_tus = None

    while True:
        try:
            msg = mlog.recv_match()
        except Exception:  # noqa: BLE001 - tolerate a corrupt record, keep scanning
            continue
        if msg is None:
            break
        t = msg.get_type()
        if t in ("BAD_DATA", "FMT", "FMTU", "UNIT", "MULT", "PARM", "FILE"):
            # still track time for PARM? these carry TimeUS but aren't needed.
            tus = getattr(msg, "TimeUS", None)
            if tus is not None:
                min_tus = tus if min_tus is None else min(min_tus, tus)
                max_tus = tus if max_tus is None else max(max_tus, tus)
            continue

        tus = getattr(msg, "TimeUS", None)
        if tus is not None:
            min_tus = tus if min_tus is None else min(min_tus, tus)
            max_tus = tus if max_tus is None else max(max_tus, tus)

        if t == "VER" and ver is None:
            ver = msg.to_dict()
        elif t == "MSG":
            text = str(getattr(msg, "Message", "")).strip()
            msg_texts.append((tus or 0, text))
            m = _BOARD_UID_RE.match(text)
            if m and board_uid is None:
                board_name = m.group(1)
                board_uid = (m.group(2) + m.group(3) + m.group(4)).upper()
            fm = _FRAME_RE.search(text)
            if fm and frame is None:
                frame = fm.group(1).strip()
            if fw_banner is None and _FW_RE.search(text) and "V" in text:
                fw_banner = text
        elif t == "GPS":
            status = getattr(msg, "Status", 0)
            lat = getattr(msg, "Lat", 0.0)
            lng = getattr(msg, "Lng", 0.0)
            if status >= 3 and common._valid_latlon(lat, lng):
                gps_track.append((float(lat), float(lng)))
                gps_alts.append(float(getattr(msg, "Alt", 0.0)))
                gps_speeds.append(float(getattr(msg, "Spd", 0.0)))
                gps_vz.append(float(getattr(msg, "VZ", 0.0)))
                if first_gps_utc is None:
                    gwk = getattr(msg, "GWk", 0)
                    gms = getattr(msg, "GMS", 0)
                    utc = common.gps_week_ms_to_utc(gwk, gms)
                    if utc is not None:
                        first_gps_utc = utc
                        first_gps_timeus = tus
        elif t == "ATT":
            roll = getattr(msg, "Roll", None)
            pitch = getattr(msg, "Pitch", None)
            if roll is not None and pitch is not None:
                tilts.append(
                    common.tilt_deg_from_rp(math.radians(float(roll)), math.radians(float(pitch)))
                )
        elif t.startswith("XKF"):
            has_xkf = True
        elif t.startswith("NKF"):
            has_nkf = True

    # --- identity -----------------------------------------------------------
    if board_uid:
        result["vehicle_uid"] = f"ap:{board_name}:{board_uid}"
        result["hardware"] = board_name
    elif ver and ver.get("BU") is not None:
        result["vehicle_uid"] = f"ap:board{ver['BU']}:{ver.get('GH', 0)}"
        result["hardware"] = f"board {ver['BU']}"
    else:
        result["vehicle_uid"] = None
        result["hardware"] = board_name

    # --- firmware / airframe ------------------------------------------------
    if ver:
        sw = f"V{ver.get('Maj')}.{ver.get('Min')}.{ver.get('Pat')}"
        gh = ver.get("GH")
        if gh is not None:
            sw += f" ({gh:08x})"
        result["sw_version"] = sw
        # vehicle type from FWS string e.g. "ArduCopter V4.6.3 (...)"
        fws = ver.get("FWS") or fw_banner or ""
        vtype = fws.split()[0] if fws else None
        result["airframe"] = f"{vtype} {frame}".strip() if (vtype or frame) else frame
    else:
        result["sw_version"] = fw_banner
        result["airframe"] = frame

    result["os_version"] = "ChibiOS"
    result["estimator"] = "EKF3" if has_xkf else ("EKF2" if has_nkf else None)
    result["vehicle_life_s"] = None

    # --- timing -------------------------------------------------------------
    if min_tus is not None and max_tus is not None:
        result["duration_s"] = max(0.0, (max_tus - min_tus) / 1e6)
    else:
        result["duration_s"] = None

    log_start_utc = None
    if first_gps_utc is not None and first_gps_timeus is not None and min_tus is not None:
        offset_s = (first_gps_timeus - min_tus) / 1e6
        log_start_utc = common.usec_to_utc(
            int(first_gps_utc.timestamp() * 1e6 - offset_s * 1e6)
        )
    result["log_start_utc"] = common.iso(log_start_utc)

    # --- track + kinematics -------------------------------------------------
    track = common.downsample(gps_track)
    result["track_geojson"] = common.to_geojson_linestring(track)

    distance = common.track_distance_m(gps_track) if len(gps_track) >= 2 else None
    dur = result["duration_s"] or 0.0
    result["distance_m"] = distance
    result["avg_speed_kmh"] = (
        common.ms_to_kmh(distance / dur) if (distance and dur > 0) else None
    )
    result["max_alt_diff_m"] = (max(gps_alts) - min(gps_alts)) if gps_alts else None

    if gps_speeds:
        max_h = max(gps_speeds)
        max_total = max(
            math.sqrt(s * s + v * v) for s, v in zip(gps_speeds, gps_vz)
        )
        result["max_speed_kmh"] = common.ms_to_kmh(max_total)
        result["max_speed_h_kmh"] = common.ms_to_kmh(max_h)
        # ArduPilot GPS.VZ is NED down-positive -> climb is -VZ.
        result["max_speed_up_kmh"] = common.ms_to_kmh(max(0.0, max(-v for v in gps_vz)))
        result["max_speed_down_kmh"] = common.ms_to_kmh(max(0.0, max(gps_vz)))
    else:
        result["max_speed_kmh"] = result["max_speed_h_kmh"] = None
        result["max_speed_up_kmh"] = result["max_speed_down_kmh"] = None

    result["max_tilt_deg"] = max(tilts) if tilts else None

    # --- logged messages ----------------------------------------------------
    base = min_tus or 0
    result["logged_messages"] = [
        {"t": round(max(0.0, (tu - base) / 1e6), 3), "level": "INFO", "msg": txt}
        for tu, txt in msg_texts
    ]

    if not gps_track:
        result["parse_status"] = "partial"
        result["parse_error"] = "no valid GPS position in log"

    return result
