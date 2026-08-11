"""Tests for the production readiness sweep."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "production_readiness_sweep.py"

SPEC = importlib.util.spec_from_file_location("production_readiness_sweep", SCRIPT)
assert SPEC and SPEC.loader
sweep = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sweep
SPEC.loader.exec_module(sweep)


def _safety_report_result(inferred_active: bool | None, source: str) -> sweep.RunResult:
    payload = {
        "kill_switch": {
            "inferred_active": inferred_active,
            "state_source": source,
            "state_confidence": "unknown" if inferred_active is None else "operator_observed",
        },
        "confirmation_firewall": {"expired_pending_count": 0},
        "autonomy_audit": {
            "schema": {
                "unredacted_secret_risk_records": 0,
            }
        },
    }
    return sweep.RunResult(0, json.dumps(payload), "", 1)


def test_probe_safety_fails_closed_when_kill_switch_state_is_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        sweep,
        "run",
        lambda *_args, **_kwargs: _safety_report_result(None, "audit_missing"),
    )

    check = next(item for item in sweep.probe_safety() if item.name == "kill_switch_inactive")

    assert check.status == "FAIL"
    assert "inferred_active=unknown" in check.evidence
    assert "source=audit_missing" in check.evidence


def test_probe_safety_passes_only_explicit_inactive_state(monkeypatch) -> None:
    monkeypatch.setattr(
        sweep,
        "run",
        lambda *_args, **_kwargs: _safety_report_result(False, "operator_baseline"),
    )

    check = next(item for item in sweep.probe_safety() if item.name == "kill_switch_inactive")

    assert check.status == "PASS"
    assert "inferred_active=false" in check.evidence


def test_probe_safety_rejects_inactive_value_without_bound_source(monkeypatch) -> None:
    monkeypatch.setattr(
        sweep,
        "run",
        lambda *_args, **_kwargs: _safety_report_result(False, "audit_missing"),
    )

    check = next(item for item in sweep.probe_safety() if item.name == "kill_switch_inactive")

    assert check.status == "FAIL"
    assert "source=audit_missing" in check.evidence


def test_parse_json_from_mixed_output_handles_cli_warnings() -> None:
    output = 'Warning: terminal\n{"response": "SAPPHIRE_GEMINI_PROBE_OK"}\n'

    assert sweep.parse_json_from_mixed_output(output) == {"response": "SAPPHIRE_GEMINI_PROBE_OK"}


def test_gemini_live_probe_uses_vertex_without_tools(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 20,
        env: dict[str, str] | None = None,
    ) -> sweep.RunResult:
        del cwd, timeout
        assert env is not None
        calls.append((cmd, env))
        return sweep.RunResult(
            0,
            """
            Warning: terminal
            {
              "response": "SAPPHIRE_GEMINI_PROBE_OK",
              "stats": {
                "models": {
                  "gemini-2.5-flash": {
                    "tokens": {"total": 42}
                  }
                },
                "tools": {"totalCalls": 0}
              }
            }
            """,
            "",
            123,
        )

    monkeypatch.setattr(sweep, "run", fake_run)

    checks = sweep.probe_gemini_live(
        argparse.Namespace(
            project="tho-ai-agent",
            region="us-central1",
            gemini_model="gemini-2.5-flash",
        )
    )

    assert checks[0].status == "PASS"
    assert "total_tokens=42" in checks[0].evidence
    assert calls[0][0][:2] == ["gemini", "--skip-trust"]
    assert calls[0][1]["GOOGLE_GENAI_USE_VERTEXAI"] == "true"
    assert calls[0][1]["GOOGLE_CLOUD_PROJECT"] == "tho-ai-agent"


def test_gemini_probe_converts_google_manual_gate_to_pass() -> None:
    google_gate = sweep.Check(
        "gcp",
        "gate_gemini_api_or_vertex_live_calls",
        "WARN",
        "manual_gate",
    )
    probe = sweep.Check("gemini", "vertex_live_probe", "PASS", "model=gemini-2.5-flash")

    sweep.apply_gemini_probe_to_google_gate([google_gate, probe], [probe])

    assert google_gate.status == "PASS"
    assert "Vertex Gemini live probe succeeded" in google_gate.evidence


class _FakeHTTPResponse:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def read(self, _limit: int) -> bytes:
        return self._body


def test_http_check_fails_when_a_different_service_answers(monkeypatch) -> None:
    """The Open WebUI false-PASS regression guard.

    `com.sovereign.openwebui` squats :8080 and its /health returns
    `{"status": true}`. The sweep probed that port for `dashboard_health`, saw a
    200 with a truthy `status`, and reported the Sapphire dashboard healthy for
    months while it was not even running. An identity assertion is the fix: a
    health check must prove *which* service answered.
    """

    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(200, {"status": True})

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.http_check(
        "local",
        "dashboard_health",
        "http://127.0.0.1:8085/health",
        expect_json={"status": "healthy"},
    )

    assert check.status == "FAIL"
    assert "identity_mismatch" in check.evidence


def test_http_check_passes_on_matching_identity_with_extra_fields(monkeypatch) -> None:
    """Subset matching: a service adding fields must not break monitoring."""

    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(200, {"status": "healthy", "timestamp": "2026-07-25T15:15:47"})

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.http_check(
        "local",
        "dashboard_health",
        "http://127.0.0.1:8085/health",
        expect_json={"status": "healthy"},
    )

    assert check.status == "PASS"
    assert "identity_mismatch" not in check.evidence


def test_dashboard_probe_targets_the_port_the_dashboard_actually_binds(monkeypatch) -> None:
    """8080 is Open WebUI and 8082 is control-plane — neither is the dashboard."""
    urls: list[str] = []

    def fake_urlopen(request: object, timeout: int) -> _FakeHTTPResponse:
        urls.append(request.full_url if hasattr(request, "full_url") else str(request))
        return _FakeHTTPResponse(200, {"status": "healthy"})

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("SAPPHIRE_DASHBOARD_PORT", raising=False)

    sweep.probe_local_endpoints({})

    assert any("127.0.0.1:8085/health" in url for url in urls)
    assert not any("127.0.0.1:8080" in url for url in urls)


def test_inference_health_warns_on_degraded_tiers(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "ok",
                "endpoints": {
                    "windows-gpu": "healthy",
                    "pi-rari1": "failed",
                    "mac-local": "healthy",
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.inference_proxy_health_check()

    assert check.status == "WARN"
    assert "status=ok" in check.evidence
    assert "degraded_tiers=pi-rari1" in check.evidence


def test_inference_health_passes_when_all_tiers_healthy(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "ok",
                "endpoints": {
                    "windows-gpu": "healthy",
                    "mac-local": "healthy",
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.inference_proxy_health_check()

    assert check.status == "PASS"
    assert "degraded_tiers" not in check.evidence


def test_inference_health_ignores_disabled_tiers(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "ok",
                "endpoints": {
                    "windows-gpu": "healthy",
                    "pi-rari1": "disabled",
                    "pi-rari2": "disabled",
                    "mac-local": "healthy",
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.inference_proxy_health_check()

    assert check.status == "PASS"
    assert "disabled_tiers=pi-rari1,pi-rari2" in check.evidence
    assert "degraded_tiers" not in check.evidence


def test_scheduled_launchagent_nonzero_last_status_warns(monkeypatch) -> None:
    always_on = [
        "com.sapphire.dashboard",
        "com.sapphire.control-plane",
        "com.sapphire.signal-logger",
        "com.sapphire.inference-proxy",
        "com.sapphire.pm-bot",
        "com.sapphire.heartbeat",
        "com.sapphire.openbb-api",
        "com.sapphire.webhook-tunnel",
        "actions.runner.arigatoexpress-Sapphire.ari-macbook-sapphire",
    ]
    scheduled = [
        ("com.sapphire.gcp-sync", "1"),
        ("com.sapphire.content-engine", "0"),
        ("com.sapphire.threat-refresh", "0"),
        ("com.sapphire.morning-brief", "0"),
        ("com.sapphire.backtest-weekly", "0"),
        ("com.sapphire.security-pipeline", "0"),
        ("com.sapphire.telemetry-collector", "0"),
        ("com.sapphire.foundry-sync", "0"),
        ("com.sapphire.tradingview-cdp", "0"),
    ]
    stdout = "\n".join(
        [f"123\t0\t{label}" for label in always_on]
        + [f"-\t{status}\t{label}" for label, status in scheduled]
    )

    monkeypatch.setattr(sweep, "run", lambda _cmd: sweep.RunResult(0, stdout, "", 12))

    checks = {check.name: check for check in sweep.probe_launchagents()}

    assert checks["com.sapphire.gcp-sync"].status == "WARN"
    assert "last_status=1" in checks["com.sapphire.gcp-sync"].evidence
    assert checks["com.sapphire.content-engine"].status == "PASS"


def test_windows_ollama_inventory_passes_with_required_models(monkeypatch) -> None:
    names = [
        "gemma3:4b",
        "qwen2.5-coder:14b",
        "deepseek-r1:14b",
        "qwen3.5:4b",
        "qwen3:14b",
        "qwen3.6:35b-a3b",
        "qwen3-coder:30b",
    ]

    def fake_urlopen(request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        assert str(request).endswith("/api/tags")
        return _FakeHTTPResponse(200, {"models": [{"name": name} for name in names]})

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_ollama_inventory_check("http://100.x.x.z:11434")

    assert check.status == "PASS"
    assert "models=7" in check.evidence
    assert "required_models_present=8/8" in check.evidence
    assert "missing_model_targets" not in check.evidence


def test_windows_ollama_inventory_warns_on_missing_aliases(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "models": [
                    {"name": "nemotron-mini:4b"},
                    {"name": "hermes3:8b"},
                ]
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_ollama_inventory_check("http://100.x.x.z:11434")

    assert check.status == "WARN"
    assert "required_models_present=0/8" in check.evidence
    assert "missing_model_targets" in check.evidence
    assert "reason" in check.evidence


def test_tcp_check_can_warn_for_optional_desktop_ports(monkeypatch) -> None:
    def fake_create_connection(_address: tuple[str, int], timeout: int) -> object:
        assert timeout == 3
        raise OSError("down")

    monkeypatch.setattr(sweep.socket, "create_connection", fake_create_connection)

    check = sweep.tcp_check(
        "windows", "telemetry_dashboard_tcp", "100.x.x.z", 3001, warn_on_error=True
    )

    assert check.status == "WARN"


def test_windows_probe_timeouts_are_env_tunable(monkeypatch) -> None:
    timeouts: list[float] = []

    def fake_urlopen(_request: object, timeout: float) -> _FakeHTTPResponse:
        timeouts.append(timeout)
        raise OSError("down")

    monkeypatch.setenv("SAPPHIRE_WINDOWS_HTTP_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_ollama_inventory_check("http://100.x.x.z:11434")

    assert check.status == "WARN"
    assert timeouts == [1.5]


def test_windows_webhook_health_surfaces_degraded_subservices(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "healthy",
                "services": {
                    "windows_webhook": {"healthy": True},
                    "windows_ollama": {"healthy": True},
                    "windows_tv_agent": {"healthy": False, "status": "broken"},
                },
                "capabilities": {"ollama_model_count": 29, "gpu_count": 1},
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_webhook_health_check("100.x.x.z")

    assert check.status == "WARN"
    assert "status=healthy" in check.evidence
    assert "degraded_services=windows_tv_agent" in check.evidence
    assert "ollama_model_count=29" in check.evidence
    assert "gpu_count=1" in check.evidence


def test_windows_webhook_health_treats_agent_only_as_pass(monkeypatch) -> None:
    """`agent_only` (process up, optional CDP unreachable) is informational, not degraded."""

    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(
            200,
            {
                "status": "healthy",
                "services": {
                    "windows_webhook": {"healthy": True, "status": "active"},
                    "windows_ollama": {"healthy": True},
                    "windows_tv_agent": {"healthy": False, "status": "agent_only"},
                },
                "capabilities": {"ollama_model_count": 29, "gpu_count": 1},
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_webhook_health_check("100.x.x.z")

    assert check.status == "PASS"
    assert "agent_only_services=windows_tv_agent" in check.evidence
    assert "degraded_services" not in check.evidence


def test_windows_tv_agent_cdp_status_passes_when_cdp_is_healthy(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "ok",
                "cdp": {
                    "healthy": True,
                    "status": "ready",
                    "latency_ms": 41,
                    "tab_count": 3,
                    "tradingview_tab_count": 1,
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_tv_agent_cdp_check("100.x.x.z")

    assert check.status == "PASS"
    assert "cdp=ready" in check.evidence
    assert "tradingview_tab_count=1" in check.evidence


def test_windows_tv_agent_cdp_status_warns_when_cdp_is_agent_only(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "agent_only",
                "cdp": {
                    "healthy": False,
                    "status": "unreachable",
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_tv_agent_cdp_check("100.x.x.z")

    assert check.status == "WARN"
    assert "status=agent_only" in check.evidence
    assert "cdp=unreachable" in check.evidence


def test_windows_scheduled_tasks_pass_when_expected_tasks_are_ready_or_running(
    monkeypatch,
) -> None:
    payload = [
        {"TaskName": name, "State": next(iter(states)), "LastTaskResult": 0}
        for name, states in sweep.WINDOWS_EXPECTED_TASK_STATES.items()
    ]

    def fake_windows_powershell_json(
        host: str, script: str, *, timeout: int | None = None
    ) -> sweep.RunResult:
        del timeout
        assert host == "100.x.x.z"
        assert "Get-ScheduledTask" in script
        assert "SapphireTradingViewCDP" in script
        return sweep.RunResult(0, json.dumps(payload), "", 25)

    monkeypatch.setattr(sweep, "windows_powershell_json", fake_windows_powershell_json)

    check = sweep.windows_scheduled_tasks_check("100.x.x.z")

    assert check.status == "PASS"
    assert "checked=6" in check.evidence
    assert "states=ok" in check.evidence


def test_windows_scheduled_tasks_warn_when_expected_task_is_missing(monkeypatch) -> None:
    payload = [
        {"TaskName": "SapphireDashboard", "State": "Running", "LastTaskResult": 0},
        {"TaskName": "SapphireTradingViewCDP", "State": "Missing", "LastTaskResult": None},
    ]

    monkeypatch.setattr(
        sweep,
        "windows_powershell_json",
        lambda _host, _script, timeout=None: sweep.RunResult(0, json.dumps(payload), "", 25),
    )

    check = sweep.windows_scheduled_tasks_check("100.x.x.z")

    assert check.status == "WARN"
    assert "missing=Sapphire-TV-Agent" in check.evidence
    assert "SapphireTradingViewCDP" in check.evidence


def test_windows_power_availability_passes_with_never_sleep_readback(monkeypatch) -> None:
    zero_power = """
    Current AC Power Setting Index: 0x00000000
    Current DC Power Setting Index: 0x00000000
    """
    payload = {
        "sleep": zero_power,
        "display": zero_power,
        "screen_save_active": "ScreenSaveActive    REG_SZ    0",
        "screen_saver_secure": "ScreenSaverIsSecure    REG_SZ    0",
        "screen_save_timeout": "ScreenSaveTimeOut    REG_SZ    0",
        "inactivity_timeout": "InactivityTimeoutSecs    REG_DWORD    0x0",
    }

    monkeypatch.setattr(
        sweep,
        "windows_powershell_json",
        lambda _host, _script, timeout=None: sweep.RunResult(0, json.dumps(payload), "", 19),
    )

    check = sweep.windows_power_availability_check("100.x.x.z")

    assert check.status == "PASS"
    assert "sleep=never" in check.evidence
    assert "inactivity_timeout=0" in check.evidence


def test_windows_power_availability_warns_on_lock_or_sleep_readback(monkeypatch) -> None:
    nonzero_power = """
    Current AC Power Setting Index: 0x00000384
    Current DC Power Setting Index: 0x00000384
    """
    payload = {
        "sleep": nonzero_power,
        "display": nonzero_power,
        "screen_save_active": "ScreenSaveActive    REG_SZ    1",
        "screen_saver_secure": "ScreenSaverIsSecure    REG_SZ    1",
        "screen_save_timeout": "ScreenSaveTimeOut    REG_SZ    600",
        "inactivity_timeout": "InactivityTimeoutSecs    REG_DWORD    0x384",
    }

    monkeypatch.setattr(
        sweep,
        "windows_powershell_json",
        lambda _host, _script, timeout=None: sweep.RunResult(0, json.dumps(payload), "", 19),
    )

    check = sweep.windows_power_availability_check("100.x.x.z")

    assert check.status == "WARN"
    assert "sleep_timeout" in check.evidence
    assert "screensaver_timeout" in check.evidence


def test_windows_research_worker_passes_with_fresh_safe_manifest(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "ok",
                "run_id": "20260429T215406Z",
                "git_sha_short": "edff5a8b",
                "freshness": {"age_seconds": 120, "max_age_seconds": 129600, "fresh": True},
                "summary": {"failed_count": 0, "safety_clear": True},
                "safety": {
                    "paper_only": True,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                },
                "schedule": {
                    "status": "ok",
                    "last_task_result_label": "not_started",
                    "last_result_ok": True,
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_research_worker_check("100.x.x.z")

    assert check.status == "PASS"
    assert "run_id=20260429T215406Z" in check.evidence
    assert "age_seconds=120" in check.evidence
    assert "task=ok/not_started" in check.evidence


def test_windows_research_worker_warns_on_stale_manifest(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "stale",
                "run_id": "20260429T215406Z",
                "freshness": {
                    "age_seconds": sweep.WINDOWS_RESEARCH_WORKER_MAX_AGE_SECONDS + 1,
                    "max_age_seconds": sweep.WINDOWS_RESEARCH_WORKER_MAX_AGE_SECONDS,
                    "fresh": False,
                },
                "summary": {"failed_count": 0, "safety_clear": True},
                "safety": {
                    "paper_only": True,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                },
                "schedule": {
                    "status": "ok",
                    "last_task_result_label": "success",
                    "last_result_ok": True,
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_research_worker_check("100.x.x.z")

    assert check.status == "WARN"
    assert "manifest_stale" in check.evidence


def test_windows_research_worker_warns_on_failed_task_result(monkeypatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> _FakeHTTPResponse:
        assert timeout == 5
        return _FakeHTTPResponse(
            200,
            {
                "status": "ok",
                "freshness": {"age_seconds": 120, "fresh": True},
                "summary": {"failed_count": 0, "safety_clear": True},
                "safety": {
                    "paper_only": True,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                },
                "schedule": {
                    "status": "ok",
                    "last_task_result_label": "code_1",
                    "last_result_ok": False,
                },
            },
        )

    monkeypatch.setattr(sweep.urllib.request, "urlopen", fake_urlopen)

    check = sweep.windows_research_worker_check("100.x.x.z")

    assert check.status == "WARN"
    assert "task_result=code_1" in check.evidence


def test_satellite_ci_no_spend_gates_pass_for_gated_workflows(tmp_path: Path) -> None:
    repo = tmp_path / "satellite"
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        """
jobs:
  test:
    if: ${{ vars.SAPPHIRE_RUNNER != '' }}
    runs-on: ${{ fromJSON(vars.SAPPHIRE_RUNNER || '"ubuntu-latest"') }}
    steps:
      - run: echo ok
""",
        encoding="utf-8",
    )
    manifest = tmp_path / "org-repos.yaml"
    manifest.write_text(
        f"""
repos:
  - id: satellite
    local_path: {repo}
    ci_strategy: local_evidence_skip_ci_bootstrap
  - id: project-go-forward
    local_path: /does/not/matter
    ci_strategy: draft_auto_deploy
""",
        encoding="utf-8",
    )

    check = sweep.probe_satellite_ci_no_spend_gates(manifest)

    assert check.status == "PASS"
    assert "checked_repos=1" in check.evidence
    assert "exceptions=project-go-forward:draft_auto_deploy" in check.evidence


def test_satellite_ci_no_spend_gates_fail_for_ungated_jobs(tmp_path: Path) -> None:
    repo = tmp_path / "satellite"
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        """
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo paid
""",
        encoding="utf-8",
    )
    manifest = tmp_path / "org-repos.yaml"
    manifest.write_text(
        f"""
repos:
  - id: satellite
    local_path: {repo}
    ci_strategy: local_evidence_skip_ci_bootstrap
""",
        encoding="utf-8",
    )

    check = sweep.probe_satellite_ci_no_spend_gates(manifest)

    assert check.status == "FAIL"
    assert "violations=satellite:ci.yml:test" in check.evidence


def test_satellite_ci_no_spend_gates_accepts_explicit_self_hosted_labels(
    tmp_path: Path,
) -> None:
    """A self-hosted runner bills nothing, so it needs no SAPPHIRE_RUNNER gate.

    Regression guard for the real `win-runner-smoke.yml` FAIL: the job pins
    `runs-on: [self-hosted, Windows, X64, sapphire-win]` — free by construction —
    but the check only recognised the `vars.SAPPHIRE_RUNNER` idiom.
    """
    repo = tmp_path / "satellite"
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "smoke.yml").write_text(
        """
jobs:
  smoke:
    runs-on: [self-hosted, Windows, X64, sapphire-win]
    steps:
      - run: echo free
""",
        encoding="utf-8",
    )
    manifest = tmp_path / "org-repos.yaml"
    manifest.write_text(
        f"""
repos:
  - id: satellite
    local_path: {repo}
    ci_strategy: local_evidence_skip_ci_bootstrap
""",
        encoding="utf-8",
    )

    check = sweep.probe_satellite_ci_no_spend_gates(manifest)

    assert check.status == "PASS"
    assert "violations" not in check.evidence


def test_runs_on_labels_normalises_every_spelling() -> None:
    assert sweep.runs_on_labels({"runs-on": "ubuntu-latest"}) == ["ubuntu-latest"]
    assert sweep.runs_on_labels({"runs-on": ["self-hosted", "X64"]}) == ["self-hosted", "X64"]
    assert sweep.runs_on_labels({"runs-on": {"group": "g", "labels": ["self-hosted"]}}) == [
        "self-hosted"
    ]
    assert sweep.runs_on_labels({}) == []


def test_satellite_merge_posture_reports_auto_merge_without_failing_hard_gates(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "satellite"
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        """
jobs:
  test:
    if: ${{ vars.SAPPHIRE_RUNNER != '' }}
    runs-on: ${{ fromJSON(vars.SAPPHIRE_RUNNER) }}
    steps:
      - run: echo ok
""",
        encoding="utf-8",
    )
    manifest = tmp_path / "org-repos.yaml"
    manifest.write_text(
        f"""
repos:
  - id: satellite
    local_path: {repo}
    github: arigatoexpress/satellite
    ci_strategy: local_evidence_skip_ci_bootstrap
""",
        encoding="utf-8",
    )

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 20,
        env: dict[str, str] | None = None,
    ) -> sweep.RunResult:
        del cwd, timeout, env
        assert cmd[:3] == ["gh", "api", "repos/arigatoexpress/satellite"]
        return sweep.RunResult(
            0,
            json.dumps(
                {
                    "allow_auto_merge": False,
                    "allow_squash_merge": True,
                    "delete_branch_on_merge": True,
                }
            ),
            "",
            7,
        )

    monkeypatch.setattr(sweep, "run", fake_run)

    check = sweep.probe_satellite_merge_posture(no_external=False, manifest_path=manifest)

    assert check.status == "WARN"
    assert "auto_merge_false=satellite" in check.evidence
    assert "satellite(auto=false,squash=true,delete=true,runner_gate=pass)" in check.evidence


def test_satellite_merge_posture_does_not_fail_on_uncloned_repos(
    tmp_path: Path, monkeypatch
) -> None:
    """Absence of a local clone is absence of evidence, not a violation.

    Most of the old arigatoexpress fleet is archived and deliberately not cloned
    on this Mac. Counting `runner_gate=missing_local` as critical pinned this
    check to FAIL permanently and buried the one genuine violation.
    """
    manifest = tmp_path / "org-repos.yaml"
    manifest.write_text(
        """
repos:
  - id: archived-satellite
    local_path: /definitely/not/cloned
    github: arigatoexpress/archived-satellite
    ci_strategy: local_evidence_skip_ci_bootstrap
""",
        encoding="utf-8",
    )

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 20,
        env: dict[str, str] | None = None,
    ) -> sweep.RunResult:
        del cmd, cwd, timeout, env
        return sweep.RunResult(
            0,
            json.dumps(
                {
                    "allow_auto_merge": True,
                    "allow_squash_merge": True,
                    "delete_branch_on_merge": True,
                }
            ),
            "",
            7,
        )

    monkeypatch.setattr(sweep, "run", fake_run)

    check = sweep.probe_satellite_merge_posture(no_external=False, manifest_path=manifest)

    assert check.status == "WARN"
    assert "runner_gate_unevaluated=archived-satellite" in check.evidence
    assert "violations" not in check.evidence


def test_satellite_merge_posture_fails_for_missing_delete_branch_or_runner_gate(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "satellite"
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        """
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo paid
""",
        encoding="utf-8",
    )
    manifest = tmp_path / "org-repos.yaml"
    manifest.write_text(
        f"""
repos:
  - id: satellite
    local_path: {repo}
    github: arigatoexpress/satellite
    ci_strategy: local_evidence_skip_ci_bootstrap
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sweep,
        "github_repo_merge_settings",
        lambda _repo: {
            "allow_auto_merge": True,
            "allow_squash_merge": True,
            "delete_branch_on_merge": False,
        },
    )

    check = sweep.probe_satellite_merge_posture(no_external=False, manifest_path=manifest)

    assert check.status == "FAIL"
    assert "satellite:delete_branch_on_merge=false" in check.evidence
    assert "satellite:runner_gate=fail:1" in check.evidence


def test_satellite_merge_posture_skips_external_calls_when_disabled(tmp_path: Path) -> None:
    manifest = tmp_path / "org-repos.yaml"
    manifest.write_text("repos: []\n", encoding="utf-8")

    check = sweep.probe_satellite_merge_posture(no_external=True, manifest_path=manifest)

    assert check.status == "SKIP"
    assert check.evidence == "--no-external"
