"""Tests for the cache-first AgentWiki Grants.gov source adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.payments.agentwiki_grants_gov import (
    GRANTS_GOV_ATTRIBUTION_NOTICE,
    GRANTS_GOV_SEARCH2_URL,
    build_grants_gov_search_request,
    search_grants_gov_opportunities,
)


class _FakeResponse:
    status = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _sample_grants_payload() -> dict[str, Any]:
    return {
        "errorcode": 0,
        "msg": "Webservice Succeeds",
        "data": {
            "hitCount": 1,
            "oppHits": [
                {
                    "id": "219999",
                    "number": "TEST-ABC-20231011-OPP1",
                    "title": "Wildfire resilience grant",
                    "agencyCode": "HHS",
                    "agencyName": "Health & Human Services",
                    "openDate": "10/11/2023",
                    "closeDate": "",
                    "oppStatus": "posted",
                    "docType": "synopsis",
                    "alnist": ["93.223"],
                }
            ],
        },
    }


def test_build_request_uses_official_search2_shape() -> None:
    body = build_grants_gov_search_request(query="wildfire", limit=500)

    assert body == {
        "rows": 50,
        "keyword": "wildfire",
        "oppNum": "",
        "eligibilities": "",
        "agencies": "",
        "oppStatuses": "forecasted|posted",
        "aln": "",
        "fundingCategories": "",
    }


def test_dry_run_never_calls_network(tmp_path: Path) -> None:
    def fail_opener(*_args, **_kwargs):
        raise AssertionError("network should not be called in dry-run mode")

    payload = search_grants_gov_opportunities(
        query="wildfire",
        limit=5,
        cache_dir=tmp_path,
        opener=fail_opener,
        generated_at="2026-05-06T00:00:00Z",
    )

    assert payload["source_mode"] == "dry_run"
    assert payload["summary"]["network_called"] is False
    assert payload["summary"]["cache_hit"] is False
    assert payload["request"]["url"] == GRANTS_GOV_SEARCH2_URL
    assert payload["request"]["body"]["keyword"] == "wildfire"
    assert payload["rights"]["attribution_notice"] == GRANTS_GOV_ATTRIBUTION_NOTICE
    assert payload["opportunities"] == []


def test_cached_payload_is_normalized_without_network(tmp_path: Path) -> None:
    request = build_grants_gov_search_request(query="wildfire", limit=5)
    dry_run = search_grants_gov_opportunities(
        query="wildfire",
        limit=5,
        cache_dir=tmp_path,
        use_cache=False,
    )
    cache_path = Path(dry_run["request"]["cache_path"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(_sample_grants_payload()), encoding="utf-8")

    payload = search_grants_gov_opportunities(
        query=request["keyword"],
        limit=request["rows"],
        cache_dir=tmp_path,
    )

    row = payload["opportunities"][0]
    assert payload["source_mode"] == "cache"
    assert payload["summary"]["cache_hit"] is True
    assert payload["summary"]["network_called"] is False
    assert payload["summary"]["hit_count"] == 1
    assert row["source_id"] == "grants_gov"
    assert row["opportunity_id"] == "219999"
    assert row["opportunity_number"] == "TEST-ABC-20231011-OPP1"
    assert row["agency"]["code"] == "HHS"
    assert row["evidence"]["official_award_status_claimed"] is False


def test_live_fetch_requires_explicit_flag_and_can_write_cache(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def opener(request, *, timeout):
        calls.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "body": json.loads(request.data.decode("utf-8")),
            }
        )
        return _FakeResponse(_sample_grants_payload())

    payload = search_grants_gov_opportunities(
        query="wildfire",
        limit=5,
        fetch_live=True,
        write_cache=True,
        cache_dir=tmp_path,
        opener=opener,
    )

    assert calls == [
        {
            "url": GRANTS_GOV_SEARCH2_URL,
            "timeout": 10.0,
            "body": payload["request"]["body"],
        }
    ]
    assert payload["source_mode"] == "live"
    assert payload["summary"]["network_called"] is True
    assert payload["summary"]["cache_written"] is True
    assert Path(payload["request"]["cache_path"]).exists()
    assert payload["opportunities"][0]["title"] == "Wildfire resilience grant"
