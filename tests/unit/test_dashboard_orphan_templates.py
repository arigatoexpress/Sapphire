"""Guardrails for dashboard templates that are intentionally not routed."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "services" / "dashboard"
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
    os.environ["AUTH_PASSWORD"] = "test"
    if str(DASHBOARD) not in sys.path:
        sys.path.insert(0, str(DASHBOARD))
    sys.modules.pop("app", None)

    import app as dashboard_app  # type: ignore[import-not-found]

    routes = {rule.rule for rule in dashboard_app.app.url_map.iter_rules()}

    assert "/platform" not in routes
    assert "/api/admin/domains" not in routes
