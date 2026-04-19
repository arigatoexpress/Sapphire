"""Tests for the Kronos prediction tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "lib"))

_spec = importlib.util.spec_from_file_location("predict_kronos", TOOLS / "internal" / "predict_kronos.py")
pk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pk)


class _FakeResponse:
    """Minimal urlopen response stub."""

    def __init__(self, payload: dict, status: int = 200):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_fetch_openbb_uses_stdlib_and_normalizes_frame(monkeypatch):
    """OpenBB fetch should succeed without requests and normalize columns."""
    payload = {
        "results": [
            {"date": "2026-04-19T00:00:00Z", "Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 1000},
            {"date": "2026-04-19T01:00:00Z", "Open": 105, "High": 112, "Low": 101, "Close": 111, "Volume": 1200},
        ]
    }

    captured: dict[str, str] = {}

    def fake_urlopen(url: str, timeout: int = 10):
        captured["url"] = url
        captured["timeout"] = str(timeout)
        return _FakeResponse(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    df = pk._fetch_openbb("BTC-USD", "1h", 2)

    assert df is not None
    assert list(df.columns) == ["open", "high", "low", "close", "volume", "datetime"]
    assert len(df) == 2
    assert df.iloc[-1]["close"] == 111
    assert "crypto/price/historical" in captured["url"]
    assert "symbol=BTC-USD" in captured["url"]
    assert captured["timeout"] == "10"


def test_fetch_openbb_returns_none_on_empty_results(monkeypatch):
    """OpenBB fetch should return None when the provider yields no bars."""

    def fake_urlopen(url: str, timeout: int = 10):
        return _FakeResponse({"results": []})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert pk._fetch_openbb("SPY", "1d", 50) is None
