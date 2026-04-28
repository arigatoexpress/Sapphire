"""Unit tests for plugins/claw-sapphire/tools/tho_intel.py.

Tests cover the market analysis logic, buyer readiness signals, and graceful
degradation when external dependencies (FRED, Regional Intel, THO API) are down.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
SAPPHIRE = Path(__file__).resolve().parents[2]
TOOLS = SAPPHIRE / "plugins" / "claw-sapphire" / "tools"
INTERNAL = TOOLS / "internal"

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# Load internal/ implementation directly — shim monkeypatch can't cross boundary.
_tho_spec = importlib.util.spec_from_file_location("tho_intel", INTERNAL / "tho_intel.py")
tho = importlib.util.module_from_spec(_tho_spec)
_tho_spec.loader.exec_module(tho)


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_macro_housing(mortgage_rate: float):
    return {
        "housing": {
            "30Y Mortgage Rate %": {"value": mortgage_rate, "label": "30Y Mortgage Rate"},
        }
    }


def _mock_action_market(
    mortgage_rate=6.5,
    permits=None,
    tho_customers=120,
    tho_conversion=55,
    regional_up=True,
    tho_api_up=True,
):
    """Return a mock action_market() result for buyer tests."""
    return {
        "success": True,
        "housing": {},
        "rates": {},
        "permits": {"total": len(permits or []), "subdivisions": 0},
        "tho": {
            "customers": tho_customers,
            "conversion": tho_conversion,
            "recent_leads": 5,
        },
        "analysis": {
            "mortgage_rate": mortgage_rate,
            "affordability": "challenging" if mortgage_rate > 6.5 else "moderate",
            "houston_permits": len(permits or []),
            "new_subdivisions": 0,
            "tho_customers": tho_customers,
            "tho_conversion": tho_conversion,
            "tho_recent_leads": 5,
            "market_sentiment": (
                "bullish — rates dropping, demand should increase"
                if mortgage_rate < 6
                else "bearish — high rates suppressing demand"
                if mortgage_rate > 7
                else "neutral — rates stable, steady demand"
            ),
        },
    }


# ── action_market ─────────────────────────────────────────────────────────────


class TestActionMarket:
    def _run(self, housing_resp, rates_resp, permits_data=None, tho_token="", tho_stats=None):

        def fake_run_tool(name, params):
            if name == "macro_data" and params.get("action") == "housing":
                return housing_resp
            if name == "macro_data" and params.get("action") == "rates":
                return rates_resp
            return {}

        # Mock urllib.request.urlopen to control Regional Intel and THO API
        def fake_urlopen(req, timeout=None, context=None):
            resp = MagicMock()
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "8787" in url:
                resp.read.return_value = (
                    b'{"permits": [{"id":1},{"id":2}]}' if permits_data is None else permits_data
                )
            elif "admin/verify" in url:
                resp.read.return_value = (
                    f'{{"token": "{tho_token}"}}'.encode() if tho_token else b'{"token": ""}'
                )
            elif "analytics/customers" in url:
                stats = tho_stats or {"total": 100, "conversion_rate": 50}
                import json

                resp.read.return_value = json.dumps(stats).encode()
            return resp.__enter__.return_value if hasattr(resp, "__enter__") else resp

        with (
            patch.object(tho, "_run_tool", side_effect=fake_run_tool),
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            return tho.action_market()

    def test_returns_success_true(self):
        result = self._run(
            _make_macro_housing(6.5),
            {},
            tho_token="tok",
            tho_stats={"total": 80, "conversion_rate": 45},
        )
        assert result["success"] is True

    def test_has_required_keys(self):
        result = self._run(_make_macro_housing(6.5), {})
        for key in ("success", "housing", "rates", "permits", "tho", "analysis"):
            assert key in result

    def test_mortgage_rate_extracted_from_housing_label(self):
        result = self._run(_make_macro_housing(7.2), {})
        assert result["analysis"]["mortgage_rate"] == pytest.approx(7.2)

    def test_affordability_challenging_when_rate_above_65(self):
        result = self._run(_make_macro_housing(7.0), {})
        assert result["analysis"]["affordability"] == "challenging"

    def test_affordability_favorable_when_rate_below_55(self):
        result = self._run(_make_macro_housing(4.5), {})
        assert result["analysis"]["affordability"] == "favorable"

    def test_graceful_when_regional_intel_down(self):
        with (
            patch.object(tho, "_run_tool", return_value={}),
            patch("urllib.request.urlopen", side_effect=OSError("connection refused")),
        ):
            result = tho.action_market()
        assert result["success"] is True
        assert result["permits"]["total"] == 0

    def test_graceful_when_tho_api_down(self):
        def fake_urlopen(req, timeout=None, context=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "8787" in url:
                mock = MagicMock()
                mock.__enter__ = lambda s: s
                mock.__exit__ = MagicMock(return_value=False)
                mock.read.return_value = b'{"permits": []}'
                return mock
            raise OSError("THO API down")

        with (
            patch.object(tho, "_run_tool", return_value={}),
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            result = tho.action_market()
        assert result["success"] is True
        assert result["tho"]["customers"] == 0

    def test_market_sentiment_bearish_when_rate_high(self):
        result = self._run(_make_macro_housing(7.5), {})
        assert "bearish" in result["analysis"]["market_sentiment"]

    def test_market_sentiment_bullish_when_rate_low(self):
        result = self._run(_make_macro_housing(5.0), {})
        assert "bullish" in result["analysis"]["market_sentiment"]


# ── action_buyers ─────────────────────────────────────────────────────────────


class TestActionBuyers:
    def _run_buyers(self, mortgage_rate, permits_count=0, tho_conversion=0):
        mock_market = _mock_action_market(
            mortgage_rate=mortgage_rate,
            permits=list(range(permits_count)),
            tho_conversion=tho_conversion,
        )
        with patch.object(tho, "action_market", return_value=mock_market):
            return tho.action_buyers()

    def test_headwind_indicator_when_rate_high(self):
        result = self._run_buyers(7.0)
        sigs = [i["signal"] for i in result["indicators"]]
        assert "headwind" in sigs

    def test_strong_buy_indicator_when_rate_low(self):
        result = self._run_buyers(4.5)
        sigs = [i["signal"] for i in result["indicators"]]
        assert "strong_buy" in sigs

    def test_neutral_indicator_when_rate_moderate(self):
        result = self._run_buyers(6.0)
        sigs = [i["signal"] for i in result["indicators"]]
        assert "neutral" in sigs

    def test_strong_demand_when_many_permits(self):
        result = self._run_buyers(6.0, permits_count=60)
        sigs = [i["signal"] for i in result["indicators"]]
        assert "strong_demand" in sigs

    def test_healthy_conversion_included(self):
        result = self._run_buyers(6.0, tho_conversion=65)
        sigs = [i["signal"] for i in result["indicators"]]
        assert "healthy" in sigs

    def test_returns_required_keys(self):
        result = self._run_buyers(6.5)
        assert "success" in result
        assert "indicators" in result
        assert "market_sentiment" in result

    def test_market_sentiment_present(self):
        result = self._run_buyers(7.5)
        assert result["market_sentiment"]  # non-empty string


class TestPinLoader:
    """PIN must come from env or secrets dir — never hardcoded."""

    def test_env_var_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("THO_ADMIN_PIN", "env-pin")
        monkeypatch.setenv("SAPPHIRE_SECRETS_DIR", str(tmp_path))
        (tmp_path / "tho_admin_pin").write_text("file-pin")
        monkeypatch.setattr(tho, "SECRETS_DIR", tmp_path)
        assert tho._load_tho_pin() == "env-pin"

    def test_secrets_file_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delenv("THO_ADMIN_PIN", raising=False)
        (tmp_path / "tho_admin_pin").write_text("  file-pin  \n")
        monkeypatch.setattr(tho, "SECRETS_DIR", tmp_path)
        assert tho._load_tho_pin() == "file-pin"

    def test_none_when_neither_set(self, monkeypatch, tmp_path):
        monkeypatch.delenv("THO_ADMIN_PIN", raising=False)
        monkeypatch.setattr(tho, "SECRETS_DIR", tmp_path)
        assert tho._load_tho_pin() is None

    def test_empty_env_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.setenv("THO_ADMIN_PIN", "")
        (tmp_path / "tho_admin_pin").write_text("file-pin")
        monkeypatch.setattr(tho, "SECRETS_DIR", tmp_path)
        assert tho._load_tho_pin() == "file-pin"

    def test_market_skips_tho_api_when_no_pin(self, monkeypatch):
        """action_market must not call Cloud Run when PIN missing."""
        monkeypatch.setattr(tho, "_load_tho_pin", lambda: None)
        monkeypatch.setattr(tho, "_run_tool", lambda name, params: {})

        call_log = []

        def fake_urlopen(*args, **kwargs):
            req = args[0] if args else kwargs.get("req")
            url = req.full_url if hasattr(req, "full_url") else str(req)
            call_log.append(url)
            raise Exception("should not be called for THO")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = tho.action_market()

        assert result["success"] is True
        assert all("project-go-forward" not in u for u in call_log), f"THO was called: {call_log}"
        assert result["tho"]["customers"] == 0


class TestNoHardcodedSecrets:
    """Guard against regressions that bake the PIN back into source."""

    def test_pin_not_in_tho_intel(self):
        src = (INTERNAL / "tho_intel.py").read_text()
        assert '"4832"' not in src, "Hardcoded PIN must not appear in source"
        assert "'4832'" not in src
