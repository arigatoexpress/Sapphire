#!/bin/bash
# Deploy Sapphire Trading Monitor to Raspberry Pi
# Copies monitoring scripts and integrates with trading system

set -e

PI_HOST="rari2"
PI_USER="aribs"
PI_DIR="/home/aribs/sapphire_trading_monitor"

echo "🚀 Deploying Sapphire Trading Monitor to Pi..."

# Check if we can reach the Pi
if ! ping -c 1 -W 2 "$PI_HOST" &>/dev/null; then
    echo "⚠️ Cannot reach Pi at $PI_HOST"
    echo "Make sure you're connected to the Pi's network"
    exit 1
fi

# Create directory on Pi
echo "📁 Creating directory on Pi..."
ssh "$PI_USER@$PI_HOST" "mkdir -p $PI_DIR"

# Copy scripts
echo "📦 Copying monitoring scripts..."
scp -q *.py "$PI_USER@$PI_HOST:$PI_DIR/"

# Make executable
ssh "$PI_USER@$PI_HOST" "chmod +x $PI_DIR/*.py"

# Install dependencies
echo "📥 Installing dependencies..."
ssh "$PI_USER@$PI_HOST" "pip3 install requests --user -q" || true

# Create trading-logs symlink if needed
ssh "$PI_USER@$PI_HOST" "mkdir -p ~/trading-logs"

# Run setup on Pi
echo "🔧 Running setup on Pi..."
ssh "$PI_USER@$PI_HOST" "cd $PI_DIR && ./setup.sh" || true

# Test the bot
echo "🧪 Testing bot commands..."
ssh "$PI_USER@$PI_HOST" "cd $PI_DIR && python3 telegram_bot_controller.py --command /status" || true

echo ""
echo "✅ Deployment complete!"
echo ""
echo "On the Pi, you can now run:"
echo "  cd $PI_DIR"
echo "  ./dashboard.py                 # Live dashboard"
echo "  ./telegram_bot_controller.py -i  # Interactive bot test"
echo ""
echo "Telegram commands available:"
echo "  /status    - System status"
echo "  /positions - Current positions"
echo "  /pnl       - P&L report"
echo "  /trades    - Recent trades"
echo "  /health    - Health check"
echo "  /mode      - Check trading mode"
echo ""
