"""Cache-first Grants.gov source adapter for AgentWiki.

The adapter is intentionally read-only and dry-run by default. Callers must set
``fetch_live=True`` before any network request is attempted, and live responses
are written only to the caller's local cache when ``write_cache=True``.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GRANTS_GOV_SEARCH2_URL = "https://api.grants.gov/v1/api/search2"
GRANTS_GOV_SEARCH2_DOCS_URL = "https://www.grants.gov/api/common/search2"
GRANTS_GOV_TERMS_URL = "https://www.grants.gov/api/terms-conditions"
GRANTS_GOV_ATTRIBUTION_NOTICE = (
    "This product uses the Grants.gov API but is not endorsed or certified by "
    "the U.S. Department of Health and Human Services."
)
DEFAULT_CACHE_DIR = Path("~/.cache/sapphire/agentwiki/grants_gov/search2").expanduser()
DEFAULT_STATUSES = "forecasted|posted"


class GrantsGovAdapterError(RuntimeError):
    """Raised when the Grants.gov adapter cannot safely build a result."""


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _normalize_pipe_filter(value: Any, *, default: str = "") -> str:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Sequence):
        return "|".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def build_grants_gov_search_request(
    *,
    query: str = "",
    limit: int | str = 10,
    statuses: Any = DEFAULT_STATUSES,
    agencies: Any = "",
    funding_categories: Any = "",
    eligibilities: Any = "",
    funding_instruments: Any = "",
    aln: Any = "",
    opportunity_number: str = "",
) -> dict[str, Any]:
    """Build the documented Grants.gov ``search2`` request body."""

    body = {
        "rows": _bounded_int(limit, default=10, minimum=1, maximum=50),
        "keyword": str(query or "").strip(),
        "oppNum": str(opportunity_number or "").strip(),
        "eligibilities": _normalize_pipe_filter(eligibilities),
        "agencies": _normalize_pipe_filter(agencies),
        "oppStatuses": _normalize_pipe_filter(statuses, default=DEFAULT_STATUSES),
        "aln": _normalize_pipe_filter(aln),
        "fundingCategories": _normalize_pipe_filter(funding_categories),
    }
    if funding_instruments not in (None, ""):
        body["fundingInstruments"] = _normalize_pipe_filter(funding_instruments)
    return body


def search_grants_gov_opportunities(
    *,
    query: str = "",
    limit: int | str = 10,
    statuses: Any = DEFAULT_STATUSES,
    agencies: Any = "",
    funding_categories: Any = "",
    eligibilities: Any = "",
    funding_instruments: Any = "",
    aln: Any = "",
    opportunity_number: str = "",
    fetch_live: bool = False,
    use_cache: bool = True,
    write_cache: bool = False,
    cache_dir: Path | str | None = None,
    opener: Callable[..., Any] | None = None,
    timeout_seconds: float = 10.0,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Search Grants.gov through cache/dry-run by default.

    ``fetch_live=False`` never opens the network. If a matching cache file is
    present and ``use_cache=True``, the cached official response is normalized.
    Otherwise the response is a dry-run plan with the exact request body that
    would be sent.
    """

    request_body = build_grants_gov_search_request(
        query=query,
        limit=limit,
        statuses=statuses,
        agencies=agencies,
        funding_categories=funding_categories,
        eligibilities=eligibilities,
        funding_instruments=funding_instruments,
        aln=aln,
        opportunity_number=opportunity_number,
    )
    resolved_cache_dir = _resolve_cache_dir(cache_dir)
    cache_path = resolved_cache_dir / f"search2-{_request_hash(request_body)}.json"

    if use_cache and cache_path.exists():
        cached = _load_cache(cache_path)
        return _response_payload(
            request_body=request_body,
            raw_payload=cached,
            source_mode="cache",
            generated_at=generated_at,
            network_called=False,
            cache_path=cache_path,
            cache_hit=True,
            cache_written=False,
            use_cache=use_cache,
            fetch_live_requested=fetch_live,
        )

    if not fetch_live:
        return _response_payload(
            request_body=request_body,
            raw_payload=None,
            source_mode="dry_run",
            generated_at=generated_at,
            network_called=False,
            cache_path=cache_path,
            cache_hit=False,
            cache_written=False,
            use_cache=use_cache,
            fetch_live_requested=fetch_live,
        )

    live_payload = _post_search2(request_body, opener=opener, timeout_seconds=timeout_seconds)
    cache_written = False
    if write_cache:
        _write_cache(cache_path, live_payload)
        cache_written = True
    return _response_payload(
        request_body=request_body,
        raw_payload=live_payload,
        source_mode="live",
        generated_at=generated_at,
        network_called=True,
        cache_path=cache_path,
        cache_hit=False,
        cache_written=cache_written,
        use_cache=use_cache,
        fetch_live_requested=fetch_live,
    )


def _resolve_cache_dir(cache_dir: Path | str | None) -> Path:
    raw = cache_dir or os.environ.get("SAPPHIRE_AGENTWIKI_GRANTS_CACHE_DIR")
    return Path(raw).expanduser() if raw else DEFAULT_CACHE_DIR


def _request_hash(request_body: Mapping[str, Any]) -> str:
    encoded = json.dumps(request_body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _load_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GrantsGovAdapterError(f"invalid Grants.gov cache file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GrantsGovAdapterError(f"invalid Grants.gov cache file {path}: expected object")
    return payload


def _write_cache(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _post_search2(
    request_body: Mapping[str, Any],
    *,
    opener: Callable[..., Any] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        GRANTS_GOV_SEARCH2_URL,
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise GrantsGovAdapterError(
            f"Grants.gov search2 request failed: {type(exc).__name__}: {exc}"
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GrantsGovAdapterError("Grants.gov search2 returned non-JSON response") from exc
    if not isinstance(payload, dict):
        raise GrantsGovAdapterError("Grants.gov search2 returned non-object JSON")
    return payload


def _response_payload(
    *,
    request_body: Mapping[str, Any],
    raw_payload: Mapping[str, Any] | None,
    source_mode: str,
    generated_at: str | None,
    network_called: bool,
    cache_path: Path,
    cache_hit: bool,
    cache_written: bool,
    use_cache: bool,
    fetch_live_requested: bool,
) -> dict[str, Any]:
    opportunities = normalize_grants_gov_opportunities(raw_payload)
    hit_count = _hit_count(raw_payload)
    cache_age = _cache_age_seconds(cache_path) if cache_hit else None
    resolved_generated_at = generated_at or _now_iso()
    return {
        "ok": True,
        "schema_version": 1,
        "mode": "agentwiki_grants_gov_source_search",
        "safety_mode": "read_only",
        "source_mode": source_mode,
        "generated_at": resolved_generated_at,
        "source": {
            "source_id": "grants_gov",
            "name": "Grants.gov API",
            "kind": "service" if network_called else "file" if cache_hit else "probe",
            "path_or_url": str(cache_path) if cache_hit else GRANTS_GOV_SEARCH2_URL,
            "docs_url": GRANTS_GOV_SEARCH2_DOCS_URL,
            "terms_url": GRANTS_GOV_TERMS_URL,
            "generated_at": resolved_generated_at,
            "age_seconds": cache_age,
        },
        "request": {
            "method": "POST",
            "url": GRANTS_GOV_SEARCH2_URL,
            "body": dict(request_body),
            "fetch_live": fetch_live_requested,
            "network_called": network_called,
            "use_cache": use_cache,
            "write_cache": cache_written,
            "cache_path": str(cache_path),
        },
        "rights": {
            "redistribution": "derived_facts_with_citation",
            "requires_attribution": True,
            "attribution_notice": GRANTS_GOV_ATTRIBUTION_NOTICE,
            "false_representation_prohibited": True,
            "payment_is_permission": False,
            "bypass_allowed": False,
        },
        "summary": {
            "opportunity_count": len(opportunities),
            "hit_count": hit_count,
            "network_called": network_called,
            "cache_hit": cache_hit,
            "cache_written": cache_written,
            "live_fetch_requires_explicit_flag": True,
            "official_award_status_claimed": False,
        },
        "opportunities": opportunities,
        "raw_response_present": raw_payload is not None,
    }


def normalize_grants_gov_opportunities(
    raw_payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Normalize the flexible Grants.gov search response into AgentWiki rows."""

    rows = _opportunity_rows(raw_payload)
    return [_normalize_opportunity(row) for row in rows if isinstance(row, Mapping)]


def _opportunity_rows(raw_payload: Mapping[str, Any] | None) -> list[Any]:
    if not raw_payload:
        return []
    data = raw_payload.get("data")
    containers = [data, raw_payload]
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        for key in ("oppHits", "opportunities", "results", "items"):
            value = container.get(key)
            if isinstance(value, list):
                return value
    return []


def _normalize_opportunity(row: Mapping[str, Any]) -> dict[str, Any]:
    opportunity_id = _pick(row, "id", "opportunityId", "oppId")
    number = _pick(row, "number", "opportunityNumber", "oppNumber")
    agency_name = _pick(row, "agencyName", "agency", "agency_name")
    agency_code = _pick(row, "agencyCode", "agency_code")
    status = _pick(row, "oppStatus", "status", "opportunityStatus")
    aln_list = row.get("alnist") or row.get("alnList") or row.get("alns") or []
    return {
        "source_id": "grants_gov",
        "opportunity_id": opportunity_id,
        "opportunity_number": number,
        "title": _pick(row, "title", "opportunityTitle", "name"),
        "agency": {
            "name": agency_name,
            "code": agency_code,
        },
        "status": status,
        "dates": {
            "open": _pick(row, "openDate", "postedDate", "postDate"),
            "close": _pick(row, "closeDate", "closeDateStr"),
        },
        "document_type": _pick(row, "docType", "documentType"),
        "assistance_listing_numbers": list(aln_list) if isinstance(aln_list, list) else [],
        "detail_url": _pick(row, "url", "link", "synopsisUrl", "opportunityUrl"),
        "evidence": {
            "source": "grants_gov.search2",
            "source_record_id": opportunity_id,
            "source_record_number": number,
            "official_award_status_claimed": False,
        },
    }


def _pick(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _hit_count(raw_payload: Mapping[str, Any] | None) -> int | None:
    if not raw_payload:
        return None
    data = raw_payload.get("data")
    for container in (data, raw_payload):
        if not isinstance(container, Mapping):
            continue
        value = container.get("hitCount") or container.get("total") or container.get("count")
        if value not in (None, ""):
            return _bounded_int(value, default=0, minimum=0, maximum=10_000_000)
    return None


def _cache_age_seconds(path: Path) -> int | None:
    try:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return None
    return max(0, int((datetime.now(UTC) - modified_at).total_seconds()))
