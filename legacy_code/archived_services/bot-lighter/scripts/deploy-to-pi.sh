#!/bin/bash
# Deploy bot-lighter to Raspberry Pi with ProtonVPN
# Run this from your Mac to deploy to the Pi

set -e

# Configuration
PI_HOST="${PI_HOST:-192.168.4.1}"  # Default Pi IP from bridge setup
PI_USER="${PI_USER:-pi}"
DEPLOY_DIR="/home/pi/bot-lighter"

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

echo ""
echo "=============================================="
echo "🚀 Deploy Bot-Lighter to Raspberry Pi"
echo "=============================================="
echo ""

# Check SSH connectivity
log_info "Checking connection to Pi at $PI_HOST..."
if ! ssh -o ConnectTimeout=5 "$PI_USER@$PI_HOST" "echo 'Pi reachable'" 2>/dev/null; then
    log_error "Cannot connect to Pi at $PI_USER@$PI_HOST"
    echo "Make sure:"
    echo "  1. Pi is powered on"
    echo "  2. Pi is on the same network"
    echo "  3. SSH is enabled on the Pi"
    exit 1
fi
log_success "Pi is reachable"

# Check for required files
if [ ! -f ".env" ]; then
    log_warning ".env file not found!"
    echo "Creating template .env file..."
    cat > .env << 'EOF'
# ProtonVPN Credentials (from https://account.protonvpn.com/account#openvpn)
PROTONVPN_USERNAME=your_openvpn_username
PROTONVPN_PASSWORD=your_openvpn_password
PROTONVPN_SERVER=NL
PROTONVPN_TIER=0

# Lighter Exchange Credentials
LIGHTER_ACCOUNT_INDEX=699444
LIGHTER_API_KEY_INDEX=2
LIGHTER_PRIVATE_KEY=your_private_key_here

# Pub/Sub Configuration (optional)
PUBSUB_PROJECT_ID=sapphire-479610
PUBSUB_SUBSCRIPTION_ID=lighter-signals-pi

# API Configuration (optional)
API_BASE_URL=https://sapphire-trading-api-699444.us-central1.run.app

# Logging
LOG_LEVEL=INFO
EOF
    log_error "Please edit .env file with your credentials and run again"
    exit 1
fi

# Check for secrets
if [ ! -d "secrets" ] || [ ! -f "secrets/pubsub-key.json" ]; then
    log_warning "Pub/Sub key not found in secrets/pubsub-key.json"
    log_info "To use Pub/Sub signals, download the service account key from GCP Console"
fi

# Create deployment package
log_info "Creating deployment package..."
DEPLOY_PACKAGE="bot-lighter-deploy-$(date +%Y%m%d-%H%M%S).tar.gz"
tar czf "$DEPLOY_PACKAGE" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.tar.gz' \
    --exclude='venv' \
    --exclude='logs/*' \
    --exclude='data/*' \
    src/ \
    config/ \
    requirements.txt \
    Dockerfile.pi \
    docker-compose.pi.yml \
    .env \
    secrets/ 2>/dev/null || true

log_success "Package created: $DEPLOY_PACKAGE"

# Copy to Pi
log_info "Copying to Pi..."
ssh "$PI_USER@$PI_HOST" "mkdir -p $DEPLOY_DIR"
scp "$DEPLOY_PACKAGE" "$PI_USER@$PI_HOST:$DEPLOY_DIR/"

# Extract and setup on Pi
log_info "Setting up on Pi..."
ssh "$PI_USER@$PI_HOST" << EOF
    set -e
    cd $DEPLOY_DIR
    
    # Backup old deployment
    if [ -d "src" ]; then
        mkdir -p backups
        tar czf "backup-$(date +%Y%m%d-%H%M%S).tar.gz" src/ config/ 2>/dev/null || true
    fi
    
    # Extract new deployment
    tar xzf "$DEPLOY_PACKAGE"
    rm "$DEPLOY_PACKAGE"
    
    # Setup Docker if not installed
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $PI_USER
        rm get-docker.sh
    fi
    
    # Setup Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        sudo pip3 install docker-compose
    fi
    
    # Create directories
    mkdir -p logs data
    
    echo "✅ Setup complete on Pi"
EOF

log_success "Deployment files copied to Pi"

# Ask what to do next
echo ""
echo "=============================================="
echo "📋 Next Steps (run on the Pi):"
echo "=============================================="
echo ""
echo "1. SSH to the Pi:"
echo "   ssh $PI_USER@$PI_HOST"
echo ""
echo "2. Go to deployment directory:"
echo "   cd $DEPLOY_DIR"
echo ""
echo "3. Option A - Docker (recommended):"
echo "   sudo docker-compose -f docker-compose.pi.yml up -d"
echo ""
echo "4. Option B - Native Python with ProtonVPN:"
echo "   sudo ./scripts/setup-protonvpn-pi.sh"
echo "   python3 -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install -r requirements.txt"
echo "   sudo systemctl start lighter-trading"
echo ""
echo "5. Check status:"
echo "   sudo docker-compose -f docker-compose.pi.yml logs -f bot"
echo "   # OR for native:"
echo "   sudo systemctl status lighter-trading"
echo ""

# Cleanup
rm -f "$DEPLOY_PACKAGE"

log_success "Deploy script complete!"
