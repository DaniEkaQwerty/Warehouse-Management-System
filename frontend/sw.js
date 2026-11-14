/* WMS Service Worker - App shell caching for warehouse offline usage */
const CACHE_NAME = "wms-shell-v28";
const ASSETS = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/css/app.css",
  "/vendor/jsQR.js",
  "/vendor/qrcode.js",
  "/js/api.js",
  "/js/ui.js",
  "/js/store.js",
  "/js/scanner.js",
  "/js/mobile.js",
  "/js/desktop.js",
  "/js/app.js"
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)))).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // API handled by app (offline queue)

  // Network-first with cache fallback so code updates are never stale
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res && res.status === 200 && res.type === "basic") {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
