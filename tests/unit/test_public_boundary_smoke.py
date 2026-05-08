from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "public_boundary_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("public_boundary_smoke_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["public_boundary_smoke_test"] = module
    spec.loader.exec_module(module)
    return module


def test_scan_text_flags_raw_wildfire_signal_key():
    script = _load_script()

    result = script.scan_text("/p/wildfire", 200, "const value = data.signals_24h;")

    assert result.status == "FAIL"
    assert "wildfire-signal-24h-key" in result.matches


def test_scan_text_flags_direct_external_admin_url():
    script = _load_script()

    result = script.scan_text(
        "/p/regional",
        200,
        '<a href="https://regional.sapphirealpha.xyz/admin">open admin console</a>',
    )

    assert result.status == "FAIL"
    assert "regional-admin-url" in result.matches
    assert "admin-console-copy" in result.matches


def test_scan_text_passes_public_safe_summary():
    script = _load_script()

    result = script.scan_text(
        "/p/system",
        200,
        "Public system summary. Service names and raw evidence require admin.",
    )

    assert result.status == "PASS"
    assert result.matches == ()
