import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import FlightDetail from "./FlightDetail.jsx";
import { fmtDuration, fmtDateTime, fmtDistance, vehicleLabel } from "../format.js";

const PAGE_SIZE = 10;

const STACK_BADGE = {
  px4: { label: "PX4", cls: "badge-px4" },
  ardupilot: { label: "ArduPilot", cls: "badge-ap" },
};

function StatusPill({ status, error, errorMsgs, warnMsgs }) {
  if (status !== "error") {
    if (errorMsgs > 0)
      return (
        <span className="pill pill-err" title={`${errorMsgs} error message(s) in log`}>
          error
        </span>
      );
    if (warnMsgs > 0)
      return (
        <span className="pill pill-warn" title={`${warnMsgs} warning message(s) in log`}>
          warn
        </span>
      );
  }
  const cls =
    status === "ok" ? "pill-ok" : status === "partial" ? "pill-warn" : "pill-err";
  return (
    <span className={`pill ${cls}`} title={error || ""}>
      {status || "—"}
    </span>
  );
}

// Build a compact list of page buttons: 1 … (window around current) … N
function pageItems(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const items = new Set([1, total, current, current - 1, current + 1]);
  const arr = [...items].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b);
  const out = [];
  let prev = 0;
  for (const n of arr) {
    if (n - prev > 1) out.push("…");
    out.push(n);
    prev = n;
  }
  return out;
}

export default function Logbook() {
  const navigate = useNavigate();
  const params = useParams();
  const selectedId = params.id ? Number(params.id) : null;
  const [searchParams] = useSearchParams();

  const [flights, setFlights] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [filters, setFilters] = useState({
    vehicle_uid: searchParams.get("vehicle_uid") || "",
    stack: "",
    date_from: "",
    date_to: "",
    q: searchParams.get("q") || "",
  });
  const [sort, setSort] = useState({ field: "date", order: "desc" });
  const [page, setPage] = useState(1);

  // scan bar
  const [scanPath, setScanPath] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState(null);
  const [activeFolder, setActiveFolder] = useState(null);

  useEffect(() => {
    api
      .status()
      .then((s) => {
        if (s.flight_count > 0) {
          setActiveFolder(s.folder);
          setScanPath((p) => p || s.folder);
        } else if (s.default_folder) {
          // Docker / shared deployment: prefill the mounted log folder path.
          setScanPath((p) => p || s.default_folder);
        }
      })
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [fl, vs] = await Promise.all([
        api.listFlights({ ...filters, sort: sort.field, order: sort.order }),
        api.listVehicles(),
      ]);
      setFlights(fl);
      setVehicles(vs);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filters, sort]);

  useEffect(() => {
    load();
  }, [load]);

  // Reset to page 1 whenever the result set changes shape.
  useEffect(() => {
    setPage(1);
  }, [filters, sort]);

  const totalPages = Math.max(1, Math.ceil(flights.length / PAGE_SIZE));
  const pageClamped = Math.min(page, totalPages);
  const pageFlights = useMemo(
    () => flights.slice((pageClamped - 1) * PAGE_SIZE, pageClamped * PAGE_SIZE),
    [flights, pageClamped]
  );

  async function runScan() {
    if (!scanPath.trim()) return;
    setScanning(true);
    setScanMsg(null);
    setError(null);
    try {
      const r = await api.scan(scanPath.trim(), recursive);
      setScanMsg(
        `Scanned ${r.scanned} · new ${r.parsed_new} · cached ${r.skipped_cached} · failed ${r.failed}`
      );
      setActiveFolder(r.folder);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setScanning(false);
    }
  }

  function setF(k, v) {
    setFilters((f) => ({ ...f, [k]: v }));
  }

  const hasFilters =
    filters.vehicle_uid || filters.stack || filters.date_from || filters.date_to || filters.q;

  return (
    <div className="logbook">
      <div className="topbars">
      {/* Scan bar */}
      <section className="card scanbar">
        <div className="scanbar-row">
          <input
            className="input grow"
            placeholder="Log folder path on the server (e.g. C:\Users\me\flightlogs)"
            value={scanPath}
            onChange={(e) => setScanPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runScan()}
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
            />
            Recursive
          </label>
          <button className="btn primary" onClick={runScan} disabled={scanning}>
            {scanning ? "Scanning…" : "Scan"}
          </button>
        </div>
        {scanMsg && <div className="scan-result">{scanMsg}</div>}
        {activeFolder && (
          <div className="scan-active muted">
            Logbook: <code>{activeFolder}\flightlogbook.db</code> — annotations
            are saved here, alongside the logs.
          </div>
        )}
      </section>

      {/* Filters */}
      <section className="card filters">
        <select
          className="input"
          value={filters.vehicle_uid}
          onChange={(e) => setF("vehicle_uid", e.target.value)}
        >
          <option value="">All vehicles</option>
          {vehicles.map((v) => (
            <option key={v.vehicle_uid} value={v.vehicle_uid}>
              {v.registration_number || v.nickname || v.vehicle_uid} ({v.flight_count})
            </option>
          ))}
        </select>
        <select
          className="input"
          value={filters.stack}
          onChange={(e) => setF("stack", e.target.value)}
        >
          <option value="">All stacks</option>
          <option value="px4">PX4</option>
          <option value="ardupilot">ArduPilot</option>
        </select>
        <input
          className="input"
          type="date"
          value={filters.date_from}
          onChange={(e) => setF("date_from", e.target.value)}
          title="From date"
        />
        <input
          className="input"
          type="date"
          value={filters.date_to}
          onChange={(e) => setF("date_to", e.target.value)}
          title="To date"
        />
        <input
          className="input grow"
          placeholder="Search file / pilot / remarks / location (e.g. 강동구)"
          value={filters.q}
          onChange={(e) => setF("q", e.target.value)}
        />
        {hasFilters && (
          <button
            className="btn ghost"
            onClick={() =>
              setFilters({ vehicle_uid: "", stack: "", date_from: "", date_to: "", q: "" })
            }
          >
            Clear
          </button>
        )}
      </section>
      </div>

      {error && <div className="banner error">{error}</div>}

      {/* Master-detail split */}
      <div className="split">
        <div className="split-left">
          <div className="list-head">
            <span className="strong">
              Flights <span className="muted">({flights.length})</span>
              {loading && <span className="muted"> · loading…</span>}
            </span>
            <span className="sort-ctrl">
              <select
                className="input sm"
                value={sort.field}
                onChange={(e) => setSort((s) => ({ ...s, field: e.target.value }))}
              >
                <option value="date">Date</option>
                <option value="duration">Duration</option>
                <option value="distance">Distance</option>
                <option value="pilot">Pilot</option>
                <option value="name">File</option>
              </select>
              <button
                className="btn sm"
                title="Toggle order"
                onClick={() =>
                  setSort((s) => ({ ...s, order: s.order === "asc" ? "desc" : "asc" }))
                }
              >
                {sort.order === "asc" ? "▲" : "▼"}
              </button>
            </span>
          </div>

          <div className="flight-cards">
            {pageFlights.map((f) => {
              const badge = STACK_BADGE[f.stack] || { label: f.stack || "?", cls: "" };
              return (
                <button
                  key={f.id}
                  className={`flight-card ${f.id === selectedId ? "selected" : ""}`}
                  onClick={() => navigate(`/flights/${f.id}`)}
                >
                  <div className="fc-row1">
                    <span className="fc-date">
                      {fmtDateTime(f.log_start_utc)}
                      {f.start_location && (
                        <span className="fc-loc"> · {f.start_location}</span>
                      )}
                    </span>
                    <span className="fc-right">
                      <span className={`badge ${badge.cls}`}>{badge.label}</span>
                      <StatusPill
                        status={f.parse_status}
                        error={f.parse_error}
                        errorMsgs={f.error_msg_count}
                        warnMsgs={f.warn_msg_count}
                      />
                    </span>
                  </div>
                  <div className="fc-row2">
                    <span className="fc-vehicle">{vehicleLabel(f)}</span>
                    <span className="fc-file" title={f.file_path}>
                      {f.file_name}
                    </span>
                  </div>
                  <div className="fc-row3 muted">
                    {fmtDuration(f.duration_s)} · {fmtDistance(f.distance_m)}
                    {f.pilot ? ` · ${f.pilot}` : ""}
                  </div>
                </button>
              );
            })}
            {!pageFlights.length && !loading && (
              <div className="empty">
                No flights. Enter a folder path above and click <b>Scan</b>.
              </div>
            )}
          </div>

          {totalPages > 1 && (
            <div className="pager">
              <button
                className="btn sm"
                disabled={pageClamped <= 1}
                onClick={() => setPage(pageClamped - 1)}
              >
                ‹
              </button>
              {pageItems(pageClamped, totalPages).map((it, i) =>
                it === "…" ? (
                  <span key={`e${i}`} className="pager-gap">
                    …
                  </span>
                ) : (
                  <button
                    key={it}
                    className={`btn sm ${it === pageClamped ? "primary" : ""}`}
                    onClick={() => setPage(it)}
                  >
                    {it}
                  </button>
                )
              )}
              <button
                className="btn sm"
                disabled={pageClamped >= totalPages}
                onClick={() => setPage(pageClamped + 1)}
              >
                ›
              </button>
            </div>
          )}
        </div>

        <div className="split-right">
          <FlightDetail id={selectedId} onUpdated={load} />
        </div>
      </div>
    </div>
  );
}
