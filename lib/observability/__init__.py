"""Observability aggregator — single-pane-of-glass system snapshot.

This package collates the live state of Sapphire's running surfaces into a
single, paste-safe ``SystemSnapshot`` that the ``/observability`` dashboard
page (and three sibling JSON endpoints) can render.

The aggregator is **read-only** and pure with respect to network state:

* It shells out to ``launchctl list`` to read LaunchAgent status (subprocess,
  short timeout, fail-soft).
* It reads filesystem snapshots under ``data/``, ``~/.cache/sapphire/`` and
  ``~/.sapphire/routine_pause/``.
* It never writes anywhere on disk and never makes outbound network calls.

All aggregator outputs are passed through :mod:`lib.security.pii_redactor`
sanitizers when they expose user-derived strings. Numbers and timestamps are
emitted unchanged; paths are abbreviated to ``data/...`` or ``~/.cache/...``
so absolute home-directory prefixes never leak into the JSON envelope.
"""

from __future__ import annotations

from .aggregator import (
    DEFAULT_BUS_PATH,
    DEFAULT_INFERENCE_PROXY_CACHE,
    DEFAULT_PAUSE_DIR,
    DEFAULT_REPO_ROOT,
    DEFAULT_SIGNAL_SOURCES,
    EventBusSnapshot,
    InferenceProxySnapshot,
    LaunchAgentRow,
    ProvenanceSnapshot,
    RoutinePauseRow,
    SignalStreamSnapshot,
    SystemSnapshot,
    build_launchagents_only,
    build_stream_rates_only,
    build_system_snapshot,
)

__all__ = [
    "DEFAULT_BUS_PATH",
    "DEFAULT_INFERENCE_PROXY_CACHE",
    "DEFAULT_PAUSE_DIR",
    "DEFAULT_REPO_ROOT",
    "DEFAULT_SIGNAL_SOURCES",
    "EventBusSnapshot",
    "InferenceProxySnapshot",
    "LaunchAgentRow",
    "ProvenanceSnapshot",
    "RoutinePauseRow",
    "SignalStreamSnapshot",
    "SystemSnapshot",
    "build_launchagents_only",
    "build_stream_rates_only",
    "build_system_snapshot",
]
