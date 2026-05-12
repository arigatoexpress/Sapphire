"""Unit tests for ``lib.observability.aggregator``.

Every probe (subprocess + filesystem) is mocked. No live network calls,
no real ``launchctl``. Clock injection makes rate windows deterministic.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.observability import aggregator  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)


def _frozen_now() -> datetime:
    return _NOW


def _make_completed(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["launchctl", "list"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _scaffold_repo(tmp_path: Path, *, plist_label: str = "com.sapphire.demo") -> Path:
    repo_root = tmp_path / "repo"
    (repo_root / "infra" / "launchagents").mkdir(parents=True)
    (repo_root / "services" / "demo" / "launchagent").mkdir(parents=True)
    (repo_root / "data" / "logs").mkdir(parents=True)
    (repo_root / "data" / "events").mkdir(parents=True)
    plist_payload = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict><key>Label</key>'
        f"<string>{plist_label}</string></dict></plist>\n"
    )
    (repo_root / "infra" / "launchagents" / "demo.plist").write_text(plist_payload)
    return repo_root


def _seed_signal_dir(repo_root: Path, subdir: str, records: list[dict]) -> Path:
    target = repo_root / "data" / subdir
    target.mkdir(parents=True, exist_ok=True)
    file = target / "events.jsonl"
    file.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return file


# ---------------------------------------------------------------------------
# Heartbeat (#1-4)
# ---------------------------------------------------------------------------


def _runner_with_output(output: str):
    def _runner() -> subprocess.CompletedProcess[str]:
        return _make_completed(output)

    return _runner


def _ok_provenance() -> dict:
    return {"ok": True, "checked": 0, "missing_or_invalid": 0, "rows": []}


def test_heartbeat_running_pid_classified_as_running(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    snapshot = aggregator.build_system_snapshot(
        repo_root=repo_root,
        pause_dir=tmp_path / "pause",
        inference_proxy_cache=tmp_path / "proxy",
        bus_path=repo_root / "data" / "events" / "bus.jsonl",
        launchctl_runner=_runner_with_output("12345\t0\tcom.sapphire.demo\n"),
        provenance_runner=_ok_provenance,
        now=_frozen_now,
    )
    rows = snapshot.heartbeat["launchagents"]
    demo = next(r for r in rows if r["label"] == "com.sapphire.demo")
    assert demo["status_label"] == "running"
    assert demo["pid"] == 12345
    assert snapshot.heartbeat["status"] == "pass"


def test_heartbeat_loaded_zero_exit_classified_as_loaded(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    snapshot = aggregator.build_system_snapshot(
        repo_root=repo_root,
        pause_dir=tmp_path / "pause",
        inference_proxy_cache=tmp_path / "proxy",
        bus_path=repo_root / "data" / "events" / "bus.jsonl",
        launchctl_runner=_runner_with_output("-\t0\tcom.sapphire.demo\n"),
        provenance_runner=_ok_provenance,
        now=_frozen_now,
    )
    demo = next(r for r in snapshot.heartbeat["launchagents"] if r["label"] == "com.sapphire.demo")
    assert demo["status_label"] == "loaded"
    assert demo["pid"] is None


def test_heartbeat_subprocess_timeout_marks_unknown(tmp_path):
    repo_root = _scaffold_repo(tmp_path)

    def boom():
        raise subprocess.TimeoutExpired(cmd="launchctl", timeout=5.0)

    snapshot = aggregator.build_system_snapshot(
        repo_root=repo_root,
        pause_dir=tmp_path / "pause",
        inference_proxy_cache=tmp_path / "proxy",
        bus_path=repo_root / "data" / "events" / "bus.jsonl",
        launchctl_runner=boom,
        provenance_runner=_ok_provenance,
        now=_frozen_now,
    )
    assert snapshot.heartbeat["status"] == "unknown"
    assert "TimeoutExpired" in (snapshot.heartbeat["error"] or "")
    # Every label is reported as unknown, none as not_loaded.
    assert all(row["status_label"] == "unknown" for row in snapshot.heartbeat["launchagents"])


def test_heartbeat_label_not_in_launchctl_marks_not_loaded(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    snapshot = aggregator.build_system_snapshot(
        repo_root=repo_root,
        pause_dir=tmp_path / "pause",
        inference_proxy_cache=tmp_path / "proxy",
        bus_path=repo_root / "data" / "events" / "bus.jsonl",
        launchctl_runner=_runner_with_output("12345\t0\tunrelated.label\n"),
        provenance_runner=_ok_provenance,
        now=_frozen_now,
    )
    demo = next(r for r in snapshot.heartbeat["launchagents"] if r["label"] == "com.sapphire.demo")
    assert demo["status_label"] == "not_loaded"


# ---------------------------------------------------------------------------
# Inference proxy (#5-7)
# ---------------------------------------------------------------------------


def test_inference_proxy_cache_absent_returns_mock_tiers(tmp_path):
    proxy = aggregator._build_inference_proxy(cache_dir=tmp_path / "absent", now=_NOW)
    assert proxy.available is False
    assert proxy.note == "cache_directory_absent"
    assert len(proxy.tiers) == 4
    assert all("endpoint" in tier for tier in proxy.tiers)


def test_inference_proxy_reads_token_consumption_when_present(tmp_path):
    cache = tmp_path / "proxy"
    cache.mkdir()
    (cache / "token_consumption.json").write_text(
        json.dumps(
            {
                "total": 12345,
                "by_tier": {"T1_GPU": 999},
                "window": "lifetime",
                "last_updated": 1761500000,
            }
        )
    )
    (cache / "tier_health.json").write_text(
        json.dumps(
            [
                {
                    "tier": "T1_GPU",
                    "endpoint": "100.71.10.48:11434",
                    "healthy": True,
                    "latency_ms": 410,
                }
            ]
        )
    )
    proxy = aggregator._build_inference_proxy(cache_dir=cache, now=_NOW)
    assert proxy.available is True
    assert proxy.token_consumption["total"] == 12345
    assert proxy.tiers[0]["healthy"] is True
    assert proxy.tiers[0]["latency_ms"] == 410
    assert proxy.last_updated and proxy.last_updated.startswith("2025-")  # mtime-derived; tolerant


def test_inference_proxy_malformed_token_file_falls_back(tmp_path):
    cache = tmp_path / "proxy"
    cache.mkdir()
    (cache / "token_consumption.json").write_text("not-json")
    proxy = aggregator._build_inference_proxy(cache_dir=cache, now=_NOW)
    assert proxy.token_consumption["total"] == 0
    # Tiers fall back to mock when tier_health is absent.
    assert len(proxy.tiers) == 4


# ---------------------------------------------------------------------------
# Signal streams (#8-12)
# ---------------------------------------------------------------------------


def test_signal_streams_count_recent_records_only(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    now_ts = _NOW.timestamp()
    records = [
        {"ts": (_NOW - timedelta(minutes=30)).isoformat()},  # within 1h
        {"ts": (_NOW - timedelta(hours=2)).isoformat()},  # within 24h
        {"ts": (_NOW - timedelta(days=2)).isoformat()},  # outside both
    ]
    _seed_signal_dir(repo_root, "signals", records)
    streams = aggregator._build_signal_streams(
        repo_root=repo_root,
        now=_NOW,
        sources=(("tradingview", "signals"),),
    )
    assert streams[0].rate_1h == 1
    assert streams[0].rate_24h == 2
    assert streams[0].files_seen == 1
    del now_ts  # silence


def test_signal_streams_directory_absent_returns_zero(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    streams = aggregator._build_signal_streams(
        repo_root=repo_root,
        now=_NOW,
        sources=(("absent", "no_such_dir"),),
    )
    assert streams[0].rate_1h == 0
    assert streams[0].rate_24h == 0
    assert streams[0].note == "directory_absent"


def test_signal_streams_malformed_json_uses_mtime_fallback(tmp_path, monkeypatch):
    repo_root = _scaffold_repo(tmp_path)
    target = repo_root / "data" / "signals"
    target.mkdir(parents=True)
    file = target / "broken.jsonl"
    file.write_text("not-json\n{also-broken\n")
    # Tighten file mtime so it falls within the 1h window.
    import os as _os

    new_mtime = (_NOW - timedelta(minutes=10)).timestamp()
    _os.utime(file, (new_mtime, new_mtime))
    streams = aggregator._build_signal_streams(
        repo_root=repo_root,
        now=_NOW,
        sources=(("tradingview", "signals"),),
    )
    assert streams[0].rate_1h == 2  # both lines counted via fallback mtime
    assert streams[0].rate_24h == 2


def test_signal_streams_supports_unix_timestamp_field(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    records = [
        {"timestamp": (_NOW - timedelta(minutes=5)).timestamp()},
        {"created_at": (_NOW - timedelta(minutes=3)).timestamp()},
    ]
    _seed_signal_dir(repo_root, "signals", records)
    streams = aggregator._build_signal_streams(
        repo_root=repo_root,
        now=_NOW,
        sources=(("tradingview", "signals"),),
    )
    assert streams[0].rate_1h == 2


def test_signal_streams_total_in_slim_endpoint(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    _seed_signal_dir(
        repo_root,
        "signals",
        [{"ts": (_NOW - timedelta(minutes=5)).isoformat()} for _ in range(3)],
    )
    payload = aggregator.build_stream_rates_only(
        repo_root=repo_root,
        signal_sources=(("tradingview", "signals"),),
        now=_frozen_now,
    )
    assert payload["mode"] == "read_only_observability_stream_rates"
    assert payload["totals"]["rate_1h"] == 3
    assert payload["totals"]["rate_24h"] == 3
    assert payload["sources"][0]["source"] == "tradingview"


# ---------------------------------------------------------------------------
# Provenance (#13-15)
# ---------------------------------------------------------------------------


def test_provenance_runner_pass_status(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    snap = aggregator._build_provenance(
        repo_root=repo_root,
        now=_NOW,
        runner=lambda: {"ok": True, "checked": 5, "missing_or_invalid": 0, "rows": []},
    )
    assert snap.status == "pass"
    assert snap.checked == 5
    assert snap.missing_or_invalid == 0
    assert snap.invalid_sample == []


def test_provenance_runner_warn_with_invalid_sample(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    rows = [
        {"ok": False, "artifact": "/abs/path/file.json", "reason": "missing_sidecar"},
        {"ok": True, "artifact": "/abs/path/ok.json", "reason": "ok"},
    ]
    snap = aggregator._build_provenance(
        repo_root=repo_root,
        now=_NOW,
        runner=lambda: {"ok": False, "checked": 2, "missing_or_invalid": 1, "rows": rows},
    )
    assert snap.status == "warn"
    assert snap.missing_or_invalid == 1
    assert snap.invalid_sample == [{"artifact": "/abs/path/file.json", "reason": "missing_sidecar"}]


def test_provenance_runner_exception_returns_unknown(tmp_path):
    repo_root = _scaffold_repo(tmp_path)

    def boom():
        raise RuntimeError("provenance script crashed")

    snap = aggregator._build_provenance(repo_root=repo_root, now=_NOW, runner=boom)
    assert snap.status == "unknown"
    assert "RuntimeError" in (snap.error or "")


# ---------------------------------------------------------------------------
# Routine pause (#16-17)
# ---------------------------------------------------------------------------


def test_routine_pause_empty_dir_returns_pass(tmp_path):
    summary, rows = aggregator._build_routine_pause(pause_dir=tmp_path / "absent")
    assert summary["status"] == "pass"
    assert summary["totals"]["paused"] == 0
    assert rows == []


def test_routine_pause_skips_dotfiles_and_non_routine_names(tmp_path):
    pause_dir = tmp_path / "pause"
    pause_dir.mkdir()
    (pause_dir / "morning-briefing").write_text("2026-04-28T10:00:00+00:00\n")
    (pause_dir / ".DS_Store").write_text("noise")
    (pause_dir / "bad.name.txt").write_text("ignored")
    summary, rows = aggregator._build_routine_pause(pause_dir=pause_dir)
    assert summary["totals"]["paused"] == 1
    assert rows[0].name == "morning-briefing"
    assert rows[0].paused_at == "2026-04-28T10:00:00+00:00"


# ---------------------------------------------------------------------------
# Event bus (#18-20)
# ---------------------------------------------------------------------------


def test_event_bus_absent_log_returns_zero_events(tmp_path):
    snap = aggregator._build_event_bus(bus_path=tmp_path / "missing.jsonl")
    assert snap.events_seen == 0
    assert snap.distinct_topics == 0
    assert snap.note == "bus_log_absent"
    # display path stays relative even when the file does not exist.
    assert snap.relative_path.endswith("missing.jsonl")


def test_event_bus_topic_distribution_counts_correctly(tmp_path):
    bus = tmp_path / "bus.jsonl"
    events = [
        {"type": "signal.generated", "ts": _NOW.isoformat()},
        {"type": "signal.generated", "ts": _NOW.isoformat()},
        {"type": "threat.detected", "ts": _NOW.isoformat()},
    ]
    bus.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    snap = aggregator._build_event_bus(bus_path=bus)
    assert snap.events_seen == 3
    assert snap.distinct_topics == 2
    topics = {row["topic"]: row["count"] for row in snap.topic_distribution}
    assert topics["signal.generated"] == 2
    assert topics["threat.detected"] == 1


def test_event_bus_skips_non_dict_lines(tmp_path):
    bus = tmp_path / "bus.jsonl"
    bus.write_text(
        json.dumps({"type": "good.event", "ts": _NOW.isoformat()})
        + "\n"
        + json.dumps([1, 2, 3])
        + "\n"  # not-a-dict
        + "garbage line\n"
        + json.dumps({"topic": "alt.topic"})
        + "\n"
    )
    snap = aggregator._build_event_bus(bus_path=bus)
    assert snap.events_seen == 2
    topics = {row["topic"] for row in snap.topic_distribution}
    assert topics == {"good.event", "alt.topic"}


# ---------------------------------------------------------------------------
# End-to-end + helpers (#21-25)
# ---------------------------------------------------------------------------


def test_build_system_snapshot_full_envelope_serializable(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    snap = aggregator.build_system_snapshot(
        repo_root=repo_root,
        pause_dir=tmp_path / "pause",
        inference_proxy_cache=tmp_path / "proxy",
        bus_path=repo_root / "data" / "events" / "bus.jsonl",
        signal_sources=(("tradingview", "signals"),),
        launchctl_runner=lambda: _make_completed("12345\t0\tcom.sapphire.demo\n"),
        provenance_runner=lambda: {"ok": True, "checked": 1, "missing_or_invalid": 0, "rows": []},
        now=_frozen_now,
    )
    payload = snap.to_dict()
    # Round-trip through json.dumps to prove the envelope is JSON-safe.
    encoded = json.dumps(payload)
    assert "schema_version" in encoded
    assert payload["status"] in {"pass", "warn", "unknown"}
    assert "heartbeat" in payload
    assert "inference_proxy" in payload
    assert "signal_streams" in payload
    assert "provenance" in payload
    assert "routine_pause" in payload
    assert "event_bus" in payload


def test_display_path_abbreviates_home_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(aggregator.Path, "home", classmethod(lambda cls: Path("/Users/aribs")))
    abbreviated = aggregator._display_path(Path("/Users/aribs/.cache/sapphire/inference_proxy"))
    assert abbreviated.replace("\\", "/") == "~/.cache/sapphire/inference_proxy"


def test_aggregate_status_warn_overrides(tmp_path):
    assert aggregator._aggregate_status("pass", "warn", "pass") == "warn"
    assert aggregator._aggregate_status("pass", "pass", "pass") == "pass"
    assert aggregator._aggregate_status("unknown", "pass") == "warn"


def test_build_launchagents_only_returns_slim_envelope(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    payload = aggregator.build_launchagents_only(
        repo_root=repo_root,
        launchctl_runner=lambda: _make_completed("12345\t0\tcom.sapphire.demo\n"),
        now=_frozen_now,
    )
    assert payload["mode"] == "read_only_observability_launchagents"
    assert payload["status"] == "pass"
    labels = {row["label"] for row in payload["launchagents"]}
    assert "com.sapphire.demo" in labels


def test_extract_timestamp_handles_zulu_iso(tmp_path):
    ts = aggregator._extract_timestamp({"ts": "2026-04-28T12:00:00Z"})
    assert ts is not None
    assert int(ts) == int(_NOW.timestamp())
    assert aggregator._extract_timestamp({"ts": "garbage"}) is None
    assert aggregator._extract_timestamp({"ts": 1761500000}) == 1761500000.0
    assert aggregator._extract_timestamp({}) is None


def test_signal_stream_with_missing_timestamps_falls_back_to_mtime(tmp_path):
    repo_root = _scaffold_repo(tmp_path)
    _seed_signal_dir(repo_root, "signals", [{"payload": "no ts here"}])
    # File mtime is "now" since just-written, so should be in the 1h window.
    streams = aggregator._build_signal_streams(
        repo_root=repo_root,
        now=datetime.now(UTC),  # use real-now so file mtime falls inside window
        sources=(("tradingview", "signals"),),
    )
    assert streams[0].rate_1h == 1
