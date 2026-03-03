"""
Unit tests — ExecutionIdempotency guard.

Critical paths:
  - claim() returns True on first call → False on duplicate (memory path)
  - Eviction: stale entries are evicted before each claim
  - mark_failed() removes signal from memory cache → allows retry
  - Graceful degradation: Firestore client = None → memory-only mode
  - Firestore: AlreadyExists → returns False (duplicate)
  - Firestore errors fail-open (return True to not block trades)
"""
import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/shared"))

from execution_idempotency import ExecutionIdempotency


# ── Memory-only mode ──────────────────────────────────────────────────────────

class TestIdempotencyMemoryMode:
    def _make(self, ttl=900) -> ExecutionIdempotency:
        return ExecutionIdempotency(platform="test", firestore_client=None, ttl_seconds=ttl)

    def test_first_claim_returns_true(self):
        ei = self._make()
        result = asyncio.get_event_loop().run_until_complete(ei.claim("sig-001", "BTCUSDT"))
        assert result is True

    def test_duplicate_claim_returns_false(self):
        ei = self._make()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ei.claim("sig-002", "ETHUSDT"))
        result = loop.run_until_complete(ei.claim("sig-002", "ETHUSDT"))
        assert result is False

    def test_different_signals_both_claim(self):
        ei = self._make()
        loop = asyncio.get_event_loop()
        r1 = loop.run_until_complete(ei.claim("sig-A", "SOLUSDT"))
        r2 = loop.run_until_complete(ei.claim("sig-B", "SOLUSDT"))
        assert r1 is True
        assert r2 is True

    def test_stale_entry_evicted_and_reclaimed(self):
        ei = self._make(ttl=1)  # 1-second TTL
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ei.claim("sig-evict", "SYM"))
        # Backdate the cache entry to be stale
        ei._cache["sig-evict"] = time.time() - 2
        result = loop.run_until_complete(ei.claim("sig-evict", "SYM"))
        assert result is True  # re-claimed after eviction

    def test_mark_failed_removes_from_cache_and_allows_retry(self):
        ei = self._make()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(ei.claim("sig-retry", "SYM"))
        loop.run_until_complete(ei.mark_failed("sig-retry", "network error"))
        result = loop.run_until_complete(ei.claim("sig-retry", "SYM"))
        assert result is True  # retry allowed after mark_failed

    def test_mark_executed_does_not_error_without_firestore(self):
        ei = self._make()
        loop = asyncio.get_event_loop()
        # Should complete silently with no Firestore client
        loop.run_until_complete(ei.mark_executed("sig-done", "order-123"))

    def test_warm_from_firestore_returns_zero_without_client(self):
        ei = self._make()
        count = asyncio.get_event_loop().run_until_complete(ei.warm_from_firestore())
        assert count == 0


# ── Document ID sanitization ───────────────────────────────────────────────────

class TestIdempotencyDocId:
    def _make(self) -> ExecutionIdempotency:
        return ExecutionIdempotency(platform="lighter", firestore_client=None)

    def test_doc_id_sanitizes_slashes(self):
        ei = self._make()
        doc_id = ei._doc_id("signal/with/slashes")
        assert "/" not in doc_id

    def test_doc_id_sanitizes_dots(self):
        ei = self._make()
        doc_id = ei._doc_id("signal.with.dots")
        assert "." not in doc_id

    def test_doc_id_includes_platform(self):
        ei = self._make()
        doc_id = ei._doc_id("my-signal")
        assert "lighter" in doc_id

    def test_doc_id_truncated_to_safe_length(self):
        ei = self._make()
        long_id = "x" * 300
        doc_id = ei._doc_id(long_id)
        # Platform suffix adds up to ~8 chars; total should stay within Firestore limits
        assert len(doc_id) < 256


# ── Firestore AlreadyExists path (mocked) ────────────────────────────────────

class _FakeDoc:
    class AlreadyExists(Exception):
        pass

    def __init__(self, fail_with=None):
        self._fail = fail_with

    async def create(self, data):
        if self._fail == "already_exists":
            from google.api_core.exceptions import AlreadyExists as GAlreadyExists
            raise GAlreadyExists("already exists")
        elif self._fail == "network":
            raise IOError("connection refused")


class _FakeCollection:
    def __init__(self, doc):
        self._doc = doc

    def document(self, name):
        return self._doc


class _FakeDb:
    def __init__(self, doc):
        self._doc = doc

    def collection(self, name):
        return _FakeCollection(self._doc)


class TestIdempotencyFirestorePaths:
    """These tests require google-api-core to be installed."""

    def test_firestore_already_exists_returns_false(self):
        try:
            from google.api_core.exceptions import AlreadyExists
        except ImportError:
            return  # skip if google-api-core not installed

        class MockDoc:
            async def create(self, data):
                raise AlreadyExists("dup")

        db = _FakeDb(MockDoc())
        ei = ExecutionIdempotency(platform="lighter", firestore_client=db)
        result = asyncio.get_event_loop().run_until_complete(
            ei._firestore_claim("sig-dup", "BTCUSDT")
        )
        assert result is False

    def test_firestore_network_error_fails_open(self):
        try:
            from google.api_core.exceptions import AlreadyExists  # noqa: F401
        except ImportError:
            return  # skip if google-api-core not installed

        class MockDoc:
            async def create(self, data):
                raise IOError("network failure")

        db = _FakeDb(MockDoc())
        ei = ExecutionIdempotency(platform="lighter", firestore_client=db)
        result = asyncio.get_event_loop().run_until_complete(
            ei._firestore_claim("sig-net", "BTCUSDT")
        )
        assert result is True  # fail-open → allow execution
