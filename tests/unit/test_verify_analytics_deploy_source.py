from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "verify_analytics_deploy_source.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_analytics_deploy_source", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_analytics_deploy_source"] = module
    spec.loader.exec_module(module)
    return module


def _write_good_source(root: Path) -> None:
    (root / "templates").mkdir()
    (root / "app.py").write_text(
        """
from flask import Flask

app = Flask(__name__)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/admin/data-engineering")
def data_engineering():
    return {}

@app.get("/api/projects")
def projects():
    return {"projects": []}
""",
        encoding="utf-8",
    )
    (root / "brain.py").write_text(
        """
def register(app):
    @app.get("/api/brain/synthesis")
    def brain():
        return {}
""",
        encoding="utf-8",
    )
    (root / "markets.py").write_text(
        """
def register(app):
    @app.get("/api/markets/snapshot")
    def markets():
        return {}
""",
        encoding="utf-8",
    )
    (root / "Dockerfile").write_text("CMD exec gunicorn --bind :$PORT app:app\n", encoding="utf-8")
    (root / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (root / "templates" / "index.html").write_text("Sapphire OS\n", encoding="utf-8")
    (root / "templates" / "admin.html").write_text("admin\n", encoding="utf-8")
    (root / "data_engineering.py").write_text(
        "def build_data_engineering_report(): pass\n", encoding="utf-8"
    )


def test_guard_accepts_analytics_flask_source(tmp_path):
    module = _load_module()
    _write_good_source(tmp_path)

    report = module.build_report(tmp_path)

    assert report.ok is True
    assert report.missing_required_files == []
    assert report.forbidden_paths_present == []
    assert report.missing_required_routes == []


def test_guard_rejects_type_script_project_uploaded_to_service_name(tmp_path):
    module = _load_module()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "server.ts").write_text("export const service = 'aoe';\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"name": "agent-opportunity-exchange"}\n', encoding="utf-8"
    )
    (tmp_path / "Dockerfile").write_text("CMD npm start\n", encoding="utf-8")

    report = module.build_report(tmp_path)

    assert report.ok is False
    assert "package.json" in report.forbidden_paths_present
    assert "src/server.ts" in report.forbidden_paths_present
    assert "/health" in report.missing_required_routes
    assert "app.py" in report.missing_required_files
    assert report.dockerfile_ok is False


def test_guard_rejects_flask_source_missing_public_contract(tmp_path):
    module = _load_module()
    _write_good_source(tmp_path)
    (tmp_path / "markets.py").write_text("# route accidentally removed\n", encoding="utf-8")

    report = module.build_report(tmp_path)

    assert report.ok is False
    assert report.forbidden_paths_present == []
    assert "/api/markets/snapshot" in report.missing_required_routes
