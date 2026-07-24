from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "services" / "dashboard" / "frontend" / "src"


def test_react_preview_uses_workbench_layout_and_inspector() -> None:
    app_source = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    styles = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    assert "operator-shell" in app_source
    assert "Evidence Inspector" in app_source
    assert "Inspect Evidence" in app_source
    assert "Action posture" in app_source
    assert "read-only evidence canvas" in app_source
    assert ".operator-shell" in styles
    assert ".inspector-panel" in styles
    assert ".status-strip" in styles


def test_react_preview_fetches_only_read_only_summary_endpoint() -> None:
    api_source = (FRONTEND / "api" / "controlPlane.ts").read_text(encoding="utf-8")
    app_source = (FRONTEND / "App.tsx").read_text(encoding="utf-8")

    assert 'fetch(dashboardUrl("/api/v2/control-plane/summary")' in api_source
    assert "method:" not in api_source
    assert "fetch(" not in app_source
    assert "POST" not in app_source
    assert "DELETE" not in app_source
    assert "PATCH" not in app_source
    assert "PUT" not in app_source


def test_react_preview_names_blocked_and_confirmation_postures() -> None:
    app_source = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    api_source = (FRONTEND / "api" / "controlPlane.ts").read_text(encoding="utf-8")

    assert "blocked" in api_source
    assert "dry_run" in api_source
    assert "confirm required" in app_source
    assert "no live mutation" in app_source
