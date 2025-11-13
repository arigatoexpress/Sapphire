#!/bin/bash

# This script deploys registered models from Vertex AI Model Registry to endpoints.
# It configures auto-scaling, traffic splitting, and monitoring.

set -e

# --- Configuration ---
PROJECT_ID="your-gcp-project"
REGION="us-central1"

# Model and Endpoint configurations
# Format: "MODEL_NAME;ENDPOINT_NAME;MACHINE_TYPE"
MODEL_CONFIGS=(
    "deepseek-v3;deepseek-v3-endpoint;n1-standard-4"
    "fingpt-alpha;fingpt-alpha-endpoint;n1-standard-4"
)

# Traffic splitting for A/B testing (optional)
# Format: "ENDPOINT_NAME;MODEL_NAME_A=TRAFFIC_A,MODEL_NAME_B=TRAFFIC_B"
# Example: "my-endpoint;model-a=50,model-b=50"
TRAFFIC_SPLIT_CONFIG=""

# --- Helper Functions ---
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# --- Main Deployment Logic ---
deploy_model_to_endpoint() {
    local model_name=$1
    local endpoint_name=$2
    local machine_type=$3

    log "Starting deployment for model '$model_name' to endpoint '$endpoint_name'ப்பான"

    # Check if the model is registered
    log "Checking if model '$model_name' is registered..."
    model_id=$(gcloud ai models list --region=$REGION --filter="displayName=$model_name" --format="value(name)")
    if [ -z "$model_id" ]; then
        log "ERROR: Model '$model_name' not found in Vertex AI Model Registry."
        return 1
    fi
    log "Model '$model_name' found with ID: $model_id"

    # Check if the endpoint exists
    log "Checking if endpoint '$endpoint_name' exists..."
    endpoint_id=$(gcloud ai endpoints list --region=$REGION --filter="displayName=$endpoint_name" --format="value(name)")
    if [ -z "$endpoint_id" ]; then
        log "Endpoint '$endpoint_name' not found. Creating a new endpoint..."
        gcloud ai endpoints create --project=$PROJECT_ID --region=$REGION --display-name=$endpoint_name
        endpoint_id=$(gcloud ai endpoints list --region=$REGION --filter="displayName=$endpoint_name" --format="value(name)")
        log "Endpoint '$endpoint_name' created with ID: $endpoint_id"
    else
        log "Endpoint '$endpoint_name' found with ID: $endpoint_id"
    fi

    # Deploy the model to the endpoint
    log "Deploying model '$model_name' to endpoint '$endpoint_name'ப்பான"
    gcloud ai endpoints deploy-model "$endpoint_id" \
        --project=$PROJECT_ID \
        --region=$REGION \
        --model="$model_id" \
        --display-name="$model_name" \
        --machine-type="$machine_type" \
        --min-replica-count=1 \
        --max-replica-count=10 \
        --traffic-split=0=100 # Start with 100% traffic to the new model if it's the only one

    log "Model '$model_name' deployed successfully to endpoint '$endpoint_name'."
}

# --- Traffic Splitting Logic ---
configure_traffic_splitting() {
    if [ -z "$TRAFFIC_SPLIT_CONFIG" ]; then
        log "No traffic splitting configuration provided. Skipping."
        return
    fi

    IFS=';' read -r endpoint_name split_details <<< "$TRAFFIC_SPLIT_CONFIG"
    log "Configuring traffic splitting for endpoint '$endpoint_name'ப்பான"

    endpoint_id=$(gcloud ai endpoints list --region=$REGION --filter="displayName=$endpoint_name" --format="value(name)")
    if [ -z "$endpoint_id" ]; then
        log "ERROR: Endpoint '$endpoint_name' for traffic splitting not found."
        return 1
    fi

    gcloud ai endpoints update "$endpoint_id" \
        --project=$PROJECT_ID \
        --region=$REGION \
        --traffic-split="$split_details"

    log "Traffic splitting configured for endpoint '$endpoint_name'."
}

# --- Monitoring and Alerting ---
setup_monitoring() {
    log "Monitoring and alerting setup is a manual process in the Google Cloud Console."
    log "Please go to the Vertex AI -> Endpoints section of the console to configure monitoring and alerting for your endpoints."
    log "You can set up alerts based on latency, error rate and other metrics."
}


# --- Script Execution ---
main() {
    log "Starting Vertex AI Endpoint Deployment Script..."

    for config in "${MODEL_CONFIGS[@]}"; do
        IFS=';' read -r model_name endpoint_name machine_type <<< "$config"
        deploy_model_to_endpoint "$model_name" "$endpoint_name" "$machine_type"
    done

    configure_traffic_splitting
    setup_monitoring

    log "Vertex AI Endpoint Deployment Script finished."
}

main
