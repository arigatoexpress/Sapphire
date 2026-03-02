# Sapphire Trading System - Full Enumeration

**Generated:** 2026-03-02  
**Status:** ✅ Operational

---

## 📦 Physical Infrastructure

### Raspberry Pi Nodes

| Node | IP | Hardware | OS | VPN IP | Location |
|------|-----|----------|-----|--------|----------|
| rari1 | 192.168.1.23 | Pi 4 Model B Rev 1.2 (4GB) | Debian 13 (trixie) | 146.70.226.x | 🇨🇭 Zürich |
| rari2 | 192.168.1.173 | Pi 4 Model B Rev 1.2 (4GB) | Debian 13 (trixie) | 79.127.184.x | 🇨🇭 Zürich |

### Network Topology

```
Internet
   │
   ├──► WiFi Router (192.168.1.1)
   │         │
   │         ├──► rari1 (192.168.1.23)
   │         │         ├──► VPN ► 146.70.226.x (Zürich)
   │         │         └──► ETH0 (192.168.2.1) - Bridge
   │         │
   │         └──► rari2 (192.168.1.173)
   │                   ├──► VPN ► 79.127.184.x (Zürich)
   │
   └──► GCP Cloud (sapphire-479610)
```

---

## 🤖 Trading Bots

### Lighter Bot (L2 Order Book)

| Attribute | Value |
|-----------|-------|
| Exchange | Lighter Protocol (ZK-Rollup) |
| Mainnet | mainnet.zklighter.elliot.ai |
| Account Index | 699444 |
| API Key Index | 2 |
| Markets | 169 |
| Trading Mode | PAPER |
| Max Notional | $250 |
| Features | ETH→WETH, BTC→WBTC aliases |

### Aster Bot (Perpetual DEX)

| Attribute | Value |
|-----------|-------|
| Exchange | Aster DEX |
| Endpoint | fapi.asterdex.com |
| Balance | ~50 USDT |
| Trading Mode | PAPER |
| Max Notional | $250 |

---

## ☁️ GCP Cloud Infrastructure

### Project Details
- **Project ID:** sapphire-479610
- **Region:** us-central1

### Cloud Run Services (17 Total)

| Service | URL | Status |
|---------|-----|--------|
| sapphire-gateway | https://sapphire-gateway-267358751314.us-central1.run.app | ✅ Active |
| sapphire-dashboard | https://sapphire-dashboard-267358751314.us-central1.run.app | ✅ Active |
| agentic-pm-hub | https://agentic-pm-hub-267358751314.us-central1.run.app | ✅ Active |
| sapphire-telegram-bot | https://sapphire-telegram-bot-267358751314.us-central1.run.app | ✅ Active |
| sapphire-aster | https://sapphire-aster-267358751314.us-central1.run.app | ✅ Active |
| sapphire-unified-frontend | https://sapphire-unified-frontend-267358751314.us-central1.run.app | ✅ Active |

### Pub/Sub Topics

- trading-signals
- risk-alerts
- position-updates
- balance-updates
- lighter-signals-rari1/rari2
- aster-signals-rari1

---

## 🔗 Integrations

### Trading Venues
- **Lighter Protocol** - ZK-Rollup L2 Order Book
- **Aster DEX** - Perpetual DEX (Binance-compatible)

### Notification Channels
- **Telegram Bot** - @sapphire_trading_bot
- **Health Dashboard** - Cloud Run service

### Agent Systems
- **Kimi-Claw** - Unified agent (DevOps/Architecture/Security)
- **Control Plane Workers** - PM Hub integration

---

## 🔐 Security

- All trading in PAPER mode (safety)
- VPN encryption for exchange traffic
- API keys in GCP Secret Manager
- SSH key authentication on Pis
- Service account isolation

---

## 📊 Deployment Statistics

| Component | Count |
|-----------|-------|
| Physical Nodes | 2 Raspberry Pi 4 |
| Trading Bots | 4 (2 Lighter + 2 Aster) |
| Cloud Run Services | 17 |
| Pub/Sub Topics | 9 |
| Python Files | ~14,000+ |
| VPN Tunnels | 2 |

---

## 🚀 Quick Access

### Pi 1 (rari1)
```bash
ssh rari@192.168.1.23  # password: root
sudo journalctl -u lighter-trading -f
sudo journalctl -u aster-trading -f
```

### Pi 2 (rari2)
```bash
ssh rari@192.168.1.173  # password: root
sudo journalctl -u lighter-trading -f
```

### Health Endpoints
- Pi 1 Lighter: http://192.168.1.23:8080/health
- Pi 1 Aster: http://192.168.1.23:8081/health
- Pi 2 Lighter: http://192.168.1.173:8080/health
