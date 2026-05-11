from __future__ import annotations

from scripts.ops import fresh_agent_runtime_status as status


def test_missing_models_uses_exact_tag_match() -> None:
    installed = ["gemma4:latest", "qwen3.6:27b"]

    assert status.missing_models(["gemma4:latest", "qwen3.6:27b"], installed) == []
    assert status.missing_models(["gemma4:26b"], installed) == ["gemma4:26b"]


def test_overall_status_prefers_fail_then_warn() -> None:
    assert status.overall_status(["ok", "warn"]) == "warn"
    assert status.overall_status(["ok", "fail", "warn"]) == "fail"
    assert status.overall_status(["ok"]) == "ok"


def test_collect_report_flags_loaded_deprecated_launchagent(monkeypatch) -> None:
    profile = status.load_runtime_profile()

    monkeypatch.setattr(status, "list_ollama_models", lambda: ["gemma4:latest", "qwen3.6:27b"])
    monkeypatch.setattr(
        status,
        "check_deprecated_launchagents",
        lambda _labels, archive_dir=None: {
            "labels": ["ai.hermes.gateway"],
            "loaded": ["ai.hermes.gateway"],
            "disabled": [],
            "archived": [],
            "archive_dir": str(archive_dir) if archive_dir else None,
        },
    )
    monkeypatch.setattr(
        status,
        "check_harnesses",
        lambda _profile: {"google_adk_installed": True, "google_adk_configured": True},
    )
    monkeypatch.setattr(status, "load_runtime_profile", lambda _path=None: profile)

    report = status.collect_report()

    assert report["status"] == "fail"
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["deprecated_launchagents_disabled"]["status"] == "fail"
