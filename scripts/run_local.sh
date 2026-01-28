#!/bin/bash
# run_local.sh
# Local development script for Sapphire V2 on Linux/macOS
# Usage: ./scripts/run_local.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Sapphire V2 Local Development ==="
echo "Project Directory: $PROJECT_DIR"

cd "$PROJECT_DIR"

# Check for .env.local
if [ ! -f ".env.local" ]; then
    echo "WARNING: .env.local not found. Creating from template..."
    if [ -f ".env.local.template" ]; then
        cp ".env.local.template" ".env.local"
        echo "Created .env.local from template. Please edit it with your API keys."
        echo "Then run this script again."
        exit 1
    else
        echo "ERROR: .env.local.template not found!"
        exit 1
    fi
fi

# Parse arguments
SKIP_DOCKER=false
DEBUG=false
PORT=8080

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-docker)
            SKIP_DOCKER=true
            shift
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Start infrastructure if not skipped
if [ "$SKIP_DOCKER" = false ]; then
    echo ""
    echo "Starting local infrastructure (Redis, PubSub)..."

    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo "ERROR: Docker is not running. Please start Docker."
        exit 1
    fi

    # Start docker-compose
    docker-compose -f docker-compose.local.yml up -d

    # Wait for services to be ready
    echo "Waiting for services to start..."
    sleep 3

    # Check Redis
    if docker exec sapphire-redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        echo "  Redis: OK"
    else
        echo "  Redis: Starting..."
    fi
fi

# Load environment variables from .env.local
echo ""
echo "Loading environment from .env.local..."
export $(grep -v '^#' .env.local | xargs)

# Set local overrides
export REDIS_HOST=localhost
export REDIS_PORT=6379
export PUBSUB_EMULATOR_HOST=localhost:8085

# Run the application
echo ""
echo "Starting Sapphire V2 on port $PORT..."
echo "Health check: http://localhost:$PORT/health"
echo "API docs: http://localhost:$PORT/docs"
echo "Press Ctrl+C to stop"
echo ""

if [ "$DEBUG" = true ]; then
    export LOG_LEVEL=DEBUG
    python -m uvicorn cloud_trader.api:app --reload --port $PORT --log-level debug
else
    python -m uvicorn cloud_trader.api:app --reload --port $PORT
fi
