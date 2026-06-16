import { useEffect, useState, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import MapTrack from "../components/MapTrack.jsx";
import { fmtDuration, fmtDateTime, fmtDistance, fmtNum } from "../format.js";

function InfoRow({ label, value }) {
  return (
    <div className="inforow">
      <span className="info-label">{label}</span>
      <span className="info-value">{value ?? "—"}</span>
    </div>
  );
}

// Color by inferred severity (sev), so ArduPilot messages — all logged as INFO
// — still show as WARN/ERROR when their text indicates a problem.
const SEV_CLS = { error: "lvl-err", warn: "lvl-warn", info: "lvl-info" };

// Label: keep the real PX4 level name, but surface the inferred severity when
// the raw level is an undifferentiated "INFO" (i.e. ArduPilot).
function levelLabel(m) {
  if ((m.level === "INFO" || m.level == null) && m.sev && m.sev !== "info") {
    return m.sev === "error" ? "ERROR" : "WARN";
  }
  return m.level || "—";
}

export default function FlightDetail({ id: propId, onUpdated }) {
  const params = useParams();
  const navigate = useNavigate();
  const id = propId ?? params.id;
  const panel = propId !== undefined; // rendered as the right-hand panel
  const [f, setF] = useState(null);
  const [vehicles, setVehicles] = useState([]);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  // editable user fields
  const [pilot, setPilot] = useState("");
  const [remarks, setRemarks] = useState("");
  const [reassign, setReassign] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      const [flight, vs] = await Promise.all([
        api.getFlight(Number(id)),
        api.listVehicles(),
      ]);
      setF(flight);
      setVehicles(vs);
      setPilot(flight.pilot || "");
      setRemarks(flight.remarks || "");
      setReassign(flight.vehicle_uid || "");
    } catch (e) {
      setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function remove() {
    const ok = window.confirm(
      `Delete this flight from the logbook AND permanently delete the log file ` +
        `from the server?\n\n${f.file_name}\n\nThis cannot be undone.`
    );
    if (!ok) return;
    setError(null);
    try {
      await api.deleteFlight(f.id, true);
      onUpdated && onUpdated(); // refresh the list
      navigate("/"); // clear the now-deleted selection
    } catch (e) {
      setError(e.message);
    }
  }

  async function save() {
    setError(null);
    try {
      const patch = { pilot, remarks };
      if (reassign && reassign !== f.vehicle_uid) patch.vehicle_uid = reassign;
      const updated = await api.patchFlight(f.id, patch);
      setF(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onUpdated && onUpdated(); // refresh the list (pilot/registration changed)
    } catch (e) {
      setError(e.message);
    }
  }

  // Placeholder when no flight is selected (split-view right panel).
  if (!id)
    return (
      <div className="detail-empty muted">
        <div className="detail-empty-icon">🛈</div>
        Select a flight from the list to see its details.
      </div>
    );
  if (error && !f) return <div className="banner error">{error}</div>;
  if (!f) return <div className="page muted">Loading…</div>;

  const reg = f.registration_number;
  const title =
    reg || f.nickname || f.airframe || (f.stack === "px4" ? "PX4 Vehicle" : "ArduPilot Vehicle");

  return (
    <div className={panel ? "detail" : "page detail"}>
      <div className="detail-top">
        {!panel && (
          <Link to="/" className="back">
            ← Flights
          </Link>
        )}
        <h1>{title}</h1>
        <span className={`badge ${f.stack === "px4" ? "badge-px4" : "badge-ap"}`}>
          {f.stack === "px4" ? "PX4" : "ArduPilot"}
        </span>
      </div>

      {f.parse_status !== "ok" && (
        <div className={`banner ${f.parse_status === "error" ? "error" : "warn"}`}>
          Parse {f.parse_status}: {f.parse_error}
        </div>
      )}

      {/* 2×2 detail grid — row1: vehicle/stats | logbook entry, row2: track | messages */}
      <div className="detail-cols">
      {/* Info blocks (reference layout: left vehicle/firmware, right stats) */}
      <div className="detail-grid">
        <section className="card">
          <h2>Vehicle &amp; Firmware</h2>
          <InfoRow label="Airframe" value={f.airframe} />
          <InfoRow label="Hardware" value={f.hardware} />
          <InfoRow label="Software Version" value={f.sw_version} />
          <InfoRow label="OS Version" value={f.os_version} />
          <InfoRow label="Estimator" value={f.estimator} />
          <InfoRow label="Logging Start" value={fmtDateTime(f.log_start_utc)} />
          <InfoRow label="Start Location" value={f.start_location} />
          <InfoRow label="Logging Duration" value={fmtDuration(f.duration_s)} />
          <InfoRow
            label="Vehicle Life Flight Time"
            value={f.vehicle_life_s != null ? fmtDuration(f.vehicle_life_s) : "—"}
          />
          <InfoRow label="Vehicle UID" value={<code>{f.vehicle_uid || "—"}</code>} />
        </section>

        <section className="card">
          <h2>Flight Statistics</h2>
          <InfoRow label="Distance" value={fmtDistance(f.distance_m)} />
          <InfoRow label="Max Altitude Difference" value={fmtNum(f.max_alt_diff_m, "m")} />
          <InfoRow label="Average Speed" value={fmtNum(f.avg_speed_kmh, "km/h")} />
          <InfoRow label="Max Speed" value={fmtNum(f.max_speed_kmh, "km/h")} />
          <InfoRow label="Max Speed Horizontal" value={fmtNum(f.max_speed_h_kmh, "km/h")} />
          <InfoRow label="Max Speed Up" value={fmtNum(f.max_speed_up_kmh, "km/h")} />
          <InfoRow label="Max Speed Down" value={fmtNum(f.max_speed_down_kmh, "km/h")} />
          <InfoRow label="Max Tilt Angle" value={fmtNum(f.max_tilt_deg, "deg")} />
        </section>
      </div>

      {/* Logbook entry (user data) */}
      <section className="card">
        <h2>Logbook Entry</h2>
        <div className="form-grid">
          <label className="field">
            <span>Pilot</span>
            <input
              className="input"
              value={pilot}
              onChange={(e) => setPilot(e.target.value)}
              placeholder="Pilot name"
            />
          </label>
          <label className="field">
            <span>Assigned vehicle</span>
            <select
              className="input"
              value={reassign}
              onChange={(e) => setReassign(e.target.value)}
            >
              {!f.vehicle_uid && <option value="">— unassigned —</option>}
              {vehicles.map((v) => (
                <option key={v.vehicle_uid} value={v.vehicle_uid}>
                  {v.registration_number || v.nickname || v.vehicle_uid}
                </option>
              ))}
            </select>
            <span className="hint">
              ArduPilot auto-matching is approximate — reassign here if needed.{" "}
              <Link to="/vehicles">Manage registrations →</Link>
            </span>
          </label>
        </div>
        <label className="field">
          <span>Remarks</span>
          <textarea
            className="input"
            rows={3}
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder="Notes about this flight…"
          />
        </label>
        <div className="form-actions">
          <button className="btn primary" onClick={save}>
            Save entry
          </button>
          {saved && <span className="saved">✓ Saved</span>}
          {error && <span className="banner error inline">{error}</span>}
          <button
            className="btn danger push-right"
            onClick={remove}
            title="Delete this flight and its log file from the server"
          >
            Delete flight
          </button>
        </div>
      </section>

      {/* Map */}
      <section className="card map-card">
        <h2>Flight Track</h2>
        <MapTrack geojson={f.track_geojson} />
      </section>

      {/* Logged messages */}
      <section className="card msgs-card">
        <h2>
          Logged Messages <span className="muted">({f.logged_messages.length})</span>
        </h2>
        <div className="msgs-scroll">
        {f.logged_messages.length ? (
          <table className="table msgs">
            <thead>
              <tr>
                <th className="num">#</th>
                <th className="num">Time</th>
                <th>Level</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {f.logged_messages.map((m, i) => (
                <tr key={i}>
                  <td className="num muted">{i}</td>
                  <td className="num">{fmtMsgTime(m.t)}</td>
                  <td>
                    <span className={`lvl ${SEV_CLS[m.sev] || "lvl-dim"}`}>
                      {levelLabel(m)}
                    </span>
                  </td>
                  <td>{m.msg}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="muted">No logged messages.</div>
        )}
        </div>
      </section>
      </div>

      <div className="filefoot muted">{f.file_path}</div>
    </div>
  );
}

function fmtMsgTime(t) {
  if (t == null) return "—";
  const total = Math.floor(t);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
