"""Isolated unit tests for ``lib.content``.

Covers:

* ``performance_policy`` — small-sample accuracy gating, sample-size extraction,
  the public-track-record threshold (and the "no predictions block at all"
  defensive branch).
* ``formatters`` — LinkedIn 1300-char clamp + small-sample copy, Substack
  markdown shape, X thread numbering and 270-char tweet ceiling.
* ``approval`` — QA-fail rejection, sensitivity-flag rejection, autonomous
  approval path. Telegram approval is mocked.
* ``auto_publish`` — discovery + ledger filtering on a tmp directory tree.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from lib.content import auto_publish, performance_policy
from lib.content.approval import ApprovalStatus, approve
from lib.content.formatters import (
    LINKEDIN_LIMIT,
    SHORT_DISCLAIMER,
    X_TWEET_LIMIT,
    _shorten_to,
    _split_tweets,
    format_linkedin,
    format_substack,
    format_x_thread,
)
from lib.content.report_generator import Report

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _crypto_facts(total_preds: int = 50, hits: int = 30) -> dict:
    """Build a 'weekly_crypto_brief' facts dict with adjustable sample size."""
    return {
        "predictions": {
            "total": total_preds,
            "hits": hits,
            "accuracy": (hits / total_preds) if total_preds else 0.0,
            "by_symbol": {
                "BTC": {"hits": 12, "total": 18, "accuracy": 12 / 18},
                "ETH": {"hits": 9, "total": 17, "accuracy": 9 / 17},
            },
        },
        "portfolio": {
            "capital": 102_500.0,
            "initial_capital": 100_000.0,
            "pnl_pct": 2.5,
            "open_positions": 2,
            "symbols": ["BTC", "ETH"],
            "positions": [
                {
                    "symbol": "BTC",
                    "side": "LONG",
                    "entry_price": 95_000,
                    "stop_loss": 90_000,
                    "take_profit": 110_000,
                },
            ],
        },
        "signal_pipeline": {
            "count": 4,
            "symbols": {"BTC": 2, "ETH": 2},
        },
    }


def _make_crypto_report(facts: dict | None = None) -> Report:
    facts = facts or _crypto_facts()
    return Report(
        kind="weekly_crypto_brief",
        title="Weekly Crypto Brief",
        generated_at="2026-04-27T08:00:00+00:00",
        facts=facts,
        body=(
            "Sapphire's six-factor TA model produced reliable signals this week. "
            "Paper portfolio gained $2,500 on a $100,000 base, a clean +2.5% return."
        ),
        sources=["data/trading_predictions.jsonl", "data/paper_portfolio.json"],
        tags=["crypto", "weekly"],
    )


# ---------------------------------------------------------------------------
# performance_policy
# ---------------------------------------------------------------------------


class TestPerformancePolicy:
    def test_prediction_sample_size_handles_int(self) -> None:
        assert performance_policy.prediction_sample_size({"total": 42}) == 42

    def test_prediction_sample_size_unwraps_predictions_block(self) -> None:
        # When the dict has a `predictions` sub-mapping, that's what we extract.
        nested = {"predictions": {"total": 99}}
        assert performance_policy.prediction_sample_size(nested) == 99

    def test_prediction_sample_size_returns_zero_on_garbage(self) -> None:
        assert performance_policy.prediction_sample_size({"total": "abc"}) == 0
        assert performance_policy.prediction_sample_size(None) == 0

    def test_has_public_track_record_at_threshold(self) -> None:
        assert performance_policy.has_public_accuracy_track_record({"total": 100}) is True
        assert performance_policy.has_public_accuracy_track_record({"total": 99}) is False

    def test_small_sample_notice_includes_count(self) -> None:
        msg = performance_policy.small_sample_accuracy_notice(
            {"total": 35},
            subject="Sapphire's TA model",
        )
        assert "35 scored forecasts" in msg
        assert "Sapphire's TA model" in msg
        assert "100" in msg

    def test_small_sample_notice_handles_zero_total(self) -> None:
        # The defensive branch the integration tests skip — total=0.
        msg = performance_policy.small_sample_accuracy_notice(
            {"total": 0},
            subject="Sapphire's TA model",
        )
        assert "scored forecasts" not in msg
        assert "100-call threshold" in msg


# ---------------------------------------------------------------------------
# formatters
# ---------------------------------------------------------------------------


class TestFormattersLinkedIn:
    def test_linkedin_crypto_under_char_limit(self) -> None:
        report = _make_crypto_report()
        out = format_linkedin(report)
        assert len(out) <= LINKEDIN_LIMIT
        assert SHORT_DISCLAIMER in out

    def test_linkedin_crypto_uses_track_record_copy_above_threshold(self) -> None:
        report = _make_crypto_report(_crypto_facts(total_preds=120, hits=80))
        out = format_linkedin(report)
        # When sample size >= 100, the formatter cites accuracy.
        assert "accuracy" in out

    def test_linkedin_crypto_uses_small_sample_copy_below_threshold(self) -> None:
        report = _make_crypto_report(_crypto_facts(total_preds=20, hits=12))
        out = format_linkedin(report)
        # Small-sample notice mentions the threshold.
        assert "100" in out

    def test_linkedin_unknown_kind_falls_through_to_body_with_disclaimer(self) -> None:
        report = Report(
            kind="ai_intel",  # has its own renderer
            title="AI Intel",
            generated_at="2026-04-27",
            facts={
                "event_count": 12,
                "agent_counts": {"sapphire_dispatch": 5},
                "device_counts": {"mac": 8, "windows-gpu": 4},
                "tracked_projects": 3,
            },
            body="A short body",
            sources=["data/system_events.jsonl"],
            tags=["ai"],
        )
        out = format_linkedin(report)
        # The generic renderer always appends the disclaimer.
        assert SHORT_DISCLAIMER in out

    def test_shorten_to_truncates_with_ellipsis(self) -> None:
        long = "abc " * 200
        cut = _shorten_to(long, 50)
        # _shorten_to does NOT strictly enforce the limit (final "…" is appended
        # after the cut), but it's bounded to limit + 1 char.
        assert len(cut) <= 51
        assert cut.endswith("…")

    def test_shorten_to_returns_unchanged_when_under_limit(self) -> None:
        short = "fits in budget"
        assert _shorten_to(short, 100) == short

    def test_shorten_to_uses_sentence_boundary_when_present(self) -> None:
        # Has a "." inside the budget — should cut there.
        text = "First sentence. Then a long second sentence that runs way past the budget."
        result = _shorten_to(text, 30)
        assert result.endswith("…")
        # Should have stopped at the period.
        assert "First sentence" in result


class TestFormattersSubstack:
    def test_substack_includes_title_and_sources_footer(self) -> None:
        report = _make_crypto_report()
        out = format_substack(report)
        assert out.startswith("# Weekly Crypto Brief")
        assert "## Data Sources" in out
        assert "## Disclaimer" in out
        # Each source rendered as code-formatted bullet
        assert "`data/trading_predictions.jsonl`" in out

    def test_substack_handles_empty_sources(self) -> None:
        report = _make_crypto_report()
        report.sources = []
        out = format_substack(report)
        assert "(none)" in out


class TestFormattersXThread:
    def test_x_thread_respects_270_char_per_tweet(self) -> None:
        report = _make_crypto_report()
        tweets = format_x_thread(report)
        assert len(tweets) > 0
        for tweet in tweets:
            assert len(tweet) <= X_TWEET_LIMIT, f"tweet too long: {tweet}"

    def test_x_thread_numbering_is_consistent(self) -> None:
        report = _make_crypto_report()
        tweets = format_x_thread(report)
        # All tweets should share the same denominator
        denominators = {t.split("/")[-1].rstrip(")") for t in tweets if "/" in t}
        assert len(denominators) == 1

    def test_x_thread_market_pulse_returns_single_tweet(self) -> None:
        report = Report(
            kind="market_pulse",
            title="Market Pulse",
            generated_at="2026-04-27",
            facts={},
            body="Pulse: BTC consolidating near 95k. Liquidity thin.",
            sources=[],
            tags=[],
        )
        tweets = format_x_thread(report)
        assert len(tweets) == 1

    def test_split_tweets_packs_short_parts_together(self) -> None:
        tweets = _split_tweets(["short one.", "short two.", "short three."])
        # Should fit into one merged tweet given 270-char budget.
        assert len(tweets) == 1
        assert "short one" in tweets[0]
        assert "short three" in tweets[0]


# ---------------------------------------------------------------------------
# approval
# ---------------------------------------------------------------------------


class TestApprovalFlow:
    def test_approve_rejects_when_qa_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Redirect approvals file to tmp_path so we don't touch repo data/.
        from lib.content import approval as approval_mod

        monkeypatch.setattr(approval_mod, "_APPROVALS_FILE", tmp_path / "approvals.jsonl")
        monkeypatch.setattr(approval_mod, "_PENDING_DIR", tmp_path / "pending")

        # Force QA to fail.
        from lib.content import qa_pipeline

        def fake_qa(report: Report) -> qa_pipeline.QAResult:
            return qa_pipeline.QAResult(
                passed=False,
                failures=["data_density_low"],
                word_count=10,
                evidence_density=0.1,
                kind=report.kind,
            )

        monkeypatch.setattr(approval_mod, "run_qa", fake_qa)

        report = _make_crypto_report()
        record = approve(report)
        assert record.status == ApprovalStatus.REJECTED
        assert "QA failed" in record.reason

    def test_approve_rejects_when_sensitivity_flagged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from lib.content import approval as approval_mod
        from lib.content import qa_pipeline

        monkeypatch.setattr(approval_mod, "_APPROVALS_FILE", tmp_path / "approvals.jsonl")
        monkeypatch.setattr(approval_mod, "_PENDING_DIR", tmp_path / "pending")

        # QA passes
        monkeypatch.setattr(
            approval_mod,
            "run_qa",
            lambda r: qa_pipeline.QAResult(
                passed=True,
                failures=[],
                word_count=200,
                evidence_density=2.0,
                kind=r.kind,
            ),
        )
        # Sensitivity check returns a flag
        monkeypatch.setattr(
            approval_mod,
            "_check_sensitivity",
            lambda body: ["api_key"],
        )
        record = approve(_make_crypto_report())
        assert record.status == ApprovalStatus.REJECTED
        assert "Sensitivity flags" in record.reason

    def test_approve_autonomous_passes_when_clean(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from lib.content import approval as approval_mod
        from lib.content import qa_pipeline

        monkeypatch.setattr(approval_mod, "_APPROVALS_FILE", tmp_path / "approvals.jsonl")
        monkeypatch.setattr(approval_mod, "_PENDING_DIR", tmp_path / "pending")
        monkeypatch.setattr(
            approval_mod,
            "run_qa",
            lambda r: qa_pipeline.QAResult(
                passed=True,
                failures=[],
                word_count=200,
                evidence_density=2.0,
                kind=r.kind,
            ),
        )
        monkeypatch.setattr(approval_mod, "_check_sensitivity", lambda body: [])

        record = approve(_make_crypto_report(), require_human=False)
        assert record.status == ApprovalStatus.APPROVED
        # And the approval line was written.
        assert (tmp_path / "approvals.jsonl").exists()

    def test_approve_human_required_parks_pending_with_failsafe_telegram(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Defensive branch the integration tests skip: Telegram raises but we
        # still park the draft as PENDING.
        from lib.content import approval as approval_mod
        from lib.content import qa_pipeline

        monkeypatch.setattr(approval_mod, "_APPROVALS_FILE", tmp_path / "approvals.jsonl")
        monkeypatch.setattr(approval_mod, "_PENDING_DIR", tmp_path / "pending")
        monkeypatch.setattr(
            approval_mod,
            "run_qa",
            lambda r: qa_pipeline.QAResult(
                passed=True,
                failures=[],
                word_count=200,
                evidence_density=2.0,
                kind=r.kind,
            ),
        )
        monkeypatch.setattr(approval_mod, "_check_sensitivity", lambda body: [])

        # Force telegram_approval.request_approval to blow up — this MUST NOT
        # short-circuit the pending parking.
        with patch(
            "lib.content.telegram_approval.request_approval",
            side_effect=RuntimeError("Telegram down"),
        ):
            record = approve(_make_crypto_report(), require_human=True)

        assert record.status == ApprovalStatus.PENDING
        # The pending path should have been written even though Telegram blew up.
        pending_files = list((tmp_path / "pending").iterdir())
        assert len(pending_files) == 1


# ---------------------------------------------------------------------------
# auto_publish discovery + ledger
# ---------------------------------------------------------------------------


class TestAutoPublishDiscovery:
    def _seed(
        self, tmp: Path, platform: str, ts: str, kind: str, content: str = "body"
    ) -> Path:
        sub = tmp / platform
        sub.mkdir(parents=True, exist_ok=True)
        ext = "md" if platform != "x" else "jsonl"
        path = sub / f"{ts}_{kind}.{ext}"
        path.write_text(content)
        return path

    def test_discover_returns_newest_unpublished_per_platform(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auto_publish, "READY_ROOT", tmp_path)
        # Two LinkedIn posts of the same kind — should pick the newer one.
        self._seed(tmp_path, "linkedin", "20260427_0600", "weekly_crypto_brief")
        self._seed(tmp_path, "linkedin", "20260427_0900", "weekly_crypto_brief")
        items = auto_publish.discover(
            window=timedelta(days=2),
            now=datetime(2026, 4, 27, 12, 0),
            ledger={},
        )
        # 1 platform × 1 kind = 1 result
        assert len(items) == 1
        assert items[0].path.name.startswith("20260427_0900")

    def test_discover_skips_files_already_in_ledger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auto_publish, "READY_ROOT", tmp_path)
        self._seed(tmp_path, "substack", "20260427_0600", "weekly_crypto_brief")
        ledger = {
            "substack:weekly_crypto_brief": {
                "published_at": "2026-04-27T07:00:00",
                "url": "https://example.test/post/1",
            }
        }
        items = auto_publish.discover(
            window=timedelta(days=2),
            now=datetime(2026, 4, 27, 12, 0),
            ledger=ledger,
        )
        assert items == []

    def test_discover_drops_files_outside_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auto_publish, "READY_ROOT", tmp_path)
        # File from 5 days ago — outside the default 48h window.
        self._seed(tmp_path, "linkedin", "20260422_0600", "ai_intel")
        items = auto_publish.discover(
            window=timedelta(hours=48),
            now=datetime(2026, 4, 27, 12, 0),
            ledger={},
        )
        assert items == []

    def test_ledger_round_trips_through_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auto_publish, "LEDGER_PATH", tmp_path / "ledger.json")
        # Empty ledger when file is missing.
        assert auto_publish._load_ledger() == {}
        # Writing then reading round-trips.
        auto_publish._write_ledger({"x:weekly_crypto_brief": {"url": "https://x.test/123"}})
        again = auto_publish._load_ledger()
        assert again["x:weekly_crypto_brief"]["url"] == "https://x.test/123"

    def test_load_ledger_recovers_from_corruption(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "ledger.json"
        path.write_text("{not-json")
        monkeypatch.setattr(auto_publish, "LEDGER_PATH", path)
        # Defensive branch the integration tests skip — corrupt JSON resets.
        assert auto_publish._load_ledger() == {}


__all__ = [
    "TestApprovalFlow",
    "TestAutoPublishDiscovery",
    "TestFormattersLinkedIn",
    "TestFormattersSubstack",
    "TestFormattersXThread",
    "TestPerformancePolicy",
]
