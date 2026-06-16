import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { fmtDateTime, fmtDuration } from "../format.js";

function VehicleRow({ v, onSaved }) {
  const [reg, setReg] = useState(v.registration_number || "");
  const [nick, setNick] = useState(v.nickname || "");
  const [notes, setNotes] = useState(v.notes || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState(null);

  const dirty =
    reg !== (v.registration_number || "") ||
    nick !== (v.nickname || "") ||
    notes !== (v.notes || "");

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      await api.patchVehicle(v.vehicle_uid, {
        registration_number: reg,
        nickname: nick,
        notes,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onSaved && onSaved();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card vehicle-card">
      <div className="vehicle-head">
        <div>
          <div className="vehicle-title">
            {reg || <span className="muted">unregistered</span>}
            <span className={`badge ${v.stack === "px4" ? "badge-px4" : "badge-ap"}`}>
              {v.stack === "px4" ? "PX4" : v.stack === "ardupilot" ? "ArduPilot" : "?"}
            </span>
          </div>
          <code className="vehicle-uid">{v.vehicle_uid}</code>
        </div>
        <div className="vehicle-meta">
          <div>
            <Link to={`/?vehicle_uid=${encodeURIComponent(v.vehicle_uid)}`}>
              {v.flight_count} sortie{v.flight_count === 1 ? "" : "s"}
            </Link>
          </div>
          <div className="muted">Total time: {fmtDuration(v.total_duration_s)}</div>
          <div className="muted">Last: {fmtDateTime(v.last_flight_utc)}</div>
        </div>
      </div>
      <div className="vehicle-fields">
        <label className="field">
          <span>Registration #</span>
          <input
            className="input"
            value={reg}
            onChange={(e) => setReg(e.target.value)}
            placeholder="e.g. WZ-001"
          />
        </label>
        <label className="field">
          <span>Nickname</span>
          <input
            className="input"
            value={nick}
            onChange={(e) => setNick(e.target.value)}
            placeholder="e.g. Ascend-1"
          />
        </label>
        <label className="field grow">
          <span>Notes</span>
          <input
            className="input"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Airframe / hardware notes"
          />
        </label>
        <div className="vehicle-save">
          <button className="btn primary" onClick={save} disabled={!dirty || saving}>
            {saving ? "…" : "Save"}
          </button>
          {saved && <span className="saved">✓</span>}
        </div>
      </div>
      <div className="vehicle-derived muted">
        {v.airframe ? `${v.airframe} · ` : ""}
        {v.hardware || ""}
      </div>
      {err && <div className="banner error inline">{err}</div>}
    </div>
  );
}

export default function Vehicles() {
  const [vehicles, setVehicles] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setVehicles(await api.listVehicles());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="page">
      <div className="table-head-row">
        <h1>Aircrafts</h1>
        {loading && <span className="muted">loading…</span>}
      </div>
      <p className="muted">
        Map each detected vehicle to a registration number. PX4 logs are matched
        by <code>sys_uuid</code>; ArduPilot logs use the board CPU id when present.
      </p>
      {error && <div className="banner error">{error}</div>}
      {vehicles.map((v) => (
        <VehicleRow key={v.vehicle_uid} v={v} onSaved={load} />
      ))}
      {!vehicles.length && !loading && (
        <div className="card empty">No vehicles yet. Scan a folder of logs first.</div>
      )}
    </div>
  );
}
