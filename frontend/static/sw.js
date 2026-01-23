const CACHE_NAME = "knowledge-assistant-v1";
const ASSETS_TO_CACHE = [
  "/",
  "/static/css/variables.css",
  "/static/css/base.css",
  "/static/css/layout.css",
  "/static/css/components.css",
  "/static/app.js",
  "/static/img/logo.png",
  "/static/img/favicon.ico",
];

// Install event: cache static assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    }),
  );
  self.skipWaiting();
});

// Activate event: enable navigation preload
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      if (self.registration.navigationPreload) {
        // Enable navigation preload
        await self.registration.navigationPreload.enable();
      }

      // Clean up old caches
      const cacheNames = await caches.keys();
      await Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        }),
      );
    })(),
  );
  self.clients.claim();
});

// Fetch event: handle navigation preload properly
self.addEventListener("fetch", (event) => {
  // Only handle navigation requests
  if (event.request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          // 1. Try to use the navigation preload response if available
          const preloadResponse = await event.preloadResponse;
          if (preloadResponse) {
            return preloadResponse;
          }

          // 2. Fallback to network
          const networkResponse = await fetch(event.request);
          return networkResponse;
        } catch (error) {
          console.error("Fetch failed; returning offline page instead.", error);

          // 3. Fallback to cache for the shell / index
          const cache = await caches.open(CACHE_NAME);
          const cachedResponse = await cache.match("/");
          return cachedResponse || Response.error();
        }
      })(),
    );
  }
});
