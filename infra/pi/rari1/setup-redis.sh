#!/bin/bash
# Install and configure Redis on rari1 (on SSD, not SD card)
# Run from Mac: ssh rari@100.x.x.x 'bash -s' < infra/pi/rari1/setup-redis.sh
set -euo pipefail

REDIS_DATA_DIR="/mnt/ssd/redis"
REDIS_LOG="/mnt/ssd/sapphire/logs/redis.log"
REDIS_PORT=6379

echo "── Installing Redis ────────────────────────────────────────────────"
sudo apt-get update -q
sudo apt-get install -y redis-server

echo "── Configuring Redis (SSD data dir) ───────────────────────────────"
sudo mkdir -p "${REDIS_DATA_DIR}"
sudo chown redis:redis "${REDIS_DATA_DIR}"
mkdir -p "$(dirname ${REDIS_LOG})"

# Update config: bind all interfaces, use SSD for data
sudo tee /etc/redis/redis.conf > /dev/null <<CONF
bind 0.0.0.0
port ${REDIS_PORT}
daemonize no
dir ${REDIS_DATA_DIR}
logfile ${REDIS_LOG}
maxmemory 256mb
maxmemory-policy allkeys-lru
# Streams: keep last 10k messages per topic
stream-node-max-bytes 4096
stream-node-max-entries 128
# Persistence: save snapshot every 5 min if 10+ keys changed
save 300 10
save 60 1000
appendonly yes
appendfsync everysec
CONF

echo "── Enabling Redis service ──────────────────────────────────────────"
sudo systemctl enable redis-server
sudo systemctl restart redis-server
sleep 2
sudo systemctl status redis-server --no-pager -l

echo ""
echo "── Test ────────────────────────────────────────────────────────────"
redis-cli ping

echo ""
echo "✅ Redis ready on rari1:${REDIS_PORT}"
echo "   Add to all service .env files:"
echo "   REDIS_URL=redis://100.x.x.x:${REDIS_PORT}"
