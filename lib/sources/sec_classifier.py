"""SEC filing classifier — pure, deterministic.

Maps SEC filings (8-K with item codes, 10-Q, 10-K, amendments) into
structured :class:`FilingEvent` records carrying:

- ``ticker`` — e.g. "AAPL"
- ``form`` — e.g. "8-K", "10-Q"
- ``items`` — raw 8-K item code(s), e.g. "1.01,8.01" (empty for 10-Q/K)
- ``severity`` — "low" / "medium" / "high"
- ``direction`` — "bull" / "bear" / "neutral"
- ``summary`` — short human-readable hint
- ``filed_at``, ``accession``, ``primary_document``, ``retrieved_at``

Source of truth for item-code semantics: SEC's `Form 8-K General Instructions
<https://www.sec.gov/files/form8-k.pdf>`_ + `Current Report on Form 8-K
<https://www.sec.gov/fast-answers/answersform8khtm.html>`_, retrieved
2026-04-29.

These mappings are intentionally conservative. We bias toward "neutral"
when the item code is ambiguous; downstream correlator weights filter
the noise.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 8-K item code → (severity, direction, label)
# ---------------------------------------------------------------------------

# Severities:
#   "high"   — likely to move the stock; usually material.
#   "medium" — relevant but not always material.
#   "low"    — disclosure-only, ceremonial.
# Directions:
#   "bull"   — generally positive read.
#   "bear"   — generally negative read.
#   "neutral" — ambiguous or pure-disclosure.
ITEM_8K_MAP: dict[str, tuple[str, str, str]] = {
    # 1.x — Registrant's business and operations
    "1.01": ("high", "neutral", "Material definitive agreement entered into"),
    "1.02": ("high", "bear", "Material definitive agreement terminated"),
    "1.03": ("high", "bear", "Bankruptcy or receivership"),
    "1.04": ("medium", "bear", "Mine safety — reporting of shutdowns/orders"),
    # 2.x — Financial information
    "2.01": ("high", "neutral", "Completion of acquisition or disposition of assets"),
    "2.02": ("high", "neutral", "Results of operations and financial condition"),
    "2.03": ("medium", "neutral", "Creation of direct financial obligation"),
    "2.04": ("high", "bear", "Triggering events accelerating financial obligation"),
    "2.05": ("medium", "bear", "Costs associated with exit or disposal activities"),
    "2.06": ("high", "bear", "Material impairments"),
    # 3.x — Securities and trading markets
    "3.01": ("high", "bear", "Listing standards / delisting notice"),
    "3.02": ("medium", "neutral", "Unregistered sales of equity securities"),
    "3.03": ("medium", "neutral", "Material modification to rights of security holders"),
    # 4.x — Matters related to accountants and financial statements
    "4.01": ("high", "bear", "Change in registrant's certifying accountant"),
    "4.02": (
        "high",
        "bear",
        "Non-reliance on previously issued financials (restatement)",
    ),
    # 5.x — Corporate governance and management
    "5.01": ("medium", "neutral", "Changes in control of registrant"),
    "5.02": ("medium", "neutral", "Departure / appointment of officers / directors"),
    "5.03": ("low", "neutral", "Amendments to articles / bylaws"),
    "5.04": ("medium", "neutral", "Temporary suspension of trading under benefit plan"),
    "5.05": ("low", "neutral", "Amendments to code of ethics"),
    "5.06": ("medium", "neutral", "Change in shell company status"),
    "5.07": ("low", "neutral", "Submission of matters to a vote of security holders"),
    "5.08": ("low", "neutral", "Shareholder director nominations"),
    # 6.x — Asset-backed securities
    "6.01": ("low", "neutral", "ABS informational and computational material"),
    "6.02": ("low", "neutral", "Change of servicer or trustee"),
    "6.03": ("medium", "neutral", "Change in credit enhancement"),
    "6.04": ("low", "neutral", "Failure to make a required distribution"),
    "6.05": ("medium", "bear", "Securities Act updating disclosure"),
    # 7.x — Regulation FD
    "7.01": ("low", "neutral", "Regulation FD disclosure"),
    # 8.x — Other events
    "8.01": ("low", "neutral", "Other events (registrant elected disclosure)"),
    # 9.x — Financial statements and exhibits
    "9.01": ("low", "neutral", "Financial statements and exhibits"),
}

# Forms not 8-K
FORM_BASE_MAP: dict[str, tuple[str, str, str]] = {
    "10-K": ("high", "neutral", "Annual report"),
    "10-K/A": ("high", "neutral", "Annual report amendment"),
    "10-Q": ("high", "neutral", "Quarterly report"),
    "10-Q/A": ("high", "neutral", "Quarterly report amendment"),
    "8-K": ("medium", "neutral", "Current report"),
    "8-K/A": ("medium", "neutral", "Current report amendment"),
}


SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class FilingEvent:
    """A classified SEC filing event."""

    ticker: str
    form: str
    items: str
    severity: str
    direction: str
    summary: str
    filed_at: str
    accession: str
    primary_document: str = ""
    retrieved_at: str = ""
    asset_hints: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Item code parsing
# ---------------------------------------------------------------------------


def parse_item_codes(items_field: str) -> list[str]:
    """Parse SEC's ``items`` recent-filings column into bare item codes.

    Examples of inputs we've observed in submissions JSON:

    - ``"1.01,2.03"``
    - ``"Item 5.02"``
    - ``"5.02,7.01,9.01"``
    - ``""`` (10-K / 10-Q have no items)
    """
    if not items_field:
        return []
    raw = str(items_field).replace("Item", "").replace("ITEM", "").replace("item", "")
    parts = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    out: list[str] = []
    for part in parts:
        # Tolerate formats like "1.01:" or "1.01-Material agreement"
        token = part.split()[0].rstrip(".:;-")
        # Validate shape: must be N.NN
        if "." in token:
            head, _, tail = token.partition(".")
            if head.isdigit() and tail.isdigit():
                out.append(f"{int(head)}.{int(tail):02d}")
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_filing(
    *,
    ticker: str,
    form: str,
    items_field: str = "",
    filed_at: str = "",
    accession: str = "",
    primary_document: str = "",
    retrieved_at: str = "",
) -> FilingEvent:
    """Classify a single filing record into a :class:`FilingEvent`."""

    form_norm = (form or "").upper().strip()
    item_codes = parse_item_codes(items_field)
    severity, direction, summary = _resolve(form=form_norm, items=item_codes)
    asset_hints = (ticker.upper(),) if ticker else ()
    return FilingEvent(
        ticker=ticker.upper(),
        form=form_norm,
        items=",".join(item_codes),
        severity=severity,
        direction=direction,
        summary=summary,
        filed_at=filed_at,
        accession=accession,
        primary_document=primary_document,
        retrieved_at=retrieved_at,
        asset_hints=asset_hints,
    )


def _resolve(*, form: str, items: list[str]) -> tuple[str, str, str]:
    """Resolve (severity, direction, summary) from form + items."""
    base = FORM_BASE_MAP.get(form)

    # 8-K: items dominate (more specific than the form-base default).
    if form.startswith("8-K"):
        if items:
            mapped = [(code, ITEM_8K_MAP.get(code)) for code in items]
            mapped = [(code, m) for code, m in mapped if m is not None]
            if mapped:
                # Highest severity wins; if tied, bear > bull > neutral.
                mapped.sort(key=lambda r: _rank(r[1]), reverse=True)  # type: ignore[arg-type]
                top_code, top_meta = mapped[0]
                assert top_meta is not None
                summary_label = top_meta[2]
                if len(mapped) > 1:
                    summary_label = f"{top_meta[2]} (+{len(mapped) - 1} other items)"
                return top_meta[0], top_meta[1], f"8-K item {top_code}: {summary_label}"
        if base:
            return base[0], base[1], base[2]

    # 10-K / 10-Q / amendments: form-base alone.
    if base:
        return base[0], base[1], base[2]

    # Unknown form (NT-10K, ARS, etc.). Stay conservative.
    return "low", "neutral", f"Filing form {form} (uncategorized)"


def _rank(meta: tuple[str, str, str] | None) -> tuple[int, int]:
    """Sort key: higher severity first, then bear > bull > neutral."""
    if meta is None:
        return (0, 0)
    sev = SEVERITY_RANK.get(meta[0], 0)
    direction_rank = {"bear": 2, "bull": 1, "neutral": 0}.get(meta[1], 0)
    return (sev, direction_rank)


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def summarize_severity(events: Iterable[FilingEvent]) -> dict[str, int]:
    """Count events by severity bucket."""
    out = {"low": 0, "medium": 0, "high": 0, "unknown": 0}
    for event in events:
        key = (event.severity or "unknown").lower()
        out[key if key in out else "unknown"] += 1
    return out


def summarize_direction(events: Iterable[FilingEvent]) -> dict[str, int]:
    """Count events by direction bucket."""
    out = {"bull": 0, "bear": 0, "neutral": 0}
    for event in events:
        key = (event.direction or "neutral").lower()
        out[key if key in out else "neutral"] += 1
    return out


def filter_high_severity(events: Iterable[FilingEvent]) -> list[FilingEvent]:
    return [e for e in events if (e.severity or "").lower() == "high"]


def is_amendment(form: str) -> bool:
    return (form or "").upper().endswith("/A")


__all__ = [
    "FORM_BASE_MAP",
    "FilingEvent",
    "ITEM_8K_MAP",
    "SEVERITY_RANK",
    "classify_filing",
    "filter_high_severity",
    "is_amendment",
    "parse_item_codes",
    "summarize_direction",
    "summarize_severity",
]
