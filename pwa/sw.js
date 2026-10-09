'use strict';
const CACHE = 'ean-skener-v3';
const SHELL = ['./', 'index.html', 'app.js', 'style.css', 'manifest.webmanifest',
  'icons/icon-192.png', 'icons/apple-touch-icon.png'];
const VENDOR = ['vendor/barcode-detector.js', 'vendor/zxing_reader.wasm'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL.concat(VENDOR))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  const path = url.pathname.replace(/^\//, '');
  // knihovna čtečky se nemění => z cache
  if (VENDOR.includes(path)) {
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
    return;
  }
  // aplikace => vždy nejnovější z PC, cache jen pro rychlé otevření bez spojení
  if (SHELL.includes(path) || path === '') {
    e.respondWith(fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
      return res;
    }).catch(() => caches.match(e.request, { ignoreSearch: true })));
  }
});
