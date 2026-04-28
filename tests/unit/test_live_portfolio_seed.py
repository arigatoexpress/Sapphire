from __future__ import annotations

import pytest

from lib.live_portfolio.seed import (
    provenance_for_operator_fill,
    record_from_operator_fill,
    seed_record,
)


def fill_payload() -> dict:
    payload = {
        "account": "Individual (...5966)",
        "symbol": "BTC",
        "type": "limit",
        "side": "buy",
        "date_filled": "2026-04-28T04:06:00Z",
        "filled_at": 76774.81,
        "amount_filled": 0.00006511,
        "fee": 0.04,
        "total_cost": 5.05,
        "source_email": "Robinhood confirmation for ari@example.com transaction 123456789",
    }
    payload["provenance"] = provenance_for_operator_fill(payload)
    return payload


def test_seed_requires_provenance() -> None:
    payload = fill_payload()
    payload.pop("provenance")
    with pytest.raises(ValueError):
        record_from_operator_fill(payload)


def test_seed_hashes_account() -> None:
    record = record_from_operator_fill(fill_payload(), account_salt="salt")
    assert record.account_hash.startswith("tenant_live_portfolio_")
    assert "5966" not in record.account_hash


def test_seed_derives_trade_id_when_missing() -> None:
    record = record_from_operator_fill(fill_payload(), account_salt="salt")
    assert record.trade_id.startswith("seed-")


def test_seed_redacts_source_email() -> None:
    record = record_from_operator_fill(fill_payload(), account_salt="salt")
    assert "ari@example.com" not in (record.source_email_message_id_redacted or "")


def test_seed_can_persist(tmp_path) -> None:
    from lib.live_portfolio.ledger import LiveLedger

    result = seed_record(fill_payload(), ledger=LiveLedger(tmp_path), persist=True, account_salt="salt")
    assert result["persisted"] is True
    assert result["path"]


def test_seed_duplicate_persist_reports_false(tmp_path) -> None:
    from lib.live_portfolio.ledger import LiveLedger

    ledger = LiveLedger(tmp_path)
    payload = fill_payload()
    seed_record(payload, ledger=ledger, persist=True, account_salt="salt")
    result = seed_record(payload, ledger=ledger, persist=True, account_salt="salt")
    assert result["persisted"] is False
