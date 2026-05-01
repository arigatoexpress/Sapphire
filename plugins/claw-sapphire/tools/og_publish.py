"""og_publish — publish a Sapphire trading signal to 0G Storage + 0G Chain.

stdin JSON:
    {
        "strategy": "kronos_btc_24h",
        "symbol": "BTC-USD",
        "action": "buy",                 // or direction: 0/1/2
        "score": 92.0,                   // optional; mapped to confidence_bp
        "signal": { ... full signal record ... },
        "inputs": { ... },               // optional; hashed for fingerprint
        "inference": {                   // optional; TEE attestation
            "provider_address": "0x...",
            "model": "...",
            "chat_id": "...",
            "base_url": "..."
        },
        "network": "testnet"             // optional; default $SAPPHIRE_OG_NETWORK
    }

stdout JSON:
    {
        "ok": true,
        "envelope_hash": "0x...",        // sha256(canonical envelope)
        "root_hash": "0x...",            // 0G Storage merkle root
        "storage_tx": "0x...",           // 0G Storage upload tx
        "anchor": {
            "signal_id": 42,
            "tx_hash": "0x...",
            "block_number": 12345,
            "explorer_url": "https://chainscan.0g.ai/tx/0x..."
        }
    }

Behavior:
- If `SAPPHIRE_OG_ENABLED` is unset, returns {"ok": false, "skipped": true}
  without touching 0G. This keeps the trading critical path safe in dev.
- Errors are returned as {"ok": false, "error": "..."} on stdout.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lib.og import is_enabled  # noqa: E402
from lib.og.chain import publish_signal  # noqa: E402
from lib.og.envelope import (  # noqa: E402
    InferenceAttestation,
    build_envelope,
    confidence_to_bp,
    direction_from_action,
)
from lib.og.storage import upload_bytes  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s og_publish %(message)s")
log = logging.getLogger("og_publish")


def _read_request() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("og_publish: empty stdin; expected a JSON payload")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"og_publish: invalid JSON on stdin: {exc}") from exc


def _resolve_direction(req: dict) -> int:
    if "direction" in req and req["direction"] is not None:
        d = int(req["direction"])
        if d not in (0, 1, 2):
            raise ValueError("direction must be 0, 1, or 2")
        return d
    return direction_from_action(req.get("action", ""))


def _resolve_confidence(req: dict) -> int:
    if "confidence_bp" in req and req["confidence_bp"] is not None:
        bp = int(req["confidence_bp"])
        if not (0 <= bp <= 10000):
            raise ValueError("confidence_bp must be 0..10000")
        return bp
    return confidence_to_bp(req.get("score"))


def _attestation(req: dict) -> InferenceAttestation:
    inf = req.get("inference") or {}
    return InferenceAttestation(
        provider_address=str(inf.get("provider_address", "")),
        model=str(inf.get("model", "")),
        chat_id=str(inf.get("chat_id", "")),
        base_url=str(inf.get("base_url", "")),
    )


def main() -> None:
    try:
        req = _read_request()
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

    if not is_enabled():
        print(
            json.dumps(
                {
                    "ok": False,
                    "skipped": True,
                    "reason": "SAPPHIRE_OG_ENABLED is not set; integration is inert",
                }
            )
        )
        return

    try:
        strategy = str(req["strategy"]).strip()
        symbol = str(req["symbol"]).strip()
        if not strategy or not symbol:
            raise ValueError("strategy and symbol are required")
    except (KeyError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": f"bad request: {exc}"}))
        sys.exit(1)

    direction = _resolve_direction(req)
    confidence_bp = _resolve_confidence(req)
    network = req.get("network")

    envelope = build_envelope(
        strategy=strategy,
        symbol=symbol,
        direction=direction,
        confidence_bp=confidence_bp,
        signal=req.get("signal") or {},
        inputs=req.get("inputs") or {},
        inference=_attestation(req),
    )

    try:
        upload_result = upload_bytes(envelope.canonical_json(), network=network)
    except Exception as exc:
        log.exception("0G Storage upload failed")
        print(json.dumps({"ok": False, "stage": "storage", "error": str(exc)}))
        sys.exit(2)

    try:
        anchor = publish_signal(
            strategy=strategy,
            symbol=symbol,
            direction=direction,
            confidence_bp=confidence_bp,
            proof_root_hash=upload_result.root_hash,
            network=network,
        )
    except Exception as exc:
        log.exception("0G Chain anchor failed")
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "anchor",
                    "error": str(exc),
                    "root_hash": upload_result.root_hash,
                    "storage_tx": upload_result.tx_hash,
                }
            )
        )
        sys.exit(3)

    print(
        json.dumps(
            {
                "ok": True,
                "envelope_hash": envelope.content_hash(),
                "root_hash": upload_result.root_hash,
                "storage_tx": upload_result.tx_hash,
                "anchor": {
                    "signal_id": anchor.signal_id,
                    "tx_hash": anchor.tx_hash,
                    "block_number": anchor.block_number,
                    "explorer_url": anchor.explorer_url,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
