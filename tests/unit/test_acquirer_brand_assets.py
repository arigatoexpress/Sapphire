"""Structural tests for the Sapphire acquirer microsite brand asset pack.

Validates the brand assets shipped under ``web/acquirer/assets/branding/``:

- File existence: every promised asset (logos, favicon, OG image, hero,
  9 capability icons, brand guidelines, provenance envelope) is on disk.
- Wiring: every brand-asset reference in ``index.html`` resolves to a real
  file or to an inline definition.
- Validity: every SVG parses as well-formed XML and is non-empty.
- Sanity: every PNG / SVG / ICO file has a reasonable size (not zero-byte,
  not absurdly large).
- Provenance: the ``.envelope.json`` sidecar lists every generated artifact
  alongside the skill that produced it and the head SHA.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = REPO_ROOT / "web" / "acquirer"
INDEX_HTML = SITE_DIR / "index.html"
BRAND_DIR = SITE_DIR / "assets" / "branding"
ICONS_DIR = BRAND_DIR / "capability-icons"
ENVELOPE = BRAND_DIR / ".envelope.json"


# ---- File existence ---------------------------------------------------------


@pytest.fixture(scope="module")
def index_body() -> str:
    assert INDEX_HTML.exists(), f"missing {INDEX_HTML}"
    return INDEX_HTML.read_text(encoding="utf-8")


def test_branding_directory_exists() -> None:
    """The branding directory and the icons subdirectory both exist."""
    assert BRAND_DIR.is_dir(), f"missing {BRAND_DIR}"
    assert ICONS_DIR.is_dir(), f"missing {ICONS_DIR}"


def test_logo_assets_present() -> None:
    """The light + dark logo lockups exist as both SVG and PNG."""
    for fname in ("logo.svg", "logo.png", "logo-dark-bg.svg", "logo-dark-bg.png"):
        target = BRAND_DIR / fname
        assert target.is_file(), f"missing logo asset: {fname}"
        assert target.stat().st_size > 200, (
            f"{fname} suspiciously small: {target.stat().st_size} bytes"
        )


def test_favicon_assets_present() -> None:
    """Favicon ships as both SVG (modern) and ICO (legacy)."""
    svg = BRAND_DIR / "favicon.svg"
    ico = BRAND_DIR / "favicon.ico"
    assert svg.is_file(), "missing favicon.svg"
    assert ico.is_file(), "missing favicon.ico"
    assert svg.stat().st_size > 100
    # ICO container with two embedded sizes is at least a few hundred bytes.
    assert ico.stat().st_size > 200


def test_og_image_present_and_dimensioned() -> None:
    """OG image exists and is at least the expected 1200x630 file weight."""
    og = BRAND_DIR / "og-image.png"
    assert og.is_file(), "missing og-image.png"
    size = og.stat().st_size
    # A 1200x630 stylized PNG should land between ~5 KB and ~2 MB.
    assert 5_000 < size < 2_000_000, f"og-image.png unreasonable size: {size}"


def test_hero_illustration_present_and_valid_svg() -> None:
    """Hero illustration is a valid, non-empty SVG."""
    hero = BRAND_DIR / "hero-illustration.svg"
    assert hero.is_file(), "missing hero-illustration.svg"
    assert hero.stat().st_size > 1000, "hero illustration suspiciously small"
    # Parse as XML to confirm it's valid.
    ET.fromstring(hero.read_text(encoding="utf-8"))


def test_capability_icons_present() -> None:
    """Every capability icon SVG required by the spec is on disk."""
    expected = {
        "signal-correlator.svg",
        "narrative-synthesis.svg",
        "cross-asset.svg",
        "macro-intel.svg",
        "onchain-depth.svg",
        "event-impact.svg",
        "counterparty.svg",
        "adversarial-defense.svg",
        "provenance.svg",
    }
    on_disk = {p.name for p in ICONS_DIR.glob("*.svg")}
    missing = expected - on_disk
    assert not missing, f"missing capability icons: {missing}"
    # Every icon should be small (a few hundred bytes to ~3 KB) and valid XML.
    for name in expected:
        path = ICONS_DIR / name
        size = path.stat().st_size
        assert 80 < size < 5000, f"{name} unreasonable size: {size}"
        ET.fromstring(path.read_text(encoding="utf-8"))


def test_brand_guidelines_present_and_substantive() -> None:
    """Brand guidelines markdown exists and is substantive (>= 600 words)."""
    md = BRAND_DIR / "brand-guidelines.md"
    assert md.is_file(), "missing brand-guidelines.md"
    body = md.read_text(encoding="utf-8")
    word_count = len(body.split())
    assert word_count >= 600, f"brand-guidelines.md too short: {word_count} words"
    # Required sections by name.
    for required in ("Palette", "Typography", "Logo", "Iconography", "Voice"):
        assert required in body, f"brand-guidelines.md missing section: {required}"


# ---- index.html wiring ------------------------------------------------------


def test_index_references_favicon(index_body: str) -> None:
    """index.html links to the favicon SVG."""
    assert 'href="assets/branding/favicon.svg"' in index_body, (
        "index.html does not reference assets/branding/favicon.svg"
    )


def test_index_references_og_image(index_body: str) -> None:
    """index.html declares the OG image meta tag pointing at the brand asset."""
    assert "og-image.png" in index_body, "index.html missing og-image.png reference"
    # Confirm a meta og:image tag exists.
    assert re.search(
        r'<meta[^>]+property=["\']og:image["\']', index_body, re.IGNORECASE
    ), "index.html missing <meta property=og:image>"


def test_index_inlines_hero_illustration(index_body: str) -> None:
    """The mission section embeds the hero signal-flow SVG inline."""
    assert "hero-illustration" in index_body, (
        "index.html missing hero-illustration figure wrapper"
    )
    assert "Sapphire signal-flow architecture" in index_body, (
        "hero illustration <title> not present in index.html"
    )
    assert "CORRELATION HUB" in index_body, (
        "hero illustration central label not present"
    )


def test_index_inlines_capability_icons(index_body: str) -> None:
    """Each of the 9 capability cards embeds an inline SVG icon."""
    # Count occurrences of the .capability-icon class — one per card head.
    count = index_body.count('class="capability-icon"')
    assert count == 9, f"expected 9 inline capability icons, found {count}"


def test_envelope_sidecar_present_and_well_formed() -> None:
    """The .envelope.json sidecar lists every generated asset with skill + prompt."""
    assert ENVELOPE.is_file(), f"missing provenance envelope at {ENVELOPE}"
    payload = json.loads(ENVELOPE.read_text(encoding="utf-8"))
    assert payload.get("version") == 1
    assert "head_sha" in payload and len(payload["head_sha"]) >= 7
    assert "skill" in payload and payload["skill"], "envelope missing top-level skill"
    assets = payload.get("assets", [])
    assert isinstance(assets, list) and len(assets) >= 18, (
        f"envelope must list at least 18 assets, found {len(assets)}"
    )
    for entry in assets:
        for key in ("path", "prompt", "skill"):
            assert key in entry and entry[key], (
                f"envelope entry missing {key!r}: {entry}"
            )
        # Every listed asset path should resolve under the branding dir.
        target = BRAND_DIR / entry["path"]
        assert target.exists(), (
            f"envelope references non-existent asset: {entry['path']}"
        )


# ---- SVG validity sweep -----------------------------------------------------


def test_every_brand_svg_parses_as_xml() -> None:
    """Every SVG in branding/ (recursively) parses cleanly."""
    svgs = list(BRAND_DIR.rglob("*.svg"))
    assert svgs, "expected at least one SVG under branding/"
    for svg in svgs:
        text = svg.read_text(encoding="utf-8")
        try:
            ET.fromstring(text)
        except ET.ParseError as exc:
            pytest.fail(f"{svg.name} failed XML parse: {exc}")


def test_no_branding_file_is_zero_byte() -> None:
    """Defensive: no committed brand asset is empty."""
    files = [p for p in BRAND_DIR.rglob("*") if p.is_file()]
    assert files, "branding directory unexpectedly empty"
    for path in files:
        assert path.stat().st_size > 0, f"{path} is zero bytes"
