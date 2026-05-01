#!/usr/bin/env python3
"""Read-only MegaETH RPC client + Sapphire plugin tool.

MegaETH is an EVM-equivalent L2 with ~10ms blocks and a heterogeneous node
design (one sequencer executes; full nodes ingest state diffs). Because it
is EVM-compatible, the JSON-RPC surface is the same as Ethereum mainnet —
``eth_blockNumber``, ``eth_getBalance``, ``eth_getBlockByNumber``,
``eth_getTransactionReceipt``, ``eth_chainId``, ``eth_gasPrice``, plus the
``newHeads`` / ``newPendingTransactions`` subscriptions over WSS.

This module is **read-only**. It does not sign transactions, does not touch
private keys, and never calls a state-changing RPC method (no
``eth_sendRawTransaction`` / ``eth_sendTransaction``). The dispatch
``actions`` whitelist is enforced server-side by the JSON-RPC method
allow-list in ``_RPC_READ_METHODS``.

Endpoints (research'd from https://docs.megaeth.com on 2026-04-30):

* Testnet HTTPS RPC: ``https://carrot.megaeth.com/rpc``
* Testnet chain ID: ``6343``  (``0x18c7``)
* Testnet block explorer: ``https://megaeth-testnet-v2.blockscout.com``
* Testnet WSS: not currently published; ``wss://carrot.megaeth.com/ws``
  is the natural sibling of the HTTPS endpoint. Configurable via
  ``SAPPHIRE_MEGAETH_WS_URL``.

All endpoints are read from env / a config dict so they can be swapped
without code changes.

stdin JSON shape::

    {"action": "status"}
    {"action": "balance", "address": "0x..."}
    {"action": "tx", "hash": "0x..."}
    {"action": "mempool_snapshot", "duration_seconds": 3, "max": 200}

Run via shim::

    echo '{"action":"status"}' | python3 plugins/claw-sapphire/tools/megaeth.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

# Read-only RPC method allow-list. Anything not on this list is rejected
# inside ``MegaETHClient._call`` to give defense-in-depth against future
# action handlers accidentally requesting a write method.
_RPC_READ_METHODS: frozenset[str] = frozenset(
    {
        "eth_chainId",
        "eth_blockNumber",
        "eth_getBlockByNumber",
        "eth_getBlockByHash",
        "eth_getBalance",
        "eth_getTransactionByHash",
        "eth_getTransactionReceipt",
        "eth_gasPrice",
        "eth_call",  # pure read; name is historically misleading
        "eth_estimateGas",
        "txpool_status",
        "txpool_content",
        "net_version",
    }
)

# Default endpoints — see module docstring for sourcing.
DEFAULT_HTTP_RPC: str = "https://carrot.megaeth.com/rpc"
DEFAULT_WS_RPC: str = "wss://carrot.megaeth.com/ws"
DEFAULT_CHAIN_ID: int = 6343
DEFAULT_EXPLORER: str = "https://megaeth-testnet-v2.blockscout.com"


@dataclass(frozen=True)
class MegaETHConfig:
    """Endpoint config block — never hardcode endpoints elsewhere."""

    http_rpc: str = field(default_factory=lambda: os.getenv("SAPPHIRE_MEGAETH_RPC_URL") or DEFAULT_HTTP_RPC)
    ws_rpc: str = field(default_factory=lambda: os.getenv("SAPPHIRE_MEGAETH_WS_URL") or DEFAULT_WS_RPC)
    chain_id: int = field(
        default_factory=lambda: int(os.getenv("SAPPHIRE_MEGAETH_CHAIN_ID") or DEFAULT_CHAIN_ID)
    )
    explorer: str = field(default_factory=lambda: os.getenv("SAPPHIRE_MEGAETH_EXPLORER") or DEFAULT_EXPLORER)
    request_timeout: float = 10.0
    ws_timeout: float = 30.0


VALID_ACTIONS: tuple[str, ...] = ("status", "balance", "tx", "mempool_snapshot")


class MegaETHError(RuntimeError):
    """Raised for RPC-layer failures (HTTP, JSON-RPC error object)."""


def _hex_to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s, 16) if s.startswith(("0x", "0X")) else int(s)
        except ValueError:
            return None
    return None


def _wei_to_eth(wei: int | None) -> float | None:
    if wei is None:
        return None
    return wei / 1e18


class MegaETHClient:
    """Async read-only JSON-RPC client for MegaETH.

    Methods are intentionally narrow — only the read paths the dispatcher
    needs. Use ``MegaETHWSClient`` for subscriptions.
    """

    def __init__(self, config: MegaETHConfig | None = None, http_client: Any = None) -> None:
        self.config = config or MegaETHConfig()
        # ``http_client`` is dependency-injectable so unit tests can supply
        # a fake ``httpx.AsyncClient``-shaped object without ever touching
        # the network.
        self._http_client = http_client
        self._owns_client = http_client is None
        self._next_id = 0

    async def __aenter__(self) -> MegaETHClient:
        if self._http_client is None:
            import httpx  # late import — do not require httpx for callers

            self._http_client = httpx.AsyncClient(timeout=self.config.request_timeout)
            self._owns_client = True
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        if method not in _RPC_READ_METHODS:
            raise MegaETHError(
                f"refusing to call non-read RPC method '{method}' "
                f"(allow-list defined in tools/internal/megaeth.py)"
            )
        if self._http_client is None:
            raise MegaETHError("MegaETHClient must be used as an async context manager")
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": list(params or []),
        }
        try:
            response = await self._http_client.post(self.config.http_rpc, json=payload)
        except Exception as exc:  # network-layer error
            raise MegaETHError(f"RPC transport error: {exc}") from exc
        if hasattr(response, "raise_for_status"):
            try:
                response.raise_for_status()
            except Exception as exc:
                raise MegaETHError(f"RPC HTTP error: {exc}") from exc
        try:
            body = response.json()
        except Exception as exc:
            raise MegaETHError(f"RPC returned non-JSON body: {exc}") from exc
        if isinstance(body, dict) and "error" in body and body["error"]:
            raise MegaETHError(f"RPC error: {body['error']}")
        if not isinstance(body, dict) or "result" not in body:
            raise MegaETHError(f"RPC malformed response: {body!r}")
        return body["result"]

    # ---- read methods -----------------------------------------------------
    async def chain_id(self) -> int:
        result = await self._call("eth_chainId", [])
        value = _hex_to_int(result)
        if value is None:
            raise MegaETHError(f"unparseable chain_id: {result!r}")
        return value

    async def block_number(self) -> int:
        result = await self._call("eth_blockNumber", [])
        value = _hex_to_int(result)
        if value is None:
            raise MegaETHError(f"unparseable block_number: {result!r}")
        return value

    async def get_block(self, number_or_tag: int | str = "latest", *, full: bool = False) -> dict[str, Any]:
        if isinstance(number_or_tag, int):
            tag = hex(number_or_tag)
        else:
            tag = str(number_or_tag).lower()
        result = await self._call("eth_getBlockByNumber", [tag, bool(full)])
        if not isinstance(result, dict):
            raise MegaETHError(f"unexpected block payload: {result!r}")
        return result

    async def get_balance(self, address: str, *, block: str = "latest") -> int:
        if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
            raise MegaETHError(f"invalid address: {address!r}")
        result = await self._call("eth_getBalance", [address, block])
        value = _hex_to_int(result)
        if value is None:
            raise MegaETHError(f"unparseable balance: {result!r}")
        return value

    async def get_tx_receipt(self, tx_hash: str) -> dict[str, Any] | None:
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x") or len(tx_hash) != 66:
            raise MegaETHError(f"invalid tx hash: {tx_hash!r}")
        result = await self._call("eth_getTransactionReceipt", [tx_hash])
        if result is None:
            return None
        if not isinstance(result, dict):
            raise MegaETHError(f"unexpected receipt payload: {result!r}")
        return result

    async def gas_price(self) -> int:
        result = await self._call("eth_gasPrice", [])
        value = _hex_to_int(result)
        if value is None:
            raise MegaETHError(f"unparseable gas_price: {result!r}")
        return value

    async def txpool_status(self) -> dict[str, Any] | None:
        """Best-effort txpool_status — not every node exposes it.

        Returns ``None`` if the method is unavailable on this endpoint.
        """
        # We don't include ``txpool_status`` reads as a hard requirement —
        # if the upstream node refuses the call we degrade gracefully.
        try:
            result = await self._call("txpool_status", [])
        except MegaETHError:
            return None
        if isinstance(result, dict):
            return result
        return None


class MegaETHWSClient:
    """Async WebSocket helper for ``newHeads`` / ``newPendingTransactions``.

    Wraps the ``websockets`` library (already a Sapphire dep). The two
    subscription helpers below are async generators so callers can drive
    them with ``async for``.
    """

    def __init__(self, config: MegaETHConfig | None = None, ws_factory: Any = None) -> None:
        self.config = config or MegaETHConfig()
        self._ws_factory = ws_factory  # injectable for tests

    async def _connect(self) -> Any:
        if self._ws_factory is not None:
            return await self._ws_factory(self.config.ws_rpc)
        import websockets  # late import

        # ``websockets.connect`` is itself an async context manager; we
        # await its ``__aenter__`` equivalent via ``connect`` and let the
        # caller close the resulting connection.
        return await websockets.connect(self.config.ws_rpc, open_timeout=self.config.ws_timeout)

    async def _subscribe(self, subscription: str) -> AsyncIterator[dict[str, Any]]:
        ws = await self._connect()
        try:
            sub_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": [subscription],
            }
            await ws.send(json.dumps(sub_payload))
            # First message is the subscription ack; we don't surface it.
            ack_raw = await ws.recv()
            try:
                ack = json.loads(ack_raw)
            except json.JSONDecodeError as exc:
                raise MegaETHError(f"WS ack non-JSON: {exc}") from exc
            if isinstance(ack, dict) and ack.get("error"):
                raise MegaETHError(f"WS subscribe error: {ack['error']}")
            while True:
                raw = await ws.recv()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict) and msg.get("method") == "eth_subscription":
                    params = msg.get("params") or {}
                    payload = params.get("result")
                    if isinstance(payload, dict):
                        yield payload
                    elif payload is not None:
                        yield {"value": payload}
        finally:
            close = getattr(ws, "close", None)
            if close is not None:
                try:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass

    def subscribe_new_heads(self) -> AsyncIterator[dict[str, Any]]:
        """Async generator yielding parsed block-header payloads."""
        return self._subscribe("newHeads")

    def subscribe_pending_txs(self) -> AsyncIterator[str | dict[str, Any]]:
        return self._subscribe("newPendingTransactions")


# ---- action dispatcher ----------------------------------------------------


async def _action_status(client: MegaETHClient) -> dict[str, Any]:
    chain_id = await client.chain_id()
    latest = await client.block_number()
    gas = await client.gas_price()
    return {
        "ok": True,
        "endpoint": client.config.http_rpc,
        "chain_id": chain_id,
        "expected_chain_id": client.config.chain_id,
        "chain_id_matches": chain_id == client.config.chain_id,
        "latest_block": latest,
        "gas_price_wei": gas,
        "gas_price_gwei": gas / 1e9 if gas is not None else None,
        "explorer": client.config.explorer,
    }


async def _action_balance(client: MegaETHClient, address: str) -> dict[str, Any]:
    wei = await client.get_balance(address)
    return {
        "ok": True,
        "address": address,
        "balance_wei": wei,
        "balance_eth": _wei_to_eth(wei),
        "endpoint": client.config.http_rpc,
    }


async def _action_tx(client: MegaETHClient, tx_hash: str) -> dict[str, Any]:
    receipt = await client.get_tx_receipt(tx_hash)
    if receipt is None:
        return {"ok": True, "tx_hash": tx_hash, "found": False}
    status_hex = receipt.get("status")
    summary = {
        "ok": True,
        "tx_hash": tx_hash,
        "found": True,
        "status": _hex_to_int(status_hex),
        "block_number": _hex_to_int(receipt.get("blockNumber")),
        "block_hash": receipt.get("blockHash"),
        "from": receipt.get("from"),
        "to": receipt.get("to"),
        "contract_address": receipt.get("contractAddress"),
        "gas_used": _hex_to_int(receipt.get("gasUsed")),
        "cumulative_gas_used": _hex_to_int(receipt.get("cumulativeGasUsed")),
        "effective_gas_price": _hex_to_int(receipt.get("effectiveGasPrice")),
        "log_count": len(receipt.get("logs") or []),
        "explorer_url": f"{client.config.explorer.rstrip('/')}/tx/{tx_hash}",
    }
    return summary


async def _action_mempool_snapshot(
    client: MegaETHClient,
    *,
    duration_seconds: float = 3.0,
    max_pending: int = 500,
    ws_client: MegaETHWSClient | None = None,
) -> dict[str, Any]:
    """Return a mempool size snapshot.

    Tries ``txpool_status`` first; if not exposed, falls back to sampling
    ``newPendingTransactions`` for ``duration_seconds``.
    """
    txpool = await client.txpool_status()
    if txpool is not None:
        pending = _hex_to_int(txpool.get("pending"))
        queued = _hex_to_int(txpool.get("queued"))
        return {
            "ok": True,
            "method": "txpool_status",
            "pending": pending,
            "queued": queued,
            "raw": txpool,
            "endpoint": client.config.http_rpc,
        }

    # Fallback: best-effort sample. Returns the count of pending tx
    # hashes seen during the sampling window. Bounded by ``max_pending``.
    sampled: list[str | dict[str, Any]] = []
    ws = ws_client or MegaETHWSClient(client.config)
    duration = max(0.1, float(duration_seconds))

    async def _sampler() -> None:
        async for item in ws.subscribe_pending_txs():
            sampled.append(item)
            if len(sampled) >= max_pending:
                break

    try:
        await asyncio.wait_for(_sampler(), timeout=duration)
    except TimeoutError:
        pass
    except Exception as exc:
        return {
            "ok": False,
            "method": "newPendingTransactions",
            "error": f"WS sampling failed: {exc}",
            "endpoint": client.config.ws_rpc,
        }

    return {
        "ok": True,
        "method": "newPendingTransactions",
        "duration_seconds": duration,
        "sampled_count": len(sampled),
        "max_pending": max_pending,
        "endpoint": client.config.ws_rpc,
    }


def _validate_action(payload: dict[str, Any]) -> str:
    raw = payload.get("action") or "status"
    action = str(raw).strip().lower().replace("-", "_")
    if action not in VALID_ACTIONS:
        raise MegaETHError(f"unknown action '{raw}'. valid: {list(VALID_ACTIONS)}")
    return action


async def _dispatch_async(payload: dict[str, Any]) -> dict[str, Any]:
    action = _validate_action(payload)
    config = MegaETHConfig()
    async with MegaETHClient(config) as client:
        if action == "status":
            return await _action_status(client)
        if action == "balance":
            address = payload.get("address")
            if not isinstance(address, str):
                raise MegaETHError("'balance' requires 'address' (0x... hex)")
            return await _action_balance(client, address)
        if action == "tx":
            tx_hash = payload.get("hash") or payload.get("tx_hash")
            if not isinstance(tx_hash, str):
                raise MegaETHError("'tx' requires 'hash' (0x... 32-byte hex)")
            return await _action_tx(client, tx_hash)
        if action == "mempool_snapshot":
            duration = float(payload.get("duration_seconds") or 3.0)
            max_pending = int(payload.get("max") or 500)
            return await _action_mempool_snapshot(
                client, duration_seconds=duration, max_pending=max_pending
            )
    # Should be unreachable.
    raise MegaETHError(f"action '{action}' not implemented")


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    """Sync entry point — runs the async dispatcher."""
    try:
        return asyncio.run(_dispatch_async(payload))
    except MegaETHError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # network / decode / asyncio fallout
        return {"ok": False, "error": f"unexpected: {exc.__class__.__name__}: {exc}"}


def run(action: str = "status", **kwargs: Any) -> str:
    return json.dumps(handle({"action": action, **kwargs}), indent=2, sort_keys=True)


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
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
