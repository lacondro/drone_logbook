"""FastAPI app: scan, flights list/detail/edit, vehicles management."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import geocode
import scanner

app = FastAPI(title="Drone Flight Logbook", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local demo only
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.restore_active_db()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ScanRequest(BaseModel):
    path: str
    recursive: bool = True


class FlightPatch(BaseModel):
    pilot: str | None = None
    remarks: str | None = None
    vehicle_uid: str | None = None  # manual re-assignment (spec §6.4)


class BulkAssign(BaseModel):
    ids: list[int]
    pilot: str | None = None
    vehicle_uid: str | None = None


class VehiclePatch(BaseModel):
    registration_number: str | None = None
    nickname: str | None = None
    notes: str | None = None


class VehicleCreate(BaseModel):
    registration_number: str | None = None
    nickname: str | None = None
    notes: str | None = None


class PilotCreate(BaseModel):
    name: str
    notes: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Columns returned in list view (track/messages excluded to keep it light).
_LIST_COLUMNS = (
    "f.id, f.file_name, f.file_path, f.stack, f.vehicle_uid, f.log_start_utc, "
    "f.start_location, "
    "f.duration_s, f.distance_m, f.max_alt_diff_m, f.max_speed_kmh, f.airframe, "
    "f.hardware, f.pilot, f.remarks, f.parse_status, f.parse_error, "
    "f.error_msg_count, f.warn_msg_count, "
    "v.registration_number, v.nickname"
)


def _flight_list_row(row) -> dict:
    return dict(row)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------
@app.post("/api/scan")
def scan(req: ScanRequest):
    try:
        summary = scanner.scan_folder(req.path, req.recursive)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Best-effort reverse geocoding of start positions (cached, never fatal).
    conn = db.get_conn()
    try:
        summary["geocoded"] = geocode.backfill(conn)
    except Exception:  # noqa: BLE001
        summary["geocoded"] = 0
    finally:
        conn.close()
    db.backup_active()
    db_path = db.get_db_path()
    summary["folder"] = str(db_path.parent)
    summary["db_path"] = str(db_path)
    return summary


@app.post("/api/upload")
async def upload_logs(files: list[UploadFile] = File(...)):
    """Save uploaded log files into the active logbook folder, then scan.

    Lets a browser push local `.ulg`/`.bin` logs to the server (e.g. the NAS),
    since the backend can only read server-side paths, not the client's disk.
    """
    folder = db.get_db_path().parent
    folder.mkdir(parents=True, exist_ok=True)

    saved = 0
    skipped: list[str] = []
    for uf in files:
        name = Path(uf.filename or "").name  # strip any directory component
        if not name:
            continue
        if Path(name).suffix.lower() not in scanner.LOG_EXTENSIONS:
            skipped.append(name)
            continue
        dest = folder / name
        with open(dest, "wb") as out:
            while chunk := await uf.read(1024 * 1024):
                out.write(chunk)
        saved += 1

    # Parse whatever is now in the folder (new files get added/refreshed).
    summary = scanner.scan_folder(str(folder), recursive=True)
    conn = db.get_conn()
    try:
        summary["geocoded"] = geocode.backfill(conn)
    except Exception:  # noqa: BLE001
        summary["geocoded"] = 0
    finally:
        conn.close()
    db.backup_active()

    db_path = db.get_db_path()
    summary.update(
        uploaded=saved,
        skipped=skipped,
        folder=str(db_path.parent),
        db_path=str(db_path),
    )
    return summary


@app.get("/api/status")
def status():
    """Active logbook location + flight count (for the UI header)."""
    db_path = db.get_db_path()
    conn = db.get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM flights").fetchone()["c"]
    finally:
        conn.close()
    return {
        "folder": str(db_path.parent),
        "db_path": str(db_path),
        "flight_count": count,
        "default_folder": db.default_folder(),
    }


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------
_SORT_FIELDS = {
    "date": "f.log_start_utc",
    "duration": "f.duration_s",
    "distance": "f.distance_m",
    "name": "f.file_name",
    "pilot": "f.pilot",
}


@app.get("/api/flights")
def list_flights(
    vehicle_uid: str | None = None,
    stack: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    sort: str = "date",
    order: str = "desc",
):
    where, params = [], []
    if vehicle_uid:
        where.append("f.vehicle_uid = ?")
        params.append(vehicle_uid)
    if stack:
        where.append("f.stack = ?")
        params.append(stack)
    if date_from:
        where.append("f.log_start_utc >= ?")
        params.append(date_from)
    if date_to:
        where.append("f.log_start_utc <= ?")
        params.append(date_to)
    if q:
        where.append(
            "(f.file_name LIKE ? OR f.pilot LIKE ? OR f.remarks LIKE ? "
            "OR f.start_location LIKE ? "
            "OR v.registration_number LIKE ? OR v.nickname LIKE ?)"
        )
        like = f"%{q}%"
        params += [like] * 6

    sort_col = _SORT_FIELDS.get(sort, "f.log_start_utc")
    order_sql = "ASC" if order.lower() == "asc" else "DESC"
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    # NULLs (e.g. failed parses with no date) sort last.
    sql = (
        f"SELECT {_LIST_COLUMNS} FROM flights f "
        f"LEFT JOIN vehicles v ON f.vehicle_uid = v.vehicle_uid "
        f"{where_sql} ORDER BY ({sort_col} IS NULL), {sort_col} {order_sql}"
    )

    conn = db.get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [_flight_list_row(r) for r in rows]


@app.post("/api/flights/bulk")
def bulk_assign(body: BulkAssign):
    """Assign pilot and/or vehicle to many flights at once."""
    fields: dict = {}
    if body.pilot is not None:
        fields["pilot"] = body.pilot
    if body.vehicle_uid is not None:
        fields["vehicle_uid"] = body.vehicle_uid
    if not body.ids:
        raise HTTPException(status_code=400, detail="no flights selected")
    if not fields:
        raise HTTPException(status_code=400, detail="nothing to assign")

    conn = db.get_conn()
    try:
        # Make sure the target vehicle row exists before assigning.
        if fields.get("vehicle_uid"):
            v = conn.execute(
                "SELECT vehicle_uid FROM vehicles WHERE vehicle_uid = ?",
                (fields["vehicle_uid"],),
            ).fetchone()
            if v is None:
                now = _now()
                conn.execute(
                    "INSERT INTO vehicles (vehicle_uid, created_at, updated_at) VALUES (?,?,?)",
                    (fields["vehicle_uid"], now, now),
                )
        fields["updated_at"] = _now()
        set_cols = list(fields.keys())
        set_sql = ", ".join(f"{c} = ?" for c in set_cols)
        ph = ", ".join(["?"] * len(body.ids))
        params = [fields[c] for c in set_cols] + body.ids
        cur = conn.execute(
            f"UPDATE flights SET {set_sql} WHERE id IN ({ph})", params
        )
        conn.commit()
        updated = cur.rowcount
    finally:
        conn.close()
    db.backup_active()
    return {"updated": updated}


@app.get("/api/flights/{flight_id}")
def get_flight(flight_id: int):
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT f.*, v.registration_number, v.nickname, v.notes AS vehicle_notes "
            "FROM flights f LEFT JOIN vehicles v ON f.vehicle_uid = v.vehicle_uid "
            "WHERE f.id = ?",
            (flight_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="flight not found")
    d = dict(row)
    d["track_geojson"] = json.loads(d["track_geojson"]) if d.get("track_geojson") else None
    msgs = json.loads(d["logged_messages"]) if d.get("logged_messages") else []
    # Attach an inferred severity so the UI can flag ArduPilot messages (which
    # are all logged as INFO) consistently with the list-view status.
    from parsers import common
    for m in msgs:
        m["sev"] = common.message_severity(m.get("level"), m.get("msg"))
    d["logged_messages"] = msgs
    return d


@app.patch("/api/flights/{flight_id}")
def patch_flight(flight_id: int, patch: FlightPatch):
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    conn = db.get_conn()
    try:
        exists = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="flight not found")
        # If reassigning to a new vehicle_uid, make sure the vehicle row exists.
        if "vehicle_uid" in fields and fields["vehicle_uid"]:
            v = conn.execute(
                "SELECT vehicle_uid FROM vehicles WHERE vehicle_uid = ?",
                (fields["vehicle_uid"],),
            ).fetchone()
            if v is None:
                now = _now()
                conn.execute(
                    "INSERT INTO vehicles (vehicle_uid, created_at, updated_at) VALUES (?,?,?)",
                    (fields["vehicle_uid"], now, now),
                )
        fields["updated_at"] = _now()
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        conn.execute(f"UPDATE flights SET {sets} WHERE id = :id", {**fields, "id": flight_id})
        conn.commit()
    finally:
        conn.close()
    db.backup_active()  # snapshot user annotations
    return get_flight(flight_id)


@app.delete("/api/flights/{flight_id}")
def delete_flight(flight_id: int, delete_file: bool = False):
    """Remove a flight from the logbook. With delete_file=true, also delete the
    underlying log file from disk (so a re-scan won't bring it back).

    Safety: a file is only unlinked when it lives inside the active logbook
    folder, never an arbitrary path.
    """
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id, file_path FROM flights WHERE id = ?", (flight_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="flight not found")
        file_path = row["file_path"]
        conn.execute("DELETE FROM flights WHERE id = ?", (flight_id,))
        conn.commit()
    finally:
        conn.close()

    file_deleted = False
    file_error = None
    if delete_file and file_path:
        try:
            p = Path(file_path).resolve()
            folder = db.get_db_path().parent.resolve()
            # Only delete files that live under the logbook folder.
            if folder == p.parent or folder in p.parents:
                if p.exists():
                    p.unlink()
                    file_deleted = True
            else:
                file_error = "file is outside the logbook folder; not deleted"
        except OSError as e:
            file_error = str(e)

    db.backup_active()
    return {"deleted": True, "file_deleted": file_deleted, "file_error": file_error}


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------
@app.get("/api/vehicles")
def list_vehicles():
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT v.*,
                      COUNT(f.id) AS flight_count,
                      COALESCE(SUM(f.duration_s), 0) AS total_duration_s,
                      MAX(f.log_start_utc) AS last_flight_utc
               FROM vehicles v
               LEFT JOIN flights f ON f.vehicle_uid = v.vehicle_uid
               GROUP BY v.vehicle_uid
               ORDER BY (v.registration_number IS NULL), v.registration_number,
                        v.vehicle_uid""",
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.post("/api/vehicles")
def create_vehicle(body: VehicleCreate):
    """Manually add an aircraft (not derived from a log). Gets a synthetic uid."""
    if not (body.registration_number or body.nickname):
        raise HTTPException(
            status_code=400, detail="registration number or nickname required"
        )
    uid = "manual-" + uuid.uuid4().hex[:12]
    now = _now()
    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO vehicles
               (vehicle_uid, registration_number, nickname, notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (uid, body.registration_number, body.nickname, body.notes, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    db.backup_active()
    return {"vehicle_uid": uid}


@app.delete("/api/vehicles/{vehicle_uid:path}")
def delete_vehicle(vehicle_uid: str):
    """Delete an aircraft. Only allowed when no flight references it (reassign
    those flights first), so log-derived data is never orphaned."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT vehicle_uid FROM vehicles WHERE vehicle_uid = ?", (vehicle_uid,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="aircraft not found")
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM flights WHERE vehicle_uid = ?", (vehicle_uid,)
        ).fetchone()["c"]
        if n:
            raise HTTPException(
                status_code=409,
                detail=f"{n} flight(s) still assigned — reassign them first",
            )
        conn.execute("DELETE FROM vehicles WHERE vehicle_uid = ?", (vehicle_uid,))
        conn.commit()
    finally:
        conn.close()
    db.backup_active()
    return {"deleted": True}


@app.patch("/api/vehicles/{vehicle_uid:path}")
def patch_vehicle(vehicle_uid: str, patch: VehiclePatch):
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT vehicle_uid FROM vehicles WHERE vehicle_uid = ?", (vehicle_uid,)
        ).fetchone()
        now = _now()
        if row is None:
            conn.execute(
                "INSERT INTO vehicles (vehicle_uid, created_at, updated_at) VALUES (?,?,?)",
                (vehicle_uid, now, now),
            )
        fields["updated_at"] = now
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        conn.execute(
            f"UPDATE vehicles SET {sets} WHERE vehicle_uid = :uid",
            {**fields, "uid": vehicle_uid},
        )
        conn.commit()
        out = conn.execute(
            "SELECT * FROM vehicles WHERE vehicle_uid = ?", (vehicle_uid,)
        ).fetchone()
    finally:
        conn.close()
    db.backup_active()  # snapshot registrations
    return dict(out)


# ---------------------------------------------------------------------------
# Pilots (a managed roster, unioned with names found on flights)
# ---------------------------------------------------------------------------
@app.get("/api/pilots")
def list_pilots():
    """Per-pilot totals (sorties + flight time) with a per-vehicle breakdown.
    Includes roster pilots that have no flights yet (shown with zero totals)."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT TRIM(f.pilot) AS pilot,
                      f.vehicle_uid AS vehicle_uid,
                      v.registration_number, v.nickname, v.stack,
                      COUNT(f.id) AS sorties,
                      COALESCE(SUM(f.duration_s), 0) AS duration_s
               FROM flights f
               LEFT JOIN vehicles v ON f.vehicle_uid = v.vehicle_uid
               WHERE f.pilot IS NOT NULL AND TRIM(f.pilot) <> ''
               GROUP BY TRIM(f.pilot), f.vehicle_uid
               ORDER BY TRIM(f.pilot)"""
        ).fetchall()
        roster = {r["name"] for r in conn.execute("SELECT name FROM pilots").fetchall()}
    finally:
        conn.close()

    pilots: dict[str, dict] = {}

    def _entry(name):
        return pilots.setdefault(
            name,
            {
                "pilot": name,
                "total_sorties": 0,
                "total_duration_s": 0.0,
                "in_roster": name in roster,
                "vehicles": [],
            },
        )

    for r in rows:
        p = _entry(r["pilot"])
        p["total_sorties"] += r["sorties"]
        p["total_duration_s"] += r["duration_s"]
        label = r["registration_number"] or r["nickname"] or r["vehicle_uid"] or "Unassigned"
        p["vehicles"].append(
            {
                "vehicle_uid": r["vehicle_uid"],
                "label": label,
                "stack": r["stack"],
                "sorties": r["sorties"],
                "duration_s": r["duration_s"],
            }
        )
    # Roster pilots with no flights yet still show up.
    for name in roster:
        _entry(name)

    # Most-active pilots first; vehicles within each by flight time.
    out = sorted(pilots.values(), key=lambda x: (-x["total_duration_s"], x["pilot"]))
    for p in out:
        p["vehicles"].sort(key=lambda v: -v["duration_s"])
    return out


@app.post("/api/pilots")
def create_pilot(body: PilotCreate):
    """Add a pilot to the roster (so it can be picked before any flight uses it)."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="pilot name required")
    now = _now()
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO pilots (name, notes, created_at, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(name) DO NOTHING",
            (name, body.notes, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    db.backup_active()
    return {"name": name}


@app.delete("/api/pilots/{name:path}")
def delete_pilot(name: str):
    """Remove a pilot from the roster. Only allowed when no flight uses the name
    (reassign/clear those flights first) so flight annotations are never lost."""
    conn = db.get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM flights WHERE TRIM(pilot) = ?", (name.strip(),)
        ).fetchone()["c"]
        if n:
            raise HTTPException(
                status_code=409,
                detail=f"{n} flight(s) still use this pilot — reassign them first",
            )
        conn.execute("DELETE FROM pilots WHERE name = ?", (name,))
        conn.commit()
    finally:
        conn.close()
    db.backup_active()
    return {"deleted": True}


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve built frontend (production-like single-port mode), if present.
# Static assets are served directly; any other (non-/api) path falls back to
# index.html so client-side routes survive a refresh / deep link.
# ---------------------------------------------------------------------------
_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_DIST / "index.html"))
