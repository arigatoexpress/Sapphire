"""Contracts for the manually started Windows WSL lifetime anchor."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ANCHOR = ROOT / "deploy" / "megaeth-ingest-wsl" / "register-observer-anchor.ps1"


def test_anchor_is_manual_triggerless_and_has_no_restart_path() -> None:
    script = ANCHOR.read_text()

    required = (
        "[switch]$Start",
        '$taskName = "Sapphire-MegaETH-Observer-Anchor"',
        '$distribution = "Ubuntu-24.04"',
        "sudo --non-interactive systemctl start sapphire-megaeth-ingest.service",
        "while sudo --non-interactive systemctl is-active --quiet ",
        "sapphire-megaeth-ingest.service; do /bin/sleep 30; done",
        "New-ScheduledTaskAction",
        "New-ScheduledTaskSettingsSet",
        "-MultipleInstances IgnoreNew",
        "New-ScheduledTaskPrincipal",
        "-LogonType Interactive",
        "-RunLevel Limited",
        "Register-ScheduledTask",
        "if ($Start)",
        "Start-ScheduledTask",
    )
    for token in required:
        assert token in script

    forbidden = (
        "New-ScheduledTaskTrigger",
        "-AtStartup",
        "-AtLogOn",
        "RestartCount",
        "RestartInterval",
        "Register-ScheduledTask -Trigger",
        "WEBHOOK_SECRET",
        "PRIVATE_KEY",
        "MNEMONIC",
        "WALLET",
        "TELEGRAM",
        "EXECUTOR",
    )
    for token in forbidden:
        assert token not in script


def test_anchor_refuses_to_replace_an_existing_task() -> None:
    script = ANCHOR.read_text()

    assert "Get-ScheduledTask -TaskName $taskName" in script
    assert "already exists; refusing to replace it" in script
    assert "Register-ScheduledTask" in script
    assert "-Force" not in script
