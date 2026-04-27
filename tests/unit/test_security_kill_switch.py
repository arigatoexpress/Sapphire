"""Tests for lib/core/security_kill_switch.py.

The module is the per-service emergency kill switch (signal logger,
inference proxy, content engine, cloud-routing flag, Telegram alert).
Every step in :func:`engage` is non-fatal — errors must be collected, not
raised. ``disengage`` simply removes the on-disk flag.

These tests stub every subprocess and notify path so nothing reaches the
real OS or network.
"""

from __future__ import annotations

import json
import sys

import pytest

import lib.core.security_kill_switch as sks


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    """Redirect the module's hard-coded data paths into tmp_path."""
    events = tmp_path / "data" / "system_events.jsonl"
    flag = tmp_path / "data" / ".security_kill_switch_active"
    monkeypatch.setattr(sks, "_EVENTS_PATH", events)
    monkeypatch.setattr(sks, "_KILL_FLAG", flag)
    return tmp_path


@pytest.fixture
def stub_externals(monkeypatch):
    """Replace every subprocess / signal / launchctl call with a no-op."""
    calls: dict[str, list] = {
        "check_output": [],
        "kill": [],
        "run": [],
        "sent_telegram": [],
    }

    def fake_check_output(args, *_a, **_kw):
        calls["check_output"].append(args)
        return ""  # no PIDs running

    def fake_kill(pid, sig):
        calls["kill"].append((pid, sig))

    def fake_run(args, *_a, **_kw):
        calls["run"].append(args)

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(sks.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(sks.os, "kill", fake_kill)
    monkeypatch.setattr(sks.subprocess, "run", fake_run)

    # Replace the dynamic Telegram import with a stub so engage() doesn't try
    # to import the real notify tool from disk.
    fake_module = type(sys)("notify")

    def fake_send(msg, priority="p1"):  # noqa: ARG001
        calls["sent_telegram"].append((msg, priority))

    fake_module.send_telegram_message = fake_send  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "notify", fake_module)

    return calls


# ---------------------------------------------------------------------------
# is_engaged / disengage — flag lifecycle
# ---------------------------------------------------------------------------


def test_is_engaged_false_without_flag():
    assert sks.is_engaged() is False


def test_is_engaged_true_when_flag_present(isolated_paths):
    sks._KILL_FLAG.parent.mkdir(parents=True, exist_ok=True)
    sks._KILL_FLAG.write_text("{}\n")
    assert sks.is_engaged() is True


def test_disengage_removes_flag(isolated_paths):
    sks._KILL_FLAG.parent.mkdir(parents=True, exist_ok=True)
    sks._KILL_FLAG.write_text("{}\n")
    assert sks.is_engaged() is True
    sks.disengage()
    assert sks.is_engaged() is False


def test_disengage_is_idempotent_when_flag_missing(isolated_paths):
    """disengage() on a clean system must be a no-op, not raise."""
    assert not sks._KILL_FLAG.exists()
    sks.disengage()  # must not raise
    sks.disengage()  # second call still must not raise
    assert not sks._KILL_FLAG.exists()


def test_disengage_round_trip_after_engage(isolated_paths, stub_externals):
    """engage writes a flag with engaged_at + reason JSON; disengage clears it."""
    result = sks.engage(reason="round-trip test")
    assert sks.is_engaged() is True

    flag_payload = json.loads(sks._KILL_FLAG.read_text())
    assert flag_payload["reason"] == "security_kill_switch"
    assert "engaged_at" in flag_payload
    assert isinstance(result, sks.KillSwitchResult)

    sks.disengage()
    assert sks.is_engaged() is False


# ---------------------------------------------------------------------------
# _block_cloud_routing — the on-disk gate the proxy checks
# ---------------------------------------------------------------------------


def test_block_cloud_routing_writes_valid_json(isolated_paths):
    result = sks.KillSwitchResult(reason="unit test")
    sks._block_cloud_routing(result)

    assert sks._KILL_FLAG.exists()
    payload = json.loads(sks._KILL_FLAG.read_text())
    assert payload["reason"] == "security_kill_switch"
    assert "engaged_at" in payload
    assert any("Cloud routing kill flag written" in a for a in result.actions)
    assert result.errors == []


def test_block_cloud_routing_records_error_on_write_failure(monkeypatch, isolated_paths):
    """If the flag dir cannot be written, the error is collected — not raised."""
    result = sks.KillSwitchResult(reason="forced failure")

    def boom(*_a, **_kw):
        raise OSError("disk full")

    # Force the write step to fail.
    monkeypatch.setattr(sks._KILL_FLAG.__class__, "write_text", lambda self, *_a, **_kw: boom())
    sks._block_cloud_routing(result)

    assert result.errors  # at least one error captured
    assert all("Write kill flag" in e for e in result.errors)


# ---------------------------------------------------------------------------
# engage — full sequence
# ---------------------------------------------------------------------------


def test_engage_writes_event_log(isolated_paths, stub_externals):
    result = sks.engage(reason="suspected SIM-swap")
    assert isinstance(result, sks.KillSwitchResult)
    assert result.reason == "suspected SIM-swap"
    # The event log must contain the engagement event.
    assert sks._EVENTS_PATH.exists()
    lines = sks._EVENTS_PATH.read_text().splitlines()
    payload = json.loads(lines[-1])
    assert payload["type"] == "security.kill_switch.engaged"
    assert "priority:p0" in payload["tags"]
    assert payload["data"]["reason"] == "suspected SIM-swap"


def test_engage_collects_actions_in_order(isolated_paths, stub_externals):
    """The four service-stop steps and the alert step each append to actions."""
    result = sks.engage(reason="test sequence")
    # We expect at least one action per step. lsof returns "" → "not running" branch.
    assert any("Signal logger" in a for a in result.actions)
    assert any("Cloud routing kill flag written" in a for a in result.actions)
    assert any("LaunchAgent" in a for a in result.actions)
    assert any("Inference proxy" in a for a in result.actions)
    assert any("Telegram P0 alert sent" in a for a in result.actions)


def test_send_telegram_alert_does_not_mutate_sys_path(isolated_paths, stub_externals):
    before = list(sys.path)
    result = sks.KillSwitchResult(reason="import hygiene")

    sks._send_telegram_alert(result)

    assert sys.path == before
    assert any("Telegram P0 alert sent" in a for a in result.actions)


def test_engage_non_fatal_when_subprocess_raises(isolated_paths, monkeypatch):
    """Errors from subprocess must NOT abort engage()."""

    def boom(*_a, **_kw):
        raise OSError("lsof not found")

    monkeypatch.setattr(sks.subprocess, "check_output", boom)
    monkeypatch.setattr(sks.subprocess, "run", lambda *a, **kw: None)

    # Telegram path: import succeeds via fake module.
    fake_module = type(sys)("notify")
    fake_module.send_telegram_message = lambda *_a, **_kw: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "notify", fake_module)

    result = sks.engage(reason="forced failure path")
    # Each subprocess-dependent step should have logged an error rather than aborted.
    assert any("Stop signal logger" in e for e in result.errors)
    assert any("Stop inference proxy" in e for e in result.errors)
    assert sks._KILL_FLAG.exists()  # cloud routing still wrote successfully


def test_engage_when_processes_running_kills_each_pid(isolated_paths, monkeypatch):
    """When lsof returns PIDs, every PID is sent SIGTERM."""
    killed: list[tuple[int, int]] = []

    def fake_check_output(args, *_a, **_kw):
        # Return two pretend PIDs.
        return "1234\n5678\n"

    def fake_kill(pid, sig):
        killed.append((pid, sig))

    def fake_run(*_a, **_kw):
        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(sks.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(sks.subprocess, "run", fake_run)
    monkeypatch.setattr(sks.os, "kill", fake_kill)

    fake_module = type(sys)("notify")
    fake_module.send_telegram_message = lambda *_a, **_kw: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "notify", fake_module)

    result = sks.engage(reason="kill running services")
    # Two services × two pids each = 4 SIGTERMs.
    assert len(killed) == 4
    assert all(sig == sks.signal.SIGTERM for _, sig in killed)
    assert any("Signal logger (:18081) stopped" in a for a in result.actions)
    assert any("Inference proxy (:11435) stopped" in a for a in result.actions)


def test_engage_telegram_failure_collects_error(isolated_paths, monkeypatch):
    """A Telegram import/send failure must be collected, not raised."""

    monkeypatch.setattr(sks.subprocess, "check_output", lambda *a, **kw: "")
    monkeypatch.setattr(sks.subprocess, "run", lambda *a, **kw: None)

    # Replace notify with a module whose send_telegram_message raises.
    fake_module = type(sys)("notify")

    def boom(*_a, **_kw):
        raise RuntimeError("network unreachable")

    fake_module.send_telegram_message = boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "notify", fake_module)

    result = sks.engage(reason="forced send failure")
    # Error captured rather than raised; sequence still completed.
    assert any("Telegram alert" in e for e in result.errors)
    assert sks._KILL_FLAG.exists()


# ---------------------------------------------------------------------------
# KillSwitchResult.summary — formatting
# ---------------------------------------------------------------------------


def test_summary_includes_reason_and_actions():
    r = sks.KillSwitchResult(reason="ops drill")
    r.actions.append("Signal logger stopped")
    r.actions.append("Cloud flag written")
    text = r.summary()
    assert "Security Kill Switch ENGAGED" in text
    assert "Reason: ops drill" in text
    assert "Signal logger stopped" in text
    assert "Cloud flag written" in text


def test_summary_renders_errors_section_when_present():
    r = sks.KillSwitchResult(reason="partial failure")
    r.actions.append("ok step")
    r.errors.append("subprocess: failed")
    text = r.summary()
    assert "Errors (non-fatal):" in text
    assert "subprocess: failed" in text


def test_summary_skips_errors_section_when_empty():
    r = sks.KillSwitchResult(reason="clean run")
    r.actions.append("ok")
    text = r.summary()
    assert "Errors (non-fatal):" not in text


# ---------------------------------------------------------------------------
# _log_event — survives event-path failure
# ---------------------------------------------------------------------------


def test_log_event_does_not_raise_when_path_unwritable(monkeypatch, isolated_paths):
    """_log_event must swallow OSError so the kill-switch flow always finishes."""
    import builtins as _builtins

    result = sks.KillSwitchResult(reason="log test")
    result.actions.append("ok")

    real_open = _builtins.open
    failures = {"called": 0}

    def fake_open(path, *args, **kwargs):
        if str(path) == str(sks._EVENTS_PATH):
            failures["called"] += 1
            raise OSError("read-only fs")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(_builtins, "open", fake_open)
    # Must not raise.
    sks._log_event(result)
    assert failures["called"] >= 1


# ---------------------------------------------------------------------------
# _disable_content_engine — exception path
# ---------------------------------------------------------------------------


def test_disable_content_engine_collects_error_when_subprocess_raises(monkeypatch):
    """If launchctl subprocess.run raises, the error is captured in result.errors."""
    result = sks.KillSwitchResult(reason="launchctl failure")

    def boom(*_a, **_kw):
        raise OSError("launchctl missing")

    monkeypatch.setattr(sks.subprocess, "run", boom)
    sks._disable_content_engine(result)

    assert any("Unload com.sapphire.content-engine" in e for e in result.errors)
    # No success action recorded when the call raised.
    assert not any("LaunchAgent" in a for a in result.actions)


# ---------------------------------------------------------------------------
# _load_telegram_sender — filesystem fallback path
# ---------------------------------------------------------------------------


def test_load_telegram_sender_uses_cached_module(monkeypatch):
    """A `notify` module already in sys.modules with send_telegram_message wins."""
    cached = type(sys)("notify")
    sentinel = object()
    cached.send_telegram_message = sentinel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "notify", cached)

    assert sks._load_telegram_sender() is sentinel


def test_load_telegram_sender_loads_from_disk_when_cache_invalid(monkeypatch, tmp_path):
    """If the cached module lacks send_telegram_message, the disk loader runs.

    We point _SAPPHIRE at a tmp dir holding a minimal notify.py and assert the
    spec/loader path executes and returns the function from disk.
    """
    # Cache an unrelated module so the early return is skipped.
    monkeypatch.setitem(sys.modules, "notify", type(sys)("notify"))

    # Build the directory layout the loader expects.
    tools_dir = tmp_path / "plugins" / "claw-sapphire" / "tools"
    tools_dir.mkdir(parents=True)
    notify_path = tools_dir / "notify.py"
    notify_path.write_text(
        "def send_telegram_message(msg, priority='p1'):\n"
        "    return {'msg': msg, 'priority': priority, 'from_disk': True}\n"
    )

    monkeypatch.setattr(sks, "_SAPPHIRE", tmp_path)

    sender = sks._load_telegram_sender()
    out = sender("hello", priority="p0")
    assert out == {"msg": "hello", "priority": "p0", "from_disk": True}


def test_load_telegram_sender_raises_when_path_missing(monkeypatch, tmp_path):
    """When neither cache nor disk path is valid, ImportError is raised."""
    monkeypatch.setitem(sys.modules, "notify", type(sys)("notify"))
    # Point at an empty tmp dir — notify.py does not exist there.
    monkeypatch.setattr(sks, "_SAPPHIRE", tmp_path)

    with pytest.raises((ImportError, FileNotFoundError)):
        sks._load_telegram_sender()


# ---------------------------------------------------------------------------
# CLI entrypoint — covers the __main__ block
# ---------------------------------------------------------------------------


def test_module_runs_as_script_with_default_reason(monkeypatch, tmp_path, capsys):
    """Executing the module as `python3 -m lib.core.security_kill_switch`."""
    import runpy

    # Redirect on-disk paths the module touches.
    flag = tmp_path / "data" / ".security_kill_switch_active"
    events = tmp_path / "data" / "system_events.jsonl"
    monkeypatch.setattr(sks, "_KILL_FLAG", flag)
    monkeypatch.setattr(sks, "_EVENTS_PATH", events)

    # Stub every external side-effect so nothing real runs.
    monkeypatch.setattr(sks.subprocess, "check_output", lambda *_a, **_kw: "")
    monkeypatch.setattr(sks.subprocess, "run", lambda *_a, **_kw: None)
    monkeypatch.setattr(sks.os, "kill", lambda *_a, **_kw: None)

    fake_module = type(sys)("notify")
    fake_module.send_telegram_message = lambda *_a, **_kw: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "notify", fake_module)

    monkeypatch.setattr(sys, "argv", ["security_kill_switch"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("lib.core.security_kill_switch", run_name="__main__")

    # All sub-calls were stubbed so no errors should be collected.
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "Security Kill Switch ENGAGED" in captured.out
    assert "Manual CLI invocation" in captured.out


def test_module_runs_as_script_with_custom_reason(monkeypatch, tmp_path, capsys):
    """The CLI joins extra argv tokens into the engagement reason."""
    import runpy

    monkeypatch.setattr(sks, "_KILL_FLAG", tmp_path / "data" / ".security_kill_switch_active")
    monkeypatch.setattr(sks, "_EVENTS_PATH", tmp_path / "data" / "system_events.jsonl")
    monkeypatch.setattr(sks.subprocess, "check_output", lambda *_a, **_kw: "")
    monkeypatch.setattr(sks.subprocess, "run", lambda *_a, **_kw: None)
    monkeypatch.setattr(sks.os, "kill", lambda *_a, **_kw: None)

    fake_module = type(sys)("notify")
    fake_module.send_telegram_message = lambda *_a, **_kw: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "notify", fake_module)

    monkeypatch.setattr(sys, "argv", ["security_kill_switch", "ops", "drill"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("lib.core.security_kill_switch", run_name="__main__")

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "Reason: ops drill" in out


def test_module_exit_code_one_when_errors_collected(monkeypatch, tmp_path, capsys):
    """When engage() collects any errors, the CLI exits with status 1."""
    import runpy

    monkeypatch.setattr(sks, "_KILL_FLAG", tmp_path / "data" / ".security_kill_switch_active")
    monkeypatch.setattr(sks, "_EVENTS_PATH", tmp_path / "data" / "system_events.jsonl")

    # Force every subprocess call to raise so each step appends an error.
    def boom(*_a, **_kw):
        raise OSError("simulated failure")

    monkeypatch.setattr(sks.subprocess, "check_output", boom)
    monkeypatch.setattr(sks.subprocess, "run", boom)
    # Telegram path also fails.
    fake_module = type(sys)("notify")
    fake_module.send_telegram_message = boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "notify", fake_module)

    monkeypatch.setattr(sys, "argv", ["security_kill_switch", "forced"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("lib.core.security_kill_switch", run_name="__main__")

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "Errors (non-fatal)" in out
