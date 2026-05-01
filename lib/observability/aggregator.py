"""Pure-logic aggregator for the ``/observability`` dashboard.

The aggregator builds a :class:`SystemSnapshot` from on-disk state and
``launchctl list`` output. It is intentionally:

* **Pure-logic** — no flask, no jinja, no redis, no network. The dashboard
  layer wraps the snapshot in JSON; this module owns the data shape.
* **Fail-soft** — every probe (subprocess, json.load, glob) is wrapped so a
  partial outage degrades a single section to ``status="unknown"`` rather
  than collapsing the whole snapshot.
* **Path-safe** — absolute paths under the user's home directory are
  abbreviated (``~/.cache/sapphire/...`` etc.) so the JSON envelope never
  leaks the operator's machine layout to a buyer-facing dashboard reader.
* **Clock-injectable** — every "now" reference flows through an optional
  ``now: Callable[[], datetime]`` argument so tests can pin the clock and
  verify rate windows deterministically.

The snapshot covers six sections, mirroring the Lane 2 spec in
``docs/handoffs/codex-megaprompt-tranche-3-2026-04-28.md``:

1. **Heartbeat** — uptime + LaunchAgent last-fire times (via launchctl).
2. **Inference proxy** — 4-tier health + token consumption (cache-derived).
3. **Signal streams** — per-source rates over the last 1h and 24h.
4. **Provenance coverage** — sidecar verification stats.
5. **Routine pause** — operator-paused routines with timestamps.
6. **Event bus** — topic distribution from the recent tail of the bus log.
"""

from __future__ import annotations

import json
import plistlib
import subprocess
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Defaults (overridable by tests / callers)
# ---------------------------------------------------------------------------

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAUSE_DIR = Path.home() / ".sapphire" / "routine_pause"
DEFAULT_INFERENCE_PROXY_CACHE = Path.home() / ".cache" / "sapphire" / "inference_proxy"
DEFAULT_BUS_PATH = DEFAULT_REPO_ROOT / "data" / "events" / "bus.jsonl"

# Signal stream sources — each entry maps a logical "source name" to the
# directory under ``data/`` whose ``*.jsonl`` files we count for rates.
# Files are read newest-mtime first; only the recent tail is loaded so a
# multi-megabyte historic log does not pull the dashboard offline.
DEFAULT_SIGNAL_SOURCES: tuple[tuple[str, str], ...] = (
    ("tradingview", "signals"),
    ("telegram_intel", "telegram_intel"),
    ("hyperliquid", "hyperliquid"),
    ("threat_intel", "threat_intel"),
    ("convergence_watchlist", "convergence_watchlist"),
)

# Hard caps on inputs — the aggregator must never block the dashboard.
_BUS_TAIL_BYTES = 256 * 1024  # 256 KB tail for topic distribution
_MAX_BUS_EVENTS = 200
_MAX_RATE_FILES = 8  # newest N files per source
_MAX_RATE_BYTES_PER_FILE = 2 * 1024 * 1024  # 2 MB
_LAUNCHCTL_TIMEOUT_S = 5.0
_HOUR_S = 3600.0
_DAY_S = 86_400.0


# ---------------------------------------------------------------------------
# Dataclasses (the JSON envelope shape)
# ---------------------------------------------------------------------------


@dataclass
class LaunchAgentRow:
    """One row in the LaunchAgent heartbeat table."""

    label: str
    status_label: str  # "running" | "loaded" | "exited" | "not_loaded" | "unknown"
    pid: int | str | None
    last_exit: int | str | None
    last_fired_at: str | None  # ISO-8601, derived from log mtime when available
    restart_count: int


@dataclass
class InferenceProxySnapshot:
    """Inference proxy tier health + token spend."""

    cache_dir: str  # display path
    tiers: list[dict[str, Any]] = field(default_factory=list)
    token_consumption: dict[str, Any] = field(default_factory=dict)
    last_updated: str | None = None
    available: bool = True
    note: str | None = None


@dataclass
class SignalStreamSnapshot:
    """Per-source rates and freshness."""

    source: str
    relative_path: str
    rate_1h: int
    rate_24h: int
    files_seen: int
    latest_record_at: str | None
    note: str | None = None


@dataclass
class ProvenanceSnapshot:
    """Provenance coverage rollup."""

    status: str  # "pass" | "warn" | "unknown"
    checked: int
    missing_or_invalid: int
    last_verify_at: str | None
    invalid_sample: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None


@dataclass
class RoutinePauseRow:
    """One operator-paused routine."""

    name: str
    paused_at: str | None


@dataclass
class EventBusSnapshot:
    """Tail of the event bus log with topic distribution."""

    relative_path: str
    events_seen: int
    distinct_topics: int
    topic_distribution: list[dict[str, Any]]
    latest_event_at: str | None
    earliest_event_at: str | None
    note: str | None = None


@dataclass
class SystemSnapshot:
    """Top-level aggregator output."""

    schema_version: int
    mode: str
    status: str  # "pass" | "warn" | "unknown"
    generated_at: str
    heartbeat: dict[str, Any]
    inference_proxy: InferenceProxySnapshot
    signal_streams: list[SignalStreamSnapshot]
    provenance: ProvenanceSnapshot
    routine_pause: dict[str, Any]
    event_bus: EventBusSnapshot

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict envelope safe for ``json.dumps``."""
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "status": self.status,
            "generated_at": self.generated_at,
            "heartbeat": self.heartbeat,
            "inference_proxy": asdict(self.inference_proxy),
            "signal_streams": [asdict(stream) for stream in self.signal_streams],
            "provenance": asdict(self.provenance),
            "routine_pause": self.routine_pause,
            "event_bus": asdict(self.event_bus),
        }


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _now(now: Callable[[], datetime] | None = None) -> datetime:
    return (now or (lambda: datetime.now(UTC)))()


def _display_path(path: Path) -> str:
    """Abbreviate absolute paths so JSON output never leaks ``$HOME``."""
    try:
        text = str(path)
    except Exception:
        return str(path)
    home = str(Path.home())
    if text.startswith(home):
        return "~" + text[len(home) :]
    return text


def _iso(ts: float | None) -> str | None:
    if ts is None or ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=UTC).replace(microsecond=0).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# LaunchAgent heartbeat
# ---------------------------------------------------------------------------


def _enumerate_launchagent_labels(repo_root: Path) -> list[str]:
    """Return the union of LaunchAgent labels declared under the repo."""
    paths: list[Path] = []
    paths.extend(sorted((repo_root / "infra" / "launchagents").glob("*.plist")))
    paths.extend(sorted((repo_root / "services").glob("*/launchagent/*.plist")))
    labels: set[str] = {"ai.hermes.gateway"}  # extra-repo gateway
    for path in paths:
        try:
            payload = plistlib.loads(path.read_bytes())
        except (OSError, plistlib.InvalidFileException):
            continue
        label = payload.get("Label") if isinstance(payload, dict) else None
        if isinstance(label, str) and label:
            labels.add(label)
    return sorted(labels)


def _parse_launchctl_list(output: str) -> dict[str, dict[str, Any]]:
    """Parse the three-column ``launchctl list`` table.

    Mirrors :func:`services.dashboard.app._parse_launchctl_list` so the
    dashboard layer can swap the inline implementation for this one once
    the aggregator lands without changing observable behavior.
    """
    rows: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("pid"):
            continue
        parts = stripped.split(maxsplit=2)
        if len(parts) != 3:
            continue
        pid_raw, status_raw, label = parts
        if pid_raw == "-":
            pid: int | str | None = None
        elif pid_raw.lstrip("-").isdigit():
            pid = int(pid_raw)
        else:
            pid = pid_raw
        last_exit: int | str | None
        if status_raw.lstrip("-").isdigit():
            last_exit = int(status_raw)
        else:
            last_exit = status_raw
        rows[label] = {"pid": pid, "last_exit": last_exit}
    return rows


def _last_fired_at(label: str, repo_root: Path) -> str | None:
    """Best-effort last-fire timestamp from log mtime when present.

    LaunchAgent stdout/stderr by Sapphire convention land under
    ``data/logs/<label>.{out,err}``. The aggregator opportunistically reads
    those file mtimes; missing logs return ``None``.
    """
    candidates = [
        repo_root / "data" / "logs" / f"{label}.out.log",
        repo_root / "data" / "logs" / f"{label}.err.log",
        repo_root / "data" / "logs" / f"{label}.out",
        repo_root / "data" / "logs" / f"{label}.err",
    ]
    best: float | None = None
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime > best:
            best = mtime
    return _iso(best)


def _restart_count(label: str, repo_root: Path) -> int:
    """Cheap restart counter from the supervisor state file when available."""
    state_path = repo_root / "data" / "supervisor_state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    entry = payload.get(label) or payload.get("agents", {}).get(label)
    if isinstance(entry, dict):
        try:
            return int(entry.get("restart_count", 0) or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _build_heartbeat(
    *,
    repo_root: Path,
    now: datetime,
    launchctl_runner: Callable[[], subprocess.CompletedProcess[str]] | None,
) -> tuple[dict[str, Any], list[LaunchAgentRow]]:
    labels = _enumerate_launchagent_labels(repo_root)
    runner = launchctl_runner or _default_launchctl_runner
    parsed: dict[str, dict[str, Any]] = {}
    error: str | None = None
    try:
        result = runner()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        error = f"{exc.__class__.__name__}: {exc}"[:160]
    except Exception as exc:  # noqa: BLE001 — fail-soft envelope
        error = f"{exc.__class__.__name__}: {exc}"[:160]
    else:
        if result.returncode != 0:
            error = (result.stderr or "")[:160] or f"launchctl exit {result.returncode}"
        else:
            parsed = _parse_launchctl_list(result.stdout)
    rows: list[LaunchAgentRow] = []
    for label in labels:
        live = parsed.get(label)
        if live is None:
            status_label = "unknown" if error else "not_loaded"
            pid: int | str | None = None
            last_exit: int | str | None = None
        else:
            pid = live.get("pid")
            last_exit = live.get("last_exit")
            if pid not in (None, "-"):
                status_label = "running"
            elif last_exit == 0:
                status_label = "loaded"
            else:
                status_label = "exited"
        rows.append(
            LaunchAgentRow(
                label=label,
                status_label=status_label,
                pid=pid,
                last_exit=last_exit,
                last_fired_at=_last_fired_at(label, repo_root),
                restart_count=_restart_count(label, repo_root),
            )
        )
    totals = {
        "labels": len(rows),
        "running": sum(1 for row in rows if row.status_label == "running"),
        "loaded": sum(1 for row in rows if row.status_label in {"running", "loaded", "exited"}),
        "not_loaded": sum(1 for row in rows if row.status_label == "not_loaded"),
        "unknown": sum(1 for row in rows if row.status_label == "unknown"),
    }
    if error:
        status = "unknown"
    elif totals["running"] >= 1:
        status = "pass"
    else:
        status = "warn"
    heartbeat = {
        "status": status,
        "checked_at": now.replace(microsecond=0).isoformat(),
        "totals": totals,
        "uptime_seconds": _process_uptime_seconds(),
        "error": error,
    }
    return heartbeat, rows


def _default_launchctl_runner() -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed argv, no shell.
        ["launchctl", "list"],
        capture_output=True,
        text=True,
        timeout=_LAUNCHCTL_TIMEOUT_S,
        check=False,
    )


def _process_uptime_seconds() -> int | None:
    """Best-effort uptime since boot. macOS-only via ``sysctl`` proc btime.

    Returns ``None`` rather than raising on any platform mismatch so the
    aggregator's heartbeat section degrades gracefully on Linux CI runners.
    """
    try:
        result = subprocess.run(  # noqa: S603 — fixed argv, no shell.
            ["sysctl", "-n", "kern.boottime"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    # Format: "{ sec = 1761500000, usec = 0 } Tue Apr ..."
    sec_token = "sec = "
    if sec_token not in text:
        return None
    try:
        rest = text.split(sec_token, 1)[1]
        sec_str = rest.split(",", 1)[0].strip()
        boot_ts = int(sec_str)
    except (IndexError, ValueError):
        return None
    if boot_ts <= 0:
        return None
    delta = max(0, int(datetime.now(UTC).timestamp()) - boot_ts)
    return delta


# ---------------------------------------------------------------------------
# Inference proxy
# ---------------------------------------------------------------------------


def _build_inference_proxy(*, cache_dir: Path, now: datetime) -> InferenceProxySnapshot:
    snapshot = InferenceProxySnapshot(cache_dir=_display_path(cache_dir))
    if not cache_dir.exists():
        snapshot.available = False
        snapshot.note = "cache_directory_absent"
        snapshot.tiers = _mock_tier_health(now)
        snapshot.token_consumption = {"total": 0, "by_tier": {}, "window": "n/a"}
        return snapshot
    tier_health_path = cache_dir / "tier_health.json"
    token_path = cache_dir / "token_consumption.json"
    snapshot.tiers = _read_tier_health(tier_health_path) or _mock_tier_health(now)
    tokens = _read_json_safe(token_path)
    if isinstance(tokens, dict):
        snapshot.token_consumption = {
            "total": int(tokens.get("total", 0) or 0),
            "by_tier": tokens.get("by_tier", {}) or {},
            "window": tokens.get("window") or "lifetime",
        }
        last = tokens.get("last_updated")
        if isinstance(last, (int, float)):
            snapshot.last_updated = _iso(float(last))
        elif isinstance(last, str):
            snapshot.last_updated = last
    else:
        snapshot.token_consumption = {"total": 0, "by_tier": {}, "window": "n/a"}
    return snapshot


def _read_tier_health(path: Path) -> list[dict[str, Any]] | None:
    payload = _read_json_safe(path)
    if not isinstance(payload, list):
        return None
    rows: list[dict[str, Any]] = []
    for entry in payload[:8]:  # cap
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "tier": str(entry.get("tier", "unknown"))[:32],
                "endpoint": str(entry.get("endpoint", ""))[:120],
                "healthy": bool(entry.get("healthy", False)),
                "latency_ms": _coerce_int(entry.get("latency_ms")),
                "last_check": entry.get("last_check"),
            }
        )
    return rows or None


def _mock_tier_health(now: datetime) -> list[dict[str, Any]]:
    """Deterministic placeholder when the proxy cache is absent.

    Tests pass a fixed ``now`` so this output is reproducible.
    """
    iso = now.replace(microsecond=0).isoformat()
    return [
        {
            "tier": "T1_GPU",
            "endpoint": "100.71.10.48:11434",
            "healthy": False,
            "latency_ms": None,
            "last_check": iso,
        },
        {
            "tier": "T2_PI",
            "endpoint": "100.120.191.1:11434",
            "healthy": False,
            "latency_ms": None,
            "last_check": iso,
        },
        {
            "tier": "T3_MAC",
            "endpoint": "127.0.0.1:11434",
            "healthy": False,
            "latency_ms": None,
            "last_check": iso,
        },
        {
            "tier": "T4_KIMI",
            "endpoint": "api.moonshot.cn",
            "healthy": False,
            "latency_ms": None,
            "last_check": iso,
        },
    ]


# ---------------------------------------------------------------------------
# Signal streams
# ---------------------------------------------------------------------------


def _build_signal_streams(
    *,
    repo_root: Path,
    now: datetime,
    sources: Iterable[tuple[str, str]],
) -> list[SignalStreamSnapshot]:
    rows: list[SignalStreamSnapshot] = []
    cutoff_1h = now.timestamp() - _HOUR_S
    cutoff_24h = now.timestamp() - _DAY_S
    for source_name, subdir in sources:
        directory = repo_root / "data" / subdir
        relative = f"data/{subdir}"
        if not directory.exists() or not directory.is_dir():
            rows.append(
                SignalStreamSnapshot(
                    source=source_name,
                    relative_path=relative,
                    rate_1h=0,
                    rate_24h=0,
                    files_seen=0,
                    latest_record_at=None,
                    note="directory_absent",
                )
            )
            continue
        files = sorted(
            (path for path in directory.glob("*.jsonl") if path.is_file()),
            key=lambda p: p.stat().st_mtime if p.exists() else 0.0,
            reverse=True,
        )[:_MAX_RATE_FILES]
        rate_1h = 0
        rate_24h = 0
        latest_record: float | None = None
        for path in files:
            try:
                file_mtime = path.stat().st_mtime
            except OSError:
                continue
            data = _read_tail_bytes(path, _MAX_RATE_BYTES_PER_FILE)
            for record_ts in _iter_record_timestamps(data, fallback_mtime=file_mtime):
                if latest_record is None or record_ts > latest_record:
                    latest_record = record_ts
                if record_ts >= cutoff_1h:
                    rate_1h += 1
                if record_ts >= cutoff_24h:
                    rate_24h += 1
        rows.append(
            SignalStreamSnapshot(
                source=source_name,
                relative_path=relative,
                rate_1h=rate_1h,
                rate_24h=rate_24h,
                files_seen=len(files),
                latest_record_at=_iso(latest_record),
            )
        )
    return rows


def _read_tail_bytes(path: Path, max_bytes: int) -> bytes:
    try:
        size = path.stat().st_size
    except OSError:
        return b""
    if size <= 0:
        return b""
    read_bytes = min(size, max(1024, max_bytes))
    try:
        with path.open("rb") as handle:
            if size > read_bytes:
                handle.seek(size - read_bytes)
                handle.readline()  # discard partial leading line
            return handle.read()
    except OSError:
        return b""


def _iter_record_timestamps(payload: bytes, *, fallback_mtime: float) -> Iterable[float]:
    if not payload:
        return ()
    timestamps: list[float] = []
    for raw_line in payload.splitlines():
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line.decode("utf-8", errors="replace"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            timestamps.append(fallback_mtime)
            continue
        ts = _extract_timestamp(record)
        timestamps.append(ts if ts is not None else fallback_mtime)
    return timestamps


def _extract_timestamp(record: Any) -> float | None:
    if not isinstance(record, dict):
        return None
    for key in ("ts", "timestamp", "created_at", "fired_at", "time"):
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                # tolerate trailing 'Z'
                normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
                parsed = datetime.fromisoformat(normalized)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed.timestamp()
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def _build_provenance(
    *,
    repo_root: Path,
    now: datetime,
    runner: Callable[[], dict[str, Any]] | None,
) -> ProvenanceSnapshot:
    snapshot = ProvenanceSnapshot(
        status="unknown",
        checked=0,
        missing_or_invalid=0,
        last_verify_at=None,
    )
    try:
        report = runner() if runner else _default_provenance_runner(repo_root)
    except Exception as exc:  # noqa: BLE001 — fail-soft envelope
        snapshot.error = f"{exc.__class__.__name__}: {exc}"[:200]
        return snapshot
    if not isinstance(report, dict):
        snapshot.error = "provenance_runner_returned_non_dict"
        return snapshot
    snapshot.checked = int(report.get("checked", 0) or 0)
    snapshot.missing_or_invalid = int(report.get("missing_or_invalid", 0) or 0)
    snapshot.status = "pass" if report.get("ok") else "warn"
    invalid = []
    for row in (report.get("rows") or [])[:200]:
        if not isinstance(row, dict) or row.get("ok"):
            continue
        invalid.append(
            {
                "artifact": str(row.get("artifact", ""))[:200],
                "reason": str(row.get("reason", ""))[:80],
            }
        )
        if len(invalid) >= 5:
            break
    snapshot.invalid_sample = invalid
    snapshot.last_verify_at = now.replace(microsecond=0).isoformat()
    return snapshot


def _default_provenance_runner(repo_root: Path) -> dict[str, Any]:
    """Run ``scripts/ops/provenance_verify.py`` in-process when possible.

    Falls back to a "no sidecars detected" report if the script imports fail
    (e.g. on a partial checkout). Never raises — wraps the runner exception
    into the report's ``error`` channel.
    """
    try:
        # Importable in normal repo state.
        import sys as _sys  # noqa: PLC0415

        if str(repo_root) not in _sys.path:
            _sys.path.insert(0, str(repo_root))
        from scripts.ops import provenance_verify  # type: ignore[import-not-found]

        return provenance_verify.build_report(
            provenance_verify.DEFAULT_ROOTS,
            older_than_hours=24.0,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "checked": 0,
            "missing_or_invalid": 0,
            "rows": [],
            "error": f"{exc.__class__.__name__}: {exc}",
        }


# ---------------------------------------------------------------------------
# Routine pause
# ---------------------------------------------------------------------------


def _build_routine_pause(*, pause_dir: Path) -> tuple[dict[str, Any], list[RoutinePauseRow]]:
    rows: list[RoutinePauseRow] = []
    if pause_dir.exists() and pause_dir.is_dir():
        for entry in sorted(pause_dir.iterdir()):
            if not entry.is_file():
                continue
            name = entry.name
            # Skip dotfiles and obvious non-routine flags. Routine names are
            # lowercase + dash only by convention.
            if name.startswith(".") or "." in name:
                continue
            paused_at = _read_pause_marker(entry)
            rows.append(RoutinePauseRow(name=name, paused_at=paused_at))
    summary = {
        "status": "warn" if rows else "pass",
        "totals": {"paused": len(rows)},
        "paused_routines": [asdict(row) for row in rows],
    }
    return summary, rows


def _read_pause_marker(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text:
        return text.splitlines()[0][:64]
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return _iso(mtime)


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------


def _build_event_bus(*, bus_path: Path, max_events: int = _MAX_BUS_EVENTS) -> EventBusSnapshot:
    relative = _display_path(bus_path)
    if not bus_path.exists() or not bus_path.is_file():
        return EventBusSnapshot(
            relative_path=relative,
            events_seen=0,
            distinct_topics=0,
            topic_distribution=[],
            latest_event_at=None,
            earliest_event_at=None,
            note="bus_log_absent",
        )
    payload = _read_tail_bytes(bus_path, _BUS_TAIL_BYTES)
    counter: Counter[str] = Counter()
    timestamps: list[float] = []
    events_seen = 0
    for raw_line in payload.splitlines()[-max_events:]:
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line.decode("utf-8", errors="replace"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        topic = str(record.get("type") or record.get("topic") or "unknown")[:96]
        counter[topic] += 1
        events_seen += 1
        ts = _extract_timestamp(record)
        if ts is not None:
            timestamps.append(ts)
    distribution = [{"topic": topic, "count": count} for topic, count in counter.most_common(20)]
    return EventBusSnapshot(
        relative_path=relative,
        events_seen=events_seen,
        distinct_topics=len(counter),
        topic_distribution=distribution,
        latest_event_at=_iso(max(timestamps)) if timestamps else None,
        earliest_event_at=_iso(min(timestamps)) if timestamps else None,
    )


# ---------------------------------------------------------------------------
# Top-level builder + slim variants for the lightweight endpoints
# ---------------------------------------------------------------------------


def build_system_snapshot(
    *,
    repo_root: Path | None = None,
    pause_dir: Path | None = None,
    inference_proxy_cache: Path | None = None,
    bus_path: Path | None = None,
    signal_sources: Iterable[tuple[str, str]] | None = None,
    launchctl_runner: Callable[[], subprocess.CompletedProcess[str]] | None = None,
    provenance_runner: Callable[[], dict[str, Any]] | None = None,
    now: Callable[[], datetime] | None = None,
) -> SystemSnapshot:
    """Build the full ``/observability`` snapshot.

    Every external dependency (subprocess, filesystem root, clock) is
    overridable so tests can pin the entire surface deterministically.
    """
    resolved_root = repo_root or DEFAULT_REPO_ROOT
    resolved_pause = pause_dir or DEFAULT_PAUSE_DIR
    resolved_proxy = inference_proxy_cache or DEFAULT_INFERENCE_PROXY_CACHE
    resolved_bus = bus_path or DEFAULT_BUS_PATH
    resolved_sources = (
        tuple(signal_sources) if signal_sources is not None else DEFAULT_SIGNAL_SOURCES
    )
    current = _now(now)
    heartbeat, agents = _build_heartbeat(
        repo_root=resolved_root, now=current, launchctl_runner=launchctl_runner
    )
    proxy = _build_inference_proxy(cache_dir=resolved_proxy, now=current)
    streams = _build_signal_streams(repo_root=resolved_root, now=current, sources=resolved_sources)
    provenance = _build_provenance(repo_root=resolved_root, now=current, runner=provenance_runner)
    pause_summary, _ = _build_routine_pause(pause_dir=resolved_pause)
    bus_snapshot = _build_event_bus(bus_path=resolved_bus)
    heartbeat["launchagents"] = [asdict(row) for row in agents]
    overall = _aggregate_status(
        heartbeat["status"],
        provenance.status,
        pause_summary["status"],
    )
    return SystemSnapshot(
        schema_version=1,
        mode="read_only_observability_snapshot",
        status=overall,
        generated_at=current.replace(microsecond=0).isoformat(),
        heartbeat=heartbeat,
        inference_proxy=proxy,
        signal_streams=streams,
        provenance=provenance,
        routine_pause=pause_summary,
        event_bus=bus_snapshot,
    )


def build_stream_rates_only(
    *,
    repo_root: Path | None = None,
    signal_sources: Iterable[tuple[str, str]] | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Slim variant for ``/api/observability-stream-rates``."""
    resolved_root = repo_root or DEFAULT_REPO_ROOT
    resolved_sources = (
        tuple(signal_sources) if signal_sources is not None else DEFAULT_SIGNAL_SOURCES
    )
    current = _now(now)
    streams = _build_signal_streams(repo_root=resolved_root, now=current, sources=resolved_sources)
    totals_1h = sum(stream.rate_1h for stream in streams)
    totals_24h = sum(stream.rate_24h for stream in streams)
    return {
        "mode": "read_only_observability_stream_rates",
        "generated_at": current.replace(microsecond=0).isoformat(),
        "totals": {"rate_1h": totals_1h, "rate_24h": totals_24h},
        "sources": [asdict(stream) for stream in streams],
    }


def build_launchagents_only(
    *,
    repo_root: Path | None = None,
    launchctl_runner: Callable[[], subprocess.CompletedProcess[str]] | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Slim variant for ``/api/observability-launchagents``."""
    resolved_root = repo_root or DEFAULT_REPO_ROOT
    current = _now(now)
    heartbeat, agents = _build_heartbeat(
        repo_root=resolved_root, now=current, launchctl_runner=launchctl_runner
    )
    return {
        "mode": "read_only_observability_launchagents",
        "generated_at": heartbeat["checked_at"],
        "status": heartbeat["status"],
        "totals": heartbeat["totals"],
        "error": heartbeat.get("error"),
        "launchagents": [asdict(row) for row in agents],
    }


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _aggregate_status(*statuses: str) -> str:
    if "warn" in statuses:
        return "warn"
    if "unknown" in statuses and not all(s == "pass" for s in statuses):
        return "warn"
    return "pass"


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_json_safe(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
