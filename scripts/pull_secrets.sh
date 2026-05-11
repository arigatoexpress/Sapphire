#!/usr/bin/env bash
# Sapphire OS — Pull secrets from GCP Secret Manager to local files
# Run this after re-enabling GCP billing on sapphire-479610
#
# Stores secrets in ~/.config/sapphire-secrets/ (gitignored)

set -euo pipefail

PROJECT="sapphire-479610"
SECRETS_DIR="$HOME/.config/sapphire-secrets"
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

echo "Pulling secrets from GCP Secret Manager ($PROJECT)..."

SECRETS=(
  "TELEGRAM_BOT_TOKEN:telegram_bot_token"
  "TELEGRAM_CHAT_ID:telegram_chat_id"
  "SAPPHIRE_CONTROL_API_TOKEN:control_api_token"
  "ANTHROPIC_API_KEY:anthropic_api_key"
)

for entry in "${SECRETS[@]}"; do
  gcp_name="${entry%%:*}"
  local_name="${entry##*:}"
  local_path="$SECRETS_DIR/$local_name"

  echo -n "  $gcp_name → $local_name ... "
  if gcloud secrets versions access latest --secret="$gcp_name" --project="$PROJECT" > "$local_path" 2>/dev/null; then
    chmod 600 "$local_path"
    echo "OK"
  else
    echo "FAILED (secret may not exist or billing still disabled)"
  fi
done

echo ""
echo "Done. Secrets stored in $SECRETS_DIR"
echo "Draft Telegram check: ./telegram_notify.sh 'Secrets pulled successfully' p2"
