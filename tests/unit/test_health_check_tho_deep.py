"""Unit tests for the THO deep health probe.

The deep probe exercises auth → Firestore → templates (GCS-backed) so a green
signal actually reflects the business path, not just process liveness.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

SAPPHIRE = Path.home() / "Code" / "Sapphire"
INTERNAL = SAPPHIRE / "plugins" / "claw-sapphire" / "tools" / "internal"

_spec = importlib.util.spec_from_file_location("health_check_internal", INTERNAL / "health_check.py")
hc = importlib.util.module_from_spec(_spec)
sys.modules["health_check_internal"] = hc
_spec.loader.exec_module(hc)


def _resp(payload: dict, status: int = 200):
    body = json.dumps(payload).encode()
    fake = io.BytesIO(body)
    fake.status = status
    fake.__enter__ = lambda self: self  # type: ignore[attr-defined]
    fake.__exit__ = lambda self, *a: False  # type: ignore[attr-defined]
    return fake


class TestThoDeepProbe:
    def test_skipped_when_pin_missing(self, monkeypatch):
        monkeypatch.setattr(hc, "_load_tho_pin", lambda: None)
        result = hc.check_tho_deep()
        assert list(result.keys()) == ["tho-deep:auth"]
        assert result["tho-deep:auth"]["status"] == "yellow"
        assert "THO_ADMIN_PIN not set" in result["tho-deep:auth"]["detail"]

    def test_full_green_path(self, monkeypatch):
        monkeypatch.setattr(hc, "_load_tho_pin", lambda: "test-pin")

        responses = [
            _resp({"token": "a" * 40}),                      # /api/admin/verify
            _resp({"total": 2000}),                           # /api/customers/count
            _resp({"templates": [{"id": "t1"}, {"id": "t2"}]}),  # /api/documents/templates
        ]

        def fake_urlopen(req, timeout=None, context=None):
            return responses.pop(0)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = hc.check_tho_deep()

        assert result["tho-deep:auth"]["status"] == "green"
        assert "JWT issued" in result["tho-deep:auth"]["detail"]
        assert result["tho-deep:firestore"]["status"] == "green"
        assert "2,000" in result["tho-deep:firestore"]["detail"]
        assert result["tho-deep:templates"]["status"] == "green"
        assert "2 templates" in result["tho-deep:templates"]["detail"]

    def test_auth_fail_skips_downstream(self, monkeypatch):
        monkeypatch.setattr(hc, "_load_tho_pin", lambda: "wrong-pin")

        def fake_urlopen(req, timeout=None, context=None):
            raise urllib.error.HTTPError(
                url="x", code=401, msg="Unauthorized", hdrs=None, fp=None  # type: ignore[arg-type]
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = hc.check_tho_deep()

        assert result["tho-deep:auth"]["status"] == "red"
        assert "401" in result["tho-deep:auth"]["detail"]
        assert result["tho-deep:firestore"]["status"] == "red"
        assert "no auth token" in result["tho-deep:firestore"]["detail"]
        assert result["tho-deep:templates"]["status"] == "red"

    def test_firestore_empty_is_yellow(self, monkeypatch):
        monkeypatch.setattr(hc, "_load_tho_pin", lambda: "test-pin")
        responses = [
            _resp({"token": "a" * 40}),
            _resp({"total": 0}),
            _resp({"templates": []}),
        ]

        def fake_urlopen(req, timeout=None, context=None):
            return responses.pop(0)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = hc.check_tho_deep()

        assert result["tho-deep:firestore"]["status"] == "yellow"
        assert result["tho-deep:templates"]["status"] == "yellow"

    def test_templates_http_error_marks_red(self, monkeypatch):
        monkeypatch.setattr(hc, "_load_tho_pin", lambda: "test-pin")
        call = {"n": 0}

        def fake_urlopen(req, timeout=None, context=None):
            call["n"] += 1
            if call["n"] == 1:
                return _resp({"token": "a" * 40})
            if call["n"] == 2:
                return _resp({"total": 1500})
            raise urllib.error.HTTPError(
                url="x", code=500, msg="Server Error", hdrs=None, fp=None  # type: ignore[arg-type]
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = hc.check_tho_deep()

        assert result["tho-deep:auth"]["status"] == "green"
        assert result["tho-deep:firestore"]["status"] == "green"
        assert result["tho-deep:templates"]["status"] == "red"
        assert "500" in result["tho-deep:templates"]["detail"]
