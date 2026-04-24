"""Tests for the scheduled Sapphire morning digest sender."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import dev_pulse  # type: ignore
import morning_digest  # type: ignore


def _pulse() -> dev_pulse.DevPulse:
    return dev_pulse.DevPulse(
        trading=dev_pulse.TradingStatus(
            last_signal_at="2026-04-24T12:00:00+00:00",
            signals_today_count=1,
            open_paper_positions=0,
            paper_portfolio_value=100000.0,
            paper_unrealized_pnl_usd=0.0,
            paper_realized_pnl_today_usd=0.0,
        ),
        webhook_delivery=dev_pulse.WebhookDeliveryStatus(
            partner_id_stats=[],
            total_attempted_24h=0,
            total_failed_24h=0,
        ),
    )


def test_morning_digest_dry_run_does_not_send(monkeypatch):
    monkeypatch.setattr(morning_digest.dev_pulse, "pulse", _pulse)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        morning_digest,
        "send_alert",
        lambda message, priority="p1": sent.append((message, priority)),
    )

    result = morning_digest.run(dry_run=True)

    assert result["ok"] is True
    assert result["sent"] is False
    assert result["priority"] == "p3"
    assert "Sapphire Morning Digest" in result["message"]
    assert sent == []


def test_morning_digest_sends_p3(monkeypatch):
    monkeypatch.setattr(morning_digest.dev_pulse, "pulse", _pulse)
    sent: list[tuple[str, str]] = []

    def fake_send(message: str, priority: str = "p1"):
        sent.append((message, priority))
        return {"ok": True}

    monkeypatch.setattr(morning_digest, "send_alert", fake_send)

    result = morning_digest.run()

    assert result["ok"] is True
    assert result["sent"] is True
    assert sent[0][1] == "p3"
