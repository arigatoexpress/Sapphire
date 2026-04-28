from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from bis.agent import BISAgent
from bis.auth import require_bis_auth
from bis.automation import auto_generate_documents_for_property, run_automation_tick
from bis.compliance import policies_as_dicts
from bis.gcs_persistence import gcs_status, load_snapshot_from_gcs, save_snapshot_to_gcs
from bis.google_sheets_api import read_sheet_rows, sheets_client_status, write_sheet_rows
from bis.intel import (
    client_intel_summary,
    ingest_market_event,
    news_source_preferences_as_dicts,
    refresh_news_intelligence,
)
from bis.models import (
    FieldObservation,
    GeneratedDocument,
    ListingStatus,
    LlcEntity,
    MarketEvent,
    NoteEntry,
    Person,
    PropertyAsset,
    ReviewTask,
    make_urn,
)
from bis.note_extraction import extract_field_suggestions, extract_follow_up_suggestions
from bis.om import extract_om_fields
from bis.scoring import compute_propensity_score
from bis.settings import get_settings
from bis.sheets_sync import (
    normalize_notes_row,
    normalize_properties_row,
    normalize_property_update_row,
    sheet_contract,
    writeback_preview_rows,
)
from bis.signals import (
    attach_signals_to_properties,
    fetch_county_permit_signals,
    permit_source_registry,
)
from bis.store import InMemoryMasterArena, PropertyQuery

router = APIRouter(prefix="/api/bis", tags=["bis"], dependencies=[Depends(require_bis_auth)])
master_arena = InMemoryMasterArena()
agent = BISAgent(master_arena)
settings = get_settings()
audit_events: list[dict[str, Any]] = []
saved_comp_searches: dict[str, dict[str, Any]] = {}
broker_followup_tasks: dict[str, dict[str, Any]] = {}


def _new_ui_urn(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex[:12]}"


def _record_audit_event(
    *,
    action: str,
    actor: str,
    summary: str,
    entity_type: str = "",
    entity_urn: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "audit_urn": _new_ui_urn("audit"),
        "action": action,
        "actor": actor or "system",
        "summary": summary,
        "entity_type": entity_type,
        "entity_urn": entity_urn,
        "details": details or {},
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    audit_events.insert(0, event)
    del audit_events[500:]
    return event


def _serialize_followup_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_urn": task.get("task_urn"),
        "action_urn": task.get("action_urn"),
        "status": task.get("status", "open"),
        "due_date": task.get("due_date"),
        "intent": task.get("intent", "follow_up"),
        "title": task.get("title", "Follow-up"),
        "reason": task.get("reason", ""),
        "property_urn": task.get("property_urn"),
        "property_address": task.get("property_address", ""),
        "owner_person_urn": task.get("owner_person_urn"),
        "owner_name": task.get("owner_name", ""),
        "source_note_urn": task.get("source_note_urn"),
        "source_label": task.get("source_label", ""),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "metadata": task.get("metadata", {}),
    }


def _create_followup_tasks_from_note(
    *,
    note: NoteEntry,
    property_urn: str | None,
    owner_person_urn: str | None,
    source_label: str,
) -> list[dict[str, Any]]:
    suggestions = extract_follow_up_suggestions(note.note_text)
    if not suggestions:
        return []

    prop = master_arena.get_property(property_urn) if property_urn else None
    owner = master_arena.get_person(owner_person_urn) if owner_person_urn else None
    created: list[dict[str, Any]] = []
    for suggestion in suggestions:
        task_urn = _new_ui_urn("followup")
        now_iso = datetime.now(tz=UTC).isoformat()
        title = "Follow up with owner"
        if suggestion.intent == "seller_follow_up":
            title = "Follow up: potential seller"
        elif suggestion.intent == "vacancy_follow_up":
            title = "Follow up: vacancy opportunity"
        elif suggestion.intent == "lease_follow_up":
            title = "Follow up: lease timing"
        task = {
            "task_urn": task_urn,
            "action_urn": task_urn,
            "status": "open",
            "due_date": suggestion.due_date.isoformat(),
            "intent": suggestion.intent,
            "title": title,
            "reason": note.note_text[:280],
            "property_urn": prop.property_urn if prop else property_urn,
            "property_address": prop.address_line1 if prop else "",
            "owner_person_urn": owner.person_urn if owner else owner_person_urn,
            "owner_name": owner.full_name if owner else "",
            "source_note_urn": note.note_urn,
            "source_label": source_label,
            "created_at": now_iso,
            "updated_at": now_iso,
            "metadata": {
                "confidence": suggestion.confidence,
                "rationale": suggestion.rationale,
            },
        }
        broker_followup_tasks[task_urn] = task
        created.append(task)
    return created


def _update_followup_task_outcome(
    *, action_urn: str, outcome: str, note: str
) -> dict[str, Any] | None:
    task = broker_followup_tasks.get(action_urn)
    if not task:
        return None
    today = date.today()
    if outcome == "snoozed":
        due_raw = str(task.get("due_date") or "")
        try:
            due = date.fromisoformat(due_raw)
        except ValueError:
            due = today
        task["due_date"] = max(due, today) + timedelta(days=1)
        task["due_date"] = task["due_date"].isoformat()
        task["status"] = "open"
        task.setdefault("metadata", {})["last_snooze_note"] = note or ""
    elif outcome in {"done", "ignored"}:
        task["status"] = outcome
        task.setdefault("metadata", {})["resolution_note"] = note or ""
    task["updated_at"] = datetime.now(tz=UTC).isoformat()
    return task


def _next_best_actions(limit: int = 20) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    now = datetime.now(tz=UTC)
    today = now.date()

    # 0) Broker follow-up tasks parsed from notes (dated work should be obvious)
    for task in list(broker_followup_tasks.values())[:200]:
        if task.get("status") != "open":
            continue
        due_raw = str(task.get("due_date") or "")
        try:
            due_date = date.fromisoformat(due_raw)
        except ValueError:
            continue
        days_delta = (due_date - today).days
        priority = 78
        if days_delta < 0:
            priority = 99
        elif days_delta == 0:
            priority = 97
        elif days_delta <= 3:
            priority = 92
        elif days_delta <= 7:
            priority = 86
        actions.append(
            {
                "action_urn": task.get("action_urn"),
                "category": "broker_follow_up",
                "priority_score": priority,
                "title": task.get("title") or "Follow up with owner",
                "reason": f"Due {due_date.isoformat()} from note. {task.get('reason','')}".strip(),
                "recommended_action": "Call / text / email and update note outcome",
                "property_urn": task.get("property_urn"),
                "property_address": task.get("property_address", ""),
                "entity_urn": task.get("task_urn"),
                "review_urn": None,
                "metadata": {
                    "due_date": due_date.isoformat(),
                    "intent": task.get("intent"),
                    "owner_name": task.get("owner_name", ""),
                    "source_note_urn": task.get("source_note_urn"),
                },
                "created_at": task.get("created_at") or now.isoformat(),
            }
        )

    # 1) Pending review queue actions (highest leverage for data quality)
    for review in master_arena.list_review_tasks(status="pending")[:50]:
        obs = master_arena.get_field_observation(review.observation_urn)
        prop = (
            master_arena.get_property(review.entity_urn)
            if review.entity_type == "property"
            else None
        )
        confidence = obs.confidence if obs else 0.0
        urgency = 85 if review.field_name == "occupancy_status" else 75
        if confidence >= 0.9:
            urgency += 5
        actions.append(
            {
                "action_urn": _new_ui_urn("task"),
                "category": "review_queue",
                "priority_score": min(100, urgency),
                "title": f"Review suggested update: {review.field_name}",
                "reason": (
                    f"BIS extracted '{obs.proposed_value}' from a note"
                    if obs and obs.proposed_value
                    else "BIS created a suggested update that needs review"
                ),
                "recommended_action": "Approve or reject suggested field update",
                "property_urn": prop.property_urn if prop else None,
                "property_address": prop.address_line1 if prop else "",
                "entity_urn": review.entity_urn,
                "review_urn": review.review_urn,
                "metadata": {
                    "confidence": confidence,
                    "field_name": review.field_name,
                    "source_type": obs.source_type if obs else "",
                },
                "created_at": review.created_at.isoformat(),
            }
        )

    # 2) Stale listings / active listings
    for prop in master_arena.list_properties():
        dom = master_arena.days_on_market(prop.property_urn)
        if prop.listing_status == ListingStatus.LISTED and dom is not None:
            if dom >= 90:
                actions.append(
                    {
                        "action_urn": _new_ui_urn("task"),
                        "category": "listing_follow_up",
                        "priority_score": 92,
                        "title": f"Stale listing follow-up ({dom} DOM)",
                        "reason": "Longer days on market may indicate pricing or strategy reset conversation.",
                        "recommended_action": "Call owner and discuss pricing / marketing / repositioning",
                        "property_urn": prop.property_urn,
                        "property_address": prop.address_line1,
                        "entity_urn": prop.property_urn,
                        "review_urn": None,
                        "metadata": {
                            "days_on_market": dom,
                            "listing_status": prop.listing_status.value,
                        },
                        "created_at": prop.updated_at.isoformat(),
                    }
                )
            elif dom >= 45:
                actions.append(
                    {
                        "action_urn": _new_ui_urn("task"),
                        "category": "listing_check_in",
                        "priority_score": 72,
                        "title": f"Check in on active listing ({dom} DOM)",
                        "reason": "Mid-cycle listing check-in to stay ahead of owner concerns.",
                        "recommended_action": "Quick owner touchpoint with comps / recent market activity",
                        "property_urn": prop.property_urn,
                        "property_address": prop.address_line1,
                        "entity_urn": prop.property_urn,
                        "review_urn": None,
                        "metadata": {
                            "days_on_market": dom,
                            "listing_status": prop.listing_status.value,
                        },
                        "created_at": prop.updated_at.isoformat(),
                    }
                )

        # 3) Vacancy opportunities
        if (prop.occupancy_status or "").lower() == "vacant":
            actions.append(
                {
                    "action_urn": _new_ui_urn("task"),
                    "category": "vacancy_opportunity",
                    "priority_score": 95,
                    "title": "Vacant property opportunity",
                    "reason": "Vacancy often increases motivation to sell, lease, or reposition.",
                    "recommended_action": "Call owner and discuss disposition / lease-up / redevelopment options",
                    "property_urn": prop.property_urn,
                    "property_address": prop.address_line1,
                    "entity_urn": prop.property_urn,
                    "review_urn": None,
                    "metadata": {
                        "occupancy_status": prop.occupancy_status,
                        "listing_status": prop.listing_status.value,
                    },
                    "created_at": prop.updated_at.isoformat(),
                }
            )

    # 4) Recent market events (fresh intel follow-up)
    for event in master_arena.list_market_events(since_days=14)[:30]:
        if event.event_type.value in {
            "listed",
            "sold",
            "client_news",
            "industry_news",
            "new_company",
        }:
            priority = 70
            if "vacat" in (event.title + " " + event.summary).lower():
                priority = 90
            actions.append(
                {
                    "action_urn": _new_ui_urn("task"),
                    "category": "market_event_follow_up",
                    "priority_score": priority,
                    "title": f"Follow up on market event: {event.title}",
                    "reason": "Recent market intelligence can create a timely outreach angle.",
                    "recommended_action": "Review event and decide if owner/client outreach is warranted",
                    "property_urn": event.property_urn,
                    "property_address": event.property_address_hint or "",
                    "entity_urn": event.event_urn,
                    "review_urn": None,
                    "metadata": {
                        "event_type": event.event_type.value,
                        "source_url": event.source_url,
                    },
                    "created_at": event.observed_at.isoformat(),
                }
            )

    # Deduplicate by category+entity+review for readability
    seen = set()
    deduped: list[dict[str, Any]] = []
    for item in sorted(
        actions, key=lambda x: (-x["priority_score"], x.get("created_at", "")), reverse=False
    ):
        key = (item["category"], item.get("entity_urn"), item.get("review_urn"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(key=lambda x: (-x["priority_score"], x.get("created_at", "")), reverse=False)
    return deduped[: max(1, min(limit, 50))]


def _backup_dir() -> Path:
    path = Path(settings.backup_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _backup_file_path() -> Path:
    return _backup_dir() / "master_arena_snapshot.latest.json"


def _snapshot_status() -> dict[str, Any]:
    path = _backup_file_path()
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat() if exists else None
    local_status = {
        "storage_mode": "local_ephemeral_filesystem",
        "warning": "Cloud Run local filesystem is ephemeral; export/download snapshots for durable backup.",
        "backup_dir": str(_backup_dir()),
        "latest_snapshot_file": str(path),
        "snapshot_exists": exists,
        "snapshot_size_bytes": size,
        "snapshot_modified_at": modified,
        "autosave_enabled": settings.autosave_snapshots,
    }
    return {
        **local_status,
        "gcs": gcs_status(settings),
    }


def _application_snapshot_payload() -> dict[str, Any]:
    arena_snapshot = master_arena.snapshot()
    return {
        "snapshot_kind": "bis_application",
        "version": 2,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "master_arena": arena_snapshot,
        "ui_state": {
            "audit_events": audit_events,
            "saved_comp_searches": list(saved_comp_searches.values()),
            "broker_followup_tasks": list(broker_followup_tasks.values()),
        },
        "counts": {
            **arena_snapshot.get("counts", {}),
            "audit_events": len(audit_events),
            "saved_comp_searches": len(saved_comp_searches),
            "broker_followup_tasks": len(broker_followup_tasks),
        },
    }


def _restore_application_snapshot(payload: dict[str, Any]) -> dict[str, int]:
    # Backward compatibility: old snapshots were raw master_arena payloads
    arena_payload = (
        payload.get("master_arena") if isinstance(payload.get("master_arena"), dict) else payload
    )
    counts = master_arena.restore_snapshot(arena_payload)

    audit_events.clear()
    saved_comp_searches.clear()
    broker_followup_tasks.clear()
    ui_state = payload.get("ui_state", {}) if isinstance(payload, dict) else {}
    for event in ui_state.get("audit_events", []):
        if isinstance(event, dict):
            audit_events.append(event)
    for row in ui_state.get("saved_comp_searches", []):
        if isinstance(row, dict) and row.get("saved_search_urn"):
            saved_comp_searches[str(row["saved_search_urn"])] = row
    for row in ui_state.get("broker_followup_tasks", []):
        if isinstance(row, dict) and row.get("task_urn"):
            broker_followup_tasks[str(row["task_urn"])] = row

    counts["audit_events"] = len(audit_events)
    counts["saved_comp_searches"] = len(saved_comp_searches)
    counts["broker_followup_tasks"] = len(broker_followup_tasks)
    return counts


def _save_snapshot_to_disk() -> dict[str, Any]:
    snapshot = _application_snapshot_payload()
    path = _backup_file_path()
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    status = _snapshot_status()
    status["counts"] = snapshot.get("counts", {})
    return status


def _save_snapshot() -> dict[str, Any]:
    disk_status = _save_snapshot_to_disk()
    snapshot = _application_snapshot_payload()
    gcs_result: dict[str, Any]
    try:
        if settings.gcs_snapshot_bucket:
            gcs_result = save_snapshot_to_gcs(snapshot, settings)
        else:
            gcs_result = {"saved": False, "reason": "gcs_not_configured"}
    except Exception as exc:
        gcs_result = {"saved": False, "error": str(exc)}
    disk_status["gcs_save"] = gcs_result
    return disk_status


def _autosave_snapshot() -> None:
    if not settings.autosave_snapshots:
        return
    try:
        _save_snapshot()
    except Exception:
        return


def _load_latest_snapshot_if_present() -> None:
    try:
        payload = load_snapshot_from_gcs(settings)
        if payload:
            _restore_application_snapshot(payload)
            return
    except Exception:
        pass
    path = _backup_file_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        _restore_application_snapshot(payload)
    except Exception:
        return


_load_latest_snapshot_if_present()


def _add_years_safe(source: date, years: int) -> date:
    try:
        return source.replace(year=source.year + years)
    except ValueError:
        return source + timedelta(days=365 * years)


class PersonUpsertRequest(BaseModel):
    person_urn: str | None = None
    full_name: str
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    dnc: bool = False
    notes: str = ""


class LlcUpsertRequest(BaseModel):
    llc_urn: str | None = None
    legal_name: str
    state: str = "TX"
    sos_file_number: str = ""
    officer_person_urns: list[str] = Field(default_factory=list)


class PropertyUpsertRequest(BaseModel):
    property_urn: str | None = None
    address_line1: str
    city: str
    county: str
    state: str = "TX"
    postal_code: str = ""
    submarket: str = ""
    corridor: str = ""
    asset_type: str = "stnl_retail"
    tenant_brand: str = ""
    building_sqft: float | None = None
    land_acres: float | None = None
    year_built: int | None = None
    asking_price: float | None = None
    noi: float | None = None
    cap_rate: float | None = None
    current_rent_psf: float | None = None
    submarket_avg_rent_psf: float | None = None
    lease_expiration: date | None = None
    ownership_start: date | None = None
    owner_llc_urns: list[str] = Field(default_factory=list)
    listing_status: ListingStatus = ListingStatus.DRAFT
    listed_at: date | None = None
    sold_at: date | None = None
    close_price: float | None = None
    listing_broker: str = ""
    redo: bool = False
    potential_listing: bool = False


class NoteCreateRequest(BaseModel):
    note_text: str
    owner_person_urn: str | None = None
    property_urn: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_by: str = "broker"


class QueryRequest(BaseModel):
    query: str


class CommandRequest(BaseModel):
    command: str
    actor: str = "broker"


class OMExtractRequest(BaseModel):
    source_name: str = "om.pdf"
    property_urn: str | None = None
    document_text: str


class PermitPullRequest(BaseModel):
    limit: int = 50
    min_valuation: float = 50000.0
    counties: list[str] = Field(default_factory=lambda: ["Travis", "Williamson", "Hays"])


class IntakeDropRequest(BaseModel):
    address_line1: str
    city: str = "Austin"
    county: str = "Travis"
    owner_name: str
    llc_name: str = ""
    tenant_brand: str = ""
    occupancy_status: str = ""
    submarket: str = ""
    corridor: str = ""
    building_sqft: float | None = None
    land_acres: float | None = None
    asking_price: float | None = None
    close_price: float | None = None
    note_text: str = ""
    listing_status: ListingStatus | None = None
    listed_at: date | None = None
    sold_at: date | None = None
    source_label: str = "intake-drop"
    auto_generate_docs: bool = True


class AutomationRunRequest(BaseModel):
    stale_listing_days: int = 45
    pull_permit_signals: bool = False
    permit_limit: int = 50
    permit_min_valuation: float = 50000.0
    permit_counties: list[str] = Field(default_factory=lambda: ["Travis", "Williamson", "Hays"])
    refresh_news_intel: bool = False
    news_max_queries: int = 12
    news_per_query_limit: int = 5
    news_lookback_days: int = 21
    news_preferred_publications: list[str] = Field(default_factory=list)
    sync_google_sheets_pull: bool = False
    sync_google_sheets_push: bool = False
    google_sheets_push_targets: list[str] = Field(
        default_factory=lambda: ["properties_computed", "reviews_pending"]
    )
    auto_approve_reviews: bool = False
    review_auto_min_confidence: float = 0.90
    review_auto_only_fields: list[str] = Field(default_factory=list)


class MarketEventIngestRequest(BaseModel):
    event_type: str
    title: str
    observed_at: datetime | None = None
    property_urn: str | None = None
    property_address_hint: str = ""
    city: str = "Austin"
    county: str = "Travis"
    create_property_if_missing: bool = True
    owner_person_urn: str | None = None
    owner_name_hint: str = ""
    company_name: str = ""
    source_url: str = ""
    summary: str = ""
    list_price: float | None = None
    close_price: float | None = None


class NewsIntelRefreshRequest(BaseModel):
    queries: list[str] = Field(default_factory=list)
    preferred_publications: list[str] = Field(default_factory=list)
    max_queries: int = 12
    per_query_limit: int = 5
    lookback_days: int = 21


class ReviewDecisionRequest(BaseModel):
    reviewed_by: str = "broker"
    review_note: str = ""


class ReviewAutoApproveRequest(BaseModel):
    reviewed_by: str = "bis-auto-review"
    review_note: str = "Auto-approved by BIS threshold policy"
    min_confidence: float = 0.90
    field_thresholds: dict[str, float] = Field(default_factory=dict)
    only_fields: list[str] = Field(default_factory=list)
    max_items: int = 50
    dry_run: bool = False


class SnapshotImportRequest(BaseModel):
    snapshot: dict[str, Any]


class SheetImportRequest(BaseModel):
    tab: str = "properties_input"
    rows: list[dict[str, Any]] = Field(default_factory=list)
    dry_run: bool = False
    auto_generate_docs: bool = True


class GoogleSheetsPullRequest(BaseModel):
    spreadsheet_id: str = ""
    import_tab: str = "properties_input"
    source_tab: str = ""
    dry_run: bool = False
    auto_generate_docs: bool = True


class GoogleSheetsPushRequest(BaseModel):
    spreadsheet_id: str = ""
    target: str = "properties_computed"
    target_tab: str = ""


class UICompsSearchRequest(BaseModel):
    city: str = ""
    county: str = ""
    tenant_brand: str = ""
    corridor: str = ""
    submarket: str = ""
    max_land_psf: float | None = None
    max_building_psf: float | None = None
    max_building_sqft: float | None = None
    min_cap_rate: float | None = None
    max_cap_rate: float | None = None
    occupancy_status: str = ""
    lease_expiring_within_years: int | None = None
    only_active_outreach: bool = False
    limit: int = 15


class SavedCompSearchRequest(BaseModel):
    name: str
    notes: str = ""
    filters: UICompsSearchRequest
    created_by: str = "dashboard-user"


class NextActionLogRequest(BaseModel):
    action_urn: str
    outcome: str = "done"
    note: str = ""
    actor: str = "dashboard-user"


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _find_person_by_name(full_name: str) -> Person | None:
    target = _norm(full_name)
    if not target:
        return None
    for person in master_arena.people.values():
        current = _norm(person.full_name)
        if target == current or target in current or current in target:
            return person
    return None


def _find_llc_by_name(legal_name: str) -> LlcEntity | None:
    target = _norm(legal_name)
    if not target:
        return None
    for llc in master_arena.llcs.values():
        current = _norm(llc.legal_name)
        if target == current or target in current or current in target:
            return llc
    return None


def _resolve_spreadsheet_id(value: str = "") -> str:
    spreadsheet_id = (value or "").strip() or settings.default_spreadsheet_id
    if not spreadsheet_id:
        raise HTTPException(
            status_code=400,
            detail="spreadsheet_id is required (or configure BIS_GOOGLE_SHEETS_SPREADSHEET_ID)",
        )
    return spreadsheet_id


def _resolve_sheet_tab_from_target(target: str, explicit_tab: str = "") -> tuple[str, str]:
    if explicit_tab.strip():
        return target, explicit_tab.strip()
    normalized = _norm(target).replace("-", "_")
    mapping = {
        "properties_new_input": settings.sheets_new_properties_tab,
        "property_updates_input": settings.sheets_property_updates_tab,
        "notes_input": settings.sheets_notes_tab,
        "properties_input": settings.sheets_input_tab,
        "properties_computed": settings.sheets_computed_tab,
        "properties_master_view": settings.sheets_master_view_tab,
        "reviews_pending": settings.sheets_reviews_tab,
        "change_log_view": settings.sheets_change_log_tab,
        "today_tasks_view": settings.sheets_today_tasks_tab,
    }
    if normalized not in mapping:
        raise HTTPException(status_code=400, detail=f"unsupported sheets target: {target}")
    return normalized, mapping[normalized]


def _writeback_preview_for_tab(tab: str) -> list[dict[str, Any]]:
    normalized = _norm(tab).replace("-", "_")
    if normalized in {"change_log_view"}:
        rows: list[dict[str, Any]] = []
        for event in audit_events[:200]:
            rows.append(
                {
                    "created_at": event.get("created_at"),
                    "action": event.get("action"),
                    "actor": event.get("actor"),
                    "summary": event.get("summary"),
                    "entity_type": event.get("entity_type"),
                    "entity_urn": event.get("entity_urn"),
                    "details_json": json.dumps(event.get("details", {}), sort_keys=True),
                }
            )
        return rows
    if normalized in {"today_tasks_view"}:
        return [
            {
                "action_urn": row.get("action_urn"),
                "category": row.get("category"),
                "priority_score": row.get("priority_score"),
                "title": row.get("title"),
                "reason": row.get("reason"),
                "recommended_action": row.get("recommended_action"),
                "property_address": row.get("property_address"),
                "entity_urn": row.get("entity_urn"),
                "created_at": row.get("created_at"),
            }
            for row in _next_best_actions(limit=200)
        ]
    return writeback_preview_rows(master_arena, tab=normalized)


def _default_review_thresholds() -> dict[str, float]:
    return {
        "occupancy_status": 0.85,
        "lease_expiration": 0.93,
        "tenant_brand": 0.88,
    }


def _auto_approve_pending_reviews(
    *,
    reviewed_by: str,
    review_note: str,
    min_confidence: float,
    field_thresholds: dict[str, float],
    only_fields: list[str],
    max_items: int,
    dry_run: bool,
) -> dict[str, Any]:
    tasks = master_arena.list_review_tasks(status="pending")
    allowed_fields = {_norm(field) for field in only_fields if _norm(field)}
    thresholds = {
        **_default_review_thresholds(),
        **{_norm(k): float(v) for k, v in field_thresholds.items()},
    }

    candidates: list[ReviewTask] = []
    skipped: list[dict[str, Any]] = []
    for task in tasks:
        obs = master_arena.get_field_observation(task.observation_urn)
        if obs is None:
            skipped.append({"review_urn": task.review_urn, "reason": "missing_observation"})
            continue
        field_name = _norm(task.field_name)
        if allowed_fields and field_name not in allowed_fields:
            skipped.append(
                {
                    "review_urn": task.review_urn,
                    "field_name": task.field_name,
                    "reason": "field_not_selected",
                }
            )
            continue
        threshold = max(min_confidence, thresholds.get(field_name, min_confidence))
        if obs.confidence < threshold:
            skipped.append(
                {
                    "review_urn": task.review_urn,
                    "field_name": task.field_name,
                    "confidence": obs.confidence,
                    "threshold": threshold,
                    "reason": "below_threshold",
                }
            )
            continue
        candidates.append(task)
        if len(candidates) >= max(1, max_items):
            break

    approved: list[dict[str, Any]] = []
    if not dry_run:
        for task in candidates:
            try:
                saved = master_arena.approve_review_task(
                    review_urn=task.review_urn,
                    reviewed_by=reviewed_by,
                    review_note=review_note,
                )
                approved.append(_serialize_review_task(saved))
            except KeyError as exc:
                skipped.append({"review_urn": task.review_urn, "reason": str(exc)})

    return {
        "status": "ok",
        "dry_run": dry_run,
        "pending_reviews_considered": len(tasks),
        "candidates": len(candidates),
        "approved_count": 0 if dry_run else len(approved),
        "approved_reviews": [] if dry_run else approved,
        "candidate_reviews": [_serialize_review_task(task) for task in candidates]
        if dry_run
        else [],
        "skipped": skipped[:100],
        "applied_thresholds": thresholds,
        "min_confidence": min_confidence,
        "only_fields": sorted(list(allowed_fields)) if allowed_fields else [],
    }


def _readiness_summary() -> dict[str, Any]:
    sheets_status = sheets_client_status()
    snapshot = _snapshot_status()
    recommendations: list[str] = []
    checks: list[dict[str, Any]] = []

    auth_ok = settings.require_auth and bool(settings.app_password)
    checks.append(
        {
            "name": "auth_password",
            "ok": auth_ok,
            "detail": "BIS basic auth enabled" if auth_ok else "Auth/password not configured",
        }
    )
    if not auth_ok:
        recommendations.append("Enable `BIS_APP_PASSWORD` and keep `/api/bis/*` protected.")

    gcs_ok = bool(snapshot.get("gcs", {}).get("configured"))
    checks.append(
        {
            "name": "durable_snapshots_gcs",
            "ok": gcs_ok,
            "detail": "GCS snapshot bucket configured"
            if gcs_ok
            else "GCS snapshot bucket not configured",
        }
    )
    if not gcs_ok:
        recommendations.append(
            "Configure `BIS_GCS_SNAPSHOT_BUCKET` for durable backups beyond Cloud Run local disk."
        )
    elif not snapshot.get("gcs", {}).get("exists"):
        recommendations.append(
            "Run `POST /api/bis/system/backup/save` once to create the first durable snapshot."
        )

    sheets_client_ok = sheets_status.available and sheets_status.auth_ok
    checks.append(
        {
            "name": "google_sheets_api_auth",
            "ok": sheets_client_ok,
            "detail": "Google Sheets API client authenticated"
            if sheets_client_ok
            else (sheets_status.error or "Google Sheets API auth unavailable"),
        }
    )
    if not sheets_client_ok:
        recommendations.append("Fix ADC/service-account auth for Google Sheets API on Cloud Run.")

    spreadsheet_id_ok = bool(settings.default_spreadsheet_id)
    checks.append(
        {
            "name": "spreadsheet_id_configured",
            "ok": spreadsheet_id_ok,
            "detail": "Default spreadsheet ID configured"
            if spreadsheet_id_ok
            else "Missing `BIS_GOOGLE_SHEETS_SPREADSHEET_ID`",
        }
    )
    if not spreadsheet_id_ok:
        recommendations.append(
            "Set `BIS_GOOGLE_SHEETS_SPREADSHEET_ID` and share the sheet with the Cloud Run service account."
        )

    pending_reviews = len(master_arena.list_review_tasks(status="pending"))
    checks.append(
        {
            "name": "review_queue_backlog",
            "ok": pending_reviews < 25,
            "detail": f"{pending_reviews} pending review tasks",
        }
    )
    if pending_reviews >= 25:
        recommendations.append(
            "Use `POST /api/bis/reviews/auto-approve` for high-confidence fields to keep the review queue current."
        )

    ready_score = sum(1 for check in checks if check["ok"])
    return {
        "status": "ok",
        "ready_score": ready_score,
        "ready_total": len(checks),
        "checks": checks,
        "recommendations": recommendations,
        "snapshot_status": snapshot,
        "google_sheets_status": {
            "available": sheets_status.available,
            "auth_ok": sheets_status.auth_ok,
            "project_id": sheets_status.project_id,
            "error": sheets_status.error or None,
        },
        "counts": {
            "people": len(master_arena.people),
            "properties": len(master_arena.properties),
            "pending_reviews": pending_reviews,
            "documents": len(master_arena.documents),
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


def _serialize_person(person: Person) -> dict[str, Any]:
    return {
        "person_urn": person.person_urn,
        "full_name": person.full_name,
        "phones": person.phones,
        "emails": person.emails,
        "dnc": person.dnc,
        "notes": person.notes,
        "created_at": person.created_at.isoformat(),
        "updated_at": person.updated_at.isoformat(),
    }


def _serialize_llc(llc: LlcEntity) -> dict[str, Any]:
    return {
        "llc_urn": llc.llc_urn,
        "legal_name": llc.legal_name,
        "state": llc.state,
        "sos_file_number": llc.sos_file_number,
        "officer_person_urns": llc.officer_person_urns,
        "created_at": llc.created_at.isoformat(),
        "updated_at": llc.updated_at.isoformat(),
    }


def _serialize_property(item: PropertyAsset) -> dict[str, Any]:
    days_on_market = master_arena.days_on_market(item.property_urn)
    list_to_close_delta = master_arena.list_to_close_delta(
        list_price=item.asking_price,
        close_price=item.close_price,
    )
    return {
        "property_urn": item.property_urn,
        "address_line1": item.address_line1,
        "city": item.city,
        "county": item.county,
        "state": item.state,
        "postal_code": item.postal_code,
        "submarket": item.submarket,
        "corridor": item.corridor,
        "asset_type": item.asset_type,
        "tenant_brand": item.tenant_brand,
        "occupancy_status": item.occupancy_status,
        "building_sqft": item.building_sqft,
        "land_acres": item.land_acres,
        "year_built": item.year_built,
        "asking_price": item.asking_price,
        "noi": item.noi,
        "cap_rate": item.cap_rate,
        "current_rent_psf": item.current_rent_psf,
        "submarket_avg_rent_psf": item.submarket_avg_rent_psf,
        "lease_expiration": item.lease_expiration.isoformat() if item.lease_expiration else None,
        "ownership_start": item.ownership_start.isoformat() if item.ownership_start else None,
        "owner_llc_urns": item.owner_llc_urns,
        "listing_status": item.listing_status.value,
        "listed_at": item.listed_at.isoformat() if item.listed_at else None,
        "sold_at": item.sold_at.isoformat() if item.sold_at else None,
        "days_on_market": days_on_market,
        "close_price": item.close_price,
        "list_to_close_delta_pct": list_to_close_delta,
        "listing_broker": item.listing_broker,
        "redo": item.redo,
        "potential_listing": item.potential_listing,
        "outreach_state": item.outreach_state.value,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "rent_psf": master_arena.rent_psf(item),
        "sale_price_per_building_sf": master_arena.sale_price_per_building_sf(item),
        "sale_price_per_land_sf": master_arena.sale_price_per_land_sf(item),
    }


def _serialize_note(note: NoteEntry) -> dict[str, Any]:
    return {
        "note_urn": note.note_urn,
        "note_text": note.note_text,
        "owner_person_urn": note.owner_person_urn,
        "property_urn": note.property_urn,
        "tags": note.tags,
        "created_by": note.created_by,
        "created_at": note.created_at.isoformat(),
    }


def _serialize_document(document: GeneratedDocument) -> dict[str, Any]:
    return {
        "document_urn": document.document_urn,
        "doc_type": document.doc_type,
        "title": document.title,
        "content": document.content,
        "property_urn": document.property_urn,
        "owner_person_urn": document.owner_person_urn,
        "source_event_urn": document.source_event_urn,
        "created_at": document.created_at.isoformat(),
    }


def _serialize_market_event(event: MarketEvent) -> dict[str, Any]:
    return {
        "event_urn": event.event_urn,
        "event_type": event.event_type.value,
        "title": event.title,
        "observed_at": event.observed_at.isoformat(),
        "property_urn": event.property_urn,
        "property_address_hint": event.property_address_hint,
        "owner_person_urn": event.owner_person_urn,
        "company_name": event.company_name,
        "source_url": event.source_url,
        "summary": event.summary,
        "attributes": event.attributes,
    }


def _serialize_observation(observation: FieldObservation) -> dict[str, Any]:
    return {
        "observation_urn": observation.observation_urn,
        "entity_type": observation.entity_type,
        "entity_urn": observation.entity_urn,
        "field_name": observation.field_name,
        "proposed_value": observation.proposed_value,
        "confidence": observation.confidence,
        "source_type": observation.source_type,
        "source_ref": observation.source_ref,
        "rationale": observation.rationale,
        "extracted_by": observation.extracted_by,
        "observed_at": observation.observed_at.isoformat(),
    }


def _serialize_review_task(task: ReviewTask) -> dict[str, Any]:
    observation = master_arena.get_field_observation(task.observation_urn)
    return {
        "review_urn": task.review_urn,
        "observation_urn": task.observation_urn,
        "entity_type": task.entity_type,
        "entity_urn": task.entity_urn,
        "field_name": task.field_name,
        "status": task.status.value,
        "created_at": task.created_at.isoformat(),
        "reviewed_at": task.reviewed_at.isoformat() if task.reviewed_at else None,
        "reviewed_by": task.reviewed_by,
        "review_note": task.review_note,
        "observation": _serialize_observation(observation) if observation else None,
    }


def _extract_note_to_review_tasks(note: NoteEntry) -> list[ReviewTask]:
    created: list[ReviewTask] = []
    entity_urn = note.property_urn or ""
    if not entity_urn:
        return created

    suggestions = extract_field_suggestions(note.note_text)
    for suggestion in suggestions:
        observation = master_arena.add_field_observation(
            FieldObservation(
                observation_urn=make_urn("obs"),
                entity_type="property",
                entity_urn=entity_urn,
                field_name=suggestion.field_name,
                proposed_value=suggestion.proposed_value,
                confidence=suggestion.confidence,
                source_type="note",
                source_ref=note.note_urn,
                rationale=suggestion.rationale,
                extracted_by="note-parser",
            )
        )
        review = master_arena.create_review_task(
            ReviewTask(
                review_urn=make_urn("review"),
                observation_urn=observation.observation_urn,
                entity_type="property",
                entity_urn=entity_urn,
                field_name=suggestion.field_name,
            )
        )
        created.append(review)
    return created


def _coerce_date_value(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            if fmt == "%Y-%m-%d":
                return date.fromisoformat(text)
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date value: {raw}")


def _coerce_float_value(raw: str) -> float | None:
    text = (raw or "").strip().replace("$", "").replace(",", "")
    if not text:
        return None
    return float(text)


def _coerce_bool_value(raw: str) -> bool:
    text = (raw or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {raw}")


def _import_note_row_impl(row: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_notes_row(row)
    linked_property = None
    linked_owner = None
    link_status: list[str] = []

    if normalized.property_urn:
        linked_property = master_arena.get_property(normalized.property_urn)
        if linked_property is None:
            raise ValueError(f"property not found for property_urn={normalized.property_urn}")
        link_status.append("linked_by_property_urn")
    elif normalized.address_line1:
        linked_property = master_arena.find_property_by_address(normalized.address_line1)
        if linked_property:
            link_status.append("linked_by_address")
        else:
            link_status.append("address_not_found")

    if normalized.owner_name:
        linked_owner = _find_person_by_name(normalized.owner_name)
        if linked_owner:
            link_status.append("linked_owner_by_name")
        else:
            link_status.append("owner_not_found")

    if linked_property and linked_owner is None:
        owners = master_arena.owners_for_property(linked_property.property_urn)
        if len(owners) == 1:
            linked_owner = owners[0]
            link_status.append("inferred_owner_from_property")

    note = master_arena.add_note(
        NoteEntry(
            note_urn=make_urn("note"),
            note_text=normalized.note_text,
            owner_person_urn=linked_owner.person_urn if linked_owner else None,
            property_urn=linked_property.property_urn if linked_property else None,
            tags=list(
                dict.fromkeys(["notes-input", normalized.source_label] + (normalized.tags or []))
            ),
            created_by=normalized.entered_by or "broker",
        )
    )
    review_tasks = _extract_note_to_review_tasks(note)
    followup_tasks = _create_followup_tasks_from_note(
        note=note,
        property_urn=note.property_urn,
        owner_person_urn=note.owner_person_urn,
        source_label=normalized.source_label,
    )

    _record_audit_event(
        action="notes_tab_import",
        actor=normalized.entered_by or "broker",
        summary=f"Imported note ({len(review_tasks)} suggestions, {len(followup_tasks)} follow-ups)",
        entity_type="note",
        entity_urn=note.note_urn,
        details={
            "property_urn": note.property_urn,
            "owner_person_urn": note.owner_person_urn,
            "link_status": link_status,
        },
    )
    return {
        "note": _serialize_note(note),
        "review_tasks": [_serialize_review_task(task) for task in review_tasks],
        "followup_tasks": [_serialize_followup_task(task) for task in followup_tasks],
        "link_status": link_status,
    }


def _apply_property_update_row_impl(row: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_property_update_row(row)
    prop = master_arena.get_property(normalized.property_urn) if normalized.property_urn else None
    if prop is None and normalized.address_line1:
        prop = master_arena.find_property_by_address(normalized.address_line1)
    if prop is None:
        raise ValueError("property update could not be linked (property_urn/address not found)")

    field_name = _norm(normalized.field_name).replace(" ", "_")
    raw_value = normalized.new_value
    if raw_value == "" and not normalized.clear_field:
        return {
            "status": "skipped",
            "reason": "empty_new_value_no_clear_field",
            "property_urn": prop.property_urn,
            "field_name": field_name,
        }

    text_fields = {"tenant_brand", "submarket", "corridor", "listing_broker", "occupancy_status"}
    float_fields = {"asking_price", "close_price", "building_sqft", "land_acres", "cap_rate", "noi"}
    date_fields = {"lease_expiration", "listed_at", "sold_at", "ownership_start"}
    bool_fields = {"redo", "potential_listing"}

    if field_name not in text_fields | float_fields | date_fields | bool_fields | {
        "listing_status"
    }:
        raise ValueError(f"unsupported property update field: {field_name}")

    if field_name == "listing_status":
        if normalized.clear_field:
            raise ValueError("listing_status cannot be cleared")
        status = ListingStatus(_norm(raw_value).replace("-", "_"))
        if status == ListingStatus.LISTED:
            master_arena.mark_listed(
                property_urn=prop.property_urn,
                listed_at=prop.listed_at,
                list_price=prop.asking_price,
            )
        elif status == ListingStatus.UNDER_CONTRACT:
            master_arena.mark_under_contract(property_urn=prop.property_urn)
        elif status == ListingStatus.SOLD:
            master_arena.mark_sold(
                property_urn=prop.property_urn, sold_at=prop.sold_at, close_price=prop.close_price
            )
        else:
            prop.listing_status = status
            master_arena.upsert_property(prop)
    elif field_name in text_fields:
        setattr(
            prop,
            field_name,
            ""
            if normalized.clear_field
            else raw_value.strip().lower()
            if field_name == "occupancy_status"
            else raw_value.strip(),
        )
        master_arena.upsert_property(prop)
    elif field_name in float_fields:
        setattr(
            prop, field_name, None if normalized.clear_field else _coerce_float_value(raw_value)
        )
        master_arena.upsert_property(prop)
    elif field_name in date_fields:
        setattr(prop, field_name, None if normalized.clear_field else _coerce_date_value(raw_value))
        master_arena.upsert_property(prop)
    elif field_name in bool_fields:
        setattr(
            prop, field_name, False if normalized.clear_field else _coerce_bool_value(raw_value)
        )
        master_arena.upsert_property(prop)

    if field_name == "redo":
        master_arena.apply_redo(prop.property_urn, redo=bool(prop.redo))

    refreshed = master_arena.get_property(prop.property_urn) or prop
    _record_audit_event(
        action="property_update_import",
        actor=normalized.requested_by,
        summary=f"Updated {field_name} for {refreshed.address_line1}",
        entity_type="property",
        entity_urn=refreshed.property_urn,
        details={
            "field_name": field_name,
            "new_value": None if normalized.clear_field else raw_value,
            "clear_field": normalized.clear_field,
            "reason": normalized.reason,
            "source_label": normalized.source_label,
        },
    )
    return {
        "status": "updated",
        "property_urn": refreshed.property_urn,
        "address_line1": refreshed.address_line1,
        "field_name": field_name,
        "value_applied": None if normalized.clear_field else raw_value,
        "clear_field": normalized.clear_field,
    }


def _intake_drop_impl(payload: IntakeDropRequest) -> dict[str, Any]:
    owner = _find_person_by_name(payload.owner_name)
    if owner is None:
        owner = master_arena.upsert_person(
            Person(
                person_urn=make_urn("person"),
                full_name=payload.owner_name.strip(),
            )
        )

    llc_name = payload.llc_name.strip() or f"{payload.owner_name.strip()} Holdings LLC"
    llc = _find_llc_by_name(llc_name)
    if llc is None:
        llc = master_arena.upsert_llc(
            LlcEntity(
                llc_urn=make_urn("llc"),
                legal_name=llc_name,
                officer_person_urns=[owner.person_urn],
            )
        )
    elif owner.person_urn not in llc.officer_person_urns:
        master_arena.attach_officer_to_llc(person_urn=owner.person_urn, llc_urn=llc.llc_urn)
        llc = master_arena.get_llc(llc.llc_urn)

    property_asset = master_arena.find_property_by_address(payload.address_line1)
    if property_asset is None:
        property_asset = master_arena.upsert_property(
            PropertyAsset(
                property_urn=make_urn("property"),
                address_line1=payload.address_line1,
                city=payload.city,
                county=payload.county,
                submarket=payload.submarket,
                corridor=payload.corridor,
                tenant_brand=payload.tenant_brand,
                occupancy_status=payload.occupancy_status.strip().lower(),
                building_sqft=payload.building_sqft,
                land_acres=payload.land_acres,
                asking_price=payload.asking_price,
                owner_llc_urns=[llc.llc_urn],
                listing_status=ListingStatus.DRAFT,
            )
        )
    else:
        if llc.llc_urn not in property_asset.owner_llc_urns:
            property_asset.owner_llc_urns.append(llc.llc_urn)
        if payload.city:
            property_asset.city = payload.city
        if payload.county:
            property_asset.county = payload.county
        if payload.submarket:
            property_asset.submarket = payload.submarket
        if payload.corridor:
            property_asset.corridor = payload.corridor
        if payload.tenant_brand:
            property_asset.tenant_brand = payload.tenant_brand
        if payload.occupancy_status.strip():
            property_asset.occupancy_status = payload.occupancy_status.strip().lower()
        if payload.building_sqft is not None:
            property_asset.building_sqft = payload.building_sqft
        if payload.land_acres is not None:
            property_asset.land_acres = payload.land_acres
        if payload.asking_price is not None:
            property_asset.asking_price = payload.asking_price
        if payload.close_price is not None:
            property_asset.close_price = payload.close_price
        property_asset = master_arena.upsert_property(property_asset)

    if payload.listing_status == ListingStatus.LISTED:
        master_arena.mark_listed(
            property_urn=property_asset.property_urn,
            listed_at=payload.listed_at,
            list_price=payload.asking_price,
        )
    elif payload.listing_status == ListingStatus.UNDER_CONTRACT:
        master_arena.mark_under_contract(property_urn=property_asset.property_urn)
    elif payload.listing_status == ListingStatus.SOLD:
        master_arena.mark_sold(
            property_urn=property_asset.property_urn,
            sold_at=payload.sold_at,
            close_price=payload.close_price,
        )
    elif payload.listing_status == ListingStatus.OFF_MARKET:
        property_asset = master_arena.get_property(property_asset.property_urn)
        property_asset.listing_status = ListingStatus.OFF_MARKET
        master_arena.upsert_property(property_asset)

    created_note = None
    review_tasks: list[ReviewTask] = []
    followup_tasks: list[dict[str, Any]] = []
    if payload.note_text.strip():
        created_note = master_arena.add_note(
            NoteEntry(
                note_urn=make_urn("note"),
                note_text=payload.note_text.strip(),
                owner_person_urn=owner.person_urn,
                property_urn=property_asset.property_urn,
                tags=["auto-intake", payload.source_label.strip().lower()],
                created_by="bis-intake",
            )
        )
        review_tasks = _extract_note_to_review_tasks(created_note)
        followup_tasks = _create_followup_tasks_from_note(
            note=created_note,
            property_urn=property_asset.property_urn,
            owner_person_urn=owner.person_urn,
            source_label=payload.source_label,
        )

    generated_docs: list[GeneratedDocument] = []
    if payload.auto_generate_docs:
        generated_docs = auto_generate_documents_for_property(
            master_arena,
            property_urn=property_asset.property_urn,
            force=True,
        )

    refreshed_property = master_arena.get_property(property_asset.property_urn)
    result = {
        "status": "ok",
        "owner": _serialize_person(owner),
        "llc": _serialize_llc(llc),
        "property": _serialize_property(refreshed_property),
        "note": _serialize_note(created_note) if created_note else None,
        "review_tasks": [_serialize_review_task(task) for task in review_tasks],
        "followup_tasks": [_serialize_followup_task(task) for task in followup_tasks],
        "generated_documents": [_serialize_document(doc) for doc in generated_docs],
    }
    _record_audit_event(
        action="intake_drop",
        actor="dashboard-user"
        if payload.source_label in {"intake-drop", "google-sheets"}
        else "broker",
        summary=f"Saved intake for {refreshed_property.address_line1} ({len(review_tasks)} suggested updates, {len(followup_tasks)} follow-ups)",
        entity_type="property",
        entity_urn=refreshed_property.property_urn,
        details={
            "review_tasks": len(review_tasks),
            "followup_tasks": len(followup_tasks),
            "source_label": payload.source_label,
        },
    )
    return result


@router.get("/health")
async def bis_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "bis",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "people": len(master_arena.people),
        "llcs": len(master_arena.llcs),
        "properties": len(master_arena.properties),
        "notes": len(master_arena.notes),
        "signals": len(master_arena.signals),
        "documents": len(master_arena.documents),
        "market_events": len(master_arena.market_events),
        "field_observations": len(master_arena.field_observations),
        "review_tasks": len(master_arena.review_tasks),
    }


@router.get("/compliance/sources")
async def list_source_policies() -> dict[str, Any]:
    return {
        "status": "ok",
        "policies": policies_as_dicts(),
    }


@router.get("/system/backup/status")
async def backup_status() -> dict[str, Any]:
    snapshot = _application_snapshot_payload()
    return {
        "status": "ok",
        **_snapshot_status(),
        "memory_counts": snapshot.get("counts", {}),
    }


@router.get("/system/readiness")
async def system_readiness() -> dict[str, Any]:
    return _readiness_summary()


@router.get("/ui/overview")
async def ui_overview() -> dict[str, Any]:
    readiness = _readiness_summary()
    pending_reviews = master_arena.list_review_tasks(status="pending")
    recent_properties = sorted(
        master_arena.list_properties(), key=lambda p: p.updated_at, reverse=True
    )[:20]
    recent_events = master_arena.list_market_events(since_days=30)[:10]
    recent_docs = master_arena.list_documents()[:10]

    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "counts": {
            "people": len(master_arena.people),
            "llcs": len(master_arena.llcs),
            "properties": len(master_arena.properties),
            "notes": len(master_arena.notes),
            "documents": len(master_arena.documents),
            "pending_reviews": len(pending_reviews),
            "open_followup_tasks": len(
                [t for t in broker_followup_tasks.values() if t.get("status") == "open"]
            ),
            "market_events_30d": len(master_arena.list_market_events(since_days=30)),
        },
        "readiness": readiness,
        "recent_properties": [_serialize_property(item) for item in recent_properties],
        "pending_reviews": [_serialize_review_task(task) for task in pending_reviews[:20]],
        "recent_events": [_serialize_market_event(event) for event in recent_events],
        "recent_documents": [_serialize_document(doc) for doc in recent_docs],
        "recent_audit_events": audit_events[:20],
        "saved_comp_searches": sorted(
            saved_comp_searches.values(), key=lambda x: x["updated_at"], reverse=True
        )[:20],
        "open_followup_tasks": [
            _serialize_followup_task(t)
            for t in sorted(
                [row for row in broker_followup_tasks.values() if row.get("status") == "open"],
                key=lambda row: (str(row.get("due_date") or ""), str(row.get("updated_at") or "")),
            )[:20]
        ],
        "next_actions": _next_best_actions(limit=15),
        "client_source_focus": {
            "news_sources": news_source_preferences_as_dicts(),
            "permit_sources": permit_source_registry(),
            "counties": ["Travis", "Williamson", "Hays", "Caldwell", "Bastrop"],
        },
        "beginner_workflow": [
            "1) Add a property/owner note in the Intake form.",
            "2) Check Suggested Updates and approve only what looks right.",
            "3) Run Daily Refresh to create docs and alerts.",
            "4) Save Backup after a working session.",
        ],
    }


@router.post("/ui/comps/search")
async def ui_comps_search(payload: UICompsSearchRequest) -> dict[str, Any]:
    query = PropertyQuery(
        tenant_brand=payload.tenant_brand,
        city=payload.city,
        county=payload.county,
        corridor=payload.corridor,
        submarket=payload.submarket,
        max_land_psf=payload.max_land_psf,
        max_building_psf=payload.max_building_psf,
        max_building_sqft=payload.max_building_sqft,
        min_cap_rate=payload.min_cap_rate,
        max_cap_rate=payload.max_cap_rate,
        occupancy_status=payload.occupancy_status,
        lease_expiring_within_years=payload.lease_expiring_within_years,
        only_active_outreach=payload.only_active_outreach,
    )
    matches = master_arena.query_properties(query)
    limit = max(1, min(payload.limit, 50))
    rows = [_serialize_property(item) for item in matches[:limit]]

    land_psf_values = [
        row["sale_price_per_land_sf"]
        for row in rows
        if row.get("sale_price_per_land_sf") is not None
    ]
    bldg_psf_values = [
        row["sale_price_per_building_sf"]
        for row in rows
        if row.get("sale_price_per_building_sf") is not None
    ]
    cap_rates = [row["cap_rate"] for row in rows if row.get("cap_rate") is not None]
    dom_values = [row["days_on_market"] for row in rows if row.get("days_on_market") is not None]

    def _avg(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    summary = {
        "match_count": len(matches),
        "returned_count": len(rows),
        "avg_land_price_per_sf": _avg([float(v) for v in land_psf_values]),
        "avg_building_price_per_sf": _avg([float(v) for v in bldg_psf_values]),
        "avg_cap_rate": _avg([float(v) for v in cap_rates]),
        "avg_days_on_market": _avg([float(v) for v in dom_values]),
    }

    filters_used = {
        "city": payload.city or None,
        "county": payload.county or None,
        "tenant_brand": payload.tenant_brand or None,
        "corridor": payload.corridor or None,
        "submarket": payload.submarket or None,
        "max_land_psf": payload.max_land_psf,
        "max_building_psf": payload.max_building_psf,
        "max_building_sqft": payload.max_building_sqft,
        "min_cap_rate": payload.min_cap_rate,
        "max_cap_rate": payload.max_cap_rate,
        "occupancy_status": payload.occupancy_status or None,
        "lease_expiring_within_years": payload.lease_expiring_within_years,
        "only_active_outreach": payload.only_active_outreach,
    }
    filter_bits = [f"{k}={v}" for k, v in filters_used.items() if v not in (None, "", False)]
    summary_text = (
        f"Found {len(matches)} matching properties"
        + (f" ({', '.join(filter_bits)})" if filter_bits else "")
        + ". "
        + (
            "Use the returned rows as a working comp list and refine filters."
            if not rows
            else "Returned the top results with pricing, DOM, and occupancy context."
        )
    )

    return {
        "status": "ok",
        "summary": summary,
        "summary_text": summary_text,
        "filters": filters_used,
        "properties": rows,
    }


@router.get("/ui/audit")
async def ui_audit(limit: int = 50) -> dict[str, Any]:
    n = max(1, min(limit, 200))
    return {
        "status": "ok",
        "count": min(len(audit_events), n),
        "events": audit_events[:n],
    }


@router.get("/ui/next-actions")
async def ui_next_actions(limit: int = 20) -> dict[str, Any]:
    rows = _next_best_actions(limit=limit)
    return {
        "status": "ok",
        "count": len(rows),
        "actions": rows,
        "summary_text": (
            "These are the highest-value actions for today based on pending reviews, vacancy signals, listing age, and recent market events."
        ),
    }


@router.post("/ui/next-actions/log")
async def ui_next_actions_log(payload: NextActionLogRequest) -> dict[str, Any]:
    outcome = (payload.outcome or "done").strip().lower()
    if outcome not in {"done", "snoozed", "ignored"}:
        raise HTTPException(
            status_code=400, detail="outcome must be one of: done, snoozed, ignored"
        )
    followup_task = _update_followup_task_outcome(
        action_urn=payload.action_urn, outcome=outcome, note=payload.note
    )
    if followup_task is not None:
        _autosave_snapshot()
    event = _record_audit_event(
        action="next_action_" + outcome,
        actor=payload.actor,
        summary=f"Marked next action {outcome}: {payload.action_urn}",
        entity_type="broker_followup_task" if followup_task else "next_action",
        entity_urn=payload.action_urn,
        details={"note": payload.note, "task_updated": bool(followup_task)},
    )
    return {
        "status": "ok",
        "audit_event": event,
        "updated_followup_task": _serialize_followup_task(followup_task) if followup_task else None,
    }


@router.post("/ui/comps/saved")
async def save_comp_search(payload: SavedCompSearchRequest) -> dict[str, Any]:
    saved_urn = _new_ui_urn("compsearch")
    record = {
        "saved_search_urn": saved_urn,
        "name": payload.name.strip(),
        "notes": payload.notes.strip(),
        "created_by": payload.created_by,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "updated_at": datetime.now(tz=UTC).isoformat(),
        "filters": payload.filters.model_dump(),
    }
    if not record["name"]:
        raise HTTPException(status_code=400, detail="name is required")
    saved_comp_searches[saved_urn] = record
    _record_audit_event(
        action="save_comp_search",
        actor=payload.created_by,
        summary=f"Saved comp search '{record['name']}'",
        entity_type="comp_search",
        entity_urn=saved_urn,
    )
    return {"status": "ok", "saved_search": record}


@router.get("/ui/comps/saved")
async def list_saved_comp_searches() -> dict[str, Any]:
    rows = sorted(saved_comp_searches.values(), key=lambda x: x["updated_at"], reverse=True)
    return {"status": "ok", "count": len(rows), "saved_searches": rows}


@router.delete("/ui/comps/saved/{saved_search_urn}")
async def delete_saved_comp_search(saved_search_urn: str) -> dict[str, Any]:
    record = saved_comp_searches.pop(saved_search_urn, None)
    if not record:
        raise HTTPException(status_code=404, detail="saved comp search not found")
    _record_audit_event(
        action="delete_comp_search",
        actor="dashboard-user",
        summary=f"Deleted comp search '{record['name']}'",
        entity_type="comp_search",
        entity_urn=saved_search_urn,
    )
    return {"status": "ok", "deleted": True, "saved_search_urn": saved_search_urn}


@router.post("/ui/comps/saved/{saved_search_urn}/run")
async def run_saved_comp_search(saved_search_urn: str) -> dict[str, Any]:
    record = saved_comp_searches.get(saved_search_urn)
    if not record:
        raise HTTPException(status_code=404, detail="saved comp search not found")
    record["updated_at"] = datetime.now(tz=UTC).isoformat()
    payload = UICompsSearchRequest(**record["filters"])
    result = await ui_comps_search(payload)
    _record_audit_event(
        action="run_comp_search",
        actor="dashboard-user",
        summary=f"Ran saved comp search '{record['name']}' ({result['summary']['returned_count']} results)",
        entity_type="comp_search",
        entity_urn=saved_search_urn,
    )
    return {
        **result,
        "saved_search": record,
    }


@router.get("/system/backup/export")
async def export_backup_snapshot() -> dict[str, Any]:
    return {
        "status": "ok",
        "snapshot": _application_snapshot_payload(),
        **_snapshot_status(),
    }


@router.post("/system/backup/save")
async def save_backup_snapshot() -> dict[str, Any]:
    result = {
        "status": "ok",
        **_save_snapshot(),
    }
    _record_audit_event(
        action="backup_save",
        actor="dashboard-user",
        summary="Saved BIS backup snapshot",
        details={"gcs": result.get("gcs_save", {})},
    )
    return result


@router.post("/system/backup/load")
async def load_backup_snapshot() -> dict[str, Any]:
    try:
        payload = load_snapshot_from_gcs(settings)
        source = "gcs"
        if payload is None:
            path = _backup_file_path()
            if not path.exists():
                raise HTTPException(
                    status_code=404, detail="no backup snapshot found in gcs or local file"
                )
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = "local_file"
        counts = _restore_application_snapshot(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"failed to load snapshot: {exc}") from exc
    result = {
        "status": "ok",
        "loaded_from": source,
        "restored_counts": counts,
        **_snapshot_status(),
    }
    _record_audit_event(
        action="backup_load",
        actor="dashboard-user",
        summary=f"Loaded backup snapshot from {source}",
        details={"restored_counts": counts},
    )
    return result


@router.post("/system/backup/import")
async def import_backup_snapshot(payload: SnapshotImportRequest) -> dict[str, Any]:
    try:
        counts = _restore_application_snapshot(payload.snapshot)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid snapshot payload: {exc}") from exc
    _autosave_snapshot()
    result = {
        "status": "ok",
        "restored_counts": counts,
    }
    _record_audit_event(
        action="backup_import",
        actor="dashboard-user",
        summary="Imported backup snapshot payload",
        details={"restored_counts": counts},
    )
    return result


@router.get("/sheets/contract")
async def get_sheets_contract() -> dict[str, Any]:
    return {
        "status": "ok",
        "contract": sheet_contract(),
        "notes": [
            "Preferred workflow: use append-only tabs `properties_new_input`, `property_updates_input`, and `notes_input`.",
            "Legacy `properties_input` import remains available for fast beta intake.",
            "Use `properties_master_view`, `reviews_pending`, `change_log_view`, and `today_tasks_view` as BIS writeback targets.",
            "JSON row import is available now and Google Sheets API sync endpoints are available when ADC/service-account auth is configured.",
        ],
        "default_spreadsheet_id_configured": bool(settings.default_spreadsheet_id),
        "tabs_config": {
            "properties_new_input": settings.sheets_new_properties_tab,
            "property_updates_input": settings.sheets_property_updates_tab,
            "notes_input": settings.sheets_notes_tab,
            "properties_input": settings.sheets_input_tab,
            "properties_computed": settings.sheets_computed_tab,
            "properties_master_view": settings.sheets_master_view_tab,
            "reviews_pending": settings.sheets_reviews_tab,
            "change_log_view": settings.sheets_change_log_tab,
            "today_tasks_view": settings.sheets_today_tasks_tab,
        },
    }


@router.get("/sheets/writeback/preview")
async def sheets_writeback_preview(tab: str = "properties_computed") -> dict[str, Any]:
    try:
        rows = _writeback_preview_for_tab(tab)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "tab": tab,
        "count": len(rows),
        "rows": rows,
    }


@router.post("/sheets/import")
async def sheets_import(payload: SheetImportRequest) -> dict[str, Any]:
    tab = _norm(payload.tab).replace("-", "_")
    supported_import_tabs = {
        "properties_input",
        "properties_new_input",
        "property_updates_input",
        "notes_input",
    }
    if tab not in supported_import_tabs:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported import tab '{payload.tab}'. Supported: {sorted(supported_import_tabs)}",
        )

    imported = 0
    errors: list[dict[str, Any]] = []
    previews: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for idx, row in enumerate(payload.rows, start=1):
        try:
            if tab in {"properties_input", "properties_new_input"}:
                normalized = normalize_properties_row(row)
                existing_prop = master_arena.find_property_by_address(normalized.address_line1)
                if payload.dry_run:
                    previews.append(
                        {
                            "row_number": idx,
                            "address_line1": normalized.address_line1,
                            "owner_name": normalized.owner_name,
                            "listing_status": normalized.listing_status.value
                            if normalized.listing_status
                            else None,
                            "occupancy_status": normalized.occupancy_status or "",
                            "existing_property_urn": existing_prop.property_urn
                            if existing_prop
                            else None,
                            "duplicate_blocked": bool(
                                existing_prop and tab == "properties_new_input"
                            ),
                        }
                    )
                    continue
                if existing_prop and tab == "properties_new_input":
                    raise ValueError(
                        f"duplicate address for properties_new_input: {normalized.address_line1} (use property_updates_input instead)"
                    )

                intake_payload = IntakeDropRequest(
                    address_line1=normalized.address_line1,
                    city=normalized.city,
                    county=normalized.county,
                    owner_name=normalized.owner_name,
                    llc_name=normalized.llc_name,
                    tenant_brand=normalized.tenant_brand,
                    occupancy_status=normalized.occupancy_status,
                    submarket=normalized.submarket,
                    corridor=normalized.corridor,
                    building_sqft=normalized.building_sqft,
                    land_acres=normalized.land_acres,
                    asking_price=normalized.asking_price,
                    close_price=normalized.close_price,
                    note_text=normalized.note_text,
                    listing_status=normalized.listing_status,
                    listed_at=normalized.listed_at,
                    sold_at=normalized.sold_at,
                    source_label=normalized.source_label,
                    auto_generate_docs=payload.auto_generate_docs,
                )
                result = _intake_drop_impl(intake_payload)
                if normalized.dnc is True:
                    master_arena.set_person_dnc(result["owner"]["person_urn"], value=True)
                if normalized.redo is True:
                    master_arena.apply_redo(result["property"]["property_urn"], redo=True)
                if normalized.occupancy_status == "vacant":
                    prop = master_arena.get_property(result["property"]["property_urn"])
                    if prop:
                        prop.occupancy_status = "vacant"
                        master_arena.upsert_property(prop)
                results.append(
                    {
                        "row_number": idx,
                        "status": "imported",
                        "mode": "new_property"
                        if tab == "properties_new_input"
                        else "property_intake",
                        "property_urn": result["property"]["property_urn"],
                        "owner_person_urn": result["owner"]["person_urn"],
                        "address_line1": result["property"]["address_line1"],
                        "review_tasks_created": len(result.get("review_tasks", [])),
                        "followup_tasks_created": len(result.get("followup_tasks", [])),
                    }
                )
                imported += 1
                continue

            if tab == "notes_input":
                normalized_note = normalize_notes_row(row)
                if payload.dry_run:
                    previews.append(
                        {
                            "row_number": idx,
                            "property_urn": normalized_note.property_urn or None,
                            "address_line1": normalized_note.address_line1 or None,
                            "owner_name": normalized_note.owner_name or None,
                            "entered_by": normalized_note.entered_by,
                            "note_preview": normalized_note.note_text[:120],
                        }
                    )
                    continue
                result = _import_note_row_impl(row)
                results.append(
                    {
                        "row_number": idx,
                        "status": "imported",
                        "note_urn": result["note"]["note_urn"],
                        "property_urn": result["note"]["property_urn"],
                        "owner_person_urn": result["note"]["owner_person_urn"],
                        "review_tasks_created": len(result["review_tasks"]),
                        "followup_tasks_created": len(result["followup_tasks"]),
                        "link_status": result["link_status"],
                    }
                )
                imported += 1
                continue

            if tab == "property_updates_input":
                normalized_update = normalize_property_update_row(row)
                if payload.dry_run:
                    previews.append(
                        {
                            "row_number": idx,
                            "property_urn": normalized_update.property_urn or None,
                            "address_line1": normalized_update.address_line1 or None,
                            "field_name": normalized_update.field_name,
                            "new_value": normalized_update.new_value,
                            "clear_field": normalized_update.clear_field,
                        }
                    )
                    continue
                result = _apply_property_update_row_impl(row)
                results.append({"row_number": idx, **result})
                if result.get("status") == "updated":
                    imported += 1
                continue
        except Exception as exc:
            errors.append({"row_number": idx, "error": str(exc), "row": row})

    if not payload.dry_run and (imported or tab in {"notes_input", "property_updates_input"}):
        _autosave_snapshot()

    return {
        "status": "ok",
        "tab": tab,
        "dry_run": payload.dry_run,
        "rows_received": len(payload.rows),
        "rows_imported": imported,
        "preview_rows": previews,
        "results": results,
        "errors": errors,
    }


@router.get("/sheets/google/status")
async def google_sheets_status() -> dict[str, Any]:
    status = sheets_client_status()
    return {
        "status": "ok",
        "google_sheets_client": {
            "available": status.available,
            "auth_ok": status.auth_ok,
            "project_id": status.project_id,
            "error": status.error or None,
        },
        "default_spreadsheet_id_configured": bool(settings.default_spreadsheet_id),
        "default_spreadsheet_id": settings.default_spreadsheet_id or None,
        "tabs": {
            "properties_new_input": settings.sheets_new_properties_tab,
            "property_updates_input": settings.sheets_property_updates_tab,
            "notes_input": settings.sheets_notes_tab,
            "properties_input": settings.sheets_input_tab,
            "properties_computed": settings.sheets_computed_tab,
            "properties_master_view": settings.sheets_master_view_tab,
            "reviews_pending": settings.sheets_reviews_tab,
            "change_log_view": settings.sheets_change_log_tab,
            "today_tasks_view": settings.sheets_today_tasks_tab,
        },
    }


@router.post("/sheets/google/pull")
async def google_sheets_pull(payload: GoogleSheetsPullRequest) -> dict[str, Any]:
    spreadsheet_id = _resolve_spreadsheet_id(payload.spreadsheet_id)
    import_target = _norm(payload.import_tab).replace("-", "_") or "properties_input"
    _, source_tab = _resolve_sheet_tab_from_target(import_target, payload.source_tab)
    try:
        rows = read_sheet_rows(spreadsheet_id=spreadsheet_id, tab_name=source_tab)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"google sheets pull failed: {exc}") from exc

    import_result = await sheets_import(
        SheetImportRequest(
            tab=import_target,
            rows=rows,
            dry_run=payload.dry_run,
            auto_generate_docs=payload.auto_generate_docs,
        )
    )
    import_result["google_sheets"] = {
        "spreadsheet_id": spreadsheet_id,
        "import_tab": import_target,
        "source_tab": source_tab,
        "rows_fetched": len(rows),
    }
    return import_result


@router.post("/sheets/google/push")
async def google_sheets_push(payload: GoogleSheetsPushRequest) -> dict[str, Any]:
    spreadsheet_id = _resolve_spreadsheet_id(payload.spreadsheet_id)
    target, target_tab = _resolve_sheet_tab_from_target(payload.target, payload.target_tab)
    try:
        rows = _writeback_preview_for_tab(target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        write_result = write_sheet_rows(
            spreadsheet_id=spreadsheet_id, tab_name=target_tab, rows=rows
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"google sheets push failed: {exc}") from exc

    return {
        "status": "ok",
        "target": target,
        "target_tab": target_tab,
        "spreadsheet_id": spreadsheet_id,
        "rows_prepared": len(rows),
        "write_result": write_result,
    }


@router.post("/seed")
async def bis_seed() -> dict[str, Any]:
    if master_arena.properties:
        return {"status": "ok", "seeded": False, "reason": "already_seeded"}

    today = date.today()
    person = master_arena.upsert_person(
        Person(
            person_urn=make_urn("person"),
            full_name="Sample Owner",
            phones=["+1-512-555-0111"],
            emails=["owner@example.com"],
        )
    )
    llc = master_arena.upsert_llc(
        LlcEntity(
            llc_urn=make_urn("llc"),
            legal_name="Austin Retail Holdings LLC",
            officer_person_urns=[person.person_urn],
        )
    )
    prop = master_arena.upsert_property(
        PropertyAsset(
            property_urn=make_urn("property"),
            address_line1="7809 S 1st St",
            city="Austin",
            county="Travis",
            submarket="South Austin",
            corridor="South Lamar / Ben White",
            tenant_brand="Walgreens",
            building_sqft=14000,
            land_acres=1.8,
            year_built=2007,
            asking_price=5850000,
            noi=340000,
            current_rent_psf=24.0,
            submarket_avg_rent_psf=30.0,
            lease_expiration=_add_years_safe(today, 3),
            ownership_start=_add_years_safe(today, -12),
            owner_llc_urns=[llc.llc_urn],
            listing_status=ListingStatus.LISTED,
            listed_at=today - timedelta(days=110),
        )
    )
    note = master_arena.add_note(
        NoteEntry(
            note_urn=make_urn("note"),
            note_text="Owner asked to revisit numbers near lease rollover; potential 1031 timing concern.",
            owner_person_urn=person.person_urn,
            property_urn=prop.property_urn,
            tags=["1031", "follow-up"],
        )
    )

    result = {
        "status": "ok",
        "seeded": True,
        "person": _serialize_person(person),
        "llc": _serialize_llc(llc),
        "property": _serialize_property(prop),
        "note": _serialize_note(note),
    }
    _autosave_snapshot()
    return result


@router.post("/persons")
async def upsert_person(payload: PersonUpsertRequest) -> dict[str, Any]:
    person = Person(
        person_urn=payload.person_urn or make_urn("person"),
        full_name=payload.full_name,
        phones=payload.phones,
        emails=payload.emails,
        dnc=payload.dnc,
        notes=payload.notes,
    )
    saved = master_arena.upsert_person(person)
    _autosave_snapshot()
    return {"status": "ok", "person": _serialize_person(saved)}


@router.post("/llcs")
async def upsert_llc(payload: LlcUpsertRequest) -> dict[str, Any]:
    for person_urn in payload.officer_person_urns:
        if not master_arena.get_person(person_urn):
            raise HTTPException(status_code=404, detail=f"person not found: {person_urn}")

    llc = LlcEntity(
        llc_urn=payload.llc_urn or make_urn("llc"),
        legal_name=payload.legal_name,
        state=payload.state,
        sos_file_number=payload.sos_file_number,
        officer_person_urns=payload.officer_person_urns,
    )
    saved = master_arena.upsert_llc(llc)
    _autosave_snapshot()
    return {"status": "ok", "llc": _serialize_llc(saved)}


@router.post("/llcs/{llc_urn}/officers/{person_urn}")
async def attach_officer(llc_urn: str, person_urn: str) -> dict[str, Any]:
    if not master_arena.get_person(person_urn):
        raise HTTPException(status_code=404, detail=f"person not found: {person_urn}")
    if not master_arena.get_llc(llc_urn):
        raise HTTPException(status_code=404, detail=f"llc not found: {llc_urn}")

    master_arena.attach_officer_to_llc(person_urn=person_urn, llc_urn=llc_urn)
    llc = master_arena.get_llc(llc_urn)
    _autosave_snapshot()
    return {"status": "ok", "llc": _serialize_llc(llc)}


@router.post("/properties")
async def upsert_property(payload: PropertyUpsertRequest) -> dict[str, Any]:
    for llc_urn in payload.owner_llc_urns:
        if not master_arena.get_llc(llc_urn):
            raise HTTPException(status_code=404, detail=f"llc not found: {llc_urn}")

    property_asset = PropertyAsset(
        property_urn=payload.property_urn or make_urn("property"),
        address_line1=payload.address_line1,
        city=payload.city,
        county=payload.county,
        state=payload.state,
        postal_code=payload.postal_code,
        submarket=payload.submarket,
        corridor=payload.corridor,
        asset_type=payload.asset_type,
        tenant_brand=payload.tenant_brand,
        building_sqft=payload.building_sqft,
        land_acres=payload.land_acres,
        year_built=payload.year_built,
        asking_price=payload.asking_price,
        noi=payload.noi,
        cap_rate=payload.cap_rate,
        current_rent_psf=payload.current_rent_psf,
        submarket_avg_rent_psf=payload.submarket_avg_rent_psf,
        lease_expiration=payload.lease_expiration,
        ownership_start=payload.ownership_start,
        owner_llc_urns=payload.owner_llc_urns,
        listing_status=payload.listing_status,
        listed_at=payload.listed_at,
        sold_at=payload.sold_at,
        close_price=payload.close_price,
        listing_broker=payload.listing_broker,
        redo=payload.redo,
        potential_listing=payload.potential_listing,
    )
    saved = master_arena.upsert_property(property_asset)
    _autosave_snapshot()
    return {"status": "ok", "property": _serialize_property(saved)}


@router.post("/intake/drop")
async def intake_drop(payload: IntakeDropRequest) -> dict[str, Any]:
    result = _intake_drop_impl(payload)
    _autosave_snapshot()
    return result


@router.post("/automation/run")
async def run_automation(payload: AutomationRunRequest) -> dict[str, Any]:
    review_auto_result: dict[str, Any] = {"attempted": False}
    if payload.auto_approve_reviews:
        review_auto_result["attempted"] = True
        review_auto_result = _auto_approve_pending_reviews(
            reviewed_by="bis-automation",
            review_note="Auto-approved during automation run",
            min_confidence=payload.review_auto_min_confidence,
            field_thresholds={},
            only_fields=payload.review_auto_only_fields,
            max_items=100,
            dry_run=False,
        )

    sheets_pull: dict[str, Any] = {"attempted": False}
    if payload.sync_google_sheets_pull:
        sheets_pull["attempted"] = True
        try:
            spreadsheet_id = _resolve_spreadsheet_id("")
            rows = read_sheet_rows(
                spreadsheet_id=spreadsheet_id, tab_name=settings.sheets_input_tab
            )
            import_result = await sheets_import(
                SheetImportRequest(
                    tab="properties_input",
                    rows=rows,
                    dry_run=False,
                    auto_generate_docs=False,
                )
            )
            sheets_pull.update(
                {
                    "ok": True,
                    "spreadsheet_id": spreadsheet_id,
                    "source_tab": settings.sheets_input_tab,
                    "rows_fetched": len(rows),
                    "rows_imported": import_result.get("rows_imported", 0),
                    "errors": len(import_result.get("errors", [])),
                }
            )
        except HTTPException as exc:
            sheets_pull.update({"ok": False, "error": str(exc.detail)})
        except Exception as exc:
            sheets_pull.update({"ok": False, "error": str(exc)})

    summary = run_automation_tick(master_arena, stale_listing_days=payload.stale_listing_days)

    permit_ingested = 0
    permit_linked = 0
    permit_source_breakdown: dict[str, int] = {}
    if payload.pull_permit_signals:
        signals = await fetch_county_permit_signals(
            counties=payload.permit_counties,
            limit_per_source=payload.permit_limit,
            min_valuation=payload.permit_min_valuation,
        )
        attached = attach_signals_to_properties(master_arena, signals)
        permit_ingested = len(attached)
        permit_linked = sum(1 for signal in attached if signal.property_urn)
        for signal in attached:
            permit_source_breakdown[signal.source] = (
                permit_source_breakdown.get(signal.source, 0) + 1
            )

    news_events_created = 0
    if payload.refresh_news_intel:
        events = refresh_news_intelligence(
            master_arena,
            preferred_publications=payload.news_preferred_publications or None,
            max_queries=payload.news_max_queries,
            per_query_limit=payload.news_per_query_limit,
            lookback_days=payload.news_lookback_days,
        )
        news_events_created = len(events)

    sheets_push_results: list[dict[str, Any]] = []
    if payload.sync_google_sheets_push:
        try:
            spreadsheet_id = _resolve_spreadsheet_id("")
            for target in payload.google_sheets_push_targets:
                try:
                    normalized_target, target_tab = _resolve_sheet_tab_from_target(target)
                    rows = _writeback_preview_for_tab(normalized_target)
                    write_result = write_sheet_rows(
                        spreadsheet_id=spreadsheet_id,
                        tab_name=target_tab,
                        rows=rows,
                    )
                    sheets_push_results.append(
                        {
                            "target": normalized_target,
                            "target_tab": target_tab,
                            "ok": True,
                            "rows_prepared": len(rows),
                            "write_result": write_result,
                        }
                    )
                except Exception as exc:
                    sheets_push_results.append({"target": target, "ok": False, "error": str(exc)})
        except HTTPException as exc:
            sheets_push_results.append({"target": "all", "ok": False, "error": str(exc.detail)})
        except Exception as exc:
            sheets_push_results.append({"target": "all", "ok": False, "error": str(exc)})

    result = {
        "status": "ok",
        **summary,
        "permit_ingested": permit_ingested,
        "permit_linked_to_property": permit_linked,
        "permit_source_breakdown": permit_source_breakdown,
        "news_events_created": news_events_created,
        "review_auto_approve": review_auto_result,
        "sheets_pull": sheets_pull,
        "sheets_push_results": sheets_push_results,
    }
    if any(
        [
            summary.get("documents_generated"),
            permit_ingested,
            news_events_created,
            review_auto_result.get("approved_count", 0),
            sheets_pull.get("ok"),
            any(item.get("ok") for item in sheets_push_results),
        ]
    ):
        _autosave_snapshot()
    _record_audit_event(
        action="automation_run",
        actor="dashboard-user",
        summary=(
            f"Ran daily refresh (docs={result.get('generated_documents',0)}, alerts={result.get('listing_age_alerts',0)}, "
            f"reviews_auto={result.get('review_auto_approve',{}).get('approved_count',0)})"
        ),
        entity_type="automation",
        entity_urn="daily_refresh",
        details={
            "sheets_pull": result.get("sheets_pull", {}),
            "sheets_push_results": result.get("sheets_push_results", []),
        },
    )
    return result


@router.get("/documents")
async def list_documents(
    property_urn: str | None = None,
    owner_person_urn: str | None = None,
    doc_type: str = "",
) -> dict[str, Any]:
    documents = master_arena.list_documents(
        property_urn=property_urn,
        owner_person_urn=owner_person_urn,
        doc_type=doc_type,
    )
    return {
        "status": "ok",
        "count": len(documents),
        "documents": [_serialize_document(document) for document in documents],
    }


@router.post("/market-events")
async def create_market_event(payload: MarketEventIngestRequest) -> dict[str, Any]:
    person_urn = payload.owner_person_urn
    if not person_urn and payload.owner_name_hint.strip():
        person = _find_person_by_name(payload.owner_name_hint)
        if person is None:
            person = master_arena.upsert_person(
                Person(person_urn=make_urn("person"), full_name=payload.owner_name_hint.strip())
            )
        person_urn = person.person_urn

    property_urn = payload.property_urn
    if not property_urn and payload.property_address_hint.strip():
        existing = master_arena.find_property_by_address(payload.property_address_hint)
        if existing:
            property_urn = existing.property_urn
        elif payload.create_property_if_missing:
            created = master_arena.upsert_property(
                PropertyAsset(
                    property_urn=make_urn("property"),
                    address_line1=payload.property_address_hint.strip(),
                    city=payload.city,
                    county=payload.county,
                    owner_llc_urns=[],
                )
            )
            property_urn = created.property_urn

    attributes: dict[str, str] = {}
    if payload.list_price is not None:
        attributes["list_price"] = str(payload.list_price)
    if payload.close_price is not None:
        attributes["close_price"] = str(payload.close_price)

    try:
        event = ingest_market_event(
            master_arena,
            event_type=payload.event_type,
            title=payload.title,
            observed_at=payload.observed_at,
            property_urn=property_urn,
            property_address_hint=payload.property_address_hint,
            owner_person_urn=person_urn,
            owner_name_hint=payload.owner_name_hint,
            company_name=payload.company_name,
            source_url=payload.source_url,
            summary=payload.summary,
            attributes=attributes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    generated_docs: list[GeneratedDocument] = []
    if event.property_urn:
        generated_docs = auto_generate_documents_for_property(
            master_arena,
            property_urn=event.property_urn,
        )

    result = {
        "status": "ok",
        "event": _serialize_market_event(event),
        "generated_documents": [_serialize_document(doc) for doc in generated_docs],
    }
    _record_audit_event(
        action="market_event_create",
        actor="dashboard-user",
        summary=f"Recorded market event: {event.event_type.value} - {event.title}",
        entity_type="market_event",
        entity_urn=event.event_urn,
        details={"property_urn": event.property_urn, "company_name": event.company_name},
    )
    _autosave_snapshot()
    return result


@router.get("/market-events")
async def list_market_events(
    property_urn: str | None = None,
    owner_person_urn: str | None = None,
    event_type: str = "",
    since_days: int = 120,
) -> dict[str, Any]:
    events = master_arena.list_market_events(
        property_urn=property_urn,
        owner_person_urn=owner_person_urn,
        event_type=event_type,
        since_days=since_days,
    )
    return {
        "status": "ok",
        "count": len(events),
        "events": [_serialize_market_event(event) for event in events],
    }


@router.post("/intel/news/refresh")
async def refresh_news(payload: NewsIntelRefreshRequest) -> dict[str, Any]:
    events = refresh_news_intelligence(
        master_arena,
        queries=payload.queries or None,
        preferred_publications=payload.preferred_publications or None,
        max_queries=payload.max_queries,
        per_query_limit=payload.per_query_limit,
        lookback_days=payload.lookback_days,
    )
    publication_breakdown: dict[str, int] = {}
    address_extracted = 0
    research_queue = 0
    for event in events:
        publication = str(event.attributes.get("source_publication") or "unknown")
        publication_breakdown[publication] = publication_breakdown.get(publication, 0) + 1
        if str(event.attributes.get("address_extracted") or "").lower() == "true":
            address_extracted += 1
        if str(event.attributes.get("research_queue") or "").lower() == "true":
            research_queue += 1
    return {
        "status": "ok",
        "created": len(events),
        "publication_breakdown": publication_breakdown,
        "address_extracted_count": address_extracted,
        "research_queue_count": research_queue,
        "events": [_serialize_market_event(event) for event in events],
    }


@router.get("/intel/news/sources")
async def list_news_sources() -> dict[str, Any]:
    return {
        "status": "ok",
        "sources": news_source_preferences_as_dicts(),
        "client_notes": [
            "Community Impact and Austin Metro are prioritized for live/public ingestion in beta.",
            "Austin American-Statesman and Austin Business Journal are tracked as subscription/manual-reference sources.",
            "Vacancy/opening/new construction news items are marked research-only when no address is found.",
        ],
    }


@router.get("/intel/clients")
async def get_client_intel(
    owner_person_urn: str | None = None, since_days: int = 90
) -> dict[str, Any]:
    return client_intel_summary(
        master_arena, owner_person_urn=owner_person_urn, since_days=since_days
    )


@router.post("/properties/{property_urn}/redo")
async def set_property_redo(property_urn: str, value: bool = True) -> dict[str, Any]:
    if not master_arena.get_property(property_urn):
        raise HTTPException(status_code=404, detail="property not found")
    master_arena.apply_redo(property_urn, redo=value)
    _autosave_snapshot()
    return {
        "status": "ok",
        "property": _serialize_property(master_arena.get_property(property_urn)),
    }


@router.get("/properties/{property_urn}")
async def get_property(property_urn: str) -> dict[str, Any]:
    prop = master_arena.get_property(property_urn)
    if not prop:
        raise HTTPException(status_code=404, detail="property not found")
    return {"status": "ok", "property": _serialize_property(prop)}


@router.get("/properties/{property_urn}/listing-duration")
async def get_listing_duration(property_urn: str) -> dict[str, Any]:
    prop = master_arena.get_property(property_urn)
    if not prop:
        raise HTTPException(status_code=404, detail="property not found")
    return {
        "status": "ok",
        "property_urn": property_urn,
        "listing_status": prop.listing_status.value,
        "listed_at": prop.listed_at.isoformat() if prop.listed_at else None,
        "sold_at": prop.sold_at.isoformat() if prop.sold_at else None,
        "days_on_market": master_arena.days_on_market(property_urn),
    }


@router.get("/properties/{property_urn}/brief")
async def get_property_brief(property_urn: str) -> dict[str, Any]:
    prop = master_arena.get_property(property_urn)
    if not prop:
        raise HTTPException(status_code=404, detail="property not found")

    owners = master_arena.owners_for_property(property_urn)
    notes = master_arena.notes_rollup_for_property(property_urn)
    documents = master_arena.list_documents(property_urn=property_urn)
    market_events = master_arena.list_market_events(property_urn=property_urn, since_days=180)
    score = compute_propensity_score(
        prop, master_arena.list_signals(property_urn=property_urn, since_days=365)
    )

    return {
        "status": "ok",
        "property": _serialize_property(prop),
        "owners": [_serialize_person(owner) for owner in owners],
        "notes_rollup": [_serialize_note(note) for note in notes[:15]],
        "documents": [_serialize_document(document) for document in documents[:10]],
        "market_events": [_serialize_market_event(event) for event in market_events[:10]],
        "propensity_score": {
            "score": score.score,
            "components": score.components,
            "generated_at": score.generated_at.isoformat(),
        },
    }


@router.get("/properties/{property_urn}/score")
async def get_property_score(property_urn: str) -> dict[str, Any]:
    prop = master_arena.get_property(property_urn)
    if not prop:
        raise HTTPException(status_code=404, detail="property not found")

    signals = master_arena.list_signals(property_urn=property_urn, since_days=365)
    score = compute_propensity_score(prop, signals)
    return {
        "status": "ok",
        "property_urn": property_urn,
        "score": score.score,
        "components": score.components,
        "signal_count": len(signals),
        "generated_at": score.generated_at.isoformat(),
    }


@router.post("/notes")
async def create_note(payload: NoteCreateRequest) -> dict[str, Any]:
    if payload.owner_person_urn and not master_arena.get_person(payload.owner_person_urn):
        raise HTTPException(status_code=404, detail=f"person not found: {payload.owner_person_urn}")
    if payload.property_urn and not master_arena.get_property(payload.property_urn):
        raise HTTPException(status_code=404, detail=f"property not found: {payload.property_urn}")

    note = NoteEntry(
        note_urn=make_urn("note"),
        note_text=payload.note_text,
        owner_person_urn=payload.owner_person_urn,
        property_urn=payload.property_urn,
        tags=[tag.strip().lower() for tag in payload.tags if tag.strip()],
        created_by=payload.created_by,
    )
    saved = master_arena.add_note(note)
    review_tasks = _extract_note_to_review_tasks(saved)
    followup_tasks = _create_followup_tasks_from_note(
        note=saved,
        property_urn=saved.property_urn,
        owner_person_urn=saved.owner_person_urn,
        source_label="api-note",
    )

    generated_docs: list[GeneratedDocument] = []
    if payload.property_urn:
        generated_docs = auto_generate_documents_for_property(
            master_arena,
            property_urn=payload.property_urn,
        )
    result = {
        "status": "ok",
        "note": _serialize_note(saved),
        "review_tasks": [_serialize_review_task(task) for task in review_tasks],
        "followup_tasks": [_serialize_followup_task(task) for task in followup_tasks],
        "generated_documents": [_serialize_document(doc) for doc in generated_docs],
    }
    _autosave_snapshot()
    return result


@router.post("/notes/{note_urn}/extract-fields")
async def extract_note_fields(note_urn: str) -> dict[str, Any]:
    note = master_arena.get_note(note_urn)
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    reviews = _extract_note_to_review_tasks(note)
    return {
        "status": "ok",
        "note": _serialize_note(note),
        "review_tasks_created": len(reviews),
        "review_tasks": [_serialize_review_task(task) for task in reviews],
    }


@router.get("/reviews")
async def list_reviews(
    status: str = "", entity_urn: str | None = None, field_name: str = ""
) -> dict[str, Any]:
    tasks = master_arena.list_review_tasks(
        status=status, entity_urn=entity_urn, field_name=field_name
    )
    return {
        "status": "ok",
        "count": len(tasks),
        "reviews": [_serialize_review_task(task) for task in tasks],
    }


@router.post("/reviews/auto-approve")
async def auto_approve_reviews(payload: ReviewAutoApproveRequest) -> dict[str, Any]:
    result = _auto_approve_pending_reviews(
        reviewed_by=payload.reviewed_by,
        review_note=payload.review_note,
        min_confidence=payload.min_confidence,
        field_thresholds=payload.field_thresholds,
        only_fields=payload.only_fields,
        max_items=payload.max_items,
        dry_run=payload.dry_run,
    )
    if result.get("approved_count", 0) > 0:
        _autosave_snapshot()
    _record_audit_event(
        action="reviews_auto_approve",
        actor=payload.reviewed_by,
        summary=(
            f"Auto-approve {'previewed' if payload.dry_run else 'ran'} "
            f"({result.get('approved_count', 0)} approved, {result.get('candidates', 0)} candidates)"
        ),
        entity_type="review_queue",
        entity_urn="pending",
        details={
            "dry_run": payload.dry_run,
            "only_fields": payload.only_fields,
            "min_confidence": payload.min_confidence,
        },
    )
    return result


@router.post("/reviews/{review_urn}/approve")
async def approve_review(review_urn: str, payload: ReviewDecisionRequest) -> dict[str, Any]:
    try:
        task = master_arena.approve_review_task(
            review_urn=review_urn,
            reviewed_by=payload.reviewed_by,
            review_note=payload.review_note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _autosave_snapshot()
    _record_audit_event(
        action="review_approve",
        actor=payload.reviewed_by,
        summary=f"Approved suggested update: {task.field_name}",
        entity_type="review",
        entity_urn=review_urn,
        details={"entity_urn": task.entity_urn, "field_name": task.field_name},
    )
    return {"status": "ok", "review": _serialize_review_task(task)}


@router.post("/reviews/{review_urn}/reject")
async def reject_review(review_urn: str, payload: ReviewDecisionRequest) -> dict[str, Any]:
    try:
        task = master_arena.reject_review_task(
            review_urn=review_urn,
            reviewed_by=payload.reviewed_by,
            review_note=payload.review_note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _autosave_snapshot()
    _record_audit_event(
        action="review_reject",
        actor=payload.reviewed_by,
        summary=f"Rejected suggested update: {task.field_name}",
        entity_type="review",
        entity_urn=review_urn,
        details={"entity_urn": task.entity_urn, "field_name": task.field_name},
    )
    return {"status": "ok", "review": _serialize_review_task(task)}


@router.post("/query")
async def run_query(payload: QueryRequest) -> dict[str, Any]:
    return {"status": "ok", **agent.query(payload.query)}


@router.post("/command")
async def run_command(payload: CommandRequest) -> dict[str, Any]:
    result = agent.apply_command(payload.command, actor=payload.actor)
    status = result.get("status")
    if status == "error":
        raise HTTPException(status_code=404, detail=result)
    if status == "ok" and result.get("note_urn"):
        note = master_arena.get_note(str(result["note_urn"]))
        if note:
            reviews = _extract_note_to_review_tasks(note)
            result["review_tasks"] = [_serialize_review_task(task) for task in reviews]
    if status == "ok":
        _autosave_snapshot()
    return result


@router.post("/om/extract")
async def parse_om(payload: OMExtractRequest) -> dict[str, Any]:
    extraction = extract_om_fields(
        source_name=payload.source_name,
        property_urn=payload.property_urn,
        document_text=payload.document_text,
    )
    master_arena.add_om_extraction(extraction)
    _autosave_snapshot()

    low_confidence_fields = [key for key, value in extraction.confidences.items() if value < 0.90]

    return {
        "status": "ok",
        "extraction": {
            "extraction_urn": extraction.extraction_urn,
            "source_name": extraction.source_name,
            "property_urn": extraction.property_urn,
            "fields": extraction.fields,
            "confidences": extraction.confidences,
            "extracted_at": extraction.extracted_at.isoformat(),
        },
        "quality_gate": {
            "threshold": 0.90,
            "pass": len(low_confidence_fields) == 0,
            "low_confidence_fields": low_confidence_fields,
        },
    }


@router.post("/signals/permits/pull")
async def pull_permit_signals(payload: PermitPullRequest) -> dict[str, Any]:
    signals = await fetch_county_permit_signals(
        counties=payload.counties,
        limit_per_source=payload.limit,
        min_valuation=payload.min_valuation,
    )
    attached = attach_signals_to_properties(master_arena, signals)

    linked = sum(1 for signal in attached if signal.property_urn)
    source_breakdown: dict[str, int] = {}
    county_breakdown: dict[str, int] = {}
    for signal in attached:
        source_breakdown[signal.source] = source_breakdown.get(signal.source, 0) + 1
        county = str(
            signal.attributes.get("county")
            or ("Travis" if signal.source == "coa_open_data" else "")
        )
        if county:
            county_breakdown[county] = county_breakdown.get(county, 0) + 1
    return {
        "status": "ok",
        "ingested": len(attached),
        "linked_to_known_property": linked,
        "counties_requested": payload.counties,
        "source_breakdown": source_breakdown,
        "county_breakdown": county_breakdown,
    }


@router.get("/signals/permit-sources")
async def list_permit_sources() -> dict[str, Any]:
    return {
        "status": "ok",
        "sources": permit_source_registry(),
        "client_counties": ["Travis", "Williamson", "Hays", "Caldwell", "Bastrop"],
        "notes": [
            "Live pull is enabled for Travis (City of Austin Open Data), Hays, and Williamson public portals.",
            "Caldwell and Bastrop are listed for workflow completeness; public permit source URLs still needed.",
            "Hays/Williamson public portal list endpoints do not expose valuation in the list response.",
        ],
    }


@router.get("/signals")
async def list_signals(property_urn: str | None = None, since_days: int = 60) -> dict[str, Any]:
    signals = master_arena.list_signals(property_urn=property_urn, since_days=since_days)
    return {
        "status": "ok",
        "count": len(signals),
        "signals": [
            {
                "signal_urn": signal.signal_urn,
                "source": signal.source,
                "signal_type": signal.signal_type.value,
                "observed_at": signal.observed_at.isoformat(),
                "property_urn": signal.property_urn,
                "property_address_hint": signal.property_address_hint,
                "value_delta": signal.value_delta,
                "attributes": signal.attributes,
            }
            for signal in signals
        ],
    }


@router.get("/properties/search")
async def search_properties(
    tenant_brand: str = "",
    city: str = "",
    county: str = "",
    corridor: str = "",
    submarket: str = "",
    max_land_psf: float | None = None,
    max_building_psf: float | None = None,
    max_building_sqft: float | None = None,
    min_cap_rate: float | None = None,
    max_cap_rate: float | None = None,
    occupancy_status: str = "",
    lease_expiring_within_years: int | None = None,
    only_active_outreach: bool = False,
) -> dict[str, Any]:
    query = PropertyQuery(
        tenant_brand=tenant_brand,
        city=city,
        county=county,
        corridor=corridor,
        submarket=submarket,
        max_land_psf=max_land_psf,
        max_building_psf=max_building_psf,
        max_building_sqft=max_building_sqft,
        min_cap_rate=min_cap_rate,
        max_cap_rate=max_cap_rate,
        occupancy_status=occupancy_status,
        lease_expiring_within_years=lease_expiring_within_years,
        only_active_outreach=only_active_outreach,
    )
    matches = master_arena.query_properties(query)
    return {
        "status": "ok",
        "count": len(matches),
        "properties": [_serialize_property(item) for item in matches],
    }


@router.get("/dashboard/submarkets")
async def dashboard_submarkets() -> dict[str, Any]:
    stats: dict[str, dict[str, Any]] = {}
    for prop in master_arena.list_properties():
        key = prop.submarket or "unassigned"
        if key not in stats:
            stats[key] = {
                "submarket": key,
                "property_count": 0,
                "redo_count": 0,
                "paused_outreach_count": 0,
                "avg_propensity_score": 0.0,
                "_score_total": 0.0,
            }
        score = compute_propensity_score(
            prop, master_arena.list_signals(property_urn=prop.property_urn, since_days=365)
        )
        row = stats[key]
        row["property_count"] += 1
        row["redo_count"] += int(prop.redo)
        row["paused_outreach_count"] += int(prop.outreach_state.value == "paused")
        row["_score_total"] += score.score

    output: list[dict[str, Any]] = []
    for row in stats.values():
        count = max(1, row["property_count"])
        avg = round(row["_score_total"] / count, 2)
        output.append(
            {
                "submarket": row["submarket"],
                "property_count": row["property_count"],
                "redo_count": row["redo_count"],
                "paused_outreach_count": row["paused_outreach_count"],
                "avg_propensity_score": avg,
            }
        )

    output.sort(key=lambda row: row["submarket"])
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "submarkets": output,
    }


@router.post("/persons/{person_urn}/dnc")
async def set_person_dnc(person_urn: str, value: bool = True) -> dict[str, Any]:
    person = master_arena.get_person(person_urn)
    if not person:
        raise HTTPException(status_code=404, detail="person not found")

    master_arena.set_person_dnc(person_urn, value=value)
    person = master_arena.get_person(person_urn)
    _autosave_snapshot()
    return {"status": "ok", "person": _serialize_person(person)}
