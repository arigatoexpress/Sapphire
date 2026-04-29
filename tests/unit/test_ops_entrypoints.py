"""Tests for operator-facing ops script compatibility entrypoints."""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_root_ops_entrypoints_delegate_to_maintained_scripts() -> None:
    entrypoints = {
        "check_required_secrets.sh": "ops/check_required_secrets.sh",
        "autonomy_readiness_check.sh": "ops/autonomy_readiness_check.sh",
    }

    for entrypoint_name, target in entrypoints.items():
        entrypoint = ROOT / "scripts" / entrypoint_name
        target_path = ROOT / "scripts" / target

        assert target_path.exists()
        assert os.access(target_path, os.X_OK)
        assert entrypoint.exists()
        assert os.access(entrypoint, os.X_OK)
        assert f'exec "${{SCRIPT_DIR}}/{target}" "$@"' in entrypoint.read_text(encoding="utf-8")


def test_frontend_endpoint_drift_script_resolves_repo_root_from_script_location() -> None:
    script = ROOT / "scripts" / "ops" / "check_frontend_endpoint_drift.sh"

    result = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT / "scripts",
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{ROOT}/services/dashboard/templates" in result.stdout
    assert f"{ROOT}/scripts/services" not in result.stdout


def test_frontend_endpoint_drift_script_fails_when_scan_roots_are_absent(
    tmp_path: Path,
) -> None:
    source = ROOT / "scripts" / "ops" / "check_frontend_endpoint_drift.sh"
    script = tmp_path / "scripts" / "ops" / "check_frontend_endpoint_drift.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(source, script)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "FAIL: scan root exists:" in result.stdout
    assert "frontend endpoint drift check FAILED" in result.stdout
