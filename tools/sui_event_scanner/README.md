# Sui Event Scanner (Standalone Tool)

Status: utility (migrated from `arigatoexpress/fullsail_scanner`, now archived)

Purpose:
- Subscribe to Sui on-chain Move events over WebSocket RPC (`suix_subscribeEvent`).
- Optionally forward matching events to a webhook.

Quick start:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r tools/sui_event_scanner/requirements.txt
```

Run:

```bash
export MOVE_EVENT_TYPE="0x123::my_dex::DepositEvent"
# Optional:
export WEBHOOK_URL="https://example.com/hook"
export SUI_WS_URL="wss://fullnode.mainnet.sui.io:443"

python tools/sui_event_scanner/scanner.py
```

Notes:
- This tool is not part of the Sapphire production runtime. It is kept here as a standalone operator utility.
