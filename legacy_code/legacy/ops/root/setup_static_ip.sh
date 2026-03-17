#!/bin/bash
set -e

REGION="us-central1"
NETWORK="sapphire-net"
SUBNET_NAME="sapphire-subnet-us"
ROUTER_NAME="sapphire-router-us"
NAT_NAME="sapphire-nat-us"
IP_NAME="sapphire-nat-ip-us"
CONNECTOR_NAME="sapphire-conn-us"
SERVICE_NAME="sapphire-v2"

echo "🚀 Setting up Static IP Infrastructure in $REGION..."

# 1. Create Subnet in us-central1 (Must be /28 for VPC Connector)
if gcloud compute networks subnets describe $SUBNET_NAME --region=$REGION --format="value(name)" &>/dev/null; then
    # Check mask
    RANGE=$(gcloud compute networks subnets describe $SUBNET_NAME --region=$REGION --format="value(ipCidrRange)")
    if [[ "$RANGE" != *"28" ]]; then
        echo "⚠️  Subnet $SUBNET_NAME is $RANGE (needs /28). Deleting..."
        gcloud compute networks subnets delete $SUBNET_NAME --region=$REGION --quiet
        echo "Creating subnet $SUBNET_NAME (/28)..."
        gcloud compute networks subnets create $SUBNET_NAME \
            --network=$NETWORK \
            --region=$REGION \
            --range=10.2.0.0/28
    else
        echo "✅ Subnet $SUBNET_NAME exists and is /28"
    fi
else
    echo "Creating subnet $SUBNET_NAME (/28)..."
    gcloud compute networks subnets create $SUBNET_NAME \
        --network=$NETWORK \
        --region=$REGION \
        --range=10.2.0.0/28
fi

# 2. Create VPC Connector
if ! gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME --region=$REGION --format="value(name)" &>/dev/null; then
    echo "Creating VPC Connector $CONNECTOR_NAME..."
    gcloud compute networks vpc-access connectors create $CONNECTOR_NAME \
        --region=$REGION \
        --subnet=$SUBNET_NAME \
        --min-instances=2 \
        --max-instances=3 \
        --machine-type=e2-micro
else
    echo "✅ VPC Connector $CONNECTOR_NAME exists"
fi

# 3. Create Cloud Router
if ! gcloud compute routers describe $ROUTER_NAME --region=$REGION --format="value(name)" &>/dev/null; then
    echo "Creating Router $ROUTER_NAME..."
    gcloud compute routers create $ROUTER_NAME \
        --network=$NETWORK \
        --region=$REGION
else
    echo "✅ Router $ROUTER_NAME exists"
fi

# 4. Reserve Static IP
if ! gcloud compute addresses describe $IP_NAME --region=$REGION --format="value(address)" &>/dev/null; then
    echo "Reserving Static IP $IP_NAME..."
    gcloud compute addresses create $IP_NAME --region=$REGION
else
    echo "✅ Static IP $IP_NAME exists"
fi

STATIC_IP=$(gcloud compute addresses describe $IP_NAME --region=$REGION --format="value(address)")
echo "🔑 YOUR STATIC IP IS: $STATIC_IP"

# 5. Create Cloud NAT
if ! gcloud compute routers nats describe $NAT_NAME --router=$ROUTER_NAME --region=$REGION --format="value(name)" &>/dev/null; then
    echo "Creating Cloud NAT $NAT_NAME..."
    gcloud compute routers nats create $NAT_NAME \
        --router=$ROUTER_NAME \
        --region=$REGION \
        --nat-custom-subnet-ip-ranges=$SUBNET_NAME \
        --nat-external-ip-pool=$IP_NAME
else
    echo "✅ Cloud NAT $NAT_NAME exists"
fi

# 6. Update Cloud Run
echo "🔄 Updating Cloud Run service to use VPC Connector..."
gcloud run services update $SERVICE_NAME \
    --region=$REGION \
    --vpc-connector=$CONNECTOR_NAME \
    --vpc-egress=all-traffic

echo "✅ DONE! Whitelist this IP on Aster/Binance: $STATIC_IP"
