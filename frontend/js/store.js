/* Offline store for the WMS mobile flow.
   - Caches warehouses, locators and the item master (per warehouse) in IndexedDB.
   - Queues inbound / outbound / transfer movements locally with a unique txn id,
     then syncs them to /api/m/sync (idempotent, ordered by timestamp).
   Works the same online and offline. */
const Store = {
  db: null,
  warehouses: [],
  items: {},        // warehouse_id (or "all") -> [items]
  locators: {},     // warehouse_id -> [locators]
  queue: [],
  syncing: false,
  lastSynced: null,
  listeners: [],
  on(eventOrCallback, maybeCallback) {
    if (typeof eventOrCallback === "function") this.listeners.push({ event: "*", fn: eventOrCallback });
    else if (typeof maybeCallback === "function") this.listeners.push({ event: eventOrCallback, fn: maybeCallback });
  },
  off(eventOrCallback, maybeCallback) {
    this.listeners = this.listeners.filter((item) => {
      if (typeof eventOrCallback === "function") return item.fn !== eventOrCallback;
      if (typeof maybeCallback === "function") return !(item.event === eventOrCallback && item.fn === maybeCallback);
      return item.event !== eventOrCallback;
    });
  },
  emit(kind, data) {
    this.listeners.forEach((item) => {
      try { if (item.event === "*" || item.event === kind) item.fn(data, kind); }
      catch (e) { console.error("Store listener error:", e); }
    });
  },

  /* ---- IndexedDB helpers ---- */
  open(userId) {
    return new Promise((resolve) => {
      if (!window.indexedDB) return resolve(null);
      const req = indexedDB.open("wms-offline-" + userId, 1);
      req.onupgradeneeded = () => { const d = req.result; if (!d.objectStoreNames.contains("kv")) d.createObjectStore("kv", { keyPath: "k" }); if (!d.objectStoreNames.contains("queue")) d.createObjectStore("queue", { keyPath: "txn_id" }); };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    });
  },
  _tx(store, mode, fn) {
    if (!this.db) return Promise.resolve();
    return new Promise((res) => { const t = this.db.transaction(store, mode); const r = fn(t.objectStore(store)); t.oncomplete = () => res(r && r.result); t.onerror = () => res(); });
  },
  put(store, v) { return this._tx(store, "readwrite", (s) => s.put(v)); },
  del(store, k) { return this._tx(store, "readwrite", (s) => s.delete(k)); },
  getAll(store) { return this._tx(store, "readonly", (s) => s.getAll()); },

  async init() {
    const u = Session.user;
    this.db = await this.open(u.id);
    this.warehouses = []; this.items = {}; this.locators = {}; this.queue = [];
    const kv = (await this.getAll("kv")) || [];
    kv.forEach((r) => {
      if (r.k === "warehouses") this.warehouses = r.v;
      else if (r.k.startsWith("items:")) this.items[r.k.slice(6)] = r.v;
      else if (r.k.startsWith("locators:")) this.locators[r.k.slice(9)] = r.v;
      else if (r.k === "lastSynced") this.lastSynced = r.v;
    });
    this.queue = ((await this.getAll("queue")) || []).sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    Net.on((on) => { if (on) this.flush(); this.emit("net"); });
    window.addEventListener("online", () => this.flush());
    if (Net.online) this.flush();
    this.emit("init");
  },
  get pending() { return this.queue.filter((t) => t.sync_status === "PENDING"); },
  get rejected() { return this.queue.filter((t) => t.sync_status === "REJECTED"); },

  /* ---- master bundle ---- */
  async loadBundle(warehouseId, { force = false, includeItems = true } = {}) {
    warehouseId = Number(warehouseId) || null;
    if (Net.online) {
      try {
        if (this.pending.length) await this.flush();
        const key = warehouseId || "all";
        const needItems = includeItems && (force || !this.items[key]);
        const b = await api("/m/bundle" + qs({ warehouse_id: warehouseId, include_items: needItems ? 1 : 0 }));
        this.warehouses = b.warehouses || [];
        if (warehouseId) this.locators[warehouseId] = b.locators || [];
        if (needItems && b.items) this.items[key] = b.items;
        await this.put("kv", { k: "warehouses", v: this.warehouses });
        if (warehouseId) await this.put("kv", { k: "locators:" + warehouseId, v: this.locators[warehouseId] });
        if (needItems && b.items) await this.put("kv", { k: "items:" + key, v: this.items[key] });
        this.emit("bundle", warehouseId);
      } catch (e) { if (!e.offline) throw e; }
    }
    return { warehouses: this.warehouses, locators: warehouseId ? (this.locators[warehouseId] || []) : [], items: this.items[warehouseId || "all"] || [] };
  },
  itemsFor(warehouseId) { return this.items[warehouseId || "all"] || []; },
  locatorsFor(warehouseId) { return this.locators[warehouseId] || []; },
  warehouse(id) { return this.warehouses.find((w) => Number(w.id) === Number(id)) || null; },
  locatorById(warehouseId, id) { return (this.locators[warehouseId] || []).find((l) => Number(l.id) === Number(id)) || null; },
  locatorByCode(warehouseId, code) {
    const c = norm(code);
    return (this.locators[warehouseId] || []).find((l) => norm(l.code) === c) || null;
  },
  itemById(warehouseId, id) { return this.itemsFor(warehouseId).find((i) => Number(i.id) === Number(id)) || null; },
  findByCode(warehouseId, code) {
    const c = norm(code);
    const list = this.itemsFor(warehouseId);
    return list.find((i) => norm(i.qr_code) === c) || list.find((i) => norm(i.code) === c) || list.find((i) => i.barcode && norm(i.barcode) === c) || null;
  },
  variantsOf(warehouseId, item) {
    if (!item) return [];
    const c = norm(item.code);
    return this.itemsFor(warehouseId).filter((i) => norm(i.code) === c);
  },
  searchItems(warehouseId, q, limit = 40) {
    const toks = norm(q).split(/\s+/).filter(Boolean);
    const list = this.itemsFor(warehouseId);
    if (!toks.length) return list.slice(0, limit);
    return list.filter((i) => { const hay = `${i.code} ${i.name} ${i.barcode || ""}`.toLowerCase(); return toks.every((t) => hay.includes(t)); }).slice(0, limit);
  },

  /* ---- movement queue ---- */
  async _enqueue(channel, txn_type, payload) {
    const t = { txn_id: uuid(), txn_type, channel, payload, timestamp: new Date().toISOString(), device_id: Session.deviceId,
      user_id: Session.user.id, sync_status: "PENDING" };
    this.queue.push(t);
    await this.put("queue", t);
    this.emit("queue");
    if (Net.online) this.flush(); else this.emit("saved-offline");
    return t;
  },
  async enqueueMovement(txn_type, payload) { return this._enqueue("movement", txn_type, payload); },
  async submitMovement(txn_type, payload) {
    /* Online: try direct endpoint for instant validation/feedback; fall back to queue. */
    const txn_id = uuid();
    const body = { ...payload, txn_id, device_id: Session.deviceId };
    if (Net.online) {
      try {
        const res = await api("/m/" + txn_type.toLowerCase(), { method: "POST", body });
        this.emit("saved-online", res);
        return { online: true, result: res };
      } catch (e) {
        if (!e.offline) throw e;  // real validation error -> surface it
      }
    }
    const t = await this.enqueueMovement(txn_type, payload);
    return { online: false, queued: t };
  },

  /* ---- Stock Opname counting queue ---- */
  async submitCount(slId, itemId, qty) {
    const txn_id = uuid();
    const body = { item_id: itemId, qty, txn_id };
    if (Net.online) {
      try { return { online: true, result: await api(`/m/sto/locators/${slId}/lines`, { method: "POST", body }) }; }
      catch (e) { if (!e.offline) throw e; }
    }
    return { online: false, queued: await this._enqueue("sto", "STO_COUNT", { sto_locator_id: slId, item_id: itemId, qty }) };
  },
  async submitFinish(slId) {
    if (Net.online) {
      try { return { online: true, result: await api(`/m/sto/locators/${slId}/finish`, { method: "POST", body: {} }) }; }
      catch (e) { if (!e.offline) throw e; }
    }
    return { online: false, queued: await this._enqueue("sto", "STO_FINISH", { sto_locator_id: slId }) };
  },

  async flush() {
    if (this.syncing || !this.pending.length || !Net.online || !Session.token) return;
    this.syncing = true; this.emit("syncing");
    try {
      let ok = 0; const rej = [];
      const groups = { movement: [], sto: [] };
      for (const t of this.pending) (t.channel === "sto" ? groups.sto : groups.movement).push(t);
      for (const [channel, list] of Object.entries(groups)) {
        if (!list.length) continue;
        const path = channel === "sto" ? "/m/sto/sync" : "/m/sync";
        const batch = list.slice(0, 200);
        const r = await api(path, { method: "POST", body: { transactions: batch.map(({ txn_id, txn_type, payload, timestamp, device_id }) => ({ txn_id, txn_type, payload, timestamp, device_id })) } });
        for (const res of r.results) {
          const t = this.queue.find((x) => x.txn_id === res.txn_id); if (!t) continue;
          if (res.result === "OK" || res.result === "DUPLICATE") { if (res.result === "OK") ok++; this.queue.splice(this.queue.indexOf(t), 1); await this.del("queue", t.txn_id); }
          else { t.sync_status = "REJECTED"; t.message = res.message; rej.push(res.message); await this.put("queue", t); }
        }
      }
      this.syncing = false;
      if (ok) { this.lastSynced = new Date().toISOString(); await this.put("kv", { k: "lastSynced", v: this.lastSynced }); }
      this.emit("synced", { ok, rejected: rej });
      if (this.pending.length) this.flush();
    } catch (e) {
      this.syncing = false; this.emit("sync-failed", e);
    }
  },
  async discardRejected() {
    for (const t of this.rejected) { this.queue.splice(this.queue.indexOf(t), 1); await this.del("queue", t.txn_id); }
    this.emit("queue");
  },
  async retryRejected() {
    for (const t of this.rejected) { t.sync_status = "PENDING"; delete t.message; await this.put("queue", t); }
    this.emit("queue");
    if (Net.online) this.flush();
  },
};
const norm = (s) => String(s || "").trim().toLowerCase();
