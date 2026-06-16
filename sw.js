// JARVIS Holo PWA Service Worker (narrative-forge PWA)
// Caches data/JSONs + basic holo.html for full offline support of the holographic neural map (loadAndParse real data).
// Pretrained PWA patterns: separate shell/data/api caches, cache-first for JSONs (offline first for holo viz), network-first APIs, offline fallback JSONs with rule42 note.
// Basic holo: cached core UI + data; Three.js CDN will gracefully degrade or use prior cached if visited.
// Advanced: cache-first for known assets, network fallback, offline shell + provenance hints.

const CACHE_VERSION = 'jarvis-holo-pwa-v3';
const SHELL_CACHE = `jarvis-holo-shell-${CACHE_VERSION}`;
const DATA_CACHE = `jarvis-holo-data-${CACHE_VERSION}`;
const API_CACHE = `jarvis-holo-api-${CACHE_VERSION}`;

const PRECACHE_ASSETS = [
  './neural-map-holo.html',
  './manifest.json',
  './sw.js',
  './data/jarvis-neural-logo.jpg',
];

const DATA_ASSETS = [
  './data/politicians-index.json',
  './data/news-synthesis.json',
  './data/news-sample.json',
  './data/news-synthesis-ripples.json', // tolerant if missing
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const shellCache = await caches.open(SHELL_CACHE);
      await shellCache.addAll(PRECACHE_ASSETS.filter(Boolean));

      const dataCache = await caches.open(DATA_CACHE);
      // Cache data JSONs; tolerant on fail for prod (will network later) - matches holo PWA
      await Promise.allSettled(
        DATA_ASSETS.map(async (url) => {
          try {
            const res = await fetch(url, { cache: 'no-cache' });
            if (res.ok) await dataCache.put(url, res.clone());
          } catch (e) { /* offline tolerant */ }
        })
      );

      await self.skipWaiting();
    })()
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => ![SHELL_CACHE, DATA_CACHE, API_CACHE].includes(k))
          .map((k) => caches.delete(k))
      );
      await self.clients.claim();
      // Notify clients of update for holo PWA (parity)
      const clients = await self.clients.matchAll({ type: 'window' });
      clients.forEach((c) => c.postMessage({ type: 'SW_UPDATED', version: CACHE_VERSION }));
    })()
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin (parity)
  if (url.origin !== self.location.origin) return;

  // 1. DATA JSONs: Cache-first (offline first for holo viz JSONs, perfect for loadAndParse) + stale-while-revalidate
  const isDataJson = url.pathname.includes('/data/') && url.pathname.endsWith('.json');
  if (isDataJson || DATA_ASSETS.some(a => url.pathname.endsWith(a.replace('./','/')))) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(DATA_CACHE);
        const cached = await cache.match(request);
        if (cached) {
          // Stale-while-revalidate in bg
          fetch(request).then((fresh) => {
            if (fresh && fresh.ok) cache.put(request, fresh.clone());
          }).catch(() => {});
          return cached;
        }
        try {
          const res = await fetch(request);
          if (res.ok) await cache.put(request, res.clone());
          return res;
        } catch {
          return new Response(JSON.stringify({ nodes: [], links: [], meta: { offline: true, rule42: true, source: 'sw-cache-fallback' } }), {
            headers: { 'Content-Type': 'application/json' },
          });
        }
      })()
    );
    return;
  }

  // 2. Navigation / html shell: network-first with cache + offline fallback UI note (PWA hints)
  if (request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html') || url.pathname.endsWith('neural-map-holo.html')) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(SHELL_CACHE);
        try {
          const res = await fetch(request);
          if (res && res.ok && request.method === 'GET') {
            cache.put(request, res.clone());
          }
          return res;
        } catch {
          const cached = await cache.match(request) || await cache.match('./neural-map-holo.html');
          if (cached) {
            return cached;
          }
          // Minimal offline shell for holo
          return new Response(`<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JARVIS Holo (Offline PWA)</title><style>body{background:#0a0503;color:#fed7aa;font-family:system-ui;padding:2rem;text-align:center}</style></head><body><h1>🌀 JARVIS Holo — Offline</h1><p>Service Worker cached data + shell. Using offline JSONs (politicians + synthesis) + full local holo viz (Rule of 42, archetypes, sonif, exports). <a href="./neural-map-holo.html">Retry</a></p><script>document.title='JARVIS Holo (Offline PWA)';</script></body></html>`, {
            headers: { 'Content-Type': 'text/html' },
          });
        }
      })()
    );
    return;
  }

  // Default: try cache, fallback network (for CDN etc)
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).catch(() => {
      if (request.destination === 'document') {
        return caches.match('./neural-map-holo.html');
      }
      return new Response('', { status: 408 });
    }))
  );
});

// Message for client-driven cache refresh (e.g. from holo page "Refresh Data") + parity messages
self.addEventListener('message', (event) => {
  if (event.data?.type === 'REFRESH_HOLO_DATA') {
    (async () => {
      const dc = await caches.open(DATA_CACHE);
      await Promise.allSettled(DATA_ASSETS.map(u => dc.delete(u)));
      for (const u of DATA_ASSETS) {
        try { const r = await fetch(u); if (r.ok) await dc.put(u, r.clone()); } catch {}
      }
      event.source?.postMessage({ type: 'HOLO_DATA_REFRESHED' });
    })();
  }
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});
