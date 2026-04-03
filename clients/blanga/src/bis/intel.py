from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus

import feedparser

from bis.models import MarketEvent, MarketEventType, Person, make_urn
from bis.store import InMemoryMasterArena


@dataclass(frozen=True)
class NewsSourcePreference:
    source_key: str
    display_name: str
    publication_match: str
    domain: str
    sections: list[str]
    access_mode: str
    auto_ingest: bool
    notes: str = ""


CLIENT_NEWS_SOURCE_PREFERENCES: list[NewsSourcePreference] = [
    NewsSourcePreference(
        source_key="community_impact",
        display_name="Community Impact",
        publication_match="Community Impact",
        domain="communityimpact.com",
        sections=["business", "dining", "traffic"],
        access_mode="public",
        auto_ingest=True,
        notes="Primary local source per client feedback for vacancies/openings and new construction mentions.",
    ),
    NewsSourcePreference(
        source_key="austin_metro",
        display_name="Austin Metro",
        publication_match="Austin Metro",
        domain="",
        sections=["business", "dining", "traffic"],
        access_mode="public_assumed_confirm_url",
        auto_ingest=True,
        notes="Client requested source; confirm exact publication URL/domain before strict domain filtering.",
    ),
    NewsSourcePreference(
        source_key="austin_american_statesman",
        display_name="Austin American-Statesman",
        publication_match="Austin American-Statesman",
        domain="statesman.com",
        sections=["austin business"],
        access_mode="subscription_manual_reference",
        auto_ingest=False,
        notes="Useful source but typically paywalled; use manual links/notes, no automated content access assumptions.",
    ),
    NewsSourcePreference(
        source_key="austin_business_journal",
        display_name="Austin Business Journal",
        publication_match="Austin Business Journal",
        domain="bizjournals.com",
        sections=["austin business"],
        access_mode="subscription_manual_reference",
        auto_ingest=False,
        notes="Useful source but paywalled; manual reference only in beta.",
    ),
]


def news_source_preferences_as_dicts() -> list[dict[str, object]]:
    return [
        {
            "source_key": src.source_key,
            "display_name": src.display_name,
            "publication_match": src.publication_match,
            "domain": src.domain,
            "sections": list(src.sections),
            "access_mode": src.access_mode,
            "auto_ingest": src.auto_ingest,
            "notes": src.notes,
        }
        for src in CLIENT_NEWS_SOURCE_PREFERENCES
    ]


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _find_person_by_name(store: InMemoryMasterArena, full_name: str) -> Person | None:
    target = _norm(full_name)
    if not target:
        return None
    for person in store.people.values():
        current = _norm(person.full_name)
        if target == current or target in current or current in target:
            return person
    return None


def _entry_source_title(entry) -> str:
    source_obj = getattr(entry, "source", None)
    title = getattr(source_obj, "title", None) if source_obj is not None else None
    return str(title or "").strip()


def _entry_source_href(entry) -> str:
    source_obj = getattr(entry, "source", None)
    href = getattr(source_obj, "href", None) if source_obj is not None else None
    return str(href or "").strip()


def _matches_preferred_publication(entry, preferred_publications: list[str]) -> bool:
    if not preferred_publications:
        return True
    src_title = _norm(_entry_source_title(entry))
    src_href = _norm(_entry_source_href(entry))
    for pref in preferred_publications:
        needle = _norm(pref)
        if not needle:
            continue
        if needle in src_title or needle in src_href:
            return True
    return False


def _published_from_entry(entry) -> datetime:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed is None:
        return datetime.now(tz=UTC)
    return datetime(
        parsed.tm_year,
        parsed.tm_mon,
        parsed.tm_mday,
        parsed.tm_hour,
        parsed.tm_min,
        parsed.tm_sec,
        tzinfo=UTC,
    )


def _news_event_type_for_entry(*, title: str, query_term: str, person_name_map: dict[str, str]) -> MarketEventType:
    lowered_title = _norm(title)
    lowered_query = _norm(query_term)

    if lowered_query in person_name_map:
        return MarketEventType.CLIENT_NEWS

    expansion_terms = {
        "opens",
        "opening",
        "expands",
        "expansion",
        "headquarters",
        "facility",
        "distribution center",
        "plant",
        "relocates",
    }
    if any(term in lowered_title for term in expansion_terms):
        return MarketEventType.NEW_COMPANY

    return MarketEventType.INDUSTRY_NEWS


def _client_local_news_seed_queries() -> list[str]:
    # Client-specific focus: public local sources + vacancy/opening/new construction signals.
    return [
        "Community Impact Austin business retail vacancy",
        "Community Impact Austin dining opening restaurant",
        "Community Impact Austin traffic development retail",
        "Austin Metro business retail vacancy",
        "Austin Metro dining restaurant opening",
        "Austin Metro traffic new construction",
        "Austin Wendy's new construction",
        "Austin AutoZone new construction",
        "Austin retail tenant vacated",
    ]


def _default_news_queries(store: InMemoryMasterArena) -> list[str]:
    queries: list[str] = []
    for person in store.people.values():
        if person.full_name.strip():
            queries.append(person.full_name.strip())
    for prop in store.properties.values():
        if prop.tenant_brand.strip():
            queries.append(prop.tenant_brand.strip())
        if prop.submarket.strip():
            queries.append(f"{prop.submarket.strip()} retail")
        if prop.corridor.strip():
            queries.append(f"{prop.corridor.strip()} development")
    queries.extend(_client_local_news_seed_queries())
    queries.append("Austin single tenant net lease")
    queries.append("Austin retail redevelopment")
    unique: list[str] = []
    seen = set()
    for query in queries:
        normalized = _norm(query)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(query)
    return unique


_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+[a-z0-9#.\- ]+?\s(?:st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ln|lane|way|pkwy|parkway|hwy|highway|rr)\b",
    re.IGNORECASE,
)


def _extract_address_hint(text: str) -> str:
    match = _ADDRESS_RE.search(text or "")
    if not match:
        return ""
    return " ".join(match.group(0).split())


def _detect_signal_kind(title: str, summary: str) -> str:
    lowered = _norm(f"{title} {summary}")
    if any(term in lowered for term in ["vacate", "vacant", "closure", "closing", "shut down", "closed location"]):
        return "vacancy"
    if any(term in lowered for term in ["opens", "opening", "grand opening", "new location"]):
        return "opening"
    if any(term in lowered for term in ["new construction", "construction", "groundbreaking", "permit filed"]):
        return "new_construction"
    return "general"


def refresh_news_intelligence(
    store: InMemoryMasterArena,
    *,
    queries: list[str] | None = None,
    preferred_publications: list[str] | None = None,
    max_queries: int = 12,
    per_query_limit: int = 5,
    lookback_days: int = 21,
    require_address_for_actionable_signals: bool = True,
) -> list[MarketEvent]:
    if max_queries <= 0 or per_query_limit <= 0:
        return []

    query_terms = queries or _default_news_queries(store)
    query_terms = query_terms[:max_queries]
    cutoff = datetime.now(tz=UTC) - timedelta(days=max(0, lookback_days))

    person_name_map = {_norm(person.full_name): person.person_urn for person in store.people.values()}
    existing_urls = {event.source_url for event in store.market_events.values() if event.source_url}
    created_events: list[MarketEvent] = []
    publication_filters = preferred_publications or [
        src.publication_match for src in CLIENT_NEWS_SOURCE_PREFERENCES if src.auto_ingest
    ]

    for query_term in query_terms:
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(query_term + ' Austin retail')}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        entries = getattr(feed, "entries", [])[:per_query_limit]
        for entry in entries:
            if not _matches_preferred_publication(entry, publication_filters):
                continue
            title = str(getattr(entry, "title", "") or "").strip()
            source_url = str(getattr(entry, "link", "") or "").strip()
            if not title or not source_url:
                continue
            if source_url in existing_urls:
                continue

            observed_at = _published_from_entry(entry)
            if observed_at < cutoff:
                continue

            event_type = _news_event_type_for_entry(
                title=title,
                query_term=query_term,
                person_name_map=person_name_map,
            )
            owner_person_urn = person_name_map.get(_norm(query_term))
            summary = str(getattr(entry, "summary", "") or "").strip()
            publication_title = _entry_source_title(entry)
            publication_href = _entry_source_href(entry)
            address_hint = _extract_address_hint(f"{title} {summary}")
            signal_kind = _detect_signal_kind(title, summary)
            address_required = signal_kind in {"vacancy", "opening", "new_construction"}
            actionable_property_signal = not (require_address_for_actionable_signals and address_required and not address_hint)

            event = MarketEvent(
                event_urn=make_urn("event"),
                event_type=event_type,
                title=title,
                observed_at=observed_at,
                property_address_hint=address_hint,
                owner_person_urn=owner_person_urn,
                company_name=query_term if event_type == MarketEventType.NEW_COMPANY else "",
                source_url=source_url,
                summary=summary[:4000],
                attributes={
                    "query_term": query_term,
                    "source_publication": publication_title,
                    "source_publication_url": publication_href,
                    "signal_kind": signal_kind,
                    "address_required": "true" if address_required else "false",
                    "address_extracted": "true" if address_hint else "false",
                    "actionable_property_signal": "true" if actionable_property_signal else "false",
                    "research_queue": "true" if (address_required and not address_hint) else "false",
                },
            )
            store.add_market_event(event)
            created_events.append(event)
            existing_urls.add(source_url)

    return created_events


def ingest_market_event(
    store: InMemoryMasterArena,
    *,
    event_type: str,
    title: str,
    observed_at: datetime | None = None,
    property_urn: str | None = None,
    property_address_hint: str = "",
    owner_person_urn: str | None = None,
    owner_name_hint: str = "",
    company_name: str = "",
    source_url: str = "",
    summary: str = "",
    attributes: dict[str, str] | None = None,
) -> MarketEvent:
    try:
        typed_event = MarketEventType(event_type)
    except ValueError as exc:
        raise ValueError(f"unsupported market event type: {event_type}") from exc

    if not owner_person_urn and owner_name_hint:
        person = _find_person_by_name(store, owner_name_hint)
        if person:
            owner_person_urn = person.person_urn

    event = MarketEvent(
        event_urn=make_urn("event"),
        event_type=typed_event,
        title=title,
        observed_at=observed_at or datetime.now(tz=UTC),
        property_urn=property_urn,
        property_address_hint=property_address_hint,
        owner_person_urn=owner_person_urn,
        company_name=company_name,
        source_url=source_url,
        summary=summary,
        attributes=attributes or {},
    )
    return store.add_market_event(event)


def client_intel_summary(
    store: InMemoryMasterArena,
    *,
    owner_person_urn: str | None = None,
    since_days: int = 90,
) -> dict[str, object]:
    if owner_person_urn:
        people = [store.get_person(owner_person_urn)]
        people = [person for person in people if person is not None]
    else:
        people = list(store.people.values())

    summaries: list[dict[str, object]] = []
    for person in people:
        events = store.list_market_events(owner_person_urn=person.person_urn, since_days=since_days)
        client_news = [event for event in events if event.event_type == MarketEventType.CLIENT_NEWS]
        listings = [event for event in events if event.event_type == MarketEventType.LISTED]
        sold = [event for event in events if event.event_type == MarketEventType.SOLD]
        companies = [event.company_name for event in events if event.company_name]

        summaries.append(
            {
                "person_urn": person.person_urn,
                "full_name": person.full_name,
                "event_count": len(events),
                "listed_count": len(listings),
                "sold_count": len(sold),
                "client_news_count": len(client_news),
                "relevant_companies": sorted(list({name for name in companies})),
                "recent_events": [
                    {
                        "event_urn": event.event_urn,
                        "event_type": event.event_type.value,
                        "title": event.title,
                        "observed_at": event.observed_at.isoformat(),
                        "property_urn": event.property_urn,
                        "source_url": event.source_url,
                    }
                    for event in events[:10]
                ],
            }
        )

    return {
        "status": "ok",
        "since_days": since_days,
        "client_summaries": summaries,
    }
