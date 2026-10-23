const CACHE_NAME = "ndn-static-v7";
const STATIC_ASSETS = [
  "/static/offline.html",
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/pwa.js",
  "/static/js/offline-store.js",
  "/static/js/offline.js",
  "/static/images/secondary-douala.svg",
  "/static/images/ndn-app-icon.svg",
  "/static/images/ndn-app-icon-192.png",
  "/static/images/ndn-app-icon-512.png",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key.startsWith("ndn-") && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            event.waitUntil(
              caches.open(CACHE_NAME).then((cache) => cache.put(request, response.clone()))
            );
          }
          return response;
        });
      })
    );
    return;
  }

  if (url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const offline = await caches.match("/static/offline.html");
        return offline || Response.error();
      })
    );
  }
});
