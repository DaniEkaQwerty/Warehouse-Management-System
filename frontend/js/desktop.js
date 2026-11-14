/* ===========================================================
   DESKTOP CONSOLE (Supervisor / Checker / Admin)
   - Dashboard, Movement history, Stock, Corrections, Sync problems
   - Master data (warehouses, locators, items, users), Excel import,
     Reports, Audit log
   =========================================================== */

const Desktop = {
  _whs: null,
  async warehouses(force = false) {
    if (!this._whs || force) { try { this._whs = (await api("/warehouses?size=200")).items || []; } catch { this._whs = this._whs || []; } }
    return this._whs;
  },
  whSelect(id, sel, { blank = null, extra = "" } = {}) {
    const list = this._whs || [];
    return `<select class="input" id="${id}" data-filter="${id.replace(/^f-/, "")}" ${extra}>${options(list, sel, "id", (w) => `${w.code} — ${w.name}`, blank)}</select>`;
  },
  typeSelect(id, sel) {
    return `<select class="input" id="${id}" data-filter="${id.replace(/^f-/, "")}"><option value="">Semua jenis</option>${Object.entries(MOVEMENT_TYPES).map(([k, v]) => `<option value="${k}" ${sel === k ? "selected" : ""}>${esc(v[0])}</option>`).join("")}</select>`;
  },

  renderShell(root, nav) {
    const canWide = Session.hasExact("SUPERVISOR", "CHECKER", "ADMIN");
    const isAdmin = Session.hasExact("ADMIN");
    const items = [
      { id: "dashboard", label: "Dashboard", hash: "#/d/dashboard", icon: "dash", show: canWide },
      { id: "movements", label: "Riwayat Stok", hash: "#/d/movements", icon: "repeat", show: canWide },
      { id: "stock", label: "Saldo Stok", hash: "#/d/stock", icon: "box", show: canWide },
      { id: "sto", label: "Stock Opname", hash: "#/d/sto", icon: "checkc", show: canWide },
      { id: "corrections", label: "Koreksi", hash: "#/d/corrections", icon: "edit", show: canWide },
      { id: "problems", label: "Transaksi Bermasalah", hash: "#/d/problems", icon: "alert", show: canWide },
      { id: "warehouses", label: "Gudang", hash: "#/d/warehouses", icon: "wh", show: isAdmin },
      { id: "locators", label: "Locator", hash: "#/d/locators", icon: "pin", show: isAdmin },
      { id: "items", label: "Master Item", hash: "#/d/items", icon: "tag", show: isAdmin },
      { id: "imports", label: "Import Excel", hash: "#/d/imports", icon: "upload", show: isAdmin },
      { id: "reports", label: "Laporan", hash: "#/d/reports", icon: "file", show: canWide },
      { id: "users", label: "Pengguna", hash: "#/d/users", icon: "users", show: isAdmin },
      { id: "audit", label: "Audit Log", hash: "#/d/audit", icon: "shield", show: isAdmin },
    ];
    const u = Session.user;
    const appName = window.APP_NAME || "WMS";
    root.innerHTML = `
      <div class="d-app" id="d-app-shell">
        <aside class="d-side">
          <div class="logo"><div class="logo-mark">${icon("box")}</div>
            <div><div style="font-weight:800;font-size:17px;">${esc(appName)}</div>
            <div class="muted" style="font-size:12px;color:#94a3b8;">${esc(window.APP_SUBTITLE || "Warehouse Management")}</div></div></div>
          <nav class="d-nav mt16" aria-label="Menu Utama">
            ${items.filter((n) => n.show).map((n) => `<a href="${n.hash}" class="${nav === n.id ? "active" : ""}">${icon(n.icon)}<span>${esc(n.label)}</span></a>`).join("")}
          </nav>
          <div class="d-user">
            <div class="row between"><div><b>${esc(u.full_name)}</b><span class="muted" style="font-size:12px;color:#94a3b8;">@${esc(u.username)} · ${esc((u.roles || [])[0] || "")}</span></div>
              <button class="btn icon ghost sm" id="d-logout" title="Logout" style="color:#cbd5e1;">${icon("logout")}</button></div>
            <a href="#/m" class="btn sm block mt8" style="background:rgba(255,255,255,.08);color:#fff;border-color:transparent;">${icon("scan", "i sm")} Buka Mobile View</a>
          </div>
        </aside>
        <div class="scrim" id="d-scrim"></div>
        <div class="d-main">
          <header class="d-top">
            <button class="btn icon ghost menu-btn" id="d-menu">${icon("menu")}</button>
            <div class="grow"><h2 style="font-size:18px;">${esc(appName)}</h2></div>
            <div id="d-net">${Net.online ? '<span class="net">ONLINE</span>' : '<span class="net off">OFFLINE</span>'}</div>
          </header>
          <main class="d-content" id="d-content"></main>
        </div>
      </div>`;
    const shell = $("#d-app-shell", root);
    $("#d-menu", root).onclick = () => shell.classList.toggle("open");
    $("#d-scrim", root).onclick = () => shell.classList.remove("open");
    $("#d-logout", root).onclick = async () => {
      if (await confirmDialog({ title: "Logout?", body: "<p>Keluar dari sistem?</p>", confirmText: "Logout", danger: true })) {
        api("/auth/logout", { method: "POST" }).catch(() => {}); Session.clear(); App.navigate("#/login");
      }
    };
    return $("#d-content", root);
  },

  pageHead(title, sub = "", actions = "") {
    return `<div class="page-head"><div><h1>${esc(title)}</h1>${sub ? `<p>${esc(sub)}</p>` : ""}</div><div class="row gap8">${actions}</div></div>`;
  },

  /* -------------------------------------------------- DASHBOARD */
  async renderDashboard(root) {
    const content = this.renderShell(root, "dashboard");
    content.innerHTML = skeleton(3, 120);
    await this.warehouses(true);
    const whId = localStorage.getItem("wms_dash_wh") || "";
    try {
      const data = await api("/dashboard" + qs({ warehouse_id: whId }));
      const c = data.cards || {};
      const problems = c.problems || 0;
      content.innerHTML = `
        ${this.pageHead("Dashboard Operasional", "Ringkasan aktivitas gudang", `<button class="btn sm" id="dash-refresh">${icon("refresh")} Refresh</button>`)}
        <div class="toolbar">
          <div class="field" style="margin:0;min-width:220px;">${this.whSelect("f-warehouse_id", whId, { blank: "Semua gudang" })}</div>
          <div class="field" style="margin:0;"><input class="input" type="date" id="dash-from" value="${esc(data.filters.date_from)}"></div>
          <div class="field" style="margin:0;"><input class="input" type="date" id="dash-to" value="${esc(data.filters.date_to)}"></div>
        </div>

        ${problems ? `<div class="banner warn">${icon("alert")}<div class="grow"><b>${problems} transaksi sync ditolak</b><span>Periksa menu Transaksi Bermasalah.</span></div><a href="#/d/problems" class="btn sm">Lihat</a></div>` : ""}

        <div class="kpis">
          <div class="kpi ok"><div class="v num">${fmt(c.inbound_today || 0)}</div><div class="l">Masuk hari ini</div><div class="kpi-sub">Periode: ${fmt(c.inbound_period || 0)}</div></div>
          <div class="kpi"><div class="v num">${fmt(c.outbound_today || 0)}</div><div class="l">Keluar hari ini</div><div class="kpi-sub">Periode: ${fmt(c.outbound_period || 0)}</div></div>
          <div class="kpi"><div class="v num">${fmt(c.transfer_today || 0)}</div><div class="l">Transfer hari ini</div><div class="kpi-sub">Periode: ${fmt(c.transfer_period || 0)}</div></div>
          <div class="kpi"><div class="v num">${fmt(c.movements_period || 0)}</div><div class="l">Total transaksi</div><div class="kpi-sub">${fmt(c.items || 0)} item · ${fmt(c.filled_locators || 0)} lokator terisi</div></div>
        </div>

        <div class="grid-2">
          <div class="card"><h3 style="margin:0 0 12px;">Aktivitas 7 Hari</h3>${this.chart(data.chart || [])}</div>
          <div class="card"><h3 style="margin:0 0 12px;">Top Saldo Stok</h3>
            <div class="table-scroll"><table class="dt"><thead><tr><th>Barang</th><th>Lokator</th><th class="r">Saldo</th></tr></thead><tbody>
              ${(data.stock || []).length ? data.stock.map((s) => `<tr><td><b>${esc(s.code)}</b><br><span class="muted" style="font-size:12px;">${esc(s.name)}</span></td><td>${esc(s.locator_code)}</td><td class="r num">${fmt(s.qty)} ${esc(s.uom)}</td></tr>`).join("") : `<tr><td colspan="3" class="muted">Belum ada stok</td></tr>`}
            </tbody></table></div></div>
        </div>

        <div class="card mt16"><h3 style="margin:0 0 12px;">Pergerakan Terakhir</h3>
          <div class="table-scroll"><table class="dt"><thead><tr><th>No</th><th>Jenis</th><th>Barang</th><th class="r">Qty</th><th>Lokator</th><th>Petugas</th><th>Waktu</th></tr></thead><tbody>
            ${(data.recent || []).length ? data.recent.map((m) => `<tr><td>${esc(m.movement_no)}</td><td>${moveBadge(m.movement_type)}</td><td>${esc(m.code)}</td><td class="r num">${fmt(m.qty)}</td><td>${esc(m.from_locator_code || "")}${m.from_locator_code && m.to_locator_code ? " → " : ""}${esc(m.to_locator_code || "")}</td><td>${esc(m.created_by_name || "")}</td><td>${fmtDate(m.created_at)}</td></tr>`).join("") : `<tr><td colspan="7" class="muted">Belum ada pergerakan</td></tr>`}
          </tbody></table></div></div>
      `;
      const reload = () => { localStorage.setItem("wms_dash_wh", $("#f-warehouse_id", content).value); this.renderDashboard(root); };
      $("#f-warehouse_id", content).onchange = reload;
      $("#dash-from", content).onchange = reload;
      $("#dash-to", content).onchange = reload;
      $("#dash-refresh", content).onclick = () => this.renderDashboard(root);
    } catch (e) {
      content.innerHTML = this.pageHead("Dashboard") + `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`;
    }
  },
  chart(rows) {
    if (!rows.length) return `<div class="muted center p20">Belum ada data</div>`;
    const max = Math.max(1, ...rows.flatMap((r) => [r.inbound, r.outbound, r.transfer]));
    return `<div class="bars">${rows.map((r) => `<div class="bar-row">
      <div class="top"><span>${esc(r.date.slice(5))}</span><span class="num">${fmt(r.inbound)} / ${fmt(r.outbound)} / ${fmt(r.transfer)}</span></div>
      <div class="progress sm"><i style="width:${Math.round(r.inbound * 100 / max)}%;background:var(--success)"></i></div>
      <div class="progress sm" style="margin-top:2px;"><i style="width:${Math.round(r.outbound * 100 / max)}%;background:var(--accent)"></i></div>
      <div class="progress sm" style="margin-top:2px;"><i style="width:${Math.round(r.transfer * 100 / max)}%;background:var(--info,#2563eb)"></i></div>
    </div>`).join("")}<div class="row gap12 muted" style="font-size:12px;margin-top:8px;"><span>● Masuk</span><span>● Keluar</span><span>● Transfer</span></div></div>`;
  },

  /* -------------------------------------------------- MOVEMENTS */
  async renderMovements(root) {
    const content = this.renderShell(root, "movements");
    await this.warehouses();
    content.innerHTML = this.pageHead("Riwayat Pergerakan Stok", "Semua transaksi masuk, keluar, transfer, penyesuaian");
    const filters = `<div class="field" style="margin:0;min-width:200px;">${this.whSelect("f-warehouse_id", "", { blank: "Semua gudang" })}</div>
      <div class="field" style="margin:0;">${this.typeSelect("f-movement_type", "")}</div>
      <div class="field" style="margin:0;"><input class="input" type="date" id="f-date_from" data-filter="date_from"></div>
      <div class="field" style="margin:0;"><input class="input" type="date" id="f-date_to" data-filter="date_to"></div>`;
    const dt = DataTable({
      columns: [
        { key: "movement_no", label: "No" },
        { label: "Jenis", render: (m) => moveBadge(m.movement_type) },
        { label: "Barang", render: (m) => `<b>${esc(m.code)}</b><br><span class="muted" style="font-size:12px;">${esc(m.name || "")}</span>` },
        { label: "Qty", align: "r", render: (m) => `<span class="num">${fmt(m.qty)} ${esc(m.uom || "")}</span>` },
        { label: "Lokator", render: (m) => `${esc(m.from_locator_code || "")}${m.from_locator_code && m.to_locator_code ? " → " : ""}${esc(m.to_locator_code || "")}` },
        { label: "Ref", render: (m) => `${esc(refLabel(m.ref_type))}${m.ref_no ? " · " + esc(m.ref_no) : ""}` },
        { label: "Petugas", key: "created_by_name" },
        { label: "Waktu", render: (m) => fmtDate(m.created_at) },
        { label: "Status", render: (m) => m.voided ? voidBadge(m) : `<span class="badge success">${icon("check")}Aktif</span>` },
      ],
      filters, exportFn: () => download("/movements/export" + qs({ ...this.filterVals(content), fmt: "xlsx" }), "riwayat_pergerakan.xlsx"),
      onRow: (m) => this.movementDetail(m, () => dt.reload()),
      load: ({ page, size, q, ...f }) => api("/movements" + qs({ page, size, q, ...f })),
    });
    content.appendChild(dt.el);
    dt.reload();
  },
  filterVals(content) { const o = {}; $$("[data-filter]", content).forEach((f) => { o[f.dataset.filter] = f.value; }); return o; },
  movementDetail(m, onDone) {
    const s = openSheet(`
      <div class="row between"><h3 style="margin:0;">${esc(m.movement_no)}</h3>${moveBadge(m.movement_type, true)}</div>
      ${m.voided ? `<div class="banner error mt8">${icon("x")}<div><b>Dibatalkan</b><span>${esc(m.void_reason || "")}</span></div></div>` : ""}
      <div class="card flat mt8">
        <div class="row between"><span class="muted">Barang</span><b>${esc(m.code)} · ${esc(m.name || "")}</b></div>
        <div class="row between mt8"><span class="muted">Jumlah</span><b class="num">${fmt(m.qty)} ${esc(m.uom || "")}</b></div>
        <div class="row between mt8"><span class="muted">Dari</span><b>${esc(m.from_locator_code || "—")}</b></div>
        <div class="row between mt8"><span class="muted">Ke</span><b>${esc(m.to_locator_code || "—")}</b></div>
        <div class="row between mt8"><span class="muted">Gudang</span><b>${esc(m.warehouse_code || "")}</b></div>
        <div class="row between mt8"><span class="muted">Referensi</span><b>${esc(refLabel(m.ref_type))}${m.ref_no ? " · " + esc(m.ref_no) : ""}</b></div>
        <div class="row between mt8"><span class="muted">Petugas</span><b>${esc(m.created_by_name || "—")}</b></div>
        <div class="row between mt8"><span class="muted">Waktu</span><b>${fmtDate(m.created_at)}</b></div>
        ${m.notes ? `<div class="row between mt8"><span class="muted">Catatan</span><b>${esc(m.notes)}</b></div>` : ""}
      </div>
      ${(!m.voided && Session.hasExact("CHECKER", "ADMIN")) ? `<div class="actions"><button class="btn lg" data-close="true">Tutup</button><button class="btn lg danger" id="mv-void">${icon("x")} Batalkan</button></div>` : `<div class="actions"><button class="btn lg" data-close="true">Tutup</button></div>`}`);
    const v = $("#mv-void", s.el);
    if (v) v.onclick = async () => {
      const reason = await promptDialog({ title: "Alasan Pembatalan", label: "Alasan (min 3 huruf)", multiline: true, confirmText: "Batalkan" });
      if (!reason || reason.trim().length < 3) { if (reason !== null) toast("Alasan minimal 3 huruf.", "warn"); return; }
      try { await api(`/movements/${m.id}/void`, { method: "POST", body: { reason } }); toast("Pergerakan dibatalkan."); s.close(); onDone && onDone(); }
      catch (e) { toast(e.message, "error"); }
    };
  },

  /* -------------------------------------------------- STOCK */
  async renderStock(root) {
    const content = this.renderShell(root, "stock");
    await this.warehouses();
    content.innerHTML = this.pageHead("Saldo Stok", "Saldo dihitung dari ledger pergerakan (bukan disimpan)");
    const filters = `<div class="field" style="margin:0;min-width:200px;">${this.whSelect("f-warehouse_id", "", { blank: "Semua gudang" })}</div>`;
    const dt = DataTable({
      columns: [
        { key: "warehouse_code", label: "Gudang" },
        { key: "locator_code", label: "Lokator" },
        { key: "code", label: "Kode" },
        { key: "name", label: "Nama Barang" },
        { key: "uom", label: "Satuan" },
        { key: "qty", label: "Saldo", align: "r", render: (r) => `<span class="num" style="font-weight:700;">${fmt(r.qty)}</span>` },
      ],
      filters, exportFn: () => download("/stock/export" + qs({ ...this.filterVals(content), fmt: "xlsx" }), "saldo_stok.xlsx"),
      load: ({ page, size, q, ...f }) => api("/stock" + qs({ page, size, q, ...f })),
    });
    content.appendChild(dt.el);
    dt.reload();
  },

  /* -------------------------------------------------- CORRECTIONS */
  async renderCorrections(root) {
    const content = this.renderShell(root, "corrections");
    await this.warehouses();
    content.innerHTML = this.pageHead("Koreksi & Pembatalan", "Riwayat pembatalan dan penyesuaian",
      `<button class="btn sm primary" id="corr-new">${icon("edit")} Buat Penyesuaian</button>`);
    const wrap = document.createElement("div"); wrap.className = "card mt16"; wrap.innerHTML = skeleton(3, 40);
    content.appendChild(wrap);
    $("#corr-new", content).onclick = () => this.adjustForm(root);
    const paint = async () => {
      try {
        const r = await api("/reports/corrections" + qs({ fmt: "json", size: 100 }));
        wrap.innerHTML = r.rows.length ? `<div class="table-scroll"><table class="dt"><thead><tr>${r.headers.map((h, i) => `<th class="${i >= 5 && i <= 5 ? "r" : ""}">${esc(h)}</th>`).join("")}</tr></thead><tbody>${r.rows.map((row) => `<tr>${row.map((v, i) => `<td class="${i === 5 ? "r num" : ""}">${esc(v ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : emptyState("checkc", "Belum ada koreksi", "Pembatalan dan penyesuaian akan tampil di sini.");
      } catch (e) { wrap.innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
    };
    paint();
    this._corrPaint = paint;
  },
  async adjustForm(root) {
    await this.warehouses();
    const whs = this._whs || [];
    if (!whs.length) { toast("Belum ada gudang.", "warn"); return; }
    const s = openSheet(`<h3>Buat Penyesuaian Stok</h3>
      <div class="field mt8"><label class="lbl">Gudang</label><select class="input" id="ad-wh">${options(whs, "", "id", (w) => `${w.code} — ${w.name}`)}</select></div>
      <div class="field"><label class="lbl">Cari Barang (kode)</label><div class="search">${icon("search")}<input class="input" id="ad-item" placeholder="Ketik kode / nama barang" autocomplete="off"></div><div id="ad-results" style="max-height:180px;overflow:auto;"></div></div>
      <div class="field"><label class="lbl">Locator (kode)</label><div class="search">${icon("search")}<input class="input" id="ad-loc" placeholder="Ketik kode lokator" autocomplete="off"></div><div id="ad-locs" style="max-height:160px;overflow:auto;"></div></div>
      <div class="row gap8"><div class="field grow"><label class="lbl">Arah</label><select class="input" id="ad-dir"><option value="ADD">Tambah (+)</option><option value="REMOVE">Kurangi (−)</option></select></div>
        <div class="field grow"><label class="lbl">Jumlah</label><input class="input num" id="ad-qty" type="number" min="0" step="0.001"></div></div>
      <div class="field"><label class="lbl">Alasan (wajib)</label><input class="input" id="ad-reason" placeholder="mis. Koreksi opname"></div>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button><button class="btn lg primary" id="ad-ok">Simpan</button></div>`, { wide: true });

    let item = null, loc = null;
    const whEl = $("#ad-wh", s.el);
    const loadWh = async () => {
      const wid = whEl.value;
      try {
        const [items, locs] = await Promise.all([api("/items?size=1&q="), api(`/locators?warehouse_id=${wid}&size=500`)]);
        void items;
        s.el._locs = locs.items || [];
      } catch { s.el._locs = []; }
    };
    whEl.onchange = loadWh; await loadWh();

    $("#ad-item", s.el).addEventListener("input", debounce(async (e) => {
      const q = e.target.value.trim(); const box = $("#ad-results", s.el);
      if (q.length < 2) { box.innerHTML = ""; return; }
      try { const r = await api("/items" + qs({ q, size: 8 })); box.innerHTML = r.items.map((i) => `<button class="btn block sm mt4 ghost" data-i="${i.id}" style="justify-content:space-between;"><span>${esc(i.code)} <span class="muted">${esc(i.name)}</span></span><span class="badge">${esc(i.uom)}</span></button>`).join("") || `<div class="muted" style="font-size:13px;padding:6px;">Tidak ada hasil</div>`;
        $$("[data-i]", box).forEach((b) => b.onclick = () => { item = r.items.find((x) => x.id === +b.dataset.i); box.innerHTML = `<div class="badge success">${esc(item.code)} · ${esc(item.uom)}</div>`; }); } catch { }
    }, 250));
    $("#ad-loc", s.el).addEventListener("input", (e) => {
      const q = norm(e.target.value); const box = $("#ad-locs", s.el);
      const rows = (s.el._locs || []).filter((l) => !q || norm(l.code).includes(q)).slice(0, 20);
      box.innerHTML = rows.map((l) => `<button class="btn block sm mt4 ghost" data-l="${l.id}">${esc(l.code)}</button>`).join("") || `<div class="muted" style="font-size:13px;padding:6px;">Tidak ada lokator</div>`;
      $$("[data-l]", box).forEach((b) => b.onclick = () => { loc = rows.find((x) => x.id === +b.dataset.l); box.innerHTML = `<div class="badge success">${esc(loc.code)}</div>`; });
    });
    $("#ad-ok", s.el).onclick = (e) => busy(e.currentTarget, async () => {
      if (!item || !loc) { toast("Pilih barang dan lokator.", "warn"); return; }
      const qty = parseFloat($("#ad-qty", s.el).value); const reason = $("#ad-reason", s.el).value.trim();
      if (!(qty > 0)) { toast("Jumlah harus lebih dari 0.", "warn"); return; }
      if (reason.length < 3) { toast("Alasan minimal 3 huruf.", "warn"); return; }
      try { await api("/movements/adjust", { method: "POST", body: { warehouse_id: +whEl.value, item_id: item.id, locator_id: loc.id, qty, direction: $("#ad-dir", s.el).value, reason } }); toast("Penyesuaian tersimpan."); s.close(); this._corrPaint && this._corrPaint(); }
      catch (err) { toast(err.message, "error"); }
    });
  },

  /* -------------------------------------------------- SYNC PROBLEMS */
  async renderProblems(root) {
    const content = this.renderShell(root, "problems");
    content.innerHTML = this.pageHead("Transaksi Bermasalah", "Transaksi offline yang ditolak server saat sinkronisasi");
    const dt = DataTable({
      columns: [
        { key: "txn_type", label: "Jenis", render: (t) => moveBadge(t.txn_type) },
        { key: "txn_id", label: "Txn ID" },
        { key: "user", label: "Petugas" },
        { key: "device_id", label: "Perangkat" },
        { label: "Alasan", render: (t) => `<span style="color:var(--error)">${esc(t.message || "")}</span>` },
        { key: "processed_at", label: "Waktu", render: (t) => fmtDate(t.processed_at) },
      ],
      search: false,
      load: ({ page, size }) => api("/sync-transactions" + qs({ result: "REJECTED", page, size })),
      empty: emptyState("checkc", "Tidak ada masalah", "Semua transaksi tersinkron dengan baik."),
    });
    content.appendChild(dt.el);
    dt.reload();
  },

  /* -------------------------------------------------- STOCK OPNAME */
  async renderSto(root) {
    const content = this.renderShell(root, "sto");
    const isManager = Session.hasExact("SUPERVISOR", "ADMIN");
    content.innerHTML = this.pageHead("Stock Opname", "Hitung fisik dibanding saldo ledger (sistem)",
      isManager ? `<button class="btn sm primary" id="sto-new">${icon("plus")} STO Baru</button>` : "");
    const filters = `<div class="field" style="margin:0;min-width:180px;"><select class="input" id="f-status" data-filter="status">
      <option value="">Semua status</option>${Object.entries(STO_STATUS).map(([k, v]) => `<option value="${k}">${esc(v[0])}</option>`).join("")}</select></div>`;
    const dt = DataTable({
      columns: [
        { key: "sto_number", label: "No. STO" },
        { key: "warehouse_code", label: "Gudang" },
        { key: "sto_date", label: "Tanggal", render: (r) => fmtDate(r.sto_date) },
        { label: "Status", render: (r) => stoBadge(r.status) },
        { label: "Progres", render: (r) => `<div class="row gap8 items-center"><div class="progress sm" style="width:80px;"><i style="width:${r.progress.percent}%"></i></div><span class="num">${r.progress.percent}%</span></div>` },
        { label: "Selesai", render: (r) => `<span class="num">${r.progress.completed}/${r.progress.total}</span>` },
        { label: "Selisih", render: (r) => r.progress.variance ? `<span class="badge warning">${r.progress.variance}</span>` : `<span class="badge success">0</span>` },
      ],
      filters, searchPlaceholder: "Cari no. STO…",
      load: ({ page, size, q, ...f }) => api("/sto" + qs({ page, size, q, ...f })),
      onRow: (r) => App.navigate("#/d/sto/" + r.id),
      empty: emptyState("checkc", "Belum ada STO", "Buat Stock Opname untuk mulai menghitung."),
    });
    content.appendChild(dt.el);
    dt.reload();
    if (isManager) $("#sto-new", content).onclick = () => this.stoForm(() => dt.reload());
  },

  async stoForm(onDone) {
    await this.warehouses(true);
    const whs = (this._whs || []).filter((w) => w.sto_enabled !== false);
    if (!whs.length) { toast("Belum ada gudang yang diaktifkan untuk STO.", "warn"); return; }
    const s = openSheet(`<h3>Stock Opname Baru</h3>
      <div class="row gap8 mt8">
        <div class="field grow"><label class="lbl">No. STO</label><input class="input" id="st-no" placeholder="STO-2026-001"></div>
        <div class="field grow"><label class="lbl">Tanggal</label><input class="input" type="date" id="st-date" value="${new Date().toISOString().slice(0, 10)}"></div></div>
      <div class="field"><label class="lbl">Gudang</label><select class="input" id="st-wh">${options(whs, "", "id", (w) => `${w.code} — ${w.name}`)}</select></div>
      <div class="field"><label class="lbl">Keterangan</label><input class="input" id="st-desc" placeholder="opsional"></div>
      <div class="sec-title" style="margin:4px 0 6px;">Penugasan Awal (opsional)</div>
      <div class="row gap8">
        <div class="field grow"><label class="lbl">Dari Lokator</label><input class="input" id="st-from" placeholder="A-01-01"></div>
        <div class="field grow"><label class="lbl">Sampai Lokator</label><input class="input" id="st-to" placeholder="A-02-20"></div></div>
      <div class="row gap8">
        <div class="field grow"><label class="lbl">Petugas Hitung (MH)</label><select class="input" id="st-counter"></select></div>
        <div class="field grow"><label class="lbl">Checker</label><select class="input" id="st-checker"></select></div></div>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button><button class="btn lg primary" id="st-ok">Simpan</button></div>`, { wide: true });
    await this._fillTeam(s.el, "#st-counter", "#st-checker");
    $("#st-ok", s.el).onclick = (e) => busy(e.currentTarget, async () => {
      const from = $("#st-from", s.el).value.trim(), to = $("#st-to", s.el).value.trim();
      const counter = +$("#st-counter", s.el).value, checker = +$("#st-checker", s.el).value;
      const body = { sto_number: $("#st-no", s.el).value.trim(), sto_date: $("#st-date", s.el).value, warehouse_id: +$("#st-wh", s.el).value, description: $("#st-desc", s.el).value.trim() || null, assignments: [] };
      if (body.sto_number.length < 3) { toast("Nomor STO minimal 3 huruf.", "warn"); return; }
      if (from || to) {
        if (!from || !to) { toast("Isi rentang lokator dari & sampai.", "warn"); return; }
        if (!counter || !checker) { toast("Pilih petugas hitung dan checker.", "warn"); return; }
        body.assignments.push({ locator_from: from, locator_to: to, counter_id: counter, checker_id: checker });
      }
      try { const r = await api("/sto", { method: "POST", body }); toast(`STO ${r.sto_number} dibuat.`); s.close(); onDone && onDone(); App.navigate("#/d/sto/" + r.id); }
      catch (err) { toast(err.message, "error"); }
    });
  },

  async _fillTeam(el, counterSel, checkerSel) {
    try {
      const [mh, ck] = await Promise.all([api("/users/options?role=MH"), api("/users/options?role=CHECKER")]);
      $(counterSel, el).innerHTML = `<option value="">— pilih —</option>` + mh.map((u) => `<option value="${u.id}">${esc(u.full_name)}</option>`).join("");
      $(checkerSel, el).innerHTML = `<option value="">— pilih —</option>` + ck.map((u) => `<option value="${u.id}">${esc(u.full_name)}</option>`).join("");
    } catch { toast("Gagal memuat daftar petugas.", "error"); }
  },

  async renderStoDetail(root, stoId) {
    const content = this.renderShell(root, "sto");
    const isManager = Session.hasExact("SUPERVISOR", "ADMIN");
    const isChecker = Session.hasExact("CHECKER", "SUPERVISOR", "ADMIN");
    content.innerHTML = skeleton(3, 120);
    let d;
    try { d = await api("/sto/" + stoId); }
    catch (e) { content.innerHTML = this.pageHead("Stock Opname") + `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; return; }
    const p = d.progress || {};
    const statusBtns = (d.next_status || []).map((st) => {
      const primary = ["COMPLETED", "COUNTING", "RECONCILIATION", "OPEN"].includes(st);
      return `<button class="btn sm ${primary ? "primary" : ""}" data-status="${st}">${esc((STO_STATUS[st] || [st])[0])}</button>`;
    }).join("");
    content.innerHTML = this.pageHead(`STO ${d.sto_number}`, `${d.warehouse_code} · ${fmtDate(d.sto_date)}`, `<a class="btn sm" href="#/d/sto">${icon("back")} Daftar</a>`) + `
      <div class="card">
        <div class="row between"><div class="row gap8 items-center">${stoBadge(d.status)}<span class="muted">${esc(d.description || "")}</span></div>
          <div class="row gap8">${isManager ? statusBtns : ""}</div></div>
        <div class="mt12"><div class="progress"><i style="width:${p.percent}%"></i></div></div>
        <div class="row gap16 mt8 muted" style="font-size:13px;flex-wrap:wrap;">
          <span>Selesai <b class="num">${p.completed}/${p.total}</b></span>
          <span>Diterima <b class="num">${p.accepted}</b></span>
          <span>Tunggu cek <b class="num">${p.waiting_check}</b></span>
          <span>Hitung ulang <b class="num">${p.recount}</b></span>
          <span>Selisih <b class="num" style="color:${p.variance ? "var(--error)" : "inherit"}">${p.variance}</b></span>
        </div>
      </div>

      ${isManager ? `<div class="card mt16"><div class="row between"><h3 style="margin:0;">Penugasan Tim</h3><button class="btn sm" id="sto-assign">${icon("plus")} Tambah</button></div>
        <div class="table-scroll mt8"><table class="dt"><thead><tr><th>Rentang Lokator</th><th>Petugas Hitung</th><th>Checker</th><th class="r">Aksi</th></tr></thead><tbody>
          ${(d.assignments || []).length ? d.assignments.map((a) => `<tr><td>${esc(a.locator_from)} – ${esc(a.locator_to)}</td><td>${esc(a.counter || "—")}</td><td>${esc(a.checker || "—")}</td><td class="r"><button class="btn sm danger" data-del-asg="${a.id}">${icon("trash")}</button></td></tr>`).join("") : `<tr><td colspan="4" class="muted">Belum ada penugasan</td></tr>`}
        </tbody></table></div>
        <div class="row gap8 mt8"><button class="btn sm" id="sto-reset">${icon("refresh")} Reset Hasil Hitung</button><button class="btn sm danger" id="sto-del">${icon("trash")} Hapus STO</button></div>
      </div>` : ""}

      <div class="tabs mt16">
        <button class="tab active" data-tab="loc">Monitoring Lokator</button>
        <button class="tab" data-tab="recon">Rekonsiliasi vs Ledger</button>
      </div>
      <div id="sto-loc" class="mt8"></div>
      <div id="sto-recon" class="mt8" style="display:none;"></div>
    `;
    const tabLoc = $("#sto-loc", content), tabRecon = $("#sto-recon", content);
    $$(".tab", content).forEach((t) => t.onclick = () => {
      $$(".tab", content).forEach((x) => x.classList.toggle("active", x === t));
      tabLoc.style.display = t.dataset.tab === "loc" ? "" : "none";
      tabRecon.style.display = t.dataset.tab === "recon" ? "" : "none";
    });
    const reloadRecon = () => { this.stoRecon(tabRecon, stoId, isChecker, reloadRecon); this.renderStoDetail(root, stoId); };
    this.stoLocators(tabLoc, stoId);
    this.stoRecon(tabRecon, stoId, isChecker, reloadRecon);

    $$("[data-status]", content).forEach((b) => b.onclick = (e) => busy(e.currentTarget, async () => {
      const st = b.dataset.status;
      try { await api(`/sto/${stoId}/status`, { method: "POST", body: { status: st } }); toast("Status diperbarui."); this.renderStoDetail(root, stoId); }
      catch (err) {
        if (/paksa/i.test(err.message)) {
          if (await confirmDialog({ title: "Lanjutkan paksa?", body: `<p>${esc(err.message)}</p>`, confirmText: "Paksa lanjut", danger: true })) {
            try { await api(`/sto/${stoId}/status`, { method: "POST", body: { status: st, force: true } }); toast("Status diperbarui (paksa)."); this.renderStoDetail(root, stoId); }
            catch (e2) { toast(e2.message, "error"); }
          }
        } else toast(err.message, "error");
      }
    }));
    const assignBtn = $("#sto-assign", content);
    if (assignBtn) assignBtn.onclick = () => this.stoAssignForm(stoId, () => this.renderStoDetail(root, stoId));
    const resetBtn = $("#sto-reset", content);
    if (resetBtn) resetBtn.onclick = async () => {
      if (!await confirmDialog({ title: "Reset hasil hitung?", body: "<p>Semua hasil hitungan pada STO ini akan dihapus dan status lokator kembali 'Belum'.</p>", confirmText: "Reset", danger: true })) return;
      try { const r = await api(`/sto/${stoId}/reset-counts`, { method: "POST", body: {} }); toast(r.message || "Direset."); this.renderStoDetail(root, stoId); } catch (e) { toast(e.message, "error"); }
    };
    const delBtn = $("#sto-del", content);
    if (delBtn) delBtn.onclick = async () => {
      if (!await confirmDialog({ title: "Hapus STO?", body: `<p>STO ${esc(d.sto_number)} beserta seluruh data hitungannya akan dihapus permanen.</p>`, confirmText: "Hapus", danger: true })) return;
      try { await api(`/sto/${stoId}`, { method: "DELETE" }); toast("STO dihapus."); App.navigate("#/d/sto"); } catch (e) { toast(e.message, "error"); }
    };
    content.addEventListener("click", (e) => {
      const g = e.target.closest("[data-del-asg]"); if (!g) return; e.stopPropagation();
      confirmDialog({ title: "Hapus penugasan?", body: "<p>Locator pada penugasan ini akan dilepas.</p>", confirmText: "Hapus", danger: true }).then(async (ok) => {
        if (!ok) return;
        try { await api(`/sto/${stoId}/assignments/${g.dataset.delAsg}`, { method: "DELETE" }); toast("Penugasan dihapus."); this.renderStoDetail(root, stoId); } catch (err) { toast(err.message, "error"); }
      });
    });
  },

  async stoAssignForm(stoId, onDone) {
    const s = openSheet(`<h3>Tambah Penugasan</h3>
      <div class="row gap8 mt8"><div class="field grow"><label class="lbl">Dari Lokator</label><input class="input" id="sa-from" placeholder="A-01-01"></div>
        <div class="field grow"><label class="lbl">Sampai Lokator</label><input class="input" id="sa-to" placeholder="A-02-20"></div></div>
      <div class="row gap8"><div class="field grow"><label class="lbl">Petugas Hitung (MH)</label><select class="input" id="sa-counter"></select></div>
        <div class="field grow"><label class="lbl">Checker</label><select class="input" id="sa-checker"></select></div></div>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button><button class="btn lg primary" id="sa-ok">Simpan</button></div>`, { wide: true });
    await this._fillTeam(s.el, "#sa-counter", "#sa-checker");
    $("#sa-ok", s.el).onclick = (e) => busy(e.currentTarget, async () => {
      const from = $("#sa-from", s.el).value.trim(), to = $("#sa-to", s.el).value.trim();
      const counter = +$("#sa-counter", s.el).value, checker = +$("#sa-checker", s.el).value;
      if (!from || !to) { toast("Isi rentang lokator.", "warn"); return; }
      if (!counter || !checker) { toast("Pilih petugas hitung dan checker.", "warn"); return; }
      try { await api(`/sto/${stoId}/assignments`, { method: "POST", body: { locator_from: from, locator_to: to, counter_id: counter, checker_id: checker } }); toast("Penugasan ditambahkan."); s.close(); onDone && onDone(); }
      catch (err) { toast(err.message, "error"); }
    });
  },

  stoLocators(host, stoId) {
    host.innerHTML = "";
    const filters = `<div class="field" style="margin:0;min-width:160px;"><select class="input" id="f-status" data-filter="status"><option value="">Semua status</option>${Object.entries(STO_LOC_STATUS).map(([k, v]) => `<option value="${k}">${esc(v[0])}</option>`).join("")}</select></div>`;
    const dt = DataTable({
      columns: [
        { key: "code", label: "Lokator" },
        { label: "Status", render: (r) => stoBadge(r.status, STO_LOC_STATUS) },
        { key: "item_count", label: "Item", align: "r" },
        { key: "total_qty", label: "Qty", align: "r", render: (r) => `<span class="num">${fmt(r.total_qty)}</span>` },
        { key: "round", label: "Putaran", align: "r" },
        { label: "Petugas / Checker", render: (r) => `${esc(r.counter || "—")}<br><span class="muted" style="font-size:12px;">${esc(r.checker || "—")}</span>` },
      ],
      filters, size: 20,
      load: ({ page, size, q, ...f }) => api(`/sto/${stoId}/locators` + qs({ page, size, q, ...f })),
      onRow: (r) => this.stoLocatorDetail(stoId, r.id),
    });
    host.appendChild(dt.el);
    dt.reload();
  },

  async stoLocatorDetail(stoId, slId) {
    const s = openSheet(`<div id="sl-body">${skeleton(2, 60)}</div>`, { wide: true });
    try {
      const d = await api(`/sto/${stoId}/locators/${slId}`);
      const rows = d.items || [];
      const hist = { DRAFT: ["Draf", ""], SUBMITTED: ["Dikirim", "info"], FINAL: ["Final", "success"], RECOUNT: ["Hitung Ulang", "warning"] };
      $("#sl-body", s.el).innerHTML = `<h3>${esc(d.code)} ${stoBadge(d.status, STO_LOC_STATUS)}</h3>
        <div class="muted mt4">Petugas: ${esc(d.counter || "—")} · Checker: ${esc(d.checker || "—")} · Putaran ${d.round}</div>
        ${d.recount_reason ? `<div class="banner warn mt8">${icon("alert")}<div class="grow"><b>Hitung ulang</b><span>${esc(d.recount_reason)}${d.recount_note ? " — " + esc(d.recount_note) : ""}</span></div></div>` : ""}
        <div class="table-scroll mt8"><table class="dt"><thead><tr><th>Kode</th><th>Nama</th><th class="r">Qty</th><th class="r">Lembar</th></tr></thead><tbody>
          ${rows.length ? rows.map((it) => `<tr><td><b>${esc(it.code)}</b></td><td>${esc(it.name)}</td><td class="r num">${fmt(it.qty)} ${esc(it.uom)}</td><td class="r">${it.sheets}</td></tr>`).join("") : `<tr><td colspan="4" class="muted">Belum ada hitungan</td></tr>`}
        </tbody></table></div>
        <div class="sec-title">Riwayat Putaran</div>
        ${(d.history || []).map((h) => `<div class="card" style="padding:10px 12px;"><div class="row between"><b>${esc(h.label)}</b>${stoBadge(h.status, hist)}</div><div class="muted" style="font-size:12px;">${esc(h.counter || "—")} · ${fmt(h.total_qty)} qty${h.reason ? " · " + esc(h.reason) : ""}</div></div>`).join("") || `<div class="muted">Belum ada riwayat</div>`}
        <div class="actions"><button class="btn lg" data-close="true">Tutup</button></div>`;
    } catch (e) { $("#sl-body", s.el).innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
  },

  async stoRecon(host, stoId, canResolve, reload) {
    host.innerHTML = skeleton(2, 60);
    try {
      const r = await api(`/sto/${stoId}/reconciliation`);
      const s = r.summary || {};
      host.innerHTML = `
        <div class="row gap8 wrap" style="margin-bottom:8px;">
          <span class="badge success">Cocok: ${s.MATCH || 0}</span>
          <span class="badge warning">Selisih: ${s.VARIANCE || 0}</span>
          <span class="badge error">Tak terduga: ${s.UNEXPECTED || 0}</span>
          <span class="badge error">Kurang: ${s.MISSING || 0}</span>
          <span class="badge info">Lokator diterima: ${r.accepted_locators}</span>
          ${r.pending_locators ? `<span class="badge">Belum dicek: ${r.pending_locators}</span>` : ""}
        </div>
        ${r.locators.length ? r.locators.map((loc) => `<div class="card mt8"><div class="row between"><b>${esc(loc.locator_code)}</b><span class="muted">${loc.rows.filter((x) => x.status !== "MATCH").length} selisih / ${loc.rows.length} item</span></div>
          <div class="table-scroll mt8"><table class="dt"><thead><tr><th>Kode</th><th>Nama</th><th class="r">Fisik</th><th class="r">Sistem</th><th class="r">Selisih</th><th>Status</th>${canResolve ? "<th></th>" : ""}</tr></thead><tbody>
            ${loc.rows.map((x) => `<tr><td><b>${esc(x.code)}</b></td><td>${esc(x.name)}</td><td class="r num">${fmt(x.physical_qty)}</td><td class="r num">${fmt(x.ledger_qty)}</td><td class="r num" style="color:${x.diff ? "var(--error)" : "inherit"}">${x.diff > 0 ? "+" : ""}${fmt(x.diff)}</td><td>${stoBadge(x.status, RECON_STATUS)}</td>${canResolve ? `<td class="r">${x.status !== "MATCH" ? `<button class="btn sm primary" data-resolve="${loc.sto_locator_id}" data-item="${x.item_id}">${icon("edit")} Selesaikan</button>` : ""}</td>` : ""}</tr>`).join("")}
          </tbody></table></div></div>`).join("") : emptyState("clock", "Belum ada data rekonsiliasi", "Rekonsiliasi muncul setelah lokator diterima (ACCEPTED).")}
      `;
      if (canResolve) $$("[data-resolve]", host).forEach((b) => b.onclick = () => {
        const loc = r.locators.find((l) => l.sto_locator_id === +b.dataset.resolve);
        const row = loc && loc.rows.find((x) => x.item_id === +b.dataset.item);
        if (row) this.resolveVariance(stoId, +b.dataset.resolve, row, reload);
      });
    } catch (e) { host.innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
  },

  async resolveVariance(stoId, slId, row, onDone) {
    const reason = await promptDialog({ title: "Selesaikan Selisih",
      label: `Alasan penyesuaian untuk ${row.code} (fisik ${fmt(row.physical_qty)} vs sistem ${fmt(row.ledger_qty)})`,
      placeholder: "mis. hasil hitung fisik akurat, sesuaikan sistem" });
    if (!reason) return;
    try { const r = await api(`/sto/${stoId}/reconciliation/resolve`, { method: "POST", body: { sto_locator_id: slId, item_id: row.item_id, reason } }); toast(`Penyesuaian ${r.movement_no || ""} dibuat.`); onDone && onDone(); }
    catch (e) { toast(e.message, "error"); }
  },

  /* -------------------------------------------------- WAREHOUSES */
  async renderWarehouses(root) {
    const content = this.renderShell(root, "warehouses");
    content.innerHTML = this.pageHead("Master Gudang", "Kelola gudang tanpa mengubah kode",
      `<button class="btn sm primary" id="wh-new">${icon("plus")} Gudang Baru</button>`);
    const dt = DataTable({
      columns: [
        { key: "code", label: "Kode" },
        { key: "name", label: "Nama" },
        { key: "type", label: "Tipe" },
        { label: "Status", render: (w) => w.active ? `<span class="badge success">Aktif</span>` : `<span class="badge">Nonaktif</span>` },
        { label: "Aksi", render: (w) => `<button class="btn sm" data-gen="${w.id}">${icon("pin")} Generator</button> <a class="btn sm" href="/labels.html?warehouse_id=${w.id}" target="_blank">${icon("print")} Label QR</a>` },
      ],
      searchPlaceholder: "Cari gudang…",
      exportFn: () => download("/warehouses/export?fmt=xlsx", "gudang.xlsx"),
      onRow: (w) => this.warehouseForm(w, () => dt.reload()),
      load: ({ page, size, q }) => api("/warehouses" + qs({ page, size, q })),
    });
    content.appendChild(dt.el);
    dt.reload();
    $("#wh-new", content).onclick = () => this.warehouseForm(null, () => dt.reload());
    dt.el.addEventListener("click", (e) => {
      const g = e.target.closest("[data-gen]"); if (!g) return; e.stopPropagation();
      this.generateLocators(+g.dataset.gen, () => dt.reload());
    });
  },
  async warehouseForm(w, onDone) {
    const s = openSheet(`<h3>${w ? "Ubah" : "Gudang Baru"}</h3>
      <div class="field mt8"><label class="lbl">Kode</label><input class="input" id="w-code" value="${esc(w ? w.code : "")}" placeholder="mis. L21"></div>
      <div class="field"><label class="lbl">Nama</label><input class="input" id="w-name" value="${esc(w ? w.name : "")}"></div>
      <div class="field"><label class="lbl">Tipe</label><input class="input" id="w-type" value="${esc(w ? w.type : "FG")}"></div>
      <label class="row gap8 items-center mt8"><input type="checkbox" id="w-active" ${(!w || w.active) ? "checked" : ""}> Aktif</label>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button>${w ? `<button class="btn lg danger" id="w-del">Hapus</button>` : ""}<button class="btn lg primary" id="w-ok">Simpan</button></div>`);
    $("#w-ok", s.el).onclick = (e) => busy(e.currentTarget, async () => {
      const body = { code: $("#w-code", s.el).value.trim(), name: $("#w-name", s.el).value.trim(), type: $("#w-type", s.el).value.trim() || "FG", active: $("#w-active", s.el).checked, sto_enabled: true };
      try { if (w) await api(`/warehouses/${w.id}`, { method: "PUT", body }); else await api("/warehouses", { method: "POST", body }); toast("Tersimpan."); s.close(); onDone && onDone(); }
      catch (err) { toast(err.message, "error"); }
    });
    const d = $("#w-del", s.el);
    if (d) d.onclick = async () => { if (!await confirmDialog({ title: "Hapus gudang?", body: `<p>${esc(w.code)}</p>`, confirmText: "Hapus", danger: true })) return; try { await api(`/warehouses/${w.id}`, { method: "DELETE" }); toast("Dihapus."); s.close(); onDone && onDone(); } catch (err) { toast(err.message, "error"); } };
  },
  async generateLocators(wid, onDone) {
    const s = openSheet(`<h3>Generator Locator</h3><p class="muted">Buat kode lokator massal (mis. A-01-01).</p>
      <div class="field"><label class="lbl">Zona (pisah koma)</label><input class="input" id="g-zones" value="A"></div>
      <div class="row gap8"><div class="field grow"><label class="lbl">Jumlah Rak</label><input class="input num" id="g-racks" type="number" value="5" min="1" max="99"></div>
      <div class="field grow"><label class="lbl">Level per Rak</label><input class="input num" id="g-levels" type="number" value="20" min="1" max="99"></div></div>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button><button class="btn lg primary" id="g-ok">Generate</button></div>`);
    $("#g-ok", s.el).onclick = (e) => busy(e.currentTarget, async () => {
      const zones = $("#g-zones", s.el).value.split(",").map((z) => z.trim()).filter(Boolean);
      try { const r = await api("/locators/generate", { method: "POST", body: { warehouse_id: wid, zones, racks: +$("#g-racks", s.el).value, levels: +$("#g-levels", s.el).value } }); toast(`${r.created} lokator dibuat.`); s.close(); onDone && onDone(); }
      catch (err) { toast(err.message, "error"); }
    });
  },

  /* -------------------------------------------------- LOCATORS */
  async renderLocators(root) {
    const content = this.renderShell(root, "locators");
    await this.warehouses();
    content.innerHTML = this.pageHead("Master Locator", "Rak / lokasi penyimpanan", `<button class="btn sm primary" id="loc-new">${icon("plus")} Locator Baru</button>`);
    const filters = `<div class="field" style="margin:0;min-width:200px;">${this.whSelect("f-warehouse_id", "", { blank: "Semua gudang" })}</div>`;
    const dt = DataTable({
      columns: [
        { key: "warehouse_code", label: "Gudang" },
        { key: "code", label: "Kode" },
        { key: "zone", label: "Zona" },
        { key: "rack", label: "Rak" },
        { key: "level", label: "Level" },
        { label: "Status", render: (l) => l.active ? `<span class="badge success">Aktif</span>` : `<span class="badge">Nonaktif</span>` },
        { label: "Aksi", render: (l) => `<a class="btn sm" href="/labels.html?warehouse_id=${l.warehouse_id}&code=${encodeURIComponent(l.code)}" target="_blank">${icon("print")} Label</a>` },
      ],
      filters, searchPlaceholder: "Cari kode lokator…",
      exportFn: () => download("/locators/export" + qs({ warehouse_id: $("#f-warehouse_id", content).value, fmt: "xlsx" }), "locator.xlsx"),
      onRow: (l) => this.locatorForm(l, () => dt.reload()),
      load: ({ page, size, q, ...f }) => api("/locators" + qs({ page, size, q, ...f })),
    });
    content.appendChild(dt.el);
    dt.reload();
    $("#loc-new", content).onclick = () => this.locatorForm(null, () => dt.reload());
  },
  async locatorForm(l, onDone) {
    await this.warehouses();
    const s = openSheet(`<h3>${l ? "Ubah" : "Locator Baru"}</h3>
      <div class="field mt8"><label class="lbl">Gudang</label><select class="input" id="l-wh">${options(this._whs, l ? l.warehouse_id : "", "id", (w) => `${w.code} — ${w.name}`)}</select></div>
      <div class="field"><label class="lbl">Kode Lokator</label><input class="input" id="l-code" value="${esc(l ? l.code : "")}"></div>
      <div class="row gap8"><div class="field grow"><label class="lbl">Zona</label><input class="input" id="l-zone" value="${esc(l ? l.zone || "" : "")}"></div>
      <div class="field grow"><label class="lbl">Rak</label><input class="input" id="l-rack" value="${esc(l ? l.rack || "" : "")}"></div>
      <div class="field grow"><label class="lbl">Level</label><input class="input" id="l-level" value="${esc(l ? l.level || "" : "")}"></div></div>
      <label class="row gap8 items-center mt8"><input type="checkbox" id="l-active" ${(!l || l.active) ? "checked" : ""}> Aktif</label>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button>${l ? `<button class="btn lg danger" id="l-del">Hapus</button>` : ""}<button class="btn lg primary" id="l-ok">Simpan</button></div>`);
    $("#l-ok", s.el).onclick = (e) => busy(e.currentTarget, async () => {
      const body = { warehouse_id: +$("#l-wh", s.el).value, code: $("#l-code", s.el).value.trim(), zone: $("#l-zone", s.el).value.trim() || null, rack: $("#l-rack", s.el).value.trim() || null, level: $("#l-level", s.el).value.trim() || null, active: $("#l-active", s.el).checked };
      try { if (l) await api(`/locators/${l.id}`, { method: "PUT", body }); else await api("/locators", { method: "POST", body }); toast("Tersimpan."); s.close(); onDone && onDone(); }
      catch (err) { toast(err.message, "error"); }
    });
    const d = $("#l-del", s.el);
    if (d) d.onclick = async () => { if (!await confirmDialog({ title: "Hapus locator?", body: `<p>${esc(l.code)}</p>`, confirmText: "Hapus", danger: true })) return; try { await api(`/locators/${l.id}`, { method: "DELETE" }); toast("Dihapus."); s.close(); onDone && onDone(); } catch (err) { toast(err.message, "error"); } };
  },

  /* -------------------------------------------------- ITEMS */
  async renderItems(root) {
    const content = this.renderShell(root, "items");
    content.innerHTML = this.pageHead("Master Item", "Daftar barang", `<button class="btn sm primary" id="it-new">${icon("plus")} Item Baru</button>`);
    const dt = DataTable({
      columns: [
        { key: "code", label: "Kode" },
        { key: "name", label: "Nama" },
        { key: "uom", label: "Satuan" },
        { key: "group_name", label: "Grup" },
        { label: "Status", render: (i) => i.active ? `<span class="badge success">Aktif</span>` : `<span class="badge">Nonaktif</span>` },
      ],
      searchPlaceholder: "Cari kode / nama…",
      exportFn: () => download("/items/export?fmt=xlsx", "items.xlsx"),
      onRow: (i) => this.itemForm(i, () => dt.reload()),
      load: ({ page, size, q }) => api("/items" + qs({ page, size, q })),
    });
    content.appendChild(dt.el);
    dt.reload();
    $("#it-new", content).onclick = () => this.itemForm(null, () => dt.reload());
  },
  async itemForm(i, onDone) {
    await this.warehouses();
    const s = openSheet(`<h3>${i ? "Ubah" : "Item Baru"}</h3>
      <div class="row gap8"><div class="field grow"><label class="lbl">Kode</label><input class="input" id="i-code" value="${esc(i ? i.code : "")}"></div>
      <div class="field" style="width:110px;"><label class="lbl">UOM</label><input class="input" id="i-uom" value="${esc(i ? i.uom : "PCS")}"></div></div>
      <div class="field"><label class="lbl">Nama</label><input class="input" id="i-name" value="${esc(i ? i.name : "")}"></div>
      <div class="row gap8"><div class="field grow"><label class="lbl">Grup Kode</label><input class="input" id="i-gcode" value="${esc(i ? i.group_code || "" : "")}"></div>
      <div class="field grow"><label class="lbl">Grup Nama</label><input class="input" id="i-gname" value="${esc(i ? i.group_name || "" : "")}"></div></div>
      <div class="row gap8"><div class="field grow"><label class="lbl">QR Code</label><input class="input" id="i-qr" value="${esc(i ? i.qr_code || "" : "")}"></div>
      <div class="field grow"><label class="lbl">Barcode</label><input class="input" id="i-barcode" value="${esc(i ? i.barcode || "" : "")}"></div></div>
      <div class="field"><label class="lbl">Gudang yang diizinkan (kosong = semua)</label>
        <div class="row gap8 wrap">${(this._whs || []).map((w) => `<label class="row gap4 items-center"><input type="checkbox" class="i-wh" value="${w.id}" ${(!i || !i.warehouse_ids.length || i.warehouse_ids.includes(w.id)) ? "checked" : ""}> ${esc(w.code)}</label>`).join("")}</div></div>
      <label class="row gap8 items-center mt8"><input type="checkbox" id="i-active" ${(!i || i.active) ? "checked" : ""}> Aktif</label>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button>${i ? `<button class="btn lg danger" id="i-del">Hapus</button>` : ""}<button class="btn lg primary" id="i-ok">Simpan</button></div>`, { wide: true });
    $("#i-ok", s.el).onclick = (e) => busy(e.currentTarget, async () => {
      const body = { code: $("#i-code", s.el).value.trim(), name: $("#i-name", s.el).value.trim(), uom: $("#i-uom", s.el).value.trim(), group_code: $("#i-gcode", s.el).value.trim() || null, group_name: $("#i-gname", s.el).value.trim() || null, qr_code: $("#i-qr", s.el).value.trim() || null, barcode: $("#i-barcode", s.el).value.trim() || null, warehouse_ids: $$(".i-wh:checked", s.el).map((c) => +c.value), active: $("#i-active", s.el).checked };
      try { if (i) await api(`/items/${i.id}`, { method: "PUT", body }); else await api("/items", { method: "POST", body }); toast("Tersimpan."); s.close(); onDone && onDone(); }
      catch (err) { toast(err.message, "error"); }
    });
    const d = $("#i-del", s.el);
    if (d) d.onclick = async () => { if (!await confirmDialog({ title: "Hapus item?", body: `<p>${esc(i.code)} (${esc(i.uom)})</p>`, confirmText: "Hapus", danger: true })) return; try { await api(`/items/${i.id}`, { method: "DELETE" }); toast("Dihapus."); s.close(); onDone && onDone(); } catch (err) { toast(err.message, "error"); } };
  },

  /* -------------------------------------------------- USERS */
  async renderUsers(root) {
    const content = this.renderShell(root, "users");
    content.innerHTML = this.pageHead("Pengguna", "Kelola akun dan role", `<button class="btn sm primary" id="u-new">${icon("plus")} Pengguna Baru</button>`);
    const dt = DataTable({
      columns: [
        { key: "username", label: "Username" },
        { key: "full_name", label: "Nama" },
        { label: "Role", render: (u) => u.roles.map((r) => `<span class="badge info">${esc(r)}</span>`).join(" ") },
        { label: "Status", render: (u) => u.active ? `<span class="badge success">Aktif</span>` : `<span class="badge">Nonaktif</span>` },
      ],
      exportFn: () => download("/users/export?fmt=xlsx", "users.xlsx"),
      onRow: (u) => this.userForm(u, () => dt.reload()),
      load: ({ page, size, q }) => api("/users" + qs({ page, size, q })),
    });
    content.appendChild(dt.el);
    dt.reload();
    $("#u-new", content).onclick = () => this.userForm(null, () => dt.reload());
  },
  async userForm(u, onDone) {
    const ROLES = ["ADMIN", "SUPERVISOR", "CHECKER", "MH"];
    const s = openSheet(`<h3>${u ? "Ubah" : "Pengguna Baru"}</h3>
      <div class="field mt8"><label class="lbl">Username</label><input class="input" id="u-un" value="${esc(u ? u.username : "")}"></div>
      <div class="field"><label class="lbl">Nama Lengkap</label><input class="input" id="u-fn" value="${esc(u ? u.full_name : "")}"></div>
      <div class="field"><label class="lbl">Password ${u ? "(kosongkan bila tidak diubah)" : ""}</label><input type="password" class="input" id="u-pw"></div>
      <div class="field"><label class="lbl">Role</label><div class="row gap12 wrap">${ROLES.map((r) => `<label class="row gap4 items-center"><input type="checkbox" class="u-role" value="${r}" ${u && u.roles.includes(r) ? "checked" : ""}> ${r}</label>`).join("")}</div></div>
      <label class="row gap8 items-center mt8"><input type="checkbox" id="u-active" ${(!u || u.active) ? "checked" : ""}> Aktif</label>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button>${u ? `<button class="btn lg danger" id="u-del">Hapus</button>` : ""}<button class="btn lg primary" id="u-ok">Simpan</button></div>`);
    $("#u-ok", s.el).onclick = (e) => busy(e.currentTarget, async () => {
      const roles = $$(".u-role:checked", s.el).map((c) => c.value);
      if (!roles.length) { toast("Pilih minimal satu role.", "warn"); return; }
      const body = { username: $("#u-un", s.el).value.trim(), full_name: $("#u-fn", s.el).value.trim(), roles, active: $("#u-active", s.el).checked };
      const pw = $("#u-pw", s.el).value; if (pw) body.password = pw;
      try { if (u) await api(`/users/${u.id}`, { method: "PUT", body }); else await api("/users", { method: "POST", body }); toast("Tersimpan."); s.close(); onDone && onDone(); }
      catch (err) { toast(err.message, "error"); }
    });
    const d = $("#u-del", s.el);
    if (d) d.onclick = async () => { if (!await confirmDialog({ title: "Hapus pengguna?", body: `<p>${esc(u.username)}</p>`, confirmText: "Hapus", danger: true })) return; try { await api(`/users/${u.id}`, { method: "DELETE" }); toast("Dihapus."); s.close(); onDone && onDone(); } catch (err) { toast(err.message, "error"); } };
  },

  /* -------------------------------------------------- IMPORTS */
  async renderImports(root) {
    const content = this.renderShell(root, "imports");
    content.innerHTML = this.pageHead("Import Excel", "Upload master data: Item, Gudang, Locator, Pengguna");
    const kinds = ["ITEM", "WAREHOUSE", "LOCATOR", "USER"];
    const card = document.createElement("div"); card.className = "card";
    card.innerHTML = `<div class="row gap8 wrap items-end">
        <div class="field" style="margin:0;min-width:200px;"><label class="lbl">Jenis Data</label>
          <select class="input" id="im-kind">${kinds.map((k) => `<option value="${k}">${k}</option>`).join("")}</select></div>
        <div class="field" style="margin:0;"><label class="lbl">File .xlsx</label><input class="input" type="file" id="im-file" accept=".xlsx"></div>
        <button class="btn primary" id="im-upload">${icon("upload")} Upload</button>
        <button class="btn" id="im-tpl">${icon("download")} Template</button>
      </div>`;
    content.appendChild(card);
    const dt = DataTable({
      columns: [
        { key: "id", label: "#" },
        { key: "kind", label: "Jenis" },
        { key: "filename", label: "File" },
        { key: "total_rows", label: "Baris", align: "r" },
        { key: "valid_rows", label: "Valid", align: "r" },
        { key: "error_rows", label: "Error", align: "r", render: (r) => r.error_rows ? `<span style="color:var(--error)">${r.error_rows}</span>` : "0" },
        { key: "status", label: "Status", render: (r) => `<span class="badge ${r.status === "COMMITTED" ? "success" : r.status === "CANCELLED" ? "error" : "info"}">${esc(r.status)}</span>` },
        { label: "Aksi", render: (r) => `<button class="btn sm" data-view="${r.id}">Detail</button>` },
      ],
      search: false,
      load: ({ page, size }) => api("/imports" + qs({ page, size })),
    });
    content.appendChild(dt.el);
    dt.reload();
    dt.el.addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (b) this.importDetail(+b.dataset.view, () => dt.reload()); });
    $("#im-tpl", content).onclick = () => download(`/imports/template/${$("#im-kind", content).value}`, `template_${$("#im-kind", content).value.toLowerCase()}.xlsx`);
    $("#im-upload", content).onclick = (e) => busy(e.currentTarget, async () => {
      const f = $("#im-file", content).files[0]; if (!f) { toast("Pilih file .xlsx.", "warn"); return; }
      const fd = new FormData(); fd.append("kind", $("#im-kind", content).value); fd.append("file", f);
      try { const r = await api("/imports/upload", { method: "POST", form: fd }); toast(`Terunggah: ${r.valid_rows} valid, ${r.error_rows} error.`); dt.reload(); this.importDetail(r.id, () => dt.reload()); }
      catch (err) { toast(err.message, "error"); }
    });
  },
  async importDetail(id, onDone) {
    const s = openSheet(`<div id="imp-body">${skeleton(3, 40)}</div>`, { wide: true });
    try {
      const imp = await api(`/imports/${id}`);
      const errs = await api(`/imports/${id}/errors?size=200`);
      $("#imp-body", s.el).innerHTML = `
        <h3 style="margin:0;">Import #${imp.id} · ${esc(imp.kind)}</h3>
        <div class="muted">${esc(imp.filename)} · ${imp.valid_rows} valid / ${imp.error_rows} error</div>
        ${imp.status === "PREVIEW" ? `<div class="row gap8 mt12"><button class="btn primary" id="imp-commit">Commit</button><button class="btn" id="imp-cancel">Batalkan</button></div>` : `<div class="banner info mt12">${icon("info")}<div>Status: <b>${esc(imp.status)}</b></div></div>`}
        ${errs.total ? `<div class="mt16"><div class="lbl">ERRORS (${errs.total})</div><div class="table-scroll" style="max-height:40vh;"><table class="dt"><thead><tr><th>Baris</th><th>Severity</th><th>Kolom</th><th>Pesan</th></tr></thead><tbody>${errs.items.map((e) => `<tr><td class="num">${e.row}</td><td>${esc(e.severity)}</td><td>${esc(e.column)}</td><td>${esc(e.message)}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
        <div class="actions"><button class="btn lg" data-close="true">Tutup</button></div>`;
      const c = $("#imp-commit", s.el);
      if (c) c.onclick = (e) => busy(e.currentTarget, async () => { try { await api(`/imports/${id}/commit`, { method: "POST" }); toast("Import berhasil di-commit."); s.close(); onDone && onDone(); } catch (err) { toast(err.message, "error"); } });
      const x = $("#imp-cancel", s.el);
      if (x) x.onclick = async () => { try { await api(`/imports/${id}/cancel`, { method: "POST" }); toast("Dibatalkan."); s.close(); onDone && onDone(); } catch (err) { toast(err.message, "error"); } };
    } catch (e) { $("#imp-body", s.el).innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
  },

  /* -------------------------------------------------- REPORTS */
  async renderReports(root) {
    const content = this.renderShell(root, "reports");
    await this.warehouses();
    const REPORTS = [
      ["stock_balance", "Saldo Stok"], ["movement_history", "Riwayat Pergerakan"], ["inbound", "Barang Masuk"],
      ["outbound", "Barang Keluar"], ["transfer", "Transfer"], ["corrections", "Koreksi & Pembatalan"],
    ];
    if (Session.hasExact("ADMIN")) REPORTS.push(["audit_log", "Audit Log"]);
    content.innerHTML = this.pageHead("Laporan", "Preview dan ekspor laporan");
    const bar = document.createElement("div"); bar.className = "toolbar";
    bar.innerHTML = `<div class="field" style="margin:0;min-width:200px;"><select class="input" id="rp-name">${REPORTS.map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></div>
      <div class="field" style="margin:0;min-width:180px;">${this.whSelect("rp-wh", "", { blank: "Semua gudang" })}</div>
      <div class="field" style="margin:0;"><input class="input" type="date" id="rp-from"></div>
      <div class="field" style="margin:0;"><input class="input" type="date" id="rp-to"></div>
      <div class="search">${icon("search")}<input class="input" id="rp-q" placeholder="Cari…"></div>
      <button class="btn sm" id="rp-run">${icon("search")} Tampilkan</button>
      <button class="btn sm" id="rp-xlsx">${icon("download")} Excel</button>
      <button class="btn sm" id="rp-csv">CSV</button>
      <button class="btn sm" id="rp-pdf">PDF</button>`;
    content.appendChild(bar);
    const out = document.createElement("div"); out.className = "card mt16"; out.innerHTML = `<div class="muted center p20">Pilih laporan lalu klik Tampilkan.</div>`;
    content.appendChild(out);
    const params = () => ({ warehouse_id: $("#rp-wh", content).value, date_from: $("#rp-from", content).value, date_to: $("#rp-to", content).value, q: $("#rp-q", content).value.trim() });
    const run = async () => {
      out.innerHTML = skeleton(3, 36);
      try {
        const r = await api(`/reports/${$("#rp-name", content).value}` + qs({ ...params(), size: 200 }));
        out.innerHTML = `<h3 style="margin:0 0 12px;">${esc(r.title)} <span class="muted" style="font-size:13px;">(${fmt(r.total)} baris)</span></h3>
          <div class="table-scroll" style="max-height:65vh;"><table class="dt"><thead><tr>${r.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${r.rows.map((row) => `<tr>${row.map((v) => `<td>${esc(v ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      } catch (e) { out.innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
    };
    $("#rp-run", content).onclick = (e) => busy(e.currentTarget, run);
    $("#rp-xlsx", content).onclick = () => download(`/reports/${$("#rp-name", content).value}` + qs({ ...params(), fmt: "xlsx" }));
    $("#rp-csv", content).onclick = () => download(`/reports/${$("#rp-name", content).value}` + qs({ ...params(), fmt: "csv" }));
    $("#rp-pdf", content).onclick = () => download(`/reports/${$("#rp-name", content).value}` + qs({ ...params(), fmt: "pdf" }));
    run();
  },

  /* -------------------------------------------------- AUDIT */
  async renderAudit(root) {
    const content = this.renderShell(root, "audit");
    content.innerHTML = this.pageHead("Audit Log", "Jejak semua aktivitas sistem");
    let actions = [];
    try { actions = await api("/audit/actions"); } catch { }
    const filters = `<div class="field" style="margin:0;min-width:180px;"><select class="input" id="f-action" data-filter="action"><option value="">Semua aksi</option>${actions.map((a) => `<option value="${esc(a)}">${esc(a)}</option>`).join("")}</select></div>`;
    const dt = DataTable({
      columns: [
        { label: "Waktu", render: (r) => fmtDate(r[0]) },
        { label: "Pengguna", render: (r) => esc(r[1]) },
        { label: "Aksi", render: (r) => `<span class="badge info">${esc(r[2])}</span>` },
        { label: "Objek", render: (r) => esc(r[3] + (r[4] ? " #" + r[4] : "")) },
        { label: "Nilai Baru", render: (r) => `<span class="muted" style="font-size:12px;">${esc((r[6] || "").slice(0, 90))}</span>` },
        { label: "IP", render: (r) => esc(r[7] || "") },
      ],
      searchPlaceholder: "Cari pengguna / aksi / objek…", filters,
      load: ({ page, size, q, action }) => api("/reports/audit_log" + qs({ page, size, q, action, fmt: "json" })).then((r) => ({ items: r.rows, total: r.total })),
    });
    content.appendChild(dt.el);
    dt.reload();
  },
};
