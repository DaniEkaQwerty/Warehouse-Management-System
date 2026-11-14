/* API client + auth session + small helpers */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => (n === null || n === undefined || n === "" ? "—" : Number(n).toLocaleString("id-ID", { maximumFractionDigits: 3 }));
const uuid = () => (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "") : Date.now().toString(16) + Math.random().toString(16).slice(2, 14) + Math.random().toString(16).slice(2, 10));
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const fmtDate = (s) => (s ? new Date(s.endsWith("Z") || s.includes("+") ? s : s + "Z").toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "—");

const Session = {
  get token() { return localStorage.getItem("sto_token"); },
  get user() {
    try {
      const u = JSON.parse(localStorage.getItem("sto_user"));
      if (u && Array.isArray(u.roles)) {
        u.roles = u.roles.map(r => String(r).toUpperCase());
      }
      return u;
    } catch { return null; }
  },
  set(token, user) {
    if (user && Array.isArray(user.roles)) {
      user.roles = user.roles.map(r => String(r).toUpperCase());
    }
    localStorage.setItem("sto_token", token);
    localStorage.setItem("sto_user", JSON.stringify(user));
  },
  clear() { localStorage.removeItem("sto_token"); localStorage.removeItem("sto_user"); },
  get deviceId() {
    let d = localStorage.getItem("sto_device");
    if (!d) { d = "dev-" + uuid().slice(0, 12); localStorage.setItem("sto_device", d); }
    return d;
  },
  has(...roles) {
    const u = this.user;
    if (!u || !Array.isArray(u.roles)) return false;
    const req = roles.map(r => String(r).toUpperCase());
    return u.roles.includes("ADMIN") || req.some(r => u.roles.includes(r));
  },
  hasExact(...roles) {
    const u = this.user;
    if (!u || !Array.isArray(u.roles)) return false;
    const req = roles.map(r => String(r).toUpperCase());
    return req.some(r => u.roles.includes(r));
  },
};

class ApiError extends Error {
  constructor(message, status, offline = false) { super(message); this.status = status; this.offline = offline; }
}

async function api(path, { method = "GET", body, form, raw } = {}) {
  const headers = {};
  if (Session.token) headers.Authorization = "Bearer " + Session.token;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch("/api" + path, { method, headers, body: payload });
  } catch {
    Net.setOnline(false);
    throw new ApiError("Tidak ada koneksi ke server.", 0, true);
  }
  Net.setOnline(true);
  if (res.status === 401 && Session.token) { Session.clear(); location.hash = "#/login"; location.reload(); throw new ApiError("Sesi berakhir.", 401); }
  if (raw) {
    if (!res.ok) throw new ApiError(await errMsg(res), res.status);
    return res;
  }
  if (!res.ok) throw new ApiError(await errMsg(res), res.status);
  return res.status === 204 ? null : res.json();
}
async function errMsg(res) {
  try { const j = await res.json(); return typeof j.detail === "string" ? j.detail : "Data gagal diproses. Silakan coba lagi."; }
  catch { return "Data gagal diproses. Silakan coba lagi."; }
}
async function download(path, filename) {
  try {
    toast(`Mengunduh file ${filename || ""}...`, "info", 2200);
    const res = await api(path, { raw: true });
    const blob = await res.blob();
    let finalName = filename || "download";
    const disp = res.headers.get("Content-Disposition");
    if (disp && !filename) {
      const m = disp.match(/filename="?([^";]+)"?/i);
      if (m && m[1]) finalName = m[1];
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.setAttribute("download", finalName);
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      a.remove();
      URL.revokeObjectURL(url);
    }, 2000);
  } catch (err) {
    console.error("Download error:", err);
    toast(err.message || "Gagal mengunduh file", "error", 4000);
  }
}
const qs = (o) => { const p = new URLSearchParams(); Object.entries(o).forEach(([k, v]) => { if (v !== "" && v !== null && v !== undefined) p.set(k, v); }); const s = p.toString(); return s ? "?" + s : ""; };

/* ---- network state (browser signal + real request failures) ---- */
const Net = {
  online: navigator.onLine, listeners: [],
  setOnline(v) { if (v !== this.online) { this.online = v; this.listeners.forEach((f) => f(v)); } },
  on(f) { this.listeners.push(f); },
};
window.addEventListener("online", () => Net.setOnline(true));
window.addEventListener("offline", () => Net.setOnline(false));
