"""Tests for the Wave B.5 ``megaeth_protocols`` agent-facing plugin tool.

The tool sits at ``plugins/claw-sapphire/tools/megaeth_protocols.py`` (shim)
with the real impl at ``plugins/claw-sapphire/tools/internal/megaeth_protocols.py``.
It composes the ``lib.chains.megaeth.MegaETHProtocols`` facade behind a
single dispatcher, so each test verifies dispatcher routing + JSON-safe
response shape rather than re-testing the facade (which has its own
~80-test suite under ``tests/lib/chains/megaeth/``).

Test groups:

1. **Dispatcher routing** — sync paths (``describe_actions``, ``list_protocols``,
   write-action refusals) plus the async-path round-trip via injected
   stub clients.
2. **Validation** — bad action names, bad arg types, missing required args.
3. **Shape contracts** — every response is ``{"action", "ok", "data"|"error"}``;
   Decimals serialize as strings; enums as names; None passes through.
4. **Live integration** (``@pytest.mark.integration``, opt-in via
   ``SAPPHIRE_MEGAETH_INTEGRATION=1``) — round-trip the real chain for
   ``lend_overview``, ``quote_swap``, ``stable_health``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import sys
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

# ---- import the tool via the shim path (mirrors how plugin loader works) ---

PLUGINS_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGINS_ROOT.parents[1]

# IMPORTANT — sys.path hygiene before loading the tool module.
#
# The internal tool imports ``lib.chains.megaeth.protocols`` from the repo's
# top-level ``lib/`` namespace package. Pytest auto-inserts the parent
# of any package containing a ``tests/__init__.py`` — i.e. ``plugins/
# claw-sapphire/`` — onto sys.path. That dir contains a *regular*
# ``lib/`` package (with __init__.py) which shadows the repo's namespace
# ``lib/`` because regular packages always win over namespace packages
# regardless of sys.path order.
#
# Fix: remove ``plugins/claw-sapphire`` from sys.path before loading the
# tool, then put it back after. The tool module never needs the plugin's
# ``lib`` package — only the repo's ``lib.chains.megaeth.*`` modules.
_PLUGIN_ROOT_STRS = {str(PLUGINS_ROOT), str(PLUGINS_ROOT) + "/"}
_evicted_paths = [p for p in sys.path if p in _PLUGIN_ROOT_STRS]
sys.path[:] = [p for p in sys.path if p not in _PLUGIN_ROOT_STRS]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_TOOL_PATH = PLUGINS_ROOT / "tools" / "internal" / "megaeth_protocols.py"
_spec = importlib.util.spec_from_file_location("megaeth_protocols_tool", _TOOL_PATH)
assert _spec is not None and _spec.loader is not None
megaeth_protocols = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(megaeth_protocols)

# Restore any sys.path entries we evicted so other plugin tests in the
# same session (if any) don't lose their pytest-managed pythonpath.
for _p in _evicted_paths:
    if _p not in sys.path:
        sys.path.append(_p)


# ---- shared stub client (same shape as facade tests) -----------------------

USDM_TOKEN = "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7"
USDT0 = "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"
USDM_TWAP60 = "0x663B50C9DA9Bd586f855aF13e91EF2f0954c9761"
USDM_ETH_ORACLE = "0xD011778057AA740BB3703Ad4d78b3c79a1aED1cb"
KUMBAYA_QUOTER = "0x1F1a8dC7E138C34b503Ca080962aC10B75384a27"
AAVE_ORACLE = "0x421117D7319E96d831972b3F7e970bbfe29C4F21"
AAVE_POOL = "0x7e324AbC5De01d112AfC03a584966ff199741C28"
SAMPLE_USER = "0x" + "1" * 40


class StubClient:
    """eth_call multi-response router. Same shape as the facade-test stubs."""

    def __init__(self, responses: dict[str, list[str]]) -> None:
        self.responses: dict[str, list[str]] = {k.lower(): list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, list[Any]]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        if method == "eth_call":
            target = params[0]["to"].lower()
            if target in self.responses and self.responses[target]:
                return self.responses[target].pop(0)
            raise RuntimeError(f"no stub for {target} (call #{len(self.calls)})")
        if method == "eth_blockNumber":
            return "0xe1dbc9"
        raise RuntimeError(f"unexpected method: {method}")


# ---- pre-built encoded responses (mirror facade-test fixtures) -------------


def _twap60_round_data(answer: int = 99_926_428) -> str:
    return (
        "0x"
        + abi_encode(
            ["uint80", "int256", "uint256", "uint256", "uint80"],
            [1, answer, 1_700_000_000, 1_700_000_060, 1],
        ).hex()
    )


def _twap60_decimals(d: int = 8) -> str:
    return "0x" + abi_encode(["uint8"], [d]).hex()


def _eth_oracle_4tuple(usd_low: int = 10**18, usd_high: int = 10**18) -> str:
    return (
        "0x"
        + abi_encode(
            ["uint256", "uint256", "uint256", "uint256"],
            [440_643_773_379_170, 440_643_773_379_170, usd_low, usd_high],
        ).hex()
    )


def _kumbaya_quote_response(out_amount: int = 999_506) -> str:
    return (
        "0x"
        + abi_encode(
            ["uint256", "uint160", "uint32", "uint256"],
            [out_amount, 10**30, 1, 107_870],
        ).hex()
    )


def _aave_price_response(price_8dec: int = 10**8) -> str:
    return "0x" + abi_encode(["uint256"], [price_8dec]).hex()


def _erc20_total_supply(units: int) -> str:
    return "0x" + abi_encode(["uint256"], [units]).hex()


def _erc20_decimals(d: int = 18) -> str:
    return "0x" + abi_encode(["uint8"], [d]).hex()


def _erc20_balance(units: int) -> str:
    return "0x" + abi_encode(["uint256"], [units]).hex()


# ---------------------------------------------------------------------------
# 1. Sync paths — describe_actions, list_protocols, write refusals
# ---------------------------------------------------------------------------


def test_default_action_is_describe_actions() -> None:
    """No action provided → default to the self-describing manifest. The
    LLM's first call is usually a discovery probe, so this is the friendly
    default rather than an error."""
    response = megaeth_protocols.handle({})
    assert response["ok"] is True
    assert response["action"] == "describe_actions"
    assert "actions" in response["data"]
    assert response["data"]["chain_id"] == 4326


def test_describe_actions_lists_every_known_action() -> None:
    response = megaeth_protocols.handle({"action": "describe_actions"})
    listed = set(response["data"]["actions"].keys())
    assert listed == set(megaeth_protocols.VALID_ACTIONS)


def test_describe_actions_documents_write_blocks() -> None:
    """The discovery manifest tells the LLM which actions are blocked
    so it doesn't try them and waste a round-trip."""
    response = megaeth_protocols.handle({"action": "describe_actions"})
    blocked = set(response["data"]["write_actions_blocked"])
    assert {"swap", "supply", "borrow", "withdraw", "repay", "bridge"} <= blocked


def test_list_protocols_enumerates_registered_entries() -> None:
    response = megaeth_protocols.handle({"action": "list_protocols"})
    assert response["ok"] is True
    keys = {p["key"] for p in response["data"]["protocols"]}
    # Wave A + B.1 + B.2 ship these registry entries.
    assert {"aave_v3", "kumbaya", "usdm", "usdt0"} <= keys
    assert response["data"]["chain_id"] == 4326


def test_list_protocols_filters_by_category() -> None:
    response = megaeth_protocols.handle({"action": "list_protocols", "category": "stable"})
    assert response["ok"] is True
    cats = {p["category"] for p in response["data"]["protocols"]}
    assert cats == {"stable"}


@pytest.mark.parametrize(
    "write_action", ["swap", "supply", "borrow", "withdraw", "repay", "bridge"]
)
def test_write_actions_refused_with_wave_c_pointer(write_action: str) -> None:
    """Write paths route through Wave C's executor, not this read-only tool.
    The refusal points the LLM at the right destination instead of returning
    a generic 'unknown action'."""
    response = megaeth_protocols.handle({"action": write_action})
    assert response["ok"] is False
    assert "Wave C" in response["error"]
    assert "signing_verified=False" in response["error"]


def test_unknown_action_returns_clean_error_with_valid_list() -> None:
    response = megaeth_protocols.handle({"action": "definitely_not_real"})
    assert response["ok"] is False
    # The error text should help the LLM self-correct.
    assert "unknown action" in response["error"]
    assert "lend_overview" in response["error"]


def test_action_name_normalization_handles_dashes_and_underscores() -> None:
    """LLMs sometimes emit 'lend-overview' or 'LendOverview'-style names.
    We normalize before lookup so misspellings of casing/separator don't
    break the round-trip."""
    # Use describe_actions because it's sync — no chain reads needed.
    r1 = megaeth_protocols.handle({"action": "describe-actions"})
    r2 = megaeth_protocols.handle({"action": "Describe_Actions"})
    assert r1["ok"] is True
    assert r2["ok"] is True


def test_payload_must_be_dict() -> None:
    response = megaeth_protocols.handle("not a dict")  # type: ignore[arg-type]
    assert response["ok"] is False
    assert "JSON object" in response["error"]


# ---------------------------------------------------------------------------
# 2. Validation — bad arg types, missing required args
# ---------------------------------------------------------------------------


def test_lend_user_position_requires_user_address() -> None:
    response = megaeth_protocols.handle({"action": "lend_user_position", "_client": StubClient({})})
    assert response["ok"] is False
    assert "user" in response["error"]


def test_lend_user_position_rejects_short_address() -> None:
    response = megaeth_protocols.handle(
        {
            "action": "lend_user_position",
            "user": "0xabc",
            "_client": StubClient({}),
        }
    )
    assert response["ok"] is False
    assert "42-char" in response["error"]


def test_oracle_price_rejects_non_hex_address() -> None:
    response = megaeth_protocols.handle(
        {
            "action": "oracle_price",
            "asset": "0x" + "z" * 40,
            "_client": StubClient({}),
        }
    )
    assert response["ok"] is False
    # Either the hex check or eth_abi catches it; the error is non-empty.
    assert "asset" in response["error"] or "non-hex" in response["error"]


def test_quote_swap_requires_amount_in() -> None:
    response = megaeth_protocols.handle(
        {
            "action": "quote_swap",
            "token_in": USDM_TOKEN,
            "token_out": USDT0,
            "_client": StubClient({}),
        }
    )
    assert response["ok"] is False
    assert "amount_in" in response["error"]


def test_quote_swap_rejects_zero_amount() -> None:
    response = megaeth_protocols.handle(
        {
            "action": "quote_swap",
            "token_in": USDM_TOKEN,
            "token_out": USDT0,
            "amount_in": 0,
            "_client": StubClient({}),
        }
    )
    assert response["ok"] is False
    assert "amount_in" in response["error"]


def test_is_safe_for_leverage_rejects_unknown_severity_name() -> None:
    response = megaeth_protocols.handle(
        {
            "action": "is_safe_for_leverage",
            "min_severity_to_block": "TOTALLY_FAKE_SEVERITY",
            "_client": StubClient({}),
        }
    )
    assert response["ok"] is False
    assert "min_severity_to_block" in response["error"]


# ---------------------------------------------------------------------------
# 3. Async dispatch via injected client — happy paths + shape contracts
# ---------------------------------------------------------------------------


def test_stable_health_routes_through_facade_returns_jsonable_dict() -> None:
    """End-to-end happy path: build the same fixture the facade tests use,
    inject as ``_client``, expect a JSON-safe dict with severity = HEALTHY."""
    client = StubClient(
        {
            USDM_TOKEN: [
                _erc20_total_supply(360_000_000 * 10**18),
                _erc20_decimals(18),
                _erc20_balance(0),
                _erc20_balance(0),
            ],
            USDM_TWAP60: [_twap60_round_data(99_926_428), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            KUMBAYA_QUOTER: [_kumbaya_quote_response(999_506)],
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    response = megaeth_protocols.handle({"action": "stable_health", "_client": client})
    assert response["ok"] is True, response.get("error")
    data = response["data"]
    assert data["venue"] == "usdm"
    # Enum serialized as name string for LLM friendliness.
    assert data["severity"] == "HEALTHY"
    assert data["should_block_leverage"] is False
    # Decimals serialize as strings.
    assert isinstance(data["circulating_supply"], str)
    # None for off-chain-managed reads.
    assert data["collateral_ratio"] is None
    assert data["mint_open"] is None


def test_peg_status_returns_severity_name_only() -> None:
    """peg_status is the cheap variant — only the severity field."""
    client = StubClient(
        {
            USDM_TWAP60: [_twap60_round_data(99_926_428), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            KUMBAYA_QUOTER: [_kumbaya_quote_response(999_506)],
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    response = megaeth_protocols.handle({"action": "peg_status", "_client": client})
    assert response["ok"] is True, response.get("error")
    assert response["data"]["severity"] == "HEALTHY"
    assert response["data"]["venue"] == "usdm"


def test_is_safe_for_leverage_returns_bool_and_reason() -> None:
    client = StubClient(
        {
            USDM_TWAP60: [_twap60_round_data(99_926_428), _twap60_decimals(8)],
            USDM_ETH_ORACLE: [_eth_oracle_4tuple(10**18, 10**18)],
            KUMBAYA_QUOTER: [_kumbaya_quote_response(999_506)],
            AAVE_ORACLE: [_aave_price_response(10**8)],
        }
    )
    response = megaeth_protocols.handle({"action": "is_safe_for_leverage", "_client": client})
    assert response["ok"] is True, response.get("error")
    assert response["data"]["safe"] is True
    assert response["data"]["reason"] == ""


def test_oracle_price_returns_decimal_as_string() -> None:
    client = StubClient({AAVE_ORACLE: [_aave_price_response(10**8)]})
    response = megaeth_protocols.handle(
        {"action": "oracle_price", "asset": USDM_TOKEN, "_client": client}
    )
    assert response["ok"] is True, response.get("error")
    # Decimal-as-str — preserves precision through the JSON wire.
    assert isinstance(response["data"]["price_usd"], str)
    assert Decimal(response["data"]["price_usd"]) == Decimal("1.000000")


def test_quote_swap_returns_no_route_signal_when_no_quote() -> None:
    """Empty quote (no pool / all reverts) is a real data condition, not an
    error. The LLM consumes the ``no_route: true`` signal to decide."""
    client = StubClient({})
    response = megaeth_protocols.handle(
        {
            "action": "quote_swap",
            "token_in": "0x" + "a" * 40,
            "token_out": "0x" + "b" * 40,
            "amount_in": 10**18,
            "_client": client,
        }
    )
    assert response["ok"] is True
    assert response["data"]["no_route"] is True
    assert "venue_checked" in response["data"]


def test_quote_swap_accepts_human_amount_with_decimals() -> None:
    """LLMs prefer human-readable amounts ('1.5 WETH') over raw 1e18 units.
    The dispatcher accepts both shapes."""
    client = StubClient({})
    response = megaeth_protocols.handle(
        {
            "action": "quote_swap",
            "token_in": "0x" + "a" * 40,
            "token_out": "0x" + "b" * 40,
            "amount_in": 1.5,
            "decimals": 18,
            "_client": client,
        }
    )
    # No pools registered → no_route response, but amount_in normalized.
    assert response["ok"] is True
    assert response["data"]["amount_in"] == int(1.5 * 10**18)


# ---------------------------------------------------------------------------
# 4. JSON-safety helpers
# ---------------------------------------------------------------------------


def test_to_jsonable_handles_decimal_enum_dataclass_bytes() -> None:
    from dataclasses import dataclass
    from enum import Enum

    class Severity(Enum):
        OK = 1
        BAD = 2

    @dataclass
    class Sample:
        value: Decimal
        sev: Severity
        raw: bytes
        nothing: None = None

    out = megaeth_protocols._to_jsonable(
        Sample(value=Decimal("1.234567890123456789"), sev=Severity.BAD, raw=b"\x01\x02")
    )
    # Round-trips to JSON without any TypeError.
    json.dumps(out)
    assert out["value"] == "1.234567890123456789"
    assert out["sev"] == "BAD"
    assert out["raw"] == "0x0102"
    assert out["nothing"] is None


# ---------------------------------------------------------------------------
# 5. Stdin/stdout entrypoint — the hermes/scheduled-task path
# ---------------------------------------------------------------------------


def test_main_round_trips_describe_actions_through_stdin() -> None:
    stdin = io.StringIO('{"action": "describe_actions"}')
    stdout = io.StringIO()
    rc = megaeth_protocols.main(stream_in=stdin, stream_out=stdout)
    assert rc == 0
    body = json.loads(stdout.getvalue())
    assert body["ok"] is True
    assert body["action"] == "describe_actions"


def test_main_returns_nonzero_on_invalid_json() -> None:
    stdin = io.StringIO("{not valid json")
    stdout = io.StringIO()
    rc = megaeth_protocols.main(stream_in=stdin, stream_out=stdout)
    assert rc == 2
    body = json.loads(stdout.getvalue())
    assert body["ok"] is False
    assert "invalid JSON" in body["error"]


def test_main_returns_one_when_action_fails() -> None:
    """Failed action → exit code 1 (validation/refusal); 0 = success, 2 = bad input."""
    stdin = io.StringIO('{"action": "swap"}')
    stdout = io.StringIO()
    rc = megaeth_protocols.main(stream_in=stdin, stream_out=stdout)
    assert rc == 1


# ---------------------------------------------------------------------------
# 6. Live mainnet integration (gated; opt-in via env var)
# ---------------------------------------------------------------------------

INTEGRATION_ENABLED = os.getenv("SAPPHIRE_MEGAETH_INTEGRATION") == "1"


@pytest.mark.integration
@pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to run live mainnet tests",
)
def test_lend_overview_live_returns_at_least_one_reserve() -> None:
    """Live: Aave V3 has many reserves — assert at least 1."""
    response = megaeth_protocols.handle({"action": "lend_overview"})
    assert response["ok"] is True, response.get("error")
    assert response["data"]["reserve_count"] >= 1


@pytest.mark.integration
@pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to run live mainnet tests",
)
def test_quote_swap_live_returns_positive_amount_out_for_weth_usdm() -> None:
    """Live: 1 WETH → USDM should quote a positive amount on Kumbaya."""
    response = megaeth_protocols.handle(
        {
            "action": "quote_swap",
            "token_in": "0x4200000000000000000000000000000000000006",  # WETH
            "token_out": USDM_TOKEN,
            "amount_in": 10**18,
        }
    )
    assert response["ok"] is True, response.get("error")
    if response["data"].get("no_route"):
        pytest.skip("no liquid pool for WETH/USDM at this moment — chain state condition")
    assert int(response["data"]["amount_out"]) > 0


@pytest.mark.integration
@pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to run live mainnet tests",
)
def test_stable_health_live_severity_in_known_band() -> None:
    """Live: severity must be one of the 5 declared bands."""
    response = megaeth_protocols.handle({"action": "stable_health"})
    assert response["ok"] is True, response.get("error")
    assert response["data"]["severity"] in {
        "HEALTHY",
        "WARNING_50BP",
        "BREAK_100BP",
        "CRISIS_500BP",
        "CIRCUIT_BREAKER",
    }
