#!/usr/bin/env python3
"""Agent-facing read-only tool for MegaETH (chain 4326) protocol state.

Wraps the ``lib.chains.megaeth`` facade behind a single dispatcher so the
LLM tool manifest stays at one entry. Research shows tool-selection
accuracy drops 74% → 49% as manifest grows past ~8 tools, so this lane
deliberately exposes one tool with many *actions* rather than many tools.

Surface (all read-only, all return JSON-serializable dicts):

* ``lend_overview`` — Aave V3 reserve aggregate (TVL, supply/borrow APY).
* ``lend_user_position`` — per-account Aave V3 health factor + collateral.
* ``oracle_price`` — Aave V3 oracle USD price for any asset.
* ``quote_swap`` — best Kumbaya quote across fee tiers.
* ``dex_overview`` — registered DEX-spot venues with top live pools.
* ``stable_health`` — composite USDM peg + supply + auth state.
* ``peg_status`` — quick severity-only USDM peg classification.
* ``is_safe_for_leverage`` — boolean gate Wave C strategy code consumes.
* ``list_protocols`` — registry enumeration (categories + addresses).
* ``describe_actions`` — self-describing action manifest for the LLM.

Write paths (``swap``/``supply``/``borrow``/``withdraw``/``repay``/
``bridge``) are intentionally NOT exposed here. They land in Wave C
behind the ``megaeth_executor`` plugin tool with the same fail-closed
gate stack as Hyperliquid (``signing_verified=False`` until verified
end-to-end). Calls to write actions return a structured refusal.

Return shape — every action returns::

    {"action": "<name>", "ok": true, "data": {...}}
    {"action": "<name>", "ok": false, "error": "<reason>"}

JSON-safe serialization: ``Decimal`` → ``str`` (preserve precision),
dataclasses → dict via ``dataclasses.asdict``, enums → ``.name``,
``None`` → ``null``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

# Wire repo root into sys.path so ``lib.chains.megaeth.*`` imports resolve
# regardless of how the tool is invoked (stdin pipe from hermes, runpy
# from the shim, importlib for tests).
_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.chains.megaeth.protocols import MegaETHProtocols  # noqa: E402

# ---- production HTTP JSON-RPC client (built into the tool) -----------------
#
# Wave A/B.1/B.2 library code uses any duck-typed object with an
# ``async _call(method, params)`` method (see ``lib.chains.megaeth.contracts.
# base._MegaETHCallable``). The standalone tool needs a real one; we ship
# a minimal httpx-based client here so the tool stands alone without
# depending on PR #529's ``MegaETHClient`` being merged. Read-only by
# construction — the allow-list rejects every write JSON-RPC method.

#: Production MegaETH mainnet endpoint. Override via env.
DEFAULT_RPC_URL = os.environ.get("SAPPHIRE_MEGAETH_RPC_URL", "https://mainnet.megaeth.com/rpc")
DEFAULT_CHAIN_ID = int(os.environ.get("SAPPHIRE_MEGAETH_CHAIN_ID", "4326"))
DEFAULT_TIMEOUT_S = float(os.environ.get("SAPPHIRE_MEGAETH_RPC_TIMEOUT_S", "10.0"))

#: JSON-RPC method allow-list. Defense-in-depth: even if a future caller
#: passed a write method through the facade, the client refuses it before
#: hitting the wire. Mirrors the ADR-1 read-only stance from PR #529.
_ALLOWED_RPC_METHODS: frozenset[str] = frozenset(
    {
        "eth_call",
        "eth_getCode",
        "eth_getLogs",
        "eth_getBalance",
        "eth_blockNumber",
        "eth_chainId",
        "eth_gasPrice",
        "eth_getTransactionCount",
        "eth_getTransactionByHash",
        "eth_getTransactionReceipt",
        "eth_getBlockByNumber",
        "eth_getBlockByHash",
        "net_version",
    }
)


class _HttpJsonRpcClient:
    """Minimal async JSON-RPC client. Built into the tool so it has no
    dependency on PR #529's ``MegaETHClient`` until that PR merges.

    Read-only by construction — :data:`_ALLOWED_RPC_METHODS` blocks every
    write method. The library wrappers call through ``_call`` so this
    plugs straight into ``MegaETHProtocols``.
    """

    def __init__(
        self,
        rpc_url: str = DEFAULT_RPC_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self._client: Any = None  # late httpx init — keep import optional
        self._req_id = 0

    async def __aenter__(self) -> _HttpJsonRpcClient:
        import httpx  # noqa: PLC0415 — late import keeps non-RPC paths import-clean

        self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        if method not in _ALLOWED_RPC_METHODS:
            raise PermissionError(
                f"JSON-RPC method {method!r} blocked by tool allow-list "
                f"(read-only); allowed: {sorted(_ALLOWED_RPC_METHODS)}"
            )
        if self._client is None:
            raise RuntimeError("_HttpJsonRpcClient not entered; use 'async with' before _call")
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params or [],
        }
        resp = await self._client.post(self.rpc_url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            err = body["error"]
            raise RuntimeError(f"JSON-RPC error from {self.rpc_url}: {err.get('message', err)}")
        return body.get("result")


# ---- JSON serialization ----------------------------------------------------


def _to_jsonable(value: Any) -> Any:
    """Recursively convert facade return values into JSON-safe primitives.

    * ``Decimal`` → ``str`` (preserves precision; the LLM is fine with
      string numerics for stable amounts).
    * Dataclasses → dict via ``dataclasses.asdict`` then recurse.
    * Enums → ``.name`` (strings are LLM-friendlier than ints).
    * ``bytes`` → ``"0x..."`` hex.
    * Lists/tuples → list of recursively-converted items.
    * Dicts → dict of recursively-converted values.
    * Everything else passes through (handles primitive int/str/bool/None).
    """
    # IMPORTANT — check Enum BEFORE int/str/bool. ``IntEnum`` (used by
    # ``PegBreak``) is a subclass of int, so the int check would match
    # first and serialize the underlying integer instead of the friendly
    # ``.name`` the LLM consumes. Same goes for ``StrEnum`` vs str.
    if isinstance(value, enum.Enum):
        return value.name
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal):
        # ``str(Decimal)`` keeps precision; ``float`` would lose it on 18-dec tokens.
        return str(value)
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # ``asdict`` recurses into nested dataclasses already; we still walk
        # the result to handle Decimal / enum leaves the dataclass holds.
        return _to_jsonable(dataclasses.asdict(value))
    if isinstance(value, list | tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, float):
        # JSON cannot represent NaN / Infinity strictly — coerce to string
        # in those cases so the dashboard's strict-JSON consumers don't bork.
        if value != value or value in (float("inf"), float("-inf")):  # NaN check
            return str(value)
        return value
    # Last resort — stringify so the response stays valid JSON.
    return str(value)


# ---- action dispatcher -----------------------------------------------------

#: Action argument schema — used by ``describe_actions`` so the LLM can
#: introspect the tool surface. Keep concise; the LLM consults this when
#: choosing an action within the tool.
ACTION_SCHEMA: dict[str, dict[str, Any]] = {
    "lend_overview": {
        "description": "Aggregate Aave V3 reserve state on MegaETH — TVL, weighted supply/borrow APY, top APY reserves.",
        "args": {"venue": "str = 'aave_v3' (optional)"},
        "returns": "dict {venue, reserve_count, total_supplied_usd, total_borrowed_usd, avg_supply_apy, avg_borrow_apy, top_supply_apy[], top_borrow_apy[]}",
        "example": {"action": "lend_overview"},
    },
    "lend_user_position": {
        "description": "Per-account Aave V3 health factor, total collateral/debt, available borrows.",
        "args": {
            "user": "str (0x... 42-char address, REQUIRED)",
            "venue": "str = 'aave_v3' (optional)",
        },
        "returns": "dict {venue, user, account: {health_factor, total_collateral_base, total_debt_base, available_borrows_base, ltv, liquidation_threshold}}",
        "example": {
            "action": "lend_user_position",
            "user": "0x0000000000000000000000000000000000000001",
        },
    },
    "oracle_price": {
        "description": "Aave V3 oracle USD price for an asset (1e8 base currency, returned as Decimal).",
        "args": {
            "asset": "str (0x... 42-char token address, REQUIRED)",
            "venue": "str = 'aave_v3' (optional)",
        },
        "returns": "dict {asset, venue, price_usd}",
        "example": {
            "action": "oracle_price",
            "asset": "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7",
        },
    },
    "quote_swap": {
        "description": "Best Kumbaya DEX quote across fee tiers for amount_in token_in -> token_out. Read-only.",
        "args": {
            "token_in": "str (0x... 42-char address, REQUIRED)",
            "token_out": "str (0x... 42-char address, REQUIRED)",
            "amount_in": "int (raw token units, REQUIRED) OR float human amount with optional 'decimals'",
            "decimals": "int (optional, used when amount_in is a float — defaults 18)",
            "max_hops": "int = 1 (Wave B step 1 is direct-only)",
        },
        "returns": "dict {venue, token_in, token_out, amount_in, amount_out, fee_pips, hops, gas_estimate} or {ok: false} if no pool",
        "example": {
            "action": "quote_swap",
            "token_in": "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7",
            "token_out": "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb",
            "amount_in": "1000000000000000000",
        },
    },
    "dex_overview": {
        "description": "Registered DEX-spot venues with top live pools.",
        "args": {},
        "returns": "dict {venue_count, total_pool_count, venues[]}",
        "example": {"action": "dex_overview"},
    },
    "stable_health": {
        "description": "Composite USDM peg + supply + auth state. Reads 4 independent oracle/venue feeds and classifies severity. Returns the structured object Wave C leverage strategies gate on.",
        "args": {"venue": "str = 'usdm' (optional)"},
        "returns": "dict {venue, peg_snapshot, severity, should_block_leverage, block_reason, circulating_supply, collateral_ratio (None for OFT), mint_open (None), redeem_open (None)}",
        "example": {"action": "stable_health"},
    },
    "peg_status": {
        "description": "Quick severity-only USDM peg classification. Cheaper than stable_health for hot loops.",
        "args": {"venue": "str = 'usdm' (optional)"},
        "returns": "dict {venue, severity}  # severity in {HEALTHY, WARNING_50BP, BREAK_100BP, CRISIS_500BP, CIRCUIT_BREAKER}",
        "example": {"action": "peg_status"},
    },
    "is_safe_for_leverage": {
        "description": "Boolean gate the LLM consumes when deciding whether to recommend leveraged USDM exposure.",
        "args": {
            "venue": "str = 'usdm' (optional)",
            "min_severity_to_block": "str = 'BREAK_100BP' (one of the PegBreak names)",
            "require_sources": "int = 2",
        },
        "returns": "dict {safe: bool, reason: str (empty when safe)}",
        "example": {"action": "is_safe_for_leverage"},
    },
    "list_protocols": {
        "description": "Registry enumeration — every protocol Sapphire knows about on chain 4326, with category + addresses.",
        "args": {"category": "str (optional filter — lending|dex_spot|stable|...)"},
        "returns": "dict {chain_id, count, protocols[]}",
        "example": {"action": "list_protocols"},
    },
    "describe_actions": {
        "description": "Self-describing action manifest. Returns this schema. Use it to discover available actions and their args.",
        "args": {},
        "returns": "dict {actions: {name: {description, args, returns, example}}}",
        "example": {"action": "describe_actions"},
    },
}

#: Write actions intentionally NOT exposed (Wave C ownership). Calls
#: returning the structured refusal are still informative, not 'unknown'.
_WRITE_ACTIONS: frozenset[str] = frozenset(
    {"swap", "supply", "borrow", "withdraw", "repay", "bridge"}
)

VALID_ACTIONS: tuple[str, ...] = tuple(ACTION_SCHEMA.keys())


# ---- argument validation helpers -------------------------------------------


def _require_address(value: Any, name: str) -> str:
    """Validate a 42-char hex address. Raises ValueError on failure."""
    if not isinstance(value, str):
        raise ValueError(f"{name!r} must be a string, got {type(value).__name__}")
    if not value.startswith("0x") or len(value) != 42:
        raise ValueError(f"{name!r} must be a 0x-prefixed 42-char address, got {value!r}")
    # Hex check — eth_abi will reject anything non-hex on encoding too,
    # but a clean error here is better than an opaque encoding traceback.
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name!r} contains non-hex characters: {value!r}") from exc
    return value


def _require_int(value: Any, name: str) -> int:
    """Coerce ``value`` to int (accepts decimal strings + plain ints)."""
    if isinstance(value, bool):
        # bool is a subclass of int but never the right shape for amounts.
        raise ValueError(f"{name!r} must be an integer, got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{name!r} not parseable as int: {value!r}") from exc
    raise ValueError(f"{name!r} must be an integer, got {type(value).__name__}")


def _coerce_amount_in(payload: dict[str, Any]) -> int:
    """Normalize ``amount_in`` to raw token units.

    Accepts:
      * ``int`` / decimal-string ``"1000000000000000000"`` → returned as-is.
      * ``float`` / human-string ``"1.5"`` with optional ``decimals`` →
        scaled by ``10 ** decimals`` (default 18).

    Raises ``ValueError`` for negative or zero amounts.
    """
    raw = payload.get("amount_in")
    if raw is None:
        raise ValueError("'amount_in' is required (int raw units OR float human amount)")
    if isinstance(raw, bool):
        raise ValueError("'amount_in' must be a number, got bool")
    if isinstance(raw, int):
        amt = raw
    elif isinstance(raw, float):
        decimals = int(payload.get("decimals", 18))
        amt = int(round(raw * (10**decimals)))
    elif isinstance(raw, str):
        if "." in raw or "e" in raw.lower():
            decimals = int(payload.get("decimals", 18))
            amt = int(round(float(raw) * (10**decimals)))
        else:
            amt = int(raw)
    else:
        raise ValueError(f"'amount_in' has unsupported type {type(raw).__name__}")
    if amt <= 0:
        raise ValueError(f"'amount_in' must be > 0, got {amt}")
    return amt


# ---- per-action handlers ---------------------------------------------------


async def _action_lend_overview(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    venue = str(payload.get("venue", "aave_v3"))
    return await proto.lend_overview(venue=venue)


async def _action_lend_user_position(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    user = _require_address(payload.get("user"), "user")
    venue = str(payload.get("venue", "aave_v3"))
    return await proto.lend_user_position(user=user, venue=venue)


async def _action_oracle_price(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    asset = _require_address(payload.get("asset"), "asset")
    venue = str(payload.get("venue", "aave_v3"))
    price = await proto.oracle_price(asset=asset, venue=venue)
    return {"asset": asset, "venue": venue, "price_usd": price}


async def _action_quote_swap(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    token_in = _require_address(payload.get("token_in"), "token_in")
    token_out = _require_address(payload.get("token_out"), "token_out")
    amount_in = _coerce_amount_in(payload)
    max_hops = _require_int(payload.get("max_hops", 1), "max_hops")
    quote = await proto.quote_swap(
        token_in=token_in,
        token_out=token_out,
        amount_in=amount_in,
        max_hops=max_hops,
    )
    if quote is None:
        # Empty quote is a normal data condition for niche pairs — surface
        # the no-route signal explicitly so the LLM can react ("fall back
        # to CEX or skip the trade") rather than guessing from a None.
        return {
            "no_route": True,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_in,
            "venue_checked": [v.key for v in proto.registry.by_category("dex_spot")],
        }
    return quote


async def _action_dex_overview(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    return await proto.dex_overview()


async def _action_stable_health(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    venue = str(payload.get("venue", "usdm"))
    return await proto.stable_health(venue=venue)


async def _action_peg_status(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    venue = str(payload.get("venue", "usdm"))
    severity = await proto.peg_status(venue=venue)
    return {"venue": venue, "severity": severity}


async def _action_is_safe_for_leverage(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    from lib.chains.megaeth.contracts.peg_monitor import PegBreak

    venue = str(payload.get("venue", "usdm"))
    raw_min = payload.get("min_severity_to_block", "BREAK_100BP")
    if isinstance(raw_min, str):
        try:
            min_sev = PegBreak[raw_min]
        except KeyError as exc:
            raise ValueError(
                f"'min_severity_to_block' must be one of {[e.name for e in PegBreak]}, "
                f"got {raw_min!r}"
            ) from exc
    elif isinstance(raw_min, int):
        min_sev = PegBreak(raw_min)
    else:
        raise ValueError(
            f"'min_severity_to_block' must be str or int, got {type(raw_min).__name__}"
        )
    require_sources = _require_int(payload.get("require_sources", 2), "require_sources")
    safe, reason = await proto.is_safe_for_leverage(
        venue=venue,
        min_severity_to_block=min_sev,
        require_sources=require_sources,
    )
    return {"safe": safe, "reason": reason, "venue": venue}


def _action_list_protocols_sync(proto: MegaETHProtocols, payload: dict[str, Any]) -> Any:
    """Sync — no chain reads needed; the registry is in-memory."""
    category_filter = payload.get("category")
    entries = proto.list_protocols()
    if category_filter:
        entries = [e for e in entries if e.category == str(category_filter)]
    serialized = [
        {
            "key": e.key,
            "name": e.name,
            "category": e.category,
            "priority": e.priority,
            "status": e.status,
            "addresses": dict(e.addresses),
            "abi_paths": dict(e.abi_paths),
            "docs_url": e.docs_url,
        }
        for e in entries
    ]
    return {
        "chain_id": DEFAULT_CHAIN_ID,
        "count": len(serialized),
        "protocols": serialized,
    }


def _action_describe_actions_sync() -> Any:
    """Self-describing manifest — what actions exist + how to call them."""
    return {
        "tool": "megaeth_protocols",
        "chain_id": DEFAULT_CHAIN_ID,
        "rpc_url": DEFAULT_RPC_URL,
        "actions": ACTION_SCHEMA,
        "write_actions_blocked": sorted(_WRITE_ACTIONS),
        "wave_c_note": (
            "Write paths (swap/supply/borrow/withdraw/repay/bridge) are NOT "
            "exposed by this tool. They land in Wave C through "
            "plugins/claw-sapphire/tools/internal/megaeth_executor.py with "
            "the same fail-closed gate stack as Hyperliquid. Until "
            "signing_verified=True is set in code, all Wave C calls remain "
            "dry-run."
        ),
    }


# ---- main dispatcher -------------------------------------------------------

#: Async actions — each takes ``(proto, payload)`` and returns a value
#: that ``_to_jsonable`` can serialize.
_ASYNC_ACTIONS: dict[str, Any] = {
    "lend_overview": _action_lend_overview,
    "lend_user_position": _action_lend_user_position,
    "oracle_price": _action_oracle_price,
    "quote_swap": _action_quote_swap,
    "dex_overview": _action_dex_overview,
    "stable_health": _action_stable_health,
    "peg_status": _action_peg_status,
    "is_safe_for_leverage": _action_is_safe_for_leverage,
}


async def _dispatch_async(payload: dict[str, Any]) -> dict[str, Any]:
    """Async dispatcher — used for actions that hit the chain.

    Builds an HTTP RPC client per call. The connection pool is short-lived
    (single-action lifetime); for hot loops the caller should use the
    library facade directly rather than the plugin tool.
    """
    action_raw = str(payload.get("action") or "describe_actions").strip()
    action = action_raw.replace("-", "_").lower()
    handler = _ASYNC_ACTIONS.get(action)
    if handler is None:
        raise KeyError(action)

    rpc_url = str(payload.get("rpc_url") or DEFAULT_RPC_URL)
    timeout_s = float(payload.get("timeout_s") or DEFAULT_TIMEOUT_S)
    # Allow tests to inject a duck-typed client — the production path
    # builds one from the env-overridable defaults.
    injected_client = payload.pop("_client", None)

    if injected_client is not None:
        proto = MegaETHProtocols(injected_client)
        result = await handler(proto, payload)
    else:
        async with _HttpJsonRpcClient(rpc_url=rpc_url, timeout_s=timeout_s) as client:
            proto = MegaETHProtocols(client)
            result = await handler(proto, payload)
    return {"action": action, "ok": True, "data": _to_jsonable(result)}


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    """Synchronous entry — runs the async dispatcher in an event loop.

    Validation errors and write-action attempts return a structured error
    dict rather than raising; only unexpected runtime errors propagate.
    """
    if not isinstance(payload, dict):
        return {
            "action": None,
            "ok": False,
            "error": "payload must be a JSON object",
        }
    action_raw = str(payload.get("action") or "describe_actions").strip()
    action = action_raw.replace("-", "_").lower()

    # Refuse write actions with a clear pointer to Wave C.
    if action in _WRITE_ACTIONS:
        return {
            "action": action,
            "ok": False,
            "error": (
                f"Wave C — write paths not yet activated; signing_verified=False. "
                f"Action {action!r} will be exposed by megaeth_executor when the "
                f"signing-verification harness lands."
            ),
        }

    # Sync-handled actions (no chain reads).
    if action == "describe_actions":
        return {
            "action": action,
            "ok": True,
            "data": _to_jsonable(_action_describe_actions_sync()),
        }
    if action == "list_protocols":
        try:
            # list_protocols only touches the registry yaml — build a
            # facade with a no-op client.
            class _NoopClient:
                async def _call(self, *_a: Any, **_k: Any) -> Any:
                    raise RuntimeError("list_protocols should not need RPC")

            proto = MegaETHProtocols(_NoopClient())
            return {
                "action": action,
                "ok": True,
                "data": _to_jsonable(_action_list_protocols_sync(proto, payload)),
            }
        except Exception as exc:
            return {"action": action, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if action not in _ASYNC_ACTIONS:
        return {
            "action": action,
            "ok": False,
            "error": (f"unknown action {action!r}; valid: {list(VALID_ACTIONS)}"),
        }

    try:
        return asyncio.run(_dispatch_async(payload))
    except ValueError as exc:
        # Validation error from inside an action handler.
        return {"action": action, "ok": False, "error": f"validation: {exc}"}
    except KeyError as exc:
        # Registry miss / ABI miss / function miss.
        return {"action": action, "ok": False, "error": f"not found: {exc}"}
    except PermissionError as exc:
        # Allow-list refusal at the RPC layer.
        return {"action": action, "ok": False, "error": f"permission: {exc}"}
    except Exception as exc:  # noqa: BLE001 — last-line defence; report and continue
        return {
            "action": action,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def run(action: str = "describe_actions", **kwargs: Any) -> str:
    """Programmatic entry — used by direct imports + simple plugin callers."""
    return json.dumps(handle({"action": action, **kwargs}), indent=2, sort_keys=True)


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
    """Stdin-JSON-in, stdout-JSON-out entry — the hermes/scheduled-task path."""
    raw = stream_in.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        json.dump({"ok": False, "error": f"invalid JSON: {exc}"}, stream_out)
        return 2
    if not isinstance(payload, dict):
        json.dump({"ok": False, "error": "stdin payload must be a JSON object"}, stream_out)
        return 2
    response = handle(payload)
    json.dump(response, stream_out, indent=2, sort_keys=True)
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


# Explicit re-exports for the shim's importlib loader. Tests import via
# the shim, so these names need to be visible at module top-level.
__all__ = [
    "ACTION_SCHEMA",
    "DEFAULT_CHAIN_ID",
    "DEFAULT_RPC_URL",
    "VALID_ACTIONS",
    "_HttpJsonRpcClient",
    "_to_jsonable",
    "handle",
    "main",
    "run",
]
