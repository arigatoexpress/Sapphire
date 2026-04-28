"""Tests for operator-facing ops script compatibility entrypoints."""

import os
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
