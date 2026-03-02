#!/bin/bash
# Test VPN and Lighter API connectivity on Raspberry Pi

echo "=============================================="
echo "🔍 Testing VPN and Lighter Connectivity"
echo "=============================================="
echo ""

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

# Test 1: Check current IP
echo "Test 1: Checking current IP address..."
IP_INFO=$(curl -s https://ipinfo.io/json 2>/dev/null)
if [ $? -eq 0 ]; then
    IP=$(echo "$IP_INFO" | grep -o '"ip": "[^"]*"' | cut -d'"' -f4)
    COUNTRY=$(echo "$IP_INFO" | grep -o '"country": "[^"]*"' | cut -d'"' -f4)
    CITY=$(echo "$IP_INFO" | grep -o '"city": "[^"]*"' | cut -d'"' -f4)
    
    echo "  IP: $IP"
    echo "  Location: $CITY, $COUNTRY"
    
    if [ "$COUNTRY" = "US" ]; then
        log_error "WARNING: IP is in US - Lighter API will be blocked!"
        log_info "Please connect to ProtonVPN first"
    else
        log_success "IP is outside US ($COUNTRY) - good for Lighter API"
    fi
else
    log_error "Failed to get IP info"
fi
echo ""

# Test 2: Check DNS resolution
echo "Test 2: Testing DNS resolution..."
if nslookup mainnet.zklighter.elliot.ai > /dev/null 2>&1; then
    log_success "DNS resolution works"
else
    log_error "DNS resolution failed"
fi
echo ""

# Test 3: Ping Lighter API
echo "Test 3: Pinging Lighter API..."
if ping -c 3 -W 5 mainnet.zklighter.elliot.ai > /dev/null 2>&1; then
    log_success "Lighter API is reachable (ping)"
else
    log_warning "Lighter API ping failed (may be blocked)"
fi
echo ""

# Test 4: HTTP connection to Lighter API
echo "Test 4: Testing HTTP connection to Lighter API..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    https://mainnet.zklighter.elliot.ai/api/v1/markets 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
    log_success "Lighter API is accessible (HTTP 200)"
elif [ "$HTTP_CODE" = "403" ]; then
    log_error "Lighter API returned 403 - likely geoblocked!"
elif [ "$HTTP_CODE" = "000" ]; then
    log_error "Connection failed - timeout or network issue"
else
    log_warning "Lighter API returned HTTP $HTTP_CODE"
fi
echo ""

# Test 5: Check if running in Docker
echo "Test 5: Checking environment..."
if [ -f /.dockerenv ]; then
    log_info "Running inside Docker container"
    if curl -s --max-time 5 https://ipinfo.io/country | grep -qv "US"; then
        log_success "Docker container has non-US IP"
    else
        log_warning "Docker container may have US IP - check VPN container"
    fi
else
    log_info "Running on host system"
fi
echo ""

# Test 6: Python Lighter SDK test (if available)
echo "Test 6: Testing Lighter SDK..."
if command -v python3 &> /dev/null; then
    python3 << 'PYEOF'
import sys
import os

# Try to import lighter
try:
    import lighter
    print("  Lighter SDK version:", lighter.__version__ if hasattr(lighter, '__version__') else 'unknown')
except ImportError:
    print("  ❌ Lighter SDK not installed")
    sys.exit(1)

# Try basic API call
try:
    client = lighter.ApiClient()
    client.configuration.host = "https://mainnet.zklighter.elliot.ai"
    
    markets_api = lighter.MarketsApi(client)
    markets = markets_api.get_markets()
    print(f"  ✅ Successfully loaded {len(markets)} markets from Lighter API")
except Exception as e:
    print(f"  ❌ Failed to connect to Lighter API: {e}")
    sys.exit(1)
PYEOF
else
    log_warning "Python3 not available for SDK test"
fi
echo ""

# Summary
echo "=============================================="
echo "📋 Summary"
echo "=============================================="
echo ""
if [ "$COUNTRY" != "US" ] && [ -n "$COUNTRY" ]; then
    log_success "VPN appears to be working (Country: $COUNTRY)"
    echo ""
    echo "You can now start the trading bot:"
    echo "  sudo docker-compose -f docker-compose.pi.yml up -d"
    echo "  # or"
    echo "  sudo systemctl start lighter-trading"
else
    log_error "VPN NOT WORKING - Please connect to ProtonVPN before trading"
    echo ""
    echo "To connect VPN:"
    echo "  sudo protonvpn-trading connect"
fi
echo ""
