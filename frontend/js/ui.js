/* Design-system components: icons, movement badges, toast, modal/sheet, confirm,
   quantity input, empty/loading, data table, simple form helpers */
const ICONS = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  count: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  checkc: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.5 3-6 6.5-6s6.5 2.5 6.5 6"/><path d="M16 4.5a3.5 3.5 0 010 7M18 14.5c2 .8 3.5 2.7 3.5 5.5"/>',
  scan: '<path d="M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3"/><path d="M7 12h10"/>',
  qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h3M20 17v4"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
  back: '<path d="M15 5l-7 7 7 7"/>', right: '<path d="M9 5l7 7-7 7"/>', down: '<path d="M6 9l6 6 6-6"/>', up: '<path d="M18 15l-6-6-6 6"/>',
  arrowDown: '<path d="M12 5v14M6 13l6 6 6-6"/>', arrowUp: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
  refresh: '<path d="M20 11a8 8 0 10-2.3 6M20 4v7h-7"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v4h16v-4"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  logout: '<path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9"/>',
  dash: '<rect x="3" y="3" width="8" height="10" rx="1.5"/><rect x="13" y="3" width="8" height="6" rx="1.5"/><rect x="13" y="11" width="8" height="10" rx="1.5"/><rect x="3" y="15" width="8" height="6" rx="1.5"/>',
  box: '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>',
  wh: '<path d="M3 21V9l9-5 9 5v12"/><path d="M7 21v-7h10v7M7 17h10"/>',
  pin: '<path d="M12 21s7-6.2 7-11.5A7 7 0 005 9.5C5 14.800 12 21 12 21z"/><circle cx="12" cy="9.500" r="2.500"/>',
  tag: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.500" cy="8.500" r="1.200"/>',
  file: '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5M9 13h7M9 17h7"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.500 8-8 9-4.500-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  cog: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.900 4.900l2.100 2.100M17 17l2.100 2.100M4.900 19.100L7 17M17 7l2.100-2.100"/>',
  alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.01"/>',
  wifioff: '<path d="M3 3l18 18M8.500 8.500A12 12 0 003 12M12.500 5.100A15 15 0 0121 12M7 16a7 7 0 015-2M10.500 19.500a2 2 0 013 0"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  repeat: '<path d="M4 12V9a3 3 0 013-3h11M15 3l3 3-3 3M20 12v3a3 3 0 01-3 3H6M9 21l-3-3 3-3"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  cmp: '<path d="M8 3L4 7l4 4M4 7h16M16 21l4-4-4-4M20 17H4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.500v.01"/>',
  flash: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  circle: '<circle cx="12" cy="12" r="8"/>',
  print: '<path d="M7 8V3h10v5"/><rect x="4" y="8" width="16" height="8" rx="1.5"/><path d="M7 16h10v5H7z"/>',
  inbox: '<path d="M3 12l3-7h12l3 7v6a1 1 0 01-1 1H4a1 1 0 01-1-1z"/><path d="M3 12h5l1 2h6l1-2h5"/>',
  outbox: '<path d="M3 13l2.5-7h13L21 13v5a1 1 0 01-1 1H4a1 1 0 01-1-1z"/><path d="M12 3v8M9 8l3-3 3 3"/>',
  bell: '<path d="M6 9a6 6 0 0112 0c0 4 1.5 5 2 6H4c.5-1 2-2 2-6z"/><path d="M10 19a2 2 0 004 0"/>',
  send: '<path d="M4 12l16-8-6 16-3-7z"/>',
};
const icon = (n, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;

/* ---------- movement type badges (text + icon, never colour alone) ---------- */
const MOVEMENT_TYPES = {
  INBOUND: ["Masuk", "success", "arrowDown"],
  OUTBOUND: ["Keluar", "accent", "arrowUp"],
  TRANSFER: ["Transfer", "info", "cmp"],
  ADJUSTMENT: ["Penyesuaian", "warning", "edit"],
};
const REF_TYPES = ["PO", "SURAT_JALAN", "DO", "LAINNYA"];
const REF_LABELS = { PO: "PO", SURAT_JALAN: "Surat Jalan", DO: "Delivery Order", LAINNYA: "Lainnya" };
const moveBadge = (t, lg = false) => {
  const [txt, c, i] = MOVEMENT_TYPES[t] || [t, "", "circle"];
  return `<span class="badge ${c} ${lg ? "lg" : ""}">${icon(i)}${esc(txt)}</span>`;
};
const refLabel = (r) => (r ? (REF_LABELS[r] || r) : "—");
const voidBadge = (m) => (m && m.voided ? `<span class="badge error">${icon("x")}Dibatalkan</span>` : "");

/* ---------- stock opname statuses ---------- */
const STO_STATUS = {
  DRAFT: ["Draf", ""], OPEN: ["Terbuka", "info"], COUNTING: ["Menghitung", "accent"],
  CHECKING: ["Pengecekan", "warning"], RECONCILIATION: ["Rekonsiliasi", "warning"],
  COMPLETED: ["Selesai", "success"], CANCELLED: ["Dibatalkan", "error"],
};
const STO_LOC_STATUS = {
  NOT_STARTED: ["Belum", ""], IN_PROGRESS: ["Proses", "accent"], WAITING_CHECK: ["Tunggu Cek", "warning"],
  ACCEPTED: ["Diterima", "success"], RECOUNT: ["Hitung Ulang", "error"], COMPLETED: ["Selesai", "success"],
};
const RECON_STATUS = {
  MATCH: ["Cocok", "success"], VARIANCE: ["Selisih", "warning"], UNEXPECTED: ["Tak Terduga", "error"],
  MISSING: ["Kurang", "error"],
};
const stoBadge = (s, map = STO_STATUS) => {
  const [txt, c] = map[s] || [s, ""];
  return `<span class="badge ${c}">${esc(txt)}</span>`;
};

/* ---------- messages ---------- */
const MESSAGE_LEVELS = { INFO: ["Info", "info"], WARN: ["Penting", "warning"], URGENT: ["Urgent", "error"] };
const MESSAGE_TARGETS = { MH: "Material Handling", CHECKER: "Checker", SUPERVISOR: "Supervisor", ALL: "Semua" };
const msgLevel = (l) => MESSAGE_LEVELS[l] || MESSAGE_LEVELS.INFO;
const msgBadge = (l) => {
  const [txt, c] = msgLevel(l);
  return `<span class="badge ${c}">${esc(txt)}</span>`;
};

/* ---------- toast ---------- */
function toast(msg, type = "success", ms = 2200) {
  let host = $("#toasts");
  if (!host) { host = document.createElement("div"); host.id = "toasts"; host.setAttribute("role", "status"); host.setAttribute("aria-live", "polite"); document.body.appendChild(host); }
  const t = document.createElement("div");
  t.className = "toast " + type;
  t.innerHTML = icon(type === "error" ? "alert" : type === "warn" ? "wifioff" : "checkc") + `<span>${esc(msg)}</span>`;
  host.appendChild(t);
  setTimeout(() => t.remove(), type === "error" ? Math.max(ms, 4000) : ms);
}
const vibrate = (p = 30) => { try { navigator.vibrate && navigator.vibrate(p); } catch {} };

/* ---------- modal / bottom sheet ---------- */
function openSheet(html, { center = false, wide = false, onClose } = {}) {
  const ov = document.createElement("div");
  ov.className = "overlay" + (center ? " center" : "") + (wide ? " wide" : "");
  ov.innerHTML = `<div class="sheet" role="dialog" aria-modal="true">${center ? "" : '<div class="grab"></div>'}${html}</div>`;
  document.body.appendChild(ov);
  const close = (v) => { ov.remove(); document.removeEventListener("keydown", esc_); onClose && onClose(v); };
  const esc_ = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", esc_);
  ov.addEventListener("mousedown", (e) => { if (e.target === ov) close(); });
  $$("[data-close]", ov).forEach((b) => b.addEventListener("click", () => close(b.dataset.close === "true" ? true : undefined)));
  return { el: ov, sheet: $(".sheet", ov), close };
}
function confirmDialog({ title, body = "", confirmText = "Ya", cancelText = "Kembali", danger = false }) {
  return new Promise((res) => {
    let done = false;
    const m = openSheet(`<h2>${esc(title)}</h2><div class="mt8">${body}</div>
      <div class="actions"><button class="btn lg" data-close="false">${esc(cancelText)}</button>
      <button class="btn lg ${danger ? "danger" : "primary"}" id="cf-ok">${esc(confirmText)}</button></div>`,
      { center: true, onClose: () => { if (!done) res(false); } });
    $("#cf-ok", m.el).onclick = () => { done = true; m.close(); res(true); };
  });
}
function promptDialog({ title, label, placeholder = "", value = "", confirmText = "Simpan", multiline = false }) {
  return new Promise((res) => {
    let done = false;
    const field = multiline
      ? `<textarea class="input" id="pd-in" rows="3" placeholder="${esc(placeholder)}">${esc(value)}</textarea>`
      : `<input class="input" id="pd-in" placeholder="${esc(placeholder)}" value="${esc(value)}" autofocus>`;
    const m = openSheet(`<h2>${esc(title)}</h2><div class="field mt8"><label class="lbl">${esc(label)}</label>${field}</div>
      <div class="actions"><button class="btn lg" data-close="false">Batal</button>
      <button class="btn lg primary" id="pd-ok">${esc(confirmText)}</button></div>`,
      { center: true, onClose: () => { if (!done) res(null); } });
    const ok = () => { done = true; const v = $("#pd-in", m.el).value; m.close(); res(v); };
    $("#pd-ok", m.el).onclick = ok;
    $("#pd-in", m.el).addEventListener("keydown", (e) => { if (e.key === "Enter" && !multiline) ok(); });
  });
}

/* ---------- button busy helper ---------- */
async function busy(btn, fn) {
  if (!btn || btn.disabled) return;
  const html = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
  try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = html; }
}

/* ---------- empty / loading ---------- */
const emptyState = (ico, title, text = "", btn = "") => `<div class="empty"><div class="ico">${icon(ico)}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${btn}</div>`;
const skeleton = (n = 3, h = 72) => Array.from({ length: n }, () => `<div class="skel card" style="height:${h}px"></div>`).join("");

/* ---------- QUANTITY INPUT component (one-handed keypad) ----------
   openQty({item, locator, available, title, unit, initial, allowZero}) -> Promise<number|null> */
function openQty({ item, locator, available = null, title = "Jumlah", initial = "", unit = "", allowZero = false }) {
  return new Promise((resolve) => {
    let str = String(initial !== undefined && initial !== null ? initial : ""), fresh = true, saved = false;
    const uom = unit || (item && item.uom) || "";
    const m = openSheet(`
      <div class="qty">
        <div class="item-found">${icon("box")}<div class="grow">
          ${title ? `<div style="font-size:12px;font-weight:700;color:var(--primary);text-transform:uppercase;margin-bottom:2px;">${esc(title)}</div>` : ""}
          <div class="code">${esc(item ? item.code : "")}</div>
          <div>${esc(item ? item.name : "")}</div>
          <div class="meta">UOM: ${esc(uom)}${locator ? " · Locator: " + esc(locator) : ""}</div></div>
          <button class="btn ghost icon" data-close="false" aria-label="Tutup">${icon("x")}</button></div>
        ${available !== null && available !== undefined ? `
          <div class="prev-note">Saldo tersedia di locator ini: <b>${fmt(available)} ${esc(uom)}</b></div>` : ""}
        <div class="qty-display"><div class="val num zero" id="q-val" style="color:#000000;">0</div><div class="unit">${esc(uom)}</div>
          <button class="btn sm clr" id="q-clr" type="button">Clear</button></div>
        <div class="qty-step">
          <button class="btn" data-step="-10" type="button">−10</button><button class="btn" data-step="-1" type="button">−1</button>
          <button class="btn" data-step="1" type="button">+1</button><button class="btn" data-step="10" type="button">+10</button></div>
        <div class="keypad">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => `<button type="button" data-k="${n}">${n}</button>`).join("")}
          <button type="button" class="fn" data-k=".">,</button><button type="button" data-k="0">0</button>
          <button type="button" class="fn" data-k="back" aria-label="Hapus">⌫</button></div>
        <div class="actions"><button class="btn primary lg" id="q-save" type="button" disabled>SUBMIT</button></div>
      </div>`, { onClose: () => { document.removeEventListener("keydown", kd); if (!saved) resolve(null); } });
    const val = $("#q-val", m.el), save = $("#q-save", m.el);
    const num_ = () => parseFloat(str || "0") || 0;
    const canSave = () => allowZero ? (str !== "" && !isNaN(parseFloat(str)) && num_() >= 0) : num_() > 0;
    const render = () => {
      val.textContent = str ? str.replace(".", ",") : "0";
      val.classList.toggle("zero", !str || (str === "0" && !allowZero));
      save.disabled = !canSave();
    };
    const press = (k) => {
      if (k === "back") str = str.slice(0, -1);
      else if (k === ".") { if (!str.includes(".")) str = (str || "0") + "."; }
      else { str = fresh && !str.includes(".") ? k : str + k; if (str.replace(".", "").length > 9) str = str.slice(0, -1); if (/^0\d/.test(str)) str = str.slice(1); }
      fresh = false; render();
    };
    $$("[data-k]", m.el).forEach((b) => b.addEventListener("click", () => { vibrate(8); press(b.dataset.k); }));
    $$("[data-step]", m.el).forEach((b) => b.addEventListener("click", () => {
      vibrate(8); const v = Math.max(0, Math.round((num_() + +b.dataset.step) * 1000) / 1000); str = String(v); fresh = false; render();
    }));
    $("#q-clr", m.el).onclick = () => { str = ""; fresh = true; render(); };
    const doSave = () => { if (canSave() && !saved) { saved = true; m.close(); resolve(num_()); } };
    save.onclick = doSave;
    const kd = (e) => {
      if (/^[0-9]$/.test(e.key)) press(e.key); else if (e.key === "." || e.key === ",") press(".");
      else if (e.key === "Backspace") press("back"); else if (e.key === "Enter") doSave();
      else if (e.key === "+") $('[data-step="1"]', m.el).click(); else if (e.key === "-") $('[data-step="-1"]', m.el).click();
    };
    document.addEventListener("keydown", kd);
    render();
  });
}

/* ---------- DESKTOP DATA TABLE: search, sort, pagination, export ---------- */
function DataTable({ columns, load, size = 20, search = true, searchPlaceholder = "Cari…", filters = "", actions = "", onRow, exportFn, empty }) {
  const el = document.createElement("div");
  el.innerHTML = `<div class="toolbar">${search ? `<div class="search">${icon("search")}<input class="input" placeholder="${esc(searchPlaceholder)}" aria-label="Cari"></div>` : ""}
    ${filters}<div class="spacer"></div>${exportFn ? `<button class="btn sm" data-exp>${icon("download")}Export</button>` : ""}${actions}</div>
    <div class="table-wrap mt16"><div class="table-scroll"><table class="dt"><thead></thead><tbody></tbody></table></div><div class="pager"></div></div>`;
  const st = { page: 1, q: "", sort: null, dir: 1, rows: [], total: 0 };
  const thead = $("thead", el), tbody = $("tbody", el), pager = $(".pager", el);
  const renderHead = () => {
    thead.innerHTML = "<tr>" + columns.map((c) => `<th class="${c.align === "r" ? "r" : ""} ${c.sortable !== false && c.key ? "sortable" : ""}" data-key="${c.key || ""}">${esc(c.label)}${st.sort === c.key ? (st.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("") + "</tr>";
  };
  const renderRows = () => {
    let rows = st.rows.slice();
    if (st.sort) rows.sort((a, b) => { const x = a[st.sort], y = b[st.sort]; return (typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""), undefined, { numeric: true })) * st.dir; });
    tbody.innerHTML = rows.length ? rows.map((r) => `<tr class="${onRow ? "clickable" : ""}" data-i="${st.rows.indexOf(r)}">${columns.map((c) => `<td class="${c.align === "r" ? "r" : ""} ${c.cls || ""}">${c.render ? c.render(r) : esc(r[c.key] ?? "—")}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${columns.length}">${empty || emptyState("search", "Tidak ada data", "Coba ubah kata kunci atau filter.")}</td></tr>`;
  };
  const renderPager = () => {
    const pages = Math.max(1, Math.ceil(st.total / size));
    pager.innerHTML = `<span>${fmt(st.total)} data</span><div class="btns"><button class="btn sm icon" data-p="-1" ${st.page <= 1 ? "disabled" : ""} aria-label="Sebelumnya">${icon("back")}</button><span>Hal ${st.page} / ${pages}</span><button class="btn sm icon" data-p="1" ${st.page >= pages ? "disabled" : ""} aria-label="Berikutnya">${icon("right")}</button></div>`;
  };
  const reload = async (resetPage = false) => {
    if (resetPage) st.page = 1;
    tbody.innerHTML = `<tr><td colspan="${columns.length}">${skeleton(4, 36)}</td></tr>`;
    try {
      const f = getFilters();
      const r = await load({ page: st.page, size, q: st.q, ...f });
      st.rows = r.items; st.total = r.total;
    } catch (e) { st.rows = []; st.total = 0; tbody.innerHTML = `<tr><td colspan="${columns.length}"><div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div></td></tr>`; renderPager(); return; }
    renderRows(); renderPager();
  };
  const getFilters = () => { const o = {}; $$("[data-filter]", el).forEach((f) => { o[f.dataset.filter] = f.value; }); return o; };
  renderHead();
  el.addEventListener("click", (e) => {
    const th = e.target.closest("th.sortable"); if (th) { const k = th.dataset.key; st.dir = st.sort === k ? -st.dir : 1; st.sort = k; renderHead(); renderRows(); return; }
    const p = e.target.closest("[data-p]"); if (p) { st.page += +p.dataset.p; reload(); return; }
    if (e.target.closest("[data-exp]")) { exportFn(); return; }
    const tr = e.target.closest("tr[data-i]"); if (tr && onRow && !e.target.closest("button,a,input,select")) onRow(st.rows[+tr.dataset.i]);
  });
  const si = $(".search input", el); if (si) si.addEventListener("input", debounce(() => { st.q = si.value.trim(); reload(true); }, 300));
  el.addEventListener("change", (e) => { if (e.target.matches("[data-filter]")) reload(true); });
  return { el, reload, get state() { return st; } };
}

/* ---------- simple form helper ---------- */
const formData = (root) => {
  const o = {};
  $$("[name]", root).forEach((f) => {
    if (f.type === "checkbox") o[f.name] = f.checked;
    else if (f.type === "radio") { if (f.checked) o[f.name] = f.value; }
    else o[f.name] = f.value;
  });
  return o;
};
const options = (list, sel, valKey = "id", labelFn = (x) => x.name, blank) =>
  (blank !== undefined ? `<option value="">${esc(blank)}</option>` : "") + list.map((x) => `<option value="${esc(x[valKey])}" ${String(x[valKey]) === String(sel) ? "selected" : ""}>${esc(labelFn(x))}</option>`).join("");
