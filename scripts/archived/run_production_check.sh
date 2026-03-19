#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
DOMAIN="${DOMAIN:-https://sapphirealpha.xyz}"
AUTH_USER="${AUTH_USER:-sapphire}"
AUTH_PASS="${AUTH_PASS:-alpha2024}"
AUTH="${AUTH_USER}:${AUTH_PASS}"
STRICT_RUNTIME_GIT="${STRICT_RUNTIME_GIT:-true}"
ALLOW_UNTRACKED="${ALLOW_UNTRACKED:-false}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-gcr.io/${PROJECT_ID}/sapphire-unified-frontend:latest}"
FRONTEND_RUNTIME_SERVICES="${FRONTEND_RUNTIME_SERVICES:-sapphire-unified-frontend sapphire-unified-jobs}"

printf "== Sapphire Production Check ==\n"
printf "project=%s region=%s domain=%s\n\n" "$PROJECT_ID" "$REGION" "$DOMAIN"

is_truthy() {
  local v="${1:-}"
  v="$(printf '%s' "$v" | tr '[:upper:]' '[:lower:]')"
  [[ "$v" == "1" || "$v" == "true" || "$v" == "yes" || "$v" == "on" ]]
}

normalize_digest() {
  local d="${1:-}"
  d="${d##*@sha256:}"
  d="${d##sha256:}"
  printf '%s' "$d"
}

if is_truthy "$STRICT_RUNTIME_GIT"; then
  printf "[0/7] Runtime == git guard\n"
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "FAIL: not inside a git repository; cannot validate runtime==git guard."
    exit 1
  fi

  if ! git diff --quiet --ignore-submodules --; then
    echo "FAIL: working tree has unstaged changes. Commit/stash before production check."
    git status --short | sed -n '1,120p'
    exit 1
  fi
  if ! git diff --cached --quiet --ignore-submodules --; then
    echo "FAIL: index has staged but uncommitted changes."
    git status --short | sed -n '1,120p'
    exit 1
  fi

  if ! is_truthy "$ALLOW_UNTRACKED"; then
    untracked_count="$(git ls-files --others --exclude-standard | wc -l | tr -d ' ')"
    if [[ "${untracked_count:-0}" != "0" ]]; then
      echo "FAIL: untracked files present (${untracked_count}). Set ALLOW_UNTRACKED=true to bypass."
      git ls-files --others --exclude-standard | sed -n '1,80p'
      exit 1
    fi
  fi

  image_repo="${FRONTEND_IMAGE%:*}"
  image_tag="${FRONTEND_IMAGE##*:}"
  latest_digest="$(
    gcloud container images list-tags "$image_repo" \
      --filter="tags:${image_tag}" \
      --limit=1 \
      --format='json' | python3 -c '
import json,sys
rows=json.load(sys.stdin)
print((rows[0].get("digest","") if rows else "").strip())
'
  )"
  if [[ -z "${latest_digest:-}" ]]; then
    echo "FAIL: unable to resolve digest for ${FRONTEND_IMAGE}"
    exit 1
  fi
  latest_digest="$(normalize_digest "$latest_digest")"
  echo "frontend_image_digest=${latest_digest}"

  for svc in $FRONTEND_RUNTIME_SERVICES; do
    rev="$(
      gcloud run services describe "$svc" \
        --project "$PROJECT_ID" \
        --region "$REGION" \
        --format='value(status.latestReadyRevisionName)'
    )"
    if [[ -z "${rev:-}" ]]; then
      echo "FAIL: unable to resolve latest revision for ${svc}"
      exit 1
    fi
    rev_digest="$(
      gcloud run revisions describe "$rev" \
        --project "$PROJECT_ID" \
        --region "$REGION" \
        --format='value(status.imageDigest)'
    )"
    rev_digest="$(normalize_digest "$rev_digest")"
    if [[ "$rev_digest" != "$latest_digest" ]]; then
      echo "FAIL: ${svc} (${rev}) digest mismatch. runtime=${rev_digest} expected=${latest_digest}"
      exit 1
    fi
    printf "runtime_match %-30s %s\n" "$svc" "$rev"
  done
  echo ""
fi

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
  /api/platform/business-brief \
  /api/platform/logs \
  /api/platform/trades \
  /api/platform/organization \
  /api/platform/readiness \
  /api/platform/projects \
  /api/platform/intel-feed \
  /api/platform/superswarm \
  /api/platform/windows-lab \
  /api/platform/contracts
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

printf "\n[extra] Contract manifest snapshot\n"
curl -s -u "$AUTH" "$DOMAIN/api/platform/contracts" | python3 -c '
import json,sys
p=json.load(sys.stdin)
print("contract_version=", p.get("version"))
print("endpoint_count=", (p.get("counts") or {}).get("total"))
print("auth_enabled=", (p.get("auth") or {}).get("enabled"))
print("public_read_only=", (p.get("auth") or {}).get("public_read_only"))
print("internal_jobs_enabled=", (p.get("auth") or {}).get("internal_jobs_enabled"))
'

printf "\n[extra] Public mutation route policy\n"
job_code=$(curl -s -o /tmp/sapphire_public_job_probe.json -w '%{http_code}' "$DOMAIN/jobs/superswarm/hourly-rollup")
printf "%-40s %s\n" "/jobs/superswarm/hourly-rollup" "$job_code"
if [[ "$job_code" != "404" ]]; then
  echo "FAIL: public mutation route must return 404 on business surface"
  exit 1
fi

printf "\n[6/7] Scheduler inventory\n"
gcloud scheduler jobs list \
  --project "$PROJECT_ID" \
  --location "$REGION" \
  --format='table(name,state,schedule,httpTarget.uri)'

if [[ -x "./scripts/cleanup_scheduler_drift.sh" ]]; then
  printf "\n[7/7] Scheduler drift audit (allowlist)\n"
  ./scripts/cleanup_scheduler_drift.sh --dry-run
fi

if [[ -x "./scripts/platform_contract_audit.sh" ]]; then
  printf "\n[extra] Platform contract audit\n"
  DOMAIN="$DOMAIN" AUTH_USER="$AUTH_USER" AUTH_PASS="$AUTH_PASS" ./scripts/platform_contract_audit.sh
fi

MONITOR_SCRIPT="${MONITOR_SCRIPT:-./scripts/unified_health_monitor.py}"
if [[ ! -f "$MONITOR_SCRIPT" && -f "/Users/aribs/sapphire_trading_monitor/unified_health_monitor.py" ]]; then
  MONITOR_SCRIPT="/Users/aribs/sapphire_trading_monitor/unified_health_monitor.py"
fi
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
if (p.get("optional_degraded_count") or 0) > 0:
    print("optional_degraded={}".format(p.get("optional_degraded_count")))
    for s in p.get("optional_degraded_services", [])[:10]:
        print(" - optional", s.get("category"), s.get("name"), s.get("error"))
'
fi

printf "\nDone.\n"
