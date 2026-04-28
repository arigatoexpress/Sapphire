"""Tests for safe default-dry-run autonomy posture."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALPHA_MAIN = ROOT / "services" / "alpha" / "src" / "main.py"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy" / "deploy_sapphire_alpha.sh"


def test_alpha_engine_autonomy_dry_run_defaults_true() -> None:
    tree = ast.parse(ALPHA_MAIN.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "_autonomy_dry_run"
                and isinstance(node.value, ast.Call)
            ):
                call = node.value
                assert call.args
                assert isinstance(call.args[0], ast.Constant)
                assert call.args[0].value == "SAPPHIRE_AUTONOMY_DRY_RUN"
                defaults = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
                assert isinstance(defaults["default"], ast.Constant)
                assert defaults["default"].value is True
                return

    raise AssertionError("_autonomy_dry_run assignment not found")


def test_sapphire_alpha_deploy_defaults_autonomy_dry_run_true() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'AUTONOMY_DRY_RUN="${AUTONOMY_DRY_RUN:-true}"' in script
    assert 'AUTONOMY_DRY_RUN="${AUTONOMY_DRY_RUN:-false}"' not in script
    assert 'AUTONOMY_ALLOW_CODE_CHANGES="${AUTONOMY_ALLOW_CODE_CHANGES:-false}"' in script
    assert 'AUTONOMY_ALLOW_GCLOUD_CHANGES="${AUTONOMY_ALLOW_GCLOUD_CHANGES:-false}"' in script
    assert 'AUTONOMY_ALLOW_CODE_CHANGES="${AUTONOMY_ALLOW_CODE_CHANGES:-true}"' not in script
    assert 'AUTONOMY_ALLOW_GCLOUD_CHANGES="${AUTONOMY_ALLOW_GCLOUD_CHANGES:-true}"' not in script
