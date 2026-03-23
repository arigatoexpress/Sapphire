# Raspberry Pi Deployment Guide - Bot Lighter

This guide covers deploying the Lighter trading bot on a Raspberry Pi with ProtonVPN to bypass US geofencing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI (with VPN)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐   │
│  │   ProtonVPN  │─────▶│  Lighter Bot │─────▶│ Lighter API  │   │
│  │   Container  │      │   Container  │      │ (Non-US IP)  │   │
│  └──────────────┘      └──────────────┘      └──────────────┘   │
│         ▲                  │                                     │
│         │                  │                                     │
│    [VPN Tunnel]      [Local Network]                             │
│         │                  │                                     │
│  Internet ◄────────── Pi Host ◄────────── Your Mac/Windows      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. Raspberry Pi 3/4 with Raspberry Pi OS (64-bit)
2. ProtonVPN account (free tier works)
3. Lighter exchange API credentials
4. SSH access to the Pi

## Quick Start

### Option 1: Docker Deployment (Recommended)

1. **On your Mac/Windows, prepare the deployment:**

```bash
cd Sapphire/services/bot-lighter

# Create .env file
cat > .env << EOF
# ProtonVPN Credentials
# Get these from: https://account.protonvpn.com/account#openvpn
PROTONVPN_USERNAME=your_openvpn_username
PROTONVPN_PASSWORD=your_openvpn_password
PROTONVPN_SERVER=NL  # Netherlands for low latency
PROTONVPN_TIER=0     # 0=Free, 1=Basic, 2=Plus

# Lighter Exchange Credentials
LIGHTER_ACCOUNT_INDEX=699444
LIGHTER_API_KEY_INDEX=2
LIGHTER_PUB_KEY=your_public_key
LIGHTER_PRIV_KEY=your_private_key

# Trading Configuration
LIGHTER_SKIP_VALIDATION=true  # Skip validation when behind VPN

# Pub/Sub (optional - for signal subscription)
PUBSUB_PROJECT_ID=sapphire-479610
PUBSUB_SUBSCRIPTION_ID=lighter-signals-pi

# Logging
LOG_LEVEL=INFO
EOF

# Download Pub/Sub service account key from GCP Console
# Place it in: secrets/pubsub-key.json

# Deploy to Pi
export PI_HOST=192.168.4.1  # Your Pi's IP
./scripts/deploy-to-pi.sh
```

2. **On the Raspberry Pi:**

```bash
ssh pi@192.168.4.1
cd ~/bot-lighter

# Start the services
sudo docker-compose -f docker-compose.pi.yml up -d

# Check logs
sudo docker-compose -f docker-compose.pi.yml logs -f bot

# Check VPN connection
sudo docker-compose -f docker-compose.pi.yml exec vpn curl https://ipinfo.io
```

### Option 2: Native Python with Systemd

1. **Install ProtonVPN on the Pi:**

```bash
ssh pi@192.168.4.1

# Download and run setup script
curl -fsSL https://raw.githubusercontent.com/yourrepo/main/scripts/setup-protonvpn-pi.sh | sudo bash

# Or manually:
sudo apt update
sudo apt install openvpn dialog python3-pip wireguard-tools
sudo pip3 install protonvpn-cli

# Initialize with your credentials
sudo protonvpn-cli init
```

2. **Copy bot code to Pi:**

```bash
# From your Mac
scp -r Sapphire/services/bot-lighter pi@192.168.4.1:~/
```

3. **Setup Python environment:**

```bash
ssh pi@192.168.4.1
cd ~/bot-lighter

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file with credentials
nano .env
```

4. **Enable and start the service:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable lighter-trading vpn-killswitch
sudo systemctl start lighter-trading

# Check status
sudo systemctl status lighter-trading
sudo journalctl -u lighter-trading -f
```

## VPN Kill Switch

The systemd service includes a kill switch that automatically stops the trading bot if the VPN disconnects. This prevents accidental trading from a US IP.

To check the kill switch:
```bash
sudo systemctl status vpn-killswitch
```

## Testing Connectivity

Test the VPN and API connectivity:

```bash
# Check VPN IP (should be non-US)
curl https://ipinfo.io

# Test Lighter API connectivity
python3 -c "
import lighter
client = lighter.SignerClient(
    url='https://mainnet.zklighter.elliot.ai',
    account_index=699444,
    api_private_keys={2: 'your_private_key'}
)
print('Connected successfully!')
"
```

## Troubleshooting

### VPN Won't Connect

```bash
# Check ProtonVPN status
sudo protonvpn-cli status

# Reconnect
sudo protonvpn-cli reconnect

# Try different server
sudo protonvpn-cli connect CH  # Switzerland
sudo protonvpn-cli connect SG  # Singapore
```

### Bot Can't Reach Lighter API

1. Verify VPN is connected: `curl https://ipinfo.io`
2. Check the IP is non-US (country code should be NL, CH, SG, etc.)
3. Try `LIGHTER_SKIP_VALIDATION=true` in .env
4. Check firewall rules: `sudo iptables -L`

### Pub/Sub Connection Issues

When running on Pi with VPN, Pub/Sub might have connectivity issues. Options:

1. **Use REST API polling instead:**
   Set `API_BASE_URL` in .env to poll the API Gateway

2. **Whitelist GCP IPs in VPN:**
   Some VPNs block GCP - check ProtonVPN settings

3. **Run without Pub/Sub:**
   The bot can operate in standalone mode, checking a local file or HTTP endpoint for signals

### Docker Issues on Pi

```bash
# If Docker won't start
docker-compose -f docker-compose.pi.yml down
sudo systemctl restart docker

# Rebuild containers (no cache)
docker-compose -f docker-compose.pi.yml build --no-cache

# Check container logs
docker-compose -f docker-compose.pi.yml logs vpn
docker-compose -f docker-compose.pi.yml logs bot
```

## Performance Tips

1. **Use Ethernet:** Connect Pi via Ethernet for more stable VPN connection
2. **Choose nearby VPN servers:** NL (Netherlands) has good latency to Lighter's servers
3. **Pi 4 recommended:** Pi 4 has better performance for crypto operations
4. **Use SSD:** Running from SSD instead of SD card improves reliability

## Security Considerations

1. **Keep private keys secure:** The Pi stores your Lighter private key
2. **Use firewall:** Only open necessary ports
3. **Enable auto-updates:** Keep the Pi and containers updated
4. **Physical security:** The Pi has your trading credentials

## Monitoring

The deployment includes a monitoring dashboard:

```bash
# View metrics (on Pi)
curl http://localhost:9100/metrics

# From your Mac (if on same network)
curl http://192.168.4.1:9100/metrics
```

## Updating the Bot

To update after code changes:

```bash
# From your Mac
./scripts/deploy-to-pi.sh

# On Pi, restart services
sudo docker-compose -f docker-compose.pi.yml up -d --build
```
