"""Fail-closed tests for the Sentinel chain-health gate factory wrapper.

Backports PR #617's discipline to the canonical
``lib/hackathon/chain_health_gate.py``: when a per-chain factory raises
during construction (e.g. RPC URL unreachable, missing dependency,
config error), the gate must NEVER silently fail-open. It must:

1. Wrap the construction exception (don't re-raise raw),
2. Record the chain as ``unavailable`` with the original error message,
3. Return ``ChainHealthVerdict(severity="BLOCK", ...)`` from
   ``evaluate_chain(chain_id)`` — fail-CLOSED.

Property under test: a payment against a chain whose gate cannot be
constructed is REFUSED, not silently approved. This is the
safety-critical invariant for autonomous trading.
"""

from __future__ import annotations

from lib.hackathon.chain_health_gate import (
    MEGAETH_CHAIN_ID,
    ChainHealthGate,
    ChainHealthVerdict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raising_factory(message: str = "RPC URL unreachable"):
    """Build a client_factory callable that always raises on invocation."""

    def _factory():
        raise RuntimeError(message)

    return _factory


# ---------------------------------------------------------------------------
# Test 1 — factory raises → evaluate_chain returns BLOCK with original error
# ---------------------------------------------------------------------------


def test_factory_init_failure_yields_block_with_original_error():
    """A factory that raises must surface as BLOCK, not raw raise.

    The recorded reason must mention the original error so the
    operator can debug why the gate declined to evaluate.
    """
    gate = ChainHealthGate(client_factory=_raising_factory("megaeth RPC down"))

    verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert isinstance(verdict, ChainHealthVerdict)
    assert verdict.severity == "BLOCK", (
        f"Construction failure must fail CLOSED, not fail OPEN — got severity={verdict.severity!r}"
    )
    assert verdict.chain_id == MEGAETH_CHAIN_ID
    # Reason must mention 'gate unavailable' and preserve the original error.
    joined = " | ".join(verdict.reasons)
    assert "gate unavailable" in joined, joined
    assert "megaeth RPC down" in joined, (
        "Original error message must be preserved in verdict reasons; "
        f"got reasons={verdict.reasons!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — factory raises only for the gated chain; other chain ids
# (which fall through to "chain not gated") still classify HEALTHY.
# Mirrors the multi-chain spirit: one chain's failure must not poison the
# others. Here the canonical only knows MegaETH, so non-MegaETH chains
# follow the legacy "chain not gated" path; the broken-MegaETH branch
# stays BLOCK.
# ---------------------------------------------------------------------------


def test_factory_failure_isolated_to_gated_chain():
    """An un-gated chain must NOT inherit the BLOCK from the gated chain.

    The gate dispatches per chain_id; a failure on one must not
    cross-contaminate another's verdict.
    """
    gate = ChainHealthGate(client_factory=_raising_factory("init exploded"))

    # MegaETH (the gated chain) — factory will raise → BLOCK.
    megaeth_verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)
    assert megaeth_verdict.severity == "BLOCK"

    # An arbitrary other chain id falls through to the "chain not gated"
    # short-circuit BEFORE the factory is invoked, so no BLOCK leak.
    arbitrum_verdict = gate.evaluate_chain(42161)
    assert arbitrum_verdict.severity == "HEALTHY"
    assert "chain not gated" in " | ".join(arbitrum_verdict.reasons)


# ---------------------------------------------------------------------------
# Test 3 — once a factory failure is observed, subsequent
# evaluate_chain calls for that chain stay BLOCK without retrying
# (sticky fail-closed). Mirrors "all factories throw → all chain_ids
# return BLOCK" for the canonical's single-gated-chain shape.
# ---------------------------------------------------------------------------


def test_factory_failure_is_sticky_block_on_repeated_calls():
    """Once unavailable, a chain stays unavailable — no silent recovery.

    Trading critical-path code may repeatedly call ``evaluate_chain``
    while a payment evaluation loops; we must NEVER flip back to
    fail-open mid-session because the factory transiently succeeded
    (or worse, was never re-attempted).
    """
    call_count = {"n": 0}

    def _flaky_then_works():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ConnectionError("first attempt: RPC unreachable")
        # If the gate were to retry, this would return a healthy mock
        # client. We assert it does NOT retry.
        from types import SimpleNamespace

        return SimpleNamespace()

    gate = ChainHealthGate(client_factory=_flaky_then_works)

    first = gate.evaluate_chain(MEGAETH_CHAIN_ID)
    second = gate.evaluate_chain(MEGAETH_CHAIN_ID)
    third = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert first.severity == "BLOCK"
    assert second.severity == "BLOCK"
    assert third.severity == "BLOCK"
    # Factory must be invoked exactly ONCE — sticky cache short-circuits
    # subsequent calls before re-invoking.
    assert call_count["n"] == 1, (
        f"Sticky fail-closed must not re-invoke factory; got {call_count['n']} invocations"
    )


# ---------------------------------------------------------------------------
# Test 4 — construction exception is wrapped, not raw raised. Caller
# never sees a bare ``RuntimeError`` / ``ConnectionError`` propagating
# out of ``evaluate_chain`` — it always returns a verdict object. This
# is the discipline that lets Sentinel's ``evaluate_attempt`` rely on
# the gate's contract instead of wrapping every call site in try/except.
# ---------------------------------------------------------------------------


def test_construction_exception_is_wrapped_not_raised():
    """``evaluate_chain`` must always return a verdict, never raise.

    The original error message survives inside ``verdict.reasons`` so
    operator dashboards can show the cause.
    """
    sentinel_message = "factory: missing MEGAETH_RPC_URL env var"
    gate = ChainHealthGate(client_factory=_raising_factory(sentinel_message))

    # Must not raise — the whole point of fail-closed-by-verdict is
    # callers rely on a returned ChainHealthVerdict.
    try:
        verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)
    except Exception as exc:  # noqa: BLE001 — test asserts no raw raise
        raise AssertionError(
            f"evaluate_chain raised {type(exc).__name__}; "
            "construction exceptions must be wrapped into a BLOCK verdict"
        ) from exc

    assert isinstance(verdict, ChainHealthVerdict)
    assert verdict.severity == "BLOCK"
    # Original error preserved (not stripped, not replaced with a
    # generic 'gate failed').
    assert sentinel_message in " | ".join(verdict.reasons)


# ---------------------------------------------------------------------------
# Test 5 (bonus) — factory raising ImportError (a real-world scenario:
# httpx not installed) is also wrapped. Ensures the except-clause is
# broad-enough that a missing-dep doesn't reach the Sentinel caller.
# ---------------------------------------------------------------------------


def test_import_error_in_factory_is_wrapped():
    """Missing-dep at factory time must produce BLOCK, not propagate ImportError.

    The default_gate() factory imports httpx-backed RPC client lazily;
    if that import fails on a stripped-down environment, we must not
    silently approve trades against a chain we can't read.
    """

    def _missing_dep_factory():
        raise ImportError("No module named 'httpx'")

    gate = ChainHealthGate(client_factory=_missing_dep_factory)
    verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.severity == "BLOCK"
    assert "httpx" in " | ".join(verdict.reasons)
