/* Reusable QR scanner. BarcodeDetector when available, jsQR fallback (bundled, works offline).
   openScanner({ validate }) -> Promise<{item}|{search:true}|{newItemCode:string}|null>
   validate(code) must return an item or throw Error(message). */
let _jsqrPromise;
function loadJsQR() {
  if (window.jsQR) return Promise.resolve(window.jsQR);
  return (_jsqrPromise ||= new Promise((res, rej) => { const s = document.createElement("script"); s.src = "/vendor/jsQR.js"; s.onload = () => res(window.jsQR); s.onerror = rej; document.head.appendChild(s); }));
}

function openScanner({ validate, hint = "Arahkan kamera ke QR item", title = "Scan QR", placeholder = "Atau ketik / scan kode item", successMsg = "Item ditemukan", search = true, searchLabel = "Search Item", allowNewItem = false }) {
  return new Promise(async (resolve) => {
    const ov = document.createElement("div");
    ov.className = "scanner";
    ov.innerHTML = `<video playsinline muted></video>
      <div class="bar"><button class="btn icon ghost" id="sc-close" style="color:#fff" aria-label="Tutup">${icon("x")}</button><strong>${esc(title)}</strong>
        <button class="btn icon ghost" id="sc-torch" style="color:#fff" aria-label="Senter">${icon("flash")}</button></div>
      <div class="frame" id="sc-frame"></div>
      <div class="foot"><div id="sc-msg" class="hint">${esc(hint)}</div>
        <div id="sc-new-item-wrap" style="display:none;margin-bottom:8px;">
          <button class="btn primary block" id="sc-new-item-btn" type="button" style="background:#f59e0b;border-color:#f59e0b;color:#fff;font-weight:700;">
            ${icon("plus")} Daftarkan Item Baru
          </button>
        </div>
        <form class="manual" id="sc-form"><input class="input" id="sc-code" placeholder="${esc(placeholder)}" autocomplete="off" autocapitalize="characters" style="color:#000 !important;background:#fff !important;font-weight:600;">
          <button class="btn primary" type="submit">OK</button></form>
        ${search ? `<button class="btn block" id="sc-search" type="button">${icon("search")}${esc(searchLabel)}</button>` : ""}</div>`;
    document.body.appendChild(ov);
    const video = $("video", ov), frame = $("#sc-frame", ov), msg = $("#sc-msg", ov);
    const newItemWrap = $("#sc-new-item-wrap", ov), newItemBtn = $("#sc-new-item-btn", ov);
    let stream, raf, stopped = false, last = "", lastAt = 0, busy_ = false, detector = null, lastFailedCode = "";

    const stop = (result) => {
      if (stopped) return; stopped = true; cancelAnimationFrame(raf);
      if (stream) stream.getTracks().forEach((t) => t.stop());
      ov.remove(); resolve(result);
    };
    const showMsg = (text, err) => { msg.className = err ? "msg" : "hint"; msg.textContent = text; };
    const handle = async (code) => {
      if (busy_ || !code) return; busy_ = true;
      const cleanCode = code.trim();
      try {
        const item = await validate(cleanCode);
        if (newItemWrap) newItemWrap.style.display = "none";
        frame.classList.add("ok"); vibrate(60); showMsg(successMsg);
        setTimeout(() => stop({ item }), 120);
      } catch (e) {
        vibrate([40, 60, 40]); showMsg(e.message || "QR tidak dikenali.", true);
        if (allowNewItem && cleanCode && newItemWrap && newItemBtn) {
          lastFailedCode = cleanCode.toUpperCase();
          newItemBtn.innerHTML = `${icon("plus")} Tambah Barang Baru (${esc(lastFailedCode)})`;
          newItemWrap.style.display = "block";
        }
        setTimeout(() => { if (!stopped) { showMsg(hint); busy_ = false; } }, 2200);
      }
    };
    $("#sc-close", ov).onclick = () => stop(null);
    if (newItemBtn) {
      newItemBtn.onclick = () => stop({ newItemCode: lastFailedCode });
    }
    const sBtn = $("#sc-search", ov);
    if (sBtn) sBtn.onclick = () => stop({ search: true });
    $("#sc-form", ov).onsubmit = (e) => { e.preventDefault(); const v = $("#sc-code", ov).value; $("#sc-code", ov).value = ""; handle(v); };
    $("#sc-torch", ov).onclick = async () => {
      try { const tr = stream.getVideoTracks()[0]; const on = !tr._torch; await tr.applyConstraints({ advanced: [{ torch: on }] }); tr._torch = on; } catch { toast("Senter tidak didukung perangkat ini.", "warn"); }
    };

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showMsg("Kamera memerlukan HTTPS / localhost. Gunakan input kode atau Search Item.", true); return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } }, audio: false });
      video.srcObject = stream; await video.play();
    } catch (e) {
      showMsg(e.name === "NotAllowedError" ? "Izin kamera ditolak. Aktifkan izin kamera atau gunakan Search Item." : "Kamera tidak dapat dibuka. Gunakan input kode atau Search Item.", true);
      return;
    }
    if ("BarcodeDetector" in window) { try { detector = new BarcodeDetector({ formats: ["qr_code", "code_128", "ean_13", "code_39"] }); } catch {} }
    const canvas = document.createElement("canvas"), ctx = canvas.getContext("2d", { willReadFrequently: true });
    let jsqr = null; if (!detector) jsqr = await loadJsQR().catch(() => null);
    const tick = async () => {
      if (stopped) return;
      if (!busy_ && video.readyState >= 2) {
        try {
          let code = "";
          if (detector) { const r = await detector.detect(video); if (r.length) code = r[0].rawValue; }
          else if (jsqr) {
            const w = 480, h = Math.round(480 * video.videoHeight / video.videoWidth) || 360; canvas.width = w; canvas.height = h;
            ctx.drawImage(video, 0, 0, w, h); const d = ctx.getImageData(0, 0, w, h); const q = jsqr(d.data, w, h, { inversionAttempts: "dontInvert" }); if (q) code = q.data;
          }
          const now = Date.now();
          if (code && (code !== last || now - lastAt > 2500)) { last = code; lastAt = now; handle(code); }
        } catch {}
      }
      raf = requestAnimationFrame(() => setTimeout(tick, 90));
    };
    tick();
  });
}
