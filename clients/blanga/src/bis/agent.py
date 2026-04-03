from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from bis.models import NoteEntry, make_urn
from bis.store import InMemoryMasterArena, PropertyQuery


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


@dataclass
class ParsedQuery:
    raw: str
    filters: PropertyQuery


@dataclass
class ParsedCommand:
    raw: str
    intent: str
    address_hint: str
    note_text: str
    mark_redo: bool = False
    mark_potential_listing: bool = False
    mark_dnc: bool = False


def parse_property_query(text: str) -> ParsedQuery:
    query = PropertyQuery()
    lowered = _norm(text)

    city_match = re.search(r"\bin\s+([a-z ]+?)(?:\s+where|$)", lowered)
    if city_match:
        query.city = city_match.group(1).strip()

    tenant_match = re.search(r"\ball\s+([a-z0-9& .'-]+?)\s+in\b", lowered)
    if tenant_match:
        query.tenant_brand = tenant_match.group(1).strip()

    land_psf_match = re.search(r"land\s+(?:is\s+)?(?:less|below)\s+than\s+\$?([0-9]+(?:\.[0-9]+)?)", lowered)
    if land_psf_match:
        query.max_land_psf = float(land_psf_match.group(1))

    lease_match = re.search(r"lease\s+exp(?:ires|iration)?\s+(?:within|in)\s+([0-9]+)\s+years?", lowered)
    if lease_match:
        query.lease_expiring_within_years = int(lease_match.group(1))

    county_match = re.search(r"\b(travis|williamson|hays|bastrop|caldwell)\s+county\b", lowered)
    if county_match:
        query.county = county_match.group(1)

    corridor_match = re.search(r"\b(burnet road|south lamar|ben white|i-35|pflugerville|manor)\b", lowered)
    if corridor_match:
        query.corridor = corridor_match.group(1)

    if "active outreach" in lowered:
        query.only_active_outreach = True

    return ParsedQuery(raw=text, filters=query)


def parse_update_command(text: str) -> ParsedCommand | None:
    normalized = text.strip()
    match = re.search(r"update\s+note\s+for\s+([^:]+):\s*(.+)$", normalized, flags=re.IGNORECASE)
    if not match:
        return None

    address_hint = match.group(1).strip()
    note_text = match.group(2).strip()
    lowered_note = _norm(note_text)

    return ParsedCommand(
        raw=text,
        intent="update_note",
        address_hint=address_hint,
        note_text=note_text,
        mark_redo=("redo" in lowered_note),
        mark_potential_listing=("potential listing" in lowered_note or "move it to the potential listings" in lowered_note),
        mark_dnc=("dnc" in lowered_note or "do not call" in lowered_note),
    )


class BISAgent:
    def __init__(self, store: InMemoryMasterArena) -> None:
        self._store = store

    def query(self, text: str) -> dict[str, object]:
        parsed = parse_property_query(text)
        matches = self._store.query_properties(parsed.filters)

        payload_matches: list[dict[str, object]] = []
        for prop in matches:
            owners = self._store.owners_for_property(prop.property_urn)
            notes = self._store.notes_rollup_for_property(prop.property_urn)
            payload_matches.append(
                {
                    "property_urn": prop.property_urn,
                    "address": prop.address_line1,
                    "city": prop.city,
                    "tenant_brand": prop.tenant_brand,
                    "lease_expiration": prop.lease_expiration.isoformat() if prop.lease_expiration else None,
                    "land_psf": self._store.sale_price_per_land_sf(prop),
                    "outreach_state": prop.outreach_state.value,
                    "owner_names": [owner.full_name for owner in owners],
                    "latest_note": notes[0].note_text if notes else "",
                }
            )

        return {
            "query": parsed.raw,
            "filters": {
                "tenant_brand": parsed.filters.tenant_brand,
                "city": parsed.filters.city,
                "county": parsed.filters.county,
                "corridor": parsed.filters.corridor,
                "submarket": parsed.filters.submarket,
                "max_land_psf": parsed.filters.max_land_psf,
                "lease_expiring_within_years": parsed.filters.lease_expiring_within_years,
                "only_active_outreach": parsed.filters.only_active_outreach,
            },
            "matches": payload_matches,
            "count": len(payload_matches),
        }

    def apply_command(self, text: str, *, actor: str = "broker") -> dict[str, object]:
        parsed = parse_update_command(text)
        if not parsed:
            return {
                "status": "ignored",
                "reason": "unsupported_command",
            }

        property_asset = self._store.find_property_by_address(parsed.address_hint)
        if not property_asset:
            return {
                "status": "error",
                "reason": "property_not_found",
                "address_hint": parsed.address_hint,
            }

        owners = self._store.owners_for_property(property_asset.property_urn)
        primary_owner = owners[0] if owners else None

        note = NoteEntry(
            note_urn=make_urn("note"),
            note_text=parsed.note_text,
            owner_person_urn=primary_owner.person_urn if primary_owner else None,
            property_urn=property_asset.property_urn,
            tags=["nl-crud", "redo" if parsed.mark_redo else ""],
            created_by=actor,
            created_at=datetime.now(tz=UTC),
        )
        note.tags = [tag for tag in note.tags if tag]
        self._store.add_note(note)

        if parsed.mark_redo:
            self._store.apply_redo(property_asset.property_urn, redo=True)
        if parsed.mark_potential_listing:
            self._store.set_potential_listing(property_asset.property_urn, True)
        if parsed.mark_dnc and primary_owner:
            self._store.set_person_dnc(primary_owner.person_urn, True)

        property_after = self._store.get_property(property_asset.property_urn)

        return {
            "status": "ok",
            "intent": parsed.intent,
            "property_urn": property_asset.property_urn,
            "note_urn": note.note_urn,
            "redo": bool(property_after.redo) if property_after else False,
            "potential_listing": bool(property_after.potential_listing) if property_after else False,
            "outreach_state": property_after.outreach_state.value if property_after else "active",
        }
