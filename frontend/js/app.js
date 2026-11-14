/* ===========================================================
   APP ROUTER & BOOTSTRAPPER
   - Loads app config (name from server)
   - Login page with demo credentials
   - Hash router with role & device detection
   - PWA service worker registration
   =========================================================== */

const App = {
  root: null,
  config: { app_name: "WMS", app_subtitle: "Warehouse Management System", demo_mode: true },

  async init() {
    this.root = document.getElementById("app");
    window.addEventListener("hashchange", () => this.route());
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

    try {
      this.config = { ...this.config, ...(await api("/auth/config")) };
      window.APP_NAME = this.config.app_name;
      window.APP_SUBTITLE = this.config.app_subtitle;
      document.title = this.config.app_name + " — " + this.config.app_subtitle;
    } catch { }

    if (Session.user) await Store.init().catch(() => {});
    this.route();
  },

  navigate(hash) { if (location.hash === hash) this.route(); else location.hash = hash; },
  isMobileDevice() { return window.innerWidth < 820; },

  async route() {
    const raw = location.hash || "";
    const clean = raw.split("?")[0];

    if (!Session.token || !Session.user) { this.renderLogin(); return; }

    if (!clean || clean === "#" || clean === "#/") {
      const u = Session.user;
      const desktop = Session.hasExact("SUPERVISOR", "CHECKER", "ADMIN");
      if (u.roles.includes("MH") && !desktop) this.navigate("#/m");
      else if (this.isMobileDevice()) this.navigate("#/m");
      else this.navigate("#/d/dashboard");
      return;
    }

    try {
      if (clean === "#/m") await Mobile.renderHome(this.root);
      else if (clean === "#/m/stock") await Mobile.renderStock(this.root);
      else if (clean === "#/m/inbound") await Mobile.renderMovement(this.root, "INBOUND");
      else if (clean === "#/m/outbound") await Mobile.renderMovement(this.root, "OUTBOUND");
      else if (clean === "#/m/transfer") await Mobile.renderMovement(this.root, "TRANSFER");
      else if (clean === "#/m/opname") await Mobile.renderOpname(this.root);
      else if (clean.startsWith("#/m/opname/count/")) await Mobile.renderStoCount(this.root, clean.split("/").pop());
      else if (clean.startsWith("#/m/opname/")) await Mobile.renderStoLocators(this.root, clean.split("/").pop());
      else if (clean === "#/m/sync") Mobile.renderSync(this.root);
      else if (clean === "#/m/me") await Mobile.renderMe(this.root);
      else if (clean === "#/d/dashboard") await Desktop.renderDashboard(this.root);
      else if (clean === "#/d/movements") await Desktop.renderMovements(this.root);
      else if (clean === "#/d/stock") await Desktop.renderStock(this.root);
      else if (clean === "#/d/sto") await Desktop.renderSto(this.root);
      else if (clean.startsWith("#/d/sto/")) await Desktop.renderStoDetail(this.root, clean.split("/").pop());
      else if (clean === "#/d/corrections") await Desktop.renderCorrections(this.root);
      else if (clean === "#/d/problems") await Desktop.renderProblems(this.root);
      else if (clean === "#/d/warehouses") await Desktop.renderWarehouses(this.root);
      else if (clean === "#/d/locators") await Desktop.renderLocators(this.root);
      else if (clean === "#/d/items") await Desktop.renderItems(this.root);
      else if (clean === "#/d/imports") await Desktop.renderImports(this.root);
      else if (clean === "#/d/reports") await Desktop.renderReports(this.root);
      else if (clean === "#/d/users") await Desktop.renderUsers(this.root);
      else if (clean === "#/d/audit") await Desktop.renderAudit(this.root);
      else this.navigate("#/m");
    } catch (e) {
      console.error("Routing error:", e);
      toast(e.message || "Gagal membuka halaman", "error");
    }
  },

  renderLogin() {
    const c = this.config;
    this.root.innerHTML = `
      <div class="login"><div class="login-card">
        <div class="logo"><div class="logo-mark">${icon("box")}</div>
          <div><div style="font-size:22px;font-weight:800;letter-spacing:-.03em;">${esc(c.app_name)}</div>
          <div class="muted" style="font-size:13px;">${esc(c.app_subtitle)}</div></div></div>

        <form class="col mt24" id="form-login">
          <div class="field"><label class="lbl">Username</label>
            <input type="text" class="input" name="username" id="login-user" required placeholder="Masukkan username" autofocus></div>
          <div class="field"><label class="lbl">Password</label>
            <input type="password" class="input" name="password" id="login-pass" required placeholder="••••••••" value="demo1234"></div>
          <button class="btn primary lg block mt8" type="submit" id="btn-login-submit">MASUK</button>
        </form>

        <div class="demo-users" id="login-demo-users">
          <div><strong>Akun Demo (klik untuk isi cepat):</strong></div>
          <div class="chips">
            <button class="chip" data-u="admin">Admin</button>
            <button class="chip" data-u="supervisor01">Supervisor</button>
            <button class="chip" data-u="checker01">Checker</button>
            <button class="chip" data-u="mh01">MH 1</button>
            <button class="chip" data-u="mh02">MH 2</button>
          </div>
          <div class="muted mt8" style="font-size:12px;">Default password: <code>demo1234</code></div>
        </div>
      </div></div>`;

    if (c.demo_mode === false) { const box = $("#login-demo-users", this.root); if (box) box.style.display = "none"; }

    $$(".demo-users .chip", this.root).forEach((ch) => ch.onclick = () => {
      $("#login-user", this.root).value = ch.dataset.u;
      $("#login-pass", this.root).value = "demo1234";
      $("#btn-login-submit", this.root).click();
    });

    const form = $("#form-login", this.root);
    form.onsubmit = async (e) => {
      e.preventDefault();
      const u = $("#login-user", form).value.trim(), p = $("#login-pass", form).value, btn = $("#btn-login-submit", form);
      await busy(btn, async () => {
        try {
          const res = await api("/auth/login", { method: "POST", body: { username: u, password: p, device_id: Session.deviceId } });
          Session.set(res.token, res.user);
          await Store.init().catch(() => {});
          toast(`Selamat datang, ${res.user.full_name}!`, "success");
          const desktop = res.user.roles.some((r) => ["SUPERVISOR", "CHECKER", "ADMIN"].includes(r));
          if (!desktop || this.isMobileDevice()) this.navigate("#/m"); else this.navigate("#/d/dashboard");
        } catch (err) { toast(err.message, "error"); }
      });
    };
  },
};

window.addEventListener("DOMContentLoaded", () => App.init());
