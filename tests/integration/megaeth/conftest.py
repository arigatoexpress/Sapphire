"""Fixtures for the MegaETH integration test suite.

The whole suite is gated by ``SAPPHIRE_MEGAETH_INTEGRATION=1``. Without that
flag every test in the directory is skipped at collection time, so the suite
is safe to leave registered in CI even when no MegaETH endpoint is available.

When the flag is set, fixtures read endpoints from environment variables and
(for the chain-id fixture) optionally probe the configured RPC. Tests should
declare the fixtures they need rather than reading env directly so the skip
behaviour stays in one place.
"""

from __future__ import annotations

import os

import pytest

INTEGRATION_FLAG = "SAPPHIRE_MEGAETH_INTEGRATION"
RPC_ENV = "SAPPHIRE_MEGAETH_RPC"
WSS_ENV = "SAPPHIRE_MEGAETH_WSS"


def _integration_enabled() -> bool:
    return os.environ.get(INTEGRATION_FLAG, "").strip() == "1"


def pytest_collection_modifyitems(config, items):
    """Mark every test in this directory as skipped unless the gate is set.

    We use a session-level skip marker rather than per-test ``skipif`` so the
    intent (whole suite is opt-in) is visible from the runner output.
    """

    if _integration_enabled():
        return

    skip_marker = pytest.mark.skip(
        reason=f"set {INTEGRATION_FLAG}=1 to run MegaETH integration tests",
    )
    for item in items:
        item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def megaeth_testnet_rpc() -> str:
    """HTTPS JSON-RPC endpoint for MegaETH testnet.

    Reads ``SAPPHIRE_MEGAETH_RPC``. Skips the test if unset; this should not
    happen when the integration flag is set, but we guard explicitly so a
    half-configured environment fails loudly.
    """

    url = os.environ.get(RPC_ENV, "").strip()
    if not url:
        pytest.skip(f"{RPC_ENV} not set")
    return url


@pytest.fixture(scope="session")
def megaeth_testnet_wss() -> str:
    """WSS subscription endpoint for MegaETH testnet."""

    url = os.environ.get(WSS_ENV, "").strip()
    if not url:
        pytest.skip(f"{WSS_ENV} not set")
    return url


@pytest.fixture(scope="session")
def megaeth_chain_id(megaeth_testnet_rpc: str) -> int:
    """Resolve the testnet chain ID from the configured RPC.

    Cached at session scope so the smoke test and any downstream test that
    needs the chain ID share a single RPC call. Returns the chain ID as an
    integer (decoded from the hex string the RPC returns).
    """

    import json
    import urllib.request

    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "eth_chainId",
            "params": [],
            "id": 1,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        megaeth_testnet_rpc,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — gated by integration flag
        body = json.loads(resp.read().decode("utf-8"))
    if "result" not in body:
        pytest.fail(f"eth_chainId failed: {body!r}")
    return int(body["result"], 16)
