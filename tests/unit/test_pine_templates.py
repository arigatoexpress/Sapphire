"""Unit tests for Sapphire Pine template generator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.trading.pine_templates import (
    SCHEMA_VERSION,
    list_generated,
    render_sapphire_watch_indicator,
    write_template,
)


def test_render_indicator_emits_pine_v5_header():
    src = render_sapphire_watch_indicator("BINANCE:ETHUSDT")
    assert "//@version=5" in src
    assert 'indicator("Sapphire Watch - BINANCE:ETHUSDT"' in src


def test_render_indicator_includes_webhook_payload_for_each_action():
    src = render_sapphire_watch_indicator("BINANCE:BTCUSDT")
    for action in ("long", "short", "exit_long", "exit_short"):
        assert f'"action": "{action}"' in src or action in src


def test_render_indicator_includes_strategy_tag():
    src = render_sapphire_watch_indicator("BINANCE:SOLUSDT")
    assert '"strategy": "sapphire_watch_indicator"' in src
    assert '"source": "tradingview_pine"' in src


def test_render_indicator_respects_extra_payload():
    src = render_sapphire_watch_indicator(
        "BINANCE:ETHUSDT",
        webhook_payload_extra={"tier": "primary", "ladder": 1},
    )
    # extra fields are emitted as escaped JSON inside a Pine single-quoted string,
    # so quotes appear as backslash-escapes in the source
    assert r'\"tier\": \"primary\"' in src
    assert r'\"ladder\": 1' in src


def test_write_template_writes_pine_and_metadata(tmp_path: Path):
    src = render_sapphire_watch_indicator("BINANCE:ETHUSDT")
    out = write_template(
        "Sapphire Watch BINANCE:ETHUSDT",
        src,
        root=tmp_path,
        metadata={"tradingview_symbol": "BINANCE:ETHUSDT"},
    )
    pine_path = Path(out["pine_path"])
    meta_path = Path(out["metadata_path"])
    assert pine_path.exists() and pine_path.read_text(encoding="utf-8") == src
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["tradingview_symbol"] == "BINANCE:ETHUSDT"
    assert meta["byte_size"] == len(src.encode("utf-8"))


def test_list_generated_filters_to_schema(tmp_path: Path):
    write_template("First", render_sapphire_watch_indicator("X"), root=tmp_path)
    # Foreign metadata should be ignored
    (tmp_path / "stale.json").write_text(json.dumps({"schema_version": "other"}), encoding="utf-8")
    rows = list_generated(tmp_path)
    assert len(rows) == 1
    assert rows[0]["schema_version"] == SCHEMA_VERSION


def test_list_generated_returns_empty_when_dir_missing(tmp_path: Path):
    assert list_generated(tmp_path / "nope") == []


def test_slug_is_filename_safe(tmp_path: Path):
    out = write_template("Watch BINANCE:ETHUSDT v1", "// pine\n", root=tmp_path)
    pine_path = Path(out["pine_path"])
    assert ":" not in pine_path.name
    assert " " not in pine_path.name


@pytest.mark.parametrize("symbol", ["BINANCE:ETHUSDT", "BYBIT:SOLUSDT", "OANDA:EURUSD"])
def test_render_works_for_multiple_venues(symbol: str):
    src = render_sapphire_watch_indicator(symbol)
    assert symbol in src
    assert "ta.ema" in src


def test_render_emits_webhook_contract_field_names():
    """Generated payload must use field names the receiver accepts."""
    src = render_sapphire_watch_indicator("BINANCE:ETHUSDT")
    # receiver reads `time`, not `ts`
    assert '"time"' in src
    assert '"ts":' not in src
    # interval + exchange are optional but the webhook understands them
    assert '"interval"' in src
    assert '"exchange"' in src


def test_generated_payload_actions_are_in_webhook_valid_set():
    """Each emitted `action` value must be in services/webhook VALID_ACTIONS."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    # Pull VALID_ACTIONS by parsing the receiver source — avoids importing the
    # FastAPI module (which has heavy side effects including network probes).
    receiver = (root / "services" / "webhook" / "src" / "receiver.py").read_text(
        encoding="utf-8"
    )
    src = render_sapphire_watch_indicator("BINANCE:ETHUSDT")
    for action in ("long", "short", "exit_long", "exit_short"):
        # Generated indicator emits these
        assert f'"action": "{action}"' in src or action in src
        # Receiver source must declare them in VALID_ACTIONS
        assert f'"{action}"' in receiver
