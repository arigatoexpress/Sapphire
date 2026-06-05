"""Guardrails for version-controlled LaunchAgent definitions."""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

from services.pipeline import check_routines

ROOT = Path(__file__).resolve().parents[2]
INFRA_LAUNCHAGENTS = ROOT / "infra" / "launchagents"
SERVICE_LAUNCHAGENT_DIRS = tuple((ROOT / "services").glob("*/launchagent"))
SENSITIVE_ENV_RE = re.compile(r"(TOKEN|SECRET|PASSWORD|PIN|BEARER|_KEY|KEY_)", re.I)
SANITIZED_ENV_NAMES = {
    "AUTH_PASSWORD",
    "RELAY_READER_TOKEN",
    "OPENROUTER_API_KEY",
    "KIMI_RELAY_CHAT_ID",
}


def _plist_paths() -> list[Path]:
    paths = list(INFRA_LAUNCHAGENTS.glob("*.plist"))
    for directory in SERVICE_LAUNCHAGENT_DIRS:
        paths.extend(directory.glob("*.plist"))
    return sorted(paths)


def _load_plist(path: Path) -> dict:
    with path.open("rb") as handle:
        return plistlib.load(handle)


def test_launchagent_plists_parse_and_have_unique_labels() -> None:
    labels: dict[str, Path] = {}

    for path in _plist_paths():
        plist = _load_plist(path)
        label = plist.get("Label")
        assert label, f"{path} is missing Label"
        assert label not in labels, f"{path} duplicates {label} from {labels[label]}"
        labels[label] = path


def test_launchagents_do_not_target_stale_worktrees() -> None:
    for path in _plist_paths():
        plist = _load_plist(path)
        working_directory = plist.get("WorkingDirectory")
        assert working_directory is None or "/Code/_worktrees/" not in working_directory, (
            f"{path} points WorkingDirectory at stale worktree {working_directory!r}"
        )


def test_daily_brief_has_one_versioned_launchagent() -> None:
    matches: list[tuple[str, Path]] = []
    for path in _plist_paths():
        plist = _load_plist(path)
        arguments = plist.get("ProgramArguments") or []
        if any(str(arg).endswith("services/intelligence/daily_brief.py") for arg in arguments):
            matches.append((plist.get("Label", ""), path))

    assert matches == [
        ("com.sapphire.morning-brief", INFRA_LAUNCHAGENTS / "com.sapphire.morning-brief.plist")
    ]


def test_routine_health_tracks_canonical_morning_brief() -> None:
    launchagents = {routine.launchagent for routine in check_routines.ROUTINES}
    routine_names = {routine.name for routine in check_routines.ROUTINES}

    assert "com.sapphire.morning-brief" in launchagents
    assert "morning-brief" in routine_names
    assert "com.sapphire.daily-brief" not in launchagents
    assert "daily-brief" not in routine_names


def test_routine_health_tracks_trading_shadow_controller() -> None:
    launchagents = {routine.launchagent for routine in check_routines.ROUTINES}
    routine_names = {routine.name for routine in check_routines.ROUTINES}

    assert "com.sapphire.trading-shadow-controller" in launchagents
    assert "trading-shadow-controller" in routine_names


def test_routine_health_tracks_pm_bot_not_hermes_gateway() -> None:
    launchagents = {routine.launchagent for routine in check_routines.ROUTINES}
    routine_names = {routine.name for routine in check_routines.ROUTINES}

    assert "com.sapphire.pm-bot" in launchagents
    assert "pm-bot" in routine_names
    assert "ai.hermes.gateway" not in launchagents
    assert "hermes-agent" not in routine_names


def test_continuous_intelligence_daily_launchagent_is_artifact_only() -> None:
    plist = _load_plist(INFRA_LAUNCHAGENTS / "com.sapphire.continuous-intelligence-daily.plist")
    env = plist["EnvironmentVariables"]
    arguments = plist["ProgramArguments"]
    launchagents = {routine.launchagent for routine in check_routines.ROUTINES}
    routine_names = {routine.name for routine in check_routines.ROUTINES}

    assert plist["Label"] == "com.sapphire.continuous-intelligence-daily"
    assert arguments == [
        "/usr/local/bin/python3",
        "-m",
        "lib.autonomy.continuous_intelligence_artifacts",
        "daily-packet",
        "--write",
    ]
    assert plist["WorkingDirectory"] == "/Users/aribs/Code/Sapphire"
    assert plist["StartCalendarInterval"] == {"Hour": 6, "Minute": 45}
    assert plist["RunAtLoad"] is False
    assert env["PYTHONPATH"] == "/Users/aribs/Code/Sapphire"
    assert "com.sapphire.continuous-intelligence-daily" in launchagents
    assert "continuous-intelligence-daily" in routine_names
    assert "--execute" not in arguments
    assert not any(key.startswith("ROBINHOOD") for key in env)


def test_content_publisher_keeps_telegram_summary_explicit() -> None:
    plist = _load_plist(INFRA_LAUNCHAGENTS / "com.sapphire.content-publisher.plist")
    env = plist["EnvironmentVariables"]

    assert env["SAPPHIRE_PUBLISH_LIVE"] == "0"
    assert env["SAPPHIRE_CONTENT_TELEGRAM_SUMMARY"] == "1"


def test_gemini_ooda_daily_launchagent_is_dry_run_only() -> None:
    plist = _load_plist(INFRA_LAUNCHAGENTS / "com.sapphire.gemini-ooda-daily.plist")
    env = plist["EnvironmentVariables"]

    assert plist["Label"] == "com.sapphire.gemini-ooda-daily"
    assert plist["ProgramArguments"] == [
        "/bin/zsh",
        "/Users/aribs/Code/Sapphire/scripts/ops/gemini_ooda_daily.sh",
    ]
    assert plist["WorkingDirectory"] == "/Users/aribs/Code/Sapphire"
    assert plist["StartCalendarInterval"] == {"Hour": 6, "Minute": 30}
    assert env["PYTHONPATH"] == "/Users/aribs/Code/Sapphire"
    assert env["SAPPHIRE_GEMINI_LIVE"] == "0"


def test_trading_shadow_controller_launchagent_is_paper_only() -> None:
    plist = _load_plist(INFRA_LAUNCHAGENTS / "com.sapphire.trading-shadow-controller.plist")
    env = plist["EnvironmentVariables"]
    arguments = plist["ProgramArguments"]

    assert plist["Label"] == "com.sapphire.trading-shadow-controller"
    assert arguments == [
        "/usr/local/bin/python3",
        "/Users/aribs/Code/Sapphire/scripts/ops/trading_shadow_controller.py",
        "--output",
        "--history",
    ]
    assert plist["WorkingDirectory"] == "/Users/aribs/Code/Sapphire"
    assert plist["StartInterval"] == 1800
    assert plist["RunAtLoad"] is True
    assert env["PYTHONPATH"] == "/Users/aribs/Code/Sapphire"
    assert "--execute" not in arguments
    assert not any(key.startswith("ROBINHOOD") for key in env)


def test_tradingview_pine_batch_global_args_precede_subcommand() -> None:
    plist = _load_plist(INFRA_LAUNCHAGENTS / "com.sapphire.tradingview-pine-batch.plist")
    arguments = plist["ProgramArguments"]

    assert plist["Label"] == "com.sapphire.tradingview-pine-batch"
    assert arguments[:4] == [
        "/opt/homebrew/bin/python3",
        "/Users/aribs/Code/Sapphire/scripts/ops/tradingview_ta_capture.py",
        "--out",
        "/Users/aribs/autonomy-status/logs/tradingview-pine-batch-latest.json",
    ]
    assert arguments[4:] == [
        "pine-generate-batch",
        "--offline",
        "--limit",
        "8",
        "--validate",
    ]
    assert arguments.index("--out") < arguments.index("pine-generate-batch")
    assert "--mutate" not in arguments


def test_dashboard_and_inference_proxy_plists_are_sanitized() -> None:
    expected = {
        ROOT / "services" / "dashboard" / "launchagent" / "com.sapphire.dashboard.plist": {
            "label": "com.sapphire.dashboard",
            "wrapper": "/Users/aribs/Code/Sapphire/services/dashboard/start.sh",
            "env": {"PATH", "PORT"},
        },
        ROOT
        / "services"
        / "inference-proxy"
        / "launchagent"
        / "com.sapphire.inference-proxy.plist": {
            "label": "com.sapphire.inference-proxy",
            "wrapper": "/Users/aribs/Code/Sapphire/services/inference-proxy/start.sh",
            "env": {"PI_RARI1_ENABLED", "PI_RARI2_ENABLED"},
        },
    }

    for path, expectation in expected.items():
        plist = _load_plist(path)
        env = plist.get("EnvironmentVariables") or {}
        arguments = plist.get("ProgramArguments") or []

        assert plist["Label"] == expectation["label"]
        assert arguments == ["/bin/bash", expectation["wrapper"]]
        assert set(env) == expectation["env"]
        assert not (SANITIZED_ENV_NAMES & set(env))
        for key in env:
            assert not SENSITIVE_ENV_RE.search(key), f"{path} embeds sensitive env key {key}"
