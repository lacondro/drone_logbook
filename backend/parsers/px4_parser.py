"""PX4 ULog (.ulg / .bin) parser built on pyulog.

Field mappings were verified against pyulog 1.2.2 with real ROTOM_ASCEND logs
(modern dataset names: ``latitude_deg``/``longitude_deg``/``altitude_msl_m``).
"""
from __future__ import annotations

import math

from pyulog import ULog

from . import common

# PX4 firmware/OS version "type" byte -> label
_VER_TYPE = {0: "dev", 64: "alpha", 128: "beta", 192: "RC", 255: "release"}
# A small MAV_TYPE -> frame-name map (the common multirotor/VTOL set).
_MAV_TYPE = {
    1: "Fixed Wing", 2: "Quadrotor", 13: "Hexarotor", 14: "Octorotor",
    3: "Coaxial", 4: "Helicopter", 15: "Tricopter",
    19: "VTOL Tailsitter Duo", 20: "VTOL Tailsitter Quad", 21: "VTOL Tiltrotor",
    22: "VTOL", 23: "VTOL", 24: "VTOL", 25: "VTOL",
}


def _decode_version(value) -> tuple[str, str]:
    """Decode a 32-bit (major<<24|minor<<16|patch<<8|type) version int.

    Returns (``"v1.16.0"``, ``"RC"``)."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "", ""
    major = (v >> 24) & 0xFF
    minor = (v >> 16) & 0xFF
    patch = (v >> 8) & 0xFF
    type_byte = v & 0xFF
    return f"v{major}.{minor}.{patch}", _VER_TYPE.get(type_byte, "")


def _get(ulog: ULog, name: str):
    try:
        return ulog.get_dataset(name)
    except (KeyError, IndexError, Exception):  # noqa: BLE001 - dataset may be absent
        return None


def parse(path: str) -> dict:
    """Parse a PX4 ULog and return a flight-summary dict.

    Raises on a fundamentally unreadable file; partial data (e.g. no GPS) is
    reported via ``parse_status='partial'`` rather than an exception.
    """
    ulog = ULog(path)
    info = ulog.msg_info_dict
    params = ulog.initial_parameters
    result: dict = {"stack": "px4", "parse_status": "ok", "parse_error": None}

    # --- identity / firmware ------------------------------------------------
    result["vehicle_uid"] = info.get("sys_uuid") or None

    hw = info.get("ver_hw")
    if info.get("ver_hw_subtype"):
        hw = f"{hw} ({info['ver_hw_subtype']})"
    result["hardware"] = hw

    rel, rtype = _decode_version(info.get("ver_sw_release"))
    git = (info.get("ver_sw") or "")[:8]
    sw = rel
    if rtype:
        sw = f"{sw} ({rtype})"
    if git:
        sw = f"{sw} ({git})"
    result["sw_version"] = sw.strip() or None

    os_rel, _ = _decode_version(info.get("sys_os_ver_release"))
    os_name = info.get("sys_os_name") or ""
    result["os_version"] = f"{os_name}, {os_rel}".strip(", ") or None

    # Airframe: MAV_TYPE gives the frame class, SYS_AUTOSTART the config id.
    mav_type = params.get("MAV_TYPE")
    autostart = params.get("SYS_AUTOSTART")
    frame = _MAV_TYPE.get(int(mav_type)) if mav_type is not None else None
    if frame and autostart is not None:
        result["airframe"] = f"{frame} (SYS_AUTOSTART {int(autostart)})"
    elif frame:
        result["airframe"] = frame
    elif autostart is not None:
        result["airframe"] = f"SYS_AUTOSTART {int(autostart)}"
    else:
        result["airframe"] = None

    # Estimator: modern PX4 uses EKF2 exclusively.
    est = params.get("SYS_MC_EST_GROUP")
    result["estimator"] = "EKF2" if est in (None, 2) else f"group {int(est)}"

    # --- duration -----------------------------------------------------------
    result["duration_s"] = max(
        0.0, (ulog.last_timestamp - ulog.start_timestamp) / 1e6
    )
    result["vehicle_life_s"] = None  # not reliably available in ULog

    # --- GPS track + UTC start ---------------------------------------------
    gps = _get(ulog, "vehicle_gps_position") or _get(ulog, "sensor_gps")
    track_points: list[tuple[float, float]] = []
    log_start_utc = None
    if gps is not None:
        d = gps.data
        lat = d.get("latitude_deg")
        lon = d.get("longitude_deg")
        ts = d.get("timestamp")
        fix = d.get("fix_type")
        utc = d.get("time_utc_usec")
        if lat is not None and lon is not None:
            for i in range(len(lat)):
                if fix is not None and fix[i] < 3:
                    continue
                if common._valid_latlon(lat[i], lon[i]):
                    track_points.append((float(lat[i]), float(lon[i])))
        # Correlate first valid UTC sample back to the log start timestamp.
        if utc is not None and ts is not None:
            for i in range(len(utc)):
                if utc[i] and utc[i] > 0:
                    anchor = common.usec_to_utc(
                        int(utc[i]) - (int(ts[i]) - int(ulog.start_timestamp))
                    )
                    log_start_utc = anchor
                    break

    result["log_start_utc"] = common.iso(log_start_utc)
    track = common.downsample(track_points)
    result["track_geojson"] = common.to_geojson_linestring(track)

    # --- speed / altitude / distance ---------------------------------------
    _compute_kinematics(ulog, track_points, result)

    # --- tilt ---------------------------------------------------------------
    result["max_tilt_deg"] = _max_tilt(ulog)

    # --- logged messages ----------------------------------------------------
    msgs = []
    for m in ulog.logged_messages:
        rel_s = max(0.0, (m.timestamp - ulog.start_timestamp) / 1e6)
        msgs.append(
            {
                "t": round(rel_s, 3),
                "level": common.px4_level_name(m.log_level),
                "msg": m.message.strip(),
            }
        )
    result["logged_messages"] = msgs

    # Degrade to 'partial' if we never got a position fix.
    if not track_points:
        result["parse_status"] = "partial"
        result["parse_error"] = "no valid GPS position in log"

    return result


def _compute_kinematics(ulog: ULog, track_points, result: dict) -> None:
    lp = _get(ulog, "vehicle_local_position")
    distance = common.track_distance_m(track_points) if track_points else None

    max_speed = max_h = max_up = max_down = None
    max_alt_diff = None

    if lp is not None:
        d = lp.data
        vx, vy, vz = d.get("vx"), d.get("vy"), d.get("vz")
        z = d.get("z")
        if vx is not None and vy is not None and vz is not None:
            speeds, hspeeds, ups, downs = [], [], [], []
            for i in range(len(vx)):
                a, b, c = float(vx[i]), float(vy[i]), float(vz[i])
                if any(math.isnan(v) for v in (a, b, c)):
                    continue
                speeds.append(math.sqrt(a * a + b * b + c * c))
                hspeeds.append(math.sqrt(a * a + b * b))
                # NED: z is down-positive, so climb rate is -vz.
                ups.append(-c)
                downs.append(c)
            if speeds:
                max_speed = max(speeds)
                max_h = max(hspeeds)
                max_up = max(0.0, max(ups))
                max_down = max(0.0, max(downs))
        if z is not None:
            alts = [-float(v) for v in z if not math.isnan(float(v))]
            if alts:
                max_alt_diff = max(alts) - min(alts)

    dur = result.get("duration_s") or 0.0
    avg = (distance / dur) if (distance and dur > 0) else None

    result["distance_m"] = distance
    result["max_alt_diff_m"] = max_alt_diff
    result["avg_speed_kmh"] = common.ms_to_kmh(avg) if avg is not None else None
    result["max_speed_kmh"] = common.ms_to_kmh(max_speed) if max_speed is not None else None
    result["max_speed_h_kmh"] = common.ms_to_kmh(max_h) if max_h is not None else None
    result["max_speed_up_kmh"] = common.ms_to_kmh(max_up) if max_up is not None else None
    result["max_speed_down_kmh"] = common.ms_to_kmh(max_down) if max_down is not None else None


def _max_tilt(ulog: ULog) -> float | None:
    att = _get(ulog, "vehicle_attitude")
    if att is None:
        return None
    d = att.data
    q0, q1, q2, q3 = d.get("q[0]"), d.get("q[1]"), d.get("q[2]"), d.get("q[3]")
    if q0 is None:
        return None
    max_tilt = 0.0
    found = False
    for i in range(len(q0)):
        x, y = float(q1[i]), float(q2[i])
        # cos(tilt) of body-z vs world-z for a unit quaternion [w,x,y,z]
        cos_t = 1.0 - 2.0 * (x * x + y * y)
        cos_t = max(-1.0, min(1.0, cos_t))
        tilt = math.degrees(math.acos(cos_t))
        if tilt > max_tilt:
            max_tilt = tilt
        found = True
    return max_tilt if found else None
