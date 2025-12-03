#!/bin/bash
set -e

echo "🚀 Starting Local Debug Environment..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  WARNING: .env file not found!"
    echo "Please create .env with ASTER_API_KEY and ASTER_SECRET_KEY."
    exit 1
fi

# Set DEV_MODE to enable hot-reload
export DEV_MODE=true

# Build minimal image
echo "🔨 Building minimal image..."
docker build -t cloud-trader:minimal -f Dockerfile.minimal .

# Sanitize .env file (remove quotes)
sed -E 's/^([^=]+)="([^"]*)"$/\1=\2/' .env > .env.clean

# Run container
echo "🐳 Starting Minimal Cloud Trader..."
docker run --rm -it \
  -p 8080:8080 \
  --env-file .env.clean \
  -e DEV_MODE=true \
  --name cloud-trader-debug \
  cloud-trader:minimal

# Cleanup
rm .env.clean
