"""Tests for the route-backed AgentWiki x402 MCP surface."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from tools.agentwiki_x402_mcp.server import AgentWikiMcpServer, AgentWikiTools

ARTIFACT_ID = "aw_opportunities_federal_fit"
RECIPIENT = "0x1111111111111111111111111111111111111111"
ASSET = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
NETWORK = "base-sepolia"


class FakeDashboardClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        call = {
            "method": method,
            "path": path,
            "query": query or {},
            "body": body or {},
            "headers": headers or {},
        }
        self.calls.append(call)
        if path.endswith("/search"):
            return {
                "ok": True,
                "mode": "agentwiki_discovery",
                "artifacts": [{"artifact_id": ARTIFACT_ID}],
            }
        if path.endswith("/quote"):
            return {
                "ok": True,
                "mode": "agentwiki_quote",
                "payment": {
                    "amount_atomic": 250_000,
                    "asset": ASSET,
                    "network": NETWORK,
                    "live_settlement_allowed": False,
                },
            }
        if path.endswith("/content") and headers and headers.get("X-PAYMENT"):
            return {
                "ok": True,
                "mode": "agentwiki_paid_artifact",
                "artifact_id": ARTIFACT_ID,
                "payment": {
                    "status": "accepted",
                    "amount_atomic": 250_000,
                    "live_settlement_allowed": False,
                },
            }
        if path.endswith("/content"):
            return {
                "ok": False,
                "http_status": 402,
                "payment_required": True,
                "receipt": {"status": "required"},
            }
        raise AssertionError(f"unexpected route: {method} {path}")


def test_mcp_lists_agentwiki_tools() -> None:
    server = AgentWikiMcpServer(AgentWikiTools(FakeDashboardClient()))

    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert {"wiki_search", "wiki_quote", "wiki_fetch_paid", "wiki_receipt"} <= tool_names


def test_search_and_quote_call_dashboard_routes() -> None:
    client = FakeDashboardClient()
    tools = AgentWikiTools(client)

    search = tools.wiki_search({"query": "grants", "limit": 3})
    quote = tools.wiki_quote({"artifact_id": ARTIFACT_ID})

    assert search["mode"] == "agentwiki_discovery"
    assert quote["mode"] == "agentwiki_quote"
    assert client.calls[0]["path"] == "/api/x402/agentwiki/search"
    assert client.calls[0]["query"]["q"] == "grants"
    assert client.calls[1]["path"].endswith(f"/{ARTIFACT_ID}/quote")


def test_fetch_paid_defaults_to_requirement_only_without_payment_header() -> None:
    client = FakeDashboardClient()
    tools = AgentWikiTools(client)

    payload = tools.wiki_fetch_paid({"artifact_id": ARTIFACT_ID})

    assert payload["http_status"] == 402
    assert payload["mcp_payment"]["mode"] == "requirement_only"
    assert "X-PAYMENT" not in client.calls[-1]["headers"]


def test_fetch_paid_requires_explicit_simulated_payment(monkeypatch) -> None:
    monkeypatch.setenv("X402_RECIPIENT", RECIPIENT)
    client = FakeDashboardClient()
    tools = AgentWikiTools(client)

    payload = tools.wiki_fetch_paid(
        {"artifact_id": ARTIFACT_ID, "simulate_payment": True, "nonce": "unit-test-nonce"}
    )

    payment_header = client.calls[-1]["headers"]["X-PAYMENT"]
    payment_payload = json.loads(base64.b64decode(payment_header).decode("utf-8"))
    assert payload["payment"]["status"] == "accepted"
    assert payload["mcp_payment"]["mode"] == "simulated_local_header"
    assert payload["mcp_payment"]["raw_payment_header_returned"] is False
    assert payment_payload["payload"]["payTo"] == RECIPIENT
    assert payment_payload["payload"]["amount"] == 250_000
    assert payment_header not in json.dumps(payload)


def test_receipt_lookup_sanitizes_hashes_by_default(tmp_path: Path) -> None:
    ledger_path = tmp_path / "receipts.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "receipt_id": "receipt-1",
                "product_id": "agentwiki_builder_brief",
                "resource": "http://127.0.0.1:8080/api/x402/agentwiki/artifacts/x/content",
                "status": "accepted",
                "amount_atomic": 250_000,
                "network": NETWORK,
                "asset": ASSET,
                "requirement_hash": "requirement-hash",
                "payment_payload_hash": "payment-hash",
                "payer": "0x2222222222222222222222222222222222222222",
                "tx_hash": "0xabc",
                "nonce": "nonce-1",
                "artifact_id": "awd-delivery",
                "source_ids": ["sam_gov"],
                "verification_reason": "",
                "recorded_at": "2026-05-06T23:59:00Z",
                "metadata": {"endpoint": "/api/x402/agentwiki/artifacts/x/content"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    tools = AgentWikiTools(FakeDashboardClient(), ledger_path=ledger_path)

    default_payload = tools.wiki_receipt({"product_id": "agentwiki_builder_brief"})
    hash_payload = tools.wiki_receipt(
        {"product_id": "agentwiki_builder_brief", "include_hashes": True}
    )

    assert default_payload["summary"]["matched_receipt_count"] == 1
    assert default_payload["summary"]["raw_payment_headers_stored"] is False
    assert "payment_payload_hash" not in default_payload["receipts"][0]
    assert hash_payload["receipts"][0]["payment_payload_hash"] == "payment-hash"


def test_mcp_tool_call_returns_text_json() -> None:
    server = AgentWikiMcpServer(AgentWikiTools(FakeDashboardClient()))

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "wiki_quote", "arguments": {"artifact_id": ARTIFACT_ID}},
        }
    )

    text = response["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert payload["mode"] == "agentwiki_quote"
