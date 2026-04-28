from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = REPO_ROOT / "web" / "customer"
INDEX_HTML = SITE_DIR / "index.html"
STYLES_CSS = SITE_DIR / "assets" / "styles.css"


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[dict[str, str]] = []
        self.anchors: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.inline_handlers: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        if "id" in attr_map:
            self.ids.add(attr_map["id"])
        if tag == "link":
            self.links.append(attr_map)
        if tag == "a":
            self.anchors.append(attr_map)
        if tag == "script":
            self.scripts.append(attr_map)
        self.inline_handlers.extend(k for k in attr_map if k.startswith("on"))


def _body() -> str:
    assert INDEX_HTML.is_file()
    return INDEX_HTML.read_text(encoding="utf-8")


def _parsed() -> Parser:
    parser = Parser()
    parser.feed(_body())
    return parser


def test_customer_site_files_exist() -> None:
    assert INDEX_HTML.is_file()
    assert STYLES_CSS.is_file()


def test_customer_site_has_no_javascript_or_external_resources() -> None:
    parsed = _parsed()
    assert parsed.scripts == []
    assert parsed.inline_handlers == []
    body = _body()
    assert "https://" not in body
    assert "http://" not in body
    css = STYLES_CSS.read_text(encoding="utf-8")
    assert "url(http" not in css
    assert "@import" not in css


def test_customer_site_required_sections_and_safety_copy() -> None:
    parsed = _parsed()
    assert {"products", "pricing", "sample", "trust", "beta"}.issubset(parsed.ids)
    body = _body()
    for required in (
        "mock=true",
        "x-sapphire-billed: 0",
        "SAPPHIRE_CUSTOMER_API_LIVE=1",
        "no customer data",
        "POST /v1/private-beta/request",
    ):
        assert required in body


def test_customer_site_doc_links_resolve() -> None:
    parsed = _parsed()
    for anchor in parsed.anchors:
        href = anchor.get("href", "")
        assert href
        assert not re.match(r"^https?://", href)
        if href.startswith("../"):
            assert (SITE_DIR / href).resolve().exists(), href
