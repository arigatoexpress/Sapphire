"""Walk-forward backtest orchestrator + regime decomposition.

Lane 5 of Tranche 6 — pure, additive layer over `lib.analytics.strategies`,
`lib.analytics.backtest_engine`, `lib.analytics.deflated_sharpe`, and the
cross-asset regime artifacts produced by Tranche 4.

This package provides three composable, side-effect-free modules:

    engine          — orchestrate train→test windows over (strategy, grid, bars).
    regime_decomp   — split walk-forward returns by regime label, emit per-regime metrics.
    deflated_sharpe — wrap `lib.analytics.deflated_sharpe` with multi-window inputs.

Nothing in this package mutates the upstream modules; the whole layer is read-only
over them. See `docs/products/walkforward-and-regime-0.1.0.md` for the design.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__: list[str] = ["__version__"]

try:
    from .engine import (  # noqa: F401
        ParameterGrid,
        WalkforwardConfig,
        WalkforwardResult,
        WalkforwardWindow,
        WindowMetrics,
        run_walkforward,
        walkforward_windows,
    )

    __all__ += [
        "ParameterGrid",
        "WalkforwardConfig",
        "WalkforwardResult",
        "WalkforwardWindow",
        "WindowMetrics",
        "run_walkforward",
        "walkforward_windows",
    ]
except ImportError:  # pragma: no cover — defensive; engine imports stdlib + analytics
    pass

try:
    from .regime_decomp import (  # noqa: F401
        RegimeDecompResult,
        RegimeReturnsBucket,
        attach_regime_labels,
        decompose_by_regime,
        load_regime_labels,
    )

    __all__ += [
        "RegimeDecompResult",
        "RegimeReturnsBucket",
        "attach_regime_labels",
        "decompose_by_regime",
        "load_regime_labels",
    ]
except ImportError:  # pragma: no cover
    pass

try:
    from .deflated_sharpe import (  # noqa: F401
        WalkforwardDSRResult,
        deflated_sharpe_for_walkforward,
    )

    __all__ += [
        "WalkforwardDSRResult",
        "deflated_sharpe_for_walkforward",
    ]
except ImportError:  # pragma: no cover
    pass
