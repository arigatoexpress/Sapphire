"""Small compatibility wrapper around feedparser.

Some clean CI-like environments can install ``feedparser`` without the legacy
``sgmllib`` shim it imports at module load time. Keep Sapphire's official-feed
parsers collectable in that case by falling back to a conservative stdlib RSS
and Atom reader.
"""

from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class FeedEntry(dict):
    """Dictionary entry that also supports feedparser-style attributes."""

    def __getattr__(self, key: str) -> Any:
        return self.get(key)


@dataclass(frozen=True)
class ParsedFeed:
    entries: list[FeedEntry]


def _load_feedparser() -> Any | None:
    try:
        import feedparser  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        if exc.name in {"feedparser", "sgmllib"}:
            return None
        raise
    return feedparser


def parse(text: str) -> Any:
    """Parse feed text with feedparser, falling back to stdlib XML parsing."""

    parser = _load_feedparser()
    if parser is not None:
        return parser.parse(text)
    return ParsedFeed(entries=_parse_stdlib_entries(text))


def _parse_stdlib_entries(text: str) -> list[FeedEntry]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    items = [element for element in root.iter() if _local_name(element.tag) == "item"]
    if not items:
        items = [element for element in root.iter() if _local_name(element.tag) == "entry"]
    return [_entry_from_element(element) for element in items]


def _entry_from_element(element: ET.Element) -> FeedEntry:
    published = _first_text(element, "pubDate", "published", "updated", "date")
    updated = _first_text(element, "updated")
    entry = FeedEntry(
        title=_first_text(element, "title"),
        link=_first_link(element),
        summary=_first_text(element, "summary", "description", "subtitle", "content"),
        description=_first_text(element, "description"),
        subtitle=_first_text(element, "subtitle"),
        id=_first_text(element, "id", "guid"),
        guid=_first_text(element, "guid"),
        published=published,
        updated=updated,
    )
    published_parsed = _parsed_time_tuple(published)
    updated_parsed = _parsed_time_tuple(updated)
    if published_parsed is not None:
        entry["published_parsed"] = published_parsed
    if updated_parsed is not None:
        entry["updated_parsed"] = updated_parsed
    return entry


def _first_text(element: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in element:
        if _local_name(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def _first_link(element: ET.Element) -> str:
    for child in element:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        return "".join(child.itertext()).strip()
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parsed_time_tuple(value: str) -> tuple[int, int, int, int, int, int, int, int, int] | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).utctimetuple()
