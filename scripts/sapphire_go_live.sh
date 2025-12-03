#!/bin/bash
set -e

# Configuration
PROJECT_ID="sapphire-479610"
REGION="us-east1"
REPO_NAME="sapphire-repo"
REPO_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"

echo "🚀 Starting Sapphire AI 2.0 Migration to GCP..."

# 1. Infrastructure Provisioning
echo "🏗️  Provisioning Infrastructure with Terraform..."
cd terraform
terraform init
# Enable APIs first
terraform apply -target=google_project_service.project_services -auto-approve
echo "Waiting for APIs to enable..."
sleep 30

# Provision Infrastructure (Repo, Network, DB, Redis, Secrets)
# We exclude Cloud Run services for now because images aren't pushed yet
terraform apply \
  -target=google_artifact_registry_repository.sapphire_repo \
  -target=google_compute_network.sapphire_net \
  -target=google_compute_subnetwork.sapphire_subnet \
  -target=google_vpc_access_connector.sapphire_connector \
  -target=google_sql_database_instance.sapphire_db \
  -target=google_sql_database.trading_db \
  -target=google_sql_user.trading_user \
  -target=google_redis_instance.sapphire_cache \
  -target=google_secret_manager_secret.secrets \
  -target=google_storage_bucket.sapphire_history \
  -auto-approve
cd ..

echo "✅ Infrastructure Provisioned!"
echo "⚠️  IMPORTANT: Please ensure you have populated the secrets in GCP Secret Manager:"
echo "   - HL_SECRET_KEY"
echo "   - ASTER_SECRET_KEY"
echo "   - GROK_API_KEY"
echo "   - GEMINI_API_KEY"
echo "   - ASTER_API_KEY"
# read -p "Press Enter to continue once secrets are set (or if you want to proceed anyway)..."

# 2. Build and Push Images
echo "🐳 Building and Pushing Docker Images via Cloud Build..."
gcloud builds submit --project $PROJECT_ID --config cloudbuild.yaml .

echo "✅ Images Pushed to Artifact Registry!"

# 3. Deploy Services (via Terraform)
# We already applied Terraform which includes the Cloud Run services, 
# but we need to make sure they pick up the new images if they were just created.
# Re-running apply will ensure the services are in the desired state.

echo "🚀 Deploying Services..."
cd terraform
terraform apply -auto-approve
cd ..

echo "✅ Deployment Complete!"

# 4. Output URLs
echo "🔍 Verifying Deployment..."
CLOUD_TRADER_URL=$(gcloud run services describe sapphire-cloud-trader --region ${REGION} --format 'value(status.url)')
DASHBOARD_URL=$(gcloud run services describe sapphire-dashboard --region ${REGION} --format 'value(status.url)')

echo "🎉 Sapphire AI 2.0 is LIVE!"
echo "------------------------------------------------"
echo "Cloud Trader API: $CLOUD_TRADER_URL"
echo "Dashboard:        $DASHBOARD_URL"
echo "------------------------------------------------"
