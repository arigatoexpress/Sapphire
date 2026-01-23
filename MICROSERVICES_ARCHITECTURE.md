# Sapphire V2 Microservices Architecture

## Overview

Sapphire V2 has been refactored from a monolithic Cloud Run service to a distributed microservices architecture with **fault isolation**, **platform-specific scaling**, and **real-time data aggregation**.

### Key Benefits

1. **Fault Isolation**: Platform failures don't cascade (Hyperliquid crash ≠ Drift downtime)
2. **Independent Scaling**: Scale Drift (high volume) separately from Lighter (low volume)
3. **Compliance**: Separate deployments per regulatory requirements
4. **Performance**: Eliminate cross-platform contention

---

## Architecture Components

### 1. Trading Services (5 instances)

Each trading service runs the same Docker image but is configured to handle **only one platform**:

| Service Name       | Platform   | Env Flags                                    | Purpose                           |
|--------------------|------------|----------------------------------------------|-----------------------------------|
| `sapphire-hl`      | Hyperliquid | `ENABLE_HYPERLIQUID=true`                   | Hyperliquid perpetual trading     |
| `sapphire-lighter` | Lighter.xyz | `ENABLE_LIGHTER=true`                       | Lighter decentralized trading     |
| `sapphire-drift`   | Drift       | `ENABLE_DRIFT=true`                         | Drift Protocol Solana trading     |
| `sapphire-aster`   | AsterDEX    | `ENABLE_ASTER=true`                         | AsterDEX futures trading          |
| `sapphire-symphony`| Symphony    | `ENABLE_SYMPHONY=true`                      | Agent orchestration (optional)    |

**Key Principle**: Each service has **exactly one** `ENABLE_*` flag set to `true`, all others `false`.

### 2. Web Service (1 instance)

| Service Name   | Purpose                              | Env Flags                |
|----------------|--------------------------------------|--------------------------|
| `sapphire-web` | Vue.js dashboard + aggregation layer | `SERVE_FRONTEND=true`    |

The web service:
- **Does NOT trade** (all `ENABLE_*` flags are `false`)
- **Subscribes** to events from all trading services via PubSub
- **Aggregates** fleet-wide state (balances, positions, health)
- **Serves** the Vue.js frontend with unified data

---

## Data Aggregation Strategy

### PubSub + Firestore Hybrid

**Why this approach?**
- ✅ **Low latency**: PubSub delivers events in ~100-500ms
- ✅ **Decoupling**: Services publish events without knowing about subscribers
- ✅ **Persistence**: Firestore stores state snapshots for historical queries
- ✅ **Native GCP**: No external dependencies

### Event Flow

```
┌─────────────────┐
│ sapphire-hl     │──┐
│ (Hyperliquid)   │  │
└─────────────────┘  │
                     │
┌─────────────────┐  │    ┌──────────────────────┐
│ sapphire-lighter│──┼────▶│  PubSub Topic:       │
│ (Lighter.xyz)   │  │    │  sapphire-service-   │
└─────────────────┘  │    │  events              │
                     │    └──────────────────────┘
┌─────────────────┐  │              │
│ sapphire-drift  │──┤              │
│ (Drift)         │  │              ▼
└─────────────────┘  │    ┌──────────────────────┐
                     │    │  PubSub Subscription:│
┌─────────────────┐  │    │  sapphire-web-events │
│ sapphire-aster  │──┘    └──────────────────────┘
│ (AsterDEX)      │                  │
└─────────────────┘                  │
                                     ▼
                          ┌──────────────────────┐
                          │  sapphire-web        │
                          │  (Aggregator)        │
                          │                      │
                          │  ├─ Shadow State    │
                          │  ├─ Firestore Sync  │
                          │  └─ Dashboard API   │
                          └──────────────────────┘
```

### Event Types

Trading services publish these events:

```python
ServiceEventType:
    HEARTBEAT              # Every 30s - service health
    BALANCE_UPDATE         # On balance change
    TRADE_EXECUTED         # After order fill
    POSITION_OPENED        # New position
    POSITION_CLOSED        # Position exit
    POSITION_UPDATED       # Position modification
    RISK_LIMIT_BREACHED    # Risk violation
```

### State Aggregator (sapphire-web only)

The `ServiceStateAggregator` class:
1. **Subscribes** to `sapphire-service-events` PubSub topic
2. **Processes** incoming events in real-time
3. **Maintains** in-memory shadow state:
   - `_balances`: Service → balance mapping
   - `_positions`: Service → positions list
   - `_last_heartbeat`: Service → timestamp
4. **Persists** to Firestore for durability
5. **Exposes** unified API for dashboard

---

## Service Identity & Scope Enforcement

### Identity Detection

Each service automatically detects its identity from environment variables:

```python
from cloud_trader.microservices.identity import get_service_identity

identity = get_service_identity()
# Returns: ServiceIdentity(
#     service_type=ServiceType.HYPERLIQUID,
#     service_name="sapphire-hl",
#     instance_id="sapphire-hl-00001-abc",
#     region="europe-west1",
#     emoji="💧",
#     is_trading_service=True,
#     is_web_service=False
# )
```

### Scope Validation

Trading services **MUST NOT** trade on unauthorized platforms:

```python
from cloud_trader.microservices.identity import validate_trading_scope

# In Hyperliquid worker:
validate_trading_scope("hyperliquid")  # ✅ OK
validate_trading_scope("drift")        # ❌ RuntimeError!
```

This prevents misconfiguration bugs (e.g., Hyperliquid worker accidentally trading on Drift).

---

## API Changes

### Endpoints Behavior by Service Type

| Endpoint            | Trading Service (HL/Drift/etc)     | Web Service (sapphire-web)        |
|---------------------|------------------------------------|-----------------------------------|
| `/api/dashboard`    | Returns **local** service data     | Returns **aggregated** fleet data |
| `/api/positions`    | Returns **local** positions        | Returns **all** positions         |
| `/api/trades`       | Returns **local** trades           | Could aggregate from events       |

### New Fleet Endpoints (sapphire-web only)

```
GET /api/fleet/summary       # Total equity, positions, service health
GET /api/fleet/positions     # All positions across fleet
GET /api/fleet/health        # Health status of all services
GET /api/fleet/balances      # Per-service balance breakdown
GET /api/fleet/events/recent # Recent events from all services
```

Example response from `/api/fleet/summary`:

```json
{
  "total_equity": 12500.45,
  "total_positions": 8,
  "services": {
    "sapphire-hl": {
      "balance": 5000.12,
      "positions": 3,
      "health": {
        "status": "healthy",
        "last_heartbeat": 1706123456.78,
        "age_seconds": 15.2
      }
    },
    "sapphire-drift": {
      "balance": 7500.33,
      "positions": 5,
      "health": {
        "status": "healthy",
        "last_heartbeat": 1706123450.12,
        "age_seconds": 21.6
      }
    }
  },
  "timestamp": 1706123471.92
}
```

---

## Deployment Guide

### Prerequisites

1. **GCP Project** with Cloud Run, PubSub, Firestore enabled
2. **Region**: `europe-west1` (configurable via `_REGION` substitution)
3. **IAM Permissions**: Service accounts need `pubsub.publisher` and `pubsub.subscriber` roles

### Step 1: Setup PubSub Infrastructure

```bash
cd /path/to/sapphire_repo
./scripts/setup-pubsub.sh
```

This creates:
- Topic: `projects/{project}/topics/sapphire-service-events`
- Subscription: `projects/{project}/subscriptions/sapphire-web-events`

### Step 2: Deploy All Services

```bash
gcloud builds submit --config=cloudbuild_microservices.yaml
```

This deploys:
1. **Build** unified Docker image
2. **Push** to GCR
3. **Deploy** 6 Cloud Run services in parallel:
   - `sapphire-hl`
   - `sapphire-lighter`
   - `sapphire-drift`
   - `sapphire-aster`
   - `sapphire-symphony`
   - `sapphire-web`

### Step 3: Verify Deployment

```bash
# Check service health
gcloud run services list --region=europe-west1

# Verify PubSub events are flowing
gcloud pubsub subscriptions pull sapphire-web-events --limit=10

# Check logs for a specific service
gcloud logging read "resource.labels.service_name=sapphire-hl" --limit=50
```

### Step 4: Access Dashboard

Navigate to the `sapphire-web` service URL:

```
https://sapphire-web-{hash}-ew.a.run.app
```

You should see:
- ✅ Total equity summed across all services
- ✅ Positions from all platforms
- ✅ Health status indicators (🟢 healthy, 🟡 stale, 🔴 down)

---

## Frontend Integration

### API Client Changes

The Vue.js frontend client should:

1. **Detect environment**: Check if running on `sapphire-web` URL
2. **Use fleet endpoints** when available:

```typescript
// client.ts
export async function getDashboard(): Promise<DashboardData> {
  // Try fleet endpoint first (sapphire-web)
  try {
    const response = await api.get('/api/fleet/summary')
    if (response.data) {
      return transformFleetData(response.data)
    }
  } catch (e) {
    console.warn('Fleet endpoint unavailable, falling back to local')
  }

  // Fallback to local endpoint (individual trading service)
  return api.get('/api/dashboard')
}
```

### Real-Time Updates

Option 1: **Polling** (simplest)
```typescript
setInterval(async () => {
  const summary = await getDashboard()
  updateUI(summary)
}, 5000) // Poll every 5 seconds
```

Option 2: **Firestore Listeners** (real-time)
```typescript
import { getFirestore, collection, onSnapshot } from 'firebase/firestore'

const db = getFirestore()
const balancesRef = collection(db, 'service_balances')

onSnapshot(balancesRef, (snapshot) => {
  snapshot.docChanges().forEach((change) => {
    if (change.type === 'modified') {
      updateBalance(change.doc.id, change.doc.data())
    }
  })
})
```

### Example Dashboard Component

```vue
<!-- FleetStatus.vue -->
<template>
  <div class="fleet-status">
    <h2>Fleet Overview</h2>
    <div class="total-equity">
      <span class="label">Total Equity:</span>
      <span class="value">${{ fleetData.total_equity.toFixed(2) }}</span>
    </div>

    <div class="services">
      <div
        v-for="(service, name) in fleetData.services"
        :key="name"
        class="service-card"
      >
        <div class="service-header">
          <span class="emoji">{{ getServiceEmoji(name) }}</span>
          <span class="name">{{ name }}</span>
          <span
            class="health-indicator"
            :class="service.health.status"
          ></span>
        </div>
        <div class="service-stats">
          <div>Balance: ${{ service.balance.toFixed(2) }}</div>
          <div>Positions: {{ service.positions }}</div>
          <div>
            Last update: {{ formatTimestamp(service.health.last_heartbeat) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/client'

const fleetData = ref({
  total_equity: 0,
  services: {}
})

async function fetchFleetData() {
  const response = await api.get('/api/fleet/summary')
  fleetData.value = response.data
}

onMounted(() => {
  fetchFleetData()
  setInterval(fetchFleetData, 5000) // Refresh every 5s
})

function getServiceEmoji(serviceName: string): string {
  const emojiMap = {
    'sapphire-hl': '💧',
    'sapphire-lighter': '⚡',
    'sapphire-drift': '🌀',
    'sapphire-aster': '⭐',
    'sapphire-symphony': '🎻'
  }
  return emojiMap[serviceName] || '🤖'
}
</script>

<style scoped>
.health-indicator {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.health-indicator.healthy {
  background: #10b981; /* green */
}

.health-indicator.stale {
  background: #f59e0b; /* amber */
}

.health-indicator.down {
  background: #ef4444; /* red */
}
</style>
```

---

## Troubleshooting

### Problem: sapphire-web shows empty state

**Diagnosis:**
```bash
# Check if PubSub subscription exists
gcloud pubsub subscriptions describe sapphire-web-events

# Check for recent messages
gcloud pubsub subscriptions pull sapphire-web-events --limit=10
```

**Solutions:**
1. Verify trading services have `ENABLE_PUBSUB=true`
2. Check IAM permissions for service accounts
3. Look for errors in sapphire-web logs:
   ```bash
   gcloud logging read "resource.labels.service_name=sapphire-web AND severity>=ERROR"
   ```

### Problem: Services trading on wrong platforms

**Diagnosis:**
```bash
# Check service environment variables
gcloud run services describe sapphire-hl --region=europe-west1 --format="value(spec.template.spec.containers[0].env)"
```

**Solution:**
- Ensure `cloudbuild_microservices.yaml` has correct `ENABLE_*` flags
- Redeploy with corrected configuration

### Problem: High latency in dashboard

**Check:**
1. PubSub message age:
   ```bash
   gcloud pubsub subscriptions describe sapphire-web-events --format="value(oldestUnackedMessageAge)"
   ```
2. Firestore write latency (Cloud Console → Firestore → Usage)

**Optimize:**
- Increase sapphire-web Cloud Run concurrency
- Add Redis caching layer for frequently accessed data

---

## Performance Characteristics

### Latency Benchmarks

| Metric                      | Target    | Typical   |
|-----------------------------|-----------|-----------|
| Event publish (trading svc) | <10ms     | 5-8ms     |
| Event delivery (PubSub)     | <500ms    | 100-300ms |
| Dashboard API response      | <200ms    | 50-150ms  |
| End-to-end (trade → UI)     | <1s       | 400-700ms |

### Scalability

- **PubSub**: 10,000+ messages/sec per topic
- **Firestore**: 10,000 writes/sec per collection
- **Cloud Run**: Auto-scales from 0 to 1000 instances/service

### Cost Optimization

1. **Batch Firestore writes**: Group updates to reduce write operations
2. **Aggressive caching**: Use Redis for read-heavy endpoints
3. **PubSub message TTL**: Set 7-day retention (not indefinite)

---

## Security Considerations

### IAM Roles

```yaml
# Service Account: sapphire-trading@{project}.iam.gserviceaccount.com
roles:
  - roles/pubsub.publisher  # For trading services
  - roles/run.invoker       # For Cloud Run
  - roles/datastore.user    # For Firestore

# Service Account: sapphire-web@{project}.iam.gserviceaccount.com
roles:
  - roles/pubsub.subscriber # For sapphire-web
  - roles/datastore.user    # For Firestore
  - roles/run.invoker
```

### Secrets Management

**DO NOT** hardcode credentials in environment variables. Use Secret Manager:

```yaml
# cloudbuild_microservices.yaml (example)
--set-secrets:
  - ASTER_API_KEY=aster-api-key:latest
  - HL_SECRET_KEY=hyperliquid-key:latest
```

### Network Security

- All services communicate via **authenticated** Cloud Run URLs
- PubSub uses **IAM-based** authentication (no API keys)
- Firestore rules enforce **server-side** access only

---

## Monitoring & Observability

### Key Metrics (Cloud Monitoring)

1. **Service Health**
   - Metric: `custom.googleapis.com/microservices/heartbeat_age`
   - Alert: Age > 120s → service might be down

2. **Event Processing Rate**
   - Metric: `pubsub.googleapis.com/subscription/num_delivered_messages`
   - Alert: Sustained 0 messages → publisher issue

3. **Aggregation Lag**
   - Metric: `custom.googleapis.com/microservices/aggregation_lag`
   - Alert: Lag > 5s → PubSub backlog

### Logging Best Practices

All services use structured logging with service identity:

```python
logger.info(f"{identity.emoji} [{identity.service_name}] Trade executed: {symbol}")
```

Example log entry:
```
💧 [sapphire-hl] Trade executed: BTC-PERP, side=BUY, size=0.1
```

### Distributed Tracing (Optional)

For advanced debugging, enable Cloud Trace:

```python
from google.cloud import trace_v1

tracer = trace_v1.TraceServiceClient()
# Instrument key operations
```

---

## Migration Checklist

### From Monolith to Microservices

- [ ] Run `scripts/setup-pubsub.sh` to create infrastructure
- [ ] Update `cloudbuild_microservices.yaml` with project ID
- [ ] Deploy all 6 services via Cloud Build
- [ ] Verify each service identity in logs
- [ ] Check PubSub subscription is receiving events
- [ ] Test dashboard shows aggregated data
- [ ] Update frontend API clients to use fleet endpoints
- [ ] Monitor for 24 hours, check for errors
- [ ] Decommission old monolith service

---

## Future Enhancements

### Planned Improvements

1. **Redis Caching Layer**
   - Cache aggregated state in Redis for <50ms API responses
   - Reduce Firestore read costs

2. **Event Replay**
   - Store events in BigQuery for historical analysis
   - Support "replay" for debugging

3. **Cross-Service Coordination**
   - Centralize portfolio rebalancing in `sapphire-symphony`
   - Coordinate hedging across platforms

4. **Advanced Health Checks**
   - Synthetic transactions to verify end-to-end flows
   - Auto-restart unhealthy services

5. **Multi-Region**
   - Deploy read-replicas in `us-central1` for lower latency
   - Use global load balancer for `sapphire-web`

---

## References

- [Google Cloud PubSub Best Practices](https://cloud.google.com/pubsub/docs/best-practices)
- [Cloud Run Microservices Architecture](https://cloud.google.com/architecture/microservices-architecture-on-google-cloud)
- [Firestore Real-Time Updates](https://firebase.google.com/docs/firestore/query-data/listen)

---

**Document Version**: 1.0
**Last Updated**: 2026-01-19
**Author**: Sapphire Trading Team
