"""The DeFi Report Pro member-email source.

TDR Pro delivers members-only research and portfolio updates by email every
Wednesday. This adapter searches the authenticated Gmail inbox for those
messages, extracts links (portfolio Google Sheet, research posts), and writes
markdown clippings into the ``~/Knowledge`` vault.

Live access is gated by ``SAPPHIRE_TDR_PRO_LIVE=1`` AND
``SAPPHIRE_TDR_PRO_EMAIL_LIVE=1``. Gmail credentials are read from:

* ``GMAIL_CREDENTIALS_PATH`` env / secret — OAuth 2.0 desktop credentials JSON
* ``GMAIL_TOKEN_PATH`` env / secret — OAuth token JSON (created after first
  interactive auth flow; never committed)

No credentials are handled by this agent. The code is shipped inert and becomes
active only after Ari completes the OAuth flow and stores the token.
"""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.source_quality.registry import SourceQualityEntry, register_source
from lib.source_quality.snr import SignalRecord

from . import SourceError, live_enabled, secret_value, utc_now

register_source(
    SourceQualityEntry(
        name="tdr_pro_email",
        lookahead_hours=168,
        description="The DeFi Report Pro member email (portfolio + research links).",
        tags=("macro", "research", "portfolio", "trading"),
    )
)

# Likely sender addresses / domains for the Wednesday Pro email. Adjust as
# needed once real messages are inspected.
TDR_PRO_EMAIL_SENDERS = (
    "michael@thedefireport.com",
    "noreply@thedefireport.beehiiv.com",
    "hello@thedefireport.com",
)
TDR_PRO_EMAIL_DOMAINS = ("thedefireport.com", "thedefireport.beehiiv.com")

_DEFAULT_TAGS = ["defi-report", "tdr-pro", "bitcoin", "macro", "clipping", "portfolio"]

_LINK_RE = re.compile(r"https?://[^\s<>\"'`{}|\[\]]+")


def _link_from_href(text: str) -> list[str]:
    """Extract URLs from raw text and ``<a href=...>`` fragments."""
    found: list[str] = []
    # Explicit hrefs first.
    for m in re.finditer(r'href=["\'](https?://[^"\']+)["\']', text, re.IGNORECASE):
        found.append(m.group(1))
    # Bare URLs next.
    for m in _LINK_RE.finditer(text):
        found.append(m.group(0).rstrip(",.;:)\"'"))
    return found


def _extract_google_sheet_links(text: str) -> list[str]:
    return [u for u in _link_from_href(text) if "docs.google.com/spreadsheets" in u]


def _extract_research_links(text: str) -> list[str]:
    return [u for u in _link_from_href(text) if "thedefireport.io" in u]


def _extract_all_links(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in _link_from_href(text):
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _body_text(payload: dict[str, Any]) -> str:
    """Best-effort extraction of readable text from a Gmail message payload."""
    mime_type = (payload.get("mimeType") or "").lower()
    data = payload.get("body", {}).get("data")
    if data:
        raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if mime_type == "text/plain":
            return raw
        if mime_type == "text/html":
            return _html_to_text(raw)
        return raw

    parts = payload.get("parts") or []
    # Prefer plain text, fall back to html converted to text.
    for part in parts:
        if (part.get("mimeType") or "").lower() == "text/plain":
            text = _body_text(part)
            if text:
                return text
    for part in parts:
        if (part.get("mimeType") or "").lower() == "text/html":
            text = _body_text(part)
            if text:
                return text
    # Recursive fallback.
    for part in parts:
        text = _body_text(part)
        if text:
            return text
    return ""


def _html_to_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    # Preserve paragraph breaks while collapsing other whitespace.
    text = text.replace("\n", "\x00")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\x00", "\n")
    return text.strip()


@dataclass(frozen=True)
class TDRProEmailItem:
    """One TDR Pro member email reduced to its extractable links and summary."""

    message_id: str
    thread_id: str
    subject: str
    sender: str
    published_at: datetime
    body_text: str
    links: tuple[str, ...]
    sheet_links: tuple[str, ...]
    research_links: tuple[str, ...]
    source: str = "tdr_pro_email"

    @property
    def slug(self) -> str:
        safe = re.sub(r"[^a-z0-9]+", "-", self.subject.lower()).strip("-") or "tdr-pro-email"
        date = self.published_at.date().isoformat()
        return f"{date}-{safe}"[:100].strip("-")

    @property
    def published_date(self) -> str:
        return self.published_at.date().isoformat()

    @property
    def portfolio_link(self) -> str | None:
        return self.sheet_links[0] if self.sheet_links else None

    def to_signal(self) -> SignalRecord:
        """Member email is context / portfolio update — direction is neutral."""
        return SignalRecord(
            source=self.source,
            symbol="BTC",
            timestamp=self.published_at,
            direction="neutral",
            confidence=0.5,
        )

    def to_clipping(self) -> str:
        description = self.subject
        fm: dict[str, Any] = {
            "title": f"TDR Pro — {self.subject}",
            "description": description,
            "type": "clipping",
            "status": "seed",
            "domain": "Trading",
            "source": self.source,
            "sender": self.sender,
            "published": self.published_date,
        }
        if self.portfolio_link:
            fm["portfolio_url"] = self.portfolio_link
        fm["tags"] = f"[{', '.join(_DEFAULT_TAGS)}]"
        today = utc_now().date().isoformat()
        fm["created"] = today
        fm["modified"] = today

        def _yaml_value(value: Any) -> str:
            text = str(value)
            escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'

        frontmatter = (
            "---\n" + "\n".join(f"{k}: {_yaml_value(v)}" for k, v in fm.items()) + "\n---\n"
        )

        lines = [
            f"# TDR Pro — {self.subject}",
            "",
            f"> From: {self.sender}  ",
            f"> Date: {self.published_date}",
            "",
            "## Links",
            "",
        ]
        if self.portfolio_link:
            lines.append(f"- [Portfolio Google Sheet]({self.portfolio_link})")
        for link in self.research_links:
            lines.append(f"- [Research]({link})")
        for link in self.links:
            if link not in self.sheet_links and link not in self.research_links:
                lines.append(f"- {link}")
        lines.extend(["", "## Summary", "", self.body_text[:2000], ""])
        return frontmatter + "\n".join(lines)


@dataclass
class TDRProEmailSource:
    """Poll Gmail for The DeFi Report Pro member emails and emit clippings."""

    name: str = "tdr_pro_email"
    label: str = "The DeFi Report Pro member email"
    inbox_dir: Path = field(
        default_factory=lambda: Path.home() / "Knowledge" / "0-Inbox" / "Clippings"
    )
    credentials_path: str | None = None
    token_path: str | None = None
    service_builder: Any | None = None

    def __post_init__(self) -> None:
        self.inbox_dir = Path(self.inbox_dir)
        if self.credentials_path is None:
            self.credentials_path = secret_value("GMAIL_CREDENTIALS_PATH") or str(
                Path.home() / ".sapphire" / "gmail-credentials.json"
            )
        if self.token_path is None:
            self.token_path = secret_value("GMAIL_TOKEN_PATH") or str(
                Path.home() / ".sapphire" / "gmail-token.json"
            )

    # ------------------------------------------------------------------
    # Credential / service helpers
    # ------------------------------------------------------------------
    def _live_allowed(self) -> bool:
        return live_enabled("TDR_PRO") and live_enabled("TDR_PRO_EMAIL")

    def _load_gmail_service(self) -> Any:
        """Lazy-load Gmail API; raise SourceError if deps or tokens missing."""
        if not self._live_allowed():
            raise SourceError("SAPPHIRE_TDR_PRO_LIVE=1 and SAPPHIRE_TDR_PRO_EMAIL_LIVE=1 required")

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise SourceError(
                "Gmail API dependencies missing; install google-api-python-client "
                "and google-auth-oauthlib: " + str(exc)
            ) from exc

        token_path = Path(self.token_path or "")
        creds: Any = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path))
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise SourceError(
                    f"Gmail token missing or invalid: {token_path}. "
                    "Run the OAuth flow locally and save the token file."
                )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _is_tdr_pro_sender(self, sender: str) -> bool:
        sender_lower = sender.lower()
        return any(addr.lower() in sender_lower for addr in TDR_PRO_EMAIL_SENDERS) or any(
            f"@{domain}" in sender_lower for domain in TDR_PRO_EMAIL_DOMAINS
        )

    def _parse_message(self, message: dict[str, Any]) -> TDRProEmailItem | None:
        payload = message.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", []) if "name" in h}
        sender = headers.get("from", "")
        subject = headers.get("subject", "")
        date_str = headers.get("date", "")

        if not self._is_tdr_pro_sender(sender):
            return None

        published = _parse_email_date(date_str)
        body = _body_text(payload)
        links = _extract_all_links(body)
        return TDRProEmailItem(
            message_id=message.get("id", ""),
            thread_id=message.get("threadId", ""),
            subject=subject,
            sender=sender,
            published_at=published,
            body_text=body[:5000],
            links=tuple(links),
            sheet_links=tuple(_extract_google_sheet_links(body)),
            research_links=tuple(_extract_research_links(body)),
        )

    # ------------------------------------------------------------------
    # Live fetch
    # ------------------------------------------------------------------
    def _search_query(self) -> str:
        domains_query = " OR ".join(f"from:{domain}" for domain in TDR_PRO_EMAIL_DOMAINS)
        return f"({domains_query}) subject:TDR Pro"

    def poll(
        self,
        *,
        since: datetime | None = None,
        limit: int = 10,
    ) -> list[TDRProEmailItem]:
        """Search Gmail and return TDR Pro member emails (newest first)."""
        service = (
            self._load_gmail_service() if self.service_builder is None else self.service_builder()
        )
        query = self._search_query()
        if since is not None:
            after = since.strftime("%Y/%m/%d")
            query = f"{query} after:{after}"

        try:
            results = (
                service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
            )
        except Exception as exc:
            raise SourceError(f"Gmail search failed: {exc}") from exc

        messages = results.get("messages", [])
        items: list[TDRProEmailItem] = []
        for msg_meta in messages:
            try:
                full = service.users().messages().get(userId="me", id=msg_meta["id"]).execute()
            except Exception as exc:
                raise SourceError(f"Gmail message fetch failed: {exc}") from exc
            item = self._parse_message(full)
            if item:
                items.append(item)
        return items

    # ------------------------------------------------------------------
    # Clipping generation
    # ------------------------------------------------------------------
    def write_clippings(
        self,
        items: list[TDRProEmailItem],
        *,
        dry_run: bool = False,
    ) -> list[Path]:
        written: list[Path] = []
        for item in items:
            markdown = item.to_clipping()
            filename = f"{item.slug}.md"
            path = self.inbox_dir / filename
            if not dry_run:
                self.inbox_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(markdown, encoding="utf-8")
            written.append(path)
        return written

    def latest_clippings(
        self,
        *,
        since: datetime | None = None,
        limit: int = 10,
        dry_run: bool = False,
    ) -> list[Path]:
        """One-shot: poll Gmail and write clippings."""
        items = self.poll(since=since, limit=limit)
        return self.write_clippings(items, dry_run=dry_run)


def _parse_email_date(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return utc_now()
    # Gmail dates are usually RFC 2822, e.g. "Wed, 15 Jul 2026 09:00:00 -0700".
    import email.utils

    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        pass
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return utc_now()


__all__ = [
    "TDRProEmailItem",
    "TDRProEmailSource",
    "TDR_PRO_EMAIL_DOMAINS",
    "TDR_PRO_EMAIL_SENDERS",
]
