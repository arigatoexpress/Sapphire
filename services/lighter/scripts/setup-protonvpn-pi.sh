#!/bin/bash
# ProtonVPN Setup for Raspberry Pi - Lighter Trading Bot
# This script sets up ProtonVPN on the Pi to bypass US geofencing

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run with sudo"
    exit 1
fi

echo ""
echo "=============================================="
echo "🚀 ProtonVPN Setup for Lighter Trading Bot"
echo "=============================================="
echo ""

# Update system
log_info "Updating system packages..."
apt update && apt upgrade -y
log_success "System updated"

# Install required dependencies
log_info "Installing dependencies..."
apt install -y \
    openvpn \
    dialog \
    python3-pip \
    python3-venv \
    wireguard-tools \
    resolvconf \
    curl \
    jq
log_success "Dependencies installed"

# Install ProtonVPN CLI
log_info "Installing ProtonVPN CLI..."
pip3 install protonvpn-cli || pip3 install protonvpn-gui
log_success "ProtonVPN CLI installed"

# Create ProtonVPN credentials file
log_info "Setting up ProtonVPN credentials..."
mkdir -p /etc/protonvpn

# Check if credentials exist in environment or prompt
if [ -z "$PROTONVPN_USERNAME" ] || [ -z "$PROTONVPN_PASSWORD" ]; then
    log_warning "ProtonVPN credentials not found in environment"
    echo ""
    echo "Please enter your ProtonVPN credentials:"
    echo "(You can get these from https://account.protonvpn.com/account#openvpn)"
    echo ""
    read -p "OpenVPN Username: " PROTONVPN_USERNAME
    read -s -p "OpenVPN Password: " PROTONVPN_PASSWORD
    echo ""
fi

# Store credentials securely
cat > /etc/protonvpn/credentials << EOF
$PROTONVPN_USERNAME
$PROTONVPN_PASSWORD
EOF
chmod 600 /etc/protonvpn/credentials
log_success "Credentials stored securely"

# Initialize ProtonVPN
log_info "Initializing ProtonVPN..."
protonvpn-cli init --config /etc/protonvpn/credentials << EOF
1
EOF
log_success "ProtonVPN initialized"

# Create VPN connection script for trading bot
cat > /usr/local/bin/protonvpn-trading << 'EOF'
#!/bin/bash
# ProtonVPN connection manager for trading bot

ACTION=$1
LOG_FILE="/var/log/protonvpn-trading.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

case "$ACTION" in
    connect)
        log "Connecting to ProtonVPN for trading..."
        # Connect to a specific country (e.g., Netherlands, Switzerland, Singapore)
        # Using Netherlands for low latency to European exchanges
        protonvpn-cli connect NL || protonvpn-cli c --cc NL
        
        # Wait for connection
        sleep 5
        
        # Verify connection
        if protonvpn-cli status | grep -q "Connected"; then
            IP=$(curl -s https://ipinfo.io/ip)
            COUNTRY=$(curl -s https://ipinfo.io/country)
            log "✅ Connected! IP: $IP ($COUNTRY)"
            exit 0
        else
            log "❌ Failed to connect"
            exit 1
        fi
        ;;
        
    disconnect)
        log "Disconnecting ProtonVPN..."
        protonvpn-cli disconnect
        log "Disconnected"
        ;;
        
    status)
        protonvpn-cli status
        curl -s https://ipinfo.io | jq -r '.ip, .city, .country'
        ;;
        
    *)
        echo "Usage: $0 {connect|disconnect|status}"
        exit 1
        ;;
esac
EOF
chmod +x /usr/local/bin/protonvpn-trading
log_success "VPN management script created"

# Create systemd service for VPN + Bot
cat > /etc/systemd/system/lighter-trading.service << 'EOF'
[Unit]
Description=Lighter Trading Bot with ProtonVPN
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=pi
Group=pi
WorkingDirectory=/home/pi/bot-lighter

# Pre-start: Connect VPN
ExecStartPre=/usr/local/bin/protonvpn-trading connect
ExecStartPre=/bin/sleep 10

# Main service
Environment="PATH=/home/pi/bot-lighter/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/home/pi/bot-lighter"
EnvironmentFile=/home/pi/bot-lighter/.env
ExecStart=/home/pi/bot-lighter/venv/bin/python -m src.main

# Post-stop: Disconnect VPN
ExecStopPost=/usr/local/bin/protonvpn-trading disconnect

Restart=always
RestartSec=30

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=false
ReadWritePaths=/home/pi/bot-lighter/logs

[Install]
WantedBy=multi-user.target
EOF
log_success "Systemd service created"

# Create kill-switch script (prevent trading without VPN)
cat > /usr/local/bin/vpn-killswitch << 'EOF'
#!/bin/bash
# VPN Kill Switch - Prevents trading if VPN disconnects

LOG_FILE="/var/log/lighter-trading.log"
BOT_SERVICE="lighter-trading.service"

check_vpn() {
    if ! protonvpn-cli status | grep -q "Connected"; then
        echo "[$(date)] 🔒 VPN DISCONNECTED - Stopping trading bot" | tee -a "$LOG_FILE"
        systemctl stop $BOT_SERVICE
        return 1
    fi
    return 0
}

# Run check every 30 seconds
while true; do
    if ! check_vpn; then
        # Try to reconnect
        echo "[$(date)] Attempting VPN reconnection..." | tee -a "$LOG_FILE"
        protonvpn-cli reconnect
        sleep 10
        
        if protonvpn-cli status | grep -q "Connected"; then
            echo "[$(date)] ✅ VPN reconnected - Restarting bot" | tee -a "$LOG_FILE"
            systemctl start $BOT_SERVICE
        fi
    fi
    sleep 30
done
EOF
chmod +x /usr/local/bin/vpn-killswitch

# Create kill-switch service
cat > /etc/systemd/system/vpn-killswitch.service << 'EOF'
[Unit]
Description=VPN Kill Switch for Trading Bot
After=lighter-trading.service

[Service]
Type=simple
ExecStart=/usr/local/bin/vpn-killswitch
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Create log directory
mkdir -p /var/log/lighter-trading
chown pi:pi /var/log/lighter-trading

echo ""
echo "=============================================="
echo -e "${GREEN}🎉 ProtonVPN Setup Complete!${NC}"
echo "=============================================="
echo ""
echo "Next Steps:"
echo "1. Copy your bot-lighter code to /home/pi/bot-lighter"
echo "2. Create .env file with API credentials"
echo "3. Enable services:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable lighter-trading vpn-killswitch"
echo ""
echo "4. Start trading bot:"
echo "   sudo systemctl start lighter-trading"
echo ""
echo "Commands:"
echo "  protonvpn-trading connect    - Connect VPN"
echo "  protonvpn-trading disconnect - Disconnect VPN"
echo "  protonvpn-trading status     - Check status"
echo "  sudo systemctl status lighter-trading - Check bot"
echo ""
echo "🛡️  Kill Switch: Bot will auto-stop if VPN disconnects"
echo ""
