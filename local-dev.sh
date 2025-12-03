#!/bin/bash

# Sapphire AI Local Development Script
echo "🚀 Starting Sapphire AI Local Development Environment"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

echo "✅ Docker is running"

# Create logs directory
mkdir -p logs

echo "🔧 Starting services with Docker Compose..."
docker-compose up -d

echo "⏳ Waiting for services to be ready..."
sleep 10

echo "🎉 Services started!"
echo ""
echo "🌐 Access your services:"
echo "   🚀 API: http://localhost:8080"
echo "   📝 Docs: http://localhost:8080/docs"
echo ""
echo "🛠️  Commands:"
echo "   📋 Logs: docker-compose logs -f"
echo "   🛑 Stop: docker-compose down"