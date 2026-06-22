// Thin REST client for the logbook backend.
const BASE = "/api";

async function req(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  status: () => req("GET", "/status"),
  scan: (path, recursive) => req("POST", "/scan", { path, recursive }),
  uploadLogs: async (files) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    const res = await fetch(BASE + "/upload", { method: "POST", body: fd });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail || detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res.json();
  },
  listFlights: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v != null)
    ).toString();
    return req("GET", "/flights" + (qs ? `?${qs}` : ""));
  },
  getFlight: (id) => req("GET", `/flights/${id}`),
  patchFlight: (id, patch) => req("PATCH", `/flights/${id}`, patch),
  deleteFlight: (id, deleteFile = false) =>
    req("DELETE", `/flights/${id}?delete_file=${deleteFile ? "true" : "false"}`),
  bulkAssign: (ids, fields) => req("POST", "/flights/bulk", { ids, ...fields }),
  listVehicles: () => req("GET", "/vehicles"),
  createVehicle: (body) => req("POST", "/vehicles", body),
  patchVehicle: (uid, patch) =>
    req("PATCH", `/vehicles/${encodeURIComponent(uid)}`, patch),
  deleteVehicle: (uid) => req("DELETE", `/vehicles/${encodeURIComponent(uid)}`),
  listPilots: () => req("GET", "/pilots"),
  createPilot: (name) => req("POST", "/pilots", { name }),
  deletePilot: (name) => req("DELETE", `/pilots/${encodeURIComponent(name)}`),
};
