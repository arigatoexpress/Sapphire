"""Tests for services/security_pipeline/run.py — the daily 3 AM security sweep.

The pipeline is a five-stage orchestrator:

    1. ``scan_secrets()``    — regex scan over Python files in lib/services/plugins
    2. ``scan_dependencies()`` — pip-audit subprocess invocation
    3. ``refresh_threat_intel()`` — calls plugins/.../threat_intel.py via subprocess
    4. ``compute_score()``   — weighted deductions producing letter grade A-F
    5. ``main()``            — assembles the report, writes JSON, publishes event

Importing ``run.py`` has two side effects we sterilize per-test:
    * It mkdir's ``ROOT/data/security/<TODAY>``.
    * It binds module-level constants to the real repo paths.

We load the module via ``importlib.util.spec_from_file_location`` with
``ROOT`` and ``OUTPUT_DIR`` redirected to ``tmp_path``, and we mock every
subprocess call to keep the unit suite hermetic.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_PATH = REPO_ROOT / "services" / "security_pipeline" / "run.py"


def _load_run_module(tmp_path: Path):
    """Load services/security_pipeline/run.py with ROOT redirected to tmp_path."""
    fake_root = tmp_path / "fake_repo"
    fake_root.mkdir()
    (fake_root / "lib").mkdir()
    (fake_root / "services").mkdir()
    (fake_root / "plugins").mkdir()

    module_name = "sapphire_test_security_pipeline_run"
    spec = importlib.util.spec_from_file_location(module_name, RUN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    # Redirect module-level paths so subsequent calls write to tmp_path
    module.ROOT = fake_root
    module.OUTPUT_DIR = fake_root / "data" / "security" / "test-date"
    module.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    module.SCAN_DIRS = [
        fake_root / "lib",
        fake_root / "services",
        fake_root / "plugins",
    ]
    return module, fake_root


@pytest.fixture
def run_mod(tmp_path):
    module, root = _load_run_module(tmp_path)
    yield module, root
    sys.modules.pop("sapphire_test_security_pipeline_run", None)


# ---------------------------------------------------------------------------
# compute_score
# ---------------------------------------------------------------------------


def test_compute_score_perfect_returns_grade_a(run_mod):
    module, _ = run_mod
    assert module.compute_score(0, 0, 0) == {"score": 100, "grade": "A"}


def test_compute_score_grade_b_band(run_mod):
    """A single secret leak is -10, so grade B at 90 raw, push to 75-89 band."""
    module, _ = run_mod
    # 2 secrets (-20) -> 80 -> B
    assert module.compute_score(2, 0, 0) == {"score": 80, "grade": "B"}


def test_compute_score_grade_c_band(run_mod):
    module, _ = run_mod
    # 1 secret (-10) + 5 vulns (-25) = -35 -> 65 -> C
    result = module.compute_score(1, 5, 0)
    assert result["score"] == 65
    assert result["grade"] == "C"


def test_compute_score_grade_d_and_f_bands(run_mod):
    module, _ = run_mod
    # 4 secrets (-40 cap) + 6 vulns (-30 cap) + 10 threats (-20 cap) = -90 -> 10 -> F
    f_grade = module.compute_score(4, 6, 10)
    assert f_grade == {"score": 10, "grade": "F"}
    # 3 secrets (-30) + 3 vulns (-15) + 5 threats (-10) = -55 -> 45 -> D
    d_grade = module.compute_score(3, 3, 5)
    assert d_grade["score"] == 45
    assert d_grade["grade"] == "D"


def test_compute_score_secret_deduction_caps_at_40(run_mod):
    module, _ = run_mod
    # 100 secrets would naively be -1000, but the cap is -40
    capped = module.compute_score(100, 0, 0)
    assert capped["score"] == 60
    assert capped["grade"] == "C"


def test_compute_score_floor_is_zero(run_mod):
    """All categories saturate; final score floor is 0, never negative."""
    module, _ = run_mod
    # 50 + 50 + 50 -> -90 -> would clamp at 10 (caps), but bump up:
    # actually with caps secrets=-40, vulns=-30, threats=-20 = -90; 100-90=10
    # To force the floor, we need to push past caps which we can't with positive ints.
    # The floor is implicit (max(0, ...)) — verify it via the absolute worst case.
    worst = module.compute_score(1000, 1000, 1000)
    assert worst["score"] == 10
    assert worst["grade"] == "F"


def test_compute_score_grade_boundaries_are_inclusive(run_mod):
    """A=>=90, B=>=75, C=>=60, D=>=40, F<40."""
    module, _ = run_mod
    # exact boundary: 90 -> A
    assert module.compute_score(1, 0, 0)["grade"] == "A"  # 100-10=90
    # exact boundary: 75 -> B; need to land on 75 exactly: -25 = 1 secret + 3 vulns
    assert module.compute_score(1, 3, 0)["grade"] == "B"  # 100-10-15=75
    # 60 -> C: -40 = 4 secrets cap (-40)
    assert module.compute_score(4, 0, 0)["grade"] == "C"  # 100-40=60
    # 40 -> D: -60 = 4 secrets (-40) + 4 vulns (-20)
    assert module.compute_score(4, 4, 0)["grade"] == "D"  # 100-40-20=40


# ---------------------------------------------------------------------------
# scan_secrets
# ---------------------------------------------------------------------------


def test_scan_secrets_finds_aws_access_key(tmp_path, run_mod):
    module, root = run_mod
    target = root / "lib" / "leaky.py"
    target.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')

    findings = module.scan_secrets()

    aws = [f for f in findings if f["type"] == "AWS access key"]
    assert len(aws) == 1
    assert aws[0]["file"].replace("\\", "/") == "lib/leaky.py"


def test_scan_secrets_finds_multiple_secret_types(run_mod):
    module, root = run_mod
    src = root / "services" / "leaky.py"
    src.write_text(
        'GH_TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"\n'
        'OPENAI = "sk-' + "a" * 48 + '"\n'
        'SLACK = "xoxb-1234567890-abcdefghijklmnop"\n'
    )

    findings = module.scan_secrets()
    types_found = {f["type"] for f in findings}

    assert "GitHub PAT" in types_found
    assert "OpenAI key" in types_found
    assert "Slack token" in types_found


def test_scan_secrets_skips_commented_lines(run_mod):
    """Comment-prefixed matches must not be flagged (false-positive guard)."""
    module, root = run_mod
    target = root / "plugins" / "annotated.py"
    target.write_text("# Example: AKIAIOSFODNN7EXAMPLE\nx = 1\n")

    findings = module.scan_secrets()

    assert findings == []


def test_scan_secrets_only_reads_python_files(run_mod):
    """Non-.py files are ignored even if they contain matching patterns."""
    module, root = run_mod
    md = root / "lib" / "README.md"
    md.write_text("Sample: AKIAIOSFODNN7EXAMPLE\n")
    py = root / "lib" / "real.py"
    py.write_text('TOKEN = "AKIAIOSFODNN7EXAMPLE"\n')

    findings = module.scan_secrets()

    # only the .py finding should appear
    files = {f["file"] for f in findings}
    assert any(f.replace("\\", "/") == "lib/real.py" for f in files)
    assert all(not f.endswith(".md") for f in files)


def test_scan_secrets_skips_ignore_dirs(run_mod):
    """Findings inside .git, __pycache__, node_modules etc must be skipped."""
    module, root = run_mod
    cache_dir = root / "lib" / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "compiled.py").write_text('x = "AKIAIOSFODNN7EXAMPLE"\n')

    findings = module.scan_secrets()

    assert findings == []


def test_scan_secrets_handles_unreadable_file(run_mod, monkeypatch):
    """OSError on read should be swallowed and the scan should continue."""
    module, root = run_mod
    bad = root / "lib" / "bad.py"
    bad.write_text("ok\n")
    good = root / "lib" / "good.py"
    good.write_text('TOKEN = "AKIAIOSFODNN7EXAMPLE"\n')

    real_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self == bad:
            raise OSError("simulated read failure")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    findings = module.scan_secrets()

    files = {f["file"] for f in findings}
    assert any(f.replace("\\", "/") == "lib/good.py" for f in files)
    assert "lib/bad.py" not in files


def test_scan_secrets_returns_empty_when_scan_dirs_missing(run_mod):
    """Non-existent SCAN_DIRS entries should be skipped silently."""
    module, _ = run_mod
    module.SCAN_DIRS = [Path("/nonexistent-dir-that-should-not-exist-12345")]

    findings = module.scan_secrets()

    assert findings == []


def test_scan_secrets_finding_shape(run_mod):
    """Each finding must include file, type, and line_preview keys."""
    module, root = run_mod
    src = root / "lib" / "x.py"
    src.write_text('TOKEN = "AKIAIOSFODNN7EXAMPLE"\n')

    findings = module.scan_secrets()

    assert len(findings) == 1
    f = findings[0]
    assert set(f.keys()) == {"file", "type", "line_preview"}
    assert f["line_preview"].endswith("...")


# ---------------------------------------------------------------------------
# scan_dependencies
# ---------------------------------------------------------------------------


def test_scan_dependencies_returns_ok_when_no_vulns(run_mod, monkeypatch):
    module, _ = run_mod

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=json.dumps({"dependencies": []}), stderr="", returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.scan_dependencies()

    assert result == {"python": [], "status": "ok"}


def test_scan_dependencies_marks_vulnerable_when_findings(run_mod, monkeypatch):
    module, _ = run_mod
    deps = [{"name": "requests", "version": "1.0", "vulns": [{"id": "PYSEC-2025-1"}]}]

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=json.dumps({"dependencies": deps}), stderr="", returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.scan_dependencies()

    assert result["status"] == "vulnerable"
    assert result["python"] == deps


def test_scan_dependencies_handles_pip_audit_missing(run_mod, monkeypatch):
    module, _ = run_mod

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("pip_audit not installed")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.scan_dependencies()

    assert result == {"python": [], "status": "pip-audit not installed"}


def test_scan_dependencies_handles_subprocess_error(run_mod, monkeypatch):
    module, _ = run_mod

    def fake_run(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.scan_dependencies()

    assert result["python"] == []
    assert result["status"].startswith("error: ")
    assert "boom" in result["status"]


def test_scan_dependencies_handles_empty_stdout(run_mod, monkeypatch):
    module, _ = run_mod

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.scan_dependencies()

    # Empty stdout shouldn't raise; status stays at "ok" with no findings.
    assert result == {"python": [], "status": "ok"}


# ---------------------------------------------------------------------------
# refresh_threat_intel
# ---------------------------------------------------------------------------


def test_refresh_threat_intel_returns_tool_not_found_when_missing(run_mod):
    """If the threat_intel.py tool is absent under the redirected ROOT,
    refresh should report the missing-tool status without calling subprocess."""
    module, _ = run_mod

    result = module.refresh_threat_intel()

    assert result == {"status": "tool not found"}


def test_refresh_threat_intel_parses_subprocess_json(run_mod, monkeypatch):
    module, root = run_mod
    tool_path = root / "plugins" / "claw-sapphire" / "tools" / "threat_intel.py"
    tool_path.parent.mkdir(parents=True, exist_ok=True)
    tool_path.write_text("# placeholder")

    captured: dict[str, Any] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(stdout=json.dumps({"total": 7, "high": 2}), returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.refresh_threat_intel()

    assert result == {"total": 7, "high": 2}
    assert captured["cmd"][1] == str(tool_path)
    assert json.loads(captured["input"]) == {"action": "latest"}


def test_refresh_threat_intel_handles_empty_stdout(run_mod, monkeypatch):
    module, root = run_mod
    tool_path = root / "plugins" / "claw-sapphire" / "tools" / "threat_intel.py"
    tool_path.parent.mkdir(parents=True, exist_ok=True)
    tool_path.write_text("# placeholder")

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="   \n", returncode=0),
    )

    result = module.refresh_threat_intel()

    assert result == {"status": "empty response"}


def test_refresh_threat_intel_handles_subprocess_exception(run_mod, monkeypatch):
    module, root = run_mod
    tool_path = root / "plugins" / "claw-sapphire" / "tools" / "threat_intel.py"
    tool_path.parent.mkdir(parents=True, exist_ok=True)
    tool_path.write_text("# placeholder")

    def fake_run(*a, **k):
        raise TimeoutError("threat tool timed out")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.refresh_threat_intel()

    assert result["status"].startswith("error: ")
    assert "timed out" in result["status"]


# ---------------------------------------------------------------------------
# main — orchestrator
# ---------------------------------------------------------------------------


def test_main_writes_pipeline_json_with_expected_shape(run_mod, monkeypatch):
    module, root = run_mod

    monkeypatch.setattr(
        module,
        "scan_secrets",
        lambda: [{"file": "lib/x.py", "type": "GitHub PAT", "line_preview": "..."}],
    )
    monkeypatch.setattr(
        module,
        "scan_dependencies",
        lambda: {"python": [{"name": "requests"}], "status": "vulnerable"},
    )
    monkeypatch.setattr(module, "refresh_threat_intel", lambda: {"total": 4})

    # No event bus / Telegram in-process; let the try/except absorb any import error.
    rc = module.main()

    assert rc == 0
    out_path = module.OUTPUT_DIR / "pipeline.json"
    assert out_path.exists()
    report = json.loads(out_path.read_text(encoding="utf-8"))

    assert report["date"] == module.TODAY
    assert "timestamp" in report
    assert report["secrets"]["count"] == 1
    assert report["secrets"]["findings"][0]["file"] == "lib/x.py"
    assert report["dependencies"]["status"] == "vulnerable"
    assert report["threats"]["count"] == 4
    # 1 secret (-10) + 1 vuln (-5) + 4 threats (-8) = -23 -> 77 -> B
    assert report["posture"] == {"score": 77, "grade": "B"}


def test_main_truncates_findings_to_first_twenty(run_mod, monkeypatch):
    module, _ = run_mod

    huge_findings = [
        {"file": f"lib/f{i}.py", "type": "API key", "line_preview": "..."} for i in range(50)
    ]
    monkeypatch.setattr(module, "scan_secrets", lambda: huge_findings)
    monkeypatch.setattr(module, "scan_dependencies", lambda: {"python": [], "status": "ok"})
    monkeypatch.setattr(module, "refresh_threat_intel", lambda: {})

    module.main()
    report = json.loads((module.OUTPUT_DIR / "pipeline.json").read_text(encoding="utf-8"))

    assert report["secrets"]["count"] == 50
    assert len(report["secrets"]["findings"]) == 20


def test_main_handles_missing_total_in_threat_response(run_mod, monkeypatch):
    """refresh_threat_intel may return {"status": "..."} without a "total" key."""
    module, _ = run_mod

    monkeypatch.setattr(module, "scan_secrets", lambda: [])
    monkeypatch.setattr(module, "scan_dependencies", lambda: {"python": [], "status": "ok"})
    monkeypatch.setattr(module, "refresh_threat_intel", lambda: {"status": "tool not found"})

    rc = module.main()
    report = json.loads((module.OUTPUT_DIR / "pipeline.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert report["threats"]["count"] == 0
    assert report["posture"]["grade"] == "A"


def test_main_publishes_event_when_bus_available(run_mod, monkeypatch):
    module, _ = run_mod

    monkeypatch.setattr(module, "scan_secrets", lambda: [])
    monkeypatch.setattr(module, "scan_dependencies", lambda: {"python": [], "status": "ok"})
    monkeypatch.setattr(module, "refresh_threat_intel", lambda: {})

    captured: dict[str, Any] = {}

    class _FakeBus:
        def publish(self, topic, payload, source):
            captured["topic"] = topic
            captured["payload"] = payload
            captured["source"] = source

    fake_bus_module = SimpleNamespace(get_bus=lambda: _FakeBus())
    monkeypatch.setitem(sys.modules, "lib.core.event_bus", fake_bus_module)

    module.main()

    assert captured["topic"] == "security.pipeline.completed"
    assert captured["source"] == "security-pipeline"
    assert captured["payload"]["date"] == module.TODAY
    assert captured["payload"]["secrets_found"] == 0
    assert captured["payload"]["vulnerabilities"] == 0
    assert "posture" in captured["payload"]


def test_main_swallows_event_publish_failure(run_mod, monkeypatch):
    module, _ = run_mod

    monkeypatch.setattr(module, "scan_secrets", lambda: [])
    monkeypatch.setattr(module, "scan_dependencies", lambda: {"python": [], "status": "ok"})
    monkeypatch.setattr(module, "refresh_threat_intel", lambda: {})

    class _BrokenBus:
        def publish(self, *a, **k):
            raise RuntimeError("redis dead")

    fake_bus_module = SimpleNamespace(get_bus=lambda: _BrokenBus())
    monkeypatch.setitem(sys.modules, "lib.core.event_bus", fake_bus_module)

    rc = module.main()

    # Failure during event publish must not crash the pipeline.
    assert rc == 0
    assert (module.OUTPUT_DIR / "pipeline.json").exists()


def test_main_sends_telegram_alert_when_secrets_found(run_mod, monkeypatch):
    module, root = run_mod

    monkeypatch.setattr(
        module,
        "scan_secrets",
        lambda: [{"file": "lib/x.py", "type": "AWS access key", "line_preview": "..."}],
    )
    monkeypatch.setattr(module, "scan_dependencies", lambda: {"python": [], "status": "ok"})
    monkeypatch.setattr(module, "refresh_threat_intel", lambda: {})

    notify_path = root / "plugins" / "claw-sapphire" / "tools" / "notify.py"
    notify_path.parent.mkdir(parents=True, exist_ok=True)
    notify_path.write_text("# placeholder")

    captured: dict[str, Any] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main()

    assert rc == 0
    assert captured["cmd"][1] == str(notify_path)
    payload = json.loads(captured["input"])
    assert payload["priority"] == "p1"
    assert "Security Pipeline" in payload["message"]


def test_main_does_not_alert_when_grade_is_passing_and_no_secrets(run_mod, monkeypatch):
    module, root = run_mod

    monkeypatch.setattr(module, "scan_secrets", lambda: [])
    monkeypatch.setattr(module, "scan_dependencies", lambda: {"python": [], "status": "ok"})
    monkeypatch.setattr(module, "refresh_threat_intel", lambda: {})

    # No-op subprocess; if main calls it for notify we'll spot it via the flag.
    called: dict[str, Any] = {"count": 0}

    def fake_run(cmd, **kwargs):
        called["count"] += 1
        called["last_cmd"] = cmd
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main()

    assert rc == 0
    # subprocess should not have been called for notify.py (grade is A, no secrets).
    notify_calls = [
        c for c in [called.get("last_cmd")] if c and any("notify.py" in str(p) for p in c)
    ]
    assert notify_calls == []
