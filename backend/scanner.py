"""Folder scanning: discover logs, parse new/changed ones, cache in SQLite."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from db import get_conn
from parsers import parse_log

LOG_EXTENSIONS = {".ulg", ".bin"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    """Cheap change-detection token: size + mtime (per spec §5)."""
    st = path.stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


def content_hash(path: Path) -> str:
    """SHA-256 of the file's bytes — identifies byte-identical logs regardless
    of filename, so the same log uploaded under two names is detected."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_duplicate(conn, chash, result, fpath):
    """Return the id of an already-stored flight that this file duplicates, or
    None. Two signals: identical bytes (content_hash), or the same flight logged
    under a different name/format (same vehicle_uid + log_start_utc)."""
    if chash:
        row = conn.execute(
            "SELECT id FROM flights WHERE content_hash = ? AND file_path != ? LIMIT 1",
            (chash, fpath),
        ).fetchone()
        if row:
            return row["id"]
    vu = result.get("vehicle_uid")
    ts = result.get("log_start_utc")
    if vu and ts:
        row = conn.execute(
            "SELECT id FROM flights WHERE vehicle_uid = ? AND log_start_utc = ? "
            "AND file_path != ? LIMIT 1",
            (vu, ts, fpath),
        ).fetchone()
        if row:
            return row["id"]
    return None


def discover(folder: Path, recursive: bool) -> list[Path]:
    if recursive:
        it = folder.rglob("*")
    else:
        it = folder.iterdir()
    return sorted(
        p for p in it if p.is_file() and p.suffix.lower() in LOG_EXTENSIONS
    )


def _ensure_vehicle(conn, vehicle_uid, stack, airframe, hardware) -> None:
    """Create a vehicles row for a new uid; never overwrite user edits."""
    if not vehicle_uid:
        return
    row = conn.execute(
        "SELECT vehicle_uid FROM vehicles WHERE vehicle_uid = ?", (vehicle_uid,)
    ).fetchone()
    if row is None:
        now = _now()
        conn.execute(
            """INSERT INTO vehicles
               (vehicle_uid, stack, airframe, hardware, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (vehicle_uid, stack, airframe, hardware, now, now),
        )


# Columns written from a parse result (user fields like pilot/remarks excluded).
_PARSE_COLUMNS = [
    "stack", "vehicle_uid", "log_start_utc", "duration_s",
    "distance_m", "max_alt_diff_m", "avg_speed_kmh", "max_speed_kmh",
    "max_speed_h_kmh", "max_speed_up_kmh", "max_speed_down_kmh", "max_tilt_deg",
    "airframe", "hardware", "sw_version", "os_version", "estimator", "vehicle_life_s",
    "track_geojson", "logged_messages", "parse_status", "parse_error",
]


def _result_to_row(result: dict) -> dict:
    row = {k: result.get(k) for k in _PARSE_COLUMNS}
    # JSON-encode nested structures for storage.
    tg = result.get("track_geojson")
    row["track_geojson"] = json.dumps(tg) if tg else None
    lm = result.get("logged_messages")
    row["logged_messages"] = json.dumps(lm, ensure_ascii=False) if lm else None
    # Count error/warning messages so the list view can flag the flight.
    from parsers import common
    row["error_msg_count"] = common.count_error_messages(lm)
    row["warn_msg_count"] = common.count_warning_messages(lm)
    return row


def _parse_one(path: Path) -> dict:
    """Parse a log, converting any exception into an error result row."""
    try:
        return parse_log(str(path))
    except Exception as e:  # noqa: BLE001 - isolate a bad log from the whole scan
        return {
            "stack": None,
            "parse_status": "error",
            "parse_error": f"{type(e).__name__}: {e}",
            "logged_messages": [],
        }


def scan_folder(folder_path: str, recursive: bool = True) -> dict:
    """Scan a folder, (re)parsing only new/changed logs. Returns a summary."""
    folder = Path(folder_path).expanduser()
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"folder not found: {folder_path}")

    # The logbook DB lives inside the scanned folder so annotations stay with
    # the logs. Switch to it (creating/upgrading schema) before scanning.
    import db as _db
    _db.set_active_db(_db.db_for_folder(folder))

    files = discover(folder, recursive)
    summary = {
        "scanned": len(files), "parsed_new": 0, "skipped_cached": 0,
        "failed": 0, "duplicates": 0, "pruned_missing": 0,
    }

    conn = get_conn()
    try:
        for path in files:
            fpath = str(path.resolve())
            fhash = file_hash(path)
            existing = conn.execute(
                "SELECT id, file_hash, content_hash FROM flights WHERE file_path = ?",
                (fpath,),
            ).fetchone()
            if existing and existing["file_hash"] == fhash:
                # Unchanged file: backfill its content hash once (older DBs).
                if existing["content_hash"] is None:
                    try:
                        conn.execute(
                            "UPDATE flights SET content_hash = ? WHERE id = ?",
                            (content_hash(path), existing["id"]),
                        )
                        conn.commit()
                    except OSError:
                        pass
                summary["skipped_cached"] += 1
                continue

            result = _parse_one(path)
            try:
                chash = content_hash(path)
            except OSError:
                chash = None

            # New file (no row at this path) that duplicates another flight —
            # identical bytes, or the same flight under a different name/format.
            if existing is None and _find_duplicate(conn, chash, result, fpath) is not None:
                summary["duplicates"] += 1
                continue

            if result.get("parse_status") == "error":
                summary["failed"] += 1
            else:
                summary["parsed_new"] += 1

            _ensure_vehicle(
                conn, result.get("vehicle_uid"), result.get("stack"),
                result.get("airframe"), result.get("hardware"),
            )

            row = _result_to_row(result)
            row.update(
                file_path=fpath, file_name=path.name, file_hash=fhash,
                content_hash=chash, updated_at=_now(),
            )

            if existing:
                # Re-parse of a changed file: refresh parse-derived columns only.
                sets = ", ".join(f"{k} = :{k}" for k in row)
                conn.execute(f"UPDATE flights SET {sets} WHERE id = :id", {**row, "id": existing["id"]})
            else:
                row["created_at"] = _now()
                cols = ", ".join(row)
                ph = ", ".join(f":{k}" for k in row)
                conn.execute(f"INSERT INTO flights ({cols}) VALUES ({ph})", row)
            conn.commit()

        # Prune stale rows: logs whose file no longer exists on disk (e.g. moved,
        # renamed, or deleted outside the app). This stops a re-scan from showing
        # duplicates left over from an old path — like an earlier DB that still
        # referenced the logs under a previous folder name.
        rows = conn.execute("SELECT id, file_path FROM flights").fetchall()
        missing = [r for r in rows if not os.path.exists(r["file_path"])]
        # Safety: don't wipe the logbook if a transient mount failure makes every
        # file look missing. Only prune when this scan saw files AND at least one
        # row still resolves to an existing file.
        if rows and missing and len(missing) < len(rows):
            conn.executemany(
                "DELETE FROM flights WHERE id = ?", [(r["id"],) for r in missing]
            )
            conn.commit()
            summary["pruned_missing"] = len(missing)
    finally:
        conn.close()

    return summary
