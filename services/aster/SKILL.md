---
name: sapphire-aster
description: Aster DEX trading bot — Solana perpetuals, CEX-style API, Shield HFT strategy
type: service
runtime: python
deploy_target: rari2
dependencies: [sapphire-core]
entry_point: src/main.py
test_command: pytest tests/
---

# services/aster

Trading bot for Aster DEX (`https://fapi.asterdex.com`). CEX-style Solana perpetuals exchange with 231 symbols and full order type support.

## Aster DEX Facts

- API: `https://fapi.asterdex.com` (verified working)
- 231 trading pairs available
- Order types: LIMIT, MARKET, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
- Does NOT support hidden/iceberg orders via API (UI-only)

## Shield Strategy

High-frequency strategy with sub-100ms stop-loss placement:

```
sl_distance = base_volatility / √leverage
```

Dynamic leverage per asset:
- BTC: 20x base, 125x max
- ETH: 15x base, 100x max
- Altcoins: 10x base, 75x max

## Credentials

- `ASTER_API_KEY`, `ASTER_API_SECRET`, `ASTER_PASSPHRASE` — via Secret Manager
- `ASTER_BASE_URL` — defaults to `https://fapi.asterdex.com`

## Dependency Issue

`asterpy` conflicts with newer aiohttp. This service uses a standalone venv:

```bash
cd services/aster
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Deploy to rari2

```bash
rsync -av services/aster/ rari@100.87.225.89:/home/rari/Sapphire/services/bot-aster/
ssh rari@100.87.225.89 "cd ~/Sapphire/services/bot-aster && source .venv/bin/activate && pip install -r requirements.txt"
```
