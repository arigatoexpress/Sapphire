# Cloud Run Load Balancer Design

## Goals
- Terminate HTTPS for `cloud-trader` and `wallet-orchestrator` behind a single global load balancer.
- Present a single static IPv4 address that can be whitelisted with the Aster API.
- Preserve Cloud Run auto-scaling and zero-maintenance characteristics.
- Provide health checks, latency monitoring, and blue/green rollouts without downtime.

## Architecture Overview

```
                ┌───────────────────────┐
Public Client → │ Global HTTPS LB       │ → Serverless NEG → Cloud Run Service (cloud-trader)
                │  • Static IPv4        │ → Serverless NEG → Cloud Run Service (wallet-orchestrator)
                │  • Managed certs      │
                │  • Cloud Armor (opt)  │
                └───────────────────────┘
```

### Key Components
- **Global static IP** (`gcloud compute addresses create aster-static-ip --global`).
- **Serverless Network Endpoint Groups (NEGs)** pointing at each Cloud Run revision.
- **Backend Service** configured for HTTP/2 (Cloud Run default) and request/response logging. Cloud Run serverless NEGs expose managed health checks automatically.
- **URL Map** routing all traffic by path prefix:
  - `/api/*` and `/metrics` → `cloud-trader` NEG
  - `/orchestrator/*` → `wallet-orchestrator` NEG
  - `/` (default) → `cloud-trader` NEG for the dashboard UI.
- **Target HTTPS proxy + SSL certificate** (managed cert for `sapphiretrade.xyz` + subdomains).
- **Forwarding Rule** binding the static IP to ports 80/443.
- Optional **Cloud Armor** policy for WAF/rate-limiting, and **Cloud Logging** sink to BigQuery.

## Provisioning Steps

1. **Reserve Static IP**
   ```bash
   gcloud compute addresses create aster-static-ip --global --ip-version=IPV4
   gcloud compute addresses describe aster-static-ip --global --format='value(address)'
   ```

2. **Create Serverless NEGs**
   ```bash
   gcloud compute network-endpoint-groups create trader-neg \
     --region=us-central1 --network-endpoint-type=serverless --cloud-run-service=cloud-trader

   gcloud compute network-endpoint-groups create orchestrator-neg \
     --region=us-central1 --network-endpoint-type=serverless --cloud-run-service=wallet-orchestrator
   ```

3. **Backend Services**
   ```bash
   gcloud compute backend-services create trader-backend \
     --load-balancing-scheme=EXTERNAL_MANAGED --protocol=HTTP --global
   gcloud compute backend-services add-backend trader-backend \
     --global --network-endpoint-group=trader-neg --network-endpoint-group-region=us-central1

   gcloud compute backend-services create orchestrator-backend \
     --load-balancing-scheme=EXTERNAL_MANAGED --protocol=HTTP --global
   gcloud compute backend-services add-backend orchestrator-backend \
     --global --network-endpoint-group=orchestrator-neg --network-endpoint-group-region=us-central1
   ```

4. **URL Map**
   ```bash
   gcloud compute url-maps create aster-url-map \
     --default-service=trader-backend

   gcloud compute url-maps add-path-matcher aster-url-map \
     --path-matcher-name=aster-matcher \
     --default-service=trader-backend \
     --backend-service-path-rules="/orchestrator/*=orchestrator-backend"

   gcloud compute url-maps add-host-rule aster-url-map \
     --hosts=sapphiretrade.xyz,www.sapphiretrade.xyz,trader.sapphiretrade.xyz,api.sapphiretrade.xyz \
     --path-matcher-name=aster-matcher
   ```

5. **HTTPS Proxy + Certificates**
   ```bash
   gcloud compute ssl-certificates create sapphiretrade-cert \
     --domains=sapphiretrade.xyz,www.sapphiretrade.xyz,trader.sapphiretrade.xyz,api.sapphiretrade.xyz

   gcloud compute target-https-proxies create aster-https-proxy \
     --ssl-certificates=sapphiretrade-cert --url-map=aster-url-map
   ```

6. **Forwarding Rule**
   ```bash
   gcloud compute forwarding-rules create aster-https-forwarding \
     --load-balancing-scheme=EXTERNAL_MANAGED \
     --address=aster-static-ip \
     --global --target-https-proxy=aster-https-proxy --ports=443

   gcloud compute forwarding-rules create aster-http-forwarding \
     --load-balancing-scheme=EXTERNAL_MANAGED \
     --address=aster-static-ip \
     --global --target-http-proxy=aster-http-proxy --ports=80
   ```

> Replace `target-http-proxy` portion with HTTPS-only if we redirect HTTP to HTTPS via URL map.

## Monitoring & Ops
- Enable Cloud Monitoring uptime checks hitting `https://trader.sapphiretrade.xyz/healthz`.
- Export LB logs to Cloud Logging for latency analysis; add BigQuery sink for long-term storage.
- Use Prometheus metrics (`aster_api_requests_total`, etc.) to correlate load balancer traffic with Aster rate limits.
- Document static IP in Secret Manager (`ASTER_STATIC_IP`) for infra reproducibility.
- Track managed certificate status via `gcloud compute ssl-certificates describe sapphiretrade-cert`. A status of `FAILED_NOT_VISIBLE` indicates DNS is not yet pointing at the LB static IP—create the A/AAAA records for `sapphiretrade.xyz`, `trader.sapphiretrade.xyz`, and `api.sapphiretrade.xyz` → `34.117.165.111`, then re-check in ~15 minutes.

## Security Considerations
- Restrict Cloud Run ingress to `internal-and-cloud-load-balancing` once LB is active.
- Add Cloud Armor rule to block abusive IPs and enforce request quotas.
- Keep secrets in Secret Manager; no changes required for LB.
- Update Cloud Run services to `--ingress=internal-and-cloud-load-balancing` once the load balancer is verified to enforce LB-only access.

## Next Steps
- ✅ DNS delegated to Cloud DNS (`ns-cloud-e*.googledomains.com`) with A/CNAME records for `sapphiretrade.xyz`, `trader`, `api`, and `www` pointing at `34.117.165.111`.
- ✅ Managed certificate `sapphiretrade-cert` now `ACTIVE`; Cloud Run ingress restricted to `internal-and-cloud-load-balancing`.
- ➡️ Update Aster API whitelist with static IP `34.117.165.111` and rerun rate-limit soak tests.
- ➡️ Enable Cloud Monitoring HTTPS uptime checks and synthetic latency probes.