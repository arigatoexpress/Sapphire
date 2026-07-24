"""Tests for the ``MegaETHProtocols`` intent-level facade.

Wave A: composition over ``AaveV3`` only. Read intents return frozen
dataclasses; write intents raise ``NotImplementedError("Wave C")`` so
downstream callers know not to depend on them yet.
"""

from __future__ import annotations

import pathlib
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.megaeth.protocols import (
    LendOverview,
    MegaETHProtocols,
    UserLendPosition,
)
from lib.chains.megaeth.registry import ProtocolEntry, ProtocolRegistry

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "getReservesData_response.hex"

UI_POOL = "0x1aB55bBdD5DF0782BBCf73553Af93BC6B29A286B"
POOL = "0x7e324AbC5De01d112AfC03a584966ff199741C28"
ORACLE = "0x421117D7319E96d831972b3F7e970bbfe29C4F21"


class StubClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = {k.lower(): v for k, v in responses.items()}
        self.calls: list[tuple[str, list[Any]]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        target = params[0]["to"].lower()
        if target not in self.responses:
            raise RuntimeError(f"no stub for {target}")
        return self.responses[target]


@pytest.mark.asyncio
async def test_lend_overview_aggregates_recorded_fixture() -> None:
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    raw_hex = FIXTURE.read_text(encoding="utf-8").strip()
    client = StubClient({UI_POOL: raw_hex})
    proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
    ov = await proto.lend_overview()
    assert isinstance(ov, LendOverview)
    assert ov.venue == "aave_v3"
    assert ov.reserve_count == 8
    # WETH supplied here was ~$240M+; total across reserves should be > $100M
    # but we keep the assertion loose in case mainnet snapshot drifts.
    assert ov.total_supplied_usd > Decimal(100_000_000)
    assert ov.total_borrowed_usd > Decimal(0)
    assert 0.0 < ov.avg_supply_apy < 0.10
    assert 0.0 < ov.avg_borrow_apy < 0.20
    # Top-N entries should be sorted desc by apy
    if len(ov.top_supply_apy) >= 2:
        assert ov.top_supply_apy[0]["supply_apy"] >= ov.top_supply_apy[1]["supply_apy"]
    if len(ov.top_borrow_apy) >= 2:
        assert ov.top_borrow_apy[0]["borrow_apy"] >= ov.top_borrow_apy[1]["borrow_apy"]


@pytest.mark.asyncio
async def test_lend_user_position_wraps_user_account_data() -> None:
    user = "0x" + "55" * 20
    encoded = abi_encode(
        ["uint256"] * 6,
        [10_000 * 10**8, 2_000 * 10**8, 5_000 * 10**8, 8500, 8000, 5 * 10**18],
    )
    client = StubClient({POOL: "0x" + encoded.hex()})
    proto = MegaETHProtocols(client)
    pos = await proto.lend_user_position(user)
    assert isinstance(pos, UserLendPosition)
    assert pos.user == user
    assert pos.account.total_collateral_base == 10_000 * 10**8
    assert pos.account.health_factor == Decimal(5)


@pytest.mark.asyncio
async def test_oracle_price_proxies_to_aave_oracle() -> None:
    asset = "0x" + "77" * 20
    raw = abi_encode(["uint256"], [int(2267.5 * 10**8)])
    client = StubClient({ORACLE: "0x" + raw.hex()})
    proto = MegaETHProtocols(client)
    price = await proto.oracle_price(asset)
    assert isinstance(price, Decimal)
    assert price == Decimal("2267.5")


def test_list_protocols_returns_registry_entries() -> None:
    proto = MegaETHProtocols(client=object())
    entries = proto.list_protocols()
    assert any(e.key == "aave_v3" for e in entries)
    assert all(isinstance(e, ProtocolEntry) for e in entries)


@pytest.mark.asyncio
async def test_lend_overview_rejects_non_lending_venue() -> None:
    e = ProtocolEntry(
        key="fake_dex",
        name="Fake DEX",
        category="dex_spot",
        priority=1,
        status="active",
        docs_url="",
        addresses={"router": "0x" + "0" * 40},
        abi_paths={"router": "x.json"},
    )
    reg = ProtocolRegistry({"fake_dex": e})
    proto = MegaETHProtocols(client=object(), registry=reg)
    with pytest.raises(ValueError, match="not a lending venue"):
        await proto.lend_overview("fake_dex")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method",
    ["swap", "supply", "borrow", "withdraw", "repay", "bridge"],
)
async def test_write_intents_raise_not_implemented_wave_c(method: str) -> None:
    proto = MegaETHProtocols(client=object())
    fn = getattr(proto, method)
    with pytest.raises(NotImplementedError, match="Wave C"):
        await fn()
