"""Property-based tests for ``lib.observability.aggregator``.

The observability aggregator powers the public buyer-facing
``/observability`` JSON envelope. Two properties dominate: it must never
leak operator paths or PII, and it must serialize to deterministic JSON.

Properties below cover:

* **Deterministic serialization**: same inputs → same JSON output bytes.
* **Bounded size**: the snapshot serializes to under 1 MB regardless of how
  many empty signal-stream sources we configure.
* **No PII / no $HOME paths**: snapshot output never contains the absolute
  path of ``$HOME`` (we only emit the abbreviated ``~`` form).
* **Schema stability**: every snapshot has the documented top-level keys.
* **Slim-variant agreement**: ``build_stream_rates_only`` agrees with the
  full snapshot's ``signal_streams`` section field-for-field.
* **Graceful degradation**: when the launchctl runner errors, the
  heartbeat section status is ``"unknown"`` and the rest of the snapshot
  still renders.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.property  # noqa: E402, F401
from lib.observability.aggregator import (  # noqa: E402
    SystemSnapshot,
    build_launchagents_only,
    build_stream_rates_only,
    build_system_snapshot,
)

# ---------------------------------------------------------------------------
# Test doubles — keep IO bounded and deterministic
# ---------------------------------------------------------------------------


def _empty_launchctl_runner() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["launchctl", "list"],
        returncode=0,
        stdout="PID\tStatus\tLabel\n",
        stderr="",
    )


def _erroring_launchctl_runner() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["launchctl", "list"],
        returncode=1,
        stdout="",
        stderr="launchctl: not available",
    )


def _quiet_provenance_runner() -> dict:
    return {
        "checked": 0,
        "missing_or_invalid": 0,
        "last_verify_at": None,
        "invalid_sample": [],
        "status": "pass",
    }


def _now_factory(t: datetime):
    def _now() -> datetime:
        return t

    return _now


# Pin a fixed UTC moment to keep deterministic outputs.
_FIXED_NOW = datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


_signal_source_names = st.text(
    alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
    min_size=2,
    max_size=12,
)
_signal_source_dirs = st.text(
    alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
    min_size=2,
    max_size=12,
)


@st.composite
def signal_sources(draw: st.DrawFn) -> tuple[tuple[str, str], ...]:
    pairs = draw(
        st.lists(
            st.tuples(_signal_source_names, _signal_source_dirs),
            min_size=0,
            max_size=6,
            unique_by=lambda pair: pair[0],
        )
    )
    return tuple(pairs)


# ---------------------------------------------------------------------------
# 1. Deterministic serialization
# ---------------------------------------------------------------------------


def _strip_uptime(payload: dict) -> dict:
    """Remove the heartbeat ``uptime_seconds`` field — it tracks the real clock
    and changes second-to-second regardless of the injected ``now``."""
    out = json.loads(json.dumps(payload))
    if isinstance(out.get("heartbeat"), dict):
        out["heartbeat"].pop("uptime_seconds", None)
    return out


@given(signal_sources())
@hyp_settings(suppress_health_check=[HealthCheck.too_slow])
def test_snapshot_to_dict_serializes_deterministically(
    sources: tuple[tuple[str, str], ...]
) -> None:
    """Two builds with the same inputs must produce byte-identical JSON.

    Excludes ``heartbeat.uptime_seconds`` because it pulls the real clock
    via ``sysctl`` and changes second-to-second; everything else must
    match byte-for-byte across calls.
    """
    a = build_system_snapshot(
        signal_sources=sources,
        launchctl_runner=_empty_launchctl_runner,
        provenance_runner=_quiet_provenance_runner,
        now=_now_factory(_FIXED_NOW),
    )
    b = build_system_snapshot(
        signal_sources=sources,
        launchctl_runner=_empty_launchctl_runner,
        provenance_runner=_quiet_provenance_runner,
        now=_now_factory(_FIXED_NOW),
    )
    j_a = json.dumps(_strip_uptime(a.to_dict()), sort_keys=True)
    j_b = json.dumps(_strip_uptime(b.to_dict()), sort_keys=True)
    assert j_a == j_b


# ---------------------------------------------------------------------------
# 2. Bounded size — snapshot fits comfortably in the dashboard envelope
# ---------------------------------------------------------------------------


@given(signal_sources())
@hyp_settings(suppress_health_check=[HealthCheck.too_slow])
def test_snapshot_size_bounded_under_1mb(
    sources: tuple[tuple[str, str], ...]
) -> None:
    snapshot = build_system_snapshot(
        signal_sources=sources,
        launchctl_runner=_empty_launchctl_runner,
        provenance_runner=_quiet_provenance_runner,
        now=_now_factory(_FIXED_NOW),
    )
    payload = json.dumps(snapshot.to_dict()).encode("utf-8")
    assert len(payload) < 1_000_000, f"snapshot is {len(payload):,} bytes"


# ---------------------------------------------------------------------------
# 3. No $HOME path leakage — every path-shaped string is abbreviated
# ---------------------------------------------------------------------------


@given(signal_sources())
@hyp_settings(suppress_health_check=[HealthCheck.too_slow])
def test_snapshot_never_leaks_home_path(
    sources: tuple[tuple[str, str], ...]
) -> None:
    snapshot = build_system_snapshot(
        signal_sources=sources,
        launchctl_runner=_empty_launchctl_runner,
        provenance_runner=_quiet_provenance_runner,
        now=_now_factory(_FIXED_NOW),
    )
    home = str(Path.home())
    payload = json.dumps(snapshot.to_dict())
    assert home not in payload, (
        f"$HOME ({home!r}) leaked into snapshot — see _display_path"
    )


# ---------------------------------------------------------------------------
# 4. Schema stability — every snapshot has the documented keys
# ---------------------------------------------------------------------------


REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "mode",
    "status",
    "generated_at",
    "heartbeat",
    "inference_proxy",
    "signal_streams",
    "provenance",
    "routine_pause",
    "event_bus",
}


@given(signal_sources())
@hyp_settings(suppress_health_check=[HealthCheck.too_slow])
def test_snapshot_top_level_keys_present(
    sources: tuple[tuple[str, str], ...]
) -> None:
    snapshot = build_system_snapshot(
        signal_sources=sources,
        launchctl_runner=_empty_launchctl_runner,
        provenance_runner=_quiet_provenance_runner,
        now=_now_factory(_FIXED_NOW),
    )
    payload = snapshot.to_dict()
    assert REQUIRED_TOP_LEVEL_KEYS.issubset(payload.keys())
    assert payload["mode"] == "read_only_observability_snapshot"
    assert payload["status"] in {"pass", "warn", "unknown"}
    assert isinstance(payload["signal_streams"], list)
    assert payload["schema_version"] == 1


# ---------------------------------------------------------------------------
# 5. Slim-variant agreement — stream-rates payload matches snapshot streams
# ---------------------------------------------------------------------------


@given(signal_sources())
@hyp_settings(suppress_health_check=[HealthCheck.too_slow])
def test_stream_rates_slim_matches_full_snapshot(
    sources: tuple[tuple[str, str], ...]
) -> None:
    if not sources:
        return
    snapshot = build_system_snapshot(
        signal_sources=sources,
        launchctl_runner=_empty_launchctl_runner,
        provenance_runner=_quiet_provenance_runner,
        now=_now_factory(_FIXED_NOW),
    )
    slim = build_stream_rates_only(
        signal_sources=sources,
        now=_now_factory(_FIXED_NOW),
    )
    snapshot_streams = [s for s in snapshot.signal_streams]
    slim_streams = slim["sources"]
    assert len(snapshot_streams) == len(slim_streams)
    for snap, slim_row in zip(snapshot_streams, slim_streams):
        assert snap.source == slim_row["source"]
        assert snap.rate_1h == slim_row["rate_1h"]
        assert snap.rate_24h == slim_row["rate_24h"]


# ---------------------------------------------------------------------------
# 6. Graceful degradation — broken launchctl yields a warning, not a crash
# ---------------------------------------------------------------------------


def test_snapshot_degrades_on_launchctl_error() -> None:
    snapshot = build_system_snapshot(
        signal_sources=(),
        launchctl_runner=_erroring_launchctl_runner,
        provenance_runner=_quiet_provenance_runner,
        now=_now_factory(_FIXED_NOW),
    )
    payload = snapshot.to_dict()
    assert payload["heartbeat"]["status"] == "unknown"
    # The rest of the envelope still serializes cleanly.
    assert isinstance(payload["heartbeat"].get("totals"), dict)
    assert isinstance(payload["signal_streams"], list)
    json_payload = json.dumps(payload)
    assert isinstance(json_payload, str)


def test_launchagents_only_endpoint_serializable() -> None:
    payload = build_launchagents_only(
        launchctl_runner=_empty_launchctl_runner,
        now=_now_factory(_FIXED_NOW),
    )
    assert "launchagents" in payload
    assert "totals" in payload
    assert "mode" in payload
    json.dumps(payload)


# ---------------------------------------------------------------------------
# 7. SystemSnapshot is dataclass-shaped
# ---------------------------------------------------------------------------


def test_system_snapshot_dataclass_shape() -> None:
    snapshot = build_system_snapshot(
        signal_sources=(),
        launchctl_runner=_empty_launchctl_runner,
        provenance_runner=_quiet_provenance_runner,
        now=_now_factory(_FIXED_NOW),
    )
    assert isinstance(snapshot, SystemSnapshot)
    assert snapshot.generated_at == "2026-04-29T12:00:00+00:00"
