"""Tests for the USDM (USDm) typed wrapper.

Recorded fixtures captured against MegaETH mainnet on 2026-04-30 from
``https://mainnet.megaeth.com/rpc``. No network is hit by these tests —
the StubClient pattern from Wave A's ``test_aave_v3.py`` and Wave B.1's
``test_kumbaya.py`` is reused.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode
from eth_utils import keccak

from lib.chains.megaeth.contracts.usdm import (
    AAVE_BASE_CURRENCY_UNIT,
    BPS_DENOMINATOR,
    BURN_ADDRESSES,
    USDM,
    MintEvent,
    PegQuote,
    RedeemEvent,
    USDMAddresses,
    _decode_burn,
    _decode_mint,
    _scale_token,
    _topic_to_address,
    divergence_bps,
)
from lib.chains.megaeth.registry import ProtocolRegistry

# Mainnet addresses used in fixture capture.
USDM_TOKEN = "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7"
USDM_TWAP60 = "0x663B50C9DA9Bd586f855aF13e91EF2f0954c9761"
USDM_ETH_ORACLE = "0xD011778057AA740BB3703Ad4d78b3c79a1aED1cb"

ADDRS = USDMAddresses(
    token=USDM_TOKEN,
    twap60_oracle=USDM_TWAP60,
    eth_oracle=USDM_ETH_ORACLE,
)


class StubClient:
    """Returns pre-staged hex responses keyed by 'to' address.

    Multi-response support: if the value is a list, it's drained in
    order across successive calls (so we can stub three sequential
    calls — totalSupply, decimals, balanceOf).

    Also supports non-eth_call methods (eth_blockNumber, eth_getLogs)
    via the optional ``method_responses`` map.
    """

    def __init__(
        self,
        responses: dict[str, str | list[str]] | None = None,
        *,
        method_responses: dict[str, Any] | None = None,
    ) -> None:
        self.responses: dict[str, list[str]] = {}
        for k, v in (responses or {}).items():
            self.responses[k.lower()] = list(v) if isinstance(v, list) else [v]
        self.method_responses: dict[str, Any] = dict(method_responses or {})
        self.calls: list[tuple[str, list[Any]]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        if method in self.method_responses:
            return self.method_responses[method]
        if method != "eth_call":
            raise RuntimeError(f"unexpected method: {method}")
        target = params[0]["to"].lower()
        if target not in self.responses or not self.responses[target]:
            raise RuntimeError(f"no stub for {target} (call #{len(self.calls)})")
        return self.responses[target].pop(0)


# ---------------------------------------------------------------------------
# Helpers — _scale_token, _topic_to_address, divergence_bps
# ---------------------------------------------------------------------------


def test_scale_token_18_decimals() -> None:
    assert _scale_token(10**18, 18) == Decimal(1)
    assert _scale_token(10**17, 18) == Decimal("0.1")
    assert _scale_token(360_753_853 * 10**18, 18) == Decimal(360_753_853)


def test_scale_token_6_decimals() -> None:
    assert _scale_token(1_000_000, 6) == Decimal(1)
    assert _scale_token(999_506, 6) == Decimal("0.999506")


def test_scale_token_zero_decimals() -> None:
    assert _scale_token(42, 0) == Decimal(42)


def test_scale_token_negative_decimals_raises() -> None:
    with pytest.raises(ValueError, match="decimals must be"):
        _scale_token(1, -1)


def test_topic_to_address_padded() -> None:
    pad = "0x" + "0" * 24 + "ab" * 20
    assert _topic_to_address(pad) == "0x" + "ab" * 20


def test_topic_to_address_invalid_length() -> None:
    with pytest.raises(ValueError, match="invalid 32-byte topic"):
        _topic_to_address("0xab")


def test_topic_to_address_missing_prefix() -> None:
    with pytest.raises(ValueError, match="invalid 32-byte topic"):
        _topic_to_address("ab" * 32)


def test_divergence_bps_no_inputs() -> None:
    assert divergence_bps([]) == Decimal(0)


def test_divergence_bps_single_input() -> None:
    assert divergence_bps([Decimal("1.0")]) == Decimal(0)


def test_divergence_bps_all_none() -> None:
    assert divergence_bps([None, None]) == Decimal(0)


def test_divergence_bps_at_peg_zero_spread() -> None:
    assert divergence_bps([Decimal(1), Decimal(1), Decimal(1)]) == Decimal(0)


def test_divergence_bps_50bp_spread() -> None:
    # $1.000 vs $0.995 → 50 bps spread off the LOW value.
    spread = divergence_bps([Decimal(1), Decimal("0.995")])
    assert Decimal("50") < spread < Decimal("50.5")


def test_divergence_bps_uses_low_as_denominator() -> None:
    # $1.10 vs $1.00 → 1000 bps using $1.00 as denom (conservative direction).
    spread = divergence_bps([Decimal("1.10"), Decimal("1.00")])
    assert spread == Decimal(1000)


def test_divergence_bps_zero_low_returns_zero() -> None:
    # If the lowest is zero, we'd divide by zero — we return 0 instead.
    assert divergence_bps([Decimal(0), Decimal(1)]) == Decimal(0)


def test_divergence_bps_skips_none_values() -> None:
    # Only the two non-None values should be considered.
    spread = divergence_bps([Decimal(1), None, Decimal("0.99"), None])
    assert Decimal("100") < spread < Decimal("101.5")


def test_divergence_bps_constant_validates() -> None:
    assert BPS_DENOMINATOR == 10_000
    assert AAVE_BASE_CURRENCY_UNIT == 10**8


# ---------------------------------------------------------------------------
# USDMAddresses
# ---------------------------------------------------------------------------


def test_addresses_from_registry_entry_full() -> None:
    reg = ProtocolRegistry.from_yaml()
    a = USDMAddresses.from_registry_entry(reg.get("usdm"))
    assert a.token == USDM_TOKEN
    assert a.twap60_oracle == USDM_TWAP60
    assert a.eth_oracle == USDM_ETH_ORACLE


def test_addresses_token_only() -> None:
    a = USDMAddresses(token=USDM_TOKEN)
    assert a.twap60_oracle is None
    assert a.eth_oracle is None


def test_burn_addresses_includes_dead_marker() -> None:
    assert "0x000000000000000000000000000000000000dEaD" in BURN_ADDRESSES


# ---------------------------------------------------------------------------
# USDM ERC20 reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_total_supply_decodes_to_decimal() -> None:
    # 360,753,853.148073 USDm at 18 decimals.
    raw_supply = 360_753_853_148_073_000_000_000_000
    enc_supply = "0x" + abi_encode(["uint256"], [raw_supply]).hex()
    enc_dec = "0x" + abi_encode(["uint8"], [18]).hex()
    client = StubClient({USDM_TOKEN: [enc_supply, enc_dec]})
    usdm = USDM(client, ADDRS)
    total = await usdm.total_supply()
    assert isinstance(total, Decimal)
    # ~360.75M
    assert Decimal("360_000_000") < total < Decimal("361_000_000")


@pytest.mark.asyncio
async def test_decimals_caches_after_first_read() -> None:
    enc_dec = "0x" + abi_encode(["uint8"], [18]).hex()
    client = StubClient({USDM_TOKEN: [enc_dec]})  # only ONE response
    usdm = USDM(client, ADDRS)
    d1 = await usdm.decimals()
    d2 = await usdm.decimals()  # should hit cache, no second eth_call
    assert d1 == d2 == 18


@pytest.mark.asyncio
async def test_symbol_returns_usdm_lowercase_m() -> None:
    enc = "0x" + abi_encode(["string"], ["USDm"]).hex()
    client = StubClient({USDM_TOKEN: enc})
    usdm = USDM(client, ADDRS)
    assert await usdm.symbol() == "USDm"


@pytest.mark.asyncio
async def test_name_string_passthrough() -> None:
    enc = "0x" + abi_encode(["string"], ["MegaUSD"]).hex()
    client = StubClient({USDM_TOKEN: enc})
    usdm = USDM(client, ADDRS)
    assert await usdm.name() == "MegaUSD"


@pytest.mark.asyncio
async def test_balance_of_decodes_and_scales() -> None:
    enc_bal = "0x" + abi_encode(["uint256"], [123 * 10**18]).hex()
    enc_dec = "0x" + abi_encode(["uint8"], [18]).hex()
    client = StubClient({USDM_TOKEN: [enc_bal, enc_dec]})
    usdm = USDM(client, ADDRS)
    bal = await usdm.balance_of("0x" + "ab" * 20)
    assert bal == Decimal(123)


@pytest.mark.asyncio
async def test_balance_of_validates_address() -> None:
    usdm = USDM(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid account"):
        await usdm.balance_of("0xBAD")


@pytest.mark.asyncio
async def test_circulating_supply_subtracts_burn_balances() -> None:
    """Total 1000 - burn(0xdead)=2 - burn(0x...01)=0 = 998.

    Decimals is cached after the first read inside ``total_supply``,
    so the stub queue is: totalSupply, decimals, balanceOf, balanceOf
    (4 responses — *not* 6, because cache spares the second decimals
    fetch on each balance_of).
    """
    enc_total = "0x" + abi_encode(["uint256"], [1000 * 10**18]).hex()
    enc_dec = "0x" + abi_encode(["uint8"], [18]).hex()
    enc_burn1 = "0x" + abi_encode(["uint256"], [2 * 10**18]).hex()
    enc_burn2 = "0x" + abi_encode(["uint256"], [0]).hex()
    client = StubClient({USDM_TOKEN: [enc_total, enc_dec, enc_burn1, enc_burn2]})
    usdm = USDM(client, ADDRS)
    circ = await usdm.circulating_supply()
    assert circ == Decimal(998)


@pytest.mark.asyncio
async def test_circulating_supply_swallows_balance_revert() -> None:
    """A burn-address read that errors is treated as 'unknown burn',
    not propagated. The most we lose is over-counting circulating by
    that burn-address balance — which is bounded by definition."""
    enc_total = "0x" + abi_encode(["uint256"], [1000 * 10**18]).hex()
    enc_dec = "0x" + abi_encode(["uint8"], [18]).hex()
    # Only one burn-address read responds; the other will RuntimeError
    # because the stub queue is exhausted. Same call sequence: totalSupply,
    # decimals, balanceOf (success), balanceOf (no stub → swallowed).
    enc_burn1 = "0x" + abi_encode(["uint256"], [3 * 10**18]).hex()
    client = StubClient({USDM_TOKEN: [enc_total, enc_dec, enc_burn1]})
    usdm = USDM(client, ADDRS)
    circ = await usdm.circulating_supply()
    # 1000 - 3 (the second burn-read errored, treated as 0).
    assert circ == Decimal(997)


@pytest.mark.asyncio
async def test_is_blacklisted_returns_bool() -> None:
    enc_t = "0x" + abi_encode(["bool"], [True]).hex()
    enc_f = "0x" + abi_encode(["bool"], [False]).hex()
    client = StubClient({USDM_TOKEN: [enc_t, enc_f]})
    usdm = USDM(client, ADDRS)
    assert await usdm.is_blacklisted("0x" + "11" * 20) is True
    assert await usdm.is_blacklisted("0x" + "22" * 20) is False


@pytest.mark.asyncio
async def test_is_blacklisted_validates_address() -> None:
    usdm = USDM(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid account"):
        await usdm.is_blacklisted("0xBAD")


@pytest.mark.asyncio
async def test_is_minter_returns_bool() -> None:
    enc = "0x" + abi_encode(["bool"], [True]).hex()
    client = StubClient({USDM_TOKEN: enc})
    usdm = USDM(client, ADDRS)
    assert await usdm.is_minter("0x" + "33" * 20) is True


@pytest.mark.asyncio
async def test_is_minter_validates_address() -> None:
    usdm = USDM(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid account"):
        await usdm.is_minter("not-an-address")


# ---------------------------------------------------------------------------
# OFF-CHAIN-managed reads return None (do NOT fake them)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collateral_ratio_returns_none_for_live_usdm() -> None:
    """Off-chain-managed; do not fake. See wrapper docstring."""
    usdm = USDM(StubClient({}), ADDRS)
    assert await usdm.collateral_ratio() is None


@pytest.mark.asyncio
async def test_mint_paused_returns_none_for_live_usdm() -> None:
    usdm = USDM(StubClient({}), ADDRS)
    assert await usdm.mint_paused() is None


@pytest.mark.asyncio
async def test_redeem_paused_returns_none_for_live_usdm() -> None:
    usdm = USDM(StubClient({}), ADDRS)
    assert await usdm.redeem_paused() is None


# ---------------------------------------------------------------------------
# peg_quote — composes the three sources, gracefully degrades on failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_peg_quote_empty_when_no_oracles_or_callables() -> None:
    """No oracles bound and no callables passed → all None, divergence 0."""
    addrs_no_oracle = USDMAddresses(token=USDM_TOKEN)  # no twap60, no eth_oracle
    usdm = USDM(StubClient({}), addrs_no_oracle)
    quote = await usdm.peg_quote()
    assert isinstance(quote, PegQuote)
    assert quote.kumbaya_usdt0 is None
    assert quote.aave_oracle_usd is None
    assert quote.twap60_usd is None
    assert quote.eth_oracle_usd is None
    assert quote.divergence_bps == Decimal(0)
    assert quote.sources_present == 0


@pytest.mark.asyncio
async def test_peg_quote_kumbaya_only() -> None:
    addrs_no_oracle = USDMAddresses(token=USDM_TOKEN)
    usdm = USDM(StubClient({}), addrs_no_oracle)

    async def kumbaya_quote() -> Decimal:
        return Decimal("0.999506")

    quote = await usdm.peg_quote(kumbaya_quote_fn=kumbaya_quote)
    assert quote.kumbaya_usdt0 == Decimal("0.999506")
    assert quote.sources_present == 1
    # Only one source → divergence 0 (no spread to compute)
    assert quote.divergence_bps == Decimal(0)


@pytest.mark.asyncio
async def test_peg_quote_kumbaya_error_returns_none_not_raise() -> None:
    addrs_no_oracle = USDMAddresses(token=USDM_TOKEN)
    usdm = USDM(StubClient({}), addrs_no_oracle)

    async def kumbaya_broken() -> Decimal:
        raise RuntimeError("simulated RPC failure")

    quote = await usdm.peg_quote(kumbaya_quote_fn=kumbaya_broken)
    assert quote.kumbaya_usdt0 is None
    assert quote.sources_present == 0
    assert "kumbaya_error" in quote.raw


@pytest.mark.asyncio
async def test_peg_quote_aave_oracle_only() -> None:
    addrs_no_oracle = USDMAddresses(token=USDM_TOKEN)
    usdm = USDM(StubClient({}), addrs_no_oracle)

    async def aave_call() -> Decimal:
        return Decimal("1.000000")

    quote = await usdm.peg_quote(aave_oracle_call_fn=aave_call)
    assert quote.aave_oracle_usd == Decimal("1.000000")
    assert quote.sources_present == 1


@pytest.mark.asyncio
async def test_peg_quote_twap60_decodes_round_data() -> None:
    """TWAP60 latestRoundData -> (uint80, int256, uint256, uint256, uint80) +
    decimals -> uint8."""
    answer = 99_926_428  # $0.99926428 at 8 decimals
    enc_round = (
        "0x"
        + abi_encode(
            ["uint80", "int256", "uint256", "uint256", "uint80"],
            [1, answer, 1_700_000_000, 1_700_000_060, 1],
        ).hex()
    )
    enc_dec = "0x" + abi_encode(["uint8"], [8]).hex()
    client = StubClient({USDM_TWAP60: [enc_round, enc_dec]})
    usdm = USDM(client, ADDRS)
    quote = await usdm.peg_quote()
    assert quote.twap60_usd is not None
    assert Decimal("0.999") < quote.twap60_usd < Decimal("1.000")
    assert quote.sources_present == 1


@pytest.mark.asyncio
async def test_peg_quote_twap60_skips_zero_or_negative_answer() -> None:
    """A zero/negative answer is treated as 'oracle stale/uninitialized'."""
    enc_round = (
        "0x"
        + abi_encode(
            ["uint80", "int256", "uint256", "uint256", "uint80"],
            [1, 0, 0, 0, 0],
        ).hex()
    )
    enc_dec = "0x" + abi_encode(["uint8"], [8]).hex()
    client = StubClient({USDM_TWAP60: [enc_round, enc_dec]})
    usdm = USDM(client, ADDRS)
    quote = await usdm.peg_quote()
    assert quote.twap60_usd is None


@pytest.mark.asyncio
async def test_peg_quote_eth_oracle_decodes_4tuple() -> None:
    """USDM_ETH oracle latestAnswer returns (eth_low, eth_high, usd_low, usd_high)."""
    eth_low = 440_643_773_379_170
    eth_high = 440_643_773_379_170
    usd_low = 1_000_000_000_000_000_000  # $1.0 at 1e18
    usd_high = 1_000_000_092_991_322_366  # ~$1.0000000930
    enc = (
        "0x"
        + abi_encode(
            ["uint256", "uint256", "uint256", "uint256"],
            [eth_low, eth_high, usd_low, usd_high],
        ).hex()
    )
    client = StubClient({USDM_ETH_ORACLE: enc})
    usdm = USDM(client, ADDRS)
    quote = await usdm.peg_quote()
    assert quote.eth_oracle_usd is not None
    assert Decimal("0.999") < quote.eth_oracle_usd < Decimal("1.001")


@pytest.mark.asyncio
async def test_peg_quote_eth_oracle_zero_band_returns_none() -> None:
    """If the oracle returns a zero band, surface as None not 0.0."""
    enc = "0x" + abi_encode(["uint256", "uint256", "uint256", "uint256"], [0, 0, 0, 0]).hex()
    client = StubClient({USDM_ETH_ORACLE: enc})
    usdm = USDM(client, ADDRS)
    quote = await usdm.peg_quote()
    assert quote.eth_oracle_usd is None


@pytest.mark.asyncio
async def test_peg_quote_three_sources_compute_divergence() -> None:
    """All three on-chain oracle sources + Kumbaya callable wired."""
    answer = 99_926_428
    enc_round = (
        "0x"
        + abi_encode(
            ["uint80", "int256", "uint256", "uint256", "uint80"],
            [1, answer, 1_700_000_000, 1_700_000_060, 1],
        ).hex()
    )
    enc_dec = "0x" + abi_encode(["uint8"], [8]).hex()
    enc_eth = (
        "0x"
        + abi_encode(
            ["uint256", "uint256", "uint256", "uint256"],
            [
                440_643_773_379_170,
                440_643_773_379_170,
                10**18,  # $1.000000
                10**18,
            ],
        ).hex()
    )
    client = StubClient(
        {
            USDM_TWAP60: [enc_round, enc_dec],
            USDM_ETH_ORACLE: enc_eth,
        }
    )
    usdm = USDM(client, ADDRS)

    async def kumbaya_quote() -> Decimal:
        return Decimal("0.999506")

    async def aave_call() -> Decimal:
        return Decimal("1.000000")

    quote = await usdm.peg_quote(kumbaya_quote_fn=kumbaya_quote, aave_oracle_call_fn=aave_call)
    assert quote.sources_present == 4
    # Spread: 1.000000 vs 0.999264 → ~7.4 bps. Comfortably HEALTHY.
    assert Decimal("5") < quote.divergence_bps < Decimal("12")


@pytest.mark.asyncio
async def test_peg_quote_aave_callable_error_swallowed() -> None:
    addrs_no_oracle = USDMAddresses(token=USDM_TOKEN)
    usdm = USDM(StubClient({}), addrs_no_oracle)

    async def kumbaya_quote() -> Decimal:
        return Decimal("1.0")

    async def aave_broken() -> Decimal:
        raise ConnectionError("simulated network error")

    quote = await usdm.peg_quote(kumbaya_quote_fn=kumbaya_quote, aave_oracle_call_fn=aave_broken)
    assert quote.kumbaya_usdt0 == Decimal("1.0")
    assert quote.aave_oracle_usd is None
    assert "aave_oracle_error" in quote.raw


# ---------------------------------------------------------------------------
# Event scans — recent_mints / recent_redeems
# ---------------------------------------------------------------------------


def _mk_log(
    topic0: str,
    block: int,
    log_idx: int,
    indexed_a: str,
    indexed_b: str,
    amount: int,
) -> dict[str, Any]:
    """Build an eth_getLogs-shaped log dict."""
    pad_a = "0x" + "0" * 24 + indexed_a[2:].lower()
    pad_b = "0x" + "0" * 24 + indexed_b[2:].lower()
    return {
        "address": USDM_TOKEN,
        "topics": [topic0, pad_a, pad_b],
        "data": "0x" + amount.to_bytes(32, "big").hex(),
        "blockNumber": hex(block),
        "transactionHash": "0x" + ("ab" * 32),
        "logIndex": hex(log_idx),
    }


@pytest.mark.asyncio
async def test_recent_mints_decodes_logs() -> None:
    topic = "0x" + keccak(text="Minted(address,uint256,address)").hex()
    logs = [
        _mk_log(
            topic,
            block=100,
            log_idx=0,
            indexed_a="0x" + "11" * 20,
            indexed_b="0x" + "22" * 20,
            amount=1000 * 10**18,
        ),
        _mk_log(
            topic,
            block=101,
            log_idx=2,
            indexed_a="0x" + "33" * 20,
            indexed_b="0x" + "44" * 20,
            amount=500 * 10**18,
        ),
    ]
    client = StubClient(
        method_responses={
            "eth_blockNumber": "0x96",  # 150
            "eth_getLogs": logs,
        }
    )
    usdm = USDM(client, ADDRS)
    out = await usdm.recent_mints(blocks=100)
    assert len(out) == 2
    assert all(isinstance(e, MintEvent) for e in out)
    # Ordered oldest-first.
    assert out[0].block_number == 100
    assert out[1].block_number == 101
    assert out[0].amount == 1000 * 10**18
    assert out[0].to == "0x" + "11" * 20
    assert out[0].minter == "0x" + "22" * 20


@pytest.mark.asyncio
async def test_recent_mints_uses_explicit_latest_block() -> None:
    """Passing latest_block skips the eth_blockNumber RPC."""
    topic = "0x" + keccak(text="Minted(address,uint256,address)").hex()
    logs = [_mk_log(topic, 50, 0, "0x" + "aa" * 20, "0x" + "bb" * 20, 10**18)]
    client = StubClient(method_responses={"eth_getLogs": logs})
    usdm = USDM(client, ADDRS)
    out = await usdm.recent_mints(blocks=10, latest_block=60)
    assert len(out) == 1
    # No eth_blockNumber call made.
    methods_called = [c[0] for c in client.calls]
    assert "eth_blockNumber" not in methods_called
    assert "eth_getLogs" in methods_called


@pytest.mark.asyncio
async def test_recent_mints_negative_blocks_raises() -> None:
    usdm = USDM(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="blocks must be positive"):
        await usdm.recent_mints(blocks=0)


@pytest.mark.asyncio
async def test_recent_mints_clamps_from_block_to_zero() -> None:
    """Don't query negative blocks; clamp to 0 if blocks > latest_block."""
    topic = "0x" + keccak(text="Minted(address,uint256,address)").hex()
    captured_params: list[Any] = []

    class CaptureClient:
        async def _call(self, method: str, params: list[Any] | None = None) -> Any:
            captured_params.append((method, params))
            if method == "eth_getLogs":
                return []
            raise RuntimeError(method)

    usdm = USDM(CaptureClient(), ADDRS)
    await usdm.recent_mints(blocks=1_000_000, latest_block=10)
    log_call = next(p for m, p in captured_params if m == "eth_getLogs")
    assert log_call[0]["fromBlock"] == "0x0"
    assert log_call[0]["toBlock"] == "0xa"
    assert log_call[0]["topics"] == [topic]


@pytest.mark.asyncio
async def test_recent_redeems_decodes_burn_logs() -> None:
    topic = "0x" + keccak(text="Burned(address,uint256,address)").hex()
    logs = [
        _mk_log(topic, 200, 0, "0x" + "55" * 20, "0x" + "66" * 20, 999 * 10**18),
    ]
    client = StubClient(method_responses={"eth_blockNumber": "0xc8", "eth_getLogs": logs})
    usdm = USDM(client, ADDRS)
    out = await usdm.recent_redeems(blocks=50)
    assert len(out) == 1
    assert isinstance(out[0], RedeemEvent)
    assert out[0].from_ == "0x" + "55" * 20
    assert out[0].burner == "0x" + "66" * 20


@pytest.mark.asyncio
async def test_recent_mints_skips_malformed_log() -> None:
    topic = "0x" + keccak(text="Minted(address,uint256,address)").hex()
    bad_log = {
        "topics": [topic],  # missing the two indexed addresses
        "data": "0x",
        "blockNumber": "0x0",
        "transactionHash": "0x",
        "logIndex": "0x0",
    }
    good_log = _mk_log(topic, 5, 0, "0x" + "77" * 20, "0x" + "88" * 20, 10**18)
    client = StubClient(
        method_responses={"eth_blockNumber": "0xa", "eth_getLogs": [bad_log, good_log]}
    )
    usdm = USDM(client, ADDRS)
    out = await usdm.recent_mints(blocks=10)
    # Bad log skipped, good log surfaced.
    assert len(out) == 1
    assert out[0].block_number == 5


@pytest.mark.asyncio
async def test_recent_mints_empty_logs_returns_empty() -> None:
    client = StubClient(method_responses={"eth_blockNumber": "0xa", "eth_getLogs": []})
    usdm = USDM(client, ADDRS)
    assert await usdm.recent_mints(blocks=10) == []


# ---------------------------------------------------------------------------
# _decode_mint / _decode_burn — direct decoder unit tests
# ---------------------------------------------------------------------------


def test_decode_mint_handles_empty_data() -> None:
    """An OFT log with no amount data should decode amount=0, not error."""
    log = {
        "topics": [
            "0x" + "ee" * 32,
            "0x" + "0" * 24 + "11" * 20,
            "0x" + "0" * 24 + "22" * 20,
        ],
        "data": "0x",
        "blockNumber": "0xa",
        "transactionHash": "0xff",
        "logIndex": "0x0",
    }
    e = _decode_mint(log)
    assert e.amount == 0
    assert e.to == "0x" + "11" * 20


def test_decode_mint_missing_topics_raises() -> None:
    log = {
        "topics": ["0x" + "ee" * 32],
        "data": "0x",
        "blockNumber": "0x1",
        "transactionHash": "0x",
        "logIndex": "0x0",
    }
    with pytest.raises(ValueError, match="missing indexed topics"):
        _decode_mint(log)


def test_decode_burn_missing_topics_raises() -> None:
    log = {
        "topics": ["0x" + "dd" * 32, "0x" + "0" * 64],
        "data": "0x",
        "blockNumber": "0x1",
        "transactionHash": "0x",
        "logIndex": "0x0",
    }
    with pytest.raises(ValueError, match="missing indexed topics"):
        _decode_burn(log)


# ---------------------------------------------------------------------------
# PegQuote dataclass
# ---------------------------------------------------------------------------


def test_peg_quote_sources_present_counts_only_non_none() -> None:
    q = PegQuote(
        kumbaya_usdt0=Decimal(1),
        aave_oracle_usd=None,
        twap60_usd=Decimal("0.999"),
        eth_oracle_usd=None,
        divergence_bps=Decimal(10),
    )
    assert q.sources_present == 2


def test_peg_quote_sources_present_zero_when_all_none() -> None:
    q = PegQuote(
        kumbaya_usdt0=None,
        aave_oracle_usd=None,
        twap60_usd=None,
        eth_oracle_usd=None,
        divergence_bps=Decimal(0),
    )
    assert q.sources_present == 0


def test_peg_quote_sources_present_all_four() -> None:
    q = PegQuote(
        kumbaya_usdt0=Decimal(1),
        aave_oracle_usd=Decimal(1),
        twap60_usd=Decimal(1),
        eth_oracle_usd=Decimal(1),
        divergence_bps=Decimal(0),
    )
    assert q.sources_present == 4


def test_mint_event_dataclass_shape() -> None:
    e = MintEvent(
        block_number=100,
        tx_hash="0xab",
        log_index=0,
        to="0x" + "11" * 20,
        amount=10**18,
        minter="0x" + "22" * 20,
    )
    assert e.amount == 10**18
    assert e.minter == "0x" + "22" * 20


def test_redeem_event_dataclass_shape() -> None:
    e = RedeemEvent(
        block_number=200,
        tx_hash="0xcd",
        log_index=1,
        from_="0x" + "33" * 20,
        amount=10**17,
        burner="0x" + "44" * 20,
    )
    assert e.from_ == "0x" + "33" * 20
    assert e.amount == 10**17
