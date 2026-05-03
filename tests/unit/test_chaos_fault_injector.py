"""Unit tests for the chaos fault-injection primitives.

These tests exercise the primitives in isolation; they do NOT touch the
event bus. The integration suite at
``tests/integration/test_event_bus_chaos.py`` covers the composed scenarios.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lib.chaos.fault_injector import (
    ClockSkew,
    FaultInjector,
    IntermittentErrorPolicy,
    NetworkPartition,
    NetworkPartitionError,
    SlowDisk,
)

# ---------------------------------------------------------------------------
# ClockSkew
# ---------------------------------------------------------------------------


def test_clock_skew_starts_at_explicit_origin():
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    clock = ClockSkew(start=origin)
    assert clock.now() == origin


def test_clock_skew_advances_forward_only():
    clock = ClockSkew()
    t0 = clock.now()
    clock.advance(60)
    assert (clock.now() - t0).total_seconds() == 60


def test_clock_skew_rejects_negative_advance():
    clock = ClockSkew()
    with pytest.raises(ValueError):
        clock.advance(-1)


def test_clock_skew_reset_returns_to_origin():
    clock = ClockSkew()
    clock.advance(120)
    clock.reset()
    assert clock.skew_seconds == 0.0


def test_clock_skew_isoformat_is_iso8601():
    clock = ClockSkew()
    s = clock.isoformat()
    # Round-trip parse.
    parsed = datetime.fromisoformat(s)
    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# NetworkPartition
# ---------------------------------------------------------------------------


def test_network_partition_passes_through_when_healthy():
    p = NetworkPartition(name="redis")
    wrapped = p.protect(lambda x: x * 2)
    assert wrapped(5) == 10


def test_network_partition_raises_when_tripped():
    p = NetworkPartition(name="redis")
    wrapped = p.protect(lambda: "hello")
    p.trip()
    with pytest.raises(NetworkPartitionError) as ei:
        wrapped()
    assert "redis" in str(ei.value)


def test_network_partition_heals_after_trip():
    p = NetworkPartition(name="kafka")
    wrapped = p.protect(lambda: 42)
    p.trip()
    p.heal()
    assert wrapped() == 42


def test_network_partition_custom_exception_factory():
    class CustomErr(Exception):
        pass

    p = NetworkPartition(name="x", exception_factory=lambda m: CustomErr(f"boom: {m}"))
    wrapped = p.protect(lambda: None)
    p.trip()
    with pytest.raises(CustomErr):
        wrapped()


# ---------------------------------------------------------------------------
# SlowDisk
# ---------------------------------------------------------------------------


def test_slow_disk_no_latency_when_unconfigured():
    disk = SlowDisk()
    out = []
    wrapped = disk.wrap_write(lambda b: out.append(b))
    wrapped("hello")
    assert out == ["hello"]


def test_slow_disk_calls_sleep_fn_with_latency():
    sleeps: list[float] = []
    disk = SlowDisk(write_latency_ms=50, sleep_fn=sleeps.append)
    wrapped = disk.wrap_write(lambda b: None)
    wrapped("x")
    wrapped("y")
    assert sleeps == [0.050, 0.050]


def test_slow_disk_raises_oserror_after_threshold():
    disk = SlowDisk(error_after_n_writes=2)
    wrapped = disk.wrap_write(lambda b: None)
    wrapped("a")
    wrapped("b")
    with pytest.raises(OSError):
        wrapped("c")


def test_slow_disk_reset_zeroes_counter():
    disk = SlowDisk(error_after_n_writes=2)
    wrapped = disk.wrap_write(lambda b: None)
    wrapped("a")
    disk.reset()
    assert disk.writes == 0


# ---------------------------------------------------------------------------
# IntermittentErrorPolicy
# ---------------------------------------------------------------------------


def test_intermittent_every_n_fails_on_multiple():
    p = IntermittentErrorPolicy(mode="every_n", every_n=3)
    assert p.should_fail(1) is False
    assert p.should_fail(3) is True
    assert p.should_fail(6) is True
    assert p.should_fail(7) is False


def test_intermittent_after_n_fails_strictly_after():
    p = IntermittentErrorPolicy(mode="after_n", after_n=2)
    assert p.should_fail(1) is False
    assert p.should_fail(2) is False
    assert p.should_fail(3) is True


def test_intermittent_flaky_window_per_interval():
    p = IntermittentErrorPolicy(mode="flaky_window", windows=((3, 5), (8, 8)))
    assert p.should_fail(2) is False
    assert p.should_fail(3) is True
    assert p.should_fail(4) is True
    assert p.should_fail(5) is True
    assert p.should_fail(6) is False
    assert p.should_fail(8) is True
    assert p.should_fail(9) is False


def test_intermittent_unknown_mode_raises():
    p = IntermittentErrorPolicy(mode="surprise")
    with pytest.raises(ValueError):
        p.should_fail(1)


def test_intermittent_maybe_raise_advances_counter():
    raised = []
    p = IntermittentErrorPolicy(
        mode="every_n",
        every_n=2,
        exception_factory=lambda i: RuntimeError(f"#{i}"),
    )
    for _ in range(4):
        try:
            p.maybe_raise()
        except RuntimeError as e:
            raised.append(str(e))
    assert raised == ["#2", "#4"]


# ---------------------------------------------------------------------------
# FaultInjector composition
# ---------------------------------------------------------------------------


def test_fault_injector_register_and_trip():
    fi = FaultInjector()
    p = NetworkPartition(name="redis")
    fi.register("redis", p)
    fi.trip("redis")
    assert p.partitioned is True


def test_fault_injector_heal_propagates():
    fi = FaultInjector()
    p = NetworkPartition(name="redis")
    fi.register("redis", p)
    fi.trip("redis")
    fi.heal("redis")
    assert p.partitioned is False


def test_fault_injector_double_register_raises():
    fi = FaultInjector()
    p = NetworkPartition(name="redis")
    fi.register("redis", p)
    with pytest.raises(ValueError):
        fi.register("redis", p)


def test_fault_injector_unknown_primitive_raises():
    fi = FaultInjector()
    with pytest.raises(KeyError):
        fi.trip("does-not-exist")


def test_fault_injector_transcript_records_actions():
    fi = FaultInjector()
    p = NetworkPartition(name="r")
    fi.register("r", p)
    fi.trip("r")
    fi.heal("r")
    actions = [verb for verb, _, _ in fi.transcript]
    assert actions == ["register", "trip", "heal"]


def test_fault_injector_reset_all_calls_each():
    fi = FaultInjector()
    disk = SlowDisk(error_after_n_writes=1)
    wrapped = disk.wrap_write(lambda b: None)
    wrapped("x")
    fi.register("disk", disk)
    fi.reset_all()
    assert disk.writes == 0


def test_fault_injector_names_returns_keys():
    fi = FaultInjector()
    fi.register("a", NetworkPartition(name="a"))
    fi.register("b", NetworkPartition(name="b"))
    assert set(fi.names()) == {"a", "b"}


def test_fault_injector_trip_on_non_trippable_raises():
    """A plain object without trip() should raise TypeError."""

    class Dummy:
        pass

    fi = FaultInjector()
    fi.register("x", Dummy())
    with pytest.raises(TypeError):
        fi.trip("x")
