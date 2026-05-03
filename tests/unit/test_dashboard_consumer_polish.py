"""Consumer-polish smoke tests for the four flagship dashboard pages.

Asserts each page (a) renders 200 with valid Basic auth, (b) contains a
plain-English headline (`.panel-headline`), (c) contains an inline
disclosure (`details.tech-disclosure`), and (d) carries a visible safety
badge (`.safety-badge`). Coverage matches the 2026-05-03 dashboard polish
megaprompt — see `docs/handoffs/ultimate-megaprompt-2026-05-03.md` §B3.
"""

from __future__ import annotations

import base64
import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def client():
    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as test_client:
        yield test_client


POLISHED_PAGES = [
    ("/", "overview"),
    ("/showcase", "showcase"),
    ("/analytics", "analytics"),
    ("/performance", "performance"),
]


@pytest.mark.parametrize("path,_label", POLISHED_PAGES)
def test_polished_page_renders_200(client, path, _label):
    response = client.get(path, headers=_auth_header())
    assert response.status_code == 200, (
        f"{path} returned {response.status_code} — expected 200"
    )


@pytest.mark.parametrize("path,_label", POLISHED_PAGES)
def test_polished_page_has_plain_english_headline(client, path, _label):
    response = client.get(path, headers=_auth_header())
    html = response.get_data(as_text=True)
    assert 'class="panel-headline"' in html, (
        f"{path} missing the .panel-headline plain-English headline block"
    )


@pytest.mark.parametrize("path,_label", POLISHED_PAGES)
def test_polished_page_has_tech_disclosure(client, path, _label):
    response = client.get(path, headers=_auth_header())
    html = response.get_data(as_text=True)
    assert 'class="tech-disclosure"' in html, (
        f"{path} missing the inline 'How does this work?' disclosure"
    )
    assert "How does this work?" in html, (
        f"{path} disclosure missing the canonical 'How does this work?' summary"
    )


@pytest.mark.parametrize("path,_label", POLISHED_PAGES)
def test_polished_page_has_safety_badge(client, path, _label):
    response = client.get(path, headers=_auth_header())
    html = response.get_data(as_text=True)
    assert "safety-badge" in html, (
        f"{path} missing a .safety-badge — every dense page should expose paper/live/dry-run state"
    )


def test_base_template_defines_polish_tokens():
    """The shared design tokens live in base.html so every page can opt in."""
    base = (ROOT / "services" / "dashboard" / "templates" / "base.html").read_text(
        encoding="utf-8"
    )
    assert ".panel-headline" in base
    assert "details.tech-disclosure" in base
    assert ".safety-badge" in base
    assert ".safety-strip" in base
    # Mobile shims stay alive after polish.
    assert "@media (max-width: 768px)" in base
    assert "@media (max-width: 480px)" in base
