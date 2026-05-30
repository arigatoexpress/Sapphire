---
name: sapphire-hyperliquid
description: Hyperliquid L1 perpetuals trading bot — EIP-712 signed orders, 150+ assets
type: service
runtime: python
deploy_target: rari2
dependencies: [sapphire-core]
entry_point: src/hyperliquid_bot/main.py
test_command: pytest tests/
---

# services/hyperliquid

Trading bot for Hyperliquid (`https://api.hyperliquid.xyz`) — a high-performance L1 DEX for perpetuals.

## Public Feed Signal Mode

`src/hyperliquid_bot/public_feed.py` is the Sapphire signal-only public feed.
It subscribes to public `trades`, `bbo`, and `l2Book` WebSocket feeds for
configured symbols and emits only read-only event-bus signals:

- `hyperliquid.trade`
- `hyperliquid.imbalance`
- `hyperliquid.book.thin`

It is blocked unless `SAPPHIRE_HYPERLIQUID_LIVE=1` and still never reads wallet
keys, never calls authenticated endpoints, and never submits trades.

Dry-run tool checks:

```bash
echo '{"action":"status"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/hyperliquid.py
echo '{"action":"subscribe-test"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/hyperliquid.py
```

## Hyperliquid Facts

- REST: `https://api.hyperliquid.xyz` (no API key, wallet signs orders)
- Testnet: `https://api.hyperliquid-testnet.xyz`
- WebSocket: `wss://api.hyperliquid.xyz/ws`
- 150+ perpetual assets
- Authentication: EIP-712 signed actions via wallet private key
- No custody: fully on-chain execution

## Architecture

```
client.py     — Async HTTP client (market data + signed order execution)
main.py       — Bot loop, signal execution, pubsub subscription
```

## Credentials

Store in Secret Manager as `hyperliquid-private-key`:
- `HYPERLIQUID_PRIVATE_KEY` — Ethereum wallet private key (0x-prefixed)
- `HYPERLIQUID_TESTNET` — set to `true` for testnet (default: false)
- `HYPERLIQUID_SIZE_USD` — default position size in USD (default: 100)

## Deploy to rari2

```bash
# Copy to rari2
rsync -av services/hyperliquid/ rari@100.x.x.y:/home/rari/Sapphire/services/bot-hyperliquid/

# Install deps in isolated venv
ssh rari@100.x.x.y "cd ~/Sapphire/services/bot-hyperliquid && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"

# Install systemd service
ssh rari@100.x.x.y "sudo systemctl enable --now hyperliquid-trading.service"
```

## Target Pairs

BTC, ETH, SOL, HYPE (native token), ZEC — same signals as Lighter bot but routed here when configured.
