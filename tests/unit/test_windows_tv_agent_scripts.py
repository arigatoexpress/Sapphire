"""Static checks for Windows TV agent setup scripts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "scripts" / "windows_setup" / "start_tv_agent.ps1"
INSTALLER = ROOT / "scripts" / "windows_setup" / "create_tv_agent_task.ps1"
COMPAT = ROOT / "scripts" / "windows_setup" / "create_task_scheduler_job.ps1"
QUICK_START = ROOT / "scripts" / "windows_setup" / "quick_start_tv_agent.bat"
MANAGER = ROOT / "scripts" / "windows_setup" / "manage_sapphire_services.bat"


def test_tv_agent_launcher_is_repo_owned_and_read_only() -> None:
    script = STARTER.read_text(encoding="utf-8")

    assert "services.windows_tv_agent.server" in script
    assert '$env:SAPPHIRE_TV_AGENT_READ_ONLY = "1"' in script
    assert "Get-NetTCPConnection -LocalPort $Port -State Listen" in script
    assert "Start-ScheduledTask" not in script


def test_tv_agent_task_installer_registers_live_task_names_without_starting_by_default() -> None:
    script = INSTALLER.read_text(encoding="utf-8")

    assert '$TaskName = "Sapphire-TV-Agent"' in script
    assert '$LogonTaskName = "Sapphire-TV-Agent-Logon"' in script
    assert "start_tv_agent.ps1" in script
    assert "StartNow" in script
    assert "Start-ScheduledTask -TaskName $TaskName" in script


def test_legacy_scheduler_entrypoint_delegates_to_new_installer() -> None:
    script = COMPAT.read_text(encoding="utf-8")

    assert "create_tv_agent_task.ps1" in script
    assert "TradingViewAutonomousManager" not in script


def test_batch_helpers_no_longer_reference_removed_backend() -> None:
    combined = QUICK_START.read_text(encoding="utf-8") + MANAGER.read_text(encoding="utf-8")

    assert "start_tv_agent.ps1" in combined
    assert "services.windows_tv_agent.server" not in combined
    assert "TradingViewAutonomousManager" not in combined
