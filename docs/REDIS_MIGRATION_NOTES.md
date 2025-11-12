# Redis-Free Caching Notes

Our Gemini AI review confirmed the trading stack no longer relies on Redis. The backend now ships with a pluggable cache layer:

- **Default backend**: in-memory TTL cache (`memory`) – no external dependency, suitable for Cloud Run/GKE pods.
- **Optional backend**: Redis (`redis`) – enabled only when `CACHE_BACKEND=redis` and `REDIS_URL` are provided.

Other subsystems that previously used Redis have first-party replacements:

| Legacy usage        | Replacement component                             |
|---------------------|----------------------------------------------------|
| Market snapshot cache | `InMemoryCache` inside `TradingService`           |
| Streams / dashboards | Google Pub/Sub (`PubSubClient`) + BigQuery sink    |
| Portfolio state      | PostgreSQL/Timescale via `TradingStorage`          |
| Feature features     | Feast (`TradingFeatureStore`) + BigQuery streaming |

## Configuration

| Variable        | Default  | Description                                  |
|-----------------|----------|----------------------------------------------|
| `CACHE_BACKEND` | `memory` | Choose `memory` (default) or `redis` backend |
| `REDIS_URL`     | `None`   | Only required when `CACHE_BACKEND=redis`     |

With `CACHE_BACKEND=memory`, the service exposes `cache.backend=memory` and `cache.connected=true` in `/dashboard` responses.
