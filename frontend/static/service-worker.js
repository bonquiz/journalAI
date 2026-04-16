const CACHE = "journalai-v1";
const ASSETS = ["/", "/favicon.png", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never cache API requests — auth cookies + real-time data.
  if (url.pathname.startsWith("/api/")) return;
  // Only handle GETs for same-origin static assets.
  if (e.request.method !== "GET" || url.origin !== self.location.origin) return;
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
