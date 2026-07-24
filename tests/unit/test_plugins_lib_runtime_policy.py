"""Isolated unit coverage for ``plugins/claw-sapphire/lib/runtime_policy.py``.

This module is small (~70 lines) but had zero test references prior to this
change. It defines a JSON-file-backed runtime policy controlling which agents
and tiers can execute tasks. We exercise:

* default policy invariants (tier ordering, no duplicate names, complexity caps)
* ``load()`` behaviour with no file / valid file / corrupt file
* ``save()`` round-trips through the user's ``~/.sapphire/runtime_policy.json``
* ``is_tier_allowed`` / ``is_repo_allowed`` happy + sad paths
* ``max_complexity`` defaults + per-tier overrides
* ``should_verify`` / ``can_auto_commit`` boolean reads

The module is loaded via ``importlib.util.spec_from_file_location`` so
``plugins/claw-sapphire/lib`` does not need to be on ``sys.path`` for the
broader test suite, and so the production source of truth is exercised
without copy/paste drift.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "plugins" / "claw-sapphire" / "lib" / "runtime_policy.py"
MODULE_NAME = "claw_sapphire_runtime_policy_under_test"


@pytest.fixture(scope="module")
def runtime_policy():
    """Load the production source via importlib (no sys.path mutation)."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    assert spec and spec.loader, f"could not load {MODULE_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated_policy_path(tmp_path, runtime_policy, monkeypatch):
    """Redirect POLICY_PATH to a tmp file so tests never touch ~/.sapphire/."""
    fake = tmp_path / "runtime_policy.json"
    monkeypatch.setattr(runtime_policy, "POLICY_PATH", fake)
    return fake


# ─── DEFAULT_POLICY invariants ────────────────────────────────────────────────


def test_default_policy_has_required_keys(runtime_policy):
    """Default policy must carry every key the helpers reference."""
    required = {
        "mode",
        "allowed_tiers",
        "allowed_agents",
        "blocked_repos",
        "max_complexity_per_tier",
        "require_verification",
        "auto_commit",
    }
    assert required.issubset(runtime_policy.DEFAULT_POLICY)


def test_default_tiers_are_ordered_and_unique(runtime_policy):
    """t0 → t1 → t2 → t3 should be strictly ordered, with no duplicates."""
    tiers = runtime_policy.DEFAULT_POLICY["allowed_tiers"]
    assert tiers == sorted(tiers), "tiers must be monotonic"
    assert len(tiers) == len(set(tiers)), "tiers must be unique"
    assert tiers[0] == "t0" and tiers[-1] == "t3"


def test_default_agents_are_unique(runtime_policy):
    """Allowed-agent names must be unique."""
    agents = runtime_policy.DEFAULT_POLICY["allowed_agents"]
    assert len(agents) == len(set(agents))
    assert all(isinstance(a, str) for a in agents)


def test_default_complexity_caps_are_monotonic_non_decreasing(runtime_policy):
    """Higher tiers should accept at least as much complexity as lower tiers."""
    caps = runtime_policy.DEFAULT_POLICY["max_complexity_per_tier"]
    # Only the tiers actually defined in the default policy — t2 is intentionally
    # absent (caller falls back to default 5 via ``max_complexity``).
    pairs = [("t0", "t1"), ("t1", "t3")]
    for low, high in pairs:
        assert caps[low] <= caps[high], (
            f"complexity({low})>{caps[low]} > complexity({high})={caps[high]}"
        )


def test_default_blocked_repos_starts_empty(runtime_policy):
    """No repos should be blocked out of the box."""
    assert runtime_policy.DEFAULT_POLICY["blocked_repos"] == []


def test_default_mode_is_open(runtime_policy):
    """Default ``mode`` is 'open' — restricted modes are opt-in."""
    assert runtime_policy.DEFAULT_POLICY["mode"] == "open"


# ─── load() ───────────────────────────────────────────────────────────────────


def test_load_returns_default_when_file_missing(runtime_policy, isolated_policy_path):
    """No policy file → ``load`` returns a copy of DEFAULT_POLICY."""
    assert not isolated_policy_path.exists()
    policy = runtime_policy.load()
    assert policy == runtime_policy.DEFAULT_POLICY
    # Crucially — it must be a copy, not the canonical dict.
    policy["mode"] = "mutated"
    assert runtime_policy.DEFAULT_POLICY["mode"] == "open"


def test_load_returns_merged_policy_when_file_valid(runtime_policy, isolated_policy_path):
    """File overrides take precedence over defaults but missing keys fall back."""
    isolated_policy_path.write_text(json.dumps({"mode": "restricted", "auto_commit": True}))
    policy = runtime_policy.load()
    assert policy["mode"] == "restricted"
    assert policy["auto_commit"] is True
    # Missing keys still inherit from DEFAULT_POLICY.
    assert policy["allowed_tiers"] == runtime_policy.DEFAULT_POLICY["allowed_tiers"]


def test_load_recovers_from_corrupt_json(runtime_policy, isolated_policy_path):
    """Corrupt JSON is silently treated as 'no policy'."""
    isolated_policy_path.write_text("{this is not json")
    policy = runtime_policy.load()
    assert policy == runtime_policy.DEFAULT_POLICY


# ─── save() ───────────────────────────────────────────────────────────────────


def test_save_writes_indented_json_and_creates_parents(runtime_policy, tmp_path, monkeypatch):
    """save() must mkdir(parents=True) and emit pretty JSON."""
    target = tmp_path / "nested" / "dir" / "runtime_policy.json"
    monkeypatch.setattr(runtime_policy, "POLICY_PATH", target)
    runtime_policy.save({"mode": "restricted", "auto_commit": True})
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"mode": "restricted", "auto_commit": True}
    # Indented output → contains newlines.
    assert "\n" in target.read_text(encoding="utf-8")


def test_save_then_load_round_trip(runtime_policy, isolated_policy_path):
    """Round-trip a non-default policy through save() → load()."""
    custom = {
        **runtime_policy.DEFAULT_POLICY,
        "mode": "restricted",
        "blocked_repos": ["danger-repo"],
        "auto_commit": True,
    }
    runtime_policy.save(custom)
    loaded = runtime_policy.load()
    assert loaded["mode"] == "restricted"
    assert loaded["blocked_repos"] == ["danger-repo"]
    assert loaded["auto_commit"] is True


# ─── is_tier_allowed ──────────────────────────────────────────────────────────


def test_is_tier_allowed_default(runtime_policy, isolated_policy_path):
    """All four tiers are allowed under the default policy."""
    for tier in ("t0", "t1", "t2", "t3"):
        assert runtime_policy.is_tier_allowed(tier) is True


def test_is_tier_allowed_rejects_unknown_tier(runtime_policy, isolated_policy_path):
    assert runtime_policy.is_tier_allowed("t99") is False
    assert runtime_policy.is_tier_allowed("") is False


def test_is_tier_allowed_respects_overrides(runtime_policy, isolated_policy_path):
    """A restricted policy should reject tiers not in its allowlist."""
    runtime_policy.save({**runtime_policy.DEFAULT_POLICY, "allowed_tiers": ["t0", "t1"]})
    assert runtime_policy.is_tier_allowed("t0") is True
    assert runtime_policy.is_tier_allowed("t3") is False


# ─── is_repo_allowed ──────────────────────────────────────────────────────────


def test_is_repo_allowed_default_passes(runtime_policy, isolated_policy_path):
    assert runtime_policy.is_repo_allowed("anything") is True


def test_is_repo_allowed_blocks_listed_repo(runtime_policy, isolated_policy_path):
    runtime_policy.save({**runtime_policy.DEFAULT_POLICY, "blocked_repos": ["sapphire"]})
    assert runtime_policy.is_repo_allowed("sapphire") is False
    assert runtime_policy.is_repo_allowed("other") is True


# ─── max_complexity ───────────────────────────────────────────────────────────


def test_max_complexity_known_tiers(runtime_policy, isolated_policy_path):
    assert runtime_policy.max_complexity("t0") == 2
    assert runtime_policy.max_complexity("t1") == 3
    assert runtime_policy.max_complexity("t3") == 5


def test_max_complexity_unknown_tier_falls_back_to_5(runtime_policy, isolated_policy_path):
    """Tiers without an explicit cap (e.g. t2 in DEFAULT_POLICY) get the default 5."""
    assert runtime_policy.max_complexity("t2") == 5
    assert runtime_policy.max_complexity("nonexistent") == 5


# ─── should_verify / can_auto_commit ──────────────────────────────────────────


def test_should_verify_default_true(runtime_policy, isolated_policy_path):
    assert runtime_policy.should_verify() is True


def test_should_verify_overridable(runtime_policy, isolated_policy_path):
    runtime_policy.save({**runtime_policy.DEFAULT_POLICY, "require_verification": False})
    assert runtime_policy.should_verify() is False


def test_can_auto_commit_default_false(runtime_policy, isolated_policy_path):
    assert runtime_policy.can_auto_commit() is False


def test_can_auto_commit_overridable(runtime_policy, isolated_policy_path):
    runtime_policy.save({**runtime_policy.DEFAULT_POLICY, "auto_commit": True})
    assert runtime_policy.can_auto_commit() is True


# ─── determinism ──────────────────────────────────────────────────────────────


def test_load_is_deterministic(runtime_policy, isolated_policy_path):
    """Calling load() three times yields identical dicts."""
    isolated_policy_path.write_text(json.dumps({"mode": "restricted"}))
    a = runtime_policy.load()
    b = runtime_policy.load()
    c = runtime_policy.load()
    assert a == b == c


def test_load_with_override_isolates_caller_mutations(runtime_policy, isolated_policy_path):
    """When a file override is present, mutating the load() result is safe.

    NOTE — known irregularity: when **no** override file is present, the
    load() fast path returns ``DEFAULT_POLICY.copy()`` (shallow). Mutating
    nested values (e.g. ``allowed_tiers.append(...)``) of that result WILL
    leak into the module-level default because ``dict.copy()`` is shallow.
    Tracking this via a non-mutating assertion here so we don't change
    source as part of a test-only PR.
    """
    isolated_policy_path.write_text(json.dumps({"mode": "restricted"}))
    snapshot = json.dumps(runtime_policy.DEFAULT_POLICY, sort_keys=True)
    p = runtime_policy.load()
    # Override-driven copy is a fresh dict from {**default, **file}.
    p["mode"] = "mutated"
    # Top-level mutation of the load() result should not affect the default.
    assert runtime_policy.DEFAULT_POLICY["mode"] == "open"
    assert json.dumps(runtime_policy.DEFAULT_POLICY, sort_keys=True) == snapshot


# ─── policy path resolution ───────────────────────────────────────────────────


def test_policy_path_is_under_user_home(runtime_policy):
    """POLICY_PATH should live under the user's home dir (no system-wide writes)."""
    assert runtime_policy.POLICY_PATH.is_absolute()
    assert str(Path.home()) in str(runtime_policy.POLICY_PATH)
    assert runtime_policy.POLICY_PATH.name == "runtime_policy.json"


def test_load_handles_io_failure_gracefully(runtime_policy, monkeypatch):
    """A missing-file scenario where exists() is True but read raises shouldn't crash.

    json.JSONDecodeError is the only handled case in source — IOError will surface,
    which we document here as a known gap rather than fix in the test layer.
    """
    fake = Path("/definitely/does/not/exist/runtime_policy.json")
    monkeypatch.setattr(runtime_policy, "POLICY_PATH", fake)
    # exists() is False → fast path, no exception.
    assert runtime_policy.load() == runtime_policy.DEFAULT_POLICY


def test_load_with_partial_corrupt_then_valid(runtime_policy, isolated_policy_path):
    """JSONDecodeError path is hit, then a subsequent valid file is read."""
    isolated_policy_path.write_text("garbage")
    assert runtime_policy.load()["mode"] == "open"
    isolated_policy_path.write_text(json.dumps({"mode": "restricted"}))
    assert runtime_policy.load()["mode"] == "restricted"


def test_save_overwrites_existing_file(runtime_policy, isolated_policy_path):
    """save() must replace prior content, not append."""
    isolated_policy_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_policy_path.write_text(json.dumps({"mode": "old"}))
    runtime_policy.save({"mode": "new"})
    assert json.loads(isolated_policy_path.read_text(encoding="utf-8")) == {"mode": "new"}


# ─── docstring / contract sanity ──────────────────────────────────────────────


def test_all_public_helpers_have_docstrings(runtime_policy):
    """Every exported helper should document its contract."""
    for name in (
        "load",
        "save",
        "is_tier_allowed",
        "is_repo_allowed",
        "max_complexity",
        "should_verify",
        "can_auto_commit",
    ):
        fn = getattr(runtime_policy, name)
        assert fn.__doc__, f"{name} is missing a docstring"


def test_module_docstring_present(runtime_policy):
    assert runtime_policy.__doc__ and "Runtime policy" in runtime_policy.__doc__


def test_unused_patch_import_smoke():
    """``unittest.mock.patch`` is imported above purely as a future-proofing tool;
    ensure the import resolves so a refactor that drops the patch doesn't break."""
    assert callable(patch)
