"""Tests for the fresh-mac reproducibility bootstrap."""

from __future__ import annotations

import os
import platform
import plistlib
import subprocess
from pathlib import Path

IS_MACOS = platform.system() == "Darwin"

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "scripts" / "ops" / "bootstrap_fresh_mac.sh"
TEARDOWN = REPO_ROOT / "scripts" / "ops" / "teardown_fresh_mac.sh"
SECRETS_EXAMPLE = REPO_ROOT / "infra" / "secrets.env.example"
LAUNCHAGENT_LIST = REPO_ROOT / "infra" / "bootstrap" / "demo-launchagents.list"


def test_bootstrap_dry_run_traces_without_writing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    target_repo = tmp_path / "checkout" / "Sapphire"
    env = {
        **os.environ,
        "HOME": str(home),
        "SAPPHIRE_BOOTSTRAP_DRY_RUN": "1",
        "SAPPHIRE_REPO_PATH": str(target_repo),
        "SAPPHIRE_BOOTSTRAP_VENV": str(tmp_path / "venv"),
        "SAPPHIRE_LAUNCHAGENTS_DIR": str(home / "Library" / "LaunchAgents"),
        "SAPPHIRE_LOG_DIR": str(home / "Library" / "Logs" / "sapphire"),
        "SAPPHIRE_AUTONOMY_LOG_DIR": str(home / "autonomy-status" / "logs"),
        "SAPPHIRE_SECRETS_DIR": str(home / ".sapphire"),
        "SAPPHIRE_SECRETS_FILE": str(home / ".sapphire" / "secrets.env"),
    }

    result = subprocess.run(
        ["bash", str(BOOTSTRAP)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "[dry-run]" in result.stdout
    assert "git clone https://github.com/arigatoexpress/Sapphire.git" in result.stdout
    assert "local_ci_verify.py" in result.stdout
    assert not home.exists()
    assert not target_repo.exists()

    # LaunchAgents are a macOS concept. On Linux the script announces the
    # fallback and skips plist installation, so asserting on plist output there
    # tests the host, not the bootstrap. Assert the correct branch either way
    # rather than dropping the coverage.
    if IS_MACOS:
        assert "RunAtLoad=false" in result.stdout
    else:
        assert "launchagents: skipped on non-macOS" in result.stdout


def test_demo_secrets_example_is_inert() -> None:
    content = SECRETS_EXAMPLE.read_text(encoding="utf-8")
    required_closed_gates = [
        "SAPPHIRE_DEMO_MODE=1",
        "SAPPHIRE_LIVE_MODE=0",
        "SAPPHIRE_DISABLE_EXTERNAL_APIS=1",
        "TELEGRAM_DRY_RUN=1",
        "TRADINGVIEW_EXECUTION_ENABLED=false",
        "SAPPHIRE_TRADING_LIVE=0",
        "SAPPHIRE_ROBINHOOD_LIVE=0",
        "SAPPHIRE_HYPERLIQUID_LIVE=0",
        "SAPPHIRE_X402_LIVE=0",
        "X402_ENABLED=0",
    ]
    for gate in required_closed_gates:
        assert gate in content
    assert "PLACEHOLDER_DO_NOT_USE" in content
    assert "aribs" not in content


def test_demo_launchagent_templates_exist_and_bootstrap_forces_runatload_false() -> None:
    script = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'payload["RunAtLoad"] = False' in script

    relpaths = [
        line.strip()
        for line in LAUNCHAGENT_LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert relpaths

    for relpath in relpaths:
        plist_path = REPO_ROOT / relpath
        assert plist_path.exists(), relpath
        with plist_path.open("rb") as handle:
            payload = plistlib.load(handle)
        assert "Label" in payload


def test_teardown_preserves_secrets_unless_placeholder_reset_requested() -> None:
    content = TEARDOWN.read_text(encoding="utf-8")
    assert "SAPPHIRE_BOOTSTRAP_RESET_SECRETS" in content
    assert "PLACEHOLDER_DO_NOT_USE" in content
    assert "preserved" in content
