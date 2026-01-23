#!/bin/bash
# Setup PubSub infrastructure for Sapphire microservices
# Run this before deploying services

set -e

PROJECT_ID="${GCP_PROJECT_ID:-sapphire-trading-prod}"
TOPIC_NAME="sapphire-service-events"
SUBSCRIPTION_NAME="sapphire-web-events"

echo "🔧 Setting up PubSub infrastructure for project: $PROJECT_ID"

# Create topic if it doesn't exist
if gcloud pubsub topics describe "$TOPIC_NAME" --project="$PROJECT_ID" &>/dev/null; then
    echo "✅ Topic $TOPIC_NAME already exists"
else
    echo "📡 Creating topic: $TOPIC_NAME"
    gcloud pubsub topics create "$TOPIC_NAME" \
        --project="$PROJECT_ID" \
        --message-retention-duration=7d
    echo "✅ Topic created successfully"
fi

# Create subscription for sapphire-web if it doesn't exist
if gcloud pubsub subscriptions describe "$SUBSCRIPTION_NAME" --project="$PROJECT_ID" &>/dev/null; then
    echo "✅ Subscription $SUBSCRIPTION_NAME already exists"
else
    echo "📡 Creating subscription: $SUBSCRIPTION_NAME"
    gcloud pubsub subscriptions create "$SUBSCRIPTION_NAME" \
        --topic="$TOPIC_NAME" \
        --project="$PROJECT_ID" \
        --ack-deadline=60 \
        --message-retention-duration=7d \
        --expiration-period=never
    echo "✅ Subscription created successfully"
fi

echo ""
echo "✅ PubSub setup complete!"
echo ""
echo "Topic: projects/$PROJECT_ID/topics/$TOPIC_NAME"
echo "Subscription: projects/$PROJECT_ID/subscriptions/$SUBSCRIPTION_NAME"
echo ""
echo "Next steps:"
echo "1. Deploy services using: gcloud builds submit --config=cloudbuild_microservices.yaml"
echo "2. Verify events: gcloud pubsub subscriptions pull $SUBSCRIPTION_NAME --limit=10"
