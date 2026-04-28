"""Seed helpers for operator-confirmed live fills."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lib.core.provenance import ProvenanceEnvelope

from .ledger import LiveLedger, LiveTradeRecord, hash_account, redact_source_reference


def _trade_id(payload: dict[str, Any]) -> str:
    explicit = payload.get("trade_id") or payload.get("order_id")
    if explicit:
        return str(explicit).strip()
    material = {
        "account": payload.get("account") or payload.get("account_hash"),
        "symbol": payload.get("symbol"),
        "fill_at": payload.get("fill_at") or payload.get("date_filled"),
        "quantity": payload.get("quantity") or payload.get("amount_filled"),
        "fill_price": payload.get("fill_price") or payload.get("filled_at"),
    }
    blob = json.dumps(material, sort_keys=True, default=str)
    return "seed-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _require_input_provenance(payload: dict[str, Any]) -> dict[str, Any]:
    provenance = payload.get("provenance") or payload.get("provenance_envelope")
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError("operator fill JSON must include a provenance envelope")
    return provenance


def provenance_for_operator_fill(payload: dict[str, Any]) -> dict[str, Any]:
    """Build an input provenance envelope for an operator-pasted fill JSON."""

    clean = {k: v for k, v in payload.items() if k not in {"provenance", "provenance_envelope"}}
    return ProvenanceEnvelope.build(
        clean,
        generator="live_portfolio.seed.operator_fill",
        metadata={"source": "operator_pasted_fill", "live_api_calls": 0},
    ).to_dict()


def record_from_operator_fill(
    payload: dict[str, Any],
    *,
    account_salt: str | None = None,
    require_input_provenance: bool = True,
) -> LiveTradeRecord:
    """Convert operator-confirmed fill JSON into a live ledger record."""

    if require_input_provenance:
        _require_input_provenance(payload)

    raw_account = payload.get("account") or payload.get("account_redacted")
    account_hash = payload.get("account_hash")
    if not account_hash:
        if raw_account is None:
            raise ValueError("account or account_hash is required")
        account_hash = hash_account(str(raw_account), salt=account_salt)

    quantity = payload.get("quantity", payload.get("amount_filled"))
    fill_price = payload.get("fill_price", payload.get("filled_at"))
    fill_at = payload.get("fill_at", payload.get("date_filled"))
    fee = payload.get("fee", 0.0)
    notional = payload.get("notional", payload.get("filled_notional_value"))
    if notional is None and quantity is not None and fill_price is not None:
        notional = float(quantity) * float(fill_price)
    total_cost = payload.get("total_cost")
    if total_cost is None and notional is not None:
        total_cost = float(notional) + float(fee or 0.0)

    source_ref = (
        payload.get("source_email_message_id")
        or payload.get("source_email_message_id_redacted")
        or payload.get("email_message_id")
        or payload.get("source_email")
    )

    record_payload = {
        "trade_id": _trade_id(payload),
        "account_hash": account_hash,
        "exchange": payload.get("exchange", "Robinhood Crypto"),
        "symbol": payload.get("symbol"),
        "side": payload.get("side", "buy"),
        "order_type": payload.get("order_type", payload.get("type", "limit")),
        "quantity": quantity,
        "fill_price": fill_price,
        "fill_at": fill_at,
        "notional": notional,
        "fee": fee,
        "total_cost": total_cost,
        "ramp_tier": int(payload.get("ramp_tier", 1)),
        "source_email_message_id_redacted": redact_source_reference(source_ref),
    }
    return LiveTradeRecord.build(
        record_payload,
        generator="live_portfolio.seed",
        metadata={"input_provenance_hash": _require_input_provenance(payload).get("envelope_hash")}
        if require_input_provenance
        else {"input_provenance_hash": None},
    )


def seed_record(
    payload: dict[str, Any],
    *,
    ledger: LiveLedger | None = None,
    persist: bool = False,
    account_salt: str | None = None,
    require_input_provenance: bool = True,
) -> dict[str, Any]:
    """Build and optionally persist one operator fill."""

    record = record_from_operator_fill(
        payload,
        account_salt=account_salt,
        require_input_provenance=require_input_provenance,
    )
    appended = False
    path: str | None = None
    if persist:
        target = ledger or LiveLedger()
        appended = target.append(record)
        path = str(target.trade_path(record))
    return {"record": record.to_dict(), "persisted": appended, "path": path}


def load_fill_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
