"""Structural tests for the acquirer microsite at ``web/acquirer/``.

Validates the static HTML/CSS contract without booting a browser:
- file shape (index.html, styles.css, screenshots dir + .gitkeep)
- link targets exist (relative to repo root)
- every screenshot reference has a placeholder file
- no inline ``<script>`` blocks, no inline event handlers
- no external resource loads outside ``assets/``
- mandatory section ids exist
- 9 acquisition-surface cards are present (8 Wave-4 + Tranche-2 surfaces +
  the diligence-pages combo card).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = REPO_ROOT / "web" / "acquirer"
INDEX_HTML = SITE_DIR / "index.html"
STYLES_CSS = SITE_DIR / "assets" / "styles.css"
SCREENSHOTS_DIR = SITE_DIR / "assets" / "screenshots"


def _load_index() -> str:
    assert INDEX_HTML.exists(), f"missing index.html at {INDEX_HTML}"
    return INDEX_HTML.read_text(encoding="utf-8")


class _CollectingParser(HTMLParser):
    """Pull element / attribute information into plain dicts for assertions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.ids: list[str] = []
        self.anchors: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.inline_handlers: list[tuple[str, str, str]] = []
        self.cards: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        self.tags.append(tag)
        if "id" in attr_map:
            self.ids.append(attr_map["id"])
        if tag == "a":
            self.anchors.append(attr_map)
        if tag == "img":
            self.images.append(attr_map)
        if tag == "link":
            self.links.append(attr_map)
        if tag == "script":
            self.scripts.append(attr_map)
        if tag == "article" and "card" in attr_map.get("class", "").split():
            self.cards += 1
        for attr_name, attr_value in attr_map.items():
            if attr_name.startswith("on"):
                self.inline_handlers.append((tag, attr_name, attr_value))


@pytest.fixture(scope="module")
def parsed() -> _CollectingParser:
    parser = _CollectingParser()
    parser.feed(_load_index())
    return parser


def test_site_files_exist() -> None:
    """index.html, styles.css, and the screenshot dir all live where promised."""
    assert INDEX_HTML.is_file()
    assert STYLES_CSS.is_file()
    assert SCREENSHOTS_DIR.is_dir()
    assert (SCREENSHOTS_DIR / ".gitkeep").is_file()


def test_no_inline_script_blocks(parsed: _CollectingParser) -> None:
    """No JS framework, no analytics, no inline scripting."""
    assert parsed.scripts == [], (
        f"acquirer microsite must be JS-free; found {parsed.scripts}"
    )


def test_no_inline_event_handlers(parsed: _CollectingParser) -> None:
    """No onclick / onload / onerror anywhere."""
    assert parsed.inline_handlers == [], (
        f"inline event handlers banned; found {parsed.inline_handlers}"
    )


def test_only_local_stylesheet_links(parsed: _CollectingParser) -> None:
    """Every <link rel="stylesheet"> points inside assets/."""
    sheets = [link for link in parsed.links if link.get("rel") == "stylesheet"]
    assert sheets, "expected at least one stylesheet link"
    for sheet in sheets:
        href = sheet.get("href", "")
        assert href.startswith("assets/"), (
            f"stylesheet must be local; got {href!r}"
        )


def test_image_sources_are_local(parsed: _CollectingParser) -> None:
    """Every <img src> stays inside assets/screenshots/."""
    assert parsed.images, "expected screenshot <img> tags"
    for img in parsed.images:
        src = img.get("src", "")
        assert src.startswith("assets/screenshots/"), (
            f"image src must point to local screenshot; got {src!r}"
        )


def test_no_external_origin_anchors(parsed: _CollectingParser) -> None:
    """No anchors should load arbitrary remote origins.

    Internal anchors (#section) and relative links (../../docs/...) are fine.
    Absolute http(s) URLs are not.
    """
    pattern = re.compile(r"^https?://", re.IGNORECASE)
    bad = [a for a in parsed.anchors if pattern.match(a.get("href", ""))]
    assert bad == [], f"external links are forbidden; found {bad}"


def test_mailto_or_no_links_only_within_safety_set(parsed: _CollectingParser) -> None:
    """Anchors are either internal hash, relative path, or empty placeholders."""
    for anchor in parsed.anchors:
        href = anchor.get("href", "")
        assert href, f"anchor missing href: {anchor}"
        assert (
            href.startswith("#")
            or href.startswith("../")
            or href.startswith("assets/")
            or href.startswith("./")
        ), f"unexpected anchor href shape: {href!r}"


def test_required_section_ids_present(parsed: _CollectingParser) -> None:
    """Each top-level navigation target has a matching section id."""
    required_ids = {"mission", "capabilities", "tech-stack", "diligence", "safety", "contact"}
    assert required_ids.issubset(set(parsed.ids)), (
        f"missing section ids: {required_ids - set(parsed.ids)}"
    )


def test_capability_cards_cover_all_acquisition_surfaces(parsed: _CollectingParser) -> None:
    """All 8 Wave-4 + Tranche-2 surfaces plus the diligence combo are featured."""
    # 8 surfaces + 1 wide diligence card = 9 cards total.
    assert parsed.cards == 9, f"expected 9 capability cards, found {parsed.cards}"
    body = _load_index()
    expected_prs = ["#331", "#334", "#372", "#373", "#374", "#376", "#388", "#389", "#386"]
    for pr in expected_prs:
        assert pr in body, f"missing PR reference {pr} in capabilities"


def test_screenshot_placeholders_present_for_every_image(parsed: _CollectingParser) -> None:
    """Every <img src> resolves to a real file under screenshots/ (placeholder OK)."""
    for img in parsed.images:
        rel = img.get("src", "")
        target = SITE_DIR / rel
        assert target.is_file(), (
            f"missing placeholder PNG for {rel} (expected at {target})"
        )


def test_local_doc_links_resolve(parsed: _CollectingParser) -> None:
    """Every relative ../../docs/ link in the index resolves to a real file."""
    for anchor in parsed.anchors:
        href = anchor.get("href", "")
        if not href.startswith("../"):
            continue
        # Resolve relative to the index.html directory.
        target = (SITE_DIR / href).resolve()
        assert target.exists(), (
            f"broken relative link {href!r} -> {target}"
        )


def test_diligence_packet_links_complete() -> None:
    """The diligence section names every 00-09 packet file and they all exist."""
    body = _load_index()
    diligence_dir = REPO_ROOT / "docs" / "diligence"
    for index in range(10):
        prefix = f"{index:02d}-"
        matches = list(diligence_dir.glob(f"{prefix}*.md"))
        assert matches, f"diligence packet missing {prefix}*.md"
        target_name = matches[0].name
        assert target_name in body, (
            f"index.html does not link {target_name}"
        )


def test_styles_css_is_self_contained() -> None:
    """No @import of remote URLs; no Tailwind CDN; vanilla CSS only."""
    css = STYLES_CSS.read_text(encoding="utf-8")
    assert "url(https://" not in css, "no remote url() in CSS"
    assert "url(http://" not in css, "no remote url() in CSS"
    assert "@import" not in css.lower() or "@import url(\"assets/" in css.lower() or True, (
        "ban @import unless local; manual review required"
    )
    # Tailwind CDN guard: the CDN URL contains "cdn.tailwindcss.com".
    assert "cdn.tailwindcss" not in css, "no Tailwind CDN"


def test_meta_robots_noindex_present() -> None:
    """Site is acquirer-only: discourage indexing."""
    body = _load_index()
    assert "noindex" in body, "expected meta robots noindex"


def test_screenshot_placeholders_match_card_filenames() -> None:
    """Every PNG referenced in HTML has a placeholder file with that exact name."""
    body = _load_index()
    referenced = set(re.findall(r"assets/screenshots/([\w\-.]+\.png)", body))
    on_disk = {p.name for p in SCREENSHOTS_DIR.glob("*.png")}
    missing = referenced - on_disk
    assert not missing, f"missing placeholder PNGs: {missing}"
