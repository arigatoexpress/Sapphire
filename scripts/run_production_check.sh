#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
DOMAIN="${DOMAIN:-https://sapphirealpha.xyz}"
AUTH_USER="${AUTH_USER:-sapphire}"
AUTH_PASS="${AUTH_PASS:-alpha2024}"
AUTH="${AUTH_USER}:${AUTH_PASS}"

printf "== Sapphire Production Check ==\n"
printf "project=%s region=%s domain=%s\n\n" "$PROJECT_ID" "$REGION" "$DOMAIN"

check_endpoint() {
  local path="$1"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" "$DOMAIN$path")
  printf "%-40s %s\n" "$path" "$code"
}

printf "[1/6] Platform contract endpoints\n"
for path in \
  /api/platform/status \
  /api/platform/metrics \
  /api/platform/autonomy \
  /api/platform/home-snapshot \
  /api/platform/logs \
  /api/platform/organization \
  /api/platform/readiness \
  /api/platform/projects \
  /api/platform/intel-feed \
  /api/platform/superswarm
  do
  check_endpoint "$path"
done

printf "\n[2/6] Frontend routes\n"
for path in \
  / \
  /trading \
  /autonomy \
  /command-deck \
  /system-health \
  /logs \
  /projects \
  /organization \
  /production-readiness \
  /infrastructure
  do
  check_endpoint "$path"
done

printf "\n[3/6] Readiness gate snapshot\n"
curl -s -u "$AUTH" "$DOMAIN/api/platform/readiness" | python3 -c '
import json,sys
p=json.load(sys.stdin)
print("overall_ok=", p.get("overall_ok"))
for gate,v in (p.get("gates") or {}).items():
    print("{}: ok={} pass={}/{}".format(gate, v.get("ok"), v.get("pass"), v.get("total")))
blockers=p.get("blockers") or []
print("blockers=", len(blockers))
for b in blockers[:5]:
    print(" -", b.get("gate"), b.get("name"), b.get("error"))
'

printf "\n[extra] Trading telemetry snapshot\n"
curl -s -u "$AUTH" "$DOMAIN/api/platform/metrics" | python3 -c '
import json,sys
p=json.load(sys.stdin)
t=(p.get("trading") or {})
print("source=", t.get("source"))
tr=(t.get("trades") or {})
pnl=(t.get("pnl") or {})
print("trades_today=", tr.get("today"), "trades_total=", tr.get("total"), "success_rate=", tr.get("success_rate"))
print("pnl_daily=", pnl.get("daily"), "pnl_weekly=", pnl.get("weekly"), "pnl_monthly=", pnl.get("monthly"), "pnl_total=", pnl.get("total"))
'

printf "\n[4/7] Gateway failover ingress\n"
GATEWAY_URL=$(gcloud run services describe sapphire-gateway \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.url)')
if [[ -n "${GATEWAY_URL:-}" ]]; then
  code=$(curl -s -o /tmp/sapphire_gateway_webhook_health.json -w '%{http_code}' "$GATEWAY_URL/webhook/health")
  printf "%-40s %s\n" "$GATEWAY_URL/webhook/health" "$code"
  if [[ -f /tmp/sapphire_gateway_webhook_health.json ]]; then
    python3 - <<'PY'
import json
from pathlib import Path
p = Path("/tmp/sapphire_gateway_webhook_health.json")
try:
    d = json.loads(p.read_text())
    ingress = d.get("tradingview_ingress", {})
    print("ingress_enabled=", ingress.get("enabled"))
    print("ingress_published=", (ingress.get("stats") or {}).get("published"))
except Exception as e:
    print("ingress_parse_error=", e)
PY
  fi
else
  echo "gateway_url_unavailable"
fi

printf "\n[5/7] Cloud Run inventory\n"
gcloud run services list \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='table(metadata.name,status.latestReadyRevisionName,status.traffic[0].percent)'

printf "\n[extra] Windows lab capabilities snapshot\n"
check_endpoint /api/platform/windows-lab

printf "\n[6/7] Scheduler inventory\n"
gcloud scheduler jobs list \
  --project "$PROJECT_ID" \
  --location "$REGION" \
  --format='table(name,state,schedule,httpTarget.uri)'

if [[ -x "./scripts/cleanup_scheduler_drift.sh" ]]; then
  printf "\n[7/7] Scheduler drift audit (allowlist)\n"
  ./scripts/cleanup_scheduler_drift.sh --dry-run
fi

MONITOR_SCRIPT="/Users/aribs/sapphire_trading_monitor/unified_health_monitor.py"
if [[ -f "$MONITOR_SCRIPT" ]]; then
  printf "\n[extra] Cross-environment monitor snapshot\n"
  python3 "$MONITOR_SCRIPT" --check | python3 -c '
import json,sys,re
text=sys.stdin.read()
m=re.search(r"\{\s*\"timestamp\".*", text, re.S)
if not m:
    print("monitor_json=unavailable")
    sys.exit(0)
p=json.loads(m.group(0))
print("overall_healthy={} healthy={}/{}".format(p.get("overall_healthy"), p.get("healthy_count"), p.get("total_services")))
for s in p.get("unhealthy_services", [])[:10]:
    print(" -", s.get("category"), s.get("name"), s.get("error"))
'
fi

printf "\nDone.\n"
