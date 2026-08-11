const CACHE = "tgs3-shell-v1";
const SHELL = [
  "/mobile",
  "/mobile/mobile.css",
  "/mobile/mobile.js",
  "/mobile/manifest.webmanifest",
  "/mobile/icons/icon-192.png",
  "/mobile/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.pathname.startsWith("/files") || url.pathname.startsWith("/folders") || url.pathname.startsWith("/mobile")) {
    event.respondWith(
      fetch(event.request).then((response) => {
        if (response.ok && url.pathname.startsWith("/mobile")) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      }).catch(() => caches.match(event.request).then((hit) => hit || caches.match("/mobile")))
    );
    return;
  }
  event.respondWith(caches.match(event.request).then((hit) => hit || fetch(event.request)));
});
