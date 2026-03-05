const CACHE_NAME = "rr-cache-v1";

const urlsToCache = [
  "/",
  "/login",
  "/static/favicon.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        console.log("Cache opened");
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener("fetch", function(event) {
  event.respondWith(
    caches.match(event.request)
      .then(function(response) {
        return response || fetch(event.request);
      })
  );
});
