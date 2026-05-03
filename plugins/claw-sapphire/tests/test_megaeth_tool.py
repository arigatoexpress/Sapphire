"""Tests for the MegaETH plugin tool (read-only RPC client).

The unit tests inject a fake httpx-shaped client and a fake WebSocket
factory; no test ever touches the network. The single integration test is
gated behind ``@pytest.mark.megaeth_integration`` and ``SAPPHIRE_MEGAETH
_INTEGRATION=1``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

TOOLS = Path(__file__).parent.parent / "tools"
ROOT = TOOLS.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("megaeth_tool", TOOLS / "internal" / "megaeth.py")
megaeth = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["megaeth_tool"] = megaeth  # required so frozen dataclass typing lookups resolve
_spec.loader.exec_module(megaeth)


# ---- helpers --------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: Any, status: int = 200) -> None:
        self._body = body
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self) -> Any:
        return self._body


class _FakeAsyncClient:
    """Minimal stand-in for ``httpx.AsyncClient``."""

    def __init__(self, responder) -> None:
        self._responder = responder
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def post(self, url: str, *, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append({"url": url, "payload": json})
        return self._responder(json)

    async def aclose(self) -> None:
        self.closed = True


def _rpc_responder(method_to_result: dict[str, Any]):
    def respond(payload: dict[str, Any]) -> _FakeResponse:
        method = payload["method"]
        if method not in method_to_result:
            return _FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "error": {"code": -32601, "message": "not found"},
                }
            )
        result = method_to_result[method]
        return _FakeResponse({"jsonrpc": "2.0", "id": payload["id"], "result": result})

    return respond


# ---- handle()/dispatcher tests -------------------------------------------


def test_unknown_action_returns_error():
    result = megaeth.handle({"action": "send_eth"})
    assert result["ok"] is False
    assert "unknown action" in result["error"].lower()


def test_balance_requires_address():
    result = megaeth.handle({"action": "balance"})
    assert result["ok"] is False
    assert "address" in result["error"].lower()


def test_tx_requires_hash():
    result = megaeth.handle({"action": "tx"})
    assert result["ok"] is False
    assert "hash" in result["error"].lower()


def test_status_uses_injected_client(monkeypatch):
    fake = _FakeAsyncClient(
        _rpc_responder(
            {
                "eth_chainId": "0x10e6",  # 4326 — mainnet
                "eth_blockNumber": "0x12d4f0",
                "eth_gasPrice": "0x3b9aca00",  # 1 gwei
            }
        )
    )

    async def _run() -> dict[str, Any]:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await megaeth._action_status(client)

    payload = asyncio.run(_run())
    assert payload["ok"] is True
    assert payload["chain_id"] == megaeth.MAINNET_CHAIN_ID == 4326
    assert payload["chain_id_matches"] is True
    assert payload["latest_block"] == 0x12D4F0
    assert payload["gas_price_wei"] == 1_000_000_000
    assert payload["gas_price_gwei"] == 1.0
    assert any(call["payload"]["method"] == "eth_chainId" for call in fake.calls)


@pytest.mark.parametrize(
    "env_chain_id, env_rpc_url, expected_chain_hex, expected_chain_int",
    [
        # Mainnet path — explicit env (matches default).
        (str(4326), "https://mainnet.megaeth.com/rpc", "0x10e6", 4326),
        # Testnet path — operator opts in via env.
        (str(6343), "https://carrot.megaeth.com/rpc", "0x18c7", 6343),
    ],
)
def test_status_works_for_both_chains(
    monkeypatch, env_chain_id, env_rpc_url, expected_chain_hex, expected_chain_int
):
    """Mainnet is the default; testnet is reachable via env override."""
    monkeypatch.setenv("SAPPHIRE_MEGAETH_CHAIN_ID", env_chain_id)
    monkeypatch.setenv("SAPPHIRE_MEGAETH_RPC_URL", env_rpc_url)
    fake = _FakeAsyncClient(
        _rpc_responder(
            {
                "eth_chainId": expected_chain_hex,
                "eth_blockNumber": "0x1",
                "eth_gasPrice": "0x3b9aca00",
            }
        )
    )

    cfg = megaeth.MegaETHConfig()
    assert cfg.chain_id == expected_chain_int
    assert cfg.http_rpc == env_rpc_url

    async def _run() -> dict[str, Any]:
        async with megaeth.MegaETHClient(config=cfg, http_client=fake) as client:
            return await megaeth._action_status(client)

    payload = asyncio.run(_run())
    assert payload["chain_id"] == expected_chain_int
    assert payload["chain_id_matches"] is True


def test_get_balance_validates_address():
    fake = _FakeAsyncClient(_rpc_responder({}))

    async def _run() -> Any:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await client.get_balance("not-an-address")

    with pytest.raises(megaeth.MegaETHError):
        asyncio.run(_run())


def test_get_balance_returns_wei():
    fake = _FakeAsyncClient(_rpc_responder({"eth_getBalance": "0xde0b6b3a7640000"}))  # 1 ETH
    addr = "0x" + "ab" * 20

    async def _run() -> int:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await client.get_balance(addr)

    wei = asyncio.run(_run())
    assert wei == 10**18


def test_get_tx_receipt_summary():
    receipt = {
        "transactionHash": "0x" + "11" * 32,
        "blockNumber": "0x10",
        "blockHash": "0x" + "22" * 32,
        "from": "0x" + "33" * 20,
        "to": "0x" + "44" * 20,
        "gasUsed": "0x5208",  # 21000
        "cumulativeGasUsed": "0x5208",
        "effectiveGasPrice": "0x3b9aca00",
        "status": "0x1",
        "contractAddress": None,
        "logs": [{"a": 1}, {"b": 2}],
    }
    fake = _FakeAsyncClient(_rpc_responder({"eth_getTransactionReceipt": receipt}))
    tx_hash = "0x" + "11" * 32

    async def _run() -> dict[str, Any]:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await megaeth._action_tx(client, tx_hash)

    payload = asyncio.run(_run())
    assert payload["ok"] is True
    assert payload["found"] is True
    assert payload["status"] == 1
    assert payload["block_number"] == 16
    assert payload["gas_used"] == 21000
    assert payload["log_count"] == 2
    assert payload["explorer_url"].endswith("/tx/" + tx_hash)


def test_get_tx_receipt_not_found():
    fake = _FakeAsyncClient(_rpc_responder({"eth_getTransactionReceipt": None}))
    tx_hash = "0x" + "ab" * 32

    async def _run() -> dict[str, Any]:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await megaeth._action_tx(client, tx_hash)

    payload = asyncio.run(_run())
    assert payload["ok"] is True
    assert payload["found"] is False


def test_rpc_method_allow_list_blocks_writes():
    """Even if a future caller tries a write method, the client refuses."""
    fake = _FakeAsyncClient(_rpc_responder({}))

    async def _run() -> Any:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await client._call("eth_sendRawTransaction", ["0xdead"])

    with pytest.raises(megaeth.MegaETHError) as exc_info:
        asyncio.run(_run())
    assert "non-read" in str(exc_info.value).lower() or "allow-list" in str(exc_info.value).lower()
    # And we never attempted to send.
    assert fake.calls == []


def test_rpc_error_object_propagates():
    def respond(payload: dict[str, Any]) -> _FakeResponse:
        return _FakeResponse(
            {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32000, "message": "boom"}}
        )

    fake = _FakeAsyncClient(respond)

    async def _run() -> Any:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await client.block_number()

    with pytest.raises(megaeth.MegaETHError) as exc:
        asyncio.run(_run())
    assert "boom" in str(exc.value)


def test_mempool_snapshot_uses_txpool_status_when_available():
    fake = _FakeAsyncClient(
        _rpc_responder(
            {
                "txpool_status": {"pending": "0x2a", "queued": "0x5"},
            }
        )
    )

    async def _run() -> dict[str, Any]:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await megaeth._action_mempool_snapshot(client, duration_seconds=0.1)

    payload = asyncio.run(_run())
    assert payload["ok"] is True
    assert payload["method"] == "txpool_status"
    assert payload["pending"] == 42
    assert payload["queued"] == 5


def test_mempool_snapshot_falls_back_to_ws_sample():
    """When txpool_status fails, fall back to WS sampling — no real WS."""

    # txpool_status returns RPC error → MegaETHClient.txpool_status returns None
    fake = _FakeAsyncClient(
        lambda payload: _FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "error": {"code": -32601, "message": "not exposed"},
            }
        )
    )

    class _FakeWS:
        async def send(self, _msg: str) -> None:
            return None

        async def recv(self) -> str:
            await asyncio.sleep(0.001)
            return json.dumps({"jsonrpc": "2.0", "id": 1, "result": "0xdeadbeef"})

        async def close(self) -> None:
            return None

    yielded = []

    class _FakeWSClient:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def _emit(self):
            for hash_ in ("0x" + "1" * 64, "0x" + "2" * 64, "0x" + "3" * 64):
                yielded.append(hash_)
                yield hash_

        def subscribe_pending_txs(self):
            return self._emit()

        def subscribe_new_heads(self):
            return self._emit()

    async def _run() -> dict[str, Any]:
        async with megaeth.MegaETHClient(http_client=fake) as client:
            return await megaeth._action_mempool_snapshot(
                client,
                duration_seconds=0.5,
                max_pending=3,
                ws_client=_FakeWSClient(),
            )

    payload = asyncio.run(_run())
    assert payload["ok"] is True
    assert payload["method"] == "newPendingTransactions"
    assert payload["sampled_count"] == 3


def test_run_returns_json_string(monkeypatch):
    monkeypatch.setattr(megaeth, "handle", lambda payload: {"ok": True, "echo": payload["action"]})

    out = json.loads(megaeth.run("status"))
    assert out == {"ok": True, "echo": "status"}


def test_main_rejects_invalid_json():
    out = io.StringIO()
    code = megaeth.main(stream_in=io.StringIO("{bad"), stream_out=out)
    assert code == 2
    assert "invalid JSON" in out.getvalue()


def test_main_rejects_non_object_json():
    out = io.StringIO()
    code = megaeth.main(stream_in=io.StringIO("[]"), stream_out=out)
    assert code == 2


def test_main_returns_nonzero_on_unknown_action():
    out = io.StringIO()
    code = megaeth.main(stream_in=io.StringIO('{"action":"trade"}'), stream_out=out)
    assert code == 1
    body = json.loads(out.getvalue())
    assert body["ok"] is False


def test_top_level_shim_exports_handle():
    spec = importlib.util.spec_from_file_location("megaeth_shim", TOOLS / "megaeth.py")
    shim = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["megaeth_shim"] = shim  # see note in module-load above
    try:
        spec.loader.exec_module(shim)
    finally:
        # The shim itself uses ``importlib.util.spec_from_file_location(__name__, _TARGET)``
        # to load the internal impl. That inner exec_module re-runs the @dataclass(frozen=True)
        # decorator, which under Python 3.12 looks up cls.__module__ in sys.modules. Make sure
        # the inner module name (``megaeth_shim`` because the shim passes __name__ through) is
        # still resolvable for the duration of the test.
        pass
    assert hasattr(shim, "handle")
    assert hasattr(shim, "MegaETHClient")
    assert hasattr(shim, "MegaETHWSClient")


def test_config_reads_env(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_MEGAETH_RPC_URL", "https://example.test/rpc")
    monkeypatch.setenv("SAPPHIRE_MEGAETH_WS_URL", "wss://example.test/ws")
    monkeypatch.setenv("SAPPHIRE_MEGAETH_CHAIN_ID", "9999")

    cfg = megaeth.MegaETHConfig()
    assert cfg.http_rpc == "https://example.test/rpc"
    assert cfg.ws_rpc == "wss://example.test/ws"
    assert cfg.chain_id == 9999


def test_default_config_targets_mainnet_with_no_ws():
    """Defaults must point at mainnet HTTP and leave WS empty.

    Public mainnet WSS does not exist; the default WS URL must be empty so
    callers don't accidentally hit a non-existent endpoint.
    """
    cfg = megaeth.MegaETHConfig()
    assert cfg.http_rpc == "https://mainnet.megaeth.com/rpc"
    assert cfg.chain_id == megaeth.MAINNET_CHAIN_ID == 4326
    assert cfg.ws_rpc == ""


def test_ws_client_refuses_when_no_ws_url(monkeypatch):
    """WS connect path raises a clear error when ``ws_rpc`` is empty."""
    cfg = megaeth.MegaETHConfig()
    assert cfg.ws_rpc == ""
    ws_client = megaeth.MegaETHWSClient(config=cfg)

    async def _run() -> Any:
        return await ws_client._connect()

    with pytest.raises(megaeth.MegaETHError) as exc_info:
        asyncio.run(_run())
    msg = str(exc_info.value).lower()
    assert "ws" in msg
    assert "partner" in msg or "set" in msg


# ---- integration test (gated) --------------------------------------------


@pytest.mark.megaeth_integration
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_MEGAETH_INTEGRATION") != "1",
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to run real-network test",
)
def test_real_network_status(monkeypatch):  # pragma: no cover - opt-in network test
    """Hits whichever network env vars point at; defaults to mainnet.

    Set ``SAPPHIRE_MEGAETH_RPC_URL`` + ``SAPPHIRE_MEGAETH_CHAIN_ID`` to
    target the carrot testnet instead of mainnet.
    """
    payload = megaeth.handle({"action": "status"})
    assert payload["ok"] is True, payload
    # Default to mainnet; the env var override may have flipped this.
    expected = int(os.getenv("SAPPHIRE_MEGAETH_CHAIN_ID") or megaeth.MAINNET_CHAIN_ID)
    assert payload["chain_id"] == expected
    assert payload["latest_block"] >= 0
