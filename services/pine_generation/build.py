"""Pine generation build pipeline.

Pulls the top-N best backtest configs and writes one Pine v5 file per
(strategy, symbol) under `pine/generated/<date>/`.

Public surface:
    - :func:`load_best_per_symbol` — read the latest best_per_symbol_*.json.
    - :func:`build_artifacts` — generate every (strategy, symbol) Pine file
      and return a manifest. Pure on inputs (rows + output dir).
    - :func:`build_from_disk` — top-level CLI helper that combines the two.
    - :func:`make_filename` — canonical Pine filename helper.

The pipeline NEVER pushes to TradingView — that's an operator-gated step in
the plugin tool. It only writes Pine source files locally.

CLI usage:
    python3 -m services.pine_generation.build [--limit 10] [--strategies SapphireComposite,RegimeAwareRSI]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.pine_generation import (  # noqa: E402
    SUPPORTED_STRATEGIES,
    PineSpec,
    generate_pine,
    spec_from_backtest_row,
    validate_pine,
)

DEFAULT_BACKTEST_DIR = REPO_ROOT / "data" / "backtests" / "strategies"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "pine" / "generated"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratedArtifact:
    """One Pine file successfully written to disk."""

    strategy: str
    symbol: str
    path: Path
    spec: PineSpec
    bytes: int
    sortino: float | None = None
    win_rate: float | None = None
    total_trades: int | None = None
    validator_warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "path": str(self.path),
            "bytes": self.bytes,
            "sortino": self.sortino,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "validator_warnings": list(self.validator_warnings),
        }


@dataclass
class BuildManifest:
    """Result of one build pass."""

    output_dir: Path
    generated_at: str
    artifacts: list[GeneratedArtifact] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "generated_at": self.generated_at,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "skipped": list(self.skipped),
            "errors": list(self.errors),
            "summary": {
                "generated": len(self.artifacts),
                "skipped": len(self.skipped),
                "errors": len(self.errors),
            },
        }


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------


_STRATEGY_SLUG_MAP: dict[str, str] = {
    "RegimeAwareRSI": "regime-aware-rsi",
    "FundingRateContrarian": "funding-rate-contrarian",
    "CorrelationBreakout": "correlation-breakout",
    "MultiTFMomentum": "multi-tf-momentum",
    "SapphireComposite": "sapphire-composite",
    "BaseStrategy": "base-strategy",
    "StrategyParams": "params-only",
}


def make_filename(strategy: str, symbol: str) -> str:
    """Produce the canonical Pine filename for one (strategy, symbol) pair.

    Slug rules: strategy uses the ``_STRATEGY_SLUG_MAP`` (kebab-case);
    symbol is uppercased and stripped of '-' and '/' separators.
    """
    slug = _STRATEGY_SLUG_MAP.get(strategy)
    if slug is None:
        # Fallback: lowercase, underscore→hyphen.
        slug = strategy.lower().replace("_", "-")
    sym = symbol.upper().replace("-", "").replace("/", "").replace(":", "")
    return f"{slug}-{sym}.pine"


def make_output_dir(root: Path | None = None, run_date: date | None = None) -> Path:
    """Compute `<root>/pine/generated/<YYYY-MM-DD>/`."""
    base = root if root is not None else DEFAULT_OUTPUT_ROOT
    d = run_date if run_date is not None else datetime.now(UTC).date()
    return base / d.isoformat()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_best_per_symbol(directory: Path | None = None) -> list[dict[str, Any]]:
    """Load the most recent `best_per_symbol_*.json` file as a list of rows.

    Returns an empty list if the directory or file is missing.
    """
    target = directory if directory is not None else DEFAULT_BACKTEST_DIR
    if not target.exists() or not target.is_dir():
        return []
    candidates = sorted(target.glob("best_per_symbol_*.json"))
    if not candidates:
        return []
    latest = candidates[-1]
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows = payload.get("results")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def filter_rows(
    rows: Iterable[dict[str, Any]],
    *,
    strategies: list[str] | None = None,
    symbols: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Apply strategy / symbol / limit filters to backtest rows.

    Rows are sorted by Sortino descending before applying limit.
    """
    out: list[dict[str, Any]] = []
    strat_set = {s for s in (strategies or [])} or None
    sym_set = {s.upper() for s in (symbols or [])} or None
    for row in rows:
        cls = row.get("strategy_cls")
        if cls not in SUPPORTED_STRATEGIES:
            continue
        if strat_set and cls not in strat_set:
            continue
        sym = row.get("symbol")
        if sym_set and (not sym or sym.upper() not in sym_set):
            continue
        out.append(row)
    out.sort(
        key=lambda r: r.get("sortino") if r.get("sortino") is not None else -1e9,
        reverse=True,
    )
    if limit is not None and limit > 0:
        out = out[:limit]
    return out


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------


def build_artifacts(
    rows: Iterable[dict[str, Any]],
    *,
    output_dir: Path,
    overwrite: bool = True,
) -> BuildManifest:
    """Generate Pine files for every row.

    Args:
        rows: Backtest rows in the shape produced by
            :func:`lib.analytics.strategies.SweepResult.to_dict`.
        output_dir: Target directory; created if missing.
        overwrite: If False, existing Pine files are kept and the row is
            skipped with reason "exists".

    Returns:
        :class:`BuildManifest` with one artifact per generated file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = BuildManifest(
        output_dir=output_dir,
        generated_at=datetime.now(UTC).isoformat(),
    )

    for row in rows:
        try:
            spec = spec_from_backtest_row(row)
        except (TypeError, ValueError) as exc:
            manifest.errors.append({"row": row, "stage": "spec", "error": str(exc)})
            continue

        target = output_dir / make_filename(spec.strategy, spec.symbol)
        if not overwrite and target.exists():
            manifest.skipped.append(
                {
                    "strategy": spec.strategy,
                    "symbol": spec.symbol,
                    "reason": "exists",
                    "path": str(target),
                }
            )
            continue

        try:
            pine_src = generate_pine(spec)
        except (TypeError, ValueError) as exc:
            manifest.errors.append(
                {
                    "strategy": spec.strategy,
                    "symbol": spec.symbol,
                    "stage": "generate",
                    "error": str(exc),
                }
            )
            continue

        result = validate_pine(pine_src)
        if not result.ok:
            manifest.errors.append(
                {
                    "strategy": spec.strategy,
                    "symbol": spec.symbol,
                    "stage": "validate",
                    "errors": result.errors,
                }
            )
            continue

        target.write_text(pine_src)
        manifest.artifacts.append(
            GeneratedArtifact(
                strategy=spec.strategy,
                symbol=spec.symbol,
                path=target,
                spec=spec,
                bytes=len(pine_src.encode("utf-8")),
                sortino=row.get("sortino"),
                win_rate=row.get("win_rate"),
                total_trades=row.get("total_trades"),
                validator_warnings=tuple(result.warnings),
            )
        )

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_from_disk(
    *,
    backtest_dir: Path | None = None,
    output_root: Path | None = None,
    run_date: date | None = None,
    strategies: list[str] | None = None,
    symbols: list[str] | None = None,
    limit: int | None = None,
    overwrite: bool = True,
) -> BuildManifest:
    """End-to-end: read backtest rows from disk, generate Pine, return manifest."""
    rows = load_best_per_symbol(backtest_dir)
    filtered = filter_rows(rows, strategies=strategies, symbols=symbols, limit=limit)
    output_dir = make_output_dir(output_root, run_date)
    return build_artifacts(filtered, output_dir=output_dir, overwrite=overwrite)


def _split_csv(s: str | None) -> list[str] | None:
    if not s:
        return None
    return [item.strip() for item in s.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--backtest-dir",
        type=Path,
        default=None,
        help=f"Directory containing best_per_symbol_*.json (default: {DEFAULT_BACKTEST_DIR})",
    )
    ap.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help=f"Output root for pine/generated/<date>/ (default: {DEFAULT_OUTPUT_ROOT})",
    )
    ap.add_argument(
        "--strategies",
        type=str,
        default=None,
        help="Comma-separated strategy class names to include",
    )
    ap.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols to include",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Top-N rows by Sortino",
    )
    ap.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Skip files that already exist",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emit the build manifest as JSON to stdout",
    )
    args = ap.parse_args(argv)

    manifest = build_from_disk(
        backtest_dir=args.backtest_dir,
        output_root=args.output_root,
        strategies=_split_csv(args.strategies),
        symbols=_split_csv(args.symbols),
        limit=args.limit,
        overwrite=not args.no_overwrite,
    )

    if args.json:
        print(json.dumps(manifest.to_dict(), indent=2, default=str))
    else:
        summary = manifest.to_dict()["summary"]
        print(
            f"pine_generation: generated={summary['generated']} "
            f"skipped={summary['skipped']} errors={summary['errors']} "
            f"out={manifest.output_dir}"
        )
        for art in manifest.artifacts:
            print(f"  {art.strategy:24s} {art.symbol:12s} → {art.path.name}")

    return 0 if not manifest.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
