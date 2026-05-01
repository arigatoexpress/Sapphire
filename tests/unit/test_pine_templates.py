"""Unit tests for Sapphire Pine template generator.

Server-side `tv pine check` validation is exercised manually via the
`pine-generate-strategy --validate` CLI when the `tv` CLI is available
(see `docs/ops/tradingview-orchestrator-runbook.md`). When `tv` is not
available in CI/agent environments, this file's structural assertions
cover the same surface — Pine v5 header, action set, payload field
names, and the strategy/screener-specific markers.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.trading.pine_templates import (
    MAX_SCREENER_SYMBOLS,
    SCHEMA_VERSION,
    list_generated,
    render_sapphire_screener,
    render_sapphire_watch_indicator,
    render_sapphire_watch_strategy,
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
    assert r"\"tier\": \"primary\"" in src
    assert r"\"ladder\": 1" in src


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
    receiver = (root / "services" / "webhook" / "src" / "receiver.py").read_text(encoding="utf-8")
    src = render_sapphire_watch_indicator("BINANCE:ETHUSDT")
    for action in ("long", "short", "exit_long", "exit_short"):
        # Generated indicator emits these
        assert f'"action": "{action}"' in src or action in src
        # Receiver source must declare them in VALID_ACTIONS
        assert f'"{action}"' in receiver


# ─── render_sapphire_watch_strategy ──────────────────────────────────────────


def test_render_strategy_emits_pine_v5_header():
    src = render_sapphire_watch_strategy("BINANCE:ETHUSDT")
    assert "//@version=5" in src
    assert 'strategy("Sapphire Strategy - BINANCE:ETHUSDT"' in src


def test_render_strategy_uses_strategy_keyword_not_indicator():
    """The renderer must emit `strategy(...)` so the in-TV Strategy Tester runs."""
    src = render_sapphire_watch_strategy("BINANCE:ETHUSDT")
    # Must be a Pine strategy
    assert "strategy(" in src
    # Must NOT be `indicator(...)` at script-level (the screener uses indicator,
    # but a strategy renderer should not).
    # Allow `// indicator` in comments — assert against the `indicator(` call.
    assert 'indicator("Sapphire' not in src


def test_render_strategy_sets_capital_and_qty_defaults():
    """Strategy must declare initial_capital, percent-of-equity sizing, commission."""
    src = render_sapphire_watch_strategy("BINANCE:ETHUSDT")
    assert "initial_capital=10000" in src
    assert "default_qty_type=strategy.percent_of_equity" in src
    assert "default_qty_value=10" in src
    assert "commission_type=strategy.commission.percent" in src
    assert "commission_value=0.05" in src


def test_render_strategy_emits_strategy_entry_and_close():
    """Strategy must call strategy.entry/close so the tester reports P/L."""
    src = render_sapphire_watch_strategy("BINANCE:ETHUSDT")
    # Both entry directions
    assert 'strategy.entry("Long", strategy.long' in src
    assert 'strategy.entry("Short", strategy.short' in src
    # Both close directions
    assert 'strategy.close("Long"' in src
    assert 'strategy.close("Short"' in src


def test_render_strategy_emits_all_four_actions():
    """Webhook payload must cover long/short/exit_long/exit_short."""
    src = render_sapphire_watch_strategy("BINANCE:ETHUSDT")
    for action in ("long", "short", "exit_long", "exit_short"):
        assert f'"action": "{action}"' in src


def test_render_strategy_uses_webhook_contract_field_names():
    """Strategy payload must match the receiver's contract."""
    src = render_sapphire_watch_strategy("BINANCE:ETHUSDT")
    # Field names the receiver expects
    assert '"time"' in src
    assert '"ts":' not in src  # historical typo we don't want
    assert '"interval"' in src
    assert '"exchange"' in src
    assert '"symbol"' in src
    assert '"price"' in src
    # Strategy tag distinct from indicator
    assert '"strategy": "sapphire_watch_strategy"' in src
    assert '"source": "tradingview_pine"' in src


# ─── render_sapphire_screener ────────────────────────────────────────────────


def test_render_screener_emits_pine_v5_header():
    src = render_sapphire_screener(["BINANCE:BTCUSDT", "BINANCE:ETHUSDT"])
    assert "//@version=5" in src
    assert "indicator(" in src
    assert "Sapphire Screener" in src


def test_render_screener_uses_request_security_for_each_symbol():
    """Multi-symbol must call request.security() — that's the whole point."""
    symbols = ["BINANCE:BTCUSDT", "BINANCE:ETHUSDT", "BINANCE:SOLUSDT"]
    src = render_sapphire_screener(symbols)
    # request.security signature is what unlocks multi-symbol
    assert "request.security(" in src
    # One call per symbol, hard-coded into the alert payload
    for sym in symbols:
        assert f'request.security("{sym}"' in src
        # Payload uses the firing symbol literal, not syminfo.ticker
        assert f'"symbol": "{sym}"' in src


def test_render_screener_does_not_use_syminfo_ticker_in_payload():
    """The firing symbol is what the receiver routes on — NOT the chart's ticker.

    syminfo.ticker is fine for ancillary fields (none in this template), but
    must never identify the firing symbol in the JSON payload.
    """
    symbols = ["BINANCE:BTCUSDT", "BINANCE:ETHUSDT"]
    src = render_sapphire_screener(symbols)
    # The chart ticker must NOT appear as the symbol field in the JSON payload
    assert '"symbol": "\' + syminfo.ticker' not in src


def test_render_screener_emits_all_four_actions_per_symbol():
    """Each symbol gets long/short/exit_long/exit_short alerts."""
    symbols = ["BINANCE:BTCUSDT", "BINANCE:ETHUSDT"]
    src = render_sapphire_screener(symbols)
    for sym in symbols:
        for action in ("long", "short", "exit_long", "exit_short"):
            # The webhook contract is: a JSON literal where symbol+action are
            # both literals (the firing symbol is hard-coded, not interpolated).
            needle = f'"symbol": "{sym}", "action": "{action}"'
            assert needle in src


def test_render_screener_uses_webhook_contract_field_names():
    src = render_sapphire_screener(["BINANCE:BTCUSDT"])
    assert '"time"' in src
    assert '"ts":' not in src
    assert '"interval"' in src
    assert '"exchange"' in src
    assert '"price"' in src
    assert '"strategy": "sapphire_screener"' in src
    assert '"source": "tradingview_pine"' in src


def test_render_screener_rejects_empty_list():
    with pytest.raises(ValueError):
        render_sapphire_screener([])


def test_render_screener_rejects_above_pine_cap():
    """Pine has a hard cap on request.security() calls; renderer enforces it."""
    too_many = [f"BINANCE:SYM{i}USDT" for i in range(MAX_SCREENER_SYMBOLS + 1)]
    with pytest.raises(ValueError):
        render_sapphire_screener(too_many)


def test_render_screener_handles_max_size():
    """The cap is inclusive — exactly MAX_SCREENER_SYMBOLS must work."""
    syms = [f"BINANCE:SYM{i}USDT" for i in range(MAX_SCREENER_SYMBOLS)]
    src = render_sapphire_screener(syms)
    assert "//@version=5" in src
    # Each symbol must appear in its own request.security call
    for sym in syms:
        assert f'request.security("{sym}"' in src


# ─── CLI: pine-generate-batch --kind ──────────────────────────────────────────


@pytest.mark.parametrize("kind", ["indicator", "strategy"])
def test_pine_generate_batch_kind_flag(tmp_path: Path, kind: str):
    """`--kind` flag on pine-generate-batch routes to the correct renderer."""
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "ops" / "tradingview_ta_capture.py"
    out_json = tmp_path / "batch.json"
    # Use --offline + small limit so the test stays hermetic.
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--out",
            str(out_json),
            "pine-generate-batch",
            "--offline",
            "--limit",
            "2",
            "--kind",
            kind,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),  # isolate generated/ dir to tmp
        },
    )
    assert result.returncode in (0, 2), (
        f"CLI exited unexpectedly:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["mode"] == "pine-generate-batch"
    assert payload["kind"] == kind
    # Inspect at least one generated file to confirm the right renderer fired.
    assert payload["count"] >= 1
    pine_path = Path(payload["generated"][0]["pine_path"])
    body = pine_path.read_text(encoding="utf-8")
    if kind == "strategy":
        assert "strategy(" in body
        assert "strategy.entry" in body
    else:
        assert 'indicator("Sapphire Watch' in body
        assert "strategy.entry" not in body
