"""SQLite storage: parse cache + user data (registrations, pilot, remarks).

The active DB lives *inside the scanned log folder* (``flightlogbook.db``) so the
parse cache and the user annotations (pilot / remarks / registrations) travel
together with the logs. The backend remembers the last folder (``.active_db``
pointer) and reopens it on restart. Before any scan it falls back to a local
default DB in the backend directory.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def default_folder() -> str | None:
    """Container/shared-deployment default log folder (env LOGBOOK_DEFAULT_FOLDER)."""
    return os.environ.get("LOGBOOK_DEFAULT_FOLDER") or None

# File created inside each scanned folder.
DB_FILENAME = "flightlogbook.db"
# Where we remember the last active DB path across restarts.
_POINTER = Path(__file__).parent / ".active_db"
# Fallback DB used before the first scan.
_DEFAULT_DB = Path(__file__).parent / "logbook.db"

# Module-level "current DB". Set by set_active_db() / restored on startup.
_active_db: Path = _DEFAULT_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_uid          TEXT PRIMARY KEY,
    stack                TEXT,
    registration_number  TEXT,
    nickname             TEXT,
    airframe             TEXT,
    hardware             TEXT,
    notes                TEXT,
    created_at           TEXT,
    updated_at           TEXT
);

CREATE TABLE IF NOT EXISTS flights (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path          TEXT UNIQUE,
    file_name          TEXT,
    file_hash          TEXT,
    stack              TEXT,
    vehicle_uid        TEXT,

    log_start_utc      TEXT,
    duration_s         REAL,
    start_location     TEXT,

    distance_m         REAL,
    max_alt_diff_m     REAL,
    avg_speed_kmh      REAL,
    max_speed_kmh      REAL,
    max_speed_h_kmh    REAL,
    max_speed_up_kmh   REAL,
    max_speed_down_kmh REAL,
    max_tilt_deg       REAL,

    airframe           TEXT,
    hardware           TEXT,
    sw_version         TEXT,
    os_version         TEXT,
    estimator          TEXT,
    vehicle_life_s     REAL,

    pilot              TEXT,
    remarks            TEXT,

    track_geojson      TEXT,
    logged_messages    TEXT,
    error_msg_count    INTEGER DEFAULT 0,
    warn_msg_count     INTEGER DEFAULT 0,

    parse_status       TEXT,
    parse_error        TEXT,

    created_at         TEXT,
    updated_at         TEXT,
    FOREIGN KEY (vehicle_uid) REFERENCES vehicles(vehicle_uid)
);

CREATE INDEX IF NOT EXISTS idx_flights_vehicle ON flights(vehicle_uid);
CREATE INDEX IF NOT EXISTS idx_flights_start   ON flights(log_start_utc);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS geocode (
    key        TEXT PRIMARY KEY,   -- "lat,lon" rounded to ~1 km
    name       TEXT,
    fetched_at TEXT
);
"""

# Bump when the error/warning classification logic changes, so existing folder
# DBs recompute their cached counts on next open (no re-scan needed).
MSG_LOGIC_VERSION = "2"


def get_db_path() -> Path:
    return _active_db


def db_for_folder(folder: Path) -> Path:
    return Path(folder) / DB_FILENAME


def set_active_db(path: Path, persist: bool = True) -> None:
    """Switch the active DB, create/upgrade its schema, and remember it."""
    global _active_db
    _active_db = Path(path)
    # If the main DB is gone but a backup survives, recover it before opening.
    bak = Path(str(_active_db) + ".bak")
    if not _active_db.exists() and bak.exists():
        try:
            import shutil
            shutil.copy(bak, _active_db)
        except OSError:
            pass
    init_db()
    if persist:
        try:
            _POINTER.write_text(str(_active_db), encoding="utf-8")
        except OSError:
            pass


def restore_active_db() -> None:
    """On startup, decide which DB to open.

    Priority: LOGBOOK_DEFAULT_FOLDER (Docker / shared deployment, deterministic)
    -> last-used folder pointer (native) -> local default DB.
    """
    env = default_folder()
    if env and Path(env).is_dir():
        set_active_db(db_for_folder(Path(env)))
        return
    if _POINTER.exists():
        try:
            saved = Path(_POINTER.read_text(encoding="utf-8").strip())
        except OSError:
            saved = None
        if saved and saved.parent.exists():
            set_active_db(saved, persist=False)
            return
    init_db()  # default DB


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_active_db, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def backup_active() -> None:
    """Write a safe copy of the active DB to ``<db>.bak`` (only when it has
    data). Guards user annotations against accidental loss of the main file."""
    src = _active_db
    if not Path(src).exists():
        return
    try:
        con = sqlite3.connect(src)
        try:
            n = con.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
            if not n:
                return
            bak = Path(str(src) + ".bak")
            dst = sqlite3.connect(bak)
            try:
                con.backup(dst)
            finally:
                dst.close()
        finally:
            con.close()
    except sqlite3.Error:
        pass


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Lightweight migrations for an existing cache DB."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(flights)").fetchall()}
    added = False
    if "error_msg_count" not in cols:
        conn.execute("ALTER TABLE flights ADD COLUMN error_msg_count INTEGER DEFAULT 0")
        added = True
    if "warn_msg_count" not in cols:
        conn.execute("ALTER TABLE flights ADD COLUMN warn_msg_count INTEGER DEFAULT 0")
        added = True
    if "start_location" not in cols:
        conn.execute("ALTER TABLE flights ADD COLUMN start_location TEXT")

    # Recompute counts if a column was just added OR the classification logic
    # version changed since this DB was last written.
    row = conn.execute("SELECT value FROM meta WHERE key = 'msg_logic'").fetchone()
    stale = row is None or row["value"] != MSG_LOGIC_VERSION
    if added or stale:
        _backfill_msg_counts(conn)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('msg_logic', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (MSG_LOGIC_VERSION,),
        )


def _backfill_msg_counts(conn: sqlite3.Connection) -> None:
    """Recompute error/warning counts from already-stored messages (no re-parse)."""
    import json

    from parsers import common

    rows = conn.execute(
        "SELECT id, logged_messages FROM flights WHERE logged_messages IS NOT NULL"
    ).fetchall()
    for r in rows:
        try:
            msgs = json.loads(r["logged_messages"])
        except (TypeError, ValueError):
            continue
        conn.execute(
            "UPDATE flights SET error_msg_count = ?, warn_msg_count = ? WHERE id = ?",
            (common.count_error_messages(msgs), common.count_warning_messages(msgs), r["id"]),
        )
