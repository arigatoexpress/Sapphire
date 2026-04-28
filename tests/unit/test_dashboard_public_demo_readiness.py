from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    sys.path.insert(0, str(REPO_ROOT))
    module = importlib.import_module("scripts.ops.dashboard_public_demo_readiness")
    importlib.reload(module)
    return module


def test_manifest_loads_and_names_safe_routes() -> None:
    module = _load_module()
    manifest = module.load_manifest()

    routes = {item["path"] for item in manifest["safe_routes"]}
    assert "/" in routes
    assert "/diligence" in routes
    assert "/production-readiness" in routes


def test_redact_text_replaces_secret_shapes_and_paths() -> None:
    module = _load_module()
    manifest = module.load_manifest()
    text = (
        "path=/Users/aribs/Code/Sapphire token=super-secret "
        "Authorization: Bearer abcdefghijklmnop user=ari@example.com Ari's dashboard"
    )

    redacted, counts = module.redact_text(text, manifest)

    assert "/Users/aribs" not in redacted
    assert "super-secret" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "Bearer " not in redacted
    assert "ari@example.com" not in redacted
    assert "Ari" not in redacted
    assert "the operator's dashboard" in redacted
    assert counts["absolute_user_path"] == 1
    assert counts["secret_assignment"] >= 1
    assert counts["bearer_token"] == 1
    assert counts["private_email"] == 1
    assert counts["operator_possessive"] == 1


def test_forbidden_residue_detects_secret_assignment_after_redaction() -> None:
    module = _load_module()
    manifest = module.load_manifest()

    assert "MOONSHOT_API_KEY=" in module.forbidden_residue("MOONSHOT_API_KEY=value", manifest)


def test_bearer_redaction_does_not_reintroduce_forbidden_literal() -> None:
    module = _load_module()
    manifest = module.load_manifest()

    redacted, counts = module.redact_text("Authorization: Bearer abcdefghijklmnop", manifest)

    assert counts["bearer_token"] == 1
    assert "Bearer " not in redacted
    assert module.forbidden_residue(redacted, manifest) == []


def test_build_report_is_green_for_current_repo_and_writes_build_json(tmp_path) -> None:
    module = _load_module()
    report = module.build_report(output_dir=tmp_path)

    assert report["ok"] is True
    assert report["totals"]["routes"] >= 5
    assert report["totals"]["sources_scanned"] >= 10
    assert report["totals"]["screenshot_placeholders"] >= 1
    assert report["written"]["plan"] == "[outside-repo]/dashboard-public-demo-plan.json"
    assert report["written"]["redaction_report"] == (
        "[outside-repo]/dashboard-public-demo-redaction-report.json"
    )
    assert (tmp_path / "dashboard-public-demo-plan.json").exists()
    assert (tmp_path / "dashboard-public-demo-redaction-report.json").exists()
    assert str(tmp_path) not in json.dumps(report)


def test_build_report_no_write_has_no_written_key(tmp_path) -> None:
    module = _load_module()
    report = module.build_report(output_dir=tmp_path, write=False)

    assert report["ok"] is True
    assert "written" not in report
    assert not list(tmp_path.glob("*"))


def test_missing_source_fails_custom_manifest(tmp_path) -> None:
    module = _load_module()
    manifest = module.load_manifest()
    manifest["scan_sources"] = ["missing.md"]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = module.build_report(manifest_path=manifest_path, output_dir=tmp_path)

    assert report["ok"] is False
    assert "source:missing.md" in report["failures"]


def test_nonempty_screenshot_fails_custom_manifest(tmp_path) -> None:
    module = _load_module()
    shot_dir = tmp_path / "shots"
    shot_dir.mkdir()
    (shot_dir / "leaky.png").write_bytes(b"not a placeholder")
    source = tmp_path / "safe.md"
    source.write_text("safe text", encoding="utf-8")
    manifest = module.load_manifest()
    manifest["scan_sources"] = [str(source)]
    manifest["placeholder_screenshot_dirs"] = [str(shot_dir)]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = module.build_report(manifest_path=manifest_path, output_dir=tmp_path / "out")

    assert report["ok"] is False
    assert any(item.startswith("screenshot:") for item in report["failures"])


def test_export_plan_has_no_live_browser_requirement() -> None:
    module = _load_module()
    manifest = module.load_manifest()
    plan = module.build_export_plan(manifest)

    assert plan["mode"] == "dry-run"
    assert plan["browser_required"] is False
    assert plan["live_dashboard_required"] is False
    assert all(route["requires_auth"] for route in plan["routes"])


def test_main_pretty_no_write_returns_zero(capsys) -> None:
    module = _load_module()
    rc = module.main(["--no-write", "--pretty"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "dry-run"


def test_manifest_routes_exist_in_dashboard_app() -> None:
    module = _load_module()
    manifest = module.load_manifest()
    app_source = REPO_ROOT.joinpath("services/dashboard/app.py").read_text(encoding="utf-8")
    dashboard_routes = set(re.findall(r'@app\.route\("([^"]+)"', app_source))

    for route in manifest["safe_routes"]:
        assert route["path"] in dashboard_routes


def test_invalid_manifest_schema_raises(tmp_path) -> None:
    module = _load_module()
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")

    with pytest.raises(ValueError):
        module.load_manifest(manifest_path)
