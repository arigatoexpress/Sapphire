"""Unit tests for ``lib/analytics/backtest_harness.py``.

Covers the §4.5 contract from ``docs/research/bearish-direction-asymmetry-2026-04-26.md``:
synthetic-data smoke test, acceptance gate boundaries, CPCV embargo, graceful
data-gap, DSR delegation, CLI exit codes, factory call count, and dataclass
serialization.

These tests use deterministic synthetic OHLCV (``_synthetic_bars`` from
``lib/analytics/backtest_engine.py``) seeded by symbol so the harness output is
reproducible across runs without yfinance.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics.backtest_engine import _synthetic_bars  # noqa: E402
from lib.analytics.backtest_harness import (  # noqa: E402
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_WARN,
    MAX_DRAWDOWN_PCT,
    MIN_DSR,
    MIN_SORTINO,
    MIN_TRADES,
    HarnessConfig,
    HarnessResult,
    _evaluate_acceptance,
    _load_symbol_bars,
    _resolve_strategy_factory,
    cli,
    run_harness,
)
from lib.analytics.cpcv import cpcv_splits  # noqa: E402

# ── Test helpers ─────────────────────────────────────────────────────────────


def _write_synthetic_csv(
    data_root: Path,
    symbol: str,
    days: int = 200,
    timeframe: str = "1d",
    start: datetime | None = None,
) -> Path:
    """Materialize ``_synthetic_bars`` to a CSV the harness can read.

    Bar timestamps are anchored at ``start`` (defaults to 2025-04-01 UTC) and step
    daily so the bars fall inside the §4.5 reference window when the harness asks
    for [2025-04-01, 2026-04-25].
    """
    sym_dir = data_root / symbol / timeframe
    sym_dir.mkdir(parents=True, exist_ok=True)
    bars = _synthetic_bars(symbol, days)
    anchor = start or datetime(2025, 4, 1, tzinfo=UTC)
    path = sym_dir / f"{symbol}_synth.csv"
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ts", "open", "high", "low", "close", "volume"])
        for i, bar in enumerate(bars):
            ts = anchor + timedelta(days=i)
            writer.writerow(
                [
                    ts.isoformat(),
                    f"{bar.open:.4f}",
                    f"{bar.high:.4f}",
                    f"{bar.low:.4f}",
                    f"{bar.close:.4f}",
                    f"{bar.volume:.4f}",
                ]
            )
    return path


class _CountingStrategy:
    """Strategy stub that emits a deterministic long signal early in the window
    and a flat at the end. Used to verify trade execution + factory call count.
    """

    def __init__(self) -> None:
        self.params = type(
            "P",
            (),
            {
                "rsi_period": 14,
                "sl_pct": 0.05,
                "tp_pct": 0.10,
            },
        )()

    @property
    def name(self) -> str:
        return "CountingStrategy"

    def on_bar(self, window: list[Any], aux: dict[str, Any]) -> Any:
        from lib.analytics.backtest import Decision

        if len(window) < 5:
            return None
        # Always-long bias produces enough trades for the engine to score
        if len(window) % 7 == 0:
            return Decision(direction="long", size=0.5, stop_pct=0.05, tp_pct=0.10)
        return None


class _FactoryCounter:
    """Wraps a strategy class so we can count factory invocations."""

    def __init__(self, cls: type) -> None:
        self.cls = cls
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        return self.cls()


# ── 1. Smoke test: synthetic series produces sensible numbers ────────────────


def test_synthetic_series_runs_and_returns_finite_metrics(tmp_path: Path) -> None:
    """With deterministic synthetic OHLCV, the harness must complete without
    raising and produce finite Sortino / drawdown values. We do not assert
    specific numerical thresholds here — that's what the boundary tests do."""
    _write_synthetic_csv(tmp_path, "BTC-USD", days=180)
    config = HarnessConfig(
        start_date="2025-04-01",
        end_date="2026-04-25",
        symbols=("BTC-USD",),
        cpcv_n_groups=4,
        cpcv_test_size=1,
    )
    result = run_harness(_FactoryCounter(_CountingStrategy), config, data_root=tmp_path)

    assert isinstance(result, HarnessResult)
    assert result.cpcv_folds > 0
    # Sortino can be 0 if no downside trades — must be a finite float regardless
    import math

    assert math.isfinite(result.mean_sortino)
    assert math.isfinite(result.deflated_sharpe)
    assert math.isfinite(result.max_drawdown_pct)
    # Drawdown can never go negative
    assert result.max_drawdown_pct >= 0.0


# ── 2. Acceptance gate boundary flips ────────────────────────────────────────


def test_acceptance_passes_when_all_gates_satisfied() -> None:
    acceptance = _evaluate_acceptance(
        total_trades=MIN_TRADES,
        mean_sortino=MIN_SORTINO,
        deflated_sharpe=MIN_DSR,
        max_drawdown_pct=MAX_DRAWDOWN_PCT,
    )
    assert acceptance["passes_section_4_5"] is True
    assert acceptance["reasons"] == []


def test_acceptance_fails_when_trades_below_threshold() -> None:
    acceptance = _evaluate_acceptance(
        total_trades=MIN_TRADES - 1,
        mean_sortino=MIN_SORTINO + 1.0,
        deflated_sharpe=MIN_DSR + 1.0,
        max_drawdown_pct=10.0,
    )
    assert acceptance["passes_section_4_5"] is False
    assert any("total_trades" in r for r in acceptance["reasons"])


def test_acceptance_fails_when_sortino_below_threshold() -> None:
    acceptance = _evaluate_acceptance(
        total_trades=MIN_TRADES + 5,
        mean_sortino=MIN_SORTINO - 0.01,
        deflated_sharpe=MIN_DSR + 1.0,
        max_drawdown_pct=10.0,
    )
    assert acceptance["passes_section_4_5"] is False
    assert any("mean_sortino" in r for r in acceptance["reasons"])


def test_acceptance_fails_when_drawdown_above_ceiling() -> None:
    acceptance = _evaluate_acceptance(
        total_trades=MIN_TRADES + 5,
        mean_sortino=MIN_SORTINO + 1.0,
        deflated_sharpe=MIN_DSR + 1.0,
        max_drawdown_pct=MAX_DRAWDOWN_PCT + 0.01,
    )
    assert acceptance["passes_section_4_5"] is False
    assert any("max_drawdown_pct" in r for r in acceptance["reasons"])


# ── 3. CPCV embargo respected (no train index appears in any test fold) ──────


def test_cpcv_embargo_is_respected_no_train_test_overlap() -> None:
    """The harness delegates to ``cpcv_splits`` which guarantees train ∩ test = ∅
    and embargo zones are evicted from train. We verify the contract directly so
    if cpcv.py ever drifts the harness's invariant we'd fail loudly."""
    n_samples = 240
    splits = list(
        cpcv_splits(
            n_samples=n_samples,
            n_groups=6,
            n_test_groups=2,
            purge_pct=0.01,
            embargo_pct=0.02,
        )
    )
    assert splits, "expected non-empty split list"
    embargo_window = max(1, int(n_samples * 0.02))
    for train_idx, test_idx in splits:
        train_set = set(train_idx)
        test_set = set(test_idx)
        # No overlap — the canonical CPCV invariant
        assert train_set.isdisjoint(test_set)
        # Embargo: no train index within ``embargo_window`` bars after a test block
        for t in test_idx:
            for j in range(t + 1, min(n_samples, t + 1 + embargo_window)):
                # Either j is a test index in another group, or it must be absent from train
                if j in test_set:
                    continue
                assert (
                    j not in train_set
                ), f"embargo violated: train idx {j} within {embargo_window} of test"


# ── 4. Graceful failure when no historical data is present ───────────────────


def test_no_data_returns_warn_signal(tmp_path: Path) -> None:
    """With an empty data_root the harness must NOT raise; it must return a
    HarnessResult flagged ``passes_section_4_5=False`` with the documented reason."""
    config = HarnessConfig(symbols=("MISSING-SYM",))
    result = run_harness(_FactoryCounter(_CountingStrategy), config, data_root=tmp_path)
    assert result.acceptance["passes_section_4_5"] is False
    assert "no historical data" in result.acceptance["reasons"]
    assert result.cpcv_folds == 0
    assert result.total_trades == 0


def test_data_with_too_few_bars_for_cpcv(tmp_path: Path) -> None:
    """When the available bars cannot be split into the requested number of
    groups, the harness fails-warn rather than divides-by-zero."""
    # Write a tiny CSV — far fewer rows than n_groups=6
    _write_synthetic_csv(tmp_path, "TINY", days=3)
    config = HarnessConfig(
        symbols=("TINY",),
        cpcv_n_groups=6,
        cpcv_test_size=2,
    )
    result = run_harness(_FactoryCounter(_CountingStrategy), config, data_root=tmp_path)
    assert result.acceptance["passes_section_4_5"] is False


# ── 5. DSR pipeline reuses lib.analytics.deflated_sharpe ────────────────────


def test_dsr_consumes_existing_deflated_sharpe_module(tmp_path: Path) -> None:
    """The harness must call ``deflated_sharpe_ratio`` from
    ``lib.analytics.deflated_sharpe`` rather than reimplement it. We monkeypatch
    the function and verify it's invoked."""
    _write_synthetic_csv(tmp_path, "BTC-USD", days=120)
    config = HarnessConfig(
        symbols=("BTC-USD",),
        cpcv_n_groups=4,
        cpcv_test_size=1,
    )

    import lib.analytics.backtest_harness as harness_mod

    original = harness_mod.deflated_sharpe_ratio
    call_count = {"n": 0}

    def _spy(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        return original(*args, **kwargs)

    harness_mod.deflated_sharpe_ratio = _spy
    try:
        run_harness(_FactoryCounter(_CountingStrategy), config, data_root=tmp_path)
    finally:
        harness_mod.deflated_sharpe_ratio = original

    assert call_count["n"] >= 1


# ── 6. CLI exit-code contract: 0 / 10 / 20 ──────────────────────────────────


def test_cli_exit_warn_on_missing_data(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    """Bare CLI with a data-empty root must return WARN (10), not FAIL (20)."""
    monkeypatch.setenv("SAPPHIRE_BACKTEST_DATA_ROOT", str(tmp_path))
    code = cli(
        [
            "--strategy",
            "lib.analytics.strategies:RegimeAwareRSI",
            "--start",
            "2025-04-01",
            "--end",
            "2026-04-25",
            "--symbols",
            "MISSING",
        ]
    )
    assert code == EXIT_WARN
    # JSON envelope must still be on stdout — let downstream tooling consume it
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["acceptance"]["passes_section_4_5"] is False


def test_cli_exit_warn_on_invalid_strategy_spec(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("SAPPHIRE_BACKTEST_DATA_ROOT", str(tmp_path))
    code = cli(
        [
            "--strategy",
            "this.module.does.not.exist:Whatever",
            "--symbols",
            "BTC-USD",
        ]
    )
    assert code == EXIT_WARN


def test_cli_exit_constants_match_compare_artifacts_contract() -> None:
    """The §4.5 spec ties the harness contract to ``compare_*_artifacts.py``.
    Lock the numeric exit codes against the documented mapping."""
    assert EXIT_PASS == 0
    assert EXIT_WARN == 10
    assert EXIT_FAIL == 20


# ── 7. Strategy factory called once per fold ────────────────────────────────


def test_strategy_factory_called_once_per_fold(tmp_path: Path) -> None:
    """The factory contract: the harness must allocate one fresh ``Strategy``
    per CPCV split, not reuse a single instance. Verified by spy."""
    _write_synthetic_csv(tmp_path, "BTC-USD", days=120)
    spy = _FactoryCounter(_CountingStrategy)
    config = HarnessConfig(
        symbols=("BTC-USD",),
        cpcv_n_groups=4,
        cpcv_test_size=1,
    )
    result = run_harness(spy, config, data_root=tmp_path)
    # C(4, 1) = 4 splits per symbol, 1 symbol → 4 folds, 4 factory calls
    assert result.cpcv_folds == spy.calls
    assert spy.calls > 0


# ── 8. HarnessResult round-trips through dataclasses.asdict ──────────────────


def test_harness_result_dataclass_round_trips_through_asdict() -> None:
    """The CLI and downstream tooling rely on JSON serialization. A round-trip
    through ``dataclasses.asdict`` + ``json.dumps`` must produce a clean object."""
    result = HarnessResult(
        cpcv_folds=15,
        total_trades=42,
        mean_pnl_pct=1.234,
        mean_sortino=0.876,
        deflated_sharpe=0.321,
        max_drawdown_pct=12.5,
        acceptance={
            "passes_section_4_5": True,
            "reasons": ["all gates met"],
        },
    )
    d = dataclasses.asdict(result)
    assert d["cpcv_folds"] == 15
    assert d["total_trades"] == 42
    assert d["acceptance"]["passes_section_4_5"] is True
    # Must serialize to JSON cleanly — no datetime, no Path, no custom types
    encoded = json.dumps(d)
    decoded = json.loads(encoded)
    assert decoded == d


# ── Bonus: factory resolver and CSV loader sanity ───────────────────────────


def test_resolve_strategy_factory_round_trip() -> None:
    factory = _resolve_strategy_factory("lib.analytics.strategies:RegimeAwareRSI")
    instance = factory()
    from lib.analytics.strategies import RegimeAwareRSI

    assert isinstance(instance, RegimeAwareRSI)


def test_resolve_strategy_factory_rejects_bad_spec() -> None:
    with pytest.raises(ValueError, match="module:class"):
        _resolve_strategy_factory("no_colon_here")


def test_load_symbol_bars_filters_by_window(tmp_path: Path) -> None:
    _write_synthetic_csv(tmp_path, "BTC-USD", days=400, start=datetime(2025, 1, 1, tzinfo=UTC))
    bars = _load_symbol_bars("BTC-USD", "2025-04-01", "2026-04-25", data_root=tmp_path)
    assert bars, "expected bars in window"
    for bar in bars:
        assert bar.ts >= datetime(2025, 4, 1, tzinfo=UTC)
        assert bar.ts <= datetime(2026, 4, 25, 23, 59, 59, tzinfo=UTC)
