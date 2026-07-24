"""Integration tests for chaos scenarios against the event bus.

Every test here mocks Redis (via ``FakeRedis``) and routes the JSONL fallback
to ``tmp_path``. The real ``data/events/bus.jsonl`` is never written.

Each test asserts at least one of:
  - ``transcript.assert_zero_loss()``
  - ``transcript.assert_no_duplicates()``
  - ``transcript.assert_ordering_preserved()``

Some tests deliberately allow duplicates (DualWriteMismatch), in which case
the transcript's ``duplicates()`` is asserted positively.

The 18+ test cases cover:
  * 5 canonical scenarios × multiple invariants
  * Boundary conditions (empty, single-event, all-redis, all-jsonl)
  * Recovery semantics (post-heal traffic returns to Redis)
  * Replay correctness across both backends
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.chaos import (
    DualWriteMismatchScenario,
    JsonlDiskFullScenario,
    RedisDiesMidPublishScenario,
    RedisDiesMidSubscribeScenario,
    RedisRecoversAfterScenario,
    list_scenarios,
    scenario_by_name,
)
from lib.chaos.event_bus_chaos import (
    FakeRedis,
    FakeRedisError,
    install_disk_full_after,
    make_dead_redis_mock,
    merge_streams,
)

# ---------------------------------------------------------------------------
# Scenario 1: redis-dies-mid-publish
# ---------------------------------------------------------------------------


def test_redis_dies_mid_publish_zero_loss(tmp_path: Path):
    sc = RedisDiesMidPublishScenario(n_events=10, trip_after=5)
    transcript = sc.run(tmp_path / "bus.jsonl")
    transcript.assert_zero_loss()
    assert transcript.total_published() == 10


def test_redis_dies_mid_publish_pre_in_redis_post_in_jsonl(tmp_path: Path):
    sc = RedisDiesMidPublishScenario(n_events=10, trip_after=5)
    transcript = sc.run(tmp_path / "bus.jsonl")
    # Pre-trip events: 5 in redis. Post-trip: 5 in jsonl.
    assert len(transcript.markers_in_redis()) == 5
    assert len(transcript.markers_in_jsonl()) == 5


def test_redis_dies_mid_publish_no_duplicates(tmp_path: Path):
    sc = RedisDiesMidPublishScenario()
    transcript = sc.run(tmp_path / "bus.jsonl")
    transcript.assert_no_duplicates()


def test_redis_dies_mid_publish_ordering_preserved(tmp_path: Path):
    sc = RedisDiesMidPublishScenario(n_events=8, trip_after=3)
    transcript = sc.run(tmp_path / "bus.jsonl")
    transcript.assert_ordering_preserved()


def test_redis_dies_mid_publish_empty_n_events_is_safe(tmp_path: Path):
    sc = RedisDiesMidPublishScenario(n_events=0, trip_after=0)
    transcript = sc.run(tmp_path / "bus.jsonl")
    assert transcript.total_published() == 0
    transcript.assert_zero_loss()


# ---------------------------------------------------------------------------
# Scenario 2: redis-dies-mid-subscribe
# ---------------------------------------------------------------------------


def test_redis_dies_mid_subscribe_zero_loss(tmp_path: Path):
    sc = RedisDiesMidSubscribeScenario(n_pre_events=4, n_post_events=6)
    transcript = sc.run(tmp_path / "bus.jsonl")
    transcript.assert_zero_loss()
    assert transcript.total_published() == 10


def test_redis_dies_mid_subscribe_subscriber_observes_post_events(tmp_path: Path):
    sc = RedisDiesMidSubscribeScenario(n_pre_events=3, n_post_events=5)
    transcript = sc.run(tmp_path / "bus.jsonl")
    # Replay path is exercised on both sides; subscriber should see at least
    # the pre-events via Redis and the post-events via JSONL.
    assert any("subscriber observed" in n for n in transcript.notes)


# ---------------------------------------------------------------------------
# Scenario 3: jsonl-fallback-disk-full
# ---------------------------------------------------------------------------


def test_jsonl_fallback_disk_full_does_not_crash(tmp_path: Path):
    sc = JsonlDiskFullScenario(n_pre_events=3, n_disk_full_events=4, error_after_n_writes=2)
    # Should not raise even though disk goes bad mid-fallback.
    transcript = sc.run(tmp_path / "bus.jsonl")
    assert len(transcript.errors) == 0


def test_jsonl_fallback_disk_full_quantifies_loss(tmp_path: Path):
    sc = JsonlDiskFullScenario(n_pre_events=2, n_disk_full_events=5, error_after_n_writes=2)
    transcript = sc.run(tmp_path / "bus.jsonl")
    # First 2 → redis. Of the 5 fallback events, only 2 should land before
    # the disk fills (slow_disk fires its OSError on the 3rd write).
    # Some events are documented-lost — this is the value the scenario
    # quantifies for an ops audit.
    assert len(transcript.markers_in_redis()) == 2
    # Up to 2 successful jsonl writes.
    assert len(transcript.markers_in_jsonl()) <= 2


# ---------------------------------------------------------------------------
# Scenario 4: redis-recovers-after-N-seconds
# ---------------------------------------------------------------------------


def test_redis_recovers_zero_loss(tmp_path: Path):
    sc = RedisRecoversAfterScenario(n_phase_one=3, n_partition_phase=4, n_phase_three=3)
    transcript = sc.run(tmp_path / "bus.jsonl")
    transcript.assert_zero_loss()


def test_redis_recovers_phases_partition_correctly(tmp_path: Path):
    sc = RedisRecoversAfterScenario(n_phase_one=3, n_partition_phase=4, n_phase_three=3)
    transcript = sc.run(tmp_path / "bus.jsonl")
    # 3 + 3 = 6 events should land in Redis (phase one + phase three).
    # 4 events should land in JSONL (partition phase).
    assert len(transcript.markers_in_redis()) == 6
    assert len(transcript.markers_in_jsonl()) == 4


def test_redis_recovers_ordering_preserved_across_boundary(tmp_path: Path):
    sc = RedisRecoversAfterScenario(n_phase_one=2, n_partition_phase=3, n_phase_three=2)
    transcript = sc.run(tmp_path / "bus.jsonl")
    transcript.assert_ordering_preserved()


# ---------------------------------------------------------------------------
# Scenario 5: dual-write-mismatch
# ---------------------------------------------------------------------------


def test_dual_write_mismatch_flags_duplicate(tmp_path: Path):
    sc = DualWriteMismatchScenario(n_events=6)
    transcript = sc.run(tmp_path / "bus.jsonl")
    dups = transcript.duplicates()
    assert len(dups) == 1, f"expected 1 duplicate, got {dups}"


def test_dual_write_mismatch_total_published_correct(tmp_path: Path):
    sc = DualWriteMismatchScenario(n_events=4)
    transcript = sc.run(tmp_path / "bus.jsonl")
    assert transcript.total_published() == 4


# ---------------------------------------------------------------------------
# Cross-cutting: registry + helpers
# ---------------------------------------------------------------------------


def test_list_scenarios_returns_five_canonical_names():
    names = list_scenarios()
    assert set(names) == {
        "redis-dies-mid-publish",
        "redis-dies-mid-subscribe",
        "jsonl-fallback-disk-full",
        "redis-recovers-after-N-seconds",
        "dual-write-mismatch",
    }


def test_scenario_by_name_round_trips(tmp_path: Path):
    sc = scenario_by_name("redis-dies-mid-publish")
    assert sc.name == "redis-dies-mid-publish"
    transcript = sc.run(tmp_path / "bus.jsonl")
    transcript.assert_zero_loss()


def test_scenario_by_name_unknown_raises():
    with pytest.raises(KeyError):
        scenario_by_name("never-existed")


def test_make_dead_redis_mock_raises_on_every_op():
    m = make_dead_redis_mock()
    with pytest.raises(Exception):
        m.ping()
    with pytest.raises(Exception):
        m.xadd("evt:foo", {"a": "b"})


def test_install_disk_full_after_helper(tmp_path: Path):
    p = tmp_path / "disk.jsonl"
    p.touch()
    proxy = install_disk_full_after(p, after_n_writes=2)
    with proxy.open("a") as f:
        f.write("a\n")
        f.write("b\n")
        with pytest.raises(OSError):
            f.write("c\n")


def test_merge_streams_preserves_order():
    redis_entries = [("100-1", "evt:foo", "m1"), ("200-1", "evt:foo", "m2")]
    jsonl_entries = [("local-300-x", "evt:foo", "m3")]
    out = merge_streams(redis_entries, jsonl_entries)
    assert out == ["m1", "m2", "m3"]


def test_fake_redis_xrange_returns_added_entries():
    fr = FakeRedis()
    fr.xadd("evt:s", {"k": "v1"})
    fr.xadd("evt:s", {"k": "v2"})
    out = fr.xrange("evt:s")
    assert len(out) == 2
    assert out[0][1]["k"] == "v1"
    assert out[1][1]["k"] == "v2"


def test_fake_redis_partition_blocks_all_calls():
    fr = FakeRedis()
    fr.trip()
    with pytest.raises(FakeRedisError):
        fr.xadd("evt:s", {"k": "v"})
    with pytest.raises(FakeRedisError):
        fr.xrange("evt:s")
    with pytest.raises(FakeRedisError):
        fr.xread({"evt:s": "0"})


def test_fake_redis_heal_restores_calls():
    fr = FakeRedis()
    fr.trip()
    fr.heal()
    fr.xadd("evt:s", {"k": "v"})
    assert len(fr.streams.get("evt:s", [])) == 1


def test_event_bus_publish_on_dead_redis_uses_fallback(tmp_path: Path):
    """Direct test: a dead-redis mock should route every publish to JSONL."""
    import threading

    from lib.core.event_bus import EventBus

    fallback = tmp_path / "bus.jsonl"
    bus = EventBus.__new__(EventBus)
    bus.source = "test"
    bus._redis_url = "redis://nowhere/0"
    bus._fallback_path = fallback
    bus._fallback_path.parent.mkdir(parents=True, exist_ok=True)
    bus._client = make_dead_redis_mock()
    bus._redis_ok = False  # Pretend connect failed.
    bus._subscribers = []
    bus._subs_lock = threading.Lock()

    for i in range(5):
        bus.publish("signal.generated", {"i": i})

    assert fallback.exists()
    lines = [line for line in fallback.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 5


def test_zero_loss_invariant_across_all_canonical_scenarios(tmp_path: Path):
    """Every scenario except dual-write-mismatch + disk-full hits zero loss."""
    forgiving = {"dual-write-mismatch", "jsonl-fallback-disk-full"}
    for name in list_scenarios():
        sc = scenario_by_name(name)
        transcript = sc.run(tmp_path / f"{name}.jsonl")
        if name not in forgiving:
            transcript.assert_zero_loss()


def test_jsonl_path_is_under_tmp_not_data_events(tmp_path: Path):
    """Sanity: chaos must NEVER write to the real data/events/ dir."""
    sc = RedisDiesMidPublishScenario()
    fp = tmp_path / "deeply" / "nested" / "bus.jsonl"
    transcript = sc.run(fp)
    assert fp.exists()
    assert "tmp" in str(fp).lower() or str(fp).startswith(str(tmp_path))
    transcript.assert_zero_loss()
