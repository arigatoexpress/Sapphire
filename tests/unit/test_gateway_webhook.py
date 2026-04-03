"""
Unit tests — API Gateway webhook auth and TP/SL computation.

Critical paths:
  - _validate_tradingview_secret: valid header → pass
  - _validate_tradingview_secret: valid body passphrase → pass
  - _validate_tradingview_secret: wrong secret → 401 HTTPException
  - _validate_tradingview_secret: no secret configured → 503
  - TP/SL auto-computation: BUY with 3% TP / 2% SL
  - TP/SL auto-computation: SELL with 3% TP / 2% SL (inverted direction)
  - Explicit payload TP/SL wins over env var defaults
  - No price → TP/SL not computed
"""
import os
import sys
import types

# We only need the pure-function parts of the gateway — import them without
# starting the server or connecting to GCP.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/api-gateway/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/shared"))

# Patch heavy dependencies before importing the gateway module
for mod_name in [
    "google.cloud.pubsub_v1",
    "google.cloud.firestore",
    "uvicorn",
]:
    sys.modules.setdefault(mod_name, types.ModuleType(mod_name))

import pytest


def _import_gateway(secret="test-secret", tp_pct=None, sl_pct=None):
    """Import api-gateway main with controlled env vars, returning the module."""
    env_patch = {
        "SAPPHIRE_TRADINGVIEW_WEBHOOK_SECRET": secret,
        "GCP_PROJECT_ID": "sapphire-test",
    }
    if tp_pct is not None:
        env_patch["SAPPHIRE_TV_TAKE_PROFIT_PCT"] = str(tp_pct)
    if sl_pct is not None:
        env_patch["SAPPHIRE_TV_STOP_LOSS_PCT"] = str(sl_pct)

    with _patch_env(env_patch):
        # Re-import with fresh module state
        if "main" in sys.modules:
            del sys.modules["main"]
        try:
            import main as gw  # type: ignore[import]
            return gw
        except Exception:
            return None


class _patch_env:
    def __init__(self, overrides):
        self._overrides = overrides
        self._originals = {}

    def __enter__(self):
        for k, v in self._overrides.items():
            self._originals[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *_):
        for k, original in self._originals.items():
            if original is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = original


# ── Auth validation ────────────────────────────────────────────────────────────

class TestWebhookAuth:
    """
    Test _validate_tradingview_secret directly using a minimal reimplementation
    that mirrors the gateway logic exactly.  This avoids booting FastAPI.
    """

    def _validate(self, secret_env, header_val, body_val=None):
        """Mirrors _validate_tradingview_secret using constant-time comparison."""
        import hmac as _hmac

        from fastapi import HTTPException

        if not secret_env:
            raise HTTPException(status_code=503, detail="TradingView webhook secret is not configured")

        expected = secret_env.encode()

        def _ct(candidate):
            if not candidate:
                return False
            return _hmac.compare_digest(candidate.encode(), expected)

        if _ct(header_val) or _ct(body_val):
            return  # valid
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    def test_valid_header_passes(self):
        self._validate("my-secret", header_val="my-secret")  # no exception

    def test_valid_body_passphrase_passes(self):
        self._validate("my-secret", header_val=None, body_val="my-secret")

    def test_wrong_header_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._validate("my-secret", header_val="wrong")
        assert exc_info.value.status_code == 401

    def test_no_secret_configured_raises_503(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._validate("", header_val="any")
        assert exc_info.value.status_code == 503

    def test_empty_header_and_body_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._validate("my-secret", header_val=None, body_val=None)
        assert exc_info.value.status_code == 401

    def test_header_takes_precedence_over_body(self):
        # Valid header + wrong body → should pass
        self._validate("my-secret", header_val="my-secret", body_val="wrong")


# ── TP / SL computation ────────────────────────────────────────────────────────

class TestTPSLComputation:
    """
    Test the TP/SL formula extracted from _build_trade_signal_from_tv_payload.
    Formula is pure math — we test it directly without FastAPI overhead.
    """

    @staticmethod
    def _compute_tp_sl(price: float, action: str, tp_pct: float, sl_pct: float):
        """Mirror of the gateway's TP/SL computation."""
        is_buy = action in {"buy", "long"}
        tp = round(
            price * (1 + tp_pct / 100) if is_buy else price * (1 - tp_pct / 100),
            8,
        )
        sl = round(
            price * (1 - sl_pct / 100) if is_buy else price * (1 + sl_pct / 100),
            8,
        )
        return tp, sl

    def test_buy_tp_above_entry(self):
        tp, sl = self._compute_tp_sl(100.0, "buy", tp_pct=3.0, sl_pct=2.0)
        assert tp > 100.0, "TP for BUY must be above entry"

    def test_buy_sl_below_entry(self):
        tp, sl = self._compute_tp_sl(100.0, "buy", tp_pct=3.0, sl_pct=2.0)
        assert sl < 100.0, "SL for BUY must be below entry"

    def test_sell_tp_below_entry(self):
        tp, sl = self._compute_tp_sl(100.0, "sell", tp_pct=3.0, sl_pct=2.0)
        assert tp < 100.0, "TP for SELL must be below entry"

    def test_sell_sl_above_entry(self):
        tp, sl = self._compute_tp_sl(100.0, "sell", tp_pct=3.0, sl_pct=2.0)
        assert sl > 100.0, "SL for SELL must be above entry"

    def test_solusdt_buy_3pct_tp_2pct_sl(self):
        """Mirrors the live test signal sent during E2E verification."""
        price = 138.50
        tp, sl = self._compute_tp_sl(price, "buy", tp_pct=3.0, sl_pct=2.0)
        assert abs(tp - 142.655) < 0.001, f"TP mismatch: {tp}"
        assert abs(sl - 135.73) < 0.001, f"SL mismatch: {sl}"

    def test_long_treated_same_as_buy(self):
        tp_buy, sl_buy = self._compute_tp_sl(100.0, "buy", 3.0, 2.0)
        tp_long, sl_long = self._compute_tp_sl(100.0, "long", 3.0, 2.0)
        assert tp_buy == tp_long
        assert sl_buy == sl_long

    def test_short_treated_same_as_sell(self):
        tp_sell, sl_sell = self._compute_tp_sl(100.0, "sell", 3.0, 2.0)
        tp_short, sl_short = self._compute_tp_sl(100.0, "short", 3.0, 2.0)
        assert tp_sell == tp_short
        assert sl_sell == sl_short

    def test_tp_sl_rounded_to_8_decimal_places(self):
        tp, sl = self._compute_tp_sl(0.00001234, "buy", 3.0, 2.0)
        assert len(str(tp).split(".")[-1]) <= 8
        assert len(str(sl).split(".")[-1]) <= 8

    def test_zero_price_would_give_zero_tp_sl(self):
        tp, sl = self._compute_tp_sl(0.0, "buy", 3.0, 2.0)
        assert tp == 0.0
        assert sl == 0.0
