"""Static guardrails for the React app-preview spine."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "services" / "dashboard" / "app.py"
DOCKERFILE = ROOT / "services" / "dashboard" / "Dockerfile"
FRONTEND = ROOT / "services" / "dashboard" / "frontend"


def test_app_preview_route_is_auth_gated_and_honest_when_unbuilt() -> None:
    source = APP.read_text(encoding="utf-8")

    assert '_FRONTEND_DIST_DIR = Path(__file__).parent / "frontend" / "dist"' in source
    assert '@app.route("/app-preview")' in source
    assert '@app.route("/app-preview/assets/<path:filename>")' in source
    assert "def app_preview():" in source
    assert "def app_preview_assets(filename):" in source
    assert '"mode": "blocked"' in source
    assert '"path_or_url": "services/dashboard/frontend/dist/index.html"' in source
    assert "send_file(index_path)" in source


def test_frontend_preview_targets_v2_summary_without_mock_data() -> None:
    api = (FRONTEND / "src" / "api" / "controlPlane.ts").read_text(encoding="utf-8")
    vite = (FRONTEND / "vite.config.ts").read_text(encoding="utf-8")
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))

    assert 'base: "/app-preview/"' in vite
    assert '"/api/v2/control-plane/summary"' in api
    assert "No mock data is displayed" in api
    assert 'currentUrl.username = ""' in api
    assert 'currentUrl.password = ""' in api
    assert package["scripts"]["build"] == "tsc -b && vite build"


def test_dashboard_container_builds_preview_assets() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "FROM node:24-slim AS frontend-build" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "COPY --from=frontend-build /frontend/dist ./frontend/dist" in dockerfile
