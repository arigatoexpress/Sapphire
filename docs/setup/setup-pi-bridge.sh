#!/bin/bash
# Raspberry Pi Ethernet Bridge Setup Script
# Run this ON THE PI to share WiFi internet over Ethernet

set -e

echo "🚀 Setting up Raspberry Pi as Ethernet Bridge"
echo "=============================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    log_warning "This script needs to run with sudo"
    echo "Please run: sudo ./setup-pi-bridge.sh"
    exit 1
fi

# Check interfaces
log_info "Checking network interfaces..."
WIFI_INTERFACE=$(iw dev | grep Interface | awk '{print $2}')
ETH_INTERFACE=$(ip link show | grep -E "eth[0-9]|enx" | awk -F: '{print $2}' | tr -d ' ' | head -1)

if [ -z "$WIFI_INTERFACE" ]; then
    log_warning "No WiFi interface found!"
    exit 1
fi

if [ -z "$ETH_INTERFACE" ]; then
    log_warning "No Ethernet interface found!"
    exit 1
fi

log_success "WiFi: $WIFI_INTERFACE"
log_success "Ethernet: $ETH_INTERFACE"

# Check WiFi has internet
log_info "Checking internet connectivity..."
if ping -c 1 -W 3 8.8.8.8 &> /dev/null; then
    log_success "Pi has internet connection"
else
    log_warning "Pi doesn't have internet. Connect WiFi first:"
    echo "  sudo raspi-config"
    exit 1
fi

# Enable IP forwarding
log_info "Enabling IP forwarding..."
echo 1 > /proc/sys/net/ipv4/ip_forward
sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
log_success "IP forwarding enabled"

# Install required packages
log_info "Installing required packages..."
apt update -qq
apt install -y -qq dnsmasq iptables-persistent
log_success "Packages installed"

# Configure dnsmasq
log_info "Configuring DHCP server..."
cat > /etc/dnsmasq.conf << EOF
# Pi Bridge Configuration
interface=$ETH_INTERFACE
dhcp-range=192.168.4.2,192.168.4.100,255.255.255.0,12h
dhcp-option=3,192.168.4.1
dhcp-option=6,8.8.8.8,8.8.4.4
server=8.8.8.8
server=8.8.4.4
listen-address=127.0.0.1,192.168.4.1
bind-interfaces
no-hosts
EOF
log_success "DHCP configured"

# Configure static IP for Ethernet
log_info "Configuring static IP for Ethernet..."

# Remove old eth0 config if exists
sed -i '/interface '$ETH_INTERFACE'/,/^$/{d}' /etc/dhcpcd.conf

# Add new config
cat >> /etc/dhcpcd.conf << EOF

# Bridge configuration for Windows laptop
interface $ETH_INTERFACE
static ip_address=192.168.4.1/24
nohook wpa_supplicant
EOF
log_success "Static IP configured (192.168.4.1)"

# Configure NAT
log_info "Configuring NAT..."
iptables -t nat -A POSTROUTING -o $WIFI_INTERFACE -j MASQUERADE
iptables -A FORWARD -i $WIFI_INTERFACE -o $ETH_INTERFACE -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i $ETH_INTERFACE -o $WIFI_INTERFACE -j ACCEPT

# Save iptables rules
netfilter-persistent save
log_success "NAT configured"

# Restart services
log_info "Restarting services..."
systemctl restart dhcpcd
systemctl enable dnsmasq
systemctl restart dnsmasq

# Check status
sleep 2
if systemctl is-active --quiet dnsmasq; then
    log_success "DHCP server is running"
else
    log_warning "DHCP server failed to start"
    systemctl status dnsmasq
fi

# Display info
echo ""
echo "=============================================="
echo -e "${GREEN}🎉 Bridge setup complete!${NC}"
echo "=============================================="
echo ""
echo "Pi Ethernet IP: 192.168.4.1"
echo "Windows laptop will get IP: 192.168.4.x"
echo ""
echo "Next steps on Windows:"
echo "1. Set Ethernet to Automatic (DHCP)"
echo "2. Run: ipconfig (should show 192.168.4.x)"
echo "3. Run: ping 8.8.8.8 (should work)"
echo ""
echo "To check connected devices on Pi:"
echo "  cat /var/lib/misc/dnsmasq.leases"
echo ""
echo "To SSH to Pi from Windows:"
echo "  ssh pi@192.168.4.1"
echo ""
