from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from lib.live_portfolio.ledger import (
    LiveLedger,
    LiveTradeRecord,
    ensure_account_hash,
    hash_account,
    parse_utc,
    redact_source_reference,
)


def record(**overrides) -> LiveTradeRecord:
    payload = {
        "trade_id": "t1",
        "account_hash": "EXAMPLE-account-hash",
        "exchange": "Robinhood Crypto",
        "symbol": "btc",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 0.00006511,
        "fill_price": 76774.81,
        "fill_at": "2026-04-28T04:06:00Z",
        "notional": 5.0,
        "fee": 0.04,
        "total_cost": 5.04,
        "ramp_tier": 1,
        "source_email_message_id_redacted": "abcdef1234567890@example.com",
        "provenance_envelope": {"generator": "test"},
    }
    payload.update(overrides)
    return LiveTradeRecord.from_dict(payload)


def test_parse_utc_normalizes_z() -> None:
    assert parse_utc("2026-04-28T04:06:00Z").tzinfo == UTC


def test_parse_utc_accepts_datetime() -> None:
    assert parse_utc(datetime(2026, 4, 28, 4, 6)).isoformat().endswith("+00:00")


def test_hash_account_uses_tenant_scope() -> None:
    hashed = hash_account("Individual (...5966)", salt="salt")
    assert hashed.startswith("tenant_live_portfolio_")
    assert "5966" not in hashed


def test_account_hash_rejects_raw_account() -> None:
    with pytest.raises(ValueError):
        ensure_account_hash("Individual (...5966)")


def test_account_hash_accepts_example_fixture() -> None:
    assert ensure_account_hash("EXAMPLE-account-hash") == "EXAMPLE-account-hash"


def test_record_normalizes_symbol_side_and_type() -> None:
    r = record()
    assert r.symbol == "BTC"
    assert r.side == "buy"
    assert r.order_type == "limit"


def test_record_rejects_bad_side() -> None:
    with pytest.raises(ValueError):
        record(side="hold")


def test_record_rejects_bad_type() -> None:
    with pytest.raises(ValueError):
        record(order_type="mystery")


def test_record_rejects_negative_fee() -> None:
    with pytest.raises(ValueError):
        record(fee=-1)


def test_record_rejects_zero_quantity() -> None:
    with pytest.raises(ValueError):
        record(quantity=0)


def test_record_rejects_raw_account_alias() -> None:
    with pytest.raises(ValueError):
        LiveTradeRecord.from_dict(
            {**record().to_dict(), "account": "...5966", "account_hash": None}
        )


def test_redact_source_reference_keeps_short_safe_value() -> None:
    assert redact_source_reference("abc123") == "abc123"


def test_redact_source_reference_redacts_email() -> None:
    redacted = redact_source_reference("message from ari@example.com " + "x" * 80)
    assert "ari@example.com" not in redacted
    assert redacted.endswith("redacted")


def test_ledger_append_and_load(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    assert ledger.append(record()) is True
    rows = ledger.load("EXAMPLE-account-hash")
    assert len(rows) == 1
    assert rows[0].trade_id == "t1"


def test_ledger_dedupe_by_trade_id_and_fill_at(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    assert ledger.append(record()) is True
    assert ledger.append(record()) is False
    assert len(ledger.load("EXAMPLE-account-hash")) == 1


def test_ledger_same_trade_id_different_fill_is_distinct(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    assert ledger.append(record()) is True
    assert ledger.append(record(fill_at="2026-04-29T04:06:00Z")) is True
    assert len(ledger.load("EXAMPLE-account-hash")) == 2


def test_ledger_load_skips_malformed_lines(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    path = tmp_path / "EXAMPLE-account-hash" / "2026-04-28" / "trades.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json}\n", encoding="utf-8")
    assert ledger.load() == []


def test_ledger_strict_load_raises_on_malformed(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    path = tmp_path / "EXAMPLE-account-hash" / "2026-04-28" / "trades.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        ledger.load(strict=True)


def test_ledger_summary_is_paste_safe(tmp_path) -> None:
    ledger = LiveLedger(tmp_path)
    ledger.append(record())
    summary = ledger.summary()
    blob = json.dumps(summary)
    assert "provenance_envelope" not in blob
    assert "...5966" not in blob


def test_record_build_adds_provenance() -> None:
    r = LiveTradeRecord.build({**record().to_dict(), "provenance_envelope": {}})
    assert r.provenance_envelope["generator"] == "live_portfolio.ledger"


def test_from_dict_accepts_type_alias() -> None:
    payload = record().to_dict()
    payload["type"] = payload.pop("order_type")
    assert LiveTradeRecord.from_dict(payload).order_type == "limit"


def test_accounts_returns_sorted_dirs(tmp_path) -> None:
    (tmp_path / "EXAMPLE-b").mkdir()
    (tmp_path / "EXAMPLE-a").mkdir()
    assert LiveLedger(tmp_path).accounts() == ["EXAMPLE-a", "EXAMPLE-b"]
