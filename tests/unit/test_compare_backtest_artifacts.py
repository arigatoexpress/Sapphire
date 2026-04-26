"""Tests for scripts/ops/compare_backtest_artifacts.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "compare_backtest_artifacts.py"
SPEC = importlib.util.spec_from_file_location("compare_backtest_artifacts", SCRIPT)
assert SPEC and SPEC.loader
comparator = importlib.util.module_from_spec(SPEC)
sys.modules["compare_backtest_artifacts"] = comparator
SPEC.loader.exec_module(comparator)


def test_identical_artifacts_pass_and_write_reports(tmp_path: Path) -> None:
    local_sweep = _write(
        tmp_path / "local_sweep.json", _artifact(computed_at="2026-05-03T04:00:00+00:00")
    )
    remote_sweep = _write(
        tmp_path / "remote_sweep.json", _artifact(computed_at="2026-05-03T04:00:10+00:00")
    )
    local_best = _write(
        tmp_path / "local_best.json", _artifact(computed_at="2026-05-03T04:00:00+00:00", best=True)
    )
    remote_best = _write(
        tmp_path / "remote_best.json", _artifact(computed_at="2026-05-03T04:00:10+00:00", best=True)
    )
    report_dir = tmp_path / "reports"

    exit_code = comparator.main(
        [
            "--local-sweep",
            str(local_sweep),
            "--remote-sweep",
            str(remote_sweep),
            "--local-best",
            str(local_best),
            "--remote-best",
            str(remote_best),
            "--report-out",
            str(report_dir),
            "--quiet",
        ]
    )

    assert exit_code == 0
    reports = sorted(report_dir.glob("shadow-comparison-*"))
    assert {path.suffix for path in reports} == {".json", ".md"}
    payload = json.loads(next(path for path in reports if path.suffix == ".json").read_text())
    assert payload["verdict"] == "PASS"
    assert payload["summary"]["rows_compared"] == 4
    assert payload["summary"]["leaderboard_top3_order_equal"] is True


def test_small_non_leaderboard_drift_warns_and_strict_fails(tmp_path: Path) -> None:
    local_sweep_data = _artifact(computed_at="2026-05-03T04:00:00+00:00", extra_rows=21)
    remote_sweep_data = _artifact(computed_at="2026-05-03T04:00:10+00:00", extra_rows=21)
    remote_sweep_data["results"][-1]["total_return_pct"] += 0.006
    local_sweep = _write(tmp_path / "local_sweep.json", local_sweep_data)
    remote_sweep = _write(tmp_path / "remote_sweep.json", remote_sweep_data)
    local_best = _write(
        tmp_path / "local_best.json", _artifact(computed_at="2026-05-03T04:00:00+00:00", best=True)
    )
    remote_best = _write(
        tmp_path / "remote_best.json", _artifact(computed_at="2026-05-03T04:00:10+00:00", best=True)
    )

    base_args = [
        "--local-sweep",
        str(local_sweep),
        "--remote-sweep",
        str(remote_sweep),
        "--local-best",
        str(local_best),
        "--remote-best",
        str(remote_best),
        "--report-out",
        str(tmp_path / "reports"),
        "--quiet",
    ]

    assert comparator.main(base_args) == 10
    assert comparator.main([*base_args, "--strict"]) == 20


def test_leaderboard_top3_set_drift_fails(tmp_path: Path) -> None:
    local_sweep_data = _artifact(computed_at="2026-05-03T04:00:00+00:00")
    remote_sweep_data = _artifact(computed_at="2026-05-03T04:00:10+00:00")
    remote_sweep_data["results"][3]["sortino"] = 20.0
    local_sweep = _write(tmp_path / "local_sweep.json", local_sweep_data)
    remote_sweep = _write(tmp_path / "remote_sweep.json", remote_sweep_data)

    exit_code = comparator.main(
        [
            "--local-sweep",
            str(local_sweep),
            "--remote-sweep",
            str(remote_sweep),
            "--report-out",
            str(tmp_path / "reports"),
            "--quiet",
        ]
    )

    assert exit_code == 20


def test_join_key_allows_same_strategy_name_with_different_params(tmp_path: Path) -> None:
    local_data = _artifact(computed_at="2026-05-03T04:00:00+00:00")
    remote_data = _artifact(computed_at="2026-05-03T04:00:10+00:00")
    for payload in (local_data, remote_data):
        duplicate = dict(payload["results"][0])
        duplicate["params"] = {"rsi_period": 14, "sl_pct": 0.02, "tp_pct": 0.05}
        payload["results"].append(duplicate)
        payload["total_backtests"] = len(payload["results"])

    local_sweep = _write(tmp_path / "local_sweep.json", local_data)
    remote_sweep = _write(tmp_path / "remote_sweep.json", remote_data)

    assert (
        comparator.main(
            [
                "--local-sweep",
                str(local_sweep),
                "--remote-sweep",
                str(remote_sweep),
                "--report-out",
                str(tmp_path / "reports"),
                "--quiet",
            ]
        )
        == 0
    )


def test_metadata_summary_surfaces_bar_fingerprint_drift(tmp_path: Path) -> None:
    local_data = _artifact(computed_at="2026-05-03T04:00:00+00:00")
    remote_data = _artifact(computed_at="2026-05-03T04:00:10+00:00")
    local_data["metadata"] = _metadata(btc_sha="btc-local", eth_sha="eth-same")
    remote_data["metadata"] = _metadata(btc_sha="btc-remote", eth_sha="eth-same")
    local_sweep = _write(tmp_path / "local_sweep.json", local_data)
    remote_sweep = _write(tmp_path / "remote_sweep.json", remote_data)
    report_dir = tmp_path / "reports"

    assert (
        comparator.main(
            [
                "--local-sweep",
                str(local_sweep),
                "--remote-sweep",
                str(remote_sweep),
                "--report-out",
                str(report_dir),
                "--quiet",
            ]
        )
        == 0
    )

    payload = json.loads(next(path for path in report_dir.glob("*.json")).read_text())
    metadata = payload["summary"]["metadata"]
    assert metadata["source"]["git_sha_equal"] is True
    assert metadata["source"]["yfinance_version_equal"] is True
    assert metadata["bar_fingerprints"]["status"] == "different"
    assert metadata["bar_fingerprints"]["matched"] == 1
    assert metadata["bar_fingerprints"]["differing"] == 1
    markdown = next(path for path in report_dir.glob("*.md")).read_text()
    assert "Bar-set fingerprint: different" in markdown


def test_identical_sweep_inputs_are_usage_error(tmp_path: Path) -> None:
    data = _artifact(computed_at="2026-05-03T04:00:00+00:00")
    local_sweep = _write(tmp_path / "local_sweep.json", data)
    remote_sweep = _write(tmp_path / "remote_sweep.json", data)

    assert (
        comparator.main(
            ["--local-sweep", str(local_sweep), "--remote-sweep", str(remote_sweep), "--quiet"]
        )
        == 64
    )


def test_malformed_json_is_config_error(tmp_path: Path) -> None:
    local_sweep = tmp_path / "local.json"
    remote_sweep = _write(
        tmp_path / "remote.json", _artifact(computed_at="2026-05-03T04:00:00+00:00")
    )
    local_sweep.write_text("{bad json")

    assert (
        comparator.main(
            ["--local-sweep", str(local_sweep), "--remote-sweep", str(remote_sweep), "--quiet"]
        )
        == 78
    )


def test_missing_input_is_io_error(tmp_path: Path) -> None:
    remote_sweep = _write(
        tmp_path / "remote.json", _artifact(computed_at="2026-05-03T04:00:00+00:00")
    )

    assert (
        comparator.main(
            [
                "--local-sweep",
                str(tmp_path / "missing.json"),
                "--remote-sweep",
                str(remote_sweep),
                "--quiet",
            ]
        )
        == 74
    )


def test_bad_invocation_uses_sysexits_usage_code() -> None:
    assert comparator.main(["--local-sweep", "only-one-side.json", "--quiet"]) == 64


def test_nearest_backtest_artifact_selection_writes_metadata(tmp_path: Path) -> None:
    local_root = tmp_path / "local-backtests"
    remote_root = tmp_path / "remote-artifact"
    _write_backtest_pair(local_root, "20260426T010000Z", "2026-04-26T01:00:00+00:00")
    _write_backtest_pair(local_root, "20260426T040003Z", "2026-04-26T04:00:03+00:00")
    _write_backtest_pair(
        remote_root / "data" / "backtests" / "strategies",
        "20260426T043620Z",
        "2026-04-26T04:36:20+00:00",
    )
    report_dir = tmp_path / "reports"

    exit_code = comparator.main(
        [
            "--local-root",
            str(local_root),
            "--remote-root",
            str(remote_root),
            "--report-out",
            str(report_dir),
            "--quiet",
        ]
    )

    assert exit_code == 0
    payload = json.loads(next(report_dir.glob("*.json")).read_text())
    assert payload["selection"]["mode"] == "nearest_backtest_artifact"
    assert payload["selection"]["local"]["run_timestamp"] == "2026-04-26T04:00:03Z"
    assert payload["selection"]["remote"]["run_timestamp"] == "2026-04-26T04:36:20Z"
    assert payload["selection"]["time_skew_seconds"] == 2177.0
    assert payload["inputs"]["local_best"]["path"].endswith("best_per_symbol_20260426T040003Z.json")
    assert payload["summary"]["leaderboard_top3_order_equal"] is True


def test_nearest_backtest_artifact_selection_rejects_stale_pairing(tmp_path: Path) -> None:
    local_root = tmp_path / "local-backtests"
    remote_root = tmp_path / "remote-artifact"
    _write_backtest_pair(local_root, "20260426T010000Z", "2026-04-26T01:00:00+00:00")
    _write_backtest_pair(remote_root, "20260426T030000Z", "2026-04-26T03:00:00+00:00")

    exit_code = comparator.main(
        [
            "--local-root",
            str(local_root),
            "--remote-root",
            str(remote_root),
            "--max-skew-minutes",
            "30",
            "--quiet",
        ]
    )

    assert exit_code == 64


def _artifact(*, computed_at: str, best: bool = False, extra_rows: int = 0) -> dict:
    rows = [
        _row("RegimeAwareRSI", "BTC-USD", 10.0, 2),
        _row("RegimeAwareRSI", "ETH-USD", 8.0, 2),
        _row("SapphireComposite", "BTC-USD", 6.0, 3),
        _row("CorrelationBreakout", "SPY", 1.0, 4),
    ]
    rows.extend(_row("ExtraStrategy", f"SYM-{idx:02d}", 0.5, 4) for idx in range(extra_rows))
    if best:
        rows = [dict(row, report=_report(row["symbol"], row["total_trades"])) for row in rows[:3]]
    return {"computed_at": computed_at, "total_backtests": len(rows), "results": rows}


def _metadata(*, btc_sha: str, eth_sha: str) -> dict:
    return {
        "source": {
            "generator": "lib.analytics.run_strategies",
            "git_sha": "abc123",
            "github_run_id": "456",
            "yfinance_version": "0.2.66",
        },
        "config": {"days": 90, "bankroll": 10000.0, "symbols": ["BTC-USD", "ETH-USD"]},
        "bar_fingerprints": {
            "BTC-USD": {"sha256": btc_sha, "bars": 90, "start": "2026-02-01", "end": "2026-05-01"},
            "ETH-USD": {"sha256": eth_sha, "bars": 90, "start": "2026-02-01", "end": "2026-05-01"},
        },
    }


def _row(strategy_cls: str, symbol: str, sortino: float, trades: int) -> dict:
    return {
        "strategy_cls": strategy_cls,
        "strategy_name": f"{strategy_cls}(p=7,sl=2%,tp=5%)",
        "symbol": symbol,
        "params": {"rsi_period": 7, "sl_pct": 0.02, "tp_pct": 0.05},
        "sortino": sortino,
        "sharpe": sortino / 2,
        "total_return_pct": 0.01,
        "win_rate": 0.75,
        "profit_factor": 2.5,
        "max_drawdown_pct": 0.002,
        "calmar": sortino / 3,
        "total_trades": trades,
    }


def _report(symbol: str, trades: int) -> dict:
    return {
        "symbol": symbol,
        "start": "2026-02-01",
        "end": "2026-05-01",
        "bars": 90,
        "trades": [{"direction": "long", "exit_reason": "take_profit"} for _ in range(trades)],
        "initial_capital": 10000.0,
        "final_capital": 10100.0,
        "total_return_pct": 1.0,
        "cagr_pct": 4.0,
        "sharpe": 2.0,
        "sortino": 4.0,
        "max_drawdown_pct": 0.2,
        "win_rate": 0.75,
        "profit_factor": 2.5,
        "expectancy": 10.0,
        "avg_trade_pnl": 10.0,
        "avg_win": 20.0,
        "avg_loss": -5.0,
        "equity_curve": [["2026-02-01", 10000.0], ["2026-05-01", 10100.0]],
    }


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _write_backtest_pair(root: Path, stamp: str, computed_at: str) -> tuple[Path, Path]:
    sweep = _write(root / f"strategy_sweep_{stamp}.json", _artifact(computed_at=computed_at))
    best = _write(
        root / f"best_per_symbol_{stamp}.json",
        _artifact(computed_at=computed_at, best=True),
    )
    return sweep, best
