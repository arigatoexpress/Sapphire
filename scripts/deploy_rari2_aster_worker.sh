#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

"${REPO_ROOT}/scripts/check_source_of_truth.sh" "${REPO_ROOT}" >/dev/null

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
REGION="${REGION:-us-central1}"
PI_HOST="${PI_HOST:-rari@100.87.225.89}"
EDGE_PRINCIPAL="${EDGE_PRINCIPAL:-serviceAccount:pi-trading-agent@sapphire-479610.iam.gserviceaccount.com}"
AUTO_SIZE_NOTIONAL_USD="${AUTO_SIZE_NOTIONAL_USD:-25}"
FALLBACK_QTY="${FALLBACK_QTY:-0.01}"
DISABLE_CLOUD_ASTER="${DISABLE_CLOUD_ASTER:-true}"

sub_create_if_missing() {
  local name="$1"
  local topic="$2"
  if gcloud pubsub subscriptions describe "projects/${PROJECT_ID}/subscriptions/${name}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    echo "✅ Subscription exists: ${name}"
  else
    echo "➕ Creating subscription: ${name}"
    gcloud pubsub subscriptions create "${name}" \
      --project "${PROJECT_ID}" \
      --topic "${topic}" \
      --ack-deadline 60 >/dev/null
  fi
}

bind_role() {
  local role="$1"
  echo "🔐 Ensuring IAM role ${role} for ${EDGE_PRINCIPAL}"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member "${EDGE_PRINCIPAL}" \
    --role "${role}" \
    --condition=None \
    --quiet >/dev/null
}

echo "== rari2 ASTER Worker Deploy =="
echo "project=${PROJECT_ID} region=${REGION} host=${PI_HOST}"

sub_create_if_missing "trading-signals-bot-aster-pi-sub" "trading-signals"
sub_create_if_missing "risk-alerts-bot-aster-pi-sub" "risk-alerts"

bind_role "roles/pubsub.subscriber"
bind_role "roles/pubsub.publisher"

echo "📦 Syncing bot-aster source to rari2"
scp -q "${REPO_ROOT}/services/bot-aster/src/main.py" "${PI_HOST}:/home/rari/Sapphire/services/bot-aster/src/main.py"

echo "🛠 Installing systemd service on rari2"
ssh -o BatchMode=yes "${PI_HOST}" "cat > /tmp/sapphire-aster-pi.service <<'UNIT'
[Unit]
Description=Sapphire ASTER Bot (Pi execution worker)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rari
WorkingDirectory=/home/rari/Sapphire/services/bot-aster/src
EnvironmentFile=/home/rari/.openclaw/trading_api/.env
Environment=PYTHONPATH=/home/rari/Sapphire/services/shared:/home/rari/Sapphire/services/bot-aster/src
Environment=GCP_PROJECT_ID=${PROJECT_ID}
Environment=SERVICE_NAME=bot-aster-pi
Environment=PORT=18080
Environment=PAPER_TRADING=false
Environment=TRADING_ENABLED=true
Environment=ASTER_AUTO_SIZE_NOTIONAL_USD=${AUTO_SIZE_NOTIONAL_USD}
Environment=ASTER_AUTO_SIZE_FALLBACK_QUANTITY=${FALLBACK_QTY}
ExecStart=/home/rari/kimi-claw/venv/bin/python /home/rari/Sapphire/services/bot-aster/src/main.py
Restart=always
RestartSec=5
KillMode=control-group

[Install]
WantedBy=multi-user.target
UNIT
sudo mv /tmp/sapphire-aster-pi.service /etc/systemd/system/sapphire-aster-pi.service
sudo systemctl daemon-reload
sudo systemctl enable --now sapphire-aster-pi.service
sudo systemctl restart sapphire-aster-pi.service
sleep 2
sudo systemctl --no-pager --full status sapphire-aster-pi.service | sed -n '1,40p'
"

if [[ "${DISABLE_CLOUD_ASTER}" == "true" ]]; then
  echo "☁️ Setting cloud bot-aster TRADING_ENABLED=false"
  gcloud run services update sapphire-aster \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --update-env-vars TRADING_ENABLED=false >/dev/null
fi

echo "🔎 Probing Pi worker health"
ssh -o BatchMode=yes "${PI_HOST}" "
for i in 1 2 3 4 5 6; do
  if curl -fsS http://127.0.0.1:18080/health >/dev/null; then
    echo 'Pi worker health OK'
    exit 0
  fi
  sleep 2
done
echo 'Pi worker health check failed' >&2
exit 1
"

echo "✅ rari2 ASTER worker deploy complete"
