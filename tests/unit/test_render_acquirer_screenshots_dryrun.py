"""Dry-run tests for ``scripts/ops/render_acquirer_screenshots.py``.

The dry-run path MUST NOT import Playwright. The live path is operator-gated
behind ``SAPPHIRE_PLAYWRIGHT_LOCAL=1`` and is not exercised here.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ops" / "render_acquirer_screenshots.py"


def _load_module():
    """Load the harness module by file path so tests do not depend on package wiring."""
    sys.path.insert(0, str(REPO_ROOT))
    module = importlib.import_module("scripts.ops.render_acquirer_screenshots")
    importlib.reload(module)
    return module


def test_script_file_exists() -> None:
    assert SCRIPT_PATH.is_file(), f"missing {SCRIPT_PATH}"


def test_dry_run_does_not_import_playwright(tmp_path, monkeypatch) -> None:
    """Importing and running the dry-run path leaves Playwright unimported."""
    # Pretend playwright is not installed.
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    module = _load_module()
    config = module.HarnessConfig(output_dir=tmp_path, dry_run=True)
    result = module.run_dry_run(config)

    assert result["mode"] == "dry-run"
    assert result["ok"] is True
    # No actual import occurred for Playwright on the dry-run path.
    # We sentinel-marked sys.modules with None earlier; if the harness had
    # imported it, that sentinel would have been overwritten or raised.
    assert sys.modules["playwright"] is None
    assert sys.modules["playwright.sync_api"] is None


def test_dry_run_writes_plan_json(tmp_path) -> None:
    """A predictable JSON plan lands at the expected location."""
    module = _load_module()
    config = module.HarnessConfig(output_dir=tmp_path, dry_run=True)
    plan_path = module.write_dry_run_plan(config)

    assert plan_path == tmp_path / "plan.dry-run.json"
    payload = json.loads(plan_path.read_text())
    assert payload["dry_run"] is True
    assert payload["env_flag"] == module.ENV_FLAG
    assert payload["pages"], "plan must list pages"
    paths = {entry["path"] for entry in payload["pages"]}
    assert "/" in paths
    assert "/diligence" in paths
    assert "/observability" in paths


def test_assert_live_authorized_blocks_when_flag_unset(tmp_path) -> None:
    """Live mode refuses to run without the explicit env flag."""
    module = _load_module()
    with pytest.raises(RuntimeError) as excinfo:
        module.assert_live_authorized(env={})
    assert module.ENV_FLAG in str(excinfo.value)


def test_assert_live_authorized_passes_when_flag_set() -> None:
    module = _load_module()
    module.assert_live_authorized(env={module.ENV_FLAG: "1"})


def test_ensure_output_dir_is_idempotent(tmp_path) -> None:
    """Calling ensure_output_dir twice does not error and does not blow data away."""
    module = _load_module()
    target = tmp_path / "alpha" / "beta" / "gamma"
    config = module.HarnessConfig(output_dir=target)
    module.ensure_output_dir(config)
    sentinel = target / "sentinel.txt"
    sentinel.write_text("hi")
    module.ensure_output_dir(config)  # second call must not destroy sentinel
    assert sentinel.read_text() == "hi"


def test_main_dry_run_emits_json_and_returns_zero(tmp_path, capsys) -> None:
    """The CLI default path is dry-run, returns 0, and prints a JSON document."""
    module = _load_module()
    rc = module.main(["--output-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["mode"] == "dry-run"
    assert payload["ok"] is True
    assert (tmp_path / "plan.dry-run.json").exists()


def test_planned_outputs_match_default_pages(tmp_path) -> None:
    """The dataclass returns the absolute paths the operator should expect."""
    module = _load_module()
    config = module.HarnessConfig(output_dir=tmp_path)
    outs = config.planned_outputs()
    assert len(outs) == len(module.DEFAULT_PAGES)
    for path in outs:
        assert path.parent == tmp_path
        assert path.suffix == ".png"


def test_dry_run_idempotent_overwrite(tmp_path) -> None:
    """Re-running dry-run twice yields the same JSON; operator can iterate safely."""
    module = _load_module()
    config = module.HarnessConfig(output_dir=tmp_path, dry_run=True)
    first_path = module.write_dry_run_plan(config)
    first = json.loads(first_path.read_text())
    second_path = module.write_dry_run_plan(config)
    second = json.loads(second_path.read_text())
    assert first == second
