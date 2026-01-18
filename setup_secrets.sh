#!/bin/bash
# Setup script to add Vertex AI API key to GCP Secret Manager
# This needs to be run once to configure the secret

PROJECT_ID="sapphire-479610"
VERTEX_API_KEY="AQ.Ab8RN6I597VxAgJeuNe7zinjSZTYktpb536gjZCFQwsS4Z1_LQ"

echo "🔐 Adding VERTEX_API_KEY to GCP Secret Manager..."

# Check if secret exists
if gcloud secrets describe vertex_api_key_v1 --project=$PROJECT_ID &>/dev/null; then
    echo "Secret exists, adding new version..."
    echo -n "$VERTEX_API_KEY" | gcloud secrets versions add vertex_api_key_v1 \
        --project=$PROJECT_ID \
        --data-file=-
else
    echo "Creating new secret..."
    echo -n "$VERTEX_API_KEY" | gcloud secrets create vertex_api_key_v1 \
        --project=$PROJECT_ID \
        --data-file=- \
        --replication-policy="automatic"
fi

echo "✅ Vertex API key configured in Secret Manager"
echo ""
echo "Verifying secret..."
gcloud secrets versions access latest --secret=vertex_api_key_v1 --project=$PROJECT_ID | head -c 10
echo "..."
