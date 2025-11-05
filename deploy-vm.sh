#!/bin/bash
set -e

PROJECT_ID="quant-ai-trader-credits"
ZONE="us-central1-a"
INSTANCE_NAME="sapphire-trader-vm-live"

echo "=== Deploying to Compute Engine VM ==="

# Create a VM with Container-Optimized OS
gcloud compute instances create $INSTANCE_NAME \
    --project=$PROJECT_ID \
    --zone=$ZONE \
    --machine-type=e2-medium \
    --service-account="sapphire@$PROJECT_ID.iam.gserviceaccount.com" \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --network-interface=network-tier=PREMIUM,subnet=default \
    --metadata=google-logging-enabled=true \
    --maintenance-policy=MIGRATE \
    --provisioning-model=STANDARD \
    --tags=http-server,https-server \
    --create-disk=auto-delete=yes,boot=yes,device-name=$INSTANCE_NAME,image-project=cos-cloud,image-family=cos-stable,mode=rw,size=10,type=pd-balanced \
    --no-shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring \
    --reservation-affinity=any

# Create firewall rules if they don't exist
gcloud compute firewall-rules create default-allow-http \
    --project=$PROJECT_ID \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:80 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=http-server || echo "Rule exists"

gcloud compute firewall-rules create default-allow-https \
    --project=$PROJECT_ID \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:443 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=https-server || echo "Rule exists"

gcloud compute firewall-rules create allow-8080 \
    --project=$PROJECT_ID \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:8080 \
    --source-ranges=0.0.0.0/0 || echo "Rule exists"

# Get the external IP
EXTERNAL_IP=$(gcloud compute instances describe $INSTANCE_NAME \
    --project=$PROJECT_ID \
    --zone=$ZONE \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "VM created with IP: $EXTERNAL_IP"

# SSH into the VM and run our container
echo "Starting container on VM..."
gcloud compute ssh $INSTANCE_NAME \
    --project=$PROJECT_ID \
    --zone=$ZONE \
    --command="docker run -d -p 8080:8080 -e GCP_PROJECT_ID=$PROJECT_ID -e ENABLE_PAPER_TRADING=false --restart always gcr.io/$PROJECT_ID/cloud-trader:minimal"

echo "=== Deployment Complete ==="
echo "API endpoint: http://$EXTERNAL_IP:8080"
echo "Health check: http://$EXTERNAL_IP:8080/healthz"
