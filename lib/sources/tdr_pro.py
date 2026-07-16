"""The DeFi Report Pro podcast RSS source.

Public podcast feed: https://feeds.transistor.fm/the-defi-report
Each episode may expose a plain-text transcript via the ``podcast:transcript``
extension.  This adapter turns new episodes into markdown clippings that are
routed into the ``~/Knowledge`` vault by ``wiki/wiki_ingest.py``.

Live HTTP is gated by ``SAPPHIRE_TDR_PRO_LIVE=1`` to keep CI and dry-run
environments deterministic.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.source_quality.registry import SourceQualityEntry, register_source
from lib.source_quality.snr import SignalRecord

from . import SourceError, http_get_text, live_enabled, utc_now

# Register with the source-quality layer at import time.  Weekly macro research
# has a slower half-life than intraday TA signals; use a 168h (7-day) lookahead.
register_source(
    SourceQualityEntry(
        name="tdr_pro",
        lookahead_hours=168,
        description="The DeFi Report Pro podcast (public RSS + transcripts).",
        tags=("macro", "research", "podcast", "trading"),
    )
)

TDR_PRO_RSS_URL = "https://feeds.transistor.fm/the-defi-report"
TDR_PRO_DOMAIN = "https://thedefireport.io/"

_DEFAULT_TAGS = ["defi-report", "tdr-pro", "bitcoin", "macro", "clipping"]


@dataclass(frozen=True)
class TDRProEpisode:
    """One podcast episode from the TDR Pro feed."""

    guid: str
    title: str
    description: str
    url: str
    published_at: datetime
    episode: str | None = None
    duration_seconds: int | None = None
    transcript_url: str | None = None
    audio_url: str | None = None
    author: str = "Michael Nadeau"
    source: str = "tdr_pro"
    slug_override: str | None = None

    @property
    def slug(self) -> str:
        """File-name-safe slug, e.g. ``e28-portfolio-audit``."""
        if self.slug_override:
            return self.slug_override
        safe = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        prefix = f"e{self.episode}" if self.episode else "tdr"
        return f"{prefix}-{safe}"[:80].strip("-")

    @property
    def published_date(self) -> str:
        return self.published_at.date().isoformat()

    @property
    def duration_label(self) -> str:
        if not self.duration_seconds:
            return ""
        seconds = int(self.duration_seconds)
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def to_signal(self) -> SignalRecord:
        """Research episodes are macro/context signals; direction is neutral."""
        return SignalRecord(
            source=self.source,
            symbol="BTC",
            timestamp=self.published_at,
            direction="neutral",
            confidence=0.5,
        )

    def _index_label(self) -> str:
        return f"E{self.episode}" if self.episode else "Special"

    def to_index_entry(self) -> str:
        """Return one markdown list item linking to this episode."""
        links: list[str] = []
        if self.audio_url:
            links.append(f"[Audio]({self.audio_url})")
        if self.transcript_url:
            links.append(f"[Transcript]({self.transcript_url})")
        link_part = " · ".join(links)
        if link_part:
            link_part = f" — {link_part}"
        return (
            f"- **{self._index_label()}** — "
            f"[{self.title}]({self.slug}.md){link_part} — {self.published_date}"
        )

    def to_clipping(
        self,
        transcript: str | None = None,
        *,
        prev_episode: TDRProEpisode | None = None,
        next_episode: TDRProEpisode | None = None,
        index_path: str = "tdr-pro-index.md",
    ) -> str:
        """Render a markdown clipping with YAML frontmatter and hub links."""
        description_one_liner = (
            self.description.split("\n")[0] if self.description else "The DeFi Report episode."
        )
        fm: dict[str, Any] = {
            "title": self.title,
            "description": description_one_liner,
            "type": "clipping",
            "status": "seed",
            "domain": "Trading",
            "source": self.source,
            "url": self.url,
            "author": self.author,
            "published": self.published_date,
        }
        if self.episode:
            fm["episode"] = f"E{self.episode}"
        if self.duration_label:
            fm["duration"] = self.duration_label
        if self.audio_url:
            fm["audio_url"] = self.audio_url
        if self.transcript_url:
            fm["transcript_url"] = self.transcript_url
        fm["tags"] = f"[{', '.join(_DEFAULT_TAGS)}]"
        today = utc_now().date().isoformat()
        fm["created"] = today
        fm["modified"] = today

        def _yaml_value(value: Any) -> str:
            text = str(value)
            # Quote everything double-quoted for frontmatter safety.
            escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'

        frontmatter = "---\n" + "\n".join(f"{k}: {_yaml_value(v)}" for k, v in fm.items()) + "\n---\n"

        body_lines: list[str] = [
            f"# {self.title}",
            "",
            f"> {description_one_liner}",
            "",
        ]
        if self.transcript_url:
            body_lines.append(f"- Transcript: {self.transcript_url}")
        if self.audio_url:
            body_lines.append(f"- Audio: {self.audio_url}")
        body_lines.append(f"- Published: {self.published_date}")
        body_lines.append("")

        if transcript:
            body_lines.append("## Transcript")
            body_lines.append("")
            body_lines.append(transcript.strip())
            body_lines.append("")
        else:
            body_lines.append("## Show notes")
            body_lines.append("")
            body_lines.append(self.description.strip())
            body_lines.append("")

        # Hub navigation links.
        body_lines.append("---")
        body_lines.append("")
        body_lines.append("## TDR Pro Hub")
        body_lines.append("")
        if prev_episode:
            body_lines.append(
                f"- ← Previous: [{prev_episode._index_label()} — {prev_episode.title}]"
                f"({prev_episode.slug}.md)"
            )
        else:
            body_lines.append("- ← Previous: (none yet)")
        if next_episode:
            body_lines.append(
                f"- → Next: [{next_episode._index_label()} — {next_episode.title}]"
                f"({next_episode.slug}.md)"
            )
        else:
            body_lines.append("- → Next: (latest episode)")
        body_lines.append(f"- 📋 Master index: [All TDR Pro episodes]({index_path})")
        body_lines.append("")

        return frontmatter + "\n".join(body_lines)


@dataclass
class TDRProSource:
    """Poll The DeFi Report podcast RSS and emit Knowledge clippings."""

    name: str = "tdr_pro"
    label: str = "The DeFi Report Pro podcast"
    url: str = TDR_PRO_RSS_URL
    inbox_dir: Path = field(default_factory=lambda: Path.home() / "Knowledge" / "0-Inbox" / "Clippings")
    fetcher: Any = None

    def __post_init__(self) -> None:
        self.inbox_dir = Path(self.inbox_dir)
        if self.fetcher is None:
            self.fetcher = http_get_text

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------
    def _fetch(self, url: str) -> str:
        if not live_enabled("TDR_PRO"):
            raise SourceError(
                "SAPPHIRE_TDR_PRO_LIVE=1 is required to fetch The DeFi Report feed; "
                "pass a local fixture or set the env var."
            )
        return self.fetcher(url)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    @staticmethod
    def _first_text(element: ET.Element, *names: str) -> str:
        wanted = {name.lower() for name in names}
        for child in element:
            if TDRProSource._local_name(child.tag) in wanted:
                return "".join(child.itertext()).strip()
        return ""

    @staticmethod
    def _first_attr(element: ET.Element, tag_name: str, attr_name: str) -> str:
        for child in element:
            if TDRProSource._local_name(child.tag) == tag_name.lower():
                value = child.attrib.get(attr_name)
                if value:
                    return value.strip()
        return ""

    @staticmethod
    def _parse_duration(value: str) -> int | None:
        text = (value or "").strip()
        if not text:
            return None
        # HH:MM:SS or MM:SS
        parts = text.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(text)
        except ValueError:
            return None

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        """Best-effort RSS date parser (RFC 2822 / ISO)."""
        text = str(value or "").strip()
        if not text:
            return utc_now()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
        import email.utils

        try:
            parsed = email.utils.parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except (TypeError, ValueError):
            pass
        return utc_now()

    @staticmethod
    def _strip_html(value: str) -> str:
        text = str(value or "")
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def parse(self, xml_text: str) -> list[TDRProEpisode]:
        """Parse RSS XML into :class:`TDRProEpisode` objects (newest first)."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise SourceError(f"failed to parse TDR Pro RSS: {exc}") from exc

        channel = root.find("channel")
        if channel is None:
            raise SourceError("TDR Pro RSS has no <channel>")

        episodes: list[TDRProEpisode] = []
        for item in channel.findall("item"):
            title = self._strip_html(self._first_text(item, "title"))
            guid = self._first_text(item, "guid") or self._first_text(item, "link")
            link = self._first_text(item, "link") or self._first_attr(item, "enclosure", "url")
            if not guid:
                continue

            description = self._strip_html(self._first_text(item, "description"))
            if not description:
                description = self._strip_html(self._first_text(item, "content:encoded"))

            published_at = self._parse_datetime(self._first_text(item, "pubDate"))
            episode = self._first_text(item, "episode")
            duration = self._parse_duration(self._first_text(item, "duration"))
            transcript_url = self._first_attr(item, "transcript", "url")
            audio_url = self._first_attr(item, "enclosure", "url")
            author = self._first_text(item, "author") or "Michael Nadeau"

            episodes.append(
                TDRProEpisode(
                    guid=guid,
                    title=title or "Untitled TDR episode",
                    description=description,
                    url=link or TDR_PRO_RSS_URL,
                    published_at=published_at,
                    episode=episode or None,
                    duration_seconds=duration,
                    transcript_url=transcript_url or None,
                    audio_url=audio_url or None,
                    author=author,
                )
            )
        return episodes

    # ------------------------------------------------------------------
    # Live fetch + clipping generation
    # ------------------------------------------------------------------
    def fetch_transcript(self, episode: TDRProEpisode) -> str | None:
        """Fetch the plain-text transcript when the episode advertises one."""
        if not episode.transcript_url:
            return None
        text = self._fetch(episode.transcript_url)
        return text.strip() if text else None

    def fetch_transcripts(
        self,
        episodes: list[TDRProEpisode],
    ) -> dict[str, str | None]:
        """Fetch transcripts for ``episodes`` that advertise them.

        Returns a mapping ``episode.guid -> transcript | None``.
        """
        out: dict[str, str | None] = {}
        for ep in episodes:
            if not ep.transcript_url:
                out[ep.guid] = None
                continue
            try:
                out[ep.guid] = self.fetch_transcript(ep)
            except SourceError:
                out[ep.guid] = None
        return out

    def poll(
        self,
        *,
        since: datetime | None = None,
        limit: int = 10,
    ) -> list[TDRProEpisode]:
        """Fetch the RSS feed and return recent episodes (no transcripts)."""
        xml_text = self._fetch(self.url)
        episodes = self.parse(xml_text)
        if since is not None:
            episodes = [ep for ep in episodes if ep.published_at >= since.astimezone(UTC)]
        return episodes[:limit]

    def write_clippings(
        self,
        episodes: list[TDRProEpisode],
        *,
        transcripts: dict[str, str | None] | None = None,
        dry_run: bool = False,
        index_path: str = "tdr-pro-index.md",
    ) -> list[Path]:
        """Write markdown clippings for ``episodes`` into ``inbox_dir``.

        Each clipping includes previous/next navigation links computed from the
        chronological order of the provided episode list.
        """
        transcripts = transcripts or {}

        def _sort_key(ep: TDRProEpisode) -> tuple:
            try:
                ep_num = int(ep.episode) if ep.episode else 0
            except ValueError:
                ep_num = 0
            return (ep.published_at, ep_num)

        sorted_eps = sorted(episodes, key=_sort_key)
        ep_index = {ep.guid: i for i, ep in enumerate(sorted_eps)}

        written: list[Path] = []
        for ep in episodes:
            transcript = transcripts.get(ep.guid)
            idx = ep_index[ep.guid]
            prev_ep = sorted_eps[idx - 1] if idx > 0 else None
            next_ep = sorted_eps[idx + 1] if idx < len(sorted_eps) - 1 else None
            markdown = ep.to_clipping(
                transcript=transcript or None,
                prev_episode=prev_ep,
                next_episode=next_ep,
                index_path=index_path,
            )
            filename = f"{ep.slug}.md"
            path = self.inbox_dir / filename
            if not dry_run:
                self.inbox_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(markdown, encoding="utf-8")
            written.append(path)
        return written

    def write_hub_index(
        self,
        episodes: list[TDRProEpisode],
        *,
        index_path: Path | None = None,
        dry_run: bool = False,
    ) -> Path:
        """Write or update the master TDR Pro episode index markdown page.

        Episodes are sorted newest-first by episode number, falling back to
        publication date.  The default ``index_path`` is the parent of
        ``inbox_dir`` so the index lives next to the clippings it catalogs.
        """
        if index_path is None:
            index_path = self.inbox_dir.parent / "tdr-pro-index.md"
        else:
            index_path = Path(index_path)

        def _sort_key(ep: TDRProEpisode) -> tuple:
            try:
                ep_num = int(ep.episode) if ep.episode else 0
            except ValueError:
                ep_num = 0
            return (ep.published_at, ep_num)

        sorted_eps = sorted(episodes, key=_sort_key, reverse=True)
        today = utc_now().date().isoformat()
        tags_value = ", ".join(_DEFAULT_TAGS)
        fm_lines = [
            "---",
            'title: "TDR Pro Episode Index"',
            'description: "Master index of The DeFi Report Pro podcast episodes."',
            'type: "index"',
            'status: "seed"',
            'domain: "Trading"',
            'source: "tdr_pro"',
            f'tags: "[{tags_value}]"',
            f'created: "{today}"',
            f'modified: "{today}"',
            "---",
        ]
        body = [
            "# TDR Pro Episode Index",
            "",
            "Master list of [The DeFi Report Pro](https://thedefireport.io/) podcast episodes ingested into the Knowledge vault.",
            "",
            f"**Episodes indexed:** {len(sorted_eps)}",
            "",
            "## Episodes",
            "",
        ]
        body.extend(ep.to_index_entry() for ep in sorted_eps)
        body.extend([
            "",
            "---",
            "",
            "## RSS source",
            "",
            f"- Feed: <{TDR_PRO_RSS_URL}>",
            f"- Website: <{TDR_PRO_DOMAIN}>",
            "",
        ])

        markdown = "\n".join(fm_lines) + "\n" + "\n".join(body) + "\n"
        if not dry_run:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(markdown, encoding="utf-8")
        return index_path

    def latest_clippings(
        self,
        *,
        since: datetime | None = None,
        limit: int = 10,
        dry_run: bool = False,
    ) -> list[Path]:
        """One-shot: poll feed, fetch transcripts, write clippings."""
        episodes = self.poll(since=since, limit=limit)
        transcripts = self.fetch_transcripts(episodes)
        return self.write_clippings(episodes, transcripts=transcripts, dry_run=dry_run)


__all__ = [
    "TDR_PRO_DOMAIN",
    "TDR_PRO_RSS_URL",
    "TDRProEpisode",
    "TDRProSource",
]
