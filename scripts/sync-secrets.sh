#!/bin/bash
set -e

echo "🔐 Syncing secrets from GCP Secret Manager..."

# Ensure namespace exists
kubectl create namespace trading --dry-run=client -o yaml | kubectl apply -f -

# Function to get secret with error handling
get_secret() {
    local secret_name="$1"
    local value
    value=$(gcloud secrets versions access latest --secret="$secret_name" --project=sapphireinfinite 2>/dev/null)
    if [ -z "$value" ]; then
        echo "⚠️  Warning: Secret $secret_name is empty or not found" >&2
        echo ""
    else
        echo "$value"
    fi
}

# Delete existing secret first to avoid merge conflicts with Helm
echo "🗑️  Removing existing secret (if any)..."
kubectl delete secret cloud-trader-secrets -n trading --ignore-not-found

# Fetch secrets
echo "📥 Fetching secrets from GCP Secret Manager..."
echo "  - Fetching DATABASE_URL..."
DATABASE_URL=$(get_secret DATABASE_URL)
echo "  - Fetching DB_PASSWORD..."
DB_PASSWORD=$(get_secret DB_PASSWORD)
echo "  - Fetching ASTER_API_KEY..."
ASTER_API_KEY=$(get_secret ASTER_API_KEY)
echo "  - Fetching ASTER_SECRET_KEY..."
ASTER_SECRET_KEY=$(get_secret ASTER_SECRET_KEY)
echo "  - Fetching TELEGRAM_BOT_TOKEN..."
TELEGRAM_BOT_TOKEN=$(get_secret TELEGRAM_BOT_TOKEN)
echo "  - Fetching TELEGRAM_CHAT_ID..."
TELEGRAM_CHAT_ID=$(get_secret TELEGRAM_CHAT_ID)
echo "  - Fetching GROK4_API_KEY..."
GROK4_API_KEY=$(get_secret GROK4_API_KEY)

# Create fresh Kubernetes secret (NOT using dry-run + apply, direct create)
echo "📦 Creating Kubernetes secret..."
kubectl create secret generic cloud-trader-secrets \
    --from-literal=DATABASE_URL="$DATABASE_URL" \
    --from-literal=DB_PASSWORD="$DB_PASSWORD" \
    --from-literal=ASTER_API_KEY="$ASTER_API_KEY" \
    --from-literal=ASTER_SECRET_KEY="$ASTER_SECRET_KEY" \
    --from-literal=TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
    --from-literal=TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
    --from-literal=GROK4_API_KEY="$GROK4_API_KEY" \
    -n trading

# Verification step
echo "🔍 Verifying secret creation..."
SECRET_DATA=$(kubectl get secret cloud-trader-secrets -n trading -o jsonpath='{.data}' 2>/dev/null)

if [ -z "$SECRET_DATA" ] || [ "$SECRET_DATA" == "{}" ]; then
    echo "❌ ERROR: Secret was created but has no data!"
    exit 1
fi

# Check that DATABASE_URL exists and has content
DB_URL_CHECK=$(kubectl get secret cloud-trader-secrets -n trading -o jsonpath='{.data.DATABASE_URL}' | base64 -d 2>/dev/null)
if [ -z "$DB_URL_CHECK" ]; then
    echo "❌ ERROR: DATABASE_URL is empty in secret!"
    exit 1
fi

echo "✅ Secrets synced and verified successfully!"
echo "   - DATABASE_URL: $(echo "$DB_URL_CHECK" | head -c 30)..."
echo "   - Total keys in secret: $(echo "$SECRET_DATA" | grep -o '"[^"]*":' | wc -l | tr -d ' ')"
