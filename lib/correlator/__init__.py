"""Sapphire Signal Correlation Engine.

Cross-source signal correlation that fuses every Sapphire signal feed
(TradingView webhooks, Telegram intel, Hyperliquid public feed,
threat-intel sweep, convergence-watchlist, sovereign-thesis,
Kronos forecast, TA scanner) into a single ``edge_score`` per
``(symbol, timeframe)`` with ``corroborated_by`` and ``divergent_sources``
arrays naming each contributing feed.

Public API
----------

The engine has four public entry points that should be all most callers
need to know about:

- :func:`engine.correlate_once` — pure: build a ``CorrelatedSignal`` from
  a dict of ``{source_name: SourceSignal}``.
- :func:`engine.correlate_universe` — orchestrate adapters + scoring across
  a configured universe of ``(symbol, timeframe)`` pairs.
- :func:`scoring.compose_score` — pure scoring math; ``edge_score`` blend,
  freshness decay, agreement bonus, contradict penalty.
- :class:`sources.SignalSource` — the adapter Protocol every source
  implementation satisfies.

Modules
-------

- ``engine``   — pure correlation logic + dataclasses + caps enforcement.
- ``scoring``  — weights, freshness decay, agreement / contradict math.
- ``sources``  — disk-snapshot adapters for every Sapphire source feed.

This package never opens a network socket and never writes to source
streams. It is a *read-only* consumer that emits a unified signal.
"""

from __future__ import annotations

from lib.correlator.engine import (
    CONSENSUS_LABELS,
    EDGE_SCORE_BOUND,
    FRESHNESS_HARD_LIMIT_SECONDS,
    MAX_CORRELATIONS_PER_HOUR,
    MAX_SOURCES_PER_CORRELATION,
    CorrelatedSignal,
    CorrelatorConfig,
    correlate_once,
    correlate_universe,
)
from lib.correlator.scoring import (
    DEFAULT_SOURCE_WEIGHTS,
    SCORING_VERSION,
    ScoringWeights,
    compose_score,
    freshness_factor,
    load_weights,
)
from lib.correlator.sources import (
    SignalSource,
    SourceSignal,
    available_sources,
    build_default_sources,
)

__all__ = [
    "CONSENSUS_LABELS",
    "DEFAULT_SOURCE_WEIGHTS",
    "EDGE_SCORE_BOUND",
    "FRESHNESS_HARD_LIMIT_SECONDS",
    "MAX_CORRELATIONS_PER_HOUR",
    "MAX_SOURCES_PER_CORRELATION",
    "SCORING_VERSION",
    "CorrelatedSignal",
    "CorrelatorConfig",
    "ScoringWeights",
    "SignalSource",
    "SourceSignal",
    "available_sources",
    "build_default_sources",
    "compose_score",
    "correlate_once",
    "correlate_universe",
    "freshness_factor",
    "load_weights",
]
