"""Smoke tests for scripts/hackathon_smoke.sh.

We exercise multiple paths:

1. ``--dry-run`` against a freshly generated key with the test-only env
   bypasses set (no funded wallet, no real deploy). Asserts exit 0 and
   "DRY-RUN COMPLETE" in stderr.
2. Missing key path -> exit 2.
3. Malformed key file -> exit 2.
4. ``--target`` defaults to ``0g`` (back-compat).
5. Invalid ``--target`` value exits with usage message.
6. ``--target robinhood --dry-run`` exits 0 and produces "DRY-RUN COMPLETE".
7. ``--target both --dry-run`` exits 0 and writes both artifact sections.

These tests do NOT invoke the real deploy script, do NOT broadcast any
transactions, and do NOT touch real RPCs in a way that could matter
(the dry-run path makes one read-only ``eth_getBalance`` call that is
allowed to be over-written by the bypass env var).
"""

from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "hackathon_smoke.sh"
SUMMARY_FILE = REPO_ROOT / "data" / "hackathon" / "submission_artifacts.md"


def _make_key(tmp_path: Path, name: str = "test_key") -> Path:
    """Generate a brand-new private key file (mode 0600)."""
    key_hex = "0x" + secrets.token_hex(32)
    key_path = tmp_path / name
    key_path.write_text(key_hex)
    key_path.chmod(0o600)
    return key_path


def _run(
    args: list[str], env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    env = {**os.environ}
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )


def test_script_is_executable() -> None:
    assert SCRIPT.exists(), f"missing: {SCRIPT}"
    mode = SCRIPT.stat().st_mode & 0o777
    assert mode & 0o100, f"script not executable: mode={oct(mode)}"


def test_help_flag() -> None:
    result = _run(["--help"])
    assert result.returncode == 0, result.stderr
    assert "scripts/hackathon_smoke.sh" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--target" in result.stdout


def test_missing_key_returns_exit_2(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_key"
    result = _run(
        ["--dry-run", "--force-dirty", "--key-path", str(missing)],
    )
    assert result.returncode == 2, (
        f"expected exit 2 for missing key; got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "key file not found" in result.stderr


def test_malformed_key_returns_exit_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad_key"
    bad.write_text("not_a_real_private_key")
    bad.chmod(0o600)
    result = _run(
        ["--dry-run", "--force-dirty", "--key-path", str(bad)],
    )
    assert result.returncode == 2, (
        f"expected exit 2 for malformed key; got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "malformed key" in result.stderr or "address derivation failed" in result.stderr


def test_dry_run_completes_with_bypasses(tmp_path: Path) -> None:
    """End-to-end dry-run with test-only bypass env vars set.

    Skipped if ``eth_account`` is missing in the environment.
    """
    pytest.importorskip("eth_account", reason="eth-account required for key derivation")

    key = _make_key(tmp_path)
    result = _run(
        ["--dry-run", "--force-dirty", "--network", "testnet", "--key-path", str(key)],
        env_overrides={
            "SAPPHIRE_HACKATHON_SMOKE_BYPASS_BALANCE": "1",
            "SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY": "1",
        },
    )
    if result.returncode != 0:
        if "RPC eth_getBalance failed" in result.stderr or "rpc error" in result.stderr.lower():
            pytest.skip("RPC unreachable from test environment")
    assert result.returncode == 0, (
        f"expected exit 0 for dry-run; got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "DRY-RUN COMPLETE" in result.stderr


def test_invalid_target_exits_with_usage() -> None:
    result = _run(["--target", "ethereum"])
    assert result.returncode == 1, (
        f"expected exit 1 for invalid target; got {result.returncode}\nstderr: {result.stderr}"
    )
    # Both the usage message and the failure reason should be present.
    assert "Usage: scripts/hackathon_smoke.sh" in result.stdout
    assert "must be '0g', 'robinhood', or 'both'" in result.stderr


def test_missing_target_defaults_to_0g(tmp_path: Path) -> None:
    """Without --target, the script must run the 0g flow (back-compat).

    We run dry-run with bypass env vars and check the log line that records
    the resolved target.
    """
    pytest.importorskip("eth_account", reason="eth-account required for key derivation")

    key = _make_key(tmp_path, "default_target_key")
    result = _run(
        ["--dry-run", "--force-dirty", "--network", "testnet", "--key-path", str(key)],
        env_overrides={
            "SAPPHIRE_HACKATHON_SMOKE_BYPASS_BALANCE": "1",
            "SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY": "1",
        },
    )
    if result.returncode != 0:
        if "RPC eth_getBalance failed" in result.stderr or "rpc error" in result.stderr.lower():
            pytest.skip("RPC unreachable from test environment")
    assert result.returncode == 0, result.stderr
    assert "target:          0g" in result.stderr or "target=0g" in result.stderr
    # Should NOT have invoked the robinhood pre-check.
    assert "robinhood deploy key" not in result.stderr


def test_target_robinhood_dry_run(tmp_path: Path) -> None:
    """``--target robinhood --dry-run`` exits 0 and produces DRY-RUN COMPLETE."""
    pytest.importorskip("eth_account", reason="eth-account required for key derivation")

    rh_key = _make_key(tmp_path, "rh_test_key")
    result = _run(
        ["--dry-run", "--force-dirty", "--target", "robinhood"],
        env_overrides={
            "SAPPHIRE_HACKATHON_SMOKE_BYPASS_BALANCE": "1",
            "SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY": "1",
            "ROBINHOOD_DEPLOY_KEY_PATH": str(rh_key),
        },
    )
    if result.returncode != 0:
        if "RPC eth_getBalance failed" in result.stderr or "rpc error" in result.stderr.lower():
            pytest.skip("Robinhood RPC unreachable from test environment")
    assert result.returncode == 0, (
        f"expected exit 0 for robinhood dry-run; got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "DRY-RUN COMPLETE" in result.stderr
    # The robinhood section should appear in the appended summary.
    assert SUMMARY_FILE.exists(), "submission_artifacts.md should have been written"
    contents = SUMMARY_FILE.read_text(encoding="utf-8")
    assert "Robinhood Chain (London Buildathon" in contents
    assert "Chain ID: 46630" in contents


def test_target_both_dry_run(tmp_path: Path) -> None:
    """``--target both --dry-run`` exits 0 and writes BOTH artifact sections."""
    pytest.importorskip("eth_account", reason="eth-account required for key derivation")

    og_key = _make_key(tmp_path, "og_both_key")
    rh_key = _make_key(tmp_path, "rh_both_key")
    result = _run(
        [
            "--dry-run",
            "--force-dirty",
            "--target",
            "both",
            "--network",
            "testnet",
            "--key-path",
            str(og_key),
        ],
        env_overrides={
            "SAPPHIRE_HACKATHON_SMOKE_BYPASS_BALANCE": "1",
            "SAPPHIRE_HACKATHON_SMOKE_SKIP_DEPLOY": "1",
            "ROBINHOOD_DEPLOY_KEY_PATH": str(rh_key),
        },
    )
    if result.returncode != 0:
        if "RPC eth_getBalance failed" in result.stderr or "rpc error" in result.stderr.lower():
            pytest.skip("RPC unreachable from test environment")
    assert result.returncode == 0, (
        f"expected exit 0 for both dry-run; got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "DRY-RUN COMPLETE" in result.stderr
    assert SUMMARY_FILE.exists(), "submission_artifacts.md should have been written"
    contents = SUMMARY_FILE.read_text(encoding="utf-8")
    # Both sections present.
    assert "0G (APAC Buildathon" in contents
    assert "Robinhood Chain (London Buildathon" in contents
    assert "Chain ID: 16602" in contents  # 0G testnet
    assert "Chain ID: 46630" in contents  # Robinhood Chain testnet
