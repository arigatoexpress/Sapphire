#!/bin/bash

# EMERGENCY STOP - Switch back to paper trading immediately
echo "🚨 EMERGENCY STOP - Switching back to PAPER TRADING"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Backup current config
cp local.env local.env.live-backup 2>/dev/null || true

# Restore paper trading config
cp local.env.paper-backup local.env

# Stop and restart with paper trading
docker-compose down
docker-compose up -d

echo "✅ Switched back to PAPER TRADING mode"
echo "📊 Check status: docker-compose ps"
echo "🌐 Dashboard: http://localhost:3000"
