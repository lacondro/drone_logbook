import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { fmtDuration } from "../format.js";

export default function Pilots() {
  const [pilots, setPilots] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [newPilot, setNewPilot] = useState("");
  const [adding, setAdding] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setPilots(await api.listPilots());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function addPilot() {
    if (!newPilot.trim()) return;
    setAdding(true);
    setError(null);
    try {
      await api.createPilot(newPilot.trim());
      setNewPilot("");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setAdding(false);
    }
  }

  async function removePilot(name) {
    if (!window.confirm(`Delete pilot "${name}" from the roster?`)) return;
    setError(null);
    try {
      await api.deletePilot(name);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="page">
      <div className="table-head-row">
        <h1>Pilots</h1>
        {loading && <span className="muted">loading…</span>}
      </div>
      <p className="muted">
        Flight totals per pilot. Add pilots to the roster below; pilots with no
        flights can be deleted.
      </p>

      <div className="card add-row">
        <input
          className="input"
          placeholder="Pilot name"
          value={newPilot}
          onChange={(e) => setNewPilot(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addPilot()}
        />
        <button
          className="btn primary"
          onClick={addPilot}
          disabled={adding || !newPilot.trim()}
        >
          {adding ? "…" : "+ Add pilot"}
        </button>
      </div>

      {error && <div className="banner error">{error}</div>}

      {pilots.map((p) => (
        <div className="card pilot-card" key={p.pilot}>
          <div className="pilot-head">
            <div className="pilot-name">
              <Link to={`/?q=${encodeURIComponent(p.pilot)}`}>{p.pilot}</Link>
            </div>
            <div className="pilot-totals">
              <span className="stat">
                <span className="stat-val">{p.total_sorties}</span>
                <span className="stat-lbl">sorties</span>
              </span>
              <span className="stat">
                <span className="stat-val">{fmtDuration(p.total_duration_s)}</span>
                <span className="stat-lbl">total time</span>
              </span>
              <span className="stat">
                <span className="stat-val">{p.vehicles.length}</span>
                <span className="stat-lbl">aircraft</span>
              </span>
              <button
                className="btn danger sm"
                onClick={() => removePilot(p.pilot)}
                disabled={p.total_sorties > 0}
                title={
                  p.total_sorties > 0
                    ? "Reassign/clear this pilot's flights before deleting"
                    : "Delete this pilot from the roster"
                }
              >
                Delete
              </button>
            </div>
          </div>

          <table className="table pilot-vehicles">
            <thead>
              <tr>
                <th>Aircraft</th>
                <th>Stack</th>
                <th className="num">Sorties</th>
                <th className="num">Flight time</th>
              </tr>
            </thead>
            <tbody>
              {p.vehicles.map((v) => (
                <tr key={v.vehicle_uid || "unassigned"}>
                  <td className="strong">
                    {v.vehicle_uid ? (
                      <Link to={`/?vehicle_uid=${encodeURIComponent(v.vehicle_uid)}`}>
                        {v.label}
                      </Link>
                    ) : (
                      v.label
                    )}
                  </td>
                  <td>
                    {v.stack ? (
                      <span className={`badge ${v.stack === "px4" ? "badge-px4" : "badge-ap"}`}>
                        {v.stack === "px4" ? "PX4" : "ArduPilot"}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="num">{v.sorties}</td>
                  <td className="num">{fmtDuration(v.duration_s)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {!pilots.length && !loading && (
        <div className="card empty">
          No pilots yet. Open a flight and record a pilot in its logbook entry.
        </div>
      )}
    </div>
  );
}
