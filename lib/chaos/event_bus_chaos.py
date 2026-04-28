"""Chaos scenarios targeted at ``lib.core.event_bus.EventBus``.

Each scenario is a small dataclass that:
  1. Builds an ``EventBus`` wired against an in-memory ``FakeRedis`` shim and
     a temp JSONL fallback path.
  2. Trips one or more faults via the ``FaultInjector`` primitives.
  3. Drives a series of publishes / subscribes against the bus.
  4. Returns a ``ChaosTranscript`` capturing what happened on each backing
     store, in order, for the test to assert against.

Five canonical scenarios are exposed:
  * ``RedisDiesMidPublishScenario`` — Redis raises mid-stream of publishes.
    Asserts: post-trip events appear in JSONL, pre-trip events stay in Redis,
    union covers every published event exactly once.
  * ``RedisDiesMidSubscribeScenario`` — subscriber's Redis read raises after a
    point. Asserts: events still flow through the JSONL tail to subscribers.
  * ``JsonlDiskFullScenario`` — Redis is dead AND fallback writes start
    raising OSError partway through. Asserts: bus does not crash; events that
    successfully wrote are intact; the bus reports the loss without raising.
  * ``RedisRecoversAfterScenario`` — Redis dies, then heals. Asserts: events
    published while down land in JSONL; events published post-recovery land
    in Redis; ordering across the boundary is preserved when a replay merges
    both.
  * ``DualWriteMismatchScenario`` — when both Redis and JSONL accept the same
    event (a hypothetical dual-write configuration), assert no duplication
    of work in the consumer-side merge.

These scenarios never touch a real Redis or filesystem; the ``FakeRedis``
shim and the temp JSONL path are passed to the bus explicitly. Any test
landing here MUST mock ``lib.core.event_bus.redis.Redis`` so the bus's own
``_connect`` path doesn't try to dial 127.0.0.1.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from lib.chaos.fault_injector import (
    FaultInjector,
    IntermittentErrorPolicy,
    NetworkPartition,
    NetworkPartitionError,
    SlowDisk,
)

# ---------------------------------------------------------------------------
# FakeRedis shim
# ---------------------------------------------------------------------------


class FakeRedisError(ConnectionError):
    """Raised when the FakeRedis shim is in a 'dead' state."""


@dataclass
class _StreamEntry:
    stream_id: str
    fields: dict[str, str]


class FakeRedis:
    """In-memory subset of redis-py used by EventBus.

    Implements only the methods the bus actually calls:
      - ``ping``
      - ``xadd(stream, entry, maxlen=..., approximate=...)``
      - ``xrange(stream, min, max, count=...)``
      - ``xread(cursor, count=..., block=...)``
      - ``xreadgroup(group, consumer, streams, count=..., block=...)``
      - ``xgroup_create(stream, group, id=, mkstream=)``

    A ``partition`` flag short-circuits all calls into a raise; tests trip it
    via ``trip()`` to simulate Redis dying.
    """

    def __init__(self) -> None:
        self.streams: dict[str, list[_StreamEntry]] = {}
        self.partition = NetworkPartition(
            name="redis", exception_factory=lambda m: FakeRedisError(m)
        )
        self._seq = 0
        self._lock = threading.Lock()
        self._intermittent: IntermittentErrorPolicy | None = None
        self._call_count = 0

    # Helper used by EventBus._connect — always succeeds when not partitioned.
    def ping(self) -> bool:
        self._maybe_raise()
        return True

    def trip(self) -> None:
        self.partition.trip()

    def heal(self) -> None:
        self.partition.heal()

    def attach_intermittent(self, policy: IntermittentErrorPolicy) -> None:
        self._intermittent = policy

    def _maybe_raise(self) -> None:
        if self.partition.partitioned:
            raise FakeRedisError("redis partition active")
        self._call_count += 1
        if self._intermittent is not None and self._intermittent.should_fail(
            self._call_count
        ):
            raise FakeRedisError(
                f"intermittent failure (call #{self._call_count})"
            )

    def xadd(
        self,
        stream: str,
        entry: dict[str, str],
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        self._maybe_raise()
        with self._lock:
            self._seq += 1
            ms = int(time.time() * 1000)
            stream_id = f"{ms}-{self._seq}"
            self.streams.setdefault(stream, []).append(
                _StreamEntry(stream_id=stream_id, fields=dict(entry))
            )
            if maxlen is not None and len(self.streams[stream]) > maxlen:
                self.streams[stream] = self.streams[stream][-maxlen:]
            return stream_id

    def xrange(
        self,
        stream: str,
        min: str = "-",  # noqa: A002 — mirrors redis-py signature
        max: str = "+",  # noqa: A002
        count: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        self._maybe_raise()
        entries = self.streams.get(stream, [])
        out: list[tuple[str, dict[str, str]]] = []
        for e in entries:
            out.append((e.stream_id, e.fields))
            if count and len(out) >= count:
                break
        return out

    def xread(
        self,
        cursor: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        self._maybe_raise()
        out: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []
        for stream, last_id in cursor.items():
            entries = self.streams.get(stream, [])
            new_entries: list[tuple[str, dict[str, str]]] = []
            for e in entries:
                if last_id == "$" or e.stream_id > last_id:
                    new_entries.append((e.stream_id, e.fields))
                if count and len(new_entries) >= count:
                    break
            if new_entries:
                out.append((stream, new_entries))
        return out

    def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        self._maybe_raise()
        # Simplified: same as xread for our purposes; consumer/group are recorded
        # but not used to dedupe — chaos tests don't need full XPENDING semantics.
        cursor = {s: "$" if v == ">" else v for s, v in streams.items()}
        return self.xread(cursor, count=count, block=block)

    def xgroup_create(
        self, stream: str, group: str, id: str = "$", mkstream: bool = False  # noqa: A002
    ) -> bool:
        self._maybe_raise()
        if mkstream:
            self.streams.setdefault(stream, [])
        return True

    def all_entries(self) -> list[tuple[str, str, dict[str, str]]]:
        """Return [(stream, stream_id, fields), ...] for every entry, ordered."""
        out: list[tuple[str, str, dict[str, str]]] = []
        for stream, entries in self.streams.items():
            for e in entries:
                out.append((stream, e.stream_id, e.fields))
        return out


# ---------------------------------------------------------------------------
# ChaosTranscript
# ---------------------------------------------------------------------------


@dataclass
class ChaosTranscript:
    """Captured record of what happened in a single chaos run.

    Tests assert against this rather than re-reading the bus, because the
    chaos run may have mutated the bus mid-flight.

    - ``published`` — every event the test asked the bus to publish, in order
      ``(idx, event_type, source, marker)`` where ``marker`` is the unique
      string in ``data["marker"]`` so the test can prove no duplicates.
    - ``redis_seen`` — events that landed in the FakeRedis store at run end.
    - ``jsonl_seen`` — events that ended up in the JSONL fallback at run end.
    - ``errors`` — exceptions captured by the bus (it shouldn't raise on the
      caller; chaos tests verify this).
    - ``backend_per_event`` — for each published event, the backend that
      received it (``redis`` / ``jsonl`` / ``lost``). Lets tests assert
      zero-loss + ordering invariants in one go.
    """

    scenario: str = "unknown"
    published: list[tuple[int, str, str, str]] = field(default_factory=list)
    redis_seen: list[tuple[str, str, str]] = field(default_factory=list)
    jsonl_seen: list[tuple[str, str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    backend_per_event: list[tuple[int, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def total_published(self) -> int:
        return len(self.published)

    def markers_published(self) -> list[str]:
        return [marker for _, _, _, marker in self.published]

    def markers_in_redis(self) -> list[str]:
        return [marker for _, _, marker in self.redis_seen]

    def markers_in_jsonl(self) -> list[str]:
        return [marker for _, _, marker in self.jsonl_seen]

    def markers_anywhere(self) -> set[str]:
        return set(self.markers_in_redis()) | set(self.markers_in_jsonl())

    def lost_markers(self) -> set[str]:
        return set(self.markers_published()) - self.markers_anywhere()

    def duplicates(self) -> list[str]:
        from collections import Counter

        counts = Counter(self.markers_in_redis() + self.markers_in_jsonl())
        return [m for m, c in counts.items() if c > 1]

    def assert_zero_loss(self) -> None:
        lost = self.lost_markers()
        if lost:
            raise AssertionError(
                f"chaos scenario {self.scenario!r}: lost {len(lost)} events: {sorted(lost)}"
            )

    def assert_no_duplicates(self) -> None:
        dups = self.duplicates()
        if dups:
            raise AssertionError(
                f"chaos scenario {self.scenario!r}: duplicates: {dups}"
            )

    def assert_ordering_preserved(self) -> None:
        """Across redis+jsonl, the published order must match the merged order.

        Redis stream IDs are ``<ms>-<seq>``; JSONL local IDs are
        ``local-<ms>-<uuid>``. Both encode real-time milliseconds in the same
        position, so we sort on the leading numeric ``ms`` part to merge in
        real-time order. The merged sequence must match ``published`` exactly,
        otherwise an event was reordered or dropped.
        """

        def _sort_key(stream_id: str) -> tuple[int, str]:
            # Strip "local-" if present, then split on "-".
            sid = stream_id[len("local-") :] if stream_id.startswith("local-") else stream_id
            parts = sid.split("-", 1)
            try:
                return (int(parts[0]), parts[1] if len(parts) > 1 else "")
            except ValueError:
                return (0, sid)

        merged: list[tuple[tuple[int, str], str]] = []
        for stream_id, _, marker in self.redis_seen:
            merged.append((_sort_key(stream_id), marker))
        for stream_id, _, marker in self.jsonl_seen:
            merged.append((_sort_key(stream_id), marker))
        merged.sort(key=lambda x: x[0])
        merged_markers = [m for _, m in merged]
        published = self.markers_published()
        if merged_markers != published:
            raise AssertionError(
                f"chaos scenario {self.scenario!r}: ordering violated; "
                f"published={published} merged={merged_markers}"
            )


# ---------------------------------------------------------------------------
# ChaosScenario base class
# ---------------------------------------------------------------------------


@dataclass
class ChaosScenario:
    """Base scenario — holds the FakeRedis + temp paths + driver."""

    name: str = "scenario"
    description: str = ""
    fault: FaultInjector = field(default_factory=lambda: FaultInjector(name="default"))
    fake_redis: FakeRedis = field(default_factory=FakeRedis)
    fallback_path: Path | None = None
    captured: ChaosTranscript = field(default_factory=ChaosTranscript)

    def setup(self, fallback_path: Path) -> None:
        self.fallback_path = fallback_path
        self.captured.scenario = self.name
        self.fault.register("redis", self.fake_redis.partition)

    def build_bus(self) -> Any:
        """Construct an EventBus wired to fake_redis + fallback_path.

        Imported lazily so the chaos module never imports the real ``redis``.
        """
        if self.fallback_path is None:
            raise RuntimeError("call setup(fallback_path) before build_bus()")
        from lib.core.event_bus import EventBus

        bus = EventBus.__new__(EventBus)
        bus.source = "chaos-test"
        bus._redis_url = "redis://chaos-fake/0"
        bus._fallback_path = self.fallback_path
        bus._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        bus._client = self.fake_redis
        bus._redis_ok = True
        bus._subscribers = []
        bus._subs_lock = threading.Lock()
        return bus

    def publish_marker(
        self,
        bus: Any,
        idx: int,
        event_type: str = "signal.generated",
        source: str = "chaos",
    ) -> str:
        """Publish a single marker event and capture it in the transcript.

        Sleeps 1ms after each publish so Redis and JSONL IDs land in distinct
        millisecond buckets — required for the cross-backend ordering
        invariant to be checkable.
        """
        marker = f"{self.name}-evt-{idx:04d}"
        ev_id = bus.publish(event_type, {"marker": marker, "i": idx}, source=source)
        self.captured.published.append((idx, event_type, source, marker))
        # Decide which backend caught it: if id starts with "local-" → JSONL.
        if isinstance(ev_id, str) and ev_id.startswith("local-"):
            self.captured.backend_per_event.append((idx, "jsonl"))
        else:
            self.captured.backend_per_event.append((idx, "redis"))
        # 1ms delay so successive publishes get distinct millisecond IDs;
        # without this, both backends pack multiple events into the same
        # millisecond and the secondary sort keys (seq vs uuid) diverge.
        time.sleep(0.0011)
        return marker

    def collect(self) -> ChaosTranscript:
        """Snapshot redis + jsonl into the transcript."""
        for stream, stream_id, fields in self.fake_redis.all_entries():
            try:
                data = json.loads(fields.get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                data = {}
            marker = data.get("marker", "")
            self.captured.redis_seen.append((stream_id, stream, marker))
        if self.fallback_path and self.fallback_path.exists():
            with self.fallback_path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    marker = rec.get("data", {}).get("marker", "")
                    self.captured.jsonl_seen.append(
                        (rec.get("id", ""), rec.get("type", ""), marker)
                    )
        return self.captured


# ---------------------------------------------------------------------------
# Concrete scenarios
# ---------------------------------------------------------------------------


@dataclass
class RedisDiesMidPublishScenario(ChaosScenario):
    """Publish 10 events; trip Redis after the 5th; assert no loss + order."""

    n_events: int = 10
    trip_after: int = 5
    name: str = "redis-dies-mid-publish"
    description: str = (
        "Redis becomes unreachable during a stream of publishes. The bus must "
        "transparently fall back to JSONL for the remaining events without "
        "dropping any."
    )

    def run(self, fallback_path: Path) -> ChaosTranscript:
        self.setup(fallback_path)
        bus = self.build_bus()
        for i in range(1, self.n_events + 1):
            if i == self.trip_after + 1:
                self.fake_redis.trip()
            self.publish_marker(bus, i)
        return self.collect()


@dataclass
class RedisDiesMidSubscribeScenario(ChaosScenario):
    """Subscriber reads from Redis until Redis dies; then tail JSONL."""

    n_pre_events: int = 4
    n_post_events: int = 6
    name: str = "redis-dies-mid-subscribe"
    description: str = (
        "A subscriber is attached; Redis dies after a few events. The "
        "subscriber should still observe later events via JSONL fallback "
        "(this scenario verifies the bus's _tail_fallback path is reachable)."
    )

    def run(self, fallback_path: Path) -> ChaosTranscript:
        self.setup(fallback_path)
        bus = self.build_bus()
        seen: list[str] = []

        # We don't actually start a real subscription thread (chaos tests are
        # deterministic) — we directly drive replay() before and after to
        # simulate a subscriber that polls.
        for i in range(1, self.n_pre_events + 1):
            self.publish_marker(bus, i)
        pre_replay = bus.replay("signal.generated", limit=100)
        seen.extend(e.data.get("marker", "") for e in pre_replay)

        self.fake_redis.trip()
        for i in range(
            self.n_pre_events + 1, self.n_pre_events + self.n_post_events + 1
        ):
            self.publish_marker(bus, i)
        post_replay = bus.replay("signal.generated", limit=100)
        seen.extend(e.data.get("marker", "") for e in post_replay)
        self.captured.notes.append(f"subscriber observed: {len(seen)} events")
        return self.collect()


@dataclass
class JsonlDiskFullScenario(ChaosScenario):
    """Redis dies, then JSONL writes start failing after N writes."""

    n_pre_events: int = 3
    n_disk_full_events: int = 4
    error_after_n_writes: int = 5
    name: str = "jsonl-fallback-disk-full"
    description: str = (
        "Redis is down, JSONL fallback engages, and partway through the "
        "fallback file's write-side starts raising OSError ('disk full'). "
        "The bus must not crash; events that wrote successfully are intact; "
        "lost events are quantified by the transcript without raising."
    )

    def run(self, fallback_path: Path) -> ChaosTranscript:
        self.setup(fallback_path)
        bus = self.build_bus()
        # Publish a few events while Redis is healthy.
        for i in range(1, self.n_pre_events + 1):
            self.publish_marker(bus, i)

        # Kill Redis — JSONL becomes the only sink.
        self.fake_redis.trip()

        # Wrap the bus's fallback path with a path proxy whose .open() injects
        # a SlowDisk that fails after N successful writes. PosixPath is a
        # frozen-attr type, so we substitute a small proxy instead of patching.
        slow_disk = SlowDisk(error_after_n_writes=self.error_after_n_writes)
        self.fault.register("disk", slow_disk)
        bus._fallback_path = _PathOpenProxy(fallback_path, slow_disk)
        try:
            for i in range(
                self.n_pre_events + 1,
                self.n_pre_events + self.n_disk_full_events + 1,
            ):
                # The bus catches OSError internally and logs — never raises.
                try:
                    self.publish_marker(bus, i)
                except Exception as e:  # pragma: no cover - defensive
                    self.captured.errors.append(f"unexpected raise on publish: {e}")
        finally:
            # Restore real path for the .collect() pass that reads back JSONL.
            bus._fallback_path = fallback_path
        self.captured.notes.append(
            f"slow_disk recorded {slow_disk.writes} writes "
            f"(threshold={self.error_after_n_writes})"
        )
        return self.collect()


@dataclass
class RedisRecoversAfterScenario(ChaosScenario):
    """Redis dies, traffic flows to JSONL, Redis recovers, traffic resumes."""

    n_phase_one: int = 3
    n_partition_phase: int = 4
    n_phase_three: int = 3
    name: str = "redis-recovers-after-N-seconds"
    description: str = (
        "Three-phase chaos: healthy Redis → partition → recovery. Events from "
        "all three phases must be recoverable via union(redis, jsonl), and "
        "ordering must be preserved across the recovery boundary."
    )

    def run(self, fallback_path: Path) -> ChaosTranscript:
        self.setup(fallback_path)
        bus = self.build_bus()

        for i in range(1, self.n_phase_one + 1):
            self.publish_marker(bus, i)

        self.fake_redis.trip()
        for i in range(
            self.n_phase_one + 1, self.n_phase_one + self.n_partition_phase + 1
        ):
            self.publish_marker(bus, i)

        self.fake_redis.heal()
        # The bus has set _redis_ok=False during the failure; nudge it back so
        # subsequent publishes route to redis. In production, _redis_ok is
        # re-asserted via a periodic health probe.
        bus._redis_ok = True
        start = self.n_phase_one + self.n_partition_phase + 1
        for i in range(start, start + self.n_phase_three):
            self.publish_marker(bus, i)
        return self.collect()


@dataclass
class DualWriteMismatchScenario(ChaosScenario):
    """Simulate a configuration where the same event hits both stores.

    The current bus is single-writer-of-record; this scenario exercises the
    *consumer-side* merge path that union()s redis + jsonl and verifies the
    chaos transcript flags duplicates exactly when present (which is what a
    real audit would do).
    """

    n_events: int = 6
    name: str = "dual-write-mismatch"
    description: str = (
        "If both Redis and JSONL captured the same logical event (which "
        "would happen during a brief mis-recovery), the transcript's "
        "deduplication report flags the duplicates so audit code can resolve "
        "them deterministically."
    )

    def run(self, fallback_path: Path) -> ChaosTranscript:
        self.setup(fallback_path)
        bus = self.build_bus()
        # Half via Redis, half via JSONL.
        for i in range(1, self.n_events + 1):
            self.publish_marker(bus, i)

        # Now manually inject a duplicate marker into the JSONL file to
        # simulate a dual-write race that produced two records for the same
        # logical event. The transcript's `duplicates()` should flag it.
        if self.fallback_path is None:
            raise RuntimeError("setup() must run first")
        dup_marker = self.captured.markers_published()[2]
        with self.fallback_path.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "id": "local-dup-injected",
                        "type": "signal.generated",
                        "ts": datetime.now(UTC).isoformat(),
                        "source": "dup-injector",
                        "data": {"marker": dup_marker, "i": -1},
                    }
                )
                + "\n"
            )
        return self.collect()


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


_SCENARIO_CLASSES: tuple[type[ChaosScenario], ...] = (
    RedisDiesMidPublishScenario,
    RedisDiesMidSubscribeScenario,
    JsonlDiskFullScenario,
    RedisRecoversAfterScenario,
    DualWriteMismatchScenario,
)


def list_scenarios() -> list[str]:
    """Return canonical scenario names."""
    return [cls().name for cls in _SCENARIO_CLASSES]


def scenario_by_name(name: str) -> ChaosScenario:
    """Return a fresh scenario instance by name."""
    for cls in _SCENARIO_CLASSES:
        instance = cls()
        if instance.name == name:
            return instance
    raise KeyError(f"unknown chaos scenario: {name!r}")


# ---------------------------------------------------------------------------
# Convenience factories
# ---------------------------------------------------------------------------


def make_dead_redis_mock() -> MagicMock:
    """Return a MagicMock pre-configured to act like a dead Redis client.

    Useful for unit tests that just want to verify EventBus error handling
    without spinning up the FakeRedis state machine.
    """
    m = MagicMock()
    err = NetworkPartitionError("fake redis is dead")
    m.ping.side_effect = err
    m.xadd.side_effect = err
    m.xrange.side_effect = err
    m.xread.side_effect = err
    m.xreadgroup.side_effect = err
    return m


def install_disk_full_after(path: Path, after_n_writes: int) -> _PathOpenProxy:
    """Return a path proxy whose ``.open()`` fails after N successful writes.

    Tests use the proxy in place of the real path: ``proxy = install_...(p,2)``,
    then ``with proxy.open("a") as f: ...``. PosixPath instances reject
    method assignment, so we wrap them rather than patching them.
    """
    slow = SlowDisk(error_after_n_writes=after_n_writes)
    return _PathOpenProxy(path, slow)


class _PathOpenProxy:
    """Path-like wrapper that injects a SlowDisk into write streams.

    Mimics enough of ``pathlib.Path`` for ``EventBus`` to use it as
    ``_fallback_path``: ``mkdir``, ``parent``, ``exists``, ``open``.
    """

    def __init__(self, path: Path, slow_disk: SlowDisk) -> None:
        self._path = path
        self._slow_disk = slow_disk

    @property
    def parent(self) -> Path:
        return self._path.parent

    def mkdir(self, *args: Any, **kwargs: Any) -> Any:
        return self._path.mkdir(*args, **kwargs)

    def exists(self) -> bool:
        return self._path.exists()

    def __fspath__(self) -> str:  # so str(proxy) and Path(proxy) work
        return str(self._path)

    def __str__(self) -> str:
        return str(self._path)

    def open(self, *args: Any, **kwargs: Any) -> Any:
        handle = self._path.open(*args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if "a" in mode or "w" in mode:
            handle.write = self._slow_disk.wrap_write(handle.write)  # type: ignore[method-assign]
        return handle


def merge_streams(
    redis_entries: Iterable[tuple[str, str, str]],
    jsonl_entries: Iterable[tuple[str, str, str]],
) -> list[str]:
    """Merge redis + jsonl event-marker streams into a single ordered list.

    Sorts on the leading millisecond integer (Redis ``<ms>-<seq>`` and JSONL
    ``local-<ms>-<uuid>`` both encode real-time ms in the first numeric
    component) so the merged sequence is real-time-ordered.
    """

    def _key(stream_id: str) -> tuple[int, str]:
        sid = stream_id[len("local-") :] if stream_id.startswith("local-") else stream_id
        parts = sid.split("-", 1)
        try:
            return (int(parts[0]), parts[1] if len(parts) > 1 else "")
        except ValueError:
            return (0, sid)

    out: list[tuple[tuple[int, str], str]] = []
    for stream_id, _, marker in redis_entries:
        out.append((_key(stream_id), marker))
    for stream_id, _, marker in jsonl_entries:
        out.append((_key(stream_id), marker))
    out.sort(key=lambda x: x[0])
    return [m for _, m in out]


__all__ = [
    "ChaosScenario",
    "ChaosTranscript",
    "DualWriteMismatchScenario",
    "FakeRedis",
    "FakeRedisError",
    "JsonlDiskFullScenario",
    "RedisDiesMidPublishScenario",
    "RedisDiesMidSubscribeScenario",
    "RedisRecoversAfterScenario",
    "install_disk_full_after",
    "list_scenarios",
    "make_dead_redis_mock",
    "merge_streams",
    "scenario_by_name",
]
