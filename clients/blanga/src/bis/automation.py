from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List

from bis.models import GeneratedDocument, ListingStatus, NoteEntry, make_urn
from bis.scoring import compute_propensity_score
from bis.store import InMemoryMasterArena


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.0f}"


def _iso_day(value: date | None) -> str:
    return value.isoformat() if value else "n/a"


def generate_property_summary_doc(store: InMemoryMasterArena, property_urn: str) -> GeneratedDocument:
    prop = store.get_property(property_urn)
    if not prop:
        raise KeyError(f"property not found: {property_urn}")

    owners = store.owners_for_property(property_urn)
    owner_names = ", ".join(owner.full_name for owner in owners) or "Unknown owner"
    days_on_market = store.days_on_market(property_urn)
    score = compute_propensity_score(prop, store.list_signals(property_urn=property_urn, since_days=365))

    content = "\n".join(
        [
            f"Property: {prop.address_line1}, {prop.city}, {prop.county} County",
            f"Tenant: {prop.tenant_brand or 'n/a'}",
            f"Owner(s): {owner_names}",
            f"Listing Status: {prop.listing_status.value}",
            f"Listed At: {_iso_day(prop.listed_at)}",
            f"Sold At: {_iso_day(prop.sold_at)}",
            f"Days On Market: {days_on_market if days_on_market is not None else 'n/a'}",
            f"Asking Price: {_money(prop.asking_price)}",
            f"Close Price: {_money(prop.close_price)}",
            f"NOI: {_money(prop.noi)}",
            f"Cap Rate: {prop.cap_rate if prop.cap_rate is not None else 'n/a'}",
            f"Propensity Score: {score.score}",
        ]
    )

    return GeneratedDocument(
        document_urn=make_urn("doc"),
        doc_type="property_summary",
        title=f"Property Summary - {prop.address_line1}",
        content=content,
        property_urn=property_urn,
        owner_person_urn=owners[0].person_urn if owners else None,
    )


def generate_call_brief_doc(store: InMemoryMasterArena, property_urn: str) -> GeneratedDocument:
    prop = store.get_property(property_urn)
    if not prop:
        raise KeyError(f"property not found: {property_urn}")

    notes = store.notes_rollup_for_property(property_urn)[:5]
    signals = store.list_signals(property_urn=property_urn, since_days=120)[:5]
    market_events = store.list_market_events(property_urn=property_urn, since_days=180)[:5]

    notes_lines = [f"- {note.created_at.date().isoformat()}: {note.note_text}" for note in notes] or ["- No notes."]
    signal_lines = [
        f"- {signal.observed_at.date().isoformat()} {signal.signal_type.value}: {signal.attributes.get('description', '')}".strip()
        for signal in signals
    ] or ["- No recent signals."]
    event_lines = [
        f"- {event.observed_at.date().isoformat()} {event.event_type.value}: {event.title}"
        for event in market_events
    ] or ["- No market events."]

    content = "\n".join(
        [
            f"Pre-Call Brief: {prop.address_line1}, {prop.city}",
            "",
            "Recent Notes:",
            *notes_lines,
            "",
            "Progress Signals:",
            *signal_lines,
            "",
            "Market Events:",
            *event_lines,
        ]
    )

    owners = store.owners_for_property(property_urn)
    return GeneratedDocument(
        document_urn=make_urn("doc"),
        doc_type="call_brief",
        title=f"Call Brief - {prop.address_line1}",
        content=content,
        property_urn=property_urn,
        owner_person_urn=owners[0].person_urn if owners else None,
    )


def auto_generate_documents_for_property(
    store: InMemoryMasterArena,
    *,
    property_urn: str,
    force: bool = False,
) -> List[GeneratedDocument]:
    prop = store.get_property(property_urn)
    if not prop:
        return []

    generated: List[GeneratedDocument] = []
    for doc_type, builder in [
        ("property_summary", generate_property_summary_doc),
        ("call_brief", generate_call_brief_doc),
    ]:
        latest = store.latest_document_for_property(property_urn=property_urn, doc_type=doc_type)
        should_generate = force or (latest is None) or (latest.created_at < prop.updated_at)
        if should_generate:
            doc = builder(store, property_urn)
            store.add_document(doc)
            generated.append(doc)

    return generated


def run_automation_tick(
    store: InMemoryMasterArena,
    *,
    stale_listing_days: int = 45,
) -> Dict[str, int]:
    generated_docs = 0
    listing_age_alerts = 0

    for prop in store.list_properties():
        if prop.listing_status == ListingStatus.LISTED:
            dom = store.days_on_market(prop.property_urn)
            if dom is not None and dom >= stale_listing_days:
                marker = f"auto-dom-{dom}"
                existing = [note for note in store.notes_rollup_for_property(prop.property_urn) if marker in note.tags]
                if not existing:
                    store.add_note(
                        NoteEntry(
                            note_urn=make_urn("note"),
                            note_text=(
                                f"Auto alert: listing has been active for {dom} days. "
                                "Recommend pricing review and owner re-engagement."
                            ),
                            property_urn=prop.property_urn,
                            tags=["auto-aging", marker],
                            created_by="bis-automation",
                            created_at=datetime.now(tz=timezone.utc),
                        )
                    )
                    listing_age_alerts += 1

        docs = auto_generate_documents_for_property(store, property_urn=prop.property_urn)
        generated_docs += len(docs)

    return {
        "properties_scanned": len(store.properties),
        "generated_documents": generated_docs,
        "listing_age_alerts": listing_age_alerts,
    }
