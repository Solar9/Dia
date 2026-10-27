// Dia's service worker: makes the UI installable and opens it without a
// network (the app shell only). The API and live updates are never cached.
const CACHE = "dia-shell-v4";
const SHELL = [
  "/", "/static/app.js", "/static/style.css", "/static/themes/dark.css",
  "/static/themes/light.css", "/static/themes/midnight.css",
  "/static/vendor/preact.module.js", "/static/vendor/hooks.module.js",
  "/static/vendor/htm.module.js", "/static/vendor/prism.bundle.js",
  "/static/icons/icon-192.png",
  "/static/icons/dia.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Network first, so an updated Dia is used at once; the cache only when offline.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/ws") return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then((hit) => hit || caches.match("/"))),
  );
});

// Notifications from `dia serve` (Web Push), shown even when the app is closed.
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data?.text() }; }
  event.waitUntil(self.registration.showNotification(data.title || "Dia", {
    body: data.body || "",
    tag: data.tag || undefined,
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/badge-96.png",
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ("focus" in client) { client.navigate(url).catch(() => {}); return client.focus(); }
      }
      return self.clients.openWindow(url);
    }),
  );
});
