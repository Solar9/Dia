// Dia's service worker: makes the UI installable and opens it without a
// network (the app shell only). The API and live updates are never cached.
const CACHE = "dia-shell-v32";
const SHELL = [
  "/", "/static/app.js", "/static/style.css", "/static/themes/dark.css",
  "/static/themes/light.css", "/static/themes/midnight.css",
  "/static/vendor/preact.module.js", "/static/vendor/hooks.module.js",
  "/static/vendor/htm.module.js", "/static/vendor/prism.bundle.js",
  "/static/icons/icon-192.png",
  "/static/icons/dia.svg",
  // the app's ES modules (kept in step with static/js by tests/test_ui_package.py)
  "/static/js/api.js",
  "/static/js/html.js",
  "/static/js/i18n.js",
  "/static/js/lang/de.js",
  "/static/js/lang/es.js",
  "/static/js/lang/fr.js",
  "/static/js/lang/index.js",
  "/static/js/lang/it.js",
  "/static/js/lang/pt.js",
  "/static/js/ui/charts.js",
  "/static/js/ui/code.js",
  "/static/js/ui/dialog.js",
  "/static/js/ui/diff.js",
  "/static/js/ui/icons.js",
  "/static/js/ui/login.js",
  "/static/js/ui/logo.js",
  "/static/js/ui/palette.js",
  "/static/js/ui/resource.js",
  "/static/js/ui/richtext.js",
  "/static/js/ui/splitter.js",
  "/static/js/ui/window.js",
  "/static/js/util.js",
  "/static/js/views/chat.js",
  "/static/js/views/cli.js",
  "/static/js/views/inbox.js",
  "/static/js/views/memory.js",
  "/static/js/views/missions.js",
  "/static/js/views/settings.js",
  "/static/js/views/settings_devices.js",
  "/static/js/views/settings_forms.js",
  "/static/js/views/status.js",
  "/static/js/views/status_summary.js",
  "/static/js/views/tasks.js",
  "/static/js/views/usage.js",
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
