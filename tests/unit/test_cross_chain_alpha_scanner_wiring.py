"""Regression guard for the cross-chain Aave arb scanner wiring.

Two defects, both silent behind a swallowed exception, so `/api/cross_chain/
aave_arb` returned HTTP 200 while doing nothing:

1. `_scan_aave_arb_async` imported `AaveApyArbScanner`, a name that no longer
   exists — the class is `CrossChainAaveScanner`. Every call raised
   ImportError, which `scan_aave_arb` caught and reported as an empty scan.
2. Fixing the name alone is not enough: a bare `CrossChainAaveScanner()`
   registers no per-chain facades, so `scan_top_assets` returns `[]`. That
   reads identically to "no arbitrage opportunities exist".
"""

from lib.hackathon.cross_chain_alpha import scan_aave_arb


def test_scanner_class_name_is_importable():
    """The name the caller imports must actually exist in the module."""
    from lib.chains.cross_chain.aave_apy_arb import CrossChainAaveScanner

    assert CrossChainAaveScanner is not None


def test_old_scanner_name_is_gone():
    """Guard against the stale name creeping back in."""
    import lib.chains.cross_chain.aave_apy_arb as mod

    assert not hasattr(mod, "AaveApyArbScanner")


def test_unwired_scanner_reports_error_not_empty_success():
    """The headline bug: no facades must surface as an explicit error."""
    result = scan_aave_arb()
    assert result["signal_count"] == 0
    assert result["signals"] == []
    assert "error" in result, "unwired scanner reported success"
    assert "not wired" in result["error"]


def test_unwired_result_keeps_documented_shape():
    result = scan_aave_arb(top_n=3)
    assert result["top_n"] == 3
    assert result["max_spread_bps"] is None
    assert set(result["thresholds"]) == {"min_signal_spread_bps", "extreme_spread_bps"}
    assert result["candidate_assets"]


def test_injected_scanner_is_used_and_no_import_error():
    """A wired scanner must reach scan_top_assets — proving the import works."""

    class _StubScanner:
        def __init__(self) -> None:
            self.calls: list[int] = []

        async def scan_top_assets(self, n: int = 5):
            self.calls.append(n)
            return []

    stub = _StubScanner()
    result = scan_aave_arb(top_n=4, scanner=stub)
    assert stub.calls == [4], "injected scanner was not invoked"
    # Reached the scanner cleanly, so no not-wired / ImportError error.
    assert "error" not in result
    assert result["signal_count"] == 0


def test_scanner_exception_is_reported_structurally():
    class _BoomScanner:
        async def scan_top_assets(self, n: int = 5):
            raise RuntimeError("rpc down")

    result = scan_aave_arb(scanner=_BoomScanner())
    assert result["signal_count"] == 0
    assert "RuntimeError" in result["error"]
    assert "rpc down" in result["error"]
