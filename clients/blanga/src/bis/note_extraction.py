from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class NoteFieldSuggestion:
    field_name: str
    proposed_value: str
    confidence: float
    rationale: str


@dataclass(frozen=True)
class FollowUpSuggestion:
    due_date: date
    intent: str
    confidence: float
    rationale: str


def _add_years_safe(source: date, years: int) -> date:
    try:
        return source.replace(year=source.year + years)
    except ValueError:
        return source + timedelta(days=365 * years)


def extract_field_suggestions(note_text: str, *, today: date | None = None) -> list[NoteFieldSuggestion]:
    text = (note_text or "").strip()
    lowered = text.lower()
    today = today or date.today()
    suggestions: list[NoteFieldSuggestion] = []

    lease_years_match = re.search(r"\b(\d{1,2})\s+years?\s+left\s+on\s+the\s+lease\b", lowered)
    if not lease_years_match:
        lease_years_match = re.search(r"\blease\s+(?:expires?|expiration)\s+in\s+(\d{1,2})\s+years?\b", lowered)
    if lease_years_match:
        years_left = int(lease_years_match.group(1))
        lease_exp = _add_years_safe(today, years_left)
        suggestions.append(
            NoteFieldSuggestion(
                field_name="lease_expiration",
                proposed_value=lease_exp.isoformat(),
                confidence=0.82,
                rationale=f"Parsed lease term from note text ({years_left} years left).",
            )
        )

    if any(term in lowered for term in ["vacant", "vacated", "tenant vacated", "dark store"]):
        suggestions.append(
            NoteFieldSuggestion(
                field_name="occupancy_status",
                proposed_value="vacant",
                confidence=0.88,
                rationale="Vacancy language detected in note text.",
            )
        )

    tenant_match = re.search(r"\btenant\s+(?:is|=)\s+([a-z0-9& .'-]{2,})", lowered)
    if tenant_match:
        suggestions.append(
            NoteFieldSuggestion(
                field_name="tenant_brand",
                proposed_value=tenant_match.group(1).strip().title(),
                confidence=0.74,
                rationale="Parsed tenant label from note text.",
            )
        )

    return suggestions


def extract_follow_up_suggestions(note_text: str, *, today: date | None = None) -> list[FollowUpSuggestion]:
    text = (note_text or "").strip()
    lowered = text.lower()
    today = today or date.today()
    if not text:
        return []

    suggestions: list[FollowUpSuggestion] = []
    patterns = [
        r"\bfollow[\s-]*up\s+(?:on|for)?\s*(\d{1,2}/\d{1,2}/\d{2,4})\b",
        r"\bcall\s+back\s+(?:on|for)?\s*(\d{1,2}/\d{1,2}/\d{2,4})\b",
        r"\breach\s+back\s+out\s+(?:on|for)?\s*(\d{1,2}/\d{1,2}/\d{2,4})\b",
    ]
    due_date: date | None = None
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue
        raw = match.group(1)
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                due_date = datetime.strptime(raw, fmt).date()
                break
            except ValueError:
                continue
        if due_date:
            break

    if due_date is None:
        relative_match = re.search(r"\bfollow[\s-]*up\s+in\s+(\d{1,3})\s+days?\b", lowered)
        if relative_match:
            due_date = today + timedelta(days=int(relative_match.group(1)))

    if due_date is None:
        return suggestions

    intent = "follow_up"
    if "looking to sell" in lowered or "wants to sell" in lowered or "considering sale" in lowered:
        intent = "seller_follow_up"
    elif "lease" in lowered and any(word in lowered for word in ["renew", "expiration", "expires"]):
        intent = "lease_follow_up"
    elif "vacant" in lowered or "vacated" in lowered:
        intent = "vacancy_follow_up"

    suggestions.append(
        FollowUpSuggestion(
            due_date=due_date,
            intent=intent,
            confidence=0.9 if intent != "follow_up" else 0.84,
            rationale="Detected follow-up timing language in note text.",
        )
    )
    return suggestions
