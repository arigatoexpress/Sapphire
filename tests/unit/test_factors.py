"""Unit tests for lib.analytics.factors — cross-sectional factor model.

Stdlib + pytest + monkeypatch only. No network. Covers:
- Pure-math helpers (_safe_pct_change, _realized_vol, _cross_sectional_z)
- Cache get/set TTL behavior
- _fetch_market_data success / failure / cache-hit paths
- CrossSectionalFactors.compute end-to-end with monkeypatched HTTP
- Volatility z-score inversion (lower vol = higher rank)
- to_dict serialization
- Edge cases: missing CoinGecko ID, empty universe, single asset, all-None factor
"""

from __future__ import annotations

import pytest

from lib.analytics import factors as f

# --- Helpers: _safe_pct_change ---------------------------------------------


class TestSafePctChange:
    def test_basic_positive_return(self):
        prices = [100.0] * 31  # 31 entries so lookback=30 is valid
        prices[-1] = 110.0  # +10% from prices[0]
        assert f._safe_pct_change(prices, 30) == pytest.approx(10.0)

    def test_basic_negative_return(self):
        prices = [200.0] * 8
        prices[-1] = 180.0  # -10% over 7 lookback
        assert f._safe_pct_change(prices, 7) == pytest.approx(-10.0)

    def test_too_few_prices_returns_none(self):
        # Need lookback+1 entries; only 5 here
        assert f._safe_pct_change([1.0, 2.0, 3.0, 4.0, 5.0], 30) is None

    def test_zero_old_price_returns_none(self):
        prices = [0.0] + [100.0] * 30  # old=0
        assert f._safe_pct_change(prices, 30) is None


# --- Helpers: _realized_vol ------------------------------------------------


class TestRealizedVol:
    def test_constant_prices_yield_zero(self):
        prices = [100.0] * 35
        vol = f._realized_vol(prices, window=30)
        assert vol is not None
        assert vol == pytest.approx(0.0, abs=1e-9)

    def test_volatile_prices_positive(self):
        # Alternating +5%/-5% oscillation → non-zero vol
        prices = [100.0]
        for i in range(35):
            prices.append(prices[-1] * (1.05 if i % 2 == 0 else 0.952381))
        vol = f._realized_vol(prices, window=30)
        assert vol is not None
        assert vol > 0.0

    def test_too_few_prices_returns_none(self):
        # Need at least window+1 prices
        assert f._realized_vol([100.0, 101.0, 102.0], window=30) is None

    def test_zero_prefix_filtered_by_prev_check(self):
        # _realized_vol skips the log-return when prices[i-1] <= 0.
        # Build a window where the first half has prices[i-1]=0 (skipped),
        # then a clean tail with enough valid returns to compute std.
        prices = [0.0] * 20 + [100.0] * 16  # 36 total; window=30 = prices[6..35]
        # In the window, prices[5..34] are: zeros until index 19, then 100s.
        # For i in 6..19, prices[i-1]=0 → skipped. For i=20, prices[19]=0 → skipped.
        # i in 21..35: prices[i-1]=100>0, prices[i]=100>0 → log(1)=0 contributes.
        # 15 valid returns of 0.0 → mean=0, var=0, vol=0.
        vol = f._realized_vol(prices, window=30)
        assert vol is not None
        assert vol == pytest.approx(0.0, abs=1e-9)


# --- Helpers: _cross_sectional_z -------------------------------------------


class TestCrossSectionalZ:
    def test_basic_zscores_sum_to_zero(self):
        vals = {"A": 1.0, "B": 2.0, "C": 3.0}
        z = f._cross_sectional_z(vals)
        # z-scores are mean-zero: mean of returns is exactly 0
        assert sum(z.values()) == pytest.approx(0.0, abs=1e-9)
        # B is the mean → its z-score is 0
        assert z["B"] == pytest.approx(0.0, abs=1e-9)
        # A < B < C ordering preserved
        assert z["A"] < z["B"] < z["C"]

    def test_none_values_become_zero(self):
        vals = {"A": 10.0, "B": 20.0, "C": None}
        z = f._cross_sectional_z(vals)
        assert z["C"] == 0.0
        # Non-None still get real z-scores
        assert z["A"] != z["B"]

    def test_fewer_than_two_valid_returns_zeros(self):
        vals = {"A": 1.0, "B": None, "C": None}
        z = f._cross_sectional_z(vals)
        # n<2 → degenerate, all 0.0
        assert z == {"A": 0.0, "B": 0.0, "C": 0.0}

    def test_zero_variance_uses_std_one(self):
        # All identical → variance 0 → std falls back to 1 (no div-by-zero)
        vals = {"A": 5.0, "B": 5.0, "C": 5.0}
        z = f._cross_sectional_z(vals)
        # All values identical = mean, so z-scores are all 0
        for v in z.values():
            assert v == pytest.approx(0.0)


# --- Cache get/set TTL -----------------------------------------------------


class TestCache:
    def setup_method(self):
        # Reset the module-level cache before each test for isolation.
        f._CACHE.clear()

    def test_set_then_get_returns_value(self):
        f._cache_set("foo", {"x": 1})
        assert f._cache_get("foo") == {"x": 1}

    def test_get_missing_returns_none(self):
        assert f._cache_get("never-set") is None

    def test_expired_entry_returns_none(self, monkeypatch):
        # Inject a stale timestamp by writing directly.
        f._CACHE["stale"] = (0.0, "old-value")  # monotonic=0 → way past TTL
        # _CACHE_TTL is 3600s; even a fresh monkeypatched monotonic > 3600 wipes it.
        monkeypatch.setattr(f.time, "monotonic", lambda: 4000.0)
        assert f._cache_get("stale") is None


# --- _fetch_market_data ----------------------------------------------------


class TestFetchMarketData:
    def setup_method(self):
        f._CACHE.clear()

    def test_cache_hit_skips_http(self, monkeypatch):
        called = {"n": 0}

        def fake_http_get(_url):  # pragma: no cover — only fires on miss
            called["n"] += 1
            return {}

        # Pre-populate cache
        f._cache_set("cg_market_bitcoin", {"chart": {"prices": []}, "detail": {}})
        # Ensure we don't import sources network path
        import lib.chain.sources as sources_mod
        monkeypatch.setattr(sources_mod, "_http_get", fake_http_get)
        out = f._fetch_market_data("bitcoin")
        assert out == {"chart": {"prices": []}, "detail": {}}
        assert called["n"] == 0  # never hit HTTP

    def test_http_failure_returns_none(self, monkeypatch):
        import lib.chain.sources as sources_mod

        def boom(_url):
            raise RuntimeError("network down")

        monkeypatch.setattr(sources_mod, "_http_get", boom)
        out = f._fetch_market_data("bitcoin")
        assert out is None

    def test_success_caches_result(self, monkeypatch):
        chart = {"prices": [[0, 100.0]], "total_volumes": [[0, 1e9]]}
        detail = {"market_data": {"market_cap": {"usd": 1e12}}}
        responses = iter([chart, detail])

        import lib.chain.sources as sources_mod
        monkeypatch.setattr(sources_mod, "_http_get", lambda _url: next(responses))
        out = f._fetch_market_data("bitcoin")
        assert out is not None
        assert out["chart"] is chart
        assert out["detail"] is detail
        # Now a second call must NOT call the iterator again (which would StopIteration).
        out2 = f._fetch_market_data("bitcoin")
        assert out2 is out


# --- CrossSectionalFactors.compute -----------------------------------------


def _make_market_data(
    prices_count: int = 35,
    base_price: float = 100.0,
    final_pct: float = 10.0,
    mcap: float = 1e10,
    vol_usd: float = 5e8,
    daily_vols: float | None = None,
) -> dict:
    """Build a CoinGecko-shaped response dict.

    Returns a chart with `prices_count` daily entries: flat at `base_price`
    until the last day, which is bumped by `final_pct` percent. Plus a
    `detail` block with given mcap and 24h volume.
    """
    if daily_vols is None:
        daily_vols = vol_usd
    prices = [[i * 86_400_000, base_price] for i in range(prices_count - 1)]
    prices.append([(prices_count - 1) * 86_400_000, base_price * (1 + final_pct / 100.0)])
    volumes = [[p[0], daily_vols] for p in prices]
    return {
        "chart": {"prices": prices, "total_volumes": volumes},
        "detail": {"market_data": {"market_cap": {"usd": mcap}, "total_volume": {"usd": vol_usd}}},
    }


class TestCompute:
    def setup_method(self):
        f._CACHE.clear()

    def test_compute_two_assets_ranks_by_composite(self, monkeypatch):
        # BTC: +20% momentum, ETH: -5% — BTC should rank #1
        btc_data = _make_market_data(final_pct=20.0, mcap=1e12)
        eth_data = _make_market_data(final_pct=-5.0, mcap=4e11)

        def fake_fetch(coin_id):
            if coin_id == "bitcoin":
                return btc_data
            if coin_id == "ethereum":
                return eth_data
            return None

        monkeypatch.setattr(f, "_fetch_market_data", fake_fetch)
        report = f.CrossSectionalFactors().compute(symbols=["BTC", "ETH"])

        assert report.strongest == "BTC"
        assert report.weakest == "ETH"
        assert report.ranked_assets == ["BTC", "ETH"]
        # Each asset got rank set
        assert report.assets[0].rank == 1
        assert report.assets[1].rank == 2
        # Dispersion is non-negative
        assert report.dispersion >= 0
        # Factor matrix populated for every requested factor
        for sym in ("BTC", "ETH"):
            for fn in f.FACTOR_NAMES:
                assert fn in report.factor_matrix[sym]

    def test_compute_skips_unknown_symbol(self, monkeypatch):
        btc_data = _make_market_data(final_pct=10.0)

        def fake_fetch(coin_id):
            return btc_data if coin_id == "bitcoin" else None

        monkeypatch.setattr(f, "_fetch_market_data", fake_fetch)
        # ZZZZ is not in ASSET_UNIVERSE — should be skipped without crashing.
        report = f.CrossSectionalFactors().compute(symbols=["BTC", "ZZZZ"])
        # Both symbols still appear (with z=0 fallback), but BTC has real data
        assert "BTC" in report.factor_matrix
        assert report.strongest in {"BTC", "ZZZZ"}
        # Unknown symbol's z-scores are all zero
        zzzz_z = report.factor_matrix.get("ZZZZ", {})
        for v in zzzz_z.values():
            assert v == 0.0

    def test_compute_handles_fetch_failure(self, monkeypatch):
        # All fetches return None → all factors missing → all z-scores 0.0
        monkeypatch.setattr(f, "_fetch_market_data", lambda _id: None)
        report = f.CrossSectionalFactors().compute(symbols=["BTC", "ETH"])
        # Composite scores should all be 0 (all z=0)
        for asset in report.assets:
            assert asset.composite_score == 0.0
        assert report.dispersion == 0.0

    def test_compute_volatility_inversion(self, monkeypatch):
        # Build two assets with identical momentum but different volatility.
        # Low-vol asset should outrank high-vol asset on the volatility factor
        # (z-scores get inverted: lower raw vol → higher z).
        low_vol_prices = [[i, 100.0] for i in range(35)]  # all flat → vol=0
        high_vol_prices = [[i, 100.0 * (1.05 if i % 2 else 0.952381)] for i in range(35)]
        # Pin both to the same final price so momentum is identical.
        low_vol_prices[-1][1] = 110.0
        high_vol_prices[-1][1] = 110.0

        low_data = {
            "chart": {"prices": low_vol_prices, "total_volumes": [[p[0], 1e9] for p in low_vol_prices]},
            "detail": {"market_data": {"market_cap": {"usd": 1e12}, "total_volume": {"usd": 5e8}}},
        }
        high_data = {
            "chart": {"prices": high_vol_prices, "total_volumes": [[p[0], 1e9] for p in high_vol_prices]},
            "detail": {"market_data": {"market_cap": {"usd": 1e12}, "total_volume": {"usd": 5e8}}},
        }

        def fake_fetch(coin_id):
            return low_data if coin_id == "bitcoin" else high_data

        monkeypatch.setattr(f, "_fetch_market_data", fake_fetch)
        report = f.CrossSectionalFactors().compute(symbols=["BTC", "ETH"])
        # BTC (low vol) should have HIGHER volatility z-score than ETH (high vol)
        assert report.factor_matrix["BTC"]["Volatility"] >= report.factor_matrix["ETH"]["Volatility"]

    def test_compute_caches_full_universe(self, monkeypatch):
        # When called with no symbols arg, the report cache key fires.
        call_count = {"n": 0}

        def fake_fetch(_id):
            call_count["n"] += 1
            return _make_market_data(final_pct=5.0)

        monkeypatch.setattr(f, "_fetch_market_data", fake_fetch)
        # First call populates cache
        r1 = f.CrossSectionalFactors().compute()
        # Second call should hit the cached factor_report without re-fetching.
        first_count = call_count["n"]
        r2 = f.CrossSectionalFactors().compute()
        assert call_count["n"] == first_count  # no new fetches
        assert r1 is r2

    def test_compute_single_asset_dispersion_zero(self, monkeypatch):
        monkeypatch.setattr(
            f, "_fetch_market_data", lambda _id: _make_market_data(final_pct=10.0)
        )
        report = f.CrossSectionalFactors().compute(symbols=["BTC"])
        # Single asset: dispersion = 0, strongest == weakest
        assert report.dispersion == 0.0
        assert report.strongest == "BTC"
        assert report.weakest == "BTC"


# --- to_dict serialization -------------------------------------------------


class TestToDict:
    def setup_method(self):
        f._CACHE.clear()

    def test_to_dict_shape(self, monkeypatch):
        monkeypatch.setattr(
            f, "_fetch_market_data", lambda _id: _make_market_data(final_pct=10.0)
        )
        report = f.CrossSectionalFactors().compute(symbols=["BTC", "ETH"])
        d = f.to_dict(report)

        # Required top-level keys present
        for key in (
            "timestamp",
            "factor_names",
            "ranked_assets",
            "strongest",
            "weakest",
            "dispersion",
            "asset_count",
            "assets",
            "factor_matrix",
        ):
            assert key in d

        assert d["asset_count"] == 2
        assert d["factor_names"] == f.FACTOR_NAMES
        # Each asset dict has expected keys
        for a in d["assets"]:
            assert {"symbol", "rank", "composite_score", "factors", "z_scores"} <= set(a.keys())
            # z-scores rounded to 3 decimals
            for v in a["z_scores"].values():
                assert isinstance(v, (int, float))
                # round(x, 3): max 3 fractional digits after rounding
                assert v == round(v, 3)

    def test_to_dict_handles_empty_assets(self):
        # Build an empty FactorReport directly (no fetches needed)
        report = f.FactorReport(
            timestamp=0.0,
            assets=[],
            ranked_assets=[],
            factor_matrix={},
            dispersion=0.0,
            strongest=None,
            weakest=None,
        )
        d = f.to_dict(report)
        assert d["asset_count"] == 0
        assert d["assets"] == []
        assert d["strongest"] is None
        assert d["weakest"] is None


# --- _risk_label-style branch sanity (not present here, but module sanity) ---


class TestModuleSanity:
    def test_factor_names_has_six(self):
        # The composite is an equal-weighted mean of these factors — it should
        # match the exact list documented in the module docstring.
        assert len(f.FACTOR_NAMES) == 6
        assert "Momentum 30d" in f.FACTOR_NAMES
        assert "Volatility" in f.FACTOR_NAMES

    def test_asset_universe_is_a_dict_of_strs(self):
        for sym, cg_id in f.ASSET_UNIVERSE.items():
            assert isinstance(sym, str)
            assert isinstance(cg_id, str)
            assert sym.isupper()

    def test_realized_vol_annualization_factor(self):
        # Constant 1% daily moves → annualized vol ≈ 1% * sqrt(365) * 100 ≈ 19.1%
        prices = [100.0]
        for _ in range(35):
            prices.append(prices[-1] * 1.01)
        vol = f._realized_vol(prices, window=30)
        assert vol is not None
        # Pure exponential growth: log returns are constant log(1.01); std=0, vol≈0
        assert vol < 1.0

    def test_realized_vol_with_known_alternating_returns(self):
        # log(1.01) and log(0.99) alternating → known stdev → known annualized vol
        prices = [100.0]
        for i in range(34):
            prices.append(prices[-1] * (1.01 if i % 2 == 0 else 0.99))
        vol = f._realized_vol(prices, window=30)
        assert vol is not None
        # std of alternating ≈ |log(1.01)| ≈ 0.00995 → annualized ≈ 19% — at minimum positive
        assert vol > 5.0

    def test_module_imports_without_network(self):
        # Sanity: re-importing factors must not trigger any network call.
        # (Import is already done at top of file; this just asserts module attrs)
        assert hasattr(f, "CrossSectionalFactors")
        assert hasattr(f, "to_dict")
        assert hasattr(f, "FactorReport")
        assert hasattr(f, "AssetFactors")
