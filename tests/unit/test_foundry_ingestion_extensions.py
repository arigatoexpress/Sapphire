"""Unit tests for Tranche-3 Foundry ontology expansion (v0.2.0).

Covers the five new transforms in :mod:`lib.foundry.ingestion`:

- :func:`to_IntelVectorRecord` / :func:`transform_intel_vector_records`
- :func:`to_TelegramIntelMessage` / :func:`transform_telegram_intel_messages`
- :func:`to_HyperliquidSignal` / :func:`transform_hyperliquid_signals`
- :func:`to_OODAPacket` / :func:`transform_ooda_packets`
- :func:`to_ThreatIndicator` / :func:`transform_threat_indicators`

Each section exercises envelope shape, watermark progression (delta detection
relative to ``since``), malformed-source rejection, and idempotent
behaviour on repeated reads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from lib.foundry.ingestion import (
    ALL_TRANSFORMS,
    _extract_iocs,
    _normalize_iso,
    to_HyperliquidSignal,
    to_IntelVectorRecord,
    to_OODAPacket,
    to_TelegramIntelMessage,
    to_ThreatIndicator,
    transform_hyperliquid_signals,
    transform_intel_vector_records,
    transform_ooda_packets,
    transform_telegram_intel_messages,
    transform_threat_indicators,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_external_caches(monkeypatch, tmp_path):
    """Force every transform to ignore the developer's home caches.

    The 5 new transforms each have a fallback path under ``~/.cache`` or
    ``~/.sapphire``; tests must never read from those. We point every
    override env var at an empty tmp_path subdir.
    """
    bad = tmp_path / "__never_used__"
    bad.mkdir(exist_ok=True)
    for var, default in (
        ("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(bad / "vector.jsonl")),
        ("SAPPHIRE_TELEGRAM_INTEL_DATA_DIR", str(bad / "telegram")),
        ("SAPPHIRE_HYPERLIQUID_SIGNAL_PATH", str(bad / "hl_signals.jsonl")),
        ("SAPPHIRE_GEMINI_OODA_CACHE_DIR", str(bad / "ooda")),
    ):
        monkeypatch.setenv(var, default)


# ---------------------------------------------------------------------------
# IntelVectorRecord (≥5 cases)
# ---------------------------------------------------------------------------


class TestIntelVectorRecord:
    def test_envelope_shape_from_record(self):
        env = to_IntelVectorRecord(
            {
                "id": "vec-1",
                "text": "BTC funding rate flipped negative",
                "embedding": [0.1, -0.2, 0.3],
                "source": "convergence_watchlist",
                "metadata": {"region": "GLOBAL"},
                "created_at": "2026-04-27T10:00:00+00:00",
            }
        )
        assert env["id"] == "vec-1"
        assert env["record_id"] == "vec-1"
        assert env["text"].startswith("BTC funding rate")
        assert env["text_length"] == len("BTC funding rate flipped negative")
        assert env["embedding_dims"] == 3
        assert isinstance(env["embedding_hash"], str) and len(env["embedding_hash"]) == 16
        assert env["created_at"] == "2026-04-27T10:00:00+00:00"
        # Foundry envelope must NOT contain the raw vector.
        assert "embedding" not in env

    def test_missing_id_rejected(self):
        with pytest.raises(ValueError, match="id"):
            to_IntelVectorRecord({"id": "", "text": "x", "embedding": []})

    def test_missing_text_rejected(self):
        with pytest.raises(ValueError, match="text"):
            to_IntelVectorRecord({"id": "v", "text": "  ", "embedding": []})

    def test_non_dict_input_rejected(self):
        with pytest.raises(ValueError):
            to_IntelVectorRecord("not a dict")  # type: ignore[arg-type]

    def test_non_list_embedding_rejected(self):
        with pytest.raises(ValueError, match="embedding"):
            to_IntelVectorRecord({"id": "v", "text": "x", "embedding": "abc"})

    def test_non_numeric_embedding_rejected(self):
        with pytest.raises(ValueError, match="numeric"):
            to_IntelVectorRecord({"id": "v", "text": "x", "embedding": [0.1, "oops"]})

    def test_long_text_truncated(self):
        env = to_IntelVectorRecord(
            {
                "id": "v",
                "text": "X" * 5000,
                "embedding": [0.0] * 10,
            }
        )
        assert len(env["text"]) == 2000
        assert env["text_length"] == 5000

    def test_transform_reads_jsonl_with_meta_skipped(self, tmp_path, monkeypatch):
        path = tmp_path / "vector.jsonl"
        path.write_text(
            json.dumps({"__meta__": True, "last_index_at": "2026-04-27T00:00:00Z"})
            + "\n"
            + json.dumps(
                {
                    "id": "vec-A",
                    "text": "alpha",
                    "embedding": [0.1, 0.2],
                    "source": "sovereign_thesis",
                    "metadata": {},
                    "created_at": "2026-04-27T10:00:00+00:00",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "id": "vec-B",
                    "text": "beta",
                    "embedding": [0.3, 0.4],
                    "source": "ad_hoc",
                    "created_at": "2026-04-26T10:00:00+00:00",
                }
            )
            + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(path))
        objects = transform_intel_vector_records(tmp_path)
        ids = sorted(o["id"] for o in objects)
        assert ids == ["vec-A", "vec-B"]

    def test_transform_since_filter(self, tmp_path, monkeypatch):
        path = tmp_path / "vector.jsonl"
        path.write_text(
            json.dumps(
                {
                    "id": "old",
                    "text": "old",
                    "embedding": [0.1],
                    "created_at": "2026-04-10T00:00:00+00:00",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "id": "new",
                    "text": "new",
                    "embedding": [0.2],
                    "created_at": "2026-04-27T00:00:00+00:00",
                }
            )
            + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(path))
        since = datetime(2026, 4, 20, tzinfo=UTC)
        objects = transform_intel_vector_records(tmp_path, since=since)
        assert [o["id"] for o in objects] == ["new"]

    def test_transform_skips_records_without_text_or_id(self, tmp_path, monkeypatch):
        path = tmp_path / "vector.jsonl"
        path.write_text(
            json.dumps({"id": "", "text": "no id", "embedding": [0.1]})
            + "\n"
            + json.dumps({"id": "no-text", "text": "", "embedding": [0.1]})
            + "\n"
            + json.dumps({"id": "ok", "text": "ok", "embedding": [0.1]})
            + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(path))
        objects = transform_intel_vector_records(tmp_path)
        assert [o["id"] for o in objects] == ["ok"]


# ---------------------------------------------------------------------------
# TelegramIntelMessage (≥5 cases)
# ---------------------------------------------------------------------------


class TestTelegramIntelMessage:
    def _row(self, **overrides):
        base = {
            "schema_version": 1,
            "canonical_id": "abcd1234",
            "ingested_at": "2026-04-27T10:00:00+00:00",
            "channel": {
                "id": "chan-1",
                "handle": "@glassnode",
                "attribution": "Glassnode (public)",
            },
            "message": {
                "id": "1001",
                "text": "BTC funding flipped",
                "published_at": "2026-04-27T09:55:00+00:00",
                "truncated": False,
            },
            "quality": {"decision": "keep", "score": 0.9, "reason": "intel"},
            "classifier": {
                "label": "alpha",
                "confidence": 0.82,
                "source": "local-inference-proxy",
                "model": "hermes3:8b",
            },
        }
        base.update(overrides)
        return base

    def test_envelope_shape_from_row(self):
        env = to_TelegramIntelMessage(self._row())
        assert env["id"] == env["canonical_id"] == "abcd1234"
        assert env["channel_handle"] == "@glassnode"
        assert env["text"] == "BTC funding flipped"
        assert env["text_length"] == len("BTC funding flipped")
        assert env["truncated"] is False
        assert env["quality_decision"] == "keep"
        assert env["classifier_label"] == "alpha"
        assert env["classifier_model"] == "hermes3:8b"

    def test_missing_canonical_id_rejected(self):
        with pytest.raises(ValueError, match="canonical_id"):
            to_TelegramIntelMessage(self._row(canonical_id=""))

    def test_message_must_be_dict(self):
        with pytest.raises(ValueError, match="message"):
            to_TelegramIntelMessage(self._row(message="not a dict"))

    def test_long_text_truncated_and_length_preserved(self):
        big = "X" * 9000
        env = to_TelegramIntelMessage(self._row(message={"id": "1", "text": big}))
        assert len(env["text"]) == 4000
        assert env["text_length"] == 9000

    def test_transform_reads_dailies_and_dedupes(self, tmp_path, monkeypatch):
        base = tmp_path / "telegram_intel"
        day = base / "2026-04-27"
        day.mkdir(parents=True)
        rows = [
            self._row(canonical_id="c1"),
            self._row(canonical_id="c2"),
            # Dup of c1 within the same file should be deduped.
            self._row(canonical_id="c1"),
        ]
        (day / "messages.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        monkeypatch.setenv("SAPPHIRE_TELEGRAM_INTEL_DATA_DIR", str(base))
        objs = transform_telegram_intel_messages(tmp_path)
        ids = sorted(o["id"] for o in objs)
        assert ids == ["c1", "c2"]

    def test_transform_since_filter(self, tmp_path, monkeypatch):
        base = tmp_path / "telegram_intel"
        day = base / "2026-04-27"
        day.mkdir(parents=True)
        old = self._row(
            canonical_id="old",
            ingested_at="2026-04-10T00:00:00+00:00",
        )
        new = self._row(
            canonical_id="new",
            ingested_at="2026-04-27T00:00:00+00:00",
        )
        (day / "messages.jsonl").write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n")
        monkeypatch.setenv("SAPPHIRE_TELEGRAM_INTEL_DATA_DIR", str(base))
        since = datetime(2026, 4, 20, tzinfo=UTC)
        objs = transform_telegram_intel_messages(tmp_path, since=since)
        assert [o["id"] for o in objs] == ["new"]

    def test_transform_skips_non_dict_rows(self, tmp_path, monkeypatch):
        base = tmp_path / "telegram_intel"
        day = base / "2026-04-27"
        day.mkdir(parents=True)
        (day / "messages.jsonl").write_text(
            '"just a string"\n' + json.dumps(self._row(canonical_id="ok")) + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_TELEGRAM_INTEL_DATA_DIR", str(base))
        objs = transform_telegram_intel_messages(tmp_path)
        assert [o["id"] for o in objs] == ["ok"]


# ---------------------------------------------------------------------------
# HyperliquidSignal (≥5 cases)
# ---------------------------------------------------------------------------


class TestHyperliquidSignal:
    def _row(self, **overrides):
        base = {
            "schema_version": "hyperliquid.signal.v1",
            "topic": "hyperliquid.trade",
            "source": "hyperliquid-public-feed",
            "paper_only": True,
            "live_trading_enabled": False,
            "published_at": "2026-04-27T10:00:00+00:00",
            "signal_type": "large_trade",
            "symbol": "BTC",
            "side": "buy",
            "price": 65000.0,
            "size": 5.0,
            "notional_usd": 325000.0,
            "threshold_usd": 250000.0,
            "exchange_time_ms": 1714217400000,
            "trade_id": "tid-1",
            "observed_at": "2026-04-27T10:00:00+00:00",
            "event_id": "evt-1",
        }
        base.update(overrides)
        return base

    def test_envelope_shape(self):
        env = to_HyperliquidSignal(self._row())
        assert env["id"] == "hl:evt-1"
        assert env["topic"] == "hyperliquid.trade"
        assert env["symbol"] == "BTC"
        assert env["paper_only"] is True
        assert env["live_trading_enabled"] is False
        assert env["price"] == 65000.0

    def test_id_falls_back_to_deterministic_hash(self):
        env = to_HyperliquidSignal(self._row(event_id=""))
        assert env["id"].startswith("hl:")
        # Stable: same payload yields same id
        env2 = to_HyperliquidSignal(self._row(event_id=""))
        assert env["id"] == env2["id"]

    def test_missing_topic_rejected(self):
        with pytest.raises(ValueError, match="topic"):
            to_HyperliquidSignal(self._row(topic=""))

    def test_missing_symbol_rejected(self):
        with pytest.raises(ValueError, match="symbol"):
            to_HyperliquidSignal(self._row(symbol=""))

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError):
            to_HyperliquidSignal(["not a dict"])  # type: ignore[arg-type]

    def test_symbol_uppercased(self):
        env = to_HyperliquidSignal(self._row(symbol="btc"))
        assert env["symbol"] == "BTC"

    def test_transform_reads_repo_log(self, tmp_path, monkeypatch):
        log_path = tmp_path / "hl_signals.jsonl"
        log_path.write_text(
            json.dumps(self._row(event_id="a")) + "\n" + json.dumps(self._row(event_id="b")) + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_SIGNAL_PATH", str(log_path))
        objs = transform_hyperliquid_signals(tmp_path)
        ids = sorted(o["id"] for o in objs)
        assert ids == ["hl:a", "hl:b"]

    def test_transform_since_filter(self, tmp_path, monkeypatch):
        log_path = tmp_path / "hl_signals.jsonl"
        old = self._row(event_id="old", published_at="2026-04-10T00:00:00+00:00")
        new = self._row(event_id="new", published_at="2026-04-27T00:00:00+00:00")
        log_path.write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n")
        monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_SIGNAL_PATH", str(log_path))
        since = datetime(2026, 4, 20, tzinfo=UTC)
        objs = transform_hyperliquid_signals(tmp_path, since=since)
        assert [o["id"] for o in objs] == ["hl:new"]

    def test_transform_dedupes_repeated_event_ids(self, tmp_path, monkeypatch):
        log_path = tmp_path / "hl_signals.jsonl"
        row = self._row(event_id="dup")
        log_path.write_text(
            json.dumps(row) + "\n" + json.dumps(row) + "\n" + json.dumps(row) + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_SIGNAL_PATH", str(log_path))
        objs = transform_hyperliquid_signals(tmp_path)
        assert [o["id"] for o in objs] == ["hl:dup"]


# ---------------------------------------------------------------------------
# OODAPacket (≥5 cases)
# ---------------------------------------------------------------------------


class TestOODAPacket:
    def _envelope(self, **overrides):
        base = {
            "ooda": {
                "observe": "BTC funding rate -0.02%",
                "orient": "Bear bias mounting",
                "decide": "Defer Bitcoin spot adds",
                "act": ["Pause autobuy", "Wait for funding to flip"],
            },
            "tokens": {
                "prompt_tokens": 10,
                "output_tokens": 80,
                "total_tokens": 90,
            },
            "_cached_at": 1714217400.0,
            "provenance": {
                "generator": "plugins.claw_sapphire.gemini_ooda",
                "model": "gemini-2.5-flash",
                "generated_at": "2026-04-27T10:00:00+00:00",
                "ttl_seconds": 86400,
                "metadata": {"cache": True, "mode": "live"},
            },
            "request_hash": "deadbeef",
        }
        base.update(overrides)
        return base

    def test_envelope_shape(self):
        env = to_OODAPacket(self._envelope())
        assert env["id"] == "ooda:deadbeef"
        assert env["observe"].startswith("BTC funding")
        assert env["model"] == "gemini-2.5-flash"
        assert env["mode"] == "live"
        assert env["total_tokens"] == 90
        assert env["cached"] is True

    def test_missing_request_hash_rejected(self):
        bad = self._envelope()
        bad.pop("request_hash")
        with pytest.raises(ValueError, match="request_hash|topic_hash"):
            to_OODAPacket(bad)

    def test_missing_ooda_block_rejected(self):
        bad = self._envelope()
        bad.pop("ooda")
        with pytest.raises(ValueError, match="ooda"):
            to_OODAPacket(bad)

    def test_act_array_capped(self):
        many_actions = [f"action-{i}" for i in range(50)]
        env = to_OODAPacket(
            self._envelope(ooda={"observe": "x", "orient": "y", "decide": "z", "act": many_actions})
        )
        assert len(env["act"]) == 8

    def test_long_strings_truncated(self):
        big = "Q" * 2000
        env = to_OODAPacket(
            self._envelope(ooda={"observe": big, "orient": big, "decide": big, "act": [big]})
        )
        assert len(env["observe"]) == 1000
        assert len(env["orient"]) == 1000
        assert len(env["decide"]) == 1000
        assert len(env["act"][0]) == 500

    def test_transform_reads_cache_dir(self, tmp_path, monkeypatch):
        cache = tmp_path / "ooda_cache"
        cache.mkdir()
        # Real filename is the request hash.
        (cache / "abcd1234.json").write_text(json.dumps(self._envelope()))
        # Counter file must be skipped.
        (cache / "counters.json").write_text('{"calls": []}')
        monkeypatch.setenv("SAPPHIRE_GEMINI_OODA_CACHE_DIR", str(cache))
        objs = transform_ooda_packets(tmp_path)
        assert len(objs) == 1
        assert objs[0]["id"] == "ooda:abcd1234"
        assert objs[0]["request_hash"] == "abcd1234"

    def test_transform_handles_corrupt_json(self, tmp_path, monkeypatch):
        cache = tmp_path / "ooda_cache"
        cache.mkdir()
        (cache / "ok.json").write_text(json.dumps(self._envelope()))
        (cache / "corrupt.json").write_text("not json{{")
        monkeypatch.setenv("SAPPHIRE_GEMINI_OODA_CACHE_DIR", str(cache))
        objs = transform_ooda_packets(tmp_path)
        assert {o["id"] for o in objs} == {"ooda:ok"}

    def test_transform_since_filter(self, tmp_path, monkeypatch):
        cache = tmp_path / "ooda_cache"
        cache.mkdir()
        old_env = self._envelope()
        old_env["provenance"]["generated_at"] = "2026-04-10T00:00:00+00:00"
        new_env = self._envelope()
        new_env["provenance"]["generated_at"] = "2026-04-27T00:00:00+00:00"
        (cache / "old.json").write_text(json.dumps(old_env))
        (cache / "new.json").write_text(json.dumps(new_env))
        monkeypatch.setenv("SAPPHIRE_GEMINI_OODA_CACHE_DIR", str(cache))
        since = datetime(2026, 4, 20, tzinfo=UTC)
        objs = transform_ooda_packets(tmp_path, since=since)
        assert [o["id"] for o in objs] == ["ooda:new"]


# ---------------------------------------------------------------------------
# ThreatIndicator (≥5 cases)
# ---------------------------------------------------------------------------


class TestThreatIndicator:
    def test_extract_iocs_basic(self):
        text = (
            "CVE-2026-1234 affects 192.168.1.1 and example.com. "
            "Hash: deadbeefcafebabe1234567890abcdef "
            "Another CVE-2026-1234 (dup) and 8.8.8.8."
        )
        iocs = _extract_iocs(text)
        assert "CVE-2026-1234" in iocs["cve_ids"]
        assert "192.168.1.1" in iocs["ipv4"]
        assert "8.8.8.8" in iocs["ipv4"]
        assert "example.com" in iocs["domains"]
        # Hashes are normalised to lowercase.
        assert any(h.startswith("deadbeefcafebabe") for h in iocs["hashes"])

    def test_extract_iocs_skips_invalid_ipv4(self):
        text = "999.999.999.999 is not real"
        iocs = _extract_iocs(text)
        assert iocs["ipv4"] == []

    def test_envelope_shape_from_advisory(self):
        env = to_ThreatIndicator(
            {
                "canonical_id": "adv-1",
                "title": "Critical RCE in libfoo",
                "description": "Affects 10.0.0.1; CVE-2026-9999",
                "severity": "critical",
                "source": "CISA",
                "published": "2026-04-27",
                "exploited": True,
                "cve_ids": ["CVE-2026-9999"],
                "domains": ["malware.example.org"],
            }
        )
        assert env["id"] == "ti:adv-1"
        assert env["advisory_id"] == "adv-1"
        assert env["exploited"] is True
        assert "CVE-2026-9999" in env["cve_ids"]
        assert "10.0.0.1" in env["ipv4_addresses"]
        assert "malware.example.org" in env["domains"]
        assert env["ioc_total"] >= 3

    def test_missing_title_rejected(self):
        with pytest.raises(ValueError, match="title"):
            to_ThreatIndicator({"title": "", "id": "x"})

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError):
            to_ThreatIndicator("nope")  # type: ignore[arg-type]

    def test_id_derived_when_canonical_missing(self):
        env = to_ThreatIndicator({"title": "Mystery threat", "published": "2026-04-27"})
        assert env["id"].startswith("ti:")
        assert env["advisory_id"]

    def test_transform_threats_json(self, tmp_path):
        intel_dir = tmp_path / "data" / "intelligence" / "2026-04-27"
        intel_dir.mkdir(parents=True)
        (intel_dir / "threats.json").write_text(
            json.dumps(
                {
                    "threats": [
                        {
                            "canonical_id": "t1",
                            "title": "RCE in libfoo",
                            "severity": "critical",
                            "source": "CISA",
                            "published": "2026-04-27",
                            "cve_ids": ["CVE-2026-1111"],
                            "exploited": True,
                        }
                    ]
                }
            )
        )
        objs = transform_threat_indicators(tmp_path)
        assert any(o["id"] == "ti:t1" for o in objs)

    def test_transform_threat_intel_md(self, tmp_path):
        md_dir = tmp_path / "data" / "threat_intel"
        md_dir.mkdir(parents=True)
        (md_dir / "advisory.md").write_text(
            "# Critical CVE-2026-7777 Advisory\n\nAffects 203.0.113.5.\n"
        )
        objs = transform_threat_indicators(tmp_path)
        # The MD-derived indicator should pick up the CVE + IP in the IOC arrays.
        md_obj = next(o for o in objs if o["title"].startswith("Critical CVE"))
        assert "CVE-2026-7777" in md_obj["cve_ids"]
        assert "203.0.113.5" in md_obj["ipv4_addresses"]

    def test_transform_dedupes_across_md_and_json(self, tmp_path):
        intel_dir = tmp_path / "data" / "intelligence" / "2026-04-27"
        intel_dir.mkdir(parents=True)
        (intel_dir / "threats.json").write_text(
            json.dumps(
                {
                    "threats": [
                        {
                            "canonical_id": "t1",
                            "title": "Same advisory",
                            "severity": "high",
                            "published": "2026-04-27",
                        }
                    ]
                }
            )
        )
        md_dir = tmp_path / "data" / "threat_intel"
        md_dir.mkdir(parents=True)
        # MD file would generate ti:<hash>; ensure both surfaces produce
        # distinct ids and neither is dropped.
        (md_dir / "different.md").write_text("# Different\n\nCVE-2026-2222\n")
        objs = transform_threat_indicators(tmp_path)
        ids = {o["id"] for o in objs}
        assert "ti:t1" in ids
        assert any(i.startswith("ti:") and i != "ti:t1" for i in ids)


# ---------------------------------------------------------------------------
# ALL_TRANSFORMS registration + helper
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_all_new_types_registered(self):
        for name in (
            "IntelVectorRecord",
            "TelegramIntelMessage",
            "HyperliquidSignal",
            "OODAPacket",
            "ThreatIndicator",
        ):
            assert name in ALL_TRANSFORMS
            assert callable(ALL_TRANSFORMS[name])

    def test_normalize_iso_handles_datetime(self):
        dt = datetime(2026, 4, 27, 10, 0, tzinfo=UTC)
        assert _normalize_iso(dt).startswith("2026-04-27")

    def test_normalize_iso_handles_none(self):
        assert _normalize_iso(None) is None
        assert _normalize_iso("") is None

    def test_normalize_iso_handles_unix_timestamp(self):
        # 2026-04-27T10:00:00+00:00 ≈ 1777716000
        result = _normalize_iso(1777716000)
        assert result is not None and "2026-" in result

    def test_normalize_iso_rejects_negative_numeric(self):
        assert _normalize_iso(-1) is None
        assert _normalize_iso(0) is None


# ---------------------------------------------------------------------------
# Watermark integration via transform_all (delta detection check)
# ---------------------------------------------------------------------------


class TestWatermarkProgression:
    """Watermark progression is exercised end-to-end via run_sync; see
    tests/unit/test_foundry_sync_extensions.py. Here we verify the input
    delta semantics: a transform run twice without source change returns
    the same envelope shape, and re-running after a source change picks
    up the new record.
    """

    def test_repeated_run_idempotent(self, tmp_path, monkeypatch):
        path = tmp_path / "vector.jsonl"
        path.write_text(
            json.dumps(
                {
                    "id": "v1",
                    "text": "alpha",
                    "embedding": [0.1],
                    "created_at": "2026-04-27T10:00:00+00:00",
                }
            )
            + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(path))
        first = transform_intel_vector_records(tmp_path)
        second = transform_intel_vector_records(tmp_path)
        # Same source → same envelope shape (excluding _sapphire_source path
        # tail which can vary by absolute vs relative).
        assert [o["id"] for o in first] == [o["id"] for o in second]
        assert first[0]["embedding_hash"] == second[0]["embedding_hash"]

    def test_picks_up_new_record_after_append(self, tmp_path, monkeypatch):
        path = tmp_path / "hl_signals.jsonl"
        first_row = {
            "topic": "hyperliquid.trade",
            "symbol": "BTC",
            "signal_type": "large_trade",
            "event_id": "first",
            "published_at": "2026-04-27T10:00:00+00:00",
        }
        path.write_text(json.dumps(first_row) + "\n")
        monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_SIGNAL_PATH", str(path))
        first = transform_hyperliquid_signals(tmp_path)
        assert {o["id"] for o in first} == {"hl:first"}

        # Append a new record; transform should pick it up on next call.
        with path.open("a") as fh:
            fh.write(
                json.dumps(
                    {
                        **first_row,
                        "event_id": "second",
                        "published_at": "2026-04-27T11:00:00+00:00",
                    }
                )
                + "\n"
            )
        second = transform_hyperliquid_signals(tmp_path)
        assert {o["id"] for o in second} == {"hl:first", "hl:second"}


# ---------------------------------------------------------------------------
# Retry / robustness on transient errors
# ---------------------------------------------------------------------------


class TestTransientErrorTolerance:
    """Each transform should keep moving past partial corruption / read errors."""

    def test_intel_vector_skips_unparseable_lines(self, tmp_path, monkeypatch):
        path = tmp_path / "vector.jsonl"
        path.write_text(
            "garbage{not-json\n" + json.dumps({"id": "ok", "text": "ok", "embedding": [0.1]}) + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(path))
        objs = transform_intel_vector_records(tmp_path)
        assert [o["id"] for o in objs] == ["ok"]

    def test_hyperliquid_skips_non_dict_and_continues(self, tmp_path, monkeypatch):
        path = tmp_path / "hl_signals.jsonl"
        path.write_text(
            "[1, 2, 3]\n"
            + json.dumps(
                {
                    "topic": "hyperliquid.trade",
                    "symbol": "BTC",
                    "signal_type": "x",
                    "event_id": "alive",
                    "published_at": "2026-04-27T10:00:00+00:00",
                }
            )
            + "\n"
        )
        monkeypatch.setenv("SAPPHIRE_HYPERLIQUID_SIGNAL_PATH", str(path))
        objs = transform_hyperliquid_signals(tmp_path)
        assert [o["id"] for o in objs] == ["hl:alive"]

    def test_telegram_intel_handles_missing_directory(self, tmp_path, monkeypatch):
        # Override points to a non-existent dir; transform should return [].
        monkeypatch.setenv("SAPPHIRE_TELEGRAM_INTEL_DATA_DIR", str(tmp_path / "does-not-exist"))
        objs = transform_telegram_intel_messages(tmp_path)
        assert objs == []

    def test_ooda_handles_missing_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_GEMINI_OODA_CACHE_DIR", str(tmp_path / "no-cache"))
        objs = transform_ooda_packets(tmp_path)
        assert objs == []

    def test_threat_indicator_handles_no_sources(self, tmp_path):
        # No data/intelligence and no data/threat_intel — clean empty result.
        objs = transform_threat_indicators(tmp_path)
        assert objs == []

    def test_threat_indicator_since_filter(self, tmp_path):
        intel_dir = tmp_path / "data" / "intelligence" / "2026-04-10"
        intel_dir.mkdir(parents=True)
        (intel_dir / "threats.json").write_text(
            json.dumps(
                {
                    "threats": [
                        {
                            "canonical_id": "old",
                            "title": "Old advisory",
                            "published": "2026-04-10",
                        }
                    ]
                }
            )
        )
        recent_dir = tmp_path / "data" / "intelligence" / "2026-04-27"
        recent_dir.mkdir(parents=True)
        (recent_dir / "threats.json").write_text(
            json.dumps(
                {
                    "threats": [
                        {
                            "canonical_id": "new",
                            "title": "New advisory",
                            "published": "2026-04-27",
                        }
                    ]
                }
            )
        )
        since = datetime(2026, 4, 20, tzinfo=UTC)
        objs = transform_threat_indicators(tmp_path, since=since)
        ids = {o["id"] for o in objs}
        assert ids == {"ti:new"}


# ---------------------------------------------------------------------------
# Backward-compat smoke test: existing transforms still run
# ---------------------------------------------------------------------------


def test_existing_transforms_unaffected(tmp_path):
    """Verify we did not break the original 8 transforms."""
    from lib.foundry.ingestion import transform_all

    result = transform_all(tmp_path)
    for k in (
        "PaperTrade",
        "Alert",
        "ServiceHealth",
        "ThreatIntel",
        "DailyBrief",
        "Region",
        "IntelItem",
        "IntelSourceHealth",
    ):
        assert k in result
        assert isinstance(result[k], list)


def test_new_transforms_appear_in_transform_all(tmp_path):
    """The 5 new types must show up in :func:`transform_all`."""
    from lib.foundry.ingestion import transform_all

    result = transform_all(tmp_path)
    for k in (
        "IntelVectorRecord",
        "TelegramIntelMessage",
        "HyperliquidSignal",
        "OODAPacket",
        "ThreatIndicator",
    ):
        assert k in result


def test_transform_all_with_since_runs_without_error(tmp_path):
    from lib.foundry.ingestion import transform_all

    since = datetime.now(UTC) - timedelta(days=1)
    # No data on disk, but every transform must succeed and return a list.
    result = transform_all(tmp_path, since=since)
    assert all(isinstance(v, list) for v in result.values())
