"""Sapphire chaos engineering — controlled fault injection against the event bus.

This package contains:
- ``fault_injector`` — reusable fault-injection primitives (clock skew, network
  partitions, slow disk, intermittent errors). Pure-Python; no real network or
  process-level chaos.
- ``event_bus_chaos`` — composed chaos scenarios specifically targeted at
  ``lib.core.event_bus.EventBus`` (Redis primary + JSONL fallback). Each scenario
  is a fixture + a small driver helper that produces a deterministic transcript
  the integration tests assert against.

Design rules (read before adding new scenarios):

1. **No real Redis touched.** Every chaos scenario operates against an in-memory
   ``FakeRedis`` shim or a ``MagicMock`` injected into the ``EventBus._client``
   slot. The operator's local Redis is never killed, restarted, or otherwise
   disturbed.

2. **No real filesystem writes.** All JSONL fallback paths route through
   ``tmp_path`` fixtures, captured-write sinks, or ``BytesIO`` adaptors so the
   real ``data/events/bus.jsonl`` is never written by chaos tests.

3. **Pure functions where possible.** Scenario factories return dataclasses or
   tuples; behavioral verbs (run / inject / heal) take an explicit ``EventBus``
   so the test owns the lifecycle.

4. **Two invariants every scenario asserts:**
     a. **Zero-event-loss** — every event the test publishes must end up in
        either the Redis-fake stream or the JSONL fallback exactly once
        (counted across both backing stores after the chaos heals).
     b. **Ordering preserved post-recovery** — for events with the same source,
        the publish order must be observable in the surviving record(s).

The chaos suite is purely additive — it never modifies the event bus
implementation; it only exercises its existing ``try / except / fallback``
seams.
"""

from __future__ import annotations

from lib.chaos.event_bus_chaos import (
    ChaosScenario,
    ChaosTranscript,
    DualWriteMismatchScenario,
    JsonlDiskFullScenario,
    RedisDiesMidPublishScenario,
    RedisDiesMidSubscribeScenario,
    RedisRecoversAfterScenario,
    list_scenarios,
    scenario_by_name,
)
from lib.chaos.fault_injector import (
    ClockSkew,
    FaultInjector,
    IntermittentErrorPolicy,
    NetworkPartition,
    SlowDisk,
)

__all__ = [
    "ChaosScenario",
    "ChaosTranscript",
    "ClockSkew",
    "DualWriteMismatchScenario",
    "FaultInjector",
    "IntermittentErrorPolicy",
    "JsonlDiskFullScenario",
    "NetworkPartition",
    "RedisDiesMidPublishScenario",
    "RedisDiesMidSubscribeScenario",
    "RedisRecoversAfterScenario",
    "SlowDisk",
    "list_scenarios",
    "scenario_by_name",
]
