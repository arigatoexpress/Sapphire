#!/bin/bash
# Run Command Deck v3.0 locally for testing

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Sapphire Command Deck v3.0 - Local Development           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Configuration
export GCP_PROJECT="sapphire-479610"
export GCP_REGION="us-central1"
export PORT="${PORT:-8082}"

# Service URLs
export GATEWAY_URL="https://sapphire-gateway-267358751314.us-central1.run.app"
export PM_HUB_URL="https://agentic-pm-hub-267358751314.us-central1.run.app"
export LOG_VIEWER_URL="https://sapphire-log-viewer-267358751314.us-central1.run.app"

# Auth (disable for local testing)
export ENABLE_AUTH="${ENABLE_AUTH:-false}"
export AUTH_USERNAME="sapphire"
export AUTH_PASSWORD="alpha2024"

# Cache
export CACHE_DURATION="10"

echo "Configuration:"
echo "  Project: $GCP_PROJECT"
echo "  Port: $PORT"
echo "  Auth: $ENABLE_AUTH"
echo "  PM Hub: $PM_HUB_URL"
echo ""

# Check for gcloud credentials
if [ -f "$HOME/.config/gcloud/application_default_credentials.json" ]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/application_default_credentials.json"
    echo "✓ Using gcloud credentials"
elif [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "✓ Using credentials from GOOGLE_APPLICATION_CREDENTIALS"
else
    echo "⚠ No credentials found. Running with mock data..."
    echo "  Set GOOGLE_APPLICATION_CREDENTIALS or run 'gcloud auth application-default login'"
fi

echo ""
echo "Starting server on http://localhost:$PORT"
echo ""
echo "Test endpoints:"
echo "  Health:     curl http://localhost:$PORT/health"
echo "  Dashboard:  curl http://localhost:$PORT/api/dashboard"
echo "  Status:     curl http://localhost:$PORT/api/status"
echo "  PM Tasks:   curl http://localhost:$PORT/api/pm/tasks"
echo ""

# Run with Flask development server
python3 app.py

# Or use gunicorn for production-like testing:
# gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60 app:app
