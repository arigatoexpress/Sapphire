"""Unit tests for :mod:`lib.sources.sec_edgar`.

All HTTP is mocked — these tests must NOT make any live SEC EDGAR calls.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lib.sources import sec_edgar
from lib.sources.sec_classifier import FilingEvent
from lib.sources.sec_edgar import (
    MAX_TICKERS_PER_PULL,
    RATE_LIMIT_REQ_PER_SEC,
    RateLimiter,
    SECEdgarSource,
    _parse_minimal_yaml,
    _user_agent,
    filter_events,
    load_tickers_config,
    severity_breakdown,
)

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def example_filings_payload() -> dict:
    """Mimic SEC's submissions JSON (column-oriented recent block)."""
    return {
        "cik": "0000320193",
        "name": "APPLE INC",
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "8-K", "10-K", "S-3"],
                "accessionNumber": [
                    "0000320193-26-000001",
                    "0000320193-26-000002",
                    "0000320193-26-000003",
                    "0000320193-26-000004",
                    "0000320193-26-000005",
                ],
                "filingDate": [
                    "2026-04-28",
                    "2026-02-15",
                    "2026-01-10",
                    "2025-11-01",
                    "2025-10-15",
                ],
                "reportDate": [
                    "2026-04-28",
                    "2025-12-31",
                    "2026-01-10",
                    "2025-09-30",
                    "",
                ],
                "items": ["1.01,2.02", "", "4.01", "", ""],
                "primaryDocument": [
                    "aapl-20260428.htm",
                    "aapl-20251231.htm",
                    "aapl-20260110.htm",
                    "aapl-20250930.htm",
                    "aapl-s3.htm",
                ],
            }
        },
    }


@pytest.fixture()
def ticker_map_payload() -> dict:
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc"},
        "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp"},
    }


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "sec_tickers.yaml"
    cfg.write_text("tickers:\n  - AAPL\n  - NVDA\n", encoding="utf-8")
    return cfg


def _build_source(
    *,
    tmp_path: Path,
    config_path: Path,
    ticker_map_payload: dict,
    filings_payload: dict,
    fetcher_log: list[str] | None = None,
) -> SECEdgarSource:
    fetched_urls = fetcher_log if fetcher_log is not None else []

    def fake_fetch(url: str, headers):
        fetched_urls.append(url)
        if "company_tickers.json" in url:
            return ticker_map_payload
        if "/submissions/CIK" in url:
            return filings_payload
        return {}

    return SECEdgarSource(
        config_path=config_path,
        cache_path=tmp_path / "filings.json",
        tickers_cache_path=tmp_path / "ticker_map.json",
        fetcher=fake_fetch,
    )


# ---------------------------------------------------------------------------
# 1. Config loading
# ---------------------------------------------------------------------------


def test_load_tickers_config_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_tickers_config(tmp_path / "missing.yaml") == []


def test_load_tickers_config_parses_yaml_subset(tmp_path: Path) -> None:
    cfg = tmp_path / "sec_tickers.yaml"
    cfg.write_text(
        "tickers:\n  - AAPL\n  - nvda\n  - 'TSLA'\n# comment\nmax_per_pull: 4\n",
        encoding="utf-8",
    )
    assert load_tickers_config(cfg) == ["AAPL", "NVDA", "TSLA"]


def test_load_tickers_config_parses_json(tmp_path: Path) -> None:
    cfg = tmp_path / "tickers.json"
    cfg.write_text(json.dumps({"tickers": ["AAPL", "AAPL", "NVDA"]}), encoding="utf-8")
    # Dedup preserved; case normalized.
    assert load_tickers_config(cfg) == ["AAPL", "NVDA"]


def test_minimal_yaml_handles_scalars_and_bools() -> None:
    parsed = _parse_minimal_yaml(
        "tickers:\n  - AAPL\nmax_per_pull: 3\nflag_true: true\nflag_false: false\nname: \"hello\"\n"
    )
    assert parsed["tickers"] == ["AAPL"]
    assert parsed["max_per_pull"] == 3
    assert parsed["flag_true"] is True
    assert parsed["flag_false"] is False
    assert parsed["name"] == "hello"


# ---------------------------------------------------------------------------
# 2. User-Agent contract
# ---------------------------------------------------------------------------


def test_user_agent_uses_env_when_set(monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_SEC_UA_NAME", "AcmeQuant")
    monkeypatch.setenv("SAPPHIRE_SEC_UA_EMAIL", "ops@acme.example")
    ua = _user_agent()
    assert "AcmeQuant" in ua and "ops@acme.example" in ua


def test_user_agent_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_SEC_UA_NAME", raising=False)
    monkeypatch.delenv("SAPPHIRE_SEC_UA_EMAIL", raising=False)
    ua = _user_agent()
    # Default generated UA still identifies the project + an email.
    assert "Sapphire" in ua and "@" in ua


def test_user_agent_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_SEC_UA_NAME", "AcmeQuant")
    monkeypatch.setenv("SAPPHIRE_SEC_UA_EMAIL", "ops@acme.example")
    assert _user_agent(override="ZetaResearch/1.0 (ops@zeta.example)") == "ZetaResearch/1.0 (ops@zeta.example)"


# ---------------------------------------------------------------------------
# 3. Rate limiter (10 req/sec hard cap)
# ---------------------------------------------------------------------------


def test_rate_limiter_caps_to_sec_ceiling() -> None:
    rl = RateLimiter(rate=99)  # operator tries to override above ceiling
    assert rl.rate <= RATE_LIMIT_REQ_PER_SEC


def test_rate_limiter_minimum_rate_is_one() -> None:
    rl = RateLimiter(rate=0)
    assert rl.rate == 1


def test_rate_limiter_sleeps_to_throttle() -> None:
    rl = RateLimiter(rate=10)
    sleeps: list[float] = []
    times = iter([0.0, 0.0, 0.05, 0.05])  # second call at +50ms; should sleep ~50ms

    def fake_now() -> float:
        return next(times)

    rl.acquire(sleep=lambda d: sleeps.append(d), now=fake_now)
    rl.acquire(sleep=lambda d: sleeps.append(d), now=fake_now)
    # First call: no sleep (first interval). Second call: should request a positive sleep.
    assert any(s > 0 for s in sleeps)


# ---------------------------------------------------------------------------
# 4. Snapshot pull behavior
# ---------------------------------------------------------------------------


def test_dry_run_returns_empty_when_no_cache_and_no_live(
    tmp_path: Path, monkeypatch, tmp_config: Path
) -> None:
    monkeypatch.delenv("SAPPHIRE_SEC_LIVE", raising=False)
    src = SECEdgarSource(
        config_path=tmp_config,
        cache_path=tmp_path / "filings.json",
        tickers_cache_path=tmp_path / "ticker_map.json",
        fetcher=lambda url, headers: {"should_not_be_called": True},
    )
    events = src.list_events()
    assert events == []


def test_live_pull_fetches_ticker_map_and_filings(
    tmp_path: Path,
    tmp_config: Path,
    ticker_map_payload: dict,
    example_filings_payload: dict,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAPPHIRE_SEC_LIVE", "1")
    fetched_urls: list[str] = []
    src = _build_source(
        tmp_path=tmp_path,
        config_path=tmp_config,
        ticker_map_payload=ticker_map_payload,
        filings_payload=example_filings_payload,
        fetcher_log=fetched_urls,
    )
    events = src.list_events()
    assert any("/submissions/CIK0000320193.json" in u for u in fetched_urls)
    assert any("company_tickers.json" in u for u in fetched_urls)
    # Only target forms (8-K / 10-K / 10-Q) — S-3 dropped.
    assert all(e.form in {"8-K", "10-Q", "10-K", "10-K/A", "10-Q/A", "8-K/A"} for e in events)
    assert any(e.form == "8-K" and "1.01" in e.items for e in events)


def test_max_tickers_per_pull_clamped(
    tmp_path: Path,
    ticker_map_payload: dict,
    example_filings_payload: dict,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAPPHIRE_SEC_LIVE", "1")
    cfg = tmp_path / "many.yaml"
    cfg.write_text(
        "tickers:\n  - AAPL\n  - NVDA\n  - TSLA\n  - MSFT\n  - AMZN\n  - GOOG\n  - META\n",
        encoding="utf-8",
    )

    seen_ciks: list[str] = []

    def fake_fetch(url: str, headers):
        if "company_tickers.json" in url:
            return ticker_map_payload
        if "/submissions/CIK" in url:
            cik = url.rsplit("CIK", 1)[1].split(".")[0]
            seen_ciks.append(cik)
            return example_filings_payload
        return {}

    src = SECEdgarSource(
        config_path=cfg,
        cache_path=tmp_path / "fc.json",
        tickers_cache_path=tmp_path / "tm.json",
        fetcher=fake_fetch,
        max_tickers=99,  # operator override; still capped
    )
    src.list_events()
    # AAPL+NVDA exist in ticker_map_payload; the rest don't, so they're skipped before fetch.
    # But the cap still bounds us at 5 even if the map had more entries.
    assert len(seen_ciks) <= MAX_TICKERS_PER_PULL


def test_cache_used_within_ttl(
    tmp_path: Path,
    tmp_config: Path,
    ticker_map_payload: dict,
    example_filings_payload: dict,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAPPHIRE_SEC_LIVE", "1")
    cache_path = tmp_path / "filings.json"
    cache_path.write_text(
        json.dumps(
            {
                "retrieved_at": datetime.now(UTC).isoformat(),
                "filings": {
                    "AAPL": [
                        {
                            "form": "8-K",
                            "accession": "X-1",
                            "filed": "2026-04-01",
                            "report_date": "2026-04-01",
                            "items": "5.02",
                            "primary_document": "x.htm",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    fetched: list[str] = []
    src = SECEdgarSource(
        config_path=tmp_config,
        cache_path=cache_path,
        tickers_cache_path=tmp_path / "tm.json",
        fetcher=lambda url, headers: fetched.append(url) or {},
    )
    events = src.list_events()
    assert fetched == [], "cache hit should suppress all live fetches"
    assert len(events) == 1
    assert events[0].ticker == "AAPL" and "5.02" in events[0].items


def test_stale_cache_used_in_dry_run(
    tmp_path: Path, tmp_config: Path, monkeypatch
) -> None:
    monkeypatch.delenv("SAPPHIRE_SEC_LIVE", raising=False)
    cache_path = tmp_path / "filings.json"
    # Older than 1h (TTL boundary)
    old_iso = (datetime.now(UTC) - timedelta(hours=8)).isoformat()
    cache_path.write_text(
        json.dumps({"retrieved_at": old_iso, "filings": {"AAPL": [{"form": "10-K", "filed": "2024-09-30"}]}}),
        encoding="utf-8",
    )
    # Force mtime to be old so read_fresh_json returns None.
    old = time.time() - 10000
    Path(cache_path).touch()
    import os
    os.utime(cache_path, (old, old))
    src = SECEdgarSource(
        config_path=tmp_config,
        cache_path=cache_path,
        tickers_cache_path=tmp_path / "tm.json",
        fetcher=lambda url, headers: {},
    )
    events = src.list_events()
    # In dry-run, even a stale cache is consumable (better than nothing).
    assert any(e.form == "10-K" for e in events)


# ---------------------------------------------------------------------------
# 5. latest_for() behavior
# ---------------------------------------------------------------------------


def test_latest_for_returns_newest_filing(
    tmp_path: Path,
    tmp_config: Path,
    ticker_map_payload: dict,
    example_filings_payload: dict,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAPPHIRE_SEC_LIVE", "1")
    src = _build_source(
        tmp_path=tmp_path,
        config_path=tmp_config,
        ticker_map_payload=ticker_map_payload,
        filings_payload=example_filings_payload,
    )
    sig = src.latest_for("AAPL", "1d")
    assert sig is not None
    assert sig.symbol == "AAPL"
    assert sig.source == "sec_edgar"
    # Newest filing in the fixture is the 2026-04-28 8-K with item 1.01,2.02.
    assert "1.01" in sig.raw["items"]
    # Live operator flag echoed for audit
    assert sig.raw["live_operator_flag"] is True
    # Rate limit echoed
    assert sig.raw["rate_limit_req_per_sec"] <= RATE_LIMIT_REQ_PER_SEC


def test_latest_for_returns_none_for_unknown_ticker(
    tmp_path: Path,
    tmp_config: Path,
    ticker_map_payload: dict,
    example_filings_payload: dict,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAPPHIRE_SEC_LIVE", "1")
    src = _build_source(
        tmp_path=tmp_path,
        config_path=tmp_config,
        ticker_map_payload=ticker_map_payload,
        filings_payload=example_filings_payload,
    )
    assert src.latest_for("ZZZZ", "1d") is None


def test_latest_for_dry_run_no_live_returns_none_when_no_cache(
    tmp_path: Path, tmp_config: Path, monkeypatch
) -> None:
    monkeypatch.delenv("SAPPHIRE_SEC_LIVE", raising=False)
    src = SECEdgarSource(
        config_path=tmp_config,
        cache_path=tmp_path / "f.json",
        tickers_cache_path=tmp_path / "tm.json",
        fetcher=lambda url, headers: {},
    )
    assert src.latest_for("AAPL", "1d") is None


# ---------------------------------------------------------------------------
# 6. Filtering helpers + correlator integration smoke
# ---------------------------------------------------------------------------


def test_filter_events_by_form_and_severity() -> None:
    events = [
        FilingEvent(ticker="A", form="8-K", items="1.01", severity="high", direction="neutral", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="10-Q", items="", severity="high", direction="neutral", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="7.01", severity="low", direction="neutral", summary="", filed_at="", accession=""),
    ]
    only_8k = filter_events(events, forms=["8-K"])
    assert len(only_8k) == 2
    only_high_8k = filter_events(events, forms=["8-K"], severities=["high"])
    assert len(only_high_8k) == 1


def test_severity_breakdown_aggregates_correctly() -> None:
    events = [
        FilingEvent(ticker="A", form="8-K", items="1.01", severity="high", direction="neutral", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="5.02", severity="medium", direction="neutral", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="7.01", severity="low", direction="neutral", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="7.01", severity="low", direction="neutral", summary="", filed_at="", accession=""),
    ]
    breakdown = severity_breakdown(events)
    assert breakdown["high"] == 1
    assert breakdown["medium"] == 1
    assert breakdown["low"] == 2


def test_sec_edgar_registered_in_correlator_default_sources() -> None:
    from lib.correlator.sources import available_sources

    klasses = available_sources()
    assert SECEdgarSource in klasses


def test_sec_edgar_user_agent_header_set_on_fetch(
    tmp_path: Path,
    tmp_config: Path,
    ticker_map_payload: dict,
    example_filings_payload: dict,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAPPHIRE_SEC_LIVE", "1")
    captured: list[dict] = []

    def fake_fetch(url: str, headers):
        captured.append(dict(headers or {}))
        if "company_tickers.json" in url:
            return ticker_map_payload
        if "/submissions/CIK" in url:
            return example_filings_payload
        return {}

    src = SECEdgarSource(
        config_path=tmp_config,
        cache_path=tmp_path / "f.json",
        tickers_cache_path=tmp_path / "tm.json",
        fetcher=fake_fetch,
    )
    src.list_events()
    assert captured, "expected at least one fetch"
    for headers in captured:
        assert "User-Agent" in headers and headers["User-Agent"]


def test_sec_module_exports_match_public_api() -> None:
    # Defensive: keep public API stable
    public = set(sec_edgar.__all__)
    expected = {
        "CACHE_TTL_SECONDS",
        "DEFAULT_TICKERS_CONFIG",
        "MAX_TICKERS_PER_PULL",
        "RATE_LIMIT_REQ_PER_SEC",
        "RateLimiter",
        "SECEdgarSource",
        "SEC_SUBMISSIONS_URL",
        "SEC_TICKERS_URL",
        "TARGET_FORMS",
        "filter_events",
        "load_tickers_config",
        "severity_breakdown",
    }
    assert expected.issubset(public)
