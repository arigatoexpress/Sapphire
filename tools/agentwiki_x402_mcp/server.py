#!/usr/bin/env python3
"""MCP-compatible stdio server for Sapphire AgentWiki x402 routes.

This server is intentionally thin: it calls the authenticated dashboard x402
routes and only reads the non-secret receipt ledger. It does not crawl sources,
settle payments, trade, send Telegram messages, or mutate production systems.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8080"
DEFAULT_PASSWORD_FILE = "~/.config/sapphire-secrets/dashboard_password"
DEFAULT_PAYER = "0x2222222222222222222222222222222222222222"


class AgentWikiMcpError(RuntimeError):
    """Raised for user-facing MCP tool errors."""


def _json_dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _require_text(args: Mapping[str, Any], key: str) -> str:
    value = str(args.get(key) or "").strip()
    if not value:
        raise AgentWikiMcpError(f"{key} is required")
    return value


def _resolve_dashboard_password() -> str:
    for key in ("SAPPHIRE_DASHBOARD_PASSWORD", "AUTH_PASSWORD"):
        value = os.environ.get(key)
        if value:
            return value
    password_file = Path(
        os.environ.get("SAPPHIRE_DASHBOARD_PASSWORD_FILE", DEFAULT_PASSWORD_FILE)
    ).expanduser()
    if password_file.exists():
        return password_file.read_text(encoding="utf-8").strip()
    raise AgentWikiMcpError(
        "dashboard auth password unavailable; set SAPPHIRE_DASHBOARD_PASSWORD "
        "or SAPPHIRE_DASHBOARD_PASSWORD_FILE"
    )


def _build_basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def build_simulated_payment_header(
    *,
    amount_atomic: int,
    pay_to: str,
    asset: str,
    network: str,
    artifact_id: str,
    payer: str = DEFAULT_PAYER,
    nonce: str | None = None,
) -> str:
    """Build a local/testnet-only x402 header accepted by Sapphire's mock verifier."""

    resolved_nonce = nonce or f"agentwiki-mcp-{artifact_id}-{time.time_ns()}"
    tx_hash = "0x" + hashlib.sha256(resolved_nonce.encode("utf-8")).hexdigest()
    payload = {
        "payload": {
            "amount": int(amount_atomic),
            "payTo": pay_to,
            "asset": asset,
            "network": network,
            "from": payer,
            "txHash": tx_hash,
            "nonce": resolved_nonce,
        }
    }
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


@dataclass
class DashboardClient:
    """Small authenticated JSON client for local dashboard routes."""

    base_url: str = DEFAULT_DASHBOARD_URL
    username: str = "sapphire"
    password: str | None = None
    timeout_seconds: float = 10.0
    opener: Callable[..., Any] | None = None

    @classmethod
    def from_env(cls) -> DashboardClient:
        return cls(
            base_url=os.environ.get("SAPPHIRE_DASHBOARD_URL", DEFAULT_DASHBOARD_URL).rstrip("/"),
            username=os.environ.get("SAPPHIRE_DASHBOARD_USERNAME", "sapphire"),
            password=_resolve_dashboard_password(),
            timeout_seconds=float(os.environ.get("SAPPHIRE_DASHBOARD_TIMEOUT", "10")),
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        url = self._url(path, query or {})
        request_headers = {
            "Accept": "application/json",
            "Authorization": _build_basic_auth(self.username, self.password or ""),
        }
        request_headers.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=data,
            headers=request_headers,
            method=method.upper(),
        )
        open_url = self.opener or urllib.request.urlopen
        try:
            with open_url(request, timeout=self.timeout_seconds) as response:
                payload = self._decode_response(response.read())
                payload.setdefault("http_status", response.status)
                return payload
        except urllib.error.HTTPError as exc:
            payload = self._decode_response(exc.read())
            payload.setdefault("ok", False)
            payload["http_status"] = exc.code
            payload["payment_required"] = exc.code == 402
            return payload
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise AgentWikiMcpError(
                f"dashboard request failed: {type(exc).__name__}: {exc}"
            ) from exc

    def _url(self, path: str, query: Mapping[str, Any]) -> str:
        clean_path = path if path.startswith("/") else f"/{path}"
        encoded = {
            str(key): str(value)
            for key, value in query.items()
            if value is not None and str(value) != ""
        }
        suffix = f"?{urllib.parse.urlencode(encoded)}" if encoded else ""
        return f"{self.base_url}{clean_path}{suffix}"

    @staticmethod
    def _decode_response(raw: bytes) -> dict[str, Any]:
        text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            return {}
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
        return {"payload": payload}


@dataclass
class AgentWikiTools:
    """Tool implementation layer shared by stdio and unit tests."""

    client: DashboardClient
    ledger_path: Path | None = None

    def wiki_search(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.client.request_json(
            "GET",
            "/api/x402/agentwiki/search",
            query={
                "q": args.get("query", args.get("q", "")),
                "category": args.get("category"),
                "limit": args.get("limit", 10),
                "max_price": args.get("max_price_usd", args.get("max_price")),
            },
        )

    def wiki_quote(self, args: Mapping[str, Any]) -> dict[str, Any]:
        artifact_id = _require_text(args, "artifact_id")
        return self.client.request_json(
            "GET",
            f"/api/x402/agentwiki/artifacts/{urllib.parse.quote(artifact_id)}/quote",
        )

    def wiki_fetch_paid(self, args: Mapping[str, Any]) -> dict[str, Any]:
        artifact_id = _require_text(args, "artifact_id")
        payment_header = str(args.get("payment_header") or "").strip()
        headers: dict[str, str] = {}
        payment_mode = "provided_header" if payment_header else "requirement_only"
        if payment_header:
            headers["X-PAYMENT"] = payment_header
        elif bool(args.get("simulate_payment", False)):
            payment_header = self._simulated_header(artifact_id, args)
            headers["X-PAYMENT"] = payment_header
            payment_mode = "simulated_local_header"

        payload = self.client.request_json(
            "POST",
            f"/api/x402/agentwiki/artifacts/{urllib.parse.quote(artifact_id)}/content",
            body={},
            headers=headers,
        )
        payload["mcp_payment"] = {
            "mode": payment_mode,
            "raw_payment_header_returned": False,
            "live_settlement_allowed": bool(
                (payload.get("payment") or {}).get("live_settlement_allowed")
            ),
        }
        return payload

    def wiki_receipt(self, args: Mapping[str, Any]) -> dict[str, Any]:
        from lib.payments.x402_products import DEFAULT_RECEIPT_LEDGER_PATH, ReceiptLedger

        ledger_path = (
            self.ledger_path
            or Path(str(args.get("ledger_path") or DEFAULT_RECEIPT_LEDGER_PATH)).expanduser()
        )
        records = [record.to_dict() for record in ReceiptLedger(ledger_path).read_all()]
        receipt_id = str(args.get("receipt_id") or "").strip()
        artifact_id = str(args.get("artifact_id") or "").strip()
        product_id = str(args.get("product_id") or "").strip()
        status = str(args.get("status") or "").strip()
        if receipt_id:
            records = [record for record in records if record["receipt_id"] == receipt_id]
        if artifact_id:
            records = [
                record for record in records if artifact_id in str(record.get("artifact_id"))
            ]
        if product_id:
            records = [record for record in records if record["product_id"] == product_id]
        if status:
            records = [record for record in records if record["status"] == status]

        try:
            limit = max(1, min(int(args.get("limit", 20)), 100))
        except (TypeError, ValueError):
            limit = 20
        include_hashes = bool(args.get("include_hashes", False))
        sanitized = [
            self._sanitize_receipt(record, include_hashes=include_hashes)
            for record in records[-limit:]
        ]
        return {
            "ok": True,
            "schema_version": 1,
            "mode": "agentwiki_receipt_lookup",
            "ledger_path": str(ledger_path),
            "summary": {
                "matched_receipt_count": len(records),
                "returned_receipt_count": len(sanitized),
                "raw_payment_headers_stored": False,
            },
            "receipts": sanitized,
        }

    def _simulated_header(self, artifact_id: str, args: Mapping[str, Any]) -> str:
        quote = self.wiki_quote({"artifact_id": artifact_id})
        payment = quote.get("payment") or {}
        pay_to = str(
            args.get("pay_to")
            or os.environ.get("SAPPHIRE_X402_SIMULATED_PAY_TO")
            or os.environ.get("X402_RECIPIENT")
            or ""
        ).strip()
        if not pay_to:
            raise AgentWikiMcpError(
                "simulate_payment requires pay_to, SAPPHIRE_X402_SIMULATED_PAY_TO, "
                "or X402_RECIPIENT"
            )
        if payment.get("live_settlement_allowed"):
            raise AgentWikiMcpError("refusing simulated payment for live-settlement product")
        return build_simulated_payment_header(
            amount_atomic=int(payment["amount_atomic"]),
            pay_to=pay_to,
            asset=str(payment["asset"]),
            network=str(payment["network"]),
            artifact_id=artifact_id,
            payer=str(args.get("payer") or DEFAULT_PAYER),
            nonce=str(args.get("nonce") or "") or None,
        )

    @staticmethod
    def _sanitize_receipt(
        record: Mapping[str, Any],
        *,
        include_hashes: bool,
    ) -> dict[str, Any]:
        allowed = {
            "receipt_id",
            "product_id",
            "resource",
            "status",
            "amount_atomic",
            "network",
            "asset",
            "payer",
            "tx_hash",
            "nonce",
            "artifact_id",
            "source_ids",
            "verification_reason",
            "recorded_at",
            "metadata",
        }
        if include_hashes:
            allowed |= {"requirement_hash", "payment_payload_hash"}
        return {key: record.get(key) for key in sorted(allowed) if key in record}


TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "wiki_search": {
        "description": "Search static rights-labeled AgentWiki artifacts through the dashboard x402 route.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "max_price_usd": {"type": "number"},
            },
        },
    },
    "wiki_quote": {
        "description": "Return a free quote, rights preview, and payment requirement for one AgentWiki artifact.",
        "inputSchema": {
            "type": "object",
            "required": ["artifact_id"],
            "properties": {"artifact_id": {"type": "string"}},
        },
    },
    "wiki_fetch_paid": {
        "description": (
            "Fetch an AgentWiki paid artifact through the x402 route. Without payment_header "
            "or simulate_payment=true this returns the HTTP 402 requirement and receipt."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["artifact_id"],
            "properties": {
                "artifact_id": {"type": "string"},
                "payment_header": {"type": "string"},
                "simulate_payment": {"type": "boolean", "default": False},
                "pay_to": {"type": "string"},
                "payer": {"type": "string"},
                "nonce": {"type": "string"},
            },
        },
    },
    "wiki_receipt": {
        "description": "Read non-secret x402 receipt records written by AgentWiki paid fetch routes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "receipt_id": {"type": "string"},
                "artifact_id": {"type": "string"},
                "product_id": {"type": "string"},
                "status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "include_hashes": {"type": "boolean", "default": False},
                "ledger_path": {"type": "string"},
            },
        },
    },
}


class AgentWikiMcpServer:
    """Minimal newline-delimited JSON-RPC server for MCP tool calls."""

    def __init__(self, tools: AgentWikiTools) -> None:
        self.tools = tools

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        if "id" not in request and str(request.get("method", "")).startswith("notifications/"):
            return None
        request_id = request.get("id")
        method = str(request.get("method") or "")
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "sapphire-agentwiki-x402", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self._tools_list()}
            elif method == "tools/call":
                params = request.get("params") or {}
                if not isinstance(params, Mapping):
                    raise AgentWikiMcpError("params must be an object")
                result = self._call_tool(params)
            else:
                return self._error(request_id, -32601, f"method not found: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except AgentWikiMcpError as exc:
            return self._error(request_id, -32000, str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._error(request_id, -32603, f"{type(exc).__name__}: {exc}")

    def _tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["inputSchema"],
            }
            for name, spec in TOOL_DEFINITIONS.items()
        ]

    def _call_tool(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = _require_text(params, "name")
        raw_args = params.get("arguments") or {}
        if not isinstance(raw_args, Mapping):
            raise AgentWikiMcpError("arguments must be an object")
        if name not in TOOL_DEFINITIONS:
            raise AgentWikiMcpError(f"unknown tool: {name}")
        handler = getattr(self.tools, name)
        payload = handler(raw_args)
        return {"content": [{"type": "text", "text": _json_dumps(payload)}]}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(server: AgentWikiMcpServer, *, stdin=sys.stdin, stdout=sys.stdout) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = server.handle(request)
        except json.JSONDecodeError as exc:
            response = AgentWikiMcpServer._error(None, -32700, f"parse error: {exc}")
        if response is not None:
            stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            stdout.flush()


def main() -> int:
    client = DashboardClient.from_env()
    server = AgentWikiMcpServer(AgentWikiTools(client))
    serve(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
