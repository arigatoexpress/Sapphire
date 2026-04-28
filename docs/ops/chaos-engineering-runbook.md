# Chaos Engineering Runbook

**Owner**: Reliability + platform engineering.
**Scope**: `lib/chaos/`, `tests/integration/test_event_bus_chaos.py`,
`tests/unit/test_chaos_fault_injector.py`.
**Posture**: chaos suite is unit-test shaped. **No production system is
ever touched.** The suite uses in-memory fakes for Redis and `tmp_path` for
all filesystem writes.

This runbook covers four operational topics:

1. How to **run** the chaos suite (everyday).
2. How to **add a scenario** (when a new failure mode is found in
   production or via review).
3. How the suite **gates live-capital flips** (release gate).
4. How to **compose primitives** for ad-hoc exploration during an incident
   review.

---

## 1. Running the suite

### Quick smoke (every commit)

```bash
cd ~/Code/Sapphire
/usr/local/bin/python3 -m pytest tests/integration/test_event_bus_chaos.py -q
/usr/local/bin/python3 -m pytest tests/unit/test_chaos_fault_injector.py -q
```

Both commands should print `0 failed` in well under a second. If anything
fails, **stop**. The chaos suite is the canary; a red chaos suite is more
serious than a red unit test because the bus is the spine of the system.

### Verbose run (when investigating a specific scenario)

```bash
/usr/local/bin/python3 -m pytest tests/integration/test_event_bus_chaos.py -v -k "redis_dies_mid_publish"
```

Replace the `-k` filter with `redis_dies_mid_subscribe`, `disk_full`,
`recovers`, or `dual_write` to drill into one scenario.

### Driving a single scenario from a Python REPL

```python
from lib.chaos import scenario_by_name
sc = scenario_by_name("redis-recovers-after-N-seconds")
t = sc.run("/tmp/bus.jsonl")
print(t.markers_published())            # what we asked for
print(t.markers_anywhere())              # what landed somewhere
print(t.lost_markers())                  # what fell through (should be empty)
print(t.duplicates())                    # double-recorded events
t.assert_zero_loss()
t.assert_no_duplicates()
t.assert_ordering_preserved()
```

Every transcript is fully self-describing — it carries the published
sequence, the per-backend resolution, and any captured errors.

### Listing available scenarios

```python
from lib.chaos import list_scenarios
list_scenarios()
# ['redis-dies-mid-publish', 'redis-dies-mid-subscribe',
#  'jsonl-fallback-disk-full', 'redis-recovers-after-N-seconds',
#  'dual-write-mismatch']
```

---

## 2. Adding a new scenario

A new chaos scenario is added when a real production incident exposes a
failure mode the existing scenarios don't cover, OR when a review (e.g.
diligence prep, reliability sprint) identifies a gap.

### Step 1: Name it

Use kebab-case: `redis-blips-during-burst`, `jsonl-line-truncated`,
`subscriber-callback-deadlocks`. The name becomes the dataclass-attribute
`name`, the `scenario_by_name()` key, and the test `-k` filter.

### Step 2: Subclass `ChaosScenario`

In `lib/chaos/event_bus_chaos.py`:

```python
@dataclass
class MyNewScenario(ChaosScenario):
    """One-line description of what failure this models."""

    n_events: int = 5
    name: str = "my-new-scenario"
    description: str = "Multi-line description for the product doc."

    def run(self, fallback_path: Path) -> ChaosTranscript:
        self.setup(fallback_path)
        bus = self.build_bus()
        # ... drive publishes / trip faults / call collect()
        return self.collect()
```

### Step 3: Register it

Append the class to `_SCENARIO_CLASSES` in `lib/chaos/event_bus_chaos.py`
and add the import to `lib/chaos/__init__.py`'s `from ... import` block
plus its `__all__`.

### Step 4: Add tests

Mirror the pattern in `tests/integration/test_event_bus_chaos.py`:

```python
def test_my_new_scenario_zero_loss(tmp_path):
    sc = MyNewScenario()
    transcript = sc.run(tmp_path / "bus.jsonl")
    transcript.assert_zero_loss()
```

At least 3 assertions per new scenario:
- `assert_zero_loss()` (or explicit "this scenario does lose N events; here
  is the count" — we want the loss quantified).
- `assert_no_duplicates()` (or explicit duplicate count assertion).
- A scenario-specific assertion that proves the failure mode you're
  modeling actually happened (not just "events flowed").

### Step 5: Update the product doc

Add a row to the **"Failure modes formally tested by Sapphire"** table in
`docs/products/chaos-engineering-0.1.0.md`. Bump to 0.2.0 once the new
scenario lands; keep the changelog inline.

### Step 6: Verify

```bash
/usr/local/bin/python3 -m pytest tests/integration/test_event_bus_chaos.py -v
```

All scenarios should still pass; your new scenario must pass; total time
must remain under 1 second.

---

## 3. Live-capital release gate

Sapphire's live-capital path (`HYPERLIQUID_TRADING_ENABLED=1` and the
Robinhood crypto path) consumes events from the bus. A bus failure with
live capital deployed is the worst-case operational event.

The release gate is **automated**:

```bash
/usr/local/bin/python3 -m pytest tests/integration/test_event_bus_chaos.py -q
# 0 failed required
```

If the chaos suite is red, **do not** flip a live-capital gate. The
heartbeat and kill-switch suites have their own gates; the chaos suite is
specifically the bus contract.

The pre-flight script in
`scripts/ops/production_readiness_sweep.py` includes the chaos suite as a
hard sub-check (see the production-readiness sprint history); a red chaos
suite causes the readiness sweep to FAIL.

---

## 4. Composing primitives for ad-hoc exploration

When investigating a recent incident, you may want to model a custom
failure that doesn't yet have a canonical scenario. Here are the patterns:

### Brownout: Redis flaps every 3rd call

```python
from lib.chaos.fault_injector import IntermittentErrorPolicy
from lib.chaos.event_bus_chaos import FakeRedis

fr = FakeRedis()
policy = IntermittentErrorPolicy(mode="every_n", every_n=3)
fr.attach_intermittent(policy)
# Now every 3rd Redis call (xadd, xrange, xread) raises FakeRedisError.
```

### Slow disk: 50ms per write

```python
from lib.chaos.fault_injector import SlowDisk

sleeps = []
disk = SlowDisk(write_latency_ms=50, sleep_fn=sleeps.append)
write_fn = disk.wrap_write(real_write_fn)
# Tests can advance the simulated clock from sleeps[].
```

### Clock skew: simulate a 2-minute drift

```python
from lib.chaos.fault_injector import ClockSkew

clock = ClockSkew()
publisher_now = clock.now()
clock.advance(120)
subscriber_now = clock.now()
# (subscriber_now - publisher_now).total_seconds() == 120
```

### Chained fault: Redis + slow disk + flapping partition

Compose them via `FaultInjector`:

```python
from lib.chaos.fault_injector import FaultInjector, NetworkPartition, SlowDisk

fi = FaultInjector(name="incident-2026-04-29")
fi.register("redis", NetworkPartition(name="redis"))
fi.register("disk", SlowDisk(write_latency_ms=200, error_after_n_writes=10))

fi.trip("redis")          # Redis goes down.
# ... publish events; observe JSONL writes via slow disk
fi.heal("redis")          # Redis recovers.
# Inspect fi.transcript for the per-action timeline.
```

`FaultInjector.transcript` is the source of truth for what fault actions
were applied in what order — useful for an incident postmortem.

---

## 5. Anti-patterns and red flags

### Don't use real Redis

```python
# WRONG — will dial 127.0.0.1:6379 on the operator's machine.
import redis
client = redis.Redis()
client.flushall()

# RIGHT — use FakeRedis and patch the bus's _client slot.
from lib.chaos.event_bus_chaos import FakeRedis
fr = FakeRedis()
bus._client = fr
```

### Don't write to `data/events/bus.jsonl`

```python
# WRONG — pollutes real production-shaped data.
bus = EventBus()  # uses default fallback path

# RIGHT — pass an explicit tmp_path.
bus = EventBus.__new__(EventBus)
bus._fallback_path = tmp_path / "bus.jsonl"
```

### Don't add `time.sleep()` in tests

The fault primitives use injected `sleep_fn` callables. Tests should pass
a fake sleep that mutates a `ClockSkew`. The chaos suite must remain
sub-second.

The one exception is the 1ms inter-publish sleep in
`ChaosScenario.publish_marker()` — this is **intentional** so that
successive publishes land in distinct millisecond buckets, which the
ordering invariant requires. A scenario that needs to publish 10,000
events would override `publish_marker` to skip the sleep and use a
dedicated sequence ID instead.

### Don't catch exceptions silently

If your scenario captures an exception that the bus shouldn't have raised,
record it in `transcript.errors` and assert against it. Silent catches are
how chaos tests turn into rubber stamps.

---

## 6. Telemetry and signal during a real chaos event

If a real Redis outage happens in production, the operator's first signal
is the bus log line:

```
WARNING lib.core.event_bus:event_bus.py event publish to redis failed (...) — using fallback
```

This line is structured: `bus.publish` catches the Redis exception, logs
the warning, and routes the rest of the publish call to JSONL. The
`data/events/bus.jsonl` file grows append-only.

When Redis recovers, **the bus does not auto-resume**. The current
implementation marks `_redis_ok = False` permanently for that bus
instance; a periodic health probe (run by the inference proxy and the
heartbeat daemon) is responsible for the eventual re-attempt. The chaos
scenario `redis-recovers-after-N-seconds` exercises the manual
`_redis_ok = True` re-arm path that ops uses during incident response.

The 0.2.0 backlog includes an automatic re-arm probe; the chaos test for
that lives at the `_recovery_probe_test` extension point already wired in
the ChaosTranscript.

---

## 7. Checklist for a new bus consumer

If you're adding a new component that subscribes to or publishes events,
walk this checklist:

- [ ] Component reads/writes through the bus, not directly through Redis.
- [ ] Component handles `bus.publish()` returning a `local-` prefixed ID
      (means the event went to JSONL, not Redis).
- [ ] Subscribers handle the `_tail_fallback` code path (it polls the
      JSONL file every second).
- [ ] Component has a regression test that exercises the chaos seam by
      using `FakeRedis` and `tmp_path`.
- [ ] If the component is on the live-capital critical path, the chaos
      suite for that consumer must be green before flipping the live gate.

---

## 8. Quick reference: invariants the suite enforces

| Invariant                  | What it means                                                   |
| -------------------------- | --------------------------------------------------------------- |
| zero-event-loss            | Every published event landed in Redis OR JSONL (or both).       |
| no-duplicates              | Across both stores, each marker appears at most once.           |
| ordering-preserved         | Real-time merge of both stores reproduces publish order.        |
| bus-does-not-crash         | Even with both backends failing, `bus.publish()` never raises.  |
| loss-quantified-on-failure | If both backends fail, the transcript reports the count.        |
| recovery-resumes-redis     | After heal, new publishes route back to Redis.                  |
| dup-detection-works        | If a duplicate sneaks through, the audit transcript flags it.   |

These are the invariants a buyer's reviewer will ask about. The chaos
suite verifies each one mechanically.
