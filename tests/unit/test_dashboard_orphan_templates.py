"""Guardrails for dashboard templates that are intentionally not routed."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "services" / "dashboard" / "app.py"
PAGES = ROOT / "services" / "dashboard" / "templates" / "pages"
BASE = ROOT / "services" / "dashboard" / "templates" / "base.html"
DEPLOY = ROOT / "services" / "dashboard" / "deploy.sh"


def test_removed_orphan_dashboard_templates_stay_removed() -> None:
    assert not (PAGES / "admin_domains.html").exists()
    assert not (PAGES / "platform.html").exists()


def test_dashboard_docs_do_not_advertise_dead_platform_route() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")

    assert 'href="/platform"' not in base
    assert "current_page in ['architecture', 'platform']" not in base
    assert 'echo "  /platform' not in deploy
    assert "-> /platform" not in deploy
    assert "Legacy aliases" not in deploy


def test_orphan_routes_are_not_registered() -> None:
    app_source = APP.read_text(encoding="utf-8")

    assert "@app.route('/platform')" not in app_source
    assert '@app.route("/platform")' not in app_source
    assert "@app.route('/api/admin/domains')" not in app_source
    assert '@app.route("/api/admin/domains")' not in app_source
