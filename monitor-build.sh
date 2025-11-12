#!/bin/bash

echo "🔍 Monitoring Sapphire MVP Build & Deploy..."

BUILD_ID="19b8a834-6b96-473e-8d39-1ade983ccf07"
PROJECT_ID="sapphireinfinite"

while true; do
    STATUS=$(gcloud builds describe $BUILD_ID --project=$PROJECT_ID --format="value(status)")

    echo "$(date): Build status: $STATUS"

    if [ "$STATUS" = "SUCCESS" ]; then
        echo "✅ Build completed successfully!"
        echo "🚀 Running smoke tests..."
        ./smoke-test.sh
        break
    elif [ "$STATUS" = "FAILURE" ] || [ "$STATUS" = "CANCELLED" ] || [ "$STATUS" = "TIMEOUT" ]; then
        echo "❌ Build failed with status: $STATUS"
        gcloud builds log $BUILD_ID --project=$PROJECT_ID | tail -50
        break
    fi

    sleep 30
done
