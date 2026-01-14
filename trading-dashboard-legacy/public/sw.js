// Service Worker for Trading Dashboard
// Provides caching and offline functionality

const CACHE_NAME = 'sapphire-trading-v1.0.0';
const STATIC_CACHE = 'sapphire-static-v1.0.0';
const API_CACHE = 'sapphire-api-v1.0.0';

// Resources to cache immediately
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/favicon.ico',
  '/sapphire-icon.svg'
];

// API endpoints to cache (with short TTL)
const API_ENDPOINTS = [
  '/portfolio-status',
  '/agent-activity',
  '/global-signals'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        return self.skipWaiting();
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME && cacheName !== STATIC_CACHE && cacheName !== API_CACHE) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      return self.clients.claim();
    })
  );
});

// Fetch event - handle requests
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Handle API requests with network-first strategy
  if (API_ENDPOINTS.some(endpoint => url.pathname.includes(endpoint))) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Cache successful responses for short time
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(API_CACHE).then((cache) => {
              // Add timestamp for cache expiry (5 minutes)
              const responseWithTimestamp = new Response(responseClone.body, {
                status: responseClone.status,
                statusText: responseClone.statusText,
                headers: {
                  ...Object.fromEntries(responseClone.headers),
                  'sw-cache-timestamp': Date.now().toString(),
                  'sw-cache-ttl': (5 * 60 * 1000).toString() // 5 minutes
                }
              });
              cache.put(request, responseWithTimestamp);
            });
          }
          return response;
        })
        .catch(() => {
          // Network failed, try cache
          return caches.match(request).then((cachedResponse) => {
            if (cachedResponse) {
              const cacheTimestamp = parseInt(cachedResponse.headers.get('sw-cache-timestamp') || '0');
              const cacheTTL = parseInt(cachedResponse.headers.get('sw-cache-ttl') || '0');
              const now = Date.now();

              // Check if cache is still valid
              if (now - cacheTimestamp < cacheTTL) {
                return cachedResponse;
              } else {
                // Cache expired, remove it
                caches.open(API_CACHE).then(cache => cache.delete(request));
              }
            }

            // No valid cache, return offline response
            return new Response(JSON.stringify({
              error: 'Offline',
              message: 'You are currently offline. Please check your internet connection.'
            }), {
              status: 503,
              headers: { 'Content-Type': 'application/json' }
            });
          });
        })
    );
    return;
  }

  // Handle static assets with cache-first strategy
  if (STATIC_ASSETS.some(asset => url.pathname === asset) ||
      request.destination === 'style' ||
      request.destination === 'script' ||
      request.destination === 'image') {
    event.respondWith(
      caches.match(request)
        .then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          return fetch(request).then((response) => {
            // Cache successful responses
            if (response.status === 200) {
              const responseClone = response.clone();
              caches.open(STATIC_CACHE).then((cache) => {
                cache.put(request, responseClone);
              });
            }
            return response;
          });
        })
    );
    return;
  }

  // Default network-first for other requests
  event.respondWith(
    fetch(request)
      .catch(() => {
        // Network failed, try cache
        return caches.match(request).then((cachedResponse) => {
          return cachedResponse || new Response('Offline - Content not available', {
            status: 503,
            headers: { 'Content-Type': 'text/plain' }
          });
        });
      })
  );
});

// Background sync for failed requests (if supported)
self.addEventListener('sync', (event) => {
  if (event.tag === 'background-sync') {
    event.waitUntil(doBackgroundSync());
  }
});

async function doBackgroundSync() {
  // Implement background sync logic here
  // This would retry failed API requests when connectivity is restored
  console.log('Background sync triggered');
}

// Push notifications (for future use)
self.addEventListener('push', (event) => {
  if (event.data) {
    const data = event.data.json();
    const options = {
      body: data.body,
      icon: '/sapphire-icon.svg',
      badge: '/sapphire-icon.svg',
      vibrate: [100, 50, 100],
      data: data.data
    };

    event.waitUntil(
      self.registration.showNotification(data.title, options)
    );
  }
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data?.url || '/')
  );
});
