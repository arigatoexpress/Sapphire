"""Regression coverage for the ``equity_quote`` price fallback chain.

``plugins/claw-sapphire/lib/market_data.py`` builds ``MarketQuote.price`` from a
four-term ``or`` chain::

    last_price -> prev_close -> close -> regular_market_previous_close -> 0

This exists because yfinance returns an *explicit* ``"last_price": None`` for
crypto tickers (BTC-USD / ETH-USD / SOL-USD) rather than omitting the key. The
original code was ``r.get("last_price", 0)``, whose default only fires on a
*missing* key -- a present-but-null value sails straight through and poisons
``MarketQuote.price`` with ``None``. PR #525 replaced it with the ``or`` chain
(truthiness, not key presence).

The chain had zero direct test references before this module: the only other
``equity_quote`` hit in the suite is ``test_plugins_lib_nvidia_agents.py``,
which covers a different module. It has already been rewritten once in place by
the factory repo fixer (``c125dcfe``, formatting-only), so a future refactor
dropping a term would ship silently and return ``0`` for all crypto. These
tests pin both the values and the term ordering.

Module is loaded via ``importlib.util.spec_from_file_location`` (mirroring
``test_plugins_lib_quant_analysis.py``) so the production source is exercised
without putting ``plugins/claw-sapphire/lib`` on ``sys.path``.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "plugins" / "claw-sapphire" / "lib" / "market_data.py"

# Ordered exactly as the production ``or`` chain evaluates them.
FALLBACK_KEYS = (
    "last_price",
    "prev_close",
    "close",
    "regular_market_previous_close",
)

CRYPTO_SYMBOLS = ("BTC-USD", "ETH-USD", "SOL-USD")


MODULE_NAME = "claw_sapphire_market_data_under_test"


@pytest.fixture(scope="module")
def market_data():
    """Load the plugin lib in isolation.

    The module must be registered in ``sys.modules`` *before* ``exec_module``:
    ``@dataclass`` resolves ``cls.__module__`` through ``sys.modules`` while
    processing ``MarketQuote``, and raises ``AttributeError`` on a miss.
    """
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    assert spec and spec.loader, f"could not load {MODULE_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(MODULE_NAME, None)


def _quote(market_data, payload: dict, symbol: str = "BTC-USD"):
    """Call ``equity_quote`` with ``_openbb_get`` stubbed to one result row."""
    with patch.object(market_data, "_openbb_get", return_value={"results": [payload]}):
        return market_data.equity_quote(symbol)


# ─── the reported bug: yfinance sends last_price=None for crypto ─────────────


@pytest.mark.parametrize("symbol", CRYPTO_SYMBOLS)
def test_crypto_null_last_price_falls_back_to_prev_close(market_data, symbol):
    """The exact reported failure: explicit None must not become the price."""
    quote = _quote(
        market_data,
        {
            "symbol": symbol,
            "last_price": None,
            "prev_close": 61250.42,
            "open": 60900.0,
            "high": 61800.0,
            "low": 60100.0,
            "volume": 812345,
        },
        symbol=symbol,
    )

    assert quote.symbol == symbol
    assert quote.price == 61250.42
    assert quote.price is not None


@pytest.mark.parametrize("symbol", CRYPTO_SYMBOLS)
def test_crypto_price_is_never_none_or_zero_when_any_term_present(market_data, symbol):
    """Every single-term payload must still yield a usable positive price."""
    for key in FALLBACK_KEYS:
        payload = {"symbol": symbol, key: 1234.5}
        # Null out every earlier term the way yfinance actually does.
        for earlier in FALLBACK_KEYS[: FALLBACK_KEYS.index(key)]:
            payload[earlier] = None

        quote = _quote(market_data, payload, symbol=symbol)

        assert quote.price == 1234.5, f"{symbol}: {key} did not survive the chain"
        assert quote.price is not None
        assert quote.price > 0


# ─── term precedence ─────────────────────────────────────────────────────────


def test_last_price_wins_when_present(market_data):
    quote = _quote(
        market_data,
        {
            "symbol": "AAPL",
            "last_price": 175.0,
            "prev_close": 170.0,
            "close": 169.0,
            "regular_market_previous_close": 168.0,
        },
        symbol="AAPL",
    )
    assert quote.price == 175.0


def test_fallback_precedence_is_exact(market_data):
    """Each term must beat every term to its right."""
    expected = {
        "last_price": 10.0,
        "prev_close": 20.0,
        "close": 30.0,
        "regular_market_previous_close": 40.0,
    }
    # Walk the chain, nulling one more leading term each pass.
    for index, key in enumerate(FALLBACK_KEYS):
        payload = {"symbol": "BTC-USD", **expected}
        for earlier in FALLBACK_KEYS[:index]:
            payload[earlier] = None

        quote = _quote(market_data, payload)

        assert quote.price == expected[key], f"precedence broke at {key}"


def test_zero_valued_term_is_skipped_not_returned(market_data):
    """A 0.0 last_price is as useless as None -- the chain must keep walking."""
    quote = _quote(
        market_data,
        {"symbol": "ETH-USD", "last_price": 0.0, "prev_close": 3400.75},
        symbol="ETH-USD",
    )
    assert quote.price == 3400.75


# ─── exhausted chain + error paths ───────────────────────────────────────────


def test_all_terms_null_yields_zero_not_none(market_data):
    """Downstream sizing math must never receive None."""
    payload = {"symbol": "SOL-USD"}
    payload.update({key: None for key in FALLBACK_KEYS})

    quote = _quote(market_data, payload, symbol="SOL-USD")

    assert quote.price == 0
    assert quote.price is not None


def test_all_terms_absent_yields_zero(market_data):
    quote = _quote(market_data, {"symbol": "SOL-USD"}, symbol="SOL-USD")
    assert quote.price == 0


def test_empty_results_returns_error_dict(market_data):
    with patch.object(market_data, "_openbb_get", return_value={"results": []}):
        result = market_data.equity_quote("BTC-USD")

    assert isinstance(result, dict)
    assert "error" in result
    assert "BTC-USD" in result["error"]


def test_symbol_falls_back_to_requested_when_row_omits_it(market_data):
    quote = _quote(market_data, {"prev_close": 100.0}, symbol="BTC-USD")
    assert quote.symbol == "BTC-USD"


def test_other_ohlcv_fields_default_to_zero_not_none(market_data):
    """``open``/``high``/``low``/``volume`` use plain ``.get(k, 0)`` defaults."""
    quote = _quote(market_data, {"symbol": "BTC-USD", "prev_close": 61000.0})

    assert quote.open == 0
    assert quote.high == 0
    assert quote.low == 0
    assert quote.volume == 0
    assert quote.source == "openbb/yfinance"


# ─── source-level pin: the chain itself must not lose a term ─────────────────


def test_fallback_chain_source_retains_every_term_in_order(market_data):
    """Guard against a formatter or 'simplification' silently dropping a term.

    The value assertions above only prove the chain works for the payload
    shapes we imagined. This pins the source so removing ``close`` (say) fails
    loudly even if no value test happens to cover it.
    """
    source = inspect.getsource(market_data.equity_quote)
    positions = []
    for key in FALLBACK_KEYS:
        needle = f'r.get("{key}")'
        assert needle in source, f"fallback term {key!r} missing from equity_quote"
        positions.append(source.index(needle))

    assert positions == sorted(positions), "fallback terms are out of precedence order"
    assert "or 0" in source, "chain must terminate in a numeric 0, never None"
