/* SoloLedger Service Worker v2 — offline support + caching */

const CACHE = 'sololedger-v2';
const STATIC_ASSETS = [
  '/app/',
  '/app/index-classic.html',
  '/app/css/style.css?v=2',
  '/app/manifest.json',
  '/app/favicon.svg',
  '/app/icon-152.png',
  '/api/v1/_js/app.js',
  '/api/v1/_js/api.js',
  '/api/v1/_js/pages/dashboard.js',
  '/api/v1/_js/pages/auth.js',
  '/api/v1/_js/pages/accounts.js',
  '/api/v1/_js/pages/import.js',
  '/api/v1/_js/pages/invoices.js',
  '/api/v1/_js/pages/mileage.js',
  '/api/v1/_js/pages/receipts.js',
  '/api/v1/_js/pages/reports.js',
  '/api/v1/_js/pages/settings.js',
  '/api/v1/_js/pages/tax.js',
  '/api/v1/_js/pages/transactions.js',
  '/api/v1/_js/pages/categorize.js',
  '/api/v1/_js/pages/onboarding.js',
  '/api/v1/_js/pages/setup.js',
  '/api/v1/_js/pages/health.js',
  '/api/v1/_js/pages/payroll.js',
];

// ── Install: cache static assets ──
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// ── Activate: clean old caches ──
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

// ── Fetch: network-only for API, cache-first for static assets ──
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls: never cache (auth-scoped financial data) — straight to network
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkOnly(event.request));
    return;
  }

  // Static assets: cache-first
  event.respondWith(cacheFirst(event.request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok && request.method === 'GET') {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return caches.match('/app/'); // fallback to home page
  }
}

async function networkOnly(request) {
  try {
    return await fetch(request);
  } catch (err) {
    return new Response(
      JSON.stringify({ success: false, error: 'Offline' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
