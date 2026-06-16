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
  listVehicles: () => req("GET", "/vehicles"),
  patchVehicle: (uid, patch) =>
    req("PATCH", `/vehicles/${encodeURIComponent(uid)}`, patch),
  listPilots: () => req("GET", "/pilots"),
};
