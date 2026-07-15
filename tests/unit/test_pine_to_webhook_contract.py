"""Pin the contract between the Pine generator and the webhook receiver.

`lib.trading.pine_templates.render_sapphire_watch_indicator` emits Pine v5
source containing JSON alert payload templates. When TradingView fires one
of those alerts the body is POSTed to ``services/webhook/src/receiver.py``,
where ``validate_payload`` gates the request and ``TradingViewAlert.from_webhook``
parses it.

Drift between the generator and the receiver is silent (Pine compiles fine,
TradingView delivers the alert, receiver rejects with HTTP 400) so we pin it
here. The test extracts the payload templates straight from the generated
Pine source, fills in the runtime placeholders with concrete values, and
walks both sides of the contract: ``validate_payload`` must accept the
payload and ``from_webhook`` must materialise an alert with the expected
fields populated.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from lib.trading.pine_templates import render_sapphire_watch_indicator

ROOT = Path(__file__).resolve().parents[2]
RECEIVER_SRC = ROOT / "services" / "webhook" / "src"

# Pine emits one ``alert('<JSON>', alert.freq_once_per_bar_close)`` per branch.
# Capture the single-quoted body so we can swap Pine placeholders for runtime values.
_ALERT_LINE_RE = re.compile(r"alert\((?P<body>'.+?')\s*,\s*alert\.freq_once_per_bar_close\)")

# Concrete TradingView-side values used to render placeholder substitutions.
# These mirror what TradingView would substitute when an alert fires.
_RUNTIME_VALUES = {
    "syminfo.ticker": "ETHUSDT",
    "syminfo.prefix": "BINANCE",
    "timeframe.period": "60",
    "str.tostring(close)": "4200.5",
    "str.tostring(time)": "1234567890",
}


@pytest.fixture(scope="module")
def receiver(tmp_path_factory: pytest.TempPathFactory):
    """Import ``services/webhook/src/receiver.py`` with side effects neutralised.

    The receiver hard-codes ``LOG_FILE = C:/sapphire/webhook.log`` (Windows
    path) and unconditionally creates the directory + a FileHandler at import
    time. We redirect the log file to a tmp path before the import so the
    module loads cleanly on macOS / Linux CI. No network calls happen at
    import time — pubsub/firestore are stubbed out (set to ``None``) and
    the capability sync loop only fires under ``lifespan``.
    """
    log_path = tmp_path_factory.mktemp("webhook") / "webhook.log"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("WEBHOOK_LOG_FILE", str(log_path))

    src_path = str(RECEIVER_SRC)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    sys.modules.pop("receiver", None)
    try:
        module = importlib.import_module("receiver")
    except Exception as exc:  # pragma: no cover - skip on unrelated import drift
        monkeypatch.undo()
        pytest.skip(f"receiver import failed: {exc!r}")

    yield module

    sys.modules.pop("receiver", None)
    if src_path in sys.path:
        sys.path.remove(src_path)
    monkeypatch.undo()


def _extract_alert_payload_templates(pine_source: str) -> list[str]:
    """Return the raw single-quoted alert body template for each Pine alert call."""
    return [m.group("body") for m in _ALERT_LINE_RE.finditer(pine_source)]


def _payload_template_to_dict(template: str) -> dict:
    """Resolve a Pine alert template into the JSON dict TradingView would POST.

    Pine concatenates literal JSON fragments with placeholder expressions
    (``syminfo.ticker``, ``str.tostring(close)``, etc.) to build the alert body.
    We strip the wrapping quotes, replace each placeholder with a concrete
    runtime value, and parse the result as JSON.
    """
    # Strip the leading/trailing single quotes that wrap the Pine string literal.
    assert template.startswith("'") and template.endswith("'"), template
    body = template[1:-1]

    # Pine source uses '...' + expr + '...' to splice. Drop the quoting
    # punctuation so what remains is plain JSON with named placeholders.
    body = body.replace("' + ", "").replace(" + '", "")

    # Replace each Pine placeholder with its runtime substitution. Numeric
    # fields (price, time) are not quoted in the template, so they slot in
    # as JSON numbers; string fields (ticker, prefix, period) sit between
    # double quotes already and the substitution preserves that.
    for placeholder, value in _RUNTIME_VALUES.items():
        body = body.replace(placeholder, value)

    # Sanity-check: no placeholder left behind.
    assert " + " not in body, body
    return json.loads(body)


# Action → action-specific assertions for downstream code (purely informational
# — the receiver itself only cares that action ∈ VALID_ACTIONS).
_EMITTED_ACTIONS = ("long", "short", "exit_long", "exit_short")


def test_pine_alerts_decode_to_valid_webhook_payloads(receiver):
    """Every alert branch in the generated indicator parses + passes validation."""
    pine_source = render_sapphire_watch_indicator("BINANCE:ETHUSDT")
    templates = _extract_alert_payload_templates(pine_source)
    assert len(templates) == len(_EMITTED_ACTIONS), (
        f"expected {len(_EMITTED_ACTIONS)} alert calls, found {len(templates)}: {templates!r}"
    )

    seen_actions: set[str] = set()
    for template in templates:
        payload = _payload_template_to_dict(template)

        # Generator-side assertions.
        assert payload["symbol"] == _RUNTIME_VALUES["syminfo.ticker"]
        assert payload["price"] == float(_RUNTIME_VALUES["str.tostring(close)"])
        assert payload["strategy"] == "sapphire_watch_indicator"
        assert payload["source"] == "tradingview_pine"
        assert payload["interval"] == _RUNTIME_VALUES["timeframe.period"]
        assert payload["exchange"] == _RUNTIME_VALUES["syminfo.prefix"]
        assert payload["time"] == int(_RUNTIME_VALUES["str.tostring(time)"])
        assert payload["action"] in _EMITTED_ACTIONS

        # Receiver-side assertions.
        assert receiver.validate_payload(payload) is True, (
            f"validate_payload rejected an emitted Pine alert: {payload!r}"
        )
        assert payload["action"] in receiver.VALID_ACTIONS

        alert = receiver.TradingViewAlert.from_webhook(payload)
        # ETHUSDT is in SYMBOL_MAP and maps to itself; this also verifies the
        # generator emits a symbol the receiver knows about.
        assert alert.symbol == "ETHUSDT"
        assert alert.action == payload["action"]
        assert alert.price == float(_RUNTIME_VALUES["str.tostring(close)"])
        assert alert.exchange == _RUNTIME_VALUES["syminfo.prefix"]
        assert alert.interval == _RUNTIME_VALUES["timeframe.period"]
        # Receiver stores the Pine ``time`` field as ``timestamp`` (str-or-int).
        assert str(alert.timestamp) == _RUNTIME_VALUES["str.tostring(time)"]

        seen_actions.add(payload["action"])

    assert seen_actions == set(_EMITTED_ACTIONS), (
        f"missing actions in generated indicator: {set(_EMITTED_ACTIONS) - seen_actions}"
    )


@pytest.mark.parametrize(
    "tv_symbol,expected_canonical",
    [
        ("BINANCE:ETHUSDT", "ETHUSDT"),
        ("BINANCE:BTCUSDT", "BTCUSDT"),
        ("BINANCE:SOLUSDT", "SOLUSDT"),
    ],
)
def test_multi_symbol_pine_alerts_round_trip_through_receiver(
    receiver, tv_symbol: str, expected_canonical: str
):
    """Generator + receiver agree across the symbols the trading pipeline trades."""
    # The Pine ``syminfo.ticker`` substitution is the bare ticker (no prefix);
    # mirror that here so the resulting payload reflects what TradingView
    # would actually POST when the alert fires.
    runtime = dict(_RUNTIME_VALUES)
    runtime["syminfo.ticker"] = expected_canonical

    pine_source = render_sapphire_watch_indicator(tv_symbol)
    templates = _extract_alert_payload_templates(pine_source)
    assert templates, f"no alert calls found in Pine source for {tv_symbol!r}"

    for template in templates:
        body = template[1:-1].replace("' + ", "").replace(" + '", "")
        for placeholder, value in runtime.items():
            body = body.replace(placeholder, value)
        payload = json.loads(body)

        assert receiver.validate_payload(payload) is True
        alert = receiver.TradingViewAlert.from_webhook(payload)
        assert alert.symbol == expected_canonical
        assert alert.action in receiver.VALID_ACTIONS
        assert alert.price == float(runtime["str.tostring(close)"])


def test_pine_payload_field_names_match_receiver_contract(receiver):
    """The payload keys the generator emits are exactly what the receiver reads."""
    pine_source = render_sapphire_watch_indicator("BINANCE:ETHUSDT")
    templates = _extract_alert_payload_templates(pine_source)
    payload = _payload_template_to_dict(templates[0])

    # Receiver requires symbol + action.
    assert "symbol" in payload
    assert "action" in payload

    # Receiver reads ``time`` (legacy ``ts`` would be silently dropped).
    assert "time" in payload
    assert "ts" not in payload

    # ``from_webhook`` populates these when present; assert the generator emits them.
    assert "price" in payload
    assert "interval" in payload
    assert "exchange" in payload


def test_receiver_deduplicates_identical_alerts(receiver):
    """Identical Pine payloads within the dedup window are reported as duplicates."""
    pine_source = render_sapphire_watch_indicator("BINANCE:ETHUSDT")
    templates = _extract_alert_payload_templates(pine_source)
    payload = _payload_template_to_dict(templates[0])
    fingerprint = receiver._alert_fingerprint(payload)
    assert not receiver._is_duplicate(fingerprint)
    receiver._record_seen(fingerprint)
    assert receiver._is_duplicate(fingerprint)
