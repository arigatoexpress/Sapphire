from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "windows_setup" / "run_research_worker.ps1"
INSTALLER = ROOT / "scripts" / "windows_setup" / "create_research_worker_task.ps1"


def test_research_worker_runs_paper_only_backtest_and_walkforward() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert "paper_only = $true" in script
    assert "live_trading_enabled = $false" in script
    assert "telegram_sends_enabled = $false" in script
    assert "lib.analytics.run_strategies" in script
    assert "--output-dir" in script
    assert "services.walkforward.build" in script
    assert "--bars-source" in script
    assert '"synthetic"' in script
    assert "$ErrorActionPreference = \"Continue\"" in script
    assert "$exitCode = $LASTEXITCODE" in script
    assert "Out-File -FilePath $LogPath" in script
    assert "Start-ScheduledTask" not in script


def test_research_worker_installer_registers_but_does_not_start_task() -> None:
    script = INSTALLER.read_text(encoding="utf-8")
    executable_lines = [
        line.strip()
        for line in script.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert "$TaskName = \"SapphireResearchWorker\"" in script
    assert "Register-ScheduledTask" in script
    assert "run_research_worker.ps1" in script
    assert "Start-ScheduledTask -TaskName $TaskName" in script
    assert not any(line.startswith("Start-ScheduledTask") for line in executable_lines)
    assert "has not been started" in script
