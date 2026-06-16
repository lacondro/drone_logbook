// Display formatters. Storage is UTC; display is local (Asia/Seoul for the demo).
export function fmtDuration(s) {
  if (s == null) return "—";
  s = Math.round(s);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m ${sec}s`;
  }
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

// "2026.06.12. 14:46" — year.month.day. 24h time, in local time.
export function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())}. ${p(
    d.getHours()
  )}:${p(d.getMinutes())}`;
}

export function fmtDistance(m) {
  if (m == null) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${m.toFixed(0)} m`;
}

export function fmtNum(v, unit = "", digits = 1) {
  if (v == null) return "—";
  return `${v.toFixed(digits)}${unit ? " " + unit : ""}`;
}

export function shortUid(uid) {
  if (!uid) return "—";
  if (uid.length <= 16) return uid;
  return uid.slice(0, 8) + "…" + uid.slice(-6);
}

// Best display label for the vehicle a flight belongs to.
export function vehicleLabel(f) {
  if (f.registration_number) return f.registration_number;
  if (f.nickname) return f.nickname;
  return shortUid(f.vehicle_uid);
}
