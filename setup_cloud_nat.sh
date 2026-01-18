#!/bin/bash
# Setup Cloud NAT with Static IP for Sapphire V2 Trading System
# This ensures all Cloud Run egress traffic uses a consistent static IP
# for whitelisting on exchange APIs (Aster, etc.)

set -e

PROJECT_ID="sapphire-479610"
REGION="us-central1"
VPC_NAME="sapphire-vpc"
SUBNET_NAME="sapphire-subnet"
CONNECTOR_NAME="sapphire-conn-us"
ROUTER_NAME="sapphire-nat-router"
NAT_NAME="sapphire-nat"
STATIC_IP_NAME="sapphire-static-ip"

echo "🚀 Setting up Cloud NAT with Static IP for Sapphire V2"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Step 1: Check if VPC exists, if not create it
echo "📡 Step 1: Checking VPC network..."
if gcloud compute networks describe $VPC_NAME --project=$PROJECT_ID &>/dev/null; then
    echo "✅ VPC $VPC_NAME already exists"
else
    echo "Creating VPC $VPC_NAME..."
    gcloud compute networks create $VPC_NAME \
        --project=$PROJECT_ID \
        --subnet-mode=custom \
        --bgp-routing-mode=regional
    echo "✅ VPC created"
fi

# Step 2: Check if subnet exists, if not create it
echo ""
echo "🌐 Step 2: Checking subnet..."
if gcloud compute networks subnets describe $SUBNET_NAME --region=$REGION --project=$PROJECT_ID &>/dev/null; then
    echo "✅ Subnet $SUBNET_NAME already exists"
else
    echo "Creating subnet $SUBNET_NAME..."
    gcloud compute networks subnets create $SUBNET_NAME \
        --project=$PROJECT_ID \
        --network=$VPC_NAME \
        --region=$REGION \
        --range=10.8.0.0/28
    echo "✅ Subnet created"
fi

# Step 3: Check if VPC connector exists, if not create it
echo ""
echo "🔌 Step 3: Checking Serverless VPC Connector..."
if gcloud compute networks vpc-access connectors describe $CONNECTOR_NAME --region=$REGION --project=$PROJECT_ID &>/dev/null; then
    echo "✅ VPC Connector $CONNECTOR_NAME already exists"
else
    echo "Creating VPC Connector $CONNECTOR_NAME..."
    gcloud compute networks vpc-access connectors create $CONNECTOR_NAME \
        --project=$PROJECT_ID \
        --region=$REGION \
        --network=$VPC_NAME \
        --range=10.8.0.0/28 \
        --min-instances=2 \
        --max-instances=10 \
        --machine-type=e2-micro
    echo "✅ VPC Connector created"
fi

# Step 4: Reserve static IP address
echo ""
echo "🏠 Step 4: Reserving static IP address..."
if gcloud compute addresses describe $STATIC_IP_NAME --region=$REGION --project=$PROJECT_ID &>/dev/null; then
    STATIC_IP=$(gcloud compute addresses describe $STATIC_IP_NAME --region=$REGION --project=$PROJECT_ID --format="get(address)")
    echo "✅ Static IP already exists: $STATIC_IP"
else
    echo "Reserving new static IP..."
    gcloud compute addresses create $STATIC_IP_NAME \
        --project=$PROJECT_ID \
        --region=$REGION

    STATIC_IP=$(gcloud compute addresses describe $STATIC_IP_NAME --region=$REGION --project=$PROJECT_ID --format="get(address)")
    echo "✅ Static IP reserved: $STATIC_IP"
fi

# Step 5: Create Cloud Router
echo ""
echo "🔀 Step 5: Creating Cloud Router..."
if gcloud compute routers describe $ROUTER_NAME --region=$REGION --project=$PROJECT_ID &>/dev/null; then
    echo "✅ Router $ROUTER_NAME already exists"
else
    echo "Creating router..."
    gcloud compute routers create $ROUTER_NAME \
        --project=$PROJECT_ID \
        --network=$VPC_NAME \
        --region=$REGION
    echo "✅ Router created"
fi

# Step 6: Create Cloud NAT with static IP
echo ""
echo "🌍 Step 6: Configuring Cloud NAT..."
if gcloud compute routers nats describe $NAT_NAME --router=$ROUTER_NAME --region=$REGION --project=$PROJECT_ID &>/dev/null; then
    echo "⚠️  NAT $NAT_NAME already exists, updating..."
    gcloud compute routers nats update $NAT_NAME \
        --router=$ROUTER_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --nat-external-ip-pool=$STATIC_IP_NAME \
        --nat-all-subnet-ip-ranges
else
    echo "Creating Cloud NAT..."
    gcloud compute routers nats create $NAT_NAME \
        --router=$ROUTER_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --nat-external-ip-pool=$STATIC_IP_NAME \
        --nat-all-subnet-ip-ranges \
        --enable-logging
    echo "✅ Cloud NAT created"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Cloud NAT Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📌 Your Static IP Address: $STATIC_IP"
echo ""
echo "🔑 Action Required:"
echo "   1. Whitelist this IP in your Aster API settings"
echo "   2. Add this IP to any other exchange API whitelists"
echo ""
echo "🚀 Next Steps:"
echo "   1. Deploy Cloud Run service with VPC connector"
echo "   2. All egress traffic will use: $STATIC_IP"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
