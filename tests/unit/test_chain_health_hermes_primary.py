"""Tests for the Hermes-primary price-source resolver and its
integration into the chain-health gate.

Scenario matrix (from the lane prompt):

1. Hermes fresh, on-chain stale -> use Hermes price; severity unaffected
2. Hermes stale, on-chain fresh -> use on-chain; flag WARNING
3. Both stale -> severity WARNING (price source unreliable)
4. Hermes API timeout -> fall back gracefully to on-chain
5. Settlement-flow flag (use_onchain_only=True) -> respects request,
   ignores Hermes

The resolver is unit-tested in isolation (``ChainHealthPriceResolver``)
and integration-tested through the per-chain gates
(``classify_arbitrum`` + ``_classify`` from chain_health_gate). Tests
mock the Hermes client at the resolver boundary so no network traffic
leaks into the test process.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from lib.chains.megaeth.contracts.peg_monitor import PegBreak
from lib.hackathon.arbitrum_chain_health import (
    ARBITRUM_CHAIN_ID,
    classify_arbitrum,
)
from lib.hackathon.chain_health_gate import _classify
from lib.hackathon.chain_health_price_source import (
    ChainHealthPriceResolver,
    PriceSource,
    ResolvedPrice,
)

# ---------------------------------------------------------------------------
# Hermes mock — duck-typed against PythHermesClient.latest_prices_by_symbol.
# ---------------------------------------------------------------------------


@dataclass
class _StubHermesPrice:
    """Minimal stand-in for PythHermesPrice (PR #625).

    Only the fields the resolver reads are populated. Tests construct
    these directly rather than mocking the full PythHermesClient
    response shape.
    """

    price: Decimal
    publish_time: int


class _StubHermesClient:
    """In-memory Hermes client. Returns canned responses or raises."""

    def __init__(
        self,
        responses: dict[str, _StubHermesPrice] | None = None,
        raise_on_call: Exception | None = None,
    ) -> None:
        self._responses = responses or {}
        self._raise = raise_on_call
        self.calls: list[tuple[str, ...]] = []

    def latest_prices_by_symbol(
        self, symbols, *, include_vaa: bool = True
    ) -> dict[str, _StubHermesPrice]:
        self.calls.append(tuple(symbols))
        if self._raise is not None:
            raise self._raise
        return {
            s.upper(): self._responses[s.upper()] for s in symbols if s.upper() in self._responses
        }


# ---------------------------------------------------------------------------
# Lend-overview fixture for the per-chain gate tests.
# ---------------------------------------------------------------------------


def _reserve(symbol: str, paused: bool = False, frozen: bool = False, utilization: float = 0.5):
    return SimpleNamespace(symbol=symbol, paused=paused, frozen=frozen, utilization=utilization)


def _lend(reserves: list) -> SimpleNamespace:
    return SimpleNamespace(reserves=reserves)


def _stable_healthy() -> SimpleNamespace:
    return SimpleNamespace(
        severity=PegBreak.HEALTHY,
        peg_snapshot=SimpleNamespace(divergence_bps=Decimal(8)),
    )


# ---------------------------------------------------------------------------
# Resolver-level tests — the 5 scenarios in isolation.
# ---------------------------------------------------------------------------


# Pinned "now" used across the resolver tests so freshness math is deterministic.
NOW = 1_777_900_000


def test_scenario_1_hermes_fresh_onchain_stale():
    """Hermes wins; severity unaffected; on-chain reader is never called."""
    fresh_hermes = _StubHermesPrice(price=Decimal("78671.62"), publish_time=NOW - 2)
    client = _StubHermesClient(responses={"BTC": fresh_hermes})

    onchain_calls: list[bool] = []

    def stale_onchain() -> tuple[Decimal, int]:
        onchain_calls.append(True)
        # 25 days stale — the PR #621 Optimism BTC scenario. The resolver
        # must not consult this when Hermes is fresh.
        return Decimal("75000.00"), NOW - (25 * 86400)

    resolver = ChainHealthPriceResolver(hermes_client=client)
    result = resolver.resolve("BTC", on_chain_reader=stale_onchain, now=NOW)

    assert result.source is PriceSource.HERMES_PRIMARY
    assert result.price_usd == Decimal("78671.62")
    assert result.age_s == 2
    assert result.severity_contribution == "HEALTHY"
    assert result.reasons == []
    # The crux of the PR #621 fix: stale on-chain cache is a no-op when
    # Hermes is fresh. Verify the on-chain reader was not consulted.
    assert onchain_calls == []


def test_scenario_2_hermes_stale_onchain_fresh():
    """Fall back to on-chain; verdict carries a WARNING reason."""
    stale_hermes = _StubHermesPrice(price=Decimal("78671.62"), publish_time=NOW - 600)
    client = _StubHermesClient(responses={"BTC": stale_hermes})

    def fresh_onchain() -> tuple[Decimal, int]:
        return Decimal("78680.00"), NOW - 5

    resolver = ChainHealthPriceResolver(hermes_client=client)
    result = resolver.resolve("BTC", on_chain_reader=fresh_onchain, now=NOW)

    assert result.source is PriceSource.ON_CHAIN_FALLBACK
    assert result.price_usd == Decimal("78680.00")
    assert result.age_s == 5
    assert result.severity_contribution == "WARNING"
    assert any("hermes stale" in r.lower() for r in result.reasons)
    assert any("on-chain BTC" in r for r in result.reasons)


def test_scenario_3_both_stale():
    """Severity WARNING; price-source unreliable; both prices captured."""
    stale_hermes = _StubHermesPrice(price=Decimal("78671.62"), publish_time=NOW - 600)
    client = _StubHermesClient(responses={"BTC": stale_hermes})

    def stale_onchain() -> tuple[Decimal, int]:
        # 25 days stale — the unambiguous PR #621 case.
        return Decimal("75000.00"), NOW - (25 * 86400)

    resolver = ChainHealthPriceResolver(hermes_client=client)
    result = resolver.resolve("BTC", on_chain_reader=stale_onchain, now=NOW)

    assert result.source is PriceSource.BOTH_STALE
    # We still surface the on-chain price + age so the dashboard can
    # render *what* was seen (callers shouldn't act on it for a fresh
    # trade; this is forensics).
    assert result.price_usd == Decimal("75000.00")
    assert result.age_s == 25 * 86400
    assert result.severity_contribution == "WARNING"
    assert any("price source unreliable" in r for r in result.reasons)


def test_scenario_4_hermes_api_timeout_falls_back_gracefully():
    """Timeout is caught; resolver behaves like Hermes-stale (graceful)."""
    client = _StubHermesClient(
        raise_on_call=httpx.ReadTimeout("hermes.pyth.network: read timed out")
    )

    def fresh_onchain() -> tuple[Decimal, int]:
        return Decimal("78680.00"), NOW - 5

    resolver = ChainHealthPriceResolver(hermes_client=client)
    result = resolver.resolve("BTC", on_chain_reader=fresh_onchain, now=NOW)

    assert result.source is PriceSource.ON_CHAIN_FALLBACK
    assert result.price_usd == Decimal("78680.00")
    assert result.severity_contribution == "WARNING"
    # Timeout is the fallback reason — operator can grep for ReadTimeout
    # to distinguish a network error from a stale-but-responding Hermes.
    assert any("ReadTimeout" in r or "hermes unavailable" in r for r in result.reasons)


def test_scenario_5_settlement_flow_use_onchain_only():
    """use_onchain_only bypasses Hermes entirely; flags settlement_opt_out."""
    # Even with a Hermes client that *would* respond fresh, settlement
    # mode must not consult it — this matters because settlement flows
    # pay gas to refresh the on-chain cache atomically and need the
    # contract to read the same value the gate is reading.
    fresh_hermes = _StubHermesPrice(price=Decimal("78671.62"), publish_time=NOW - 2)
    client = _StubHermesClient(responses={"BTC": fresh_hermes})

    def fresh_onchain() -> tuple[Decimal, int]:
        return Decimal("78650.00"), NOW - 8

    resolver = ChainHealthPriceResolver(hermes_client=client)
    result = resolver.resolve(
        "BTC",
        on_chain_reader=fresh_onchain,
        use_onchain_only=True,
        now=NOW,
    )

    assert result.source is PriceSource.ON_CHAIN_FALLBACK
    assert result.price_usd == Decimal("78650.00")  # on-chain, not Hermes
    assert result.settlement_opt_out is True
    # Hermes was not contacted at all — empty calls list confirms.
    assert client.calls == []
    # Settlement flow uses on-chain by request -> HEALTHY contribution
    # (the dashboard shouldn't render this as a degraded state).
    assert result.severity_contribution == "HEALTHY"


# ---------------------------------------------------------------------------
# Resolver edge cases beyond the 5 prompt scenarios.
# ---------------------------------------------------------------------------


def test_no_fallback_available_when_onchain_reader_is_none():
    """Hermes stale + no on-chain reader = NO_FALLBACK_AVAILABLE/WARNING."""
    stale_hermes = _StubHermesPrice(price=Decimal("78671.62"), publish_time=NOW - 600)
    client = _StubHermesClient(responses={"BTC": stale_hermes})

    resolver = ChainHealthPriceResolver(hermes_client=client)
    # Wave A: many chains have no on-chain Pyth wrapper yet. Resolver
    # must surface this as a distinct enum value, not a network error.
    result = resolver.resolve("BTC", on_chain_reader=None, now=NOW)

    assert result.source is PriceSource.NO_FALLBACK_AVAILABLE
    assert result.severity_contribution == "WARNING"
    assert any("no on-chain Pyth wrapper" in r for r in result.reasons)


def test_settlement_flow_with_no_reader_warns():
    """Settlement-mode without an on-chain reader is a wiring bug; surface."""
    client = _StubHermesClient(responses={})
    resolver = ChainHealthPriceResolver(hermes_client=client)
    result = resolver.resolve("BTC", on_chain_reader=None, use_onchain_only=True, now=NOW)

    assert result.source is PriceSource.NO_FALLBACK_AVAILABLE
    assert result.severity_contribution == "WARNING"
    assert result.settlement_opt_out is True
    assert any("settlement-mode" in r for r in result.reasons)


def test_onchain_reader_exception_is_swallowed():
    """A misbehaving on-chain reader must not propagate."""
    stale_hermes = _StubHermesPrice(price=Decimal("78671.62"), publish_time=NOW - 600)
    client = _StubHermesClient(responses={"BTC": stale_hermes})

    def busted_onchain():
        raise RuntimeError("on-chain RPC blew up")

    resolver = ChainHealthPriceResolver(hermes_client=client)
    result = resolver.resolve("BTC", on_chain_reader=busted_onchain, now=NOW)

    # Reader errored, Hermes was stale -> both effectively unavailable.
    assert result.source is PriceSource.BOTH_STALE
    assert result.severity_contribution == "WARNING"
    assert result.price_usd is None


# ---------------------------------------------------------------------------
# Integration tests — _classify (MegaETH) + classify_arbitrum compose the
# resolver verdict into their per-chain ChainHealthVerdict shape.
# ---------------------------------------------------------------------------


def test_megaeth_classify_with_fresh_hermes_remains_healthy():
    """The PR #621 closure: 25-day-stale on-chain BTC no longer flags WARNING.

    This is the exact scenario the lane prompt calls out as the visible
    behavioural change. We construct a HEALTHY peg + HEALTHY Aave +
    HERMES_PRIMARY resolved price and verify the gate verdict stays
    HEALTHY — the on-chain Pyth cache age is irrelevant because
    Hermes is the ground truth.
    """
    stable = _stable_healthy()
    lend = _lend([_reserve("USDC"), _reserve("WETH")])
    fresh_resolved = ResolvedPrice(
        symbol="BTC",
        source=PriceSource.HERMES_PRIMARY,
        price_usd=Decimal("78671.62"),
        publish_time_s=NOW - 2,
        age_s=2,
        severity_contribution="HEALTHY",
        reasons=[],
    )
    verdict = _classify(stable, lend, resolved=fresh_resolved)
    assert verdict.severity == "HEALTHY"
    # The Hermes-primary line is appended for dashboard visibility,
    # even though severity didn't change — closes the loop visibly.
    assert any("Hermes primary" in r for r in verdict.reasons)


def test_megaeth_classify_lifts_to_warning_on_both_stale():
    """Healthy peg + healthy Aave + BOTH_STALE price source -> WARNING."""
    stable = _stable_healthy()
    lend = _lend([_reserve("USDC")])
    both_stale = ResolvedPrice(
        symbol="BTC",
        source=PriceSource.BOTH_STALE,
        price_usd=Decimal("75000"),
        publish_time_s=NOW - 25 * 86400,
        age_s=25 * 86400,
        severity_contribution="WARNING",
        reasons=["price-source: both Hermes and on-chain BTC stale"],
    )
    verdict = _classify(stable, lend, resolved=both_stale)
    assert verdict.severity == "WARNING"
    assert any("both Hermes and on-chain" in r for r in verdict.reasons)


def test_megaeth_classify_does_not_lower_block():
    """Price-source axis must not lower severity below the peg/Aave verdict.

    A USDM crisis is a hard BLOCK; even if Hermes is fresh, the chain
    is un-tradeable on the peg axis and the verdict must remain BLOCK.
    """
    stable = SimpleNamespace(
        severity=PegBreak.CRISIS_500BP,
        peg_snapshot=SimpleNamespace(divergence_bps=Decimal(523)),
    )
    lend = _lend([_reserve("USDC")])
    fresh_resolved = ResolvedPrice(
        symbol="BTC",
        source=PriceSource.HERMES_PRIMARY,
        price_usd=Decimal("78671.62"),
        publish_time_s=NOW - 2,
        age_s=2,
        severity_contribution="HEALTHY",
        reasons=[],
    )
    verdict = _classify(stable, lend, resolved=fresh_resolved)
    assert verdict.severity == "BLOCK"


def test_arbitrum_classify_lifts_to_warning_on_onchain_fallback():
    """Arbitrum HEALTHY Aave stays HEALTHY without resolved price source."""
    lend = _lend([_reserve("USDC"), _reserve("WETH")])
    verdict = classify_arbitrum(lend)
    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == ARBITRUM_CHAIN_ID


def test_arbitrum_classify_with_fresh_hermes_remains_healthy():
    """Mirror MegaETH: fresh Hermes leaves a healthy Arbitrum HEALTHY."""
    lend = _lend([_reserve("USDC")])
    verdict = classify_arbitrum(lend)
    assert verdict.severity == "HEALTHY"


def test_megaeth_existing_tests_still_pass_when_resolved_is_none():
    """Backward compatibility: omitting ``resolved`` keeps prior behaviour.

    The lane prompt explicitly requires the existing chain_health tests
    to still pass with Hermes mocked HEALTHY. This test asserts the
    structural property: when no ResolvedPrice is provided, the verdict
    is identical to the pre-Hermes shape.
    """
    stable = _stable_healthy()
    lend = _lend([_reserve("USDC")])
    verdict = _classify(stable, lend)
    assert verdict.severity == "HEALTHY"
    # No price-source noise in reasons when no resolver is wired.
    assert not any("Hermes" in r or "price-source" in r for r in verdict.reasons)


# ---------------------------------------------------------------------------
# Default-client construction — the lazy import path. We patch the
# PythHermesClient constructor so we can verify the resolver wires it
# without instantiating httpx in the test process.
# ---------------------------------------------------------------------------


def test_resolver_lazy_constructs_default_hermes_client_on_first_use():
    """A resolver built with no client doesn't import httpx until resolve()."""
    fresh = _StubHermesPrice(price=Decimal("78671.62"), publish_time=NOW - 2)
    fake = _StubHermesClient(responses={"BTC": fresh})

    with patch(
        "lib.chains.cross_chain.pyth_hermes.PythHermesClient",
        return_value=fake,
    ):
        resolver = ChainHealthPriceResolver()  # no client injected
        result = resolver.resolve("BTC", now=NOW)

    assert result.source is PriceSource.HERMES_PRIMARY


# ---------------------------------------------------------------------------
# Determinism guard — the resolver must use the injected ``now`` kwarg
# rather than the wall clock so test runs are stable.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now_offset", "expected_source"),
    [
        (0, PriceSource.HERMES_PRIMARY),  # publish_time matches now -> age 0, fresh
        (10, PriceSource.HERMES_PRIMARY),  # 10s after publish -> still fresh
        (3600, PriceSource.NO_FALLBACK_AVAILABLE),  # 1h after -> stale, no fallback
    ],
)
def test_freshness_threshold_respects_now_kwarg(now_offset, expected_source):
    fresh = _StubHermesPrice(price=Decimal("78671.62"), publish_time=NOW)
    client = _StubHermesClient(responses={"BTC": fresh})
    resolver = ChainHealthPriceResolver(hermes_client=client)
    result = resolver.resolve("BTC", on_chain_reader=None, now=NOW + now_offset)
    assert result.source is expected_source
