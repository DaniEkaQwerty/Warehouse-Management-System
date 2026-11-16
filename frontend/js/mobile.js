/* ===========================================================
   MOBILE SCREENS (Material Handling / field operators)
   - Home (warehouse picker, today's activity, quick actions, recent)
   - Inbound (barang masuk), Outbound (barang keluar), Transfer
   - Stock (saldo per lokator), Sync center, Profile
   =========================================================== */

const Mobile = {
  warehouseId: null,

  initState() {
    const saved = localStorage.getItem("wms_mobile_wh");
    this.warehouseId = saved ? Number(saved) : null;
    const whs = Store.warehouses;
    if (whs && whs.length && !whs.some((w) => Number(w.id) === this.warehouseId)) this.warehouseId = Number(whs[0].id);
    if (this.warehouseId) localStorage.setItem("wms_mobile_wh", String(this.warehouseId));
  },
  setWarehouse(id) {
    this.warehouseId = Number(id) || null;
    if (this.warehouseId) localStorage.setItem("wms_mobile_wh", String(this.warehouseId));
  },

  topbar(title, { back = null, right = "" } = {}) {
    const u = Session.user;
    return `<header class="m-top">
      ${back ? `<button class="btn icon ghost" id="m-back" aria-label="Kembali">${icon("back")}</button>` : `<div class="logo-mark" style="width:34px;height:34px;border-radius:8px;">${icon("box")}</div>`}
      <div class="title"><h2>${esc(title)}</h2><div class="sub">${esc(u.full_name)}</div></div>
      ${right || `<button class="btn icon ghost" id="m-profile" aria-label="Akun">${icon("user")}</button>`}
    </header>`;
  },
  renderBottomNav(active) {
    const pending = Store.pending.length;
    const tabs = [
      { id: "home", label: "BERANDA", hash: "#/m", icon: "home" },
      { id: "scan", label: "SCAN", hash: "#/m/scan", icon: "scan" },
      { id: "me", label: "AKUN", hash: "#/m/me", icon: "user" },
    ];
    return `<nav class="m-nav" aria-label="Navigasi Utama">
      ${tabs.map((t) => `<a href="${t.hash}" class="${active === t.id ? "active" : ""}">${icon(t.icon)}<span>${esc(t.label)}</span>${t.id === "home" && pending ? `<span class="dot">${pending}</span>` : ""}</a>`).join("")}
    </nav>`;
  },
  wireTopbar(root, { onBack } = {}) {
    const b = $("#m-back", root); if (b) b.onclick = onBack || (() => App.navigate("#/m"));
    const p = $("#m-profile", root); if (p) p.onclick = () => App.navigate("#/m/me");
  },
  async ensureBundle(warehouseId, includeItems = true) {
    if (!Store.warehouses.length || includeItems) await Store.loadBundle(warehouseId, { includeItems }).catch(() => {});
  },

  /* -------------------------------------------------- HOME (Beranda) */
  async renderHome(root) {
    await this.ensureBundle(this.warehouseId, true);
    this.initState();
    root.innerHTML = `${this.topbar("Beranda")}
      <main class="m-page" id="m-content">${skeleton(3, 110)}</main>
      ${this.renderBottomNav("home")}`;
    this.wireTopbar(root);
    const content = $("#m-content", root);

    const whs = Store.warehouses;
    if (!whs.length) {
      content.innerHTML = emptyState("wh", "Belum ada gudang", "Minta Admin menambahkan gudang terlebih dahulu.");
      return;
    }
    let data = { counts: {}, recent: [], messages: [], unread: 0, tasks: [] };
    try { data = await api("/m/home" + qs({ warehouse_id: this.warehouseId })); } catch (e) { /* offline */ }
    const tasks = data.tasks || [];

    const c = data.counts || {};
    const msgs = data.messages || [];
    const unread = data.unread || 0;
    const pending = Store.pending.length, rejected = Store.rejected.length;

    content.innerHTML = `
      ${(pending || rejected) ? `<div class="banner ${rejected ? "error" : "warn"}">
        ${icon(rejected ? "alert" : "wifioff")}
        <div class="grow"><b>${pending} transaksi menunggu sinkron</b><span>${rejected ? rejected + " ditolak server" : "Akan terkirim otomatis saat online."}</span></div>
        <a href="#/m/sync" class="btn sm">Lihat</a>
      </div>` : ""}

      <div class="field"><label class="lbl">GUDANG AKTIF</label>
        <select class="input" id="m-wh">${options(whs, this.warehouseId, "id", (w) => `${w.code} — ${w.name}`)}</select></div>

      <div class="row between items-center"><div class="sec-title" style="margin:0;">Pesan</div>
        ${unread ? `<span class="badge error" id="msg-unread">${unread} baru</span>` : ""}</div>
      ${msgs.length ? msgs.slice(0, 4).map((m) => this.messageCard(m)).join("")
        : emptyState("bell", "Belum ada pesan", "Pesan dari Admin, Supervisor, atau Checker akan tampil di sini.")}

      <div class="sec-title">Tugas Saya</div>
      ${tasks.length ? tasks.map((s) => `<button class="card block" data-sto="${s.id}" style="text-align:left;width:100%;">
          <div class="row between"><b>${esc(s.sto_number)}</b>${stoBadge(s.status)}</div>
          <div class="muted" style="font-size:13px;">${esc(s.warehouse_code)} · ${esc(fmtDate(s.sto_date))}</div>
          <div class="row gap8 wrap mt8"><span class="badge info">${s.my_locators} lokator saya</span>
            ${s.my_todo ? `<span class="badge warning">${s.my_todo} belum selesai</span>` : `<span class="badge success">semua selesai</span>`}</div>
        </button>`).join("") : emptyState("checkc", "Tidak ada tugas", "Belum ada Stock Opname aktif untuk Anda.")}

      <div class="sec-title">Aktivitas Hari Ini</div>
      <div class="stat-grid">
        <div class="stat ok"><div class="v num">${fmt(c.inbound || 0)}</div><div class="l">Masuk (qty)</div></div>
        <div class="stat"><div class="v num">${fmt(c.outbound || 0)}</div><div class="l">Keluar (qty)</div></div>
        <div class="stat"><div class="v num">${fmt(c.transfer || 0)}</div><div class="l">Pindah (qty)</div></div>
      </div>

      <div class="sec-title">Aksi Cepat</div>
      <div class="row gap8 wrap">
        <a href="#/m/scan" class="btn primary grow" style="justify-content:center;">${icon("scan")} Transaksi Barang</a>
        <a href="#/m/stock" class="btn ghost grow" style="justify-content:center;">${icon("search")} Cek Stok</a>
      </div>

      <div class="sec-title">Pergerakan Terakhir Saya</div>
      ${(data.recent && data.recent.length) ? data.recent.map((m) => this.movementCard(m)).join("") : emptyState("clock", "Belum ada aktivitas", "Transaksi yang Anda buat akan tampil di sini.")}
    `;

    $("#m-wh", content).onchange = (e) => { this.setWarehouse(e.target.value); Store.loadBundle(this.warehouseId, { includeItems: true }).finally(() => this.renderHome(root)); };
    $$("[data-sto]", content).forEach((b) => b.onclick = () => App.navigate("#/m/opname/" + b.dataset.sto));
    $$("[data-msg]", content).forEach((b) => b.onclick = () => {
      const m = msgs.find((x) => String(x.id) === b.dataset.msg);
      if (!m) return;
      this.openMessage(m, () => {
        if (m.read) return;
        m.read = true;
        b.classList.remove("unread");
        const ub = $("#msg-unread", content);
        const n = msgs.filter((x) => !x.read).length;
        if (ub) { if (n) ub.textContent = n + " baru"; else ub.remove(); }
        api(`/m/messages/${m.id}/read`, { method: "POST" }).catch(() => {});
      });
    });
  },

  messageCard(m) {
    return `<div class="card msg ${m.read ? "" : "unread"}" data-msg="${m.id}" style="padding:12px 14px;cursor:pointer;">
      <div class="row between"><div class="row gap8 items-center">${msgBadge(m.level)}${m.read ? "" : '<span class="badge accent">Baru</span>'}</div><span class="muted" style="font-size:12px;">${fmtDate(m.created_at)}</span></div>
      ${m.title ? `<div class="mt8"><b>${esc(m.title)}</b></div>` : ""}
      <div class="muted" style="font-size:13px;">${esc(m.body.length > 110 ? m.body.slice(0, 110) + "…" : m.body)}</div>
      <div class="muted" style="font-size:12px;margin-top:4px;">— ${esc(m.sender || "Sistem")}</div>
    </div>`;
  },

  openMessage(m, onRead) {
    openSheet(`
      <div class="row between items-center">${msgBadge(m.level)}<span class="muted" style="font-size:12px;">${fmtDate(m.created_at)}</span></div>
      <h3 class="mt8">${esc(m.title || "Pesan")}</h3>
      <p style="white-space:pre-wrap;">${esc(m.body)}</p>
      <div class="muted" style="font-size:12px;">Dari: ${esc(m.sender || "Sistem")} · Untuk: ${esc(MESSAGE_TARGETS[m.target_role] || m.target_role)}</div>
      <div class="actions"><button class="btn lg block primary" data-close="true">Tutup</button></div>`);
    onRead && onRead();
  },

  movementCard(m) {
    const dir = m.movement_type === "INBOUND" ? `→ ${esc(m.to_locator_code || "—")}`
      : m.movement_type === "OUTBOUND" ? `${esc(m.from_locator_code || "—")} →`
        : `${esc(m.from_locator_code || "—")} → ${esc(m.to_locator_code || "—")}`;
    return `<div class="card" style="padding:12px 14px;">
      <div class="row between"><div class="row gap8 items-center">${moveBadge(m.movement_type)}<b class="num">${esc(m.movement_no || "")}</b></div>${voidBadge(m)}</div>
      <div class="mt8"><b>${esc(m.code || "")}</b> · ${esc(m.name || "")}</div>
      <div class="row between mt8"><span class="muted" style="font-size:13px;">${dir}</span><span class="num" style="font-weight:700;">${fmt(m.qty)} ${esc(m.uom || "")}</span></div>
      <div class="muted" style="font-size:12px;margin-top:4px;">${fmtDate(m.created_at)}</div>
    </div>`;
  },

  /* -------------------------------------------------- STOCK */
  async renderStock(root) {
    await this.ensureBundle(this.warehouseId, false);
    this.initState();
    root.innerHTML = `${this.topbar("Cek Stok")}
      <main class="m-page" id="m-content">
        <div class="field"><label class="lbl">GUDANG</label>
          <select class="input" id="m-wh">${options(Store.warehouses, this.warehouseId, "id", (w) => `${w.code} — ${w.name}`)}</select></div>
        <div class="field"><label class="lbl">CARI (kode / nama / lokator)</label>
          <input class="input" id="m-q" placeholder="Ketik untuk mencari…" autocomplete="off"></div>
        <div id="m-stock-list">${skeleton(4, 64)}</div>
      </main>
      ${this.renderBottomNav("scan")}`;
    this.wireTopbar(root);
    const list = $("#m-stock-list", root);
    const load = async () => {
      if (!this.warehouseId) { list.innerHTML = emptyState("wh", "Pilih gudang"); return; }
      if (!Net.online) { list.innerHTML = emptyState("wifioff", "Butuh koneksi", "Saldo stok selalu dihitung dari server."); return; }
      list.innerHTML = skeleton(4, 64);
      try {
        const r = await api("/m/stock" + qs({ warehouse_id: this.warehouseId, q: $("#m-q", root).value.trim() }));
        const items = r.items || [];
        list.innerHTML = items.length ? items.map((s) => `<div class="card" style="padding:12px 14px;">
          <div class="row between"><b>${esc(s.code)}</b><span class="num" style="font-weight:700;">${fmt(s.qty)} ${esc(s.uom)}</span></div>
          <div>${esc(s.name)}</div><div class="muted" style="font-size:13px;">${icon("pin", "i sm")} ${esc(s.locator_code)} · ${esc(s.warehouse_code || "")}</div></div>`).join("")
          : emptyState("box", "Stok kosong", "Tidak ada saldo yang cocok dengan pencarian.");
      } catch (e) { list.innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
    };
    $("#m-wh", root).onchange = (e) => { this.setWarehouse(e.target.value); load(); };
    $("#m-q", root).addEventListener("input", debounce(load, 300));
    load();
  },

  /* -------------------------------------------------- MOVEMENTS (unified Scan) */
  async renderScan(root) {
    await this.ensureBundle(this.warehouseId, true);
    this.initState();
    this._scanType = this._scanType || "INBOUND";
    root.innerHTML = `${this.topbar("Scan")}
      <main class="m-page" id="m-content"></main>
      ${this.renderBottomNav("scan")}`;
    this.wireTopbar(root);
    const content = $("#m-content", root);
    const paint = () => {
      content.innerHTML = `<div class="seg" id="mv-seg">
          ${[["INBOUND", "Masuk"], ["OUTBOUND", "Keluar"], ["TRANSFER", "Pindah"]].map(([t, l]) => `<button type="button" data-t="${t}" class="${this._scanType === t ? "active" : ""}">${esc(l)}</button>`).join("")}
        </div>
        <div id="mv-host"></div>`;
      $$("#mv-seg button", content).forEach((b) => b.onclick = () => { this._scanType = b.dataset.t; paint(); });
      this.movementForm($("#mv-host", content), this._scanType, paint);
    };
    paint();
  },

  async renderMovement(root, type) {
    await this.ensureBundle(this.warehouseId, true);
    this.initState();
    const title = { INBOUND: "Barang Masuk", OUTBOUND: "Barang Keluar", TRANSFER: "Transfer" }[type] || "Transaksi";
    root.innerHTML = `${this.topbar(title)}
      <main class="m-page" id="m-content"></main>
      ${this.renderBottomNav("scan")}`;
    this.wireTopbar(root);
    this.movementForm($("#m-content", root), type, null);
  },

  movementForm(content, type, onSwitch) {
    const meta = {
      INBOUND: { title: "Barang Masuk", sub: "Terima barang ke lokator", icon: "inbox" },
      OUTBOUND: { title: "Barang Keluar", sub: "Keluarkan barang dari lokator", icon: "outbox" },
      TRANSFER: { title: "Transfer", sub: "Pindahkan antar lokator", icon: "cmp" },
    }[type];
    const st = { item: null, from: null, to: null, qty: null, refType: "PO", refNo: "", notes: "" };

    const render = async () => {
      const whs = Store.warehouses;
      content.innerHTML = `
        <div class="banner info" style="margin-top:0;">${icon(meta.icon)}<div class="grow"><b>${esc(meta.title)}</b><span>${esc(meta.sub)}</span></div></div>
        <div class="field"><label class="lbl">GUDANG</label>
          <select class="input" id="mv-wh">${options(whs, this.warehouseId, "id", (w) => `${w.code} — ${w.name}`)}</select></div>

        <div class="field"><label class="lbl">BARANG</label>
          <button class="btn block ${st.item ? "ghost" : "primary"}" id="mv-item" style="justify-content:space-between;">
            ${st.item ? `<span>${esc(st.item.code)} · ${esc(st.item.name)} <span class="muted">(${esc(st.item.uom)})</span></span><span class="muted">ganti</span>` : `${icon("scan")} Scan / Cari Barang`}
          </button></div>

        ${type === "INBOUND" ? this.locatorField("mv-to", "LOKATOR TUJUAN", st.to) : ""}
        ${type === "OUTBOUND" ? this.locatorField("mv-from", "LOKATOR ASAL", st.from) : ""}
        ${type === "TRANSFER" ? this.locatorField("mv-from", "DARI LOKATOR", st.from) + this.locatorField("mv-to", "KE LOKATOR", st.to) : ""}

        <div id="mv-balance"></div>

        <div class="field"><label class="lbl">JUMLAH</label>
          <button class="btn block ${st.qty ? "ghost" : "primary"}" id="mv-qty" style="justify-content:space-between;">
            ${st.qty ? `<span class="num" style="font-weight:700;">${fmt(st.qty)} ${esc(st.item ? st.item.uom : "")}</span><span class="muted">ubah</span>` : `${icon("plus")} Masukkan Jumlah`}
          </button></div>

        <div class="row gap8">
          <div class="field grow"><label class="lbl">JENIS REFERENSI</label>
            <select class="input" id="mv-ref">${REF_TYPES.map((r) => `<option value="${r}" ${st.refType === r ? "selected" : ""}>${esc(refLabel(r))}</option>`).join("")}</select></div>
          <div class="field grow"><label class="lbl">NO REFERENSI</label>
            <input class="input" id="mv-refno" placeholder="Opsional" value="${esc(st.refNo)}"></div>
        </div>
        <div class="field"><label class="lbl">CATATAN</label>
          <input class="input" id="mv-notes" placeholder="Opsional" value="${esc(st.notes)}"></div>

        <button class="btn primary lg block mt16" id="mv-submit" ${(!st.item || !st.qty) ? "disabled" : ""}>SIMPAN TRANSAKSI</button>
      `;

      $("#mv-wh", content).onchange = (e) => {
        this.setWarehouse(e.target.value);
        st.item = st.from = st.to = null;
        Store.loadBundle(this.warehouseId, { includeItems: true }).finally(render);
      };
      $("#mv-item", content).onclick = async () => {
        const it = await this.pickItem();
        if (it) { st.item = it; st.qty = null; render(); }
      };
      const bindLoc = (id, key) => { const b = $("#" + id, content); if (b) b.onclick = async () => { const l = await this.pickLocator(); if (l) { st[key] = l; render(); } }; };
      bindLoc("mv-from", "from"); bindLoc("mv-to", "to");
      const clrBtn = (id, key) => { const b = $("#" + id + "-clear", content); if (b) b.onclick = (e) => { e.stopPropagation(); st[key] = null; render(); }; };
      clrBtn("mv-from", "from"); clrBtn("mv-to", "to");
      $("#mv-qty", content).onclick = async () => {
        if (!st.item) { toast("Pilih barang dulu.", "warn"); return; }
        const avail = await this.availableFor(type, st);
        const q = await openQty({ item: st.item, locator: (type === "OUTBOUND" ? (st.from && st.from.code) : null), available: avail, title: "Jumlah " + meta.title });
        if (q !== null) { st.qty = q; render(); }
      };
      $("#mv-ref", content).onchange = (e) => { st.refType = e.target.value; };
      $("#mv-refno", content).oninput = (e) => { st.refNo = e.target.value; };
      $("#mv-notes", content).oninput = (e) => { st.notes = e.target.value; };
      $("#mv-submit", content).onclick = (e) => busy(e.currentTarget, () => submit());

      // available balance hint
      const balEl = $("#mv-balance", content);
      const avail = await this.availableFor(type, st);
      if (avail !== null && st.item && (st.from || st.to)) {
        balEl.innerHTML = `<div class="banner info">${icon("info")}<div class="grow"><b>Saldo tersedia</b><span class="num">${fmt(avail)} ${esc(st.item.uom)} di ${esc((st.from || st.to).code)}</span></div></div>`;
      } else if (st.item && (st.from || st.to) && !Net.online) {
        balEl.innerHTML = `<div class="banner warn">${icon("wifioff")}<div class="grow"><span>Saldo tidak dapat dicek saat offline.</span></div></div>`;
      } else balEl.innerHTML = "";
    };

    const submit = async () => {
      const payload = {
        warehouse_id: this.warehouseId, item_id: st.item.id, qty: st.qty,
        from_locator_id: type === "INBOUND" ? null : (st.from && st.from.id),
        to_locator_id: type === "OUTBOUND" ? null : (st.to && st.to.id),
        ref_type: st.refType || null, ref_no: st.refNo || null, notes: st.notes || null,
      };
      try {
        const r = await Store.submitMovement(type, payload);
        vibrate(60);
        if (r.online) {
          toast(`${meta.title} tersimpan · ${r.result.movement_no}`, "success");
          this.showResult(r.result, type, () => { st.item = null; st.from = null; st.to = null; st.qty = null; st.refNo = ""; st.notes = ""; render(); });
        } else {
          toast("Tersimpan offline, akan dikirim otomatis.", "warn", 3200);
          App.navigate("#/m");
        }
      } catch (err) {
        toast(err.message || "Transaksi gagal disimpan", "error", 4200);
      }
    };

    render();
  },

  showResult(m, type, onAgain) {
    const m2 = openSheet(`
      <div class="center"><div style="font-size:44px;color:var(--success);">${icon("checkc")}</div>
      <h2 class="mt8">Tersimpan</h2><div class="muted">${esc(m.movement_no)}</div></div>
      <div class="card flat mt16"><div class="row between"><span class="muted">Barang</span><b>${esc(m.code)}</b></div>
      <div class="row between mt8"><span class="muted">Jumlah</span><b class="num">${fmt(m.qty)} ${esc(m.uom)}</b></div>
      <div class="row between mt8"><span class="muted">Lokator</span><b>${esc(m.from_locator_code || "")} ${m.from_locator_code && m.to_locator_code ? "→" : ""} ${esc(m.to_locator_code || "")}</b></div></div>
      <div class="actions"><button class="btn lg" data-close="true">Selesai</button><button class="btn lg primary" id="rs-again">Tambah Lagi</button></div>`);
    $("#rs-again", m2.el).onclick = () => { m2.close(); onAgain && onAgain(); };
  },

  locatorField(id, label, loc) {
    return `<div class="field"><label class="lbl">${esc(label)}</label>
      <div class="row gap8">
        <button class="btn grow ${loc ? "ghost" : "primary"}" id="${id}" style="justify-content:space-between;">
          ${loc ? `<span>${icon("pin", "i sm")} ${esc(loc.code)}</span><span class="muted">ganti</span>` : `${icon("scan")} Scan / Cari Lokator`}
        </button>
        ${loc ? `<button class="btn icon" id="${id}-clear" aria-label="Hapus">${icon("x")}</button>` : ""}
      </div></div>`;
  },

  async availableFor(type, st) {
    if (type === "INBOUND" || !st.item || !st.from) return null;
    if (!Net.online) return null;
    try {
      const r = await api("/m/stock" + qs({ warehouse_id: this.warehouseId, locator_id: st.from.id, item_id: st.item.id }));
      return (r.items && r.items.length) ? r.items[0].qty : 0;
    } catch { return null; }
  },

  /* -------------------------------------------------- pickers */
  async pickItem() {
    const whId = this.warehouseId;
    const validate = (code) => {
      const it = Store.findByCode(whId, code);
      if (!it) throw new Error("Barang tidak ditemukan.");
      const variants = Store.variantsOf(whId, it);
      if (variants.length > 1) return { variants };
      return it;
    };
    const res = await openScanner({ validate, title: "Scan Barang", hint: "Arahkan kamera ke QR / barcode barang", placeholder: "Ketik / scan kode barang", successMsg: "Barang ditemukan" });
    if (!res) return null;
    if (res.variants) return this.chooseVariant(res.variants);
    if (res.search) return this.openItemSearch();
    return res.item || null;
  },
  chooseVariant(variants) {
    return new Promise((resolve) => {
      const m = openSheet(`<h3>Pilih Satuan (UOM)</h3><p class="muted">Kode ini punya beberapa satuan.</p>
        ${variants.map((v, i) => `<button class="btn block mt8" data-v="${i}" style="justify-content:space-between;"><b>${esc(v.code)}</b><span>${esc(v.uom)} · ${esc(v.name)}</span></button>`).join("")}`,
        { onClose: () => resolve(null) });
      $$("[data-v]", m.el).forEach((b) => b.onclick = () => { const v = variants[+b.dataset.v]; m.close(); resolve(v); });
    });
  },
  openItemSearch() {
    const whId = this.warehouseId;
    return new Promise((resolve) => {
      const m = openSheet(`<h3>Cari Barang</h3>
        <div class="search mt8">${icon("search")}<input class="input" id="is-q" placeholder="Kode / nama barang" autofocus></div>
        <div id="is-list" style="max-height:55vh;overflow:auto;margin-top:8px;">${Store.itemsFor(whId).slice(0, 30).map((i) => this.itemRow(i)).join("")}</div>`,
        { onClose: () => resolve(null) });
      const list = $("#is-list", m.el);
      const paint = () => { const rows = Store.searchItems(whId, $("#is-q", m.el).value, 40); list.innerHTML = rows.length ? rows.map((i) => this.itemRow(i)).join("") : `<div class="muted p20 center">Tidak ada hasil</div>`; bind(); };
      const bind = () => $$("[data-item]", list).forEach((b) => b.onclick = () => { const it = Store.itemById(whId, +b.dataset.item); m.close(); resolve(it); });
      $("#is-q", m.el).addEventListener("input", debounce(paint, 200));
      bind();
    });
  },
  itemRow(i) { return `<button class="btn block mt8 ghost" data-item="${i.id}" style="justify-content:space-between;text-align:left;"><span><b>${esc(i.code)}</b><br><span class="muted" style="font-size:13px;">${esc(i.name)}</span></span><span class="badge">${esc(i.uom)}</span></button>`; },

  async pickLocator() {
    const whId = this.warehouseId;
    const validate = (code) => {
      const l = Store.locatorByCode(whId, code);
      if (!l) throw new Error("Lokator tidak ditemukan di gudang ini.");
      return l;
    };
    const res = await openScanner({ validate, title: "Scan Lokator", hint: "Arahkan kamera ke QR lokator / rak", placeholder: "Ketik / scan kode lokator", successMsg: "Lokator ditemukan" });
    if (!res) return null;
    if (res.search) return this.openLocatorSearch();
    return res.item || null;
  },
  openLocatorSearch() {
    const whId = this.warehouseId;
    return new Promise((resolve) => {
      const m = openSheet(`<h3>Cari Lokator</h3>
        <div class="search mt8">${icon("search")}<input class="input" id="ls-q" placeholder="Kode lokator" autofocus></div>
        <div id="ls-list" style="max-height:55vh;overflow:auto;margin-top:8px;"></div>`, { onClose: () => resolve(null) });
      const list = $("#ls-list", m.el);
      const paint = () => {
        const q = norm($("#ls-q", m.el).value);
        const rows = Store.locatorsFor(whId).filter((l) => !q || norm(l.code).includes(q)).slice(0, 60);
        list.innerHTML = rows.length ? rows.map((l) => `<button class="btn block mt8 ghost" data-loc="${l.id}" style="justify-content:space-between;"><b>${esc(l.code)}</b><span class="muted" style="font-size:13px;">${esc(l.zone || "")} ${esc(l.rack || "")}</span></button>`).join("") : `<div class="muted p20 center">Tidak ada lokator</div>`;
        $$("[data-loc]", list).forEach((b) => b.onclick = () => { const l = Store.locatorById(whId, +b.dataset.loc); m.close(); resolve(l); });
      };
      $("#ls-q", m.el).addEventListener("input", debounce(paint, 150));
      paint();
    });
  },

  /* -------------------------------------------------- STOCK OPNAME (counting) */
  async renderOpname(root) {
    await this.ensureBundle(this.warehouseId, false);
    root.innerHTML = `${this.topbar("Stock Opname")}
      <main class="m-page" id="m-content">${skeleton(3, 92)}</main>
      ${this.renderBottomNav("home")}`;
    this.wireTopbar(root);
    const content = $("#m-content", root);
    if (!Net.online) { content.innerHTML = emptyState("wifioff", "Butuh koneksi", "Daftar STO diambil dari server."); return; }
    try {
      const r = await api("/m/sto");
      const items = r.items || [];
      content.innerHTML = `<div class="sec-title">Stock Opname Aktif</div>` + (items.length
        ? items.map((s) => `<button class="card block" data-sto="${s.id}" style="text-align:left;width:100%;">
            <div class="row between"><b>${esc(s.sto_number)}</b>${stoBadge(s.status)}</div>
            <div class="muted" style="font-size:13px;">${esc(s.warehouse_code)} · ${esc(fmtDate(s.sto_date))}</div>
            <div class="row gap8 wrap mt8"><span class="badge info">${s.my_locators} lokator saya</span>
              ${s.my_todo ? `<span class="badge warning">${s.my_todo} belum selesai</span>` : `<span class="badge success">semua selesai</span>`}</div>
          </button>`).join("")
        : emptyState("checkc", "Belum ada STO", "Belum ada Stock Opname aktif untuk Anda."));
      $$("[data-sto]", content).forEach((b) => b.onclick = () => App.navigate("#/m/opname/" + b.dataset.sto));
    } catch (e) { content.innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
  },

  async renderStoLocators(root, stoId) {
    root.innerHTML = `${this.topbar("Pilih Lokator", { back: "#/m/opname" })}
      <main class="m-page" id="m-content">${skeleton(4, 72)}</main>
      ${this.renderBottomNav("home")}`;
    this.wireTopbar(root, { onBack: () => App.navigate("#/m/opname") });
    const content = $("#m-content", root);
    try {
      const d = await api("/m/sto/" + stoId);
      const locs = d.locators || [];
      content.innerHTML = `<div class="banner info">${icon("checkc")}<div class="grow"><b>${esc(d.sto_number)}</b><span>${esc(d.warehouse_code)} · ${stoBadge(d.status)}</span></div></div>
        ${locs.length ? locs.map((l) => `<button class="card block" data-sl="${l.id}" style="text-align:left;width:100%;">
            <div class="row between"><b>${icon("pin", "i sm")} ${esc(l.code)}</b>${stoBadge(l.status, STO_LOC_STATUS)}</div>
            <div class="muted" style="font-size:13px;">${l.item_count} item · ${fmt(l.total_qty)} qty${l.round > 1 ? " · putaran " + l.round : ""}</div>
          </button>`).join("") : emptyState("pin", "Tidak ada lokator", "Anda tidak ditugaskan pada STO ini.")}`;
      $$("[data-sl]", content).forEach((b) => b.onclick = () => App.navigate("#/m/opname/count/" + b.dataset.sl));
    } catch (e) { content.innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; }
  },

  async renderStoCount(root, slid) {
    await this.ensureBundle(this.warehouseId, true);
    this._count = this._count || {};
    root.innerHTML = `${this.topbar("Hitung Fisik", { back: "#/m/opname" })}
      <main class="m-page has-sticky" id="m-content">${skeleton(3, 80)}</main>
      <div class="m-sticky" id="m-sticky"></div>
      ${this.renderBottomNav("home")}`;
    this.wireTopbar(root, { onBack: () => App.navigate("#/m/opname") });
    const content = $("#m-content", root), sticky = $("#m-sticky", root);
    const load = async () => {
      if (Net.online) {
        try { this._count[slid] = await api("/m/sto/locators/" + slid); }
        catch (e) { if (!this._count[slid]) { content.innerHTML = `<div class="banner error">${icon("alert")}<div>${esc(e.message)}</div></div>`; sticky.innerHTML = ""; return; } }
      }
      this.paintStoCount(content, sticky, slid, load);
    };
    await load();
  },

  paintStoCount(content, sticky, slid, reload) {
    const d = this._count[slid];
    if (!d) { content.innerHTML = emptyState("wifioff", "Data tidak tersedia", "Sambungkan ke internet untuk memuat."); return; }
    const items = d.items || [];
    const canCount = ["NOT_STARTED", "IN_PROGRESS", "RECOUNT"].includes(d.status);
    const isChecker = Session.hasExact("CHECKER", "SUPERVISOR", "ADMIN");

    content.innerHTML = `
      <div class="banner info" style="margin-top:0;">${icon("pin")}<div class="grow"><b>${esc(d.code)}</b>
        <span>${esc(d.sto_number || "")} · ${esc(d.warehouse_code || "")} ${d.round > 1 ? "· putaran " + d.round : ""}</span></div>${stoBadge(d.status, STO_LOC_STATUS)}</div>
      ${d.recount_reason ? `<div class="banner warn">${icon("alert")}<div class="grow"><b>Perlu hitung ulang</b><span>${esc(d.recount_reason)}${d.recount_note ? " — " + esc(d.recount_note) : ""}</span></div></div>` : ""}
      <div class="row between mt8"><div class="sec-title" style="margin:0;">Hasil Hitung</div>
        <div class="muted" style="font-size:13px;">${items.length} item · ${fmt(d.total_qty)} qty</div></div>
      ${items.length ? items.map((it) => `<div class="card" style="padding:12px 14px;">
        <div class="row between"><b>${esc(it.code)}</b><span class="num" style="font-weight:700;">${fmt(it.qty)} ${esc(it.uom)}</span></div>
        <div class="row between mt8"><span class="muted" style="font-size:13px;">${esc(it.name)}${it.sheets > 1 ? " · " + it.sheets + " lembar" : ""}</span>
          ${canCount && Net.online ? `<button class="btn sm danger" data-del="${it.last_id}">${icon("trash")}</button>` : ""}</div>
      </div>`).join("") : emptyState("box", "Belum ada hitungan", "Tekan 'Tambah Barang' untuk mulai menghitung.")}`;

    if (canCount) {
      sticky.innerHTML = `<button class="btn primary lg" id="sc-add" style="flex:2;">${icon("plus")} Tambah Barang</button>
        <button class="btn lg success" id="sc-finish">${icon("checkc")} Selesai</button>`;
      $("#sc-add", sticky).onclick = async () => {
        const it = await this.pickItem();
        if (!it) return;
        const q = await openQty({ item: it, title: "Jumlah Fisik", unit: it.uom });
        if (q === null) return;
        await busy($("#sc-add", sticky), async () => {
          try {
            const r = await Store.submitCount(slid, it.id, q);
            vibrate(60);
            if (r.online) { this._count[slid] = r.result.locator; toast(`${it.code} tercatat`, "success"); this.paintStoCount(content, sticky, slid, reload); }
            else {
              const l = this._count[slid];
              const ex = (l.items || []).find((x) => x.item_id === it.id);
              if (ex) { ex.qty = Math.round((ex.qty + q) * 1000) / 1000; ex.sheets = (ex.sheets || 1) + 1; }
              else l.items = [{ item_id: it.id, code: it.code, name: it.name, uom: it.uom, qty: q, sheets: 1, last_id: 0 }].concat(l.items || []);
              l.total_qty = Math.round(((l.total_qty || 0) + q) * 1000) / 1000;
              this.paintStoCount(content, sticky, slid, reload);
            }
          } catch (e) { toast(e.message, "error"); }
        });
      };
      $("#sc-finish", sticky).onclick = async (e) => {
        if (!(await confirmDialog({ title: "Selesaikan hitungan?", body: "<p>Lokator akan dikirim ke Checker untuk diverifikasi.</p>", confirmText: "Selesai" }))) return;
        await busy(e.currentTarget, async () => {
          try {
            const r = await Store.submitFinish(slid);
            vibrate(60);
            if (r.online) { this._count[slid] = r.result.locator; toast("Terkirim ke Checker.", "success"); App.navigate("#/m/opname/" + this._count[slid].sto_id); }
            else { toast("Ditandai selesai, akan dikirim saat online.", "warn", 3200); App.navigate("#/m/opname"); }
          } catch (err) { toast(err.message, "error"); }
        });
      };
      $$("[data-del]", content).forEach((b) => b.onclick = (e) => busy(e.currentTarget, async () => {
        try { const r = await api(`/m/sto/locators/${slid}/lines/${b.dataset.del}`, { method: "DELETE" }); this._count[slid] = r.locator; this.paintStoCount(content, sticky, slid, reload); }
        catch (err) { toast(err.message, "error"); }
      }));
    } else if (d.status === "WAITING_CHECK" && isChecker) {
      sticky.innerHTML = `<button class="btn lg danger" id="sc-recount">${icon("refresh")} Hitung Ulang</button>
        <button class="btn lg success" id="sc-accept" style="flex:2;">${icon("checkc")} Terima</button>`;
      $("#sc-accept", sticky).onclick = (e) => busy(e.currentTarget, async () => {
        try { const r = await api(`/m/sto/locators/${slid}/accept`, { method: "POST", body: {} }); this._count[slid] = r.locator; toast("Diterima.", "success"); this.paintStoCount(content, sticky, slid, reload); }
        catch (err) { toast(err.message, "error"); }
      });
      $("#sc-recount", sticky).onclick = async () => {
        const reason = await promptDialog({ title: "Minta Hitung Ulang", label: "Alasan (wajib)", placeholder: "mis. Quantity tidak sesuai" });
        if (!reason) return;
        try { const r = await api(`/m/sto/locators/${slid}/recount`, { method: "POST", body: { reason, note: null } }); this._count[slid] = r.locator; toast("Hitung ulang diminta.", "warn"); this.paintStoCount(content, sticky, slid, reload); }
        catch (err) { toast(err.message, "error"); }
      };
    } else {
      sticky.innerHTML = `<button class="btn lg block" id="sc-back">Kembali</button>`;
      $("#sc-back", sticky).onclick = () => App.navigate("#/m/opname");
    }
  },

  /* -------------------------------------------------- SYNC */
  renderSync(root) {
    const paint = () => {
      const pending = Store.pending, rejected = Store.rejected;
      root.innerHTML = `${this.topbar("Sinkronisasi")}
        <main class="m-page">
          <div class="card"><div class="row between"><div><div class="lbl">STATUS</div><h3>${Net.online ? '<span class="net">ONLINE</span>' : '<span class="net off">OFFLINE</span>'}</h3></div>
            <button class="btn sm" id="sy-flush">${icon("refresh")} Sync Sekarang</button></div>
            <div class="mt16 pt12 col" style="border-top:1px solid var(--border);">
              <div class="row between"><span class="muted">Menunggu kirim</span><b class="num">${pending.length}</b></div>
              <div class="row between"><span class="muted">Ditolak</span><b class="num" style="color:${rejected.length ? "var(--error)" : "inherit"}">${rejected.length}</b></div>
              <div class="row between"><span class="muted">Terakhir sinkron</span><span>${fmtDate(Store.lastSynced)}</span></div>
            </div>
          </div>
          ${rejected.length ? `<div class="row gap8 mt8"><button class="btn grow" id="sy-retry">${icon("refresh")} Kirim Ulang</button><button class="btn grow danger" id="sy-discard">${icon("trash")} Buang Ditolak</button></div>` : ""}
          <div class="sec-title">Antrean</div>
          ${Store.queue.length ? Store.queue.map((t) => `<div class="card" style="padding:12px 14px;">
            <div class="row between"><div class="row gap8 items-center">${moveBadge(t.txn_type)}${t.sync_status === "REJECTED" ? '<span class="badge error">Ditolak</span>' : '<span class="badge warning">Menunggu</span>'}</div><span class="muted" style="font-size:12px;">${fmtDate(t.timestamp)}</span></div>
            <div class="mt8">${esc((t.payload && t.payload.item_id) ? ("Item #" + t.payload.item_id) : "")} · qty ${fmt(t.payload && t.payload.qty)}</div>
            ${t.message ? `<div class="banner error mt8" style="margin:8px 0 0;">${icon("alert")}<div>${esc(t.message)}</div></div>` : ""}
          </div>`).join("") : emptyState("checkc", "Antrean kosong", "Semua transaksi sudah terkirim.")}
        </main>${this.renderBottomNav("home")}`;
      this.wireTopbar(root);
      const f = $("#sy-flush", root); if (f) f.onclick = (e) => busy(e.currentTarget, () => Store.flush().then(paint));
      const rt = $("#sy-retry", root); if (rt) rt.onclick = (e) => busy(e.currentTarget, () => Store.retryRejected().then(paint));
      const dc = $("#sy-discard", root); if (dc) dc.onclick = async () => { if (await confirmDialog({ title: "Buang transaksi ditolak?", body: "<p>Transaksi yang ditolak server akan dihapus dari perangkat.</p>", confirmText: "Buang", danger: true })) { await Store.discardRejected(); paint(); } };
    };
    paint();
  },

  /* -------------------------------------------------- PROFILE */
  async renderMe(root) {
    const u = Session.user;
    root.innerHTML = `${this.topbar("Akun")}
      <main class="m-page">
        <div class="card"><div class="row gap12 items-center"><div class="logo-mark">${icon("user")}</div>
          <div class="grow"><b>${esc(u.full_name)}</b><div class="muted">@${esc(u.username)}</div>
          <div class="row gap8 wrap mt8">${(u.roles || []).map((r) => `<span class="badge info">${esc(r)}</span>`).join("")}</div></div></div></div>

        <div class="card"><div class="lbl">STATUS SINKRONISASI</div>
          <div class="row between mt8"><span>${Net.online ? '<span class="net">ONLINE</span>' : '<span class="net off">OFFLINE</span>'}</span><a href="#/m/sync" class="btn sm">${Store.pending.length} menunggu</a></div></div>

        ${Session.hasExact("ADMIN", "SUPERVISOR", "CHECKER") ? `<div class="card flat" style="border:1px dashed var(--border-strong);">
          <div class="row between"><div><strong>Tampilan Desktop</strong><p class="muted" style="font-size:13px;">Dashboard, laporan, master data</p></div>
          <a href="#/d/dashboard" class="btn sm primary">Buka</a></div></div>` : ""}

        <button class="btn block mt16" id="me-pw">${icon("cog")} Ubah Password</button>
        <button class="btn lg block danger mt8" id="me-logout">${icon("logout")} Logout</button>
      </main>${this.renderBottomNav("me")}`;
    this.wireTopbar(root);
    $("#me-pw", root).onclick = () => this.changePassword();
    $("#me-logout", root).onclick = async () => {
      if (await confirmDialog({ title: "Logout?", body: "<p>Anda akan keluar dari aplikasi.</p>", confirmText: "Logout", danger: true })) {
        api("/auth/logout", { method: "POST" }).catch(() => {}); Session.clear(); App.navigate("#/login");
      }
    };
  },
  async changePassword() {
    const m = openSheet(`<h3>Ubah Password</h3>
      <div class="field mt8"><label class="lbl">Password Lama</label><input type="password" class="input" id="pw-old"></div>
      <div class="field"><label class="lbl">Password Baru (min 6)</label><input type="password" class="input" id="pw-new"></div>
      <div class="actions"><button class="btn lg" data-close="true">Batal</button><button class="btn lg primary" id="pw-ok">Simpan</button></div>`);
    $("#pw-ok", m.el).onclick = (e) => busy(e.currentTarget, async () => {
      try { await api("/auth/change-password", { method: "POST", body: { old_password: $("#pw-old", m.el).value, new_password: $("#pw-new", m.el).value } }); toast("Password diperbarui."); m.close(); }
      catch (err) { toast(err.message, "error"); }
    });
  },
};
